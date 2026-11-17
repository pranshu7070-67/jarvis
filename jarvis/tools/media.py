"""Spotify and media control.

Spotify: opens tracks, albums and playlists straight in the Spotify desktop app using
spotify: links, and adds ':play' so they start playing. Finding a track by NAME needs a
free Spotify developer app (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in .env); without
it, a search page opens in the app instead. Pasted open.spotify.com links always work.

Pause / next / previous use the system media keys, so they work for Spotify and most
other players.
"""

import base64
import os
import re
import subprocess
import time
import webbrowser
from typing import Optional

from .. import platform_utils as pu
from ..registry import tool

KINDS = ("track", "album", "playlist", "artist")
_SPOTIFY_URL = re.compile(
    r"^https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist|artist)/([A-Za-z0-9]{10,30})", re.I)
_SPOTIFY_URI = re.compile(r"^spotify:(track|album|playlist|artist):([A-Za-z0-9]{10,30})$", re.I)

_token = {"value": None, "expires": 0.0}


def parse_spotify_link(text: str) -> Optional[tuple]:
    """('track', id) for an open.spotify.com link or spotify: URI, else None."""
    text = (text or "").strip()
    m = _SPOTIFY_URL.match(text) or _SPOTIFY_URI.match(text)
    return (m.group(1).lower(), m.group(2)) if m else None


def spotify_uri(kind: str, item_id: str, autoplay: bool = True) -> str:
    uri = f"spotify:{kind}:{item_id}"
    return uri + ":play" if autoplay and kind in ("track", "album", "playlist", "artist") else uri


def _open_uri(uri: str) -> None:
    os_name = pu.current_os()
    if os_name == "Windows":
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
        except OSError:
            # Spotify app not installed / not registered: use the web player instead.
            parts = uri.split(":")
            if len(parts) >= 3 and parts[1] in KINDS:
                webbrowser.open(f"https://open.spotify.com/{parts[1]}/{parts[2]}")
            else:
                webbrowser.open("https://open.spotify.com/search/" + uri.split(":", 2)[-1])
    elif os_name == "Darwin":
        subprocess.Popen(["open", uri])
    else:
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _credentials() -> Optional[tuple]:
    cid, secret = os.environ.get("SPOTIFY_CLIENT_ID", ""), os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    return (cid, secret) if cid and secret else None


def _app_token() -> str:
    import requests
    if _token["value"] and time.time() < _token["expires"] - 30:
        return _token["value"]
    cid, secret = _credentials()  # type: ignore[misc]
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    resp = requests.post("https://accounts.spotify.com/api/token",
                         headers={"Authorization": f"Basic {auth}"},
                         data={"grant_type": "client_credentials"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _token.update(value=data["access_token"], expires=time.time() + data.get("expires_in", 3600))
    return _token["value"]


def search_spotify(query: str, kind: str) -> Optional[dict]:
    import requests
    resp = requests.get("https://api.spotify.com/v1/search",
                        headers={"Authorization": f"Bearer {_app_token()}"},
                        params={"q": query, "type": kind, "limit": 1}, timeout=10)
    resp.raise_for_status()
    items = [i for i in resp.json().get(f"{kind}s", {}).get("items", []) if i]
    if not items:
        return None
    item = items[0]
    by = ""
    if item.get("artists"):
        by = ", ".join(a["name"] for a in item["artists"])
    elif item.get("owner"):
        by = item["owner"].get("display_name", "")
    return {"id": item["id"], "name": item["name"], "by": by}


def find_without_keys(query: str, kind: str) -> Optional[tuple]:
    """Find a Spotify item by name with a plain web search (no developer keys needed)."""
    try:
        from ddgs import DDGS
        results = DDGS().text(f"site:open.spotify.com/{kind} {query}", max_results=5)
    except Exception:
        return None
    for r in results or []:
        parsed = parse_spotify_link(r.get("href", "") or r.get("url", ""))
        if parsed and parsed[0] == kind:
            title = re.sub(r"\s*[|\-].*Spotify.*$", "", r.get("title", "")).strip()
            return parsed[1], title
    return None


@tool()
def play_spotify(query: str, kind: str = "track") -> str:
    """Play a song, album, playlist or artist on Spotify by name, or play a pasted Spotify link.

    Args:
        query: Song / album / playlist / artist name, e.g. 'Blinding Lights The Weeknd', or a Spotify link.
        kind: One of track, album, playlist, artist.
    """
    query = (query or "").strip()
    if not query:
        return "Error: tell me what to play."
    parsed = parse_spotify_link(query)
    if parsed:
        _open_uri(spotify_uri(*parsed))
        return f"Playing your Spotify {parsed[0]} in the Spotify app."
    kind = (kind or "track").strip().lower()
    if kind not in KINDS:
        return f"Error: kind must be one of {', '.join(KINDS)}."
    if _credentials():
        found = search_spotify(query, kind)
        if found is None:
            return f"Error: Spotify has no {kind} matching '{query}'."
        _open_uri(spotify_uri(kind, found["id"]))
        by = f" by {found['by']}" if found["by"] else ""
        return f"Playing {found['name']}{by} on Spotify."
    hit = find_without_keys(query, kind)
    if hit:
        _open_uri(spotify_uri(kind, hit[0]))
        return f"Playing {hit[1] or query} on Spotify."
    from urllib.parse import quote
    _open_uri(f"spotify:search:{quote(query)}")
    return (f"I couldn't find an exact match, so I opened a Spotify search for '{query}'. "
            "Press play on the top result.")


# --------------------------------------------------------------- media keys --

_WIN_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}
_MAC_SCRIPT = {"play_pause": "playpause", "next": "next track", "previous": "previous track"}
_LINUX = {"play_pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}


def _press_windows_key(vk: int) -> None:
    import ctypes
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    scan = user32.MapVirtualKeyW(vk, 0)          # real scan code, like a physical key
    EXTENDED, KEYUP = 0x1, 0x2                   # media keys are "extended" keys
    user32.keybd_event(vk, scan, EXTENDED, 0)
    user32.keybd_event(vk, scan, EXTENDED | KEYUP, 0)


@tool()
def media_control(action: str) -> str:
    """Control whatever is playing: pause/resume, next song, previous song.

    Args:
        action: One of play_pause, next, previous, stop.
    """
    action = (action or "").strip().lower().replace(" ", "_")
    aliases = {"pause": "play_pause", "play": "play_pause", "resume": "play_pause", "skip": "next",
               "prev": "previous", "back": "previous"}
    action = aliases.get(action, action)
    if action not in _WIN_KEYS:
        return "Error: action must be play_pause, next, previous or stop."
    os_name = pu.current_os()
    if os_name == "Windows":
        _press_windows_key(_WIN_KEYS[action])
        return f"Sent '{action}' to your media player."
    if os_name == "Darwin":
        if action not in _MAC_SCRIPT:
            return "Error: that action isn't supported on macOS."
        ok, out = pu.run(["osascript", "-e", f'tell application "Spotify" to {_MAC_SCRIPT[action]}'])
        return f"Sent '{action}' to Spotify." if ok else f"Error: {out}"
    if not pu.which("playerctl"):
        return "Error: install playerctl (sudo apt install playerctl) to control media on Linux."
    ok, out = pu.run(["playerctl", _LINUX[action]])
    return f"Sent '{action}' to your media player." if ok else f"Error: {out}"
