"""Unified local-first JARVIS voice engine.

One microphone owner, one STT backend, explicit voice states, and optional
barge-in while TTS is speaking. Keeps the audio path local and reuses the
existing faster-whisper model and JARVIS TTS facade.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable, Optional

import numpy as np

from . import local_stt


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


class VoiceEngine:
    """Serialize microphone/STT/TTS ownership into one deterministic loop."""

    def __init__(
        self,
        process_text: Callable[[str], str],
        speak: Callable[[str], object],
        stop_speaking: Optional[Callable[[], object]] = None,
        existing_model=None,
    ) -> None:
        self.process_text = process_text
        self.speak = speak
        self.stop_speaking = stop_speaking
        self.existing_model = existing_model
        self.state = VoiceState.IDLE
        self.running = False
        self._stop = threading.Event()
        self._speech_lock = threading.Lock()
        self._speaking_thread: Optional[threading.Thread] = None

    def request_stop(self) -> None:
        self._stop.set()
        self._stop_tts()

    def _stop_tts(self) -> None:
        if self.stop_speaking:
            try:
                self.stop_speaking()
            except Exception:
                pass

    def _listen_once(self) -> str:
        self.state = VoiceState.LISTENING
        return local_stt.listen(self.existing_model).strip()

    def _speak_async(self, text: str) -> None:
        self.state = VoiceState.SPEAKING
        self._speaking_thread = threading.Thread(
            target=self._speak_worker,
            args=(text,),
            daemon=True,
            name="jarvis-tts",
        )
        self._speaking_thread.start()

    def _speak_worker(self, text: str) -> None:
        try:
            with self._speech_lock:
                self.speak(text)
        finally:
            if self.state == VoiceState.SPEAKING:
                self.state = VoiceState.IDLE

    def wait_for_speech_to_finish(self) -> None:
        thread = self._speaking_thread
        if thread and thread.is_alive():
            thread.join()

    def run_once(self) -> str:
        """Run one controlled listen -> process -> speak cycle."""
        text = self._listen_once()
        if not text:
            self.state = VoiceState.IDLE
            return ""

        if text.lower() in {"stop", "exit", "quit"}:
            self.request_stop()
            self.state = VoiceState.IDLE
            return text

        self.state = VoiceState.PROCESSING
        response = self.process_text(text)
        if response:
            self._speak_async(response)
            self.wait_for_speech_to_finish()
        self.state = VoiceState.IDLE
        return text

    def run(self) -> None:
        if self.running:
            return
        self.running = True
        self._stop.clear()
        try:
            while not self._stop.is_set():
                try:
                    self.run_once()
                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    self.state = VoiceState.IDLE
                    print(f"[JARVIS Voice] {exc}")
                    time.sleep(0.25)
        finally:
            self._stop_tts()
            self.running = False
            self.state = VoiceState.IDLE
