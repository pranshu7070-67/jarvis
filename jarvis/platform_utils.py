"""Small OS helpers. Kept in one place so tests can swap them out."""

import platform
import shutil
import subprocess


def current_os() -> str:
    """'Windows', 'Darwin' (macOS) or 'Linux'."""
    return platform.system()


def which(name: str):
    return shutil.which(name)


def run(cmd: list, timeout: int = 10) -> tuple:
    """Run a command (never through a shell). Returns (ok, output)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, f"'{cmd[0]}' is not installed"
    except subprocess.TimeoutExpired:
        return False, f"'{cmd[0]}' timed out"
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, output
