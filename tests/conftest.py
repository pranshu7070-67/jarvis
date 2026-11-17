import pytest

import jarvis.tools  # noqa: F401  (registers every tool)
from jarvis import safety


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Tests never touch your real ~/.jarvis notes or settings."""
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path / "jarvis-home"))
    for var in ("JARVIS_CITY", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    yield
    safety.reset_confirmer()
