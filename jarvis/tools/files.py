"""Find and open files and folders."""

import os
import time
from pathlib import Path

from .. import platform_utils as pu
from ..registry import tool

# Opening these would *run* code rather than show a document, so they are refused.
BLOCKED_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".psm1", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".lnk", ".reg", ".dll", ".jar", ".sh", ".bash", ".command",
    ".app", ".pkg", ".dmg", ".run", ".appimage", ".desktop", ".py", ".pl", ".rb",
}

_SKIP_DIRS = {"node_modules", "__pycache__", "site-packages", "AppData", "Library", "venv", ".venv"}


def is_blocked(path: Path) -> bool:
    return path.suffix.lower() in BLOCKED_EXTENSIONS


@tool()
def open_path(path: str) -> str:
    """Open a file or folder with its default application.

    Args:
        path: Full path to a file or folder. ~ means the home folder.
    """
    target = Path(path).expanduser()
    if not target.exists():
        return f"Error: '{path}' does not exist."
    target = target.resolve()
    if target.is_file() and is_blocked(target):
        return "Error: for safety I won't launch program or script files."
    os_name = pu.current_os()
    if os_name == "Windows":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return f"Opened {target}."
    ok, out = pu.run(["open" if os_name == "Darwin" else "xdg-open", str(target)])
    return f"Opened {target}." if ok else f"Error: {out}"


@tool()
def find_files(query: str, folder: str = "~", max_results: int = 15) -> str:
    """Search for files or folders whose name contains some text.

    Args:
        query: Text to look for in the file name (case-insensitive).
        folder: Folder to search in. Defaults to the home folder.
        max_results: Maximum number of matches to return.
    """
    root = Path(folder).expanduser()
    if not root.is_dir():
        return f"Error: '{folder}' is not a folder."
    needle = query.strip().lower()
    if not needle:
        return "Error: give me something to search for."
    limit = max(1, min(int(max_results), 50))
    deadline = time.monotonic() + 8
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
        for name in dirnames + filenames:
            if needle in name.lower():
                found.append(str(Path(dirpath) / name))
                if len(found) >= limit:
                    return "\n".join(found)
        if time.monotonic() > deadline:
            break
    return "\n".join(found) if found else f"No files matching '{query}' in {root}."
