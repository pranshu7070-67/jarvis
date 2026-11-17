# J.A.R.V.I.S.: a free AI assistant that controls your laptop

Type (or later, say) what you want. JARVIS opens apps, changes volume and brightness, finds files, takes screenshots, researches the web, and asks before doing anything risky.

```
you > open spotify
jarvis > Opened Spotify.
you > volume 30
jarvis > Volume set to 30%.
you > research the best budget DACs under $100 and give me the top 3
jarvis > (searches, reads pages, summarises, lists sources)
you > shutdown
  [!] Allow shutdown_computer()? [y/N]
```

**Free to run.** The brain is Google Gemini (free tier, no credit card) with Groq as an optional free backup. Simple commands like `volume 30` or `open chrome` never touch the API at all, so your daily quota goes a long way.

> **Status: v0.3.0.** Typed commands, system control, web research, weather, notes, a notebook interface and Spotify. Voice, screen vision and memory are on the roadmap below.

---

## Quick start

You need **Python 3.10+** on Windows, macOS or Linux.

```bash
git clone https://github.com/<your-username>/jarvis-assistant.git
cd jarvis-assistant

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Get a free key at **https://aistudio.google.com** (click "Get API key"), paste it into `.env` after `GEMINI_API_KEY=`, then:

```bash
python -m jarvis
```

No key yet? It still starts and handles the simple commands offline (`python -m jarvis --no-ai`).

Other ways to run it:

```bash
python -m jarvis --once "volume 50"     # run one command and exit
python -m jarvis --version
```

Type `help` for examples and `tools` for everything it can do.

## What it can do

| Area | Tools |
|---|---|
| Apps and sites | `open_app`, `open_url`, `open_path` |
| Files | `find_files` |
| Sound and screen | `set_volume`, `set_mute`, `set_brightness`, `lock_screen`, `take_screenshot` |
| Power | `sleep_computer`, `restart_computer`, `shutdown_computer` (**always ask first**) |
| Info | `get_time`, `system_status` (battery, CPU, memory, disk) |
| Research | `web_search`, `read_webpage` |
| Weather | `get_weather` (free, no key, uses Open-Meteo) |
| Notes | `add_note`, `list_notes`, `read_note`, `search_notes`, `delete_note` (asks first) |
| Notebook UI | `open_notebook`, or run `python -m jarvis --ui` |
| Music | `play_spotify`, `media_control` (pause, resume, next, previous) |

### Weather, notes, notebook

```
weather                      weather in Mumbai
note buy milk                make a note: exam on friday        list notes
open notebook                (opens the dashboard in your browser)
```

Set `JARVIS_CITY=Mumbai` in `.env` so plain `weather` knows where you are. Notes are saved in `~/.jarvis/notes.json` (a plain file you own).

**The notebook page** (`python -m jarvis --ui`) has a notes editor with search, pinning and autosave, a weather panel, and a chat console wired to the same assistant. It runs only on your own computer: it listens on `127.0.0.1`, needs a random per-session link, and checks the `Host` and `Origin` headers so other websites can't talk to it. Shutdown, restart, sleep and note deletion by chat can't be confirmed from that page, so Jarvis refuses them there; use the terminal for those.

### Spotify

```
play playlist <paste a Spotify link>      play https://open.spotify.com/track/...
play Blinding Lights                      play me some Daft Punk on spotify
pause    resume    next    previous
recommend me 5 songs like Starboy         (AI suggests, then ask it to play one)
```

How it works, honestly:
- **Pasted Spotify links** (`open.spotify.com/...`) always work: Jarvis opens them in the Spotify app with `:play` so they start.
- **Playing by name** needs a free Spotify developer app so Jarvis can look the song up. Create one at developer.spotify.com/dashboard (any name; Redirect URI `http://127.0.0.1:8888/callback`), then put the Client ID and Client secret in `.env` as `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`. Without them, Jarvis opens a Spotify search for you instead.
- **Pause / next / previous** use your keyboard's media keys, so they work for Spotify and most other players. The Spotify desktop app must be installed and running for links to start playing.
- **Recommendations** come from the AI model's own music knowledge, not from Spotify (Spotify closed its recommendation API to new apps). Ask in plain words, e.g. "recommend 5 songs like Starboy", then say "play the first one".
- Not tested on a real Spotify account yet, so please report what happens.

Per-OS requirements:

| | Volume | Brightness | Notes |
|---|---|---|---|
| **Windows** | `pycaw` (auto-installed) | `screen-brightness-control` (auto-installed) | Works on most laptop screens; some external monitors don't support it |
| **macOS** | built in | `brew install brightness` | Screen lock uses display sleep; set "require password immediately" in System Settings |
| **Linux** | `pactl` or `amixer` | `brightnessctl` (`sudo apt install brightnessctl`) | `xdg-open` and `loginctl` are used for files and locking |

## How it works

```
 you type a command
        |
        v
  [ router ]  matches simple commands with regexes ("volume 40", "open chrome")
        |            -> runs the tool directly: instant, free, works offline
        | no match
        v
  [ AI brain ]  Gemini (primary) -> Groq (backup if Gemini errors or hits its quota)
        |            picks tools, reads results, answers
        v
  [ tool registry ]  every tool goes through the same safety wrapper
```

