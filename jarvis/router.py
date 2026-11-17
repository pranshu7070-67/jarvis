"""Fast path: handle simple, unambiguous commands without calling an AI.

This makes common commands instant, free (no API quota) and offline. Anything the
router doesn't recognise returns None and goes to the AI brain instead.
"""

import re
from typing import Callable, Optional

Route = tuple  # (tool_name, kwargs)

_FILLER = re.compile(r"^(?:(?:hey |ok |okay )?jarvis[,:]?\s+|please\s+|can you\s+|could you\s+)", re.I)
_URL = re.compile(r"^(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:[/?#]\S*)?$", re.I)
_PATH = re.compile(r"^(?:~|/|[A-Za-z]:[\\/])")
_COMPLEX = re.compile(r"\b(?:and|then|so|for|with|in|on|about|that|which|where)\b", re.I)


def clean(text: str) -> str:
    t = text.strip().rstrip(".!?").strip()
    while True:
        new = _FILLER.sub("", t, count=1)
        if new == t:
            break
        t = new
    return re.sub(r"\s+please$", "", t, flags=re.I).strip()


def _open(m) -> Optional[Route]:
    target = m["target"].strip().strip("\"'")
    if _URL.match(target):
        return "open_url", {"url": target}
    if _PATH.match(target):
        return "open_path", {"path": target}
    if len(target.split()) > 4 or _COMPLEX.search(target):
        return None  # too complicated for the fast path
    return "open_app", {"name": target}


def _percent(tool_name: str) -> Callable:
    def build(m) -> Optional[Route]:
        n = int(m["n"])
        return (tool_name, {"percent": n}) if 0 <= n <= 100 else None
    return build


def _const(tool_name: str, **kwargs) -> Callable:
    return lambda m: (tool_name, dict(kwargs))


_AUDIO = r"(?:(?:the )?(?:sound|volume|audio|speakers?))"

def _weather(m) -> Optional[Route]:
    groups = m.groupdict()
    city = (groups.get("city") or groups.get("city2") or groups.get("city3") or "").strip().strip("\"'")
    return "get_weather", {"city": city}


def _note(m) -> Optional[Route]:
    return "add_note", {"text": m["t"].strip()}


def _play(m) -> Optional[Route]:
    target = m["t"].strip()
    if _NOT_MUSIC.search(target):
        return None  # "play big bang theory on netflix": let the AI decide
    kind = (m.groupdict().get("kind") or "track").lower()
    kind = "track" if kind == "song" else kind
    return "play_spotify", {"query": target, "kind": kind}


_NOT_MUSIC = re.compile(r"\b(?:netflix|youtube|prime|hotstar|disney|movie|video|episode|show|series|game)\b", re.I)

