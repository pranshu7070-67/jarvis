"""Quick notes, saved locally in ~/.jarvis/notes.json and shown in the notebook UI."""

import uuid
from datetime import datetime
from typing import Optional

from .. import store
from ..registry import tool


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def create_note(text: str, title: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("a note needs some text")
    note = {
        "id": uuid.uuid4().hex[:8],
        "title": (title or "").strip() or text.splitlines()[0][:40],
        "text": text,
        "created": _now(),
        "updated": _now(),
        "pinned": False,
    }
    with store.locked():
        notes = store.load_notes()
        notes.insert(0, note)
        store.save_notes(notes)
    return note


def update_note(note_id: str, text: Optional[str] = None, title: Optional[str] = None,
                pinned: Optional[bool] = None) -> dict:
    with store.locked():
        notes = store.load_notes()
        for note in notes:
            if note["id"] == note_id:
                if text is not None:
                    note["text"] = text
                if title is not None:
                    note["title"] = title.strip() or note["title"]
                if pinned is not None:
                    note["pinned"] = bool(pinned)
                note["updated"] = _now()
                store.save_notes(notes)
                return note
    raise KeyError(note_id)


def remove_note(note_id: str) -> bool:
    with store.locked():
        notes = store.load_notes()
        kept = [n for n in notes if n["id"] != note_id]
        if len(kept) == len(notes):
            return False
        store.save_notes(kept)
        return True


def all_notes() -> list:
    # Pinned notes first; sorted() is stable, so newest-first order is kept within each group.
    return sorted(store.load_notes(), key=lambda n: not n.get("pinned"))


def _line(n: dict) -> str:
    when = n["created"][:16].replace("T", " ")
    return f"[{n['id']}] {n['title']}  ({when})"


@tool()
def add_note(text: str, title: str = "") -> str:
    """Save a new note.

    Args:
        text: The note content.
        title: Optional short title. Defaults to the first line.
    """
    note = create_note(text, title)
    return f"Saved note [{note['id']}] '{note['title']}'."


@tool()
def list_notes(limit: int = 10) -> str:
    """List the most recent notes with their ids.

    Args:
        limit: How many notes to show.
    """
    notes = all_notes()[: max(1, min(int(limit), 50))]
    if not notes:
        return "You have no notes yet."
    return "\n".join(_line(n) for n in notes)


@tool()
def read_note(note_id: str) -> str:
    """Show the full text of one note.

    Args:
        note_id: The note's id from list_notes.
    """
    for n in store.load_notes():
        if n["id"] == note_id.strip():
            return f"{n['title']}\n\n{n['text']}"
    return f"Error: no note with id '{note_id}'."


@tool()
def search_notes(query: str) -> str:
    """Find notes whose title or text contains some words.

    Args:
        query: Words to look for.
    """
    needle = query.strip().lower()
    hits = [n for n in store.load_notes()
            if needle and (needle in n["text"].lower() or needle in n["title"].lower())]
    if not hits:
        return f"No notes match '{query}'."
    return "\n".join(_line(n) for n in hits[:20])


@tool(risk="confirm")
def delete_note(note_id: str) -> str:
    """Permanently delete a note.

    Args:
        note_id: The note's id from list_notes.
    """
    return "Note deleted." if remove_note(note_id.strip()) else f"Error: no note with id '{note_id}'."
