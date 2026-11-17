"""OS-specific tools, tested by capturing the commands they would run."""

import pytest

from jarvis import platform_utils as pu
from jarvis import registry
from jarvis.tools import apps, files, system


@pytest.fixture
def recorder(monkeypatch):
    calls = []
    monkeypatch.setattr(pu, "run", lambda cmd, timeout=10: calls.append(cmd) or (True, ""))
    return calls


def fake_os(monkeypatch, name, available=()):
    monkeypatch.setattr(pu, "current_os", lambda: name)
    monkeypatch.setattr(pu, "which", lambda exe: f"/usr/bin/{exe}" if exe in available else None)


def test_volume_linux_pactl(monkeypatch, recorder):
    fake_os(monkeypatch, "Linux", available=("pactl",))
    assert registry.call("set_volume", percent=40) == "Volume set to 40%."
    assert recorder == [["pactl", "set-sink-volume", "@DEFAULT_SINK@", "40%"]]


def test_volume_linux_falls_back_to_amixer(monkeypatch, recorder):
    fake_os(monkeypatch, "Linux", available=("amixer",))
    registry.call("set_volume", percent=10)
    assert recorder == [["amixer", "sset", "Master", "10%"]]


def test_volume_linux_with_no_tools(monkeypatch, recorder):
    fake_os(monkeypatch, "Linux")
    assert registry.call("set_volume", percent=10).startswith("Error:")
    assert recorder == []


def test_volume_is_clamped(monkeypatch, recorder):
    fake_os(monkeypatch, "Darwin")
    registry.call("set_volume", percent=250)
    registry.call("set_volume", percent=-5)
    assert recorder[0][-1] == "set volume output volume 100"
    assert recorder[1][-1] == "set volume output volume 0"


def test_mute_mac(monkeypatch, recorder):
    fake_os(monkeypatch, "Darwin")
    registry.call("set_mute", muted=True)
    assert recorder == [["osascript", "-e", "set volume output muted true"]]


def test_brightness_linux(monkeypatch, recorder):
    fake_os(monkeypatch, "Linux", available=("brightnessctl",))
    registry.call("set_brightness", percent=55)
    assert recorder == [["brightnessctl", "set", "55%"]]


def test_brightness_mac_needs_helper(monkeypatch, recorder):
    fake_os(monkeypatch, "Darwin")
    assert "brew install brightness" in registry.call("set_brightness", percent=50)


def test_lock_windows(monkeypatch, recorder):
    fake_os(monkeypatch, "Windows")
    assert registry.call("lock_screen") == "Screen locked."
    assert recorder == [["rundll32.exe", "user32.dll,LockWorkStation"]]


@pytest.mark.parametrize("os_name, action, expected", [
    ("Linux", "shutdown", ["systemctl", "poweroff"]),
    ("Linux", "restart", ["systemctl", "reboot"]),
    ("Windows", "shutdown", ["shutdown", "/s", "/t", "10"]),
    ("Darwin", "sleep", ["pmset", "sleepnow"]),
])
def test_power_commands(monkeypatch, recorder, os_name, action, expected):
    fake_os(monkeypatch, os_name)
    assert system._power(action).startswith("Okay")
    assert recorder == [expected]


def test_command_failure_is_reported(monkeypatch):
    fake_os(monkeypatch, "Linux", available=("pactl",))
    monkeypatch.setattr(pu, "run", lambda cmd, timeout=10: (False, "no sink"))
    assert registry.call("set_volume", percent=30) == "Error: no sink"


def test_get_time_and_status():
    assert len(registry.call("get_time")) > 10
    status = registry.call("system_status")
    assert "CPU" in status and "Memory" in status


# ------------------------------------------------------------- apps ------

@pytest.mark.parametrize("bad", ["", "chrome; rm -rf /", "a" * 80, "$(whoami)", "x|y", "a&b"])
def test_open_app_rejects_unsafe_names(bad):
    assert registry.call("open_app", name=bad).startswith("Error:")


def test_open_app_mac(monkeypatch, recorder):
    fake_os(monkeypatch, "Darwin")
    assert registry.call("open_app", name="Spotify") == "Opened Spotify."
    assert recorder == [["open", "-a", "Spotify"]]


def test_open_app_alias(monkeypatch, recorder):
    fake_os(monkeypatch, "Darwin")
    registry.call("open_app", name="Settings")
    assert recorder == [["open", "-a", "System Settings"]]


def test_open_app_linux_missing(monkeypatch):
    fake_os(monkeypatch, "Linux")
    assert registry.call("open_app", name="nonexistentapp").startswith("Error:")


@pytest.mark.parametrize("url, expected", [
    ("youtube.com", "https://youtube.com"),
    ("http://example.com/a?b=1", "http://example.com/a?b=1"),
    ("javascript:alert(1)", None),
    ("file:///etc/passwd", None),
    ("ftp://example.com", None),
    ("", None),
])
def test_normalize_url(url, expected):
    assert apps.normalize_url(url) == expected


def test_open_url_opens_only_http(monkeypatch):
    opened = []
    monkeypatch.setattr(apps.webbrowser, "open", lambda u: opened.append(u))
    assert registry.call("open_url", url="file:///etc/passwd").startswith("Error:")
    assert registry.call("open_url", url="example.com").startswith("Opened")
    assert opened == ["https://example.com"]


# ------------------------------------------------------------ files ------

def test_open_path_refuses_programs_and_scripts(tmp_path, recorder, monkeypatch):
    fake_os(monkeypatch, "Linux")
    script = tmp_path / "evil.sh"
    script.write_text("echo hi")
    doc = tmp_path / "notes.txt"
    doc.write_text("hello")
    assert "won't launch" in registry.call("open_path", path=str(script))
    assert registry.call("open_path", path=str(doc)).startswith("Opened")
    assert recorder == [["xdg-open", str(doc.resolve())]]


def test_open_path_missing():
    assert registry.call("open_path", path="/definitely/not/here").startswith("Error:")


def test_find_files(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "My Resume 2026.pdf").write_text("x")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "resume-secret.txt").write_text("x")
    out = registry.call("find_files", query="resume", folder=str(tmp_path))
    assert "My Resume 2026.pdf" in out
    assert "secret" not in out
    assert registry.call("find_files", query="zzz", folder=str(tmp_path)).startswith("No files")
    assert registry.call("find_files", query="x", folder="/not/a/folder").startswith("Error:")


def test_open_app_windows_finds_store_apps(monkeypatch):
    from jarvis.tools import apps
    fake_os(monkeypatch, "Windows")
    launched = []
    monkeypatch.setattr(apps, "_start_menu_app_id", lambda n: "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")
    monkeypatch.setattr(apps.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))
    assert registry.call("open_app", name="WhatsApp") == "Opened WhatsApp."
    assert launched == [["explorer.exe", "shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"]]


def test_open_app_windows_falls_back_to_the_website(monkeypatch):
    from jarvis.tools import apps
    fake_os(monkeypatch, "Windows")
    opened = []
    monkeypatch.setattr(apps, "_start_menu_app_id", lambda n: None)
    monkeypatch.setattr(apps.pu, "which", lambda n: None)
    monkeypatch.setattr(apps.webbrowser, "open", opened.append)
    out = registry.call("open_app", name="WhatsApp")
    assert opened == ["https://web.whatsapp.com"] and "browser" in out
