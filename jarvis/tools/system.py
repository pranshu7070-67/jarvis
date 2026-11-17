"""Volume, brightness, power, screenshots and system status.

OS-specific calls are isolated here. Linux/macOS use built-in or common command line
tools; Windows uses the pycaw and screen-brightness-control packages (installed by
requirements.txt on Windows only).
"""

from datetime import datetime
from pathlib import Path

from .. import platform_utils as pu
from ..registry import tool


def _clamp(percent) -> int:
    return max(0, min(100, int(percent)))


def _result(ok: bool, out: str, success: str) -> str:
    return success if ok else f"Error: {out or 'command failed'}"


# ---------------------------------------------------------------- volume --

def _win_endpoint():
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError as exc:
        raise RuntimeError("volume control on Windows needs: pip install pycaw") from exc
    device = AudioUtilities.GetSpeakers()
    if hasattr(device, "EndpointVolume"):  # newer pycaw
        return device.EndpointVolume
    from ctypes import POINTER, cast  # older pycaw
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    iface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


@tool()
def set_volume(percent: int) -> str:
    """Set the speaker volume.

    Args:
        percent: Volume level from 0 to 100.
    """
    level = _clamp(percent)
    os_name = pu.current_os()
    if os_name == "Windows":
        _win_endpoint().SetMasterVolumeLevelScalar(level / 100, None)
        return f"Volume set to {level}%."
    if os_name == "Darwin":
        ok, out = pu.run(["osascript", "-e", f"set volume output volume {level}"])
    elif pu.which("pactl"):
        ok, out = pu.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
    elif pu.which("amixer"):
        ok, out = pu.run(["amixer", "sset", "Master", f"{level}%"])
    else:
        return "Error: install pactl (PulseAudio/PipeWire) or amixer to control volume."
    return _result(ok, out, f"Volume set to {level}%.")


@tool()
def set_mute(muted: bool = True) -> str:
    """Mute or unmute the speakers.

    Args:
        muted: True to mute, False to unmute.
    """
    os_name = pu.current_os()
    word = "muted" if muted else "unmuted"
    if os_name == "Windows":
        _win_endpoint().SetMute(1 if muted else 0, None)
        return f"Speakers {word}."
    if os_name == "Darwin":
        flag = "true" if muted else "false"
        ok, out = pu.run(["osascript", "-e", f"set volume output muted {flag}"])
    elif pu.which("pactl"):
        ok, out = pu.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"])
    elif pu.which("amixer"):
        ok, out = pu.run(["amixer", "sset", "Master", "mute" if muted else "unmute"])
    else:
        return "Error: install pactl or amixer to control the mute state."
    return _result(ok, out, f"Speakers {word}.")


# ------------------------------------------------------------ brightness --

@tool()
def set_brightness(percent: int) -> str:
    """Set the screen brightness.

    Args:
        percent: Brightness from 0 to 100.
    """
    level = _clamp(percent)
    os_name = pu.current_os()
    if os_name == "Windows":
        try:
            import screen_brightness_control as sbc
        except ImportError as exc:
            raise RuntimeError("needs: pip install screen-brightness-control") from exc
        sbc.set_brightness(level)
        return f"Brightness set to {level}%."
    if os_name == "Darwin":
        if not pu.which("brightness"):
            return "Error: on macOS install the helper first: brew install brightness"
        ok, out = pu.run(["brightness", f"{level / 100:.2f}"])
    elif pu.which("brightnessctl"):
        ok, out = pu.run(["brightnessctl", "set", f"{level}%"])
    else:
        return "Error: install brightnessctl to control brightness on Linux."
    return _result(ok, out, f"Brightness set to {level}%.")


# ----------------------------------------------------------------- power --

