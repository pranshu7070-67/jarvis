"""Checks that our tool functions are accepted by the real google-genai SDK.

No network and no API key needed: it only builds the function declarations.
"""

import pytest

pytest.importorskip("google.genai")

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from jarvis import registry  # noqa: E402


def test_every_tool_converts_to_a_gemini_function_declaration():
    client = genai.Client(api_key="not-a-real-key")
    for t in registry.REGISTRY.values():
        decl = types.FunctionDeclaration.from_callable(client=client, callable=t.func)
        assert decl.name == t.name
        assert decl.description
