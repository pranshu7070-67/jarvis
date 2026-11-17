import pytest

from jarvis import platform_utils as pu
from jarvis import registry, safety, store
from jarvis.tools import media, notes, weather


# ------------------------------------------------------------------ notes --

def test_add_list_read_search_delete():
    assert registry.call("list_notes") == "You have no notes yet."
    out = registry.call("add_note", text="Buy milk and eggs", title="Shopping")
    assert out.startswith("Saved note")
    note_id = store.load_notes()[0]["id"]
    assert "Shopping" in registry.call("list_notes")
    assert "Buy milk and eggs" in registry.call("read_note", note_id=note_id)
    assert note_id in registry.call("search_notes", query="MILK")
    assert registry.call("search_notes", query="zebra").startswith("No notes match")

    safety.set_confirmer(lambda p: False)
    assert registry.call("delete_note", note_id=note_id).startswith("Cancelled")
    assert len(store.load_notes()) == 1
    safety.set_confirmer(lambda p: True)
    assert registry.call("delete_note", note_id=note_id) == "Note deleted."
    assert store.load_notes() == []


def test_title_defaults_to_first_line_and_empty_notes_are_rejected():
    note = notes.create_note("First line here\nsecond line")
    assert note["title"] == "First line here"
    assert registry.call("add_note", text="   ").startswith("Error:")


def test_pinned_notes_sort_first_and_update_works():
    a = notes.create_note("older")
    b = notes.create_note("newer")
    assert [n["id"] for n in notes.all_notes()] == [b["id"], a["id"]]
    notes.update_note(a["id"], pinned=True)
    assert notes.all_notes()[0]["id"] == a["id"]
    assert notes.update_note(a["id"], text="changed")["text"] == "changed"
    with pytest.raises(KeyError):
        notes.update_note("nope", text="x")


def test_corrupt_notes_file_does_not_crash():
    store.notes_path().write_text("{not json", encoding="utf-8")
    assert store.load_notes() == []
    assert registry.call("list_notes") == "You have no notes yet."


# ---------------------------------------------------------------- weather --

def fake_get(url, params):
    if url == weather.GEOCODE:
        if params["name"].lower() == "atlantis":
            return {}
        return {"results": [{"name": "Mumbai", "admin1": "Maharashtra", "country": "India",
                             "latitude": 19.07, "longitude": 72.88}]}
    return {
        "current": {"temperature_2m": 31.4, "apparent_temperature": 36.0, "relative_humidity_2m": 70,
                    "weather_code": 2, "wind_speed_10m": 12.0},
        "daily": {"time": ["2026-10-25", "2026-10-26", "2026-10-27"], "weather_code": [2, 61, 95],
                  "temperature_2m_max": [33, 30, 29], "temperature_2m_min": [26, 25, 24],
                  "precipitation_probability_max": [10, 70, 90]},
    }


def test_weather_report(monkeypatch):
    monkeypatch.setattr(weather, "_get", fake_get)
    out = registry.call("get_weather", city="Mumbai")
    assert "Mumbai, Maharashtra, India: partly cloudy, 31°C" in out
    assert "light rain" in out and "thunderstorm" in out and "rain 90%" in out


def test_weather_uses_default_city_and_reports_problems(monkeypatch):
    monkeypatch.setattr(weather, "_get", fake_get)
    ask = registry.call("get_weather")
    assert ask.startswith("Which city?") and not ask.startswith("Error:")   # a question, so the AI isn't dragged in
    monkeypatch.setenv("JARVIS_CITY", "Mumbai")
    assert "Mumbai" in registry.call("get_weather")
    assert "couldn't find" in registry.call("get_weather", city="Atlantis")


def test_weather_remembers_the_last_city(monkeypatch):
    monkeypatch.setattr(weather, "_get", fake_get)
    assert "Mumbai" in registry.call("get_weather", city="Mumbai")
    assert "Mumbai" in registry.call("get_weather")   # no city given: uses the remembered one


def test_weather_codes():
    assert weather.describe(0) == "clear sky"
    assert weather.describe(12345) == "unknown conditions"


# ------------------------------------------------------------------ media --

