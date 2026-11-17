"""Where Jarvis keeps its own data (notes). A plain JSON file in your home folder."""

import json
import os
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()


def data_dir() -> Path:
    override = os.environ.get("JARVIS_HOME")
    path = Path(override).expanduser() if override else Path.home() / ".jarvis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def notes_path() -> Path:
    return data_dir() / "notes.json"


def load_notes() -> list:
    path = notes_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_notes(notes: list) -> None:
    """Write atomically so a crash can never leave a half-written notes file."""
    path = notes_path()
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def locked():
    return _lock
