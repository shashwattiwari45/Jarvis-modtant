"""Compatibility entry point for Jarvis.

Run this file exactly as before:
    python jarvisvav1.py

The launcher now selects the local-first runtime for capable Windows laptops.
All legacy `jarvis.core` exports remain available for compatibility.
"""
import os
import subprocess
import sys
from pathlib import Path

from jarvis.core import *  # noqa: F401,F403
from jarvis.local_entrypoint import main

__all__ = ["main"]


if __name__ == "__main__":
    if os.getenv("JARVIS_HUD_CHILD") != "1":
        web_ui = Path(__file__).resolve().parent / "web_ui"
        hud_env = os.environ.copy()
        hud_env["JARVIS_HUD_CHILD"] = "1"
        hud_env["JARVIS_PYTHON"] = sys.executable
        try:
            subprocess.Popen(
                ["npm.cmd", "run", "desktop:dev"],
                cwd=web_ui,
                env=hud_env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            print("[JARVIS HUD] Starting desktop HUD...")
        except OSError as exc:
            print(f"[JARVIS HUD] Could not start automatically: {exc}")
    main()