@pytest.mark.parametrize("text, expected", [
    ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc", ("playlist", "37i9dQZF1DXcBWIGoYBM5M")),
    ("https://open.spotify.com/intl-en/track/4uLU6hMCjMI75M1A2tKUQC", ("track", "4uLU6hMCjMI75M1A2tKUQC")),
    ("spotify:album:1DFixLWuPkv3KT3TnV35m3", ("album", "1DFixLWuPkv3KT3TnV35m3")),
    ("https://evil.example/open.spotify.com/track/abc", None),
    ("blinding lights", None),
])
def test_parse_spotify_link(text, expected):
    assert media.parse_spotify_link(text) == expected


def test_pasted_link_plays_without_any_credentials(monkeypatch):
    opened = []
    monkeypatch.setattr(media, "_open_uri", opened.append)
    out = registry.call("play_spotify", query="https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x")
    assert opened == ["spotify:playlist:37i9dQZF1DXcBWIGoYBM5M:play"]
    assert "playlist" in out


def test_play_by_name_with_credentials(monkeypatch):
    opened = []
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(media, "_open_uri", opened.append)
    monkeypatch.setattr(media, "search_spotify", lambda q, k: {"id": "abc1234567", "name": "Blinding Lights", "by": "The Weeknd"})
    assert registry.call("play_spotify", query="blinding lights") == "Playing Blinding Lights by The Weeknd on Spotify."
    assert opened == ["spotify:track:abc1234567:play"]
    monkeypatch.setattr(media, "search_spotify", lambda q, k: None)
    assert registry.call("play_spotify", query="zzzz").startswith("Error:")


def test_play_by_name_without_credentials_uses_web_search(monkeypatch):
    opened = []
    monkeypatch.setattr(media, "_open_uri", opened.append)
    monkeypatch.setattr(media, "find_without_keys", lambda q, k: ("4uLU6hMCjMI75M1A2tKUQC", "Blinding Lights"))
    out = registry.call("play_spotify", query="blinding lights")
    assert opened == ["spotify:track:4uLU6hMCjMI75M1A2tKUQC:play"]
    assert out.startswith("Playing Blinding Lights")


def test_play_by_name_falls_back_to_search_page(monkeypatch):
    opened = []
    monkeypatch.setattr(media, "_open_uri", opened.append)
    monkeypatch.setattr(media, "find_without_keys", lambda q, k: None)
    out = registry.call("play_spotify", query="blinding lights")
    assert opened == ["spotify:search:blinding%20lights"]
    assert "search" in out


def test_play_rejects_bad_kind_and_empty():
    assert registry.call("play_spotify", query="x", kind="podcast").startswith("Error:")
    assert registry.call("play_spotify", query="  ").startswith("Error:")


@pytest.fixture
def recorder(monkeypatch):
    calls = []
    monkeypatch.setattr(pu, "run", lambda cmd, timeout=10: calls.append(cmd) or (True, ""))
    return calls


def test_media_control_windows_presses_the_right_key(monkeypatch):
    keys = []
    monkeypatch.setattr(pu, "current_os", lambda: "Windows")
    monkeypatch.setattr(media, "_press_windows_key", keys.append)
    registry.call("media_control", action="pause")
    registry.call("media_control", action="skip")
    registry.call("media_control", action="previous")
    assert keys == [0xB3, 0xB0, 0xB1]


def test_media_control_mac_and_linux(monkeypatch, recorder):
    monkeypatch.setattr(pu, "current_os", lambda: "Darwin")
    registry.call("media_control", action="next")
    assert recorder == [["osascript", "-e", 'tell application "Spotify" to next track']]
    recorder.clear()
    monkeypatch.setattr(pu, "current_os", lambda: "Linux")
    monkeypatch.setattr(pu, "which", lambda exe: "/usr/bin/playerctl")
    registry.call("media_control", action="play_pause")
    assert recorder == [["playerctl", "play-pause"]]


def test_media_control_rejects_unknown_actions():
    assert registry.call("media_control", action="explode").startswith("Error:")


def test_weather_forgives_a_misspelled_city(monkeypatch):
    def fake(url, params):
        if url == weather.GEOCODE:
            name = params["name"].lower()
            if name == "ahemdabad":
                return {}
            if name in ("ahe", "ah"):
                return {"results": [{"name": "Ahmedabad", "admin1": "Gujarat", "country": "India", "latitude": 23.0, "longitude": 72.6}]}
        return fake_get(url, params)
    monkeypatch.setattr(weather, "_get", fake)
    assert "Ahmedabad" in registry.call("get_weather", city="ahemdabad")
