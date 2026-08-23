"""Fast deterministic Windows actions for common JARVIS commands.

These handlers are deliberately small and conservative. They cover the common
"open X" requests that should not need an LLM tool-selection round trip. All
other requests continue through the existing JARVIS tool-calling brain.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path


WEB_APPS = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "github": "https://github.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
}

APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "settings": "ms-settings:",
    "task manager": "taskmgr.exe",
}


def _chrome_path() -> str | None:
    candidates = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return shutil.which("chrome") or shutil.which("chrome.exe")


def _open_chrome(url: str | None = None) -> str:
    target = url or "about:blank"
    chrome = _chrome_path()
    if chrome:
        subprocess.Popen([chrome, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Chrome is open."
    # If Chrome is not installed, do not silently substitute another browser.
    return "I couldn't find Google Chrome on this PC."


def try_execute(text: str) -> str | None:
    """Execute a small set of deterministic local commands, or return None."""
    if os.name != "nt":
        return None

    raw = " ".join(str(text).strip().split())
    lowered = raw.casefold()
    if not raw:
        return None

    # Chrome must be handled explicitly so "open Chrome" does not depend on
    # the default Windows browser.
    if re.fullmatch(r"(?:please )?(?:open|launch|start) (?:google )?chrome", lowered):
        return _open_chrome()

    chrome_url = re.fullmatch(
        r"(?:please )?(?:open|launch|start) (?:google )?chrome (?:and )?(?:open|go to) (https?://\S+)",
        lowered,
    )
    if chrome_url:
        return _open_chrome(chrome_url.group(1))

    for name, url in WEB_APPS.items():
        if re.fullmatch(rf"(?:please )?(?:open|launch|start) {re.escape(name)}", lowered):
            webbrowser.open(url)
            return f"Opening {name}."

    for name, executable in APP_ALIASES.items():
        if re.fullmatch(rf"(?:please )?(?:open|launch|start) {re.escape(name)}", lowered):
            if executable.endswith(":"):
                os.startfile(executable)
            else:
                subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening {name}."

    url_match = re.fullmatch(r"(?:please )?(?:open|go to) (https?://\S+)", raw, flags=re.I)
    if url_match:
        webbrowser.open(url_match.group(1))
        return "Opening the requested page."

    if lowered in {"close chrome", "exit chrome", "quit chrome"}:
        subprocess.run(["taskkill", "/IM", "chrome.exe", "/F"], capture_output=True)
        return "Chrome closed."

    return None
