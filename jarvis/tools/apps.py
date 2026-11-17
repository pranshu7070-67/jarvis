"""Open applications and websites."""

import os
import re
import subprocess
import webbrowser
from typing import Optional
from urllib.parse import urlparse

from .. import platform_utils as pu
from ..registry import tool

# Only plain app names are accepted from the AI / user: no shell characters.
_APP_NAME = re.compile(r"^[\w .+\-]{1,60}$")
_BARE_HOST = re.compile(r"^(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#]\S*)?$", re.I)

_ALIASES = {
    "Windows": {
        "calculator": "calc",
        "file explorer": "explorer",
        "explorer": "explorer",
        "files": "explorer",
        "task manager": "taskmgr",
        "settings": "ms-settings:",
        "paint": "mspaint",
        "terminal": "wt",
        "command prompt": "cmd",
        "edge": "msedge",
        "word": "winword",
        "powerpoint": "powerpnt",
        "snipping tool": "snippingtool",
    },
    "Darwin": {
        "settings": "System Settings",
        "files": "Finder",
        "chrome": "Google Chrome",
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
    },
    "Linux": {
        "calculator": "gnome-calculator",
        "files": "nautilus",
        "file manager": "nautilus",
        "terminal": "gnome-terminal",
        "settings": "gnome-control-center",
        "chrome": "google-chrome",
        "vscode": "code",
    },
}


def resolve_app_name(name: str) -> str:
    return _ALIASES.get(pu.current_os(), {}).get(name.strip().lower(), name.strip())


_WEB_FALLBACK = {"whatsapp": "https://web.whatsapp.com", "telegram": "https://web.telegram.org",
                 "instagram": "https://www.instagram.com", "netflix": "https://www.netflix.com"}


def _start_menu_app_id(name: str) -> Optional[str]:
    """Find an installed app (including Microsoft Store apps like WhatsApp) in the Start menu."""
    script = ('$n=$env:JARVIS_APP; $a=Get-StartApps | Where-Object { $_.Name -like "*$n*" } '
              '| Select-Object -First 1; if ($a) { $a.AppID }')
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             env={**os.environ, "JARVIS_APP": name}, capture_output=True, text=True,
                             timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    app_id = (out.stdout or "").strip().splitlines()
    return app_id[0].strip() if app_id and app_id[0].strip() else None


def _open_windows(name: str, target: str) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # 1. Anything in the Start menu, which covers Store apps such as WhatsApp.
    if target == name:   # not one of our built-in aliases (calc, explorer...)
        app_id = _start_menu_app_id(name)
        if app_id:
            subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app_id])
            return f"Opened {name}."
    # 2. Classic programs that Windows can find by name (chrome, notepad, calc...).
    if target != name or pu.which(target) or pu.which(target + ".exe"):
        subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=flags)
        return f"Asked Windows to open {name}."
    # 3. Not installed as an app: use the website version if there is one.
    web = _WEB_FALLBACK.get(name.lower())
    if web:
        webbrowser.open(web)
        return f"I couldn't find the {name} app, so I opened {web} in your browser."
    subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=flags)
    return f"Asked Windows to open {name}. If nothing opened, it may not be installed."


@tool()
def open_app(name: str) -> str:
    """Open an installed application by name, e.g. chrome, spotify, notepad, calculator.

    Args:
        name: The application name.
    """
    name = (name or "").strip()
    if not _APP_NAME.match(name):
        return "Error: that doesn't look like a plain application name."
    target = resolve_app_name(name)
    os_name = pu.current_os()

    if os_name == "Windows":
        return _open_windows(name, target)

    if os_name == "Darwin":
        ok, out = pu.run(["open", "-a", target])
        return f"Opened {name}." if ok else f"Error: couldn't open {name}. {out}"

    exe = pu.which(target) or pu.which(target.lower().replace(" ", "-"))
    if exe:
        subprocess.Popen([exe], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened {name}."
    if pu.which("gtk-launch"):
        ok, out = pu.run(["gtk-launch", target.lower().replace(" ", "-")])
        if ok:
            return f"Opened {name}."
    return f"Error: couldn't find an app called '{name}'."


def normalize_url(url: str) -> Optional[str]:
    """Return a safe http(s) URL or None."""
    url = (url or "").strip()
    if not url:
        return None
    if "://" not in url:
        # Bare input must look like a host (youtube.com, example.org/path), which
        # rules out things like "javascript:alert(1)" before a scheme is added.
        if not _BARE_HOST.match(url):
            return None
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return url


@tool()
def open_url(url: str) -> str:
    """Open a website in the default browser.

    Args:
        url: A web address such as https://youtube.com or youtube.com.
    """
    safe = normalize_url(url)
    if safe is None:
        return "Error: only http/https web addresses can be opened."
    webbrowser.open(safe)
    return f"Opened {safe} in your browser."
