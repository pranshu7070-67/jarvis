"""Contacts and WhatsApp calling / messaging.

WhatsApp has no official way for other programs to place a call, so Jarvis does what you
would do by hand: it opens the chat with that person in the WhatsApp desktop app, then
presses WhatsApp's own call shortcut (Ctrl+Shift+C for voice, Ctrl+Shift+V for video).
It only ever calls people you have saved, and the number list stays on your computer
(~/.jarvis/contacts.json).
"""

import json
import os
import re
import subprocess
import tempfile
import time
import webbrowser
from typing import Optional
from urllib.parse import quote

from .. import platform_utils as pu
from .. import store
from ..registry import tool

_NAME = re.compile(r"^[\w .'\-]{1,40}$")


def _path():
    return store.data_dir() / "contacts.json"


def load_contacts() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(contacts: dict) -> None:
    path = _path()
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(contacts, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def normalize_number(raw: str) -> Optional[str]:
    """Digits with country code, e.g. '98765 43210' -> '919876543210' (10 digits assume India)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = os.environ.get("JARVIS_COUNTRY_CODE", "91").strip("+ ") + digits
    return digits if 11 <= len(digits) <= 15 else None


def _sound(name: str) -> str:
    """Rough spoken-sound key, so 'neerav' and 'nirav' (or 'Rahul'/'Raahul') compare equal."""
    n = re.sub(r"[^a-z]", "", (name or "").lower())
    for a, b in (("ph", "f"), ("ee", "i"), ("ea", "i"), ("oo", "u"), ("ou", "u"), ("w", "v"), ("y", "i"),
                 ("th", "t"), ("sh", "s"), ("kh", "k"), ("gh", "g"), ("bh", "b"), ("dh", "d"), ("ck", "k"), ("q", "k")):
        n = n.replace(a, b)
    n = re.sub(r"(.)\1+", r"\1", n)                  # aa -> a, ll -> l
    return n[:1] + re.sub(r"[aeiouh]", "", n[1:])     # keep first letter, then consonants only


def find_contact(name: str) -> Optional[tuple]:
    """Exact name, then part of a name, then the closest-sounding name (voice often mis-spells)."""
    import difflib
    want = (name or "").strip().lower()
    contacts = load_contacts()
    if not want or not contacts:
        return None
    for key, number in contacts.items():
        if key.lower() == want:
            return key, number
    part = [(k, v) for k, v in contacts.items() if want in k.lower()]
    if len(part) == 1:
        return part[0]
    key_w = _sound(want)
    scored = []
    for k, v in contacts.items():
        first = k.split()[0] if k.split() else k
        ratio = max(difflib.SequenceMatcher(None, want, k.lower()).ratio(),
                    difflib.SequenceMatcher(None, want, first.lower()).ratio())
        same_sound = key_w and key_w in (_sound(k), _sound(first))
        scored.append((1.0 if same_sound else ratio, k, v))
    scored.sort(reverse=True)
    best = scored[0]
    if best[0] >= 0.78 and (len(scored) == 1 or best[0] - scored[1][0] >= 0.1):
        return best[1], best[2]
    return None


@tool()
def add_contact(name: str, number: str) -> str:
    """Save a contact (name and phone number) so Jarvis can call or message them on WhatsApp.

    Args:
        name: The contact's name, e.g. Mom.
        number: Phone number with or without country code, e.g. 9876543210 or +919876543210.
    """
    name = (name or "").strip()
    if not _NAME.match(name):
        return "Error: use a plain name (letters, numbers, spaces)."
    digits = normalize_number(number)
    if not digits:
        return "Error: that doesn't look like a phone number. Include all digits, e.g. 9876543210."
    contacts = load_contacts()
    contacts[name] = digits
    _save(contacts)
    return f"Saved {name} ({'+' + digits[:-10]} {digits[-10:]})." if len(digits) > 10 else f"Saved {name}."


@tool()
def list_contacts() -> str:
    """List the saved contacts (names only)."""
    names = sorted(load_contacts())
    return "Contacts: " + ", ".join(names) if names else "No contacts yet. Say: save contact Mom 9876543210"


@tool(risk="confirm")
def delete_contact(name: str) -> str:
    """Remove a saved contact.

    Args:
        name: The contact's name.
    """
    contacts = load_contacts()
    hit = find_contact(name)
    if not hit:
        return f"Error: no contact called '{name}'."
    contacts.pop(hit[0], None)
    _save(contacts)
    return f"Removed {hit[0]}."


# ----------------------------------------------------------------- WhatsApp --

_VK = {"ctrl": 0x11, "shift": 0x10, "c": 0x43, "v": 0x56}


def _press(*keys: str) -> None:
    """Press a key combination on Windows."""
    import ctypes
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    codes = [_VK[k] for k in keys]
    for code in codes:
        user32.keybd_event(code, 0, 0, 0)
    for code in reversed(codes):
        user32.keybd_event(code, 0, 2, 0)


def _open_chat(number: str, text: str = "") -> None:
    uri = f"whatsapp://send?phone={number}" + (f"&text={quote(text)}" if text else "")
    try:
        os.startfile(uri)  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        webbrowser.open(f"https://wa.me/{number}" + (f"?text={quote(text)}" if text else ""))
        raise _WebOnly()


class _WebOnly(Exception):
    pass


@tool()
def whatsapp_call(name: str, video: bool = False) -> str:
    """Start a WhatsApp voice or video call to a saved contact (WhatsApp desktop app must be installed and logged in).

    Args:
        name: A saved contact's name, e.g. Mom.
        video: True for a video call, false for a voice call.
    """
    hit = find_contact(name)
    if not hit:
        return f"I don't have a contact called '{name}'. Say: save contact {name} 9876543210"
    if pu.current_os() != "Windows":
        return "Error: WhatsApp calling from Jarvis is Windows-only for now."
    try:
        _open_chat(hit[1])
    except _WebOnly:
        return (f"The WhatsApp desktop app isn't installed, so I opened the chat with {hit[0]} in your browser. "
                "Calls need the desktop app.")
    time.sleep(4)   # give WhatsApp time to open and focus the chat
    _press("ctrl", "shift", "v" if video else "c")
    return f"Calling {hit[0]} on WhatsApp ({'video' if video else 'voice'}). If nothing happened, click the call icon in the chat."


@tool()
def whatsapp_message(name: str, text: str = "") -> str:
    """Open a WhatsApp chat with a saved contact, with the message typed in. You press Enter to send it.

    Args:
        name: A saved contact's name.
        text: Optional message to pre-fill.
    """
    hit = find_contact(name)
    if not hit:
        return f"I don't have a contact called '{name}'. Say: save contact {name} 9876543210"
    try:
        _open_chat(hit[1], text)
    except _WebOnly:
        return f"Opened the chat with {hit[0]} in WhatsApp Web. Press Enter to send."
    return f"Opened your WhatsApp chat with {hit[0]}" + (". The message is typed in: press Enter to send." if text else ".")
