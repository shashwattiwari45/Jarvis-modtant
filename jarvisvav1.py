"""Compatibility entry point for Jarvis.

Run this file exactly as before:
    python jarvisvav1.py

The launcher now selects the local-first runtime for capable Windows laptops.
All legacy `jarvis.core` exports remain available for compatibility.
"""
from jarvis.core import *  # noqa: F401,F403
from jarvis.local_entrypoint import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
