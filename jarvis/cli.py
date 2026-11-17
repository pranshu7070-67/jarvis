"""Terminal interface: python -m jarvis"""

import argparse
import os
import sys

from . import __version__, platform_utils, registry
from . import tools  # noqa: F401  (importing registers every tool)
from .agent import Jarvis
from .brain import create_brain
from .config import load_config

HELP = """\
Try things like:
  open chrome            volume 40            brightness 60        mute / unmute
  open youtube.com       lock screen          screenshot           battery
  what time is it        restart / shutdown / sleep  (asks you first)
  weather in Mumbai      note buy milk        list notes           open notebook
  play Blinding Lights   play playlist <name or Spotify link>      pause / next / previous

With an API key you can also say things like:
  research the best budget DACs and give me the top 3
  find my resume pdf and open it
  open spotify and set the volume to 30

Meta commands:  help   tools   exit
"""


def _style():
    """ANSI colour helpers that quietly turn off when output isn't a terminal."""
    if os.name == "nt":
        os.system("")  # enables ANSI escapes in Windows terminals
    on = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    return (lambda s: f"\033[36m{s}\033[0m" if on else s,
            lambda s: f"\033[2m{s}\033[0m" if on else s)


def build() -> Jarvis:
    cfg = load_config()
    for note in cfg.notes:
        print(f"  [note] {note}", file=sys.stderr)
    brain = None
    if cfg.has_ai:
        brain = create_brain(cfg, registry.callables(), registry.by_name(), platform_utils.current_os())
    return Jarvis(brain=brain)


def run_check() -> int:
    """python -m jarvis --check : find out exactly why the AI isn't answering."""
    from .brain import GeminiBrain, GroqBrain, describe_error

    cfg = load_config()
    os_name = platform_utils.current_os()
    print(f"Jarvis {__version__} self-check\n")
    print(f"  .env file : {cfg.env_file or 'NOT FOUND. It must sit next to README.md in this folder'}")
    for note in cfg.notes:
        print(f"  note      : {note}")
    print(f"  Gemini key: {'found' if cfg.gemini_key else 'missing'}")
    print(f"  Groq key  : {'found' if cfg.groq_key else 'missing'}\n")

    working = 0
    ask = "Reply with exactly the word: OK"
    attempts = []
    if cfg.gemini_key:
        attempts.append(("Gemini", lambda: GeminiBrain(cfg.gemini_key, cfg.gemini_model, [], os_name).ask(ask)))
    if cfg.groq_key:
        attempts.append(("Groq", lambda: GroqBrain(cfg.groq_key, cfg.groq_model, {}, os_name).ask(ask)))
    for name, attempt in attempts:
        try:
            reply = attempt()
            print(f"  {name:<7}: PASS (the model replied: {reply[:40]!r})")
            working += 1
        except Exception as exc:
            print(f"  {name:<7}: FAIL, {describe_error(exc)}")
    if not attempts:
        print("  No API key found. Put your key after GEMINI_API_KEY= in the .env file, save it, and run this again.")

    result = registry.call("web_search", query="current president of india", max_results=1)
    print(f"  Web search: {'FAIL, ' + result[:120] if result.startswith('Error:') else 'PASS'}")
    print("\nAll good." if working else "\nThe AI is not working yet. Fix the FAIL line above, then run --check again.")
    return 0 if working else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="AI assistant that controls your laptop.")
    parser.add_argument("--once", metavar="COMMAND", help="run one command and exit")
    parser.add_argument("--no-ai", action="store_true", help="only use offline fast-path commands")
    parser.add_argument("--ui", action="store_true", help="open the notebook / dashboard in your browser")
    parser.add_argument("--check", action="store_true", help="test your API keys and web search, and say what's wrong")
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    args = parser.parse_args(argv)

    if args.check:
        return run_check()

    cyan, dim = _style()
    try:
        jarvis = Jarvis() if args.no_ai else build()
    except Exception as exc:
        print(f"Could not start the AI brain: {exc}", file=sys.stderr)
        jarvis = Jarvis()

    if args.once:
        print(jarvis.handle(args.once))
        return 0

    if args.ui:
        from .ui import server
        srv = server.UIServer(jarvis)
        print(cyan("Jarvis console: ") + srv.url)
        print(dim("Opening your browser. Keep this window open; press Ctrl+C to stop."))
        server.open_in_browser(srv)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
        return 0

    mode = "AI + fast commands" if jarvis.brain else "offline fast commands only"
    print(cyan(f"J.A.R.V.I.S. v{__version__}") + dim(f"  [{mode}]  type 'help' or 'exit'"))
    if jarvis.brain is None and not args.no_ai:
        print("  No API key loaded, so only simple commands work. Run:  python -m jarvis --check")
    while True:
        try:
            line = input(cyan("you > ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        low = line.lower()
        if low in ("exit", "quit", "q"):
            return 0
        if low == "help":
            print(HELP)
        elif low == "tools":
            for t in registry.REGISTRY.values():
                flag = "  (asks first)" if t.risk == "confirm" else ""
                print(f"  {t.name:<20} {t.summary}{flag}")
        else:
            try:
                reply = jarvis.handle(line)
            except Exception as exc:  # keep the window alive no matter what
                reply = f"Error: {exc}"
            if reply:
                print(cyan("jarvis > ") + reply)


if __name__ == "__main__":
    raise SystemExit(main())
