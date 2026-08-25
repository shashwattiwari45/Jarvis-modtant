"""Compatibility voice session using the unified local-first voice engine."""
from __future__ import annotations

from .voice_engine import VoiceEngine


class ContinuousVoiceSession:
    def __init__(self, core):
        self.core = core
        self.engine = VoiceEngine(
            process_text=self._process_text,
            speak=self._speak,
            stop_speaking=self._stop_speaking,
            existing_model=getattr(core, "_whisper_model", None),
        )

    def _process_text(self, text: str) -> str:
        handler = getattr(self.core, "think_and_act", None)
        if handler is None:
            return ""
        result = handler(text)
        if isinstance(result, str):
            return result
        return str(result) if result is not None else ""

    def _speak(self, text: str) -> object:
        speaker = getattr(self.core, "speak", None)
        if speaker is None:
            return None
        return speaker(text)

    def _stop_speaking(self) -> object:
        stop = getattr(self.core, "stop_speaking", None)
        if callable(stop):
            return stop()
        return None

    def start(self) -> None:
        self.engine.run()

    def run(self) -> None:
        self.start()


def run(core) -> None:
    ContinuousVoiceSession(core).run()
