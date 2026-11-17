import pytest

from jarvis.router import route


@pytest.mark.parametrize("text, expected", [
    ("open chrome", ("open_app", {"name": "chrome"})),
    ("Open Spotify.", ("open_app", {"name": "Spotify"})),
    ("hey jarvis, please open file explorer", ("open_app", {"name": "file explorer"})),
    ("could you launch calculator please", ("open_app", {"name": "calculator"})),
    ("open youtube.com", ("open_url", {"url": "youtube.com"})),
    ("open https://github.com/anthropics", ("open_url", {"url": "https://github.com/anthropics"})),
    ("open ~/Documents", ("open_path", {"path": "~/Documents"})),
    ("open C:\\Users\\me\\notes.txt", ("open_path", {"path": "C:\\Users\\me\\notes.txt"})),
    ("volume 40", ("set_volume", {"percent": 40})),
    ("set the volume to 75%", ("set_volume", {"percent": 75})),
    ("brightness 60", ("set_brightness", {"percent": 60})),
    ("set screen brightness to 20", ("set_brightness", {"percent": 20})),
    ("mute", ("set_mute", {"muted": True})),
    ("mute the sound", ("set_mute", {"muted": True})),
    ("unmute", ("set_mute", {"muted": False})),
    ("lock screen", ("lock_screen", {})),
    ("lock my laptop", ("lock_screen", {})),
    ("take a screenshot", ("take_screenshot", {})),
    ("screenshot", ("take_screenshot", {})),
    ("what time is it", ("get_time", {})),
    ("what's the date", ("get_time", {})),
    ("battery", ("system_status", {})),
    ("how is my battery", ("system_status", {})),
    ("shutdown", ("shutdown_computer", {})),
    ("shut down the computer", ("shutdown_computer", {})),
    ("restart my laptop", ("restart_computer", {})),
    ("sleep", ("sleep_computer", {})),
    ("weather", ("get_weather", {"city": ""})),
    ("what's the weather in Mumbai", ("get_weather", {"city": "Mumbai"})),
    ("weather in New Delhi today", ("get_weather", {"city": "New Delhi"})),
    ("how is the weather in Pune", ("get_weather", {"city": "Pune"})),
    ("note buy milk", ("add_note", {"text": "buy milk"})),
    ("make a note: call mom at 6", ("add_note", {"text": "call mom at 6"})),
    ("take a note that the exam is on friday", ("add_note", {"text": "the exam is on friday"})),
    ("my notes", ("list_notes", {})),
    ("show notes", ("list_notes", {})),
    ("open notebook", ("open_notebook", {})),
    ("open my notes", ("open_notebook", {})),
    ("play blinding lights by the weeknd", ("play_spotify", {"query": "blinding lights by the weeknd", "kind": "track"})),
    ("play me some Daft Punk on spotify", ("play_spotify", {"query": "Daft Punk", "kind": "track"})),
    ("play playlist lofi beats", ("play_spotify", {"query": "lofi beats", "kind": "playlist"})),
    ("play https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", ("play_spotify", {"query": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "kind": "track"})),
    ("pause", ("media_control", {"action": "play_pause"})),
    ("resume", ("media_control", {"action": "play_pause"})),
    ("next song", ("media_control", {"action": "next"})),
    ("skip", ("media_control", {"action": "next"})),
    ("previous track", ("media_control", {"action": "previous"})),
])
def test_fast_path(text, expected):
    assert route(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "   ",
    "open spotify and play some jazz",
    "open notes on my project",
    "open the thing I was working on yesterday afternoon",
    "volume 400",
    "set volume to loud",
    "research the best budget DACs",
    "what is the capital of france",
    "turn off the lights",
    "sleep better tips",
    "who won the match last night",
    "play big bang theory on netflix",
    "play the latest episode of friends",
    "recommend me a song",
    "weather report for my project",
    "notes on my project",
])
def test_goes_to_the_ai(text):
    assert route(text) is None


def test_more_note_phrasings():
    from jarvis import router
    assert router.route("new note buy milk") == ("add_note", {"text": "buy milk"})
    assert router.route("remind me to call mom") == ("add_note", {"text": "call mom"})


def test_greetings_are_answered_without_the_ai():
    from jarvis import router
    assert router.route("hey") == ("small_talk", {"kind": "hello"})
    assert router.route("Hello Jarvis!") == ("small_talk", {"kind": "hello"})
    assert router.route("thanks") == ("small_talk", {"kind": "thanks"})
    assert router.route("hey what is the capital of france") is None


def test_more_weather_phrasings():
    from jarvis import router
    assert router.route("how is the weather today") == ("get_weather", {"city": ""})
    assert router.route("is it raining in delhi") == ("get_weather", {"city": "delhi"})


def test_weather_of_city():
    from jarvis import router
    assert router.route("weather of ahmedabad") == ("get_weather", {"city": "ahmedabad"})


def test_call_and_contact_phrases():
    from jarvis import router
    assert router.route("call mom") == ("whatsapp_call", {"name": "mom", "video": False})
    assert router.route("video call mom on whatsapp") == ("whatsapp_call", {"name": "mom", "video": True})
    assert router.route("save contact Mom 9876543210") == ("add_contact", {"name": "Mom", "number": "9876543210"})
    assert router.route("message mom: running late") == ("whatsapp_message", {"name": "mom", "text": "running late"})
    assert router.route("open whatsapp") == ("open_app", {"name": "whatsapp"})
