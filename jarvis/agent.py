"""The assistant: fast-path router first, AI brain for everything else."""

from typing import Callable, Optional

from . import registry
from .brain import BrainError
from .router import route as default_route

NO_AI_MESSAGE = (
    "I only understand simple commands right now (no API key is set). "
    "Add GEMINI_API_KEY to your .env file to unlock questions, research and natural language, "
    "then run 'python -m jarvis --check' to confirm it works. Type 'help' to see what works offline."
)


class Jarvis:
    def __init__(self, brain=None, router: Callable = default_route):
        self.brain = brain
        self.router = router

    def handle(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        prompt = text
        routed = self.router(text)
        if routed:
            name, kwargs = routed
            result = registry.call(name, **kwargs)
            if not result.startswith("Error:") or self.brain is None:
                return result
            # The quick path failed; let the AI try with the failure as context.
            prompt = f"{text}\n\n(A quick attempt failed with: {result} Please try another way.)"

        if self.brain is None:
            return NO_AI_MESSAGE
        try:
            return self.brain.ask(prompt)
        except BrainError as exc:
            return f"Error: the AI brain is unavailable ({exc}). Simple commands still work; type 'help'."
        except Exception as exc:  # never let a crash take the assistant down
            return f"Error: something went wrong while thinking ({exc})."
