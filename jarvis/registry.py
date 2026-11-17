"""Tool registry.

Tools register themselves with ``@tool``. The AI brain and the fast-path router both
call the *same wrapped functions*, so the safety check cannot be bypassed by either.

Conventions for tool functions:
- Type-hint every parameter with str, int, float, bool or Optional[...] of those.
- Write a docstring: first line is the description the AI sees, and an ``Args:``
  section documents each parameter.
- Return a short string. Failures return text starting with ``Error:``.
"""

import functools
import inspect
from dataclasses import dataclass
from typing import Callable

from . import safety


@dataclass(frozen=True)
class Tool:
    name: str
    func: Callable
    risk: str
    summary: str


REGISTRY: dict = {}


def tool(risk: str = "safe"):
    """Register a function as a tool. risk is "safe" or "confirm"."""
    if risk not in ("safe", "confirm"):
        raise ValueError("risk must be 'safe' or 'confirm'")

    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if risk == "confirm":
                try:
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    shown = ", ".join(f"{k}={v!r}" for k, v in bound.arguments.items())
                except TypeError:
                    shown = ""
                if not safety.confirm(f"Allow {fn.__name__}({shown})?"):
                    return "Cancelled: the user declined this action."
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # tools must never crash the assistant
                return f"Error: {exc}"

        summary = (inspect.getdoc(fn) or "").splitlines()[0] if fn.__doc__ else fn.__name__
        REGISTRY[fn.__name__] = Tool(fn.__name__, wrapper, risk, summary)
        return wrapper

    return decorator


def call(tool_name: str, /, **kwargs) -> str:
    """Run a tool by name. The name is positional-only because tools may have a
    parameter called ``name`` of their own (open_app does)."""
    entry = REGISTRY.get(tool_name)
    if entry is None:
        return f"Error: unknown tool '{tool_name}'"
    return str(entry.func(**kwargs))


def callables() -> list:
    return [t.func for t in REGISTRY.values()]


def by_name() -> dict:
    return {name: t.func for name, t in REGISTRY.items()}
