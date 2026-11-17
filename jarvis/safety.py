"""Human-in-the-loop confirmation for risky actions.

Every tool marked ``risk="confirm"`` asks through :func:`confirm` before it runs.
The default asks on the terminal; a future GUI or voice front end can swap in its
own asker with :func:`set_confirmer`.
"""

import contextlib
import threading
from typing import Callable

Confirmer = Callable[[str], bool]


def _cli_confirm(prompt: str) -> bool:
    try:
        answer = input(f"  [!] {prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


_confirmer: Confirmer = _cli_confirm


def set_confirmer(fn: Confirmer) -> None:
    """Replace how confirmations are asked (used by tests and other front ends)."""
    global _confirmer
    _confirmer = fn


def reset_confirmer() -> None:
    global _confirmer
    _confirmer = _cli_confirm


_local = threading.local()


@contextlib.contextmanager
def override(fn: Confirmer):
    """Use a different confirmer for the current thread only (the web UI uses this so
    it never changes how the terminal asks)."""
    previous = getattr(_local, "fn", None)
    _local.fn = fn
    try:
        yield
    finally:
        _local.fn = previous


def confirm(prompt: str) -> bool:
    """Return True only if the user explicitly approves."""
    fn = getattr(_local, "fn", None) or _confirmer
    return bool(fn(prompt))