@tool()
def lock_screen() -> str:
    """Lock the computer screen."""
    os_name = pu.current_os()
    if os_name == "Windows":
        ok, out = pu.run(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif os_name == "Darwin":
        ok, out = pu.run(["pmset", "displaysleepnow"])
    elif pu.which("loginctl"):
        ok, out = pu.run(["loginctl", "lock-session"])
    elif pu.which("xdg-screensaver"):
        ok, out = pu.run(["xdg-screensaver", "lock"])
    else:
        return "Error: no screen-lock command found."
    return _result(ok, out, "Screen locked.")


def _power(action: str) -> str:
    """action is 'sleep', 'restart' or 'shutdown'."""
    os_name = pu.current_os()
    commands = {
        "Windows": {
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "restart": ["shutdown", "/r", "/t", "10"],
            "shutdown": ["shutdown", "/s", "/t", "10"],
        },
        "Darwin": {
            "sleep": ["pmset", "sleepnow"],
            "restart": ["osascript", "-e", 'tell app "System Events" to restart'],
            "shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'],
        },
        "Linux": {
            "sleep": ["systemctl", "suspend"],
            "restart": ["systemctl", "reboot"],
            "shutdown": ["systemctl", "poweroff"],
        },
    }
    cmd = commands.get(os_name, commands["Linux"])[action]
    ok, out = pu.run(cmd, timeout=15)
    extra = " Run 'shutdown /a' within 10 seconds to abort." if os_name == "Windows" and action != "sleep" else ""
    return _result(ok, out, f"Okay: {action} started.{extra}")


@tool(risk="confirm")
def sleep_computer() -> str:
    """Put the computer to sleep."""
    return _power("sleep")


@tool(risk="confirm")
def restart_computer() -> str:
    """Restart the computer."""
    return _power("restart")


@tool(risk="confirm")
def shutdown_computer() -> str:
    """Shut the computer down."""
    return _power("shutdown")


# --------------------------------------------------------- info & capture --

@tool()
def take_screenshot() -> str:
    """Take a screenshot of the screen and save it to Pictures/jarvis."""
    try:
        import mss
    except ImportError as exc:
        raise RuntimeError("needs: pip install mss") from exc
    folder = Path.home() / "Pictures" / "jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    with mss.mss() as sct:
        sct.shot(mon=-1, output=str(path))
    return f"Saved screenshot to {path}"


def system_report(cpu_interval: float = 0.3) -> dict:
    """Structured CPU / memory / disk / battery numbers (used by the tool and the web UI)."""
    import psutil
    report = {"cpu": psutil.cpu_percent(interval=cpu_interval),
              "mem": psutil.virtual_memory().percent, "disk": None, "battery": None}
    try:
        report["disk"] = psutil.disk_usage(str(Path.home())).percent
    except OSError:
        pass
    battery = psutil.sensors_battery()
    if battery is not None:
        report["battery"] = {"percent": battery.percent, "plugged": bool(battery.power_plugged)}
    return report


@tool()
def system_status() -> str:
    """Report battery, CPU, memory and disk usage."""
    r = system_report(0.5)
    lines = [f"CPU: {r['cpu']:.0f}%", f"Memory: {r['mem']:.0f}% used"]
    if r["disk"] is not None:
        lines.append(f"Disk: {r['disk']:.0f}% used")
    if r["battery"] is not None:
        state = "charging" if r["battery"]["plugged"] else "on battery"
        lines.insert(0, f"Battery: {r['battery']['percent']:.0f}% ({state})")
    return "\n".join(lines)


@tool()
def get_time() -> str:
    """Get the current local date and time."""
    return datetime.now().astimezone().strftime("%A, %d %B %Y, %I:%M %p %Z")


@tool()
def small_talk(kind: str = "hello") -> str:
    """Reply instantly to a greeting or thanks without using the AI.

    Args:
        kind: hello, thanks or bye.
    """
    from datetime import datetime
    if kind == "thanks":
        return "Anytime."
    if kind == "bye":
        return "See you later."
    hour = datetime.now().hour
    part = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    return f"{part}. What can I do for you?"
