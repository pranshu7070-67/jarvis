import json
from typing import Optional

import pytest

from jarvis import registry
from jarvis.agent import Jarvis, NO_AI_MESSAGE
from jarvis.brain import BrainError, FallbackBrain, GroqBrain, create_brain, function_schema
from jarvis.config import Config


# -------------------------------------------------------------- schema ----

def test_function_schema_from_signature_and_docstring():
    def demo(query: str, count: int = 5, strict: Optional[bool] = None) -> str:
        """Do a demo search.

        Args:
            query: What to look for.
            count: How many.
        """

    schema = function_schema(demo)["function"]
    assert schema["name"] == "demo"
    assert schema["description"] == "Do a demo search."
    props = schema["parameters"]["properties"]
    assert props["query"] == {"type": "string", "description": "What to look for."}
    assert props["count"]["type"] == "integer"
    assert props["strict"]["type"] == "boolean"
    assert schema["parameters"]["required"] == ["query"]


def test_every_registered_tool_has_a_valid_schema():
    for t in registry.REGISTRY.values():
        s = function_schema(t.func)["function"]
        assert s["name"] == t.name and s["description"]
        assert s["parameters"]["type"] == "object"


# ---------------------------------------------------------------- Groq ----

class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self): pass
    def json(self): return self._payload


def tool_call_message(name, args, call_id="c1"):
    return {"choices": [{"message": {"content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}


def text_message(text):
    return {"choices": [{"message": {"content": text}}]}


def test_groq_brain_runs_tools_then_answers():
    replies = [tool_call_message("echo", {"word": "hi"}), text_message("Done: HI")]
    sent = []

    def post(url, headers, json, timeout):
        sent.append(json)
        return FakeResponse(replies.pop(0))

    seen = []
    def echo(word: str) -> str:
        """Shout a word.

        Args:
            word: The word.
        """
        seen.append(word)
        return word.upper()

    brain = GroqBrain("key", "model", {"echo": echo}, "Linux", post=post)
    assert brain.ask("shout hi") == "Done: HI"
    assert seen == ["hi"]
    tool_msgs = [m for m in brain.messages if m["role"] == "tool"]
    assert tool_msgs[0]["content"] == "HI"
    assert sent[0]["tools"][0]["function"]["name"] == "echo"


def test_groq_brain_survives_bad_tool_calls():
    replies = [tool_call_message("missing", {}), text_message("ok")]
    brain = GroqBrain("k", "m", {}, "Linux", post=lambda *a, **k: FakeResponse(replies.pop(0)))
    assert brain.ask("x") == "ok"
    assert "unknown tool" in [m for m in brain.messages if m["role"] == "tool"][0]["content"]


def test_groq_brain_stops_runaway_loops():
    brain = GroqBrain("k", "m", {}, "Linux",
                      post=lambda *a, **k: FakeResponse(tool_call_message("loop", {})))
    assert "too many steps" in brain.ask("x")


# ------------------------------------------------------------- fallback ---

class Stub:
    def __init__(self, name, reply=None, fail=False):
        self.name, self.reply, self.fail = name, reply, fail
    def ask(self, text):
        if self.fail:
            raise RuntimeError("429 quota exceeded")
        return self.reply


def test_fallback_uses_the_next_brain():
    brain = FallbackBrain([Stub("gemini", fail=True), Stub("groq", reply="from groq")])
    assert brain.ask("hi") == "from groq"


def test_fallback_raises_when_everything_fails():
    with pytest.raises(BrainError) as exc:
        FallbackBrain([Stub("a", fail=True), Stub("b", fail=True)]).ask("hi")
    assert "a:" in str(exc.value) and "b:" in str(exc.value)


def test_create_brain_without_keys_is_none():
    cfg = Config(None, None, "m", "m")
    assert create_brain(cfg, [], {}, "Linux") is None
    assert not cfg.has_ai


def test_create_brain_groq_only_is_wrapped_so_failures_cannot_crash():
    cfg = Config(None, "gk", "m", "gm")
    brain = create_brain(cfg, [], {}, "Linux")
    assert isinstance(brain, FallbackBrain)
    assert isinstance(brain.brains[0], GroqBrain)


# ---------------------------------------------------------------- agent ---

class RecordingBrain:
    name = "rec"
    def __init__(self): self.asked = []
    def ask(self, text): self.asked.append(text); return "AI reply"


def test_simple_commands_never_touch_the_ai(monkeypatch):
    monkeypatch.setattr(registry, "call", lambda tool_name, /, **kw: f"called {tool_name} {kw}")
    brain = RecordingBrain()
    assert Jarvis(brain).handle("volume 30") == "called set_volume {'percent': 30}"
    assert brain.asked == []


def test_complex_requests_go_to_the_ai():
    brain = RecordingBrain()
    assert Jarvis(brain).handle("research the best budget DACs") == "AI reply"
    assert brain.asked == ["research the best budget DACs"]


def test_failed_quick_path_falls_back_to_the_ai(monkeypatch):
    monkeypatch.setattr(registry, "call", lambda tool_name, /, **kw: "Error: couldn't find an app called 'youtube'.")
    brain = RecordingBrain()
    assert Jarvis(brain).handle("open youtube") == "AI reply"
    assert "quick attempt failed" in brain.asked[0]


def test_failed_quick_path_without_ai_returns_the_error(monkeypatch):
    monkeypatch.setattr(registry, "call", lambda tool_name, /, **kw: "Error: nope")
    assert Jarvis().handle("open youtube") == "Error: nope"


def test_no_ai_message_for_non_commands():
    assert Jarvis().handle("tell me a joke") == NO_AI_MESSAGE


def test_brain_failure_is_reported_not_raised():
    class Dead:
        def ask(self, text): raise BrainError("gemini: quota")
    reply = Jarvis(Dead()).handle("tell me a joke")
    assert reply.startswith("Error:") and "quota" in reply


def test_empty_input():
    assert Jarvis().handle("   ") == ""
