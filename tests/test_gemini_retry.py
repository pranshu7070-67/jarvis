"""A Gemini 503 ("high demand") used to end the conversation. Now it retries, then tries backups."""

import pytest

pytest.importorskip("google.genai")

from jarvis.brain import GeminiBrain, describe_error, error_status  # noqa: E402


class Busy(Exception):
    def __init__(self, code=503, text="503 UNAVAILABLE. This model is currently experiencing high demand."):
        super().__init__(text)
        self.code = code


class FakeChat:
    def __init__(self, model, outcomes, log):
        self.model, self.outcomes, self.log = model, outcomes, log

    def send_message(self, text):
        self.log.append(self.model)
        script = self.outcomes.get(self.model, [])
        outcome = script.pop(0) if script else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return type("R", (), {"text": f"answer from {self.model}"})()

    def get_history(self):
        return ["earlier turn"]


def make(outcomes):
    log, sleeps, histories = [], [], []
    brain = GeminiBrain("fake-key", "main", [], "Linux", backups=("backup1", "backup2"), sleep=sleeps.append)

    def fake_make_chat(model, history=None):
        histories.append((model, history))
        return FakeChat(model, outcomes, log)

    brain._make_chat = fake_make_chat
    return brain, log, sleeps, histories


def test_a_brief_overload_is_retried_on_the_same_model():
    brain, log, sleeps, _ = make({"main": [Busy(), "ok"]})
    assert brain.ask("hi") == "answer from main"
    assert log == ["main", "main"] and len(sleeps) == 1


def test_a_long_overload_moves_to_the_backup_and_keeps_the_conversation():
    brain, log, sleeps, histories = make({"main": [Busy(), Busy()]})
    assert brain.ask("hi") == "answer from backup1"
    assert log == ["main", "main", "backup1"]
    assert histories[-1] == ("backup1", ["earlier turn"])


def test_the_working_model_is_remembered():
    brain, log, _, _ = make({"main": [Busy(), Busy()]})
    brain.ask("one")
    log.clear()
    brain.ask("two")
    assert log == ["backup1"]  # does not go back to retrying the overloaded model


def test_quota_exhaustion_switches_model_without_waiting():
    brain, log, sleeps, _ = make({"main": [Busy(429, "429 RESOURCE_EXHAUSTED")]})
    assert brain.ask("hi") == "answer from backup1"
    assert log == ["main", "backup1"] and sleeps == []


def test_a_missing_model_is_skipped():
    brain, log, _, _ = make({"main": [Busy(404, "404 NOT_FOUND model")]})
    assert brain.ask("hi") == "answer from backup1"


def test_a_bad_key_stops_immediately():
    brain, log, _, _ = make({"main": [Busy(400, "API key not valid")]})
    with pytest.raises(Busy):
        brain.ask("hi")
    assert log == ["main"]


def test_when_every_model_is_busy_the_last_error_is_raised():
    brain, log, _, _ = make({m: [Busy()] * 2 for m in ("main", "backup1", "backup2")})
    with pytest.raises(Busy):
        brain.ask("hi")
    assert log.count("backup2") == 2


def test_error_helpers():
    assert error_status(Busy()) == 503
    assert error_status(RuntimeError("503 UNAVAILABLE x")) == 503
    assert error_status(RuntimeError("something")) is None
    assert "busy" in describe_error(Busy())


def test_a_model_that_rejects_fast_mode_is_retried_normally():
    brain, log, _, _ = make({"main": [Busy(400, "400 INVALID_ARGUMENT. Request contains an invalid argument.")]})
    assert brain._fast is True
    assert brain.ask("hi") == "answer from main"
    assert brain._fast is False
