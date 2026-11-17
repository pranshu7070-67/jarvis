"""The web UI server. Standard library only.

Security model (this page can run assistant commands, so it must not be reachable by
other websites or other computers):
- It listens on 127.0.0.1 only.
- Every request needs a random per-session token, which only the URL we open contains.
- The Host header must be localhost (blocks DNS-rebinding) and any Origin header must be
  this same server (blocks other websites posting to it from your browser).
- Power actions (shutdown / restart / sleep / delete) cannot be confirmed from the web
  page, so Jarvis refuses them there. Use the terminal for those.
"""

import contextlib
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from .. import safety
from ..tools import notes as notes_tool
from ..tools import weather as weather_tool

INDEX = Path(__file__).with_name("index.html")
MAX_BODY = 200_000
DEFAULT_PORT = 8765

_instance = {"server": None}


def _deny_in_ui(prompt: str) -> bool:
    return False


class UIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, jarvis, port: int = DEFAULT_PORT, token: Optional[str] = None):
        self.jarvis = jarvis
        self.token = token or secrets.token_urlsafe(24)
        self.chat_lock = threading.Lock()
        last_error = None
        for p in ([port] if port == 0 else range(port, port + 20)):
            try:
                super().__init__(("127.0.0.1", p), Handler)
                break
            except OSError as exc:
                last_error = exc
        else:
            raise OSError(f"no free port near {port}: {last_error}")
        self.port = self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def allowed_hosts(self) -> set:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def start_background(self) -> None:
        threading.Thread(target=self.serve_forever, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server: UIServer
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):  # keep the terminal clean
        pass

    # -- helpers --------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"))

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _guard(self, need_token_header: bool) -> bool:
        """Host / Origin / token checks. Sends the error and returns False on failure."""
        if self.headers.get("Host", "") not in self.server.allowed_hosts():
            self._error(403, "bad host")
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in self.server.allowed_hosts()}:
            self._error(403, "bad origin")
            return False
        if need_token_header:
            sent = self.headers.get("X-Jarvis-Token", "")
            if not secrets.compare_digest(sent.encode(), self.server.token.encode()):
                self._error(401, "bad token")
                return False
        return True

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            raise ValueError("missing or oversized body")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    # -- routes ---------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            if not self._guard(False):
                return
            token = parse_qs(url.query).get("t", [""])[0]
            if not secrets.compare_digest(token.encode(), self.server.token.encode()):
                return self._error(401, "open Jarvis from the link it prints in the terminal")
            return self._send(200, INDEX.read_bytes(), "text/html")
        if not self._guard(True):
            return
        if url.path == "/api/notes":
            return self._json(200, notes_tool.all_notes())
        if url.path == "/api/weather":
            city = parse_qs(url.query).get("city", [""])[0]
            try:
                return self._json(200, weather_tool.weather_report(city))
            except ValueError as exc:
                return self._error(400, str(exc))
            except Exception as exc:
                return self._error(502, f"weather service unavailable ({type(exc).__name__})")
        if url.path == "/api/system":
            try:
                from ..tools import system as system_tool
                return self._json(200, system_tool.system_report())
            except Exception as exc:
                return self._error(500, f"system info unavailable ({type(exc).__name__})")
        if url.path == "/api/status":
            return self._json(200, {"ai": self.server.jarvis.brain is not None,
                                    "default_city": weather_tool.default_city()})
        self._error(404, "not found")

    def do_POST(self):
        if not self._guard(True):
            return
        path = urlparse(self.path).path
        try:
            data = self._body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self._error(400, str(exc))
        if path == "/api/notes":
            try:
                return self._json(201, notes_tool.create_note(str(data.get("text", "")), str(data.get("title", ""))))
            except ValueError as exc:
                return self._error(400, str(exc))
        if path == "/api/chat":
            text = str(data.get("text", "")).strip()[:2000]
            if not text:
                return self._error(400, "empty message")
            # Quick commands (volume, music, notes...) never wait behind a slow AI question;
            # only AI questions take turns, because they share one conversation.
            quick = self.server.jarvis.router(text) is not None
            guard = contextlib.nullcontext() if quick else self.server.chat_lock
            with guard, safety.override(_deny_in_ui):
                try:
                    reply = self.server.jarvis.handle(text)
                except Exception as exc:
                    reply = f"Error: {exc}"
            if reply.startswith("Cancelled"):
                reply += " (Power and delete actions can't be confirmed from this page. Use the terminal.)"
            return self._json(200, {"reply": reply})
        self._error(404, "not found")

    def do_PUT(self):
        if not self._guard(True):
            return
        path = urlparse(self.path).path
        if not path.startswith("/api/notes/"):
            return self._error(404, "not found")
        try:
            data = self._body()
            note = notes_tool.update_note(
                path.rsplit("/", 1)[1],
                text=str(data["text"]) if "text" in data else None,
                title=str(data["title"]) if "title" in data else None,
                pinned=bool(data["pinned"]) if "pinned" in data else None,
            )
        except KeyError:
            return self._error(404, "no such note")
        except (ValueError, json.JSONDecodeError) as exc:
            return self._error(400, str(exc))
        self._json(200, note)

    def do_DELETE(self):
        if not self._guard(True):
            return
        path = urlparse(self.path).path
        if not path.startswith("/api/notes/"):
            return self._error(404, "not found")
        if notes_tool.remove_note(path.rsplit("/", 1)[1]):
            return self._json(200, {"ok": True})
        self._error(404, "no such note")


def ensure_running(jarvis_factory: Callable, port: int = DEFAULT_PORT) -> UIServer:
    """Start the UI server in the background once, and return it."""
    server = _instance["server"]
    if server is None:
        server = UIServer(jarvis_factory(), port=port)
        server.start_background()
        _instance["server"] = server
    return server


def open_in_browser(server: UIServer) -> None:
    webbrowser.open(server.url)
