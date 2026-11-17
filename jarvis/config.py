"""Settings, read from environment variables (or a .env file)."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Config:
    gemini_key: Optional[str]
    groq_key: Optional[str]
    gemini_model: str
    groq_model: str
    env_file: Optional[str] = None  # which .env file was loaded, if any
    notes: tuple = ()  # friendly warnings, e.g. "your key was on the wrong line"

    @property
    def has_ai(self) -> bool:
        return bool(self.gemini_key or self.groq_key)


def _clean(value: Optional[str]) -> Optional[str]:
    """Strip spaces and stray quotes people paste around keys."""
    if not value:
        return None
    return value.strip().strip("\"'").strip() or None


def fix_swapped_keys(gemini: Optional[str], groq: Optional[str]) -> tuple:
    """Google keys start with 'AIza' and Groq keys with 'gsk_'. If one was pasted on the
    other's line, move it and say so. Returns (gemini, groq, notes)."""
    notes = []
    if groq and groq.startswith("AIza") and not (gemini and gemini.startswith("AIza")):
        notes.append("Your Google (Gemini) key was on the GROQ_API_KEY line. I'm using it as your "
                     "Gemini key; please move it to the GEMINI_API_KEY line in .env.")
        gemini, groq = groq, (gemini if gemini and gemini.startswith("gsk_") else None)
    elif gemini and gemini.startswith("gsk_") and not (groq and groq.startswith("gsk_")):
        notes.append("Your Groq key was on the GEMINI_API_KEY line. I'm using it as your Groq key; "
                     "please move it to the GROQ_API_KEY line in .env.")
        gemini, groq = None, gemini
    return gemini, groq, tuple(notes)


def load_config() -> Config:
    env_file = None
    try:
        from dotenv import find_dotenv, load_dotenv
        env_file = find_dotenv() or find_dotenv(usecwd=True) or None
        if env_file:
            load_dotenv(env_file)
    except ImportError:
        pass
    env = os.environ.get
    gemini, groq, notes = fix_swapped_keys(
        _clean(env("GEMINI_API_KEY") or env("GOOGLE_API_KEY")), _clean(env("GROQ_API_KEY")))
    return Config(
        gemini_key=gemini,
        groq_key=groq,
        # "-latest" aliases keep working when Google retires older model names.
        gemini_model=env("JARVIS_GEMINI_MODEL", "gemini-flash-latest"),
        groq_model=env("JARVIS_GROQ_MODEL", "openai/gpt-oss-120b"),
        env_file=env_file,
        notes=notes,
    )
