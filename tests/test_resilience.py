"""The things that went wrong on a real laptop: a rejected key crashed the program."""

import datetime

import pytest

from jarvis import cli
from jarvis.agent import Jarvis
from jarvis.brain import BrainError, FallbackBrain, GroqBrain, describe_error, system_prompt
from jarvis.config import Config, fix_swapped_keys, load_config


class FakeHTTPError(Exception):
    def __init__(self, status):
        super().__init__(f"{status} Client Error")
        self.response = type("R", (), {"status_code": status})()


class GoogleStyleError(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


@pytest.mark.parametrize("exc, expect", [
    (FakeHTTPError(401), "key was rejected"),
    (FakeHTTPError(403), "key was rejected"),
    (FakeHTTPError(429), "free-tier limit"),
    (FakeHTTPError(404), "model name"),
    (GoogleStyleError(400, "API key not valid. Please pass a valid API key."), "key was rejected"),
    (GoogleStyleError(429, "RESOURCE_EXHAUSTED"), "free-tier limit"),
    (RuntimeError("something odd\nsecond line"), "something odd"),
])
def test_describe_error_is_plain_language(exc, expect):
    assert expect in describe_error(exc)


def test_a_rejected_key_gives_a_message_not_a_crash():
    class Rejecting:
        name = "groq"
        def ask(self, text):
            raise FakeHTTPError(401)

    reply = Jarvis(FallbackBrain([Rejecting()])).handle("who is the president of india")
    assert reply.startswith("Error:") and "key was rejected" in reply and "Traceback" not in reply


def test_agent_survives_any_brain_exception():
    class Broken:
        def ask(self, text):
            raise ValueError("boom")

    assert "boom" in Jarvis(Broken()).handle("tell me a joke")


# ----------------------------------------------------------- key mix-ups --

def test_google_key_on_the_groq_line_is_moved_with_a_note():
    gemini, groq, notes = fix_swapped_keys(None, "AIzaSyExample")
    assert (gemini, groq) == ("AIzaSyExample", None) and "GEMINI_API_KEY" in notes[0]


def test_groq_key_on_the_gemini_line_is_moved():
    gemini, groq, notes = fix_swapped_keys("gsk_example", None)
    assert (gemini, groq) == (None, "gsk_example") and notes


def test_both_keys_swapped_are_fully_swapped():
    assert fix_swapped_keys("gsk_a", "AIza_b")[:2] == ("AIza_b", "gsk_a")


def test_correct_keys_are_untouched():
    assert fix_swapped_keys("AIza_b", "gsk_a") == ("AIza_b", "gsk_a", ())


def test_load_config_strips_quotes_and_spaces(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", ' "AIzaSyExample" ')
    monkeypatch.setenv("GROQ_API_KEY", "")
    cfg = load_config()
    assert cfg.gemini_key == "AIzaSyExample" and cfg.groq_key is None


def test_load_config_fixes_a_swapped_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "AIzaSyExample")
    cfg = load_config()
    assert cfg.gemini_key == "AIzaSyExample" and cfg.groq_key is None and cfg.notes


# ---------------------------------------------------- prompt and payload --

def test_prompt_tells_the_ai_to_search_for_current_facts_and_knows_the_date():
    prompt = system_prompt("Windows")
    assert "web_search FIRST" in prompt and "president" in prompt
    assert datetime.date.today().strftime("%Y") in prompt


def test_groq_request_omits_an_empty_tools_list():
    sent = []

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "OK"}}]}

    brain = GroqBrain("k", "m", {}, "Linux", post=lambda url, headers, json, timeout: sent.append(json) or Resp())
    assert brain.ask("hi") == "OK"
    assert "tools" not in sent[0] and "tool_choice" not in sent[0]


# --------------------------------------------------------------- --check ---

def test_check_without_keys_explains_what_to_do(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda: Config(None, None, "m", "m"))
    monkeypatch.setattr(cli.registry, "call", lambda *a, **k: "ok")
    assert cli.run_check() == 1
    out = capsys.readouterr().out
    assert "NOT FOUND" in out and "GEMINI_API_KEY" in out


def test_check_reports_a_rejected_key(monkeypatch, capsys):
    import jarvis.brain as brain_mod

    class Rejecting:
        def __init__(self, *a, **k): pass
        def ask(self, text): raise FakeHTTPError(401)

    monkeypatch.setattr(cli, "load_config", lambda: Config(None, "gsk_x", "m", "m"))
    monkeypatch.setattr(brain_mod, "GroqBrain", Rejecting)
    monkeypatch.setattr(cli.registry, "call", lambda *a, **k: "ok")
    assert cli.run_check() == 1
    out = capsys.readouterr().out
    assert "Groq" in out and "FAIL" in out and "key was rejected" in out
