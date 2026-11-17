"""Open the notebook interface in your browser."""

from ..registry import tool


@tool()
def open_notebook() -> str:
    """Open the Jarvis notebook and dashboard (notes, weather, chat) in the browser."""
    from ..cli import build
    from ..ui import server

    srv = server.ensure_running(build)
    server.open_in_browser(srv)
    return "Opened your notebook in the browser. (It only works while this window stays open.)"