_RULES = [
    (re.compile(r"^(?:save|add)(?: a)?(?: new)? contact\s+(?P<n>[A-Za-z][\w .'\-]*?)\s*[:\-]?\s+(?P<num>\+?[\d][\d \-]{8,18})$", re.I),
     lambda m: ("add_contact", {"name": m["n"].strip(), "number": m["num"]})),
    (re.compile(r"^(?:show |list )?(?:my )?contacts$", re.I), _const("list_contacts")),
    (re.compile(r"^(?:whatsapp |whats app )?(?P<v>video )?(?:call|ring)\s+(?P<n>.+?)(?: on (?:whatsapp|whats app))?$", re.I),
     lambda m: ("whatsapp_call", {"name": m["n"].strip(), "video": bool(m["v"])})),
    (re.compile(r"^(?:whatsapp|message|text|msg)\s+(?P<n>[\w .'\-]{1,40}?)(?:\s*[:,]\s*|\s+(?:saying|that)\s+)(?P<t>.+)$", re.I),
     lambda m: ("whatsapp_message", {"name": m["n"].strip(), "text": m["t"].strip()})),
    (re.compile(r"^(?:open )?whatsapp(?: chat)?(?: with)? (?P<n>[\w .'\-]{1,40})$", re.I),
     lambda m: ("whatsapp_message", {"name": m["n"].strip(), "text": ""})),
    (re.compile(r"^(?:hi|hey|hello|hii+|yo|hola|namaste|sup|good (?:morning|afternoon|evening))(?: (?:there|jarvis))?$|^hey jarvis$", re.I), _const("small_talk", kind="hello")),
    (re.compile(r"^(?:thanks?|thank you|thx|ty)(?: (?:a lot|so much|jarvis))?$", re.I), _const("small_talk", kind="thanks")),
    (re.compile(r"^(?:bye|goodbye|see you|good night)(?: jarvis)?$", re.I), _const("small_talk", kind="bye")),
    (re.compile(r"^(?:(?:open|launch)\s+(?:my |the )?(?:notes|notebook|note book)|show\s+(?:my |the )?(?:notebook|note book))$", re.I),
     _const("open_notebook")),
    (re.compile(r"^(?:show |list |read )?(?:me )?(?:my |all )?notes$|^what(?:'s| are) my notes$", re.I), _const("list_notes")),
    (re.compile(r"^(?:make|take|add|save|write|create)(?: me)?(?: a| a new)? note(?: that| to| saying| about)?\s*[:\-]?\s+(?P<t>.+)$", re.I), _note),
    (re.compile(r"^note(?: down)?\s*[:\-]?\s+(?P<t>.+)$", re.I), _note),
    (re.compile(r"^(?:new|another) note\s*[:\-]?\s+(?P<t>.+)$", re.I), _note),
    (re.compile(r"^(?:remind me to|remember to|don'?t let me forget to)\s+(?P<t>.+)$", re.I), _note),
    (re.compile(r"^(?:what(?:'s| is) )?(?:the )?(?:weather|temperature|forecast)(?: like)?(?: (?:in|at|for|of) (?P<city>.+?))?(?: today| now| right now)?$"
                r"|^how(?:'s| is) the weather(?: like)?(?: (?:in|at) (?P<city2>.+?))?(?: today| now| right now)?$|^is it (?:raining|sunny|hot|cold)(?: (?:in|at) (?P<city3>.+?))?(?: today| now| right now)?$", re.I), _weather),
    (re.compile(r"^(?:play|resume|unpause)(?: (?:the )?(?:music|song|it))?$|^pause(?: (?:the )?(?:music|song))?$|^stop (?:the )?music$", re.I),
     lambda m: ("media_control", {"action": "play_pause"})),
    (re.compile(r"^(?:next|skip)(?: (?:the )?(?:song|track))?$", re.I), _const("media_control", action="next")),
    (re.compile(r"^(?:previous|prev|back)(?: (?:the )?(?:song|track))?$|^go back a song$", re.I), _const("media_control", action="previous")),
    (re.compile(r"^play(?: me)?(?: the| a| some)?\s+(?:(?P<kind>song|track|album|playlist|artist)\s+)?(?P<t>.+?)(?:\s+on spotify)?$", re.I), _play),
    (re.compile(r"^(?:open|launch|start)\s+(?P<target>.+)$", re.I), _open),
    (re.compile(r"^(?:set |change )?(?:the )?volume (?:to |at )?(?P<n>\d{1,3})\s*%?$", re.I), _percent("set_volume")),
    (re.compile(r"^(?:set |change )?(?:the )?(?:screen )?brightness (?:to |at )?(?P<n>\d{1,3})\s*%?$", re.I), _percent("set_brightness")),
    (re.compile(rf"^unmute(?: {_AUDIO})?$", re.I), _const("set_mute", muted=False)),
    (re.compile(rf"^mute(?: {_AUDIO})?$", re.I), _const("set_mute", muted=True)),
    (re.compile(r"^lock(?: (?:the |my )?(?:screen|computer|laptop|pc|device))?$", re.I), _const("lock_screen")),
    (re.compile(r"^(?:take (?:a )?)?screen ?shot$", re.I), _const("take_screenshot")),
    (re.compile(r"^(?:what(?:'s| is)(?: the)?\s+)?(?:current )?(?:time|date)(?: now| today| is it)?$"
                r"|^what time is it(?: now)?$|^what day is it(?: today)?$", re.I), _const("get_time")),
    (re.compile(r"^(?:system |laptop |pc )?(?:status|battery(?: status| level)?)$"
                r"|^how(?:'s| is) my (?:battery|laptop|system)$", re.I), _const("system_status")),
    (re.compile(r"^(?:shut ?down|power off)(?: (?:the |my )?(?:computer|laptop|pc|system))?(?: now)?$", re.I), _const("shutdown_computer")),
    (re.compile(r"^(?:restart|reboot)(?: (?:the |my )?(?:computer|laptop|pc|system))?(?: now)?$", re.I), _const("restart_computer")),
    (re.compile(r"^(?:sleep|suspend)(?: (?:the |my )?(?:computer|laptop|pc|system))?(?: now)?$", re.I), _const("sleep_computer")),
]


def route(text: str) -> Optional[Route]:
    """Return (tool_name, kwargs) if the text is a simple command, else None."""
    t = clean(text)
    if not t:
        return None
    for pattern, build in _RULES:
        m = pattern.match(t)
        if m:
            return build(m)
    return None
