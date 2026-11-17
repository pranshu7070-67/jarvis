import http.client
import json

import pytest

from jarvis import safety
from jarvis.agent import Jarvis
from jarvis.tools import weather
from jarvis.ui.server import UIServer


@pytest.fixture
def server():
    srv = UIServer(Jarvis(), port=0)
    srv.start_background()
    yield srv
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, body=None, token=True, host=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{srv.port}"}
    if token:
        headers["X-Jarvis-Token"] = srv.token
    if origin:
        headers["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except ValueError:
        return resp.status, raw.decode()


def test_page_needs_the_session_token(server):
    assert request(server, "GET", "/", token=False)[0] == 401
    assert request(server, "GET", "/?t=wrong", token=False)[0] == 401
    status, html = request(server, "GET", f"/?t={server.token}", token=False)
    assert status == 200 and "J.A.R.V.I.S" in html


def test_api_rejects_missing_or_wrong_token(server):
    assert request(server, "GET", "/api/notes", token=False)[0] == 401
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    conn.request("GET", "/api/notes", headers={"Host": f"127.0.0.1:{server.port}", "X-Jarvis-Token": "nope"})
    assert conn.getresponse().status == 401


def test_dns_rebinding_and_cross_site_requests_are_blocked(server):
    assert request(server, "GET", "/api/notes", host="evil.example")[0] == 403
    assert request(server, "GET", "/api/notes", origin="https://evil.example")[0] == 403
    assert request(server, "POST", "/api/chat", {"text": "what time is it"}, origin="http://evil.example")[0] == 403
    assert request(server, "GET", "/api/notes", origin=f"http://127.0.0.1:{server.port}")[0] == 200


def test_notes_crud(server):
    status, note = request(server, "POST", "/api/notes", {"title": "Plan", "text": "Learn Python"})
    assert status == 201 and note["title"] == "Plan"
    assert request(server, "GET", "/api/notes")[1][0]["id"] == note["id"]
    status, updated = request(server, "PUT", f"/api/notes/{note['id']}", {"text": "Learn Python 3.13", "pinned": True})
    assert status == 200 and updated["text"] == "Learn Python 3.13" and updated["pinned"] is True
    assert request(server, "PUT", "/api/notes/missing", {"text": "x"})[0] == 404
    assert request(server, "DELETE", f"/api/notes/{note['id']}")[0] == 200
    assert request(server, "DELETE", f"/api/notes/{note['id']}")[0] == 404
    assert request(server, "POST", "/api/notes", {"text": "  "})[0] == 400


def test_chat_runs_commands(server):
    status, data = request(server, "POST", "/api/chat", {"text": "note buy milk"})
    assert status == 200 and data["reply"].startswith("Saved note")
    assert request(server, "GET", "/api/notes")[1][0]["text"] == "buy milk"
    assert request(server, "POST", "/api/chat", {"text": ""})[0] == 400


def test_power_actions_are_refused_from_the_web_page_but_not_the_terminal(server):
    ran = []
    from jarvis.tools import system
    system._power = lambda action: ran.append(action) or "ran"  # type: ignore[assignment]
    safety.set_confirmer(lambda p: True)  # the terminal user would say yes...
    status, data = request(server, "POST", "/api/chat", {"text": "shutdown"})
    assert "Cancelled" in data["reply"] and "terminal" in data["reply"]
    assert ran == []  # ...but the web page can never approve it
    assert safety.confirm("terminal still works") is True


def test_weather_endpoint(server, monkeypatch):
    from tests.test_notes_weather_media import fake_get
    monkeypatch.setattr(weather, "_get", fake_get)
    status, data = request(server, "GET", "/api/weather?city=Mumbai")
    assert status == 200 and data["place"].startswith("Mumbai") and len(data["days"]) == 3
    assert request(server, "GET", "/api/weather?city=")[0] == 200   # falls back to the remembered city


def test_unknown_routes_and_bad_bodies(server):
    assert request(server, "GET", "/api/nothing")[0] == 404
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    conn.request("POST", "/api/chat", body="not json", headers={
        "Host": f"127.0.0.1:{server.port}", "X-Jarvis-Token": server.token, "Content-Length": "8"})
    assert conn.getresponse().status == 400


def test_system_endpoint_and_page_has_the_new_panels(server):
    status, data = request(server, "GET", "/api/system")
    assert status == 200 and 0 <= data["cpu"] <= 100 and 0 <= data["mem"] <= 100
    assert data["battery"] is None or {"percent", "plugged"} <= set(data["battery"])
    assert request(server, "GET", "/api/system", token=False)[0] == 401
    _, html = request(server, "GET", f"/?t={server.token}", token=False)
    for needle in ('id="p-wx"', 'id="p-sys"', 'id="p-deck"', 'id="p-nb"', 'id="p-co"'):
        assert needle in html
    assert "confirm(" not in html and "alert(" not in html  # no browser dialogs; delete is two-step in the page


def test_quick_commands_do_not_wait_behind_a_slow_ai_question(server):
    with server.chat_lock:   # pretend a slow AI question is in progress
        status, data = request(server, "POST", "/api/chat", {"text": "note still works"})
    assert status == 200 and data["reply"].startswith("Saved note")