If a fast-path command fails (for example `open youtube` isn't an installed app), the AI gets a chance to recover (it will open the website instead).

## Troubleshooting

Run this first. It tests your keys and web search and tells you what's wrong in plain words:

```bash
python -m jarvis --check
```

| What you see | What it means | Fix |
|---|---|---|
| `.env file: NOT FOUND` | Jarvis can't see your keys | `.env` must sit next to `README.md`. Copy `.env.example` to `.env` |
| `Gemini key: missing` | Nothing after `GEMINI_API_KEY=` | Paste your key there, no spaces or quotes, then save |
| `FAIL, the API key was rejected` | The key is wrong or is on the wrong line | Google keys start with `AIza` and go on the `GEMINI_API_KEY` line. Groq keys start with `gsk_` and go on the `GROQ_API_KEY` line |
| `FAIL, the free-tier limit was reached` | You used up the free quota for now | Wait a minute, or add a Groq key as a backup |
| `Web search: FAIL` | Can't reach the search service | Check your internet or try another network |

## Safety model

An assistant that can control your computer has to be careful. What's built in:

- **Confirmation for risky actions.** Shutdown, restart and sleep ask `[y/N]` on every call. The check lives in the tool wrapper, so neither the AI nor the router can skip it.
- **No shell.** Commands are run as argument lists, never through a shell, and app names are restricted to plain characters.
- **No launching programs.** `open_path` refuses `.exe`, `.sh`, `.bat`, `.py` and other executable or script types.
- **Web content is untrusted.** Pages and search results are labelled as untrusted data in the model's context, and the system prompt tells it not to obey instructions found in them. Because the dangerous tools always ask you first, a malicious page can't silently shut your laptop down.
- **SSRF guard.** `read_webpage` only fetches public `http(s)` addresses and re-checks every redirect, so it can't be tricked into reading `localhost`, your router, or cloud metadata endpoints.
- **Secrets stay local.** `.env` is git-ignored. Never commit API keys.

Not covered yet: there is no deletion or arbitrary-shell tool *on purpose*. If you add one, mark it `risk="confirm"`.

## Add your own tool

Create a function, decorate it, done. The AI discovers it automatically from the type hints and docstring.

```python
# jarvis/tools/notes.py
from ..registry import tool

@tool()  # use @tool(risk="confirm") for anything destructive
def add_note(text: str) -> str:
    """Save a quick note to a text file.

    Args:
        text: The note to save.
    """
    with open("notes.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")
    return "Note saved."
```

Then add `notes` to the import line in `jarvis/tools/__init__.py`. Rules: type-hint every parameter (`str`, `int`, `float`, `bool`), return a short string, and return `Error: ...` on failure. To add a fast-path phrase, add a rule to `jarvis/router.py`.

## Configuration

Set in `.env` (see `.env.example`):

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Primary brain (free at aistudio.google.com) |
| `GROQ_API_KEY` | Optional backup brain (free at console.groq.com) |
| `JARVIS_CITY` | Default city for `weather` |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Optional, lets `play <song name>` start songs automatically |
| `JARVIS_GEMINI_MODEL` | Default `gemini-flash-latest` |
| `JARVIS_GROQ_MODEL` | Default `openai/gpt-oss-120b` |

Free-tier limits and model names change often. If you get quota errors, check your limits in AI Studio, or add the Groq key so JARVIS falls back automatically. Free-tier prompts to Google may be used to improve their products, so don't paste anything private.

## Tests

```bash
pip install pytest
python -m pytest -q
```

The tests need no network, API keys or special hardware: OS-specific commands are captured rather than run, and the Groq loop is tested against a fake server. CI runs them on Linux, Windows and macOS (see `.github/workflows/ci.yml`).

**Honest limits:** real calls to Gemini, Groq and web search, and the Windows/macOS system calls (volume, brightness, lock), are only covered by command-capture tests, not by end-to-end runs on every OS. If something misbehaves on your machine, please open an issue with your OS and the output of `python -m jarvis --once "<command>"`.

## Roadmap

- [x] **Stage 1: Core.** Typed commands, app and system control, web research, safety layer, Gemini + Groq
- [x] **Stage 1.5: Weather, notes, notebook UI, Spotify** (this release)
- [ ] **Stage 2: Voice.** Wake word ("Hey Jarvis") with openWakeWord, speech-to-text with Whisper, spoken replies with edge-tts
- [ ] **Stage 3: Senses and memory.** "What's on my screen?" (screenshot to Gemini vision), webcam, and a local memory file of your preferences and past chats
- [ ] **Stage 4: Proactive.** Reminders, a daily briefing, background alerts, and a sci-fi HUD dashboard
- [ ] Home automation through Home Assistant
- [ ] A sandboxed "write and run code" tool

Contributions welcome. Pick a roadmap item or a new tool, add tests, and open a PR.

## License

MIT. See [LICENSE](LICENSE).
