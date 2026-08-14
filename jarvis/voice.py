"""Public voice/STT facade.

The implementations currently live in jarvis.core to preserve behavior. This facade gives
future modules a stable import surface while extraction is done incrementally.
"""
from .core import (
    listen, speak, switch_voice, _listen_with_whisper, _listen_with_google,
)

__all__ = ["listen", "speak", "switch_voice", "_listen_with_whisper", "_listen_with_google"]
