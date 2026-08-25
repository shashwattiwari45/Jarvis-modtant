"""Unified local-first JARVIS voice engine.

One microphone owner, one STT backend, explicit voice states, and low-latency
barge-in while TTS is speaking. Audio capture and speech recognition remain
local wherever possible.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

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
        barge_in: bool = True,
    ) -> None:
        self.process_text = process_text
        self.speak = speak
        self.stop_speaking = stop_speaking
        self.existing_model = existing_model
        self.barge_in = barge_in
        self.state = VoiceState.IDLE
        self.running = False
        self._stop = threading.Event()
        self._speech_lock = threading.Lock()
        self._speaking_thread: Optional[threading.Thread] = None
        self._interrupt_event = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()
        self._interrupt_event.set()
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

    def _speak_worker(self, text: str) -> None:
        try:
            with self._speech_lock:
                self.speak(text)
        finally:
            if self.state == VoiceState.SPEAKING:
                self.state = VoiceState.IDLE

    def _start_speaking(self, text: str) -> None:
        self.state = VoiceState.SPEAKING
        self._interrupt_event.clear()
        self._speaking_thread = threading.Thread(
            target=self._speak_worker,
            args=(text,),
            daemon=True,
            name="jarvis-tts",
        )
        self._speaking_thread.start()

    def _wait_or_interrupt_speech(self) -> Optional[str]:
        thread = self._speaking_thread
        if not thread:
            return None
        if not self.barge_in:
            thread.join()
            return None

        # Very lightweight local RMS watcher used only during TTS. It does not
        # transcribe audio; it detects a sustained user speech-like signal and
        # then lets the normal local STT path take ownership.
        try:
            device = local_stt.get_input_device()
        except Exception:
            device = None
        try:
            sample_rate = local_stt.get_input_sample_rate(device)
        except Exception:
            sample_rate = 16000

        block_seconds = 0.10
        block_size = max(1, int(sample_rate * block_seconds))
        noise = []
        voice_hits = 0
        threshold = None

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                blocksize=block_size,
                device=device,
                latency="low",
            ) as stream:
                for _ in range(3):
                    data, _ = stream.read(block_size)
                    noise.append(data[:, 0].copy())
                baseline = local_stt.rms(np.concatenate(noise)) if noise else 0.0
                threshold = max(500.0, baseline * 3.0)

                while thread.is_alive() and not self._stop.is_set():
                    data, _ = stream.read(block_size)
                    level = local_stt.rms(data[:, 0])
                    voice_hits = voice_hits + 1 if level >= threshold else 0
                    if voice_hits >= 2:
                        self.state = VoiceState.INTERRUPTED
                        self._interrupt_event.set()
                        self._stop_tts()
                        return "__INTERRUPT__"
        except Exception:
            thread.join()
        return None

    def _speak_and_wait(self, text: str) -> bool:
        if not text:
            return False
        self._start_speaking(text)
        interrupted = self._wait_or_interrupt_speech()
        if interrupted == "__INTERRUPT__":
            thread = self._speaking_thread
            if thread and thread.is_alive():
                thread.join(timeout=1.0)
            return True
        return False

    def run_once(self) -> str:
        text = self._listen_once()
        if not text:
            self.state = VoiceState.IDLE
            return ""

        lowered = text.lower()
        if lowered in {"stop", "exit", "quit"}:
            self.request_stop()
            self.state = VoiceState.IDLE
            return text

        self.state = VoiceState.PROCESSING
        response = self.process_text(text)
        self._speak_and_wait(response)
        self.state = VoiceState.IDLE if not self._stop.is_set() else VoiceState.INTERRUPTED
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
                    time.sleep(0.2)
        finally:
            self._stop_tts()
            self.running = False
            self.state = VoiceState.IDLE
