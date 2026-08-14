"""Compatibility entry point for Jarvis.

The full implementation lives in :mod:`jarvis.core`.
Run this file exactly as before:
    python jarvisvav1.py
"""

from jarvis.core import *  # noqa: F401,F403
from jarvis.core import main


if __name__ == "__main__":
    main()
