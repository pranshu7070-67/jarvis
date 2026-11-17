import inspect

from jarvis import registry, safety


def test_every_tool_is_registered_with_a_valid_risk():
    assert len(registry.REGISTRY) >= 14
    for name, t in registry.REGISTRY.items():
        assert t.name == name
        assert t.risk in ("safe", "confirm")
        assert t.summary


def test_power_tools_require_confirmation():
    for name in ("shutdown_computer", "restart_computer", "sleep_computer"):
        assert registry.REGISTRY[name].risk == "confirm"


def test_declined_action_does_not_run(monkeypatch):
    ran = []
    from jarvis.tools import system
    monkeypatch.setattr(system, "_power", lambda action: ran.append(action) or "ran")
    safety.set_confirmer(lambda prompt: False)
    result = registry.call("shutdown_computer")
    assert result.startswith("Cancelled")
    assert ran == []


def test_approved_action_runs(monkeypatch):
    ran = []
    from jarvis.tools import system
    monkeypatch.setattr(system, "_power", lambda action: ran.append(action) or "ran")
    prompts = []
    safety.set_confirmer(lambda prompt: prompts.append(prompt) or True)
    assert registry.call("restart_computer") == "ran"
    assert ran == ["restart"]
    assert "restart_computer" in prompts[0]


def test_tool_exceptions_become_error_strings():
    @registry.tool()
    def _boom(x: int) -> str:
        """Always fails."""
        raise RuntimeError("kaboom")

    try:
        assert registry.call("_boom", x=1) == "Error: kaboom"
    finally:
        registry.REGISTRY.pop("_boom", None)


def test_unknown_tool_and_bad_arguments():
    assert registry.call("nope").startswith("Error:")
    assert registry.call("set_volume", wrong=1).startswith("Error:")


def test_wrapper_keeps_the_original_signature_for_the_ai_sdk():
    fn = registry.REGISTRY["set_volume"].func
    assert list(inspect.signature(fn).parameters) == ["percent"]
    assert fn.__doc__
