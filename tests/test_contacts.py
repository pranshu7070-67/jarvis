from jarvis import registry
from jarvis.tools import contacts


def test_normalize_number():
    assert contacts.normalize_number("98765 43210") == "919876543210"
    assert contacts.normalize_number("+91 98765-43210") == "919876543210"
    assert contacts.normalize_number("12345") is None
    assert contacts.normalize_number("abc") is None


def test_save_list_and_find():
    assert registry.call("add_contact", name="Mom", number="9876543210").startswith("Saved Mom")
    assert registry.call("list_contacts") == "Contacts: Mom"
    assert contacts.find_contact("mom") == ("Mom", "919876543210")
    assert contacts.find_contact("nobody") is None
    assert registry.call("add_contact", name="Mom", number="12").startswith("Error:")
    assert registry.call("add_contact", name="bad;name", number="9876543210").startswith("Error:")


def test_call_unknown_contact_asks_instead_of_erroring():
    out = registry.call("whatsapp_call", name="Ghost")
    assert "save contact" in out and not out.startswith("Error:")


def test_whatsapp_call_opens_chat_then_presses_the_call_shortcut(monkeypatch):
    registry.call("add_contact", name="Mom", number="9876543210")
    steps = []
    monkeypatch.setattr(contacts.pu, "current_os", lambda: "Windows")
    monkeypatch.setattr(contacts, "_open_chat", lambda number, text="": steps.append(("chat", number, text)))
    monkeypatch.setattr(contacts, "_press", lambda *keys: steps.append(("keys",) + keys))
    monkeypatch.setattr(contacts.time, "sleep", lambda s: None)
    assert "Calling Mom" in registry.call("whatsapp_call", name="mom")
    assert steps == [("chat", "919876543210", ""), ("keys", "ctrl", "shift", "c")]
    steps.clear()
    registry.call("whatsapp_call", name="Mom", video=True)
    assert steps[-1] == ("keys", "ctrl", "shift", "v")


def test_message_prefills_but_never_sends(monkeypatch):
    registry.call("add_contact", name="Mom", number="9876543210")
    opened = []
    monkeypatch.setattr(contacts, "_open_chat", lambda number, text="": opened.append((number, text)))
    out = registry.call("whatsapp_message", name="Mom", text="running late")
    assert opened == [("919876543210", "running late")] and "press Enter" in out


def test_voice_misspellings_still_find_the_contact():
    registry.call("add_contact", name="Nirav", number="9876543210")
    registry.call("add_contact", name="Rahul Sharma", number="9123456780")
    registry.call("add_contact", name="Mom", number="9000000001")
    assert contacts.find_contact("neerav")[0] == "Nirav"
    assert contacts.find_contact("Niraav")[0] == "Nirav"
    assert contacts.find_contact("rahool")[0] == "Rahul Sharma"
    assert contacts.find_contact("rahul")[0] == "Rahul Sharma"
    assert contacts.find_contact("mum")[0] == "Mom"
    assert contacts.find_contact("zebra") is None


def test_two_similar_names_are_not_guessed():
    registry.call("add_contact", name="Nirav", number="9876543210")
    registry.call("add_contact", name="Neeraj", number="9123456780")
    assert contacts.find_contact("neerav")[0] == "Nirav"      # sounds like Nirav, not Neeraj
    assert contacts.find_contact("ner") is None              # could be either: ask instead of guessing
