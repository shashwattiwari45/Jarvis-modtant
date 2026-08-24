"""Continuous voice-session runtime for JARVIS.

Keeps one SpeechRecognition microphone session alive instead of repeatedly
opening/calibrating the microphone for every turn. Audio is transcribed by the
existing Whisper/Google pipeline in core.py, then sent through the existing
local-action + tool-calling brain.
"""
from __future__ import annotations

import queue
import re
import threading
import time

try:
    import speech_recognition as sr
except ImportError:
    sr = None


WAKE_PHRASES = (
    re.compile(r"\bwake up\s+jarvis\b", re.I),
    re.compile(r"\bhey\s+jarvis\b", re.I),
    re.compile(r"\bokay\s+jarvis\b", re.I),
    re.compile(r"\bok\s+jarvis\b", re.I),
)
SLEEP_PHRASE = re.compile(r"\b(?:go to sleep|sleep|stand by|standby)\s+jarvis\b", re.I)


class ContinuousVoiceSession:
    """One persistent microphone stream feeding the existing JARVIS brain."""

    def __init__(self, core, dictation_mode=False):
        self.core = core
        self.queue: queue.Queue = queue.Queue(maxsize=4)
        self.stop_background = None
        self.running = False
        self.asleep = False
        self.dictation_mode = dictation_mode
        self.speaking = threading.Event()
        self._last_audio_at = time.monotonic()

    def configure_microphone(self) -> None:
        recognizer = self.core.recognizer
        recognizer.pause_threshold = 0.85
        recognizer.non_speaking_duration = 0.25
        recognizer.phrase_threshold = 0.15
        recognizer.dynamic_energy_threshold = True
        recognizer.dynamic_energy_adjustment_damping = 0.05
        recognizer.dynamic_energy_ratio = 1.15
        recognizer.operation_timeout = None

    def _callback(self, recognizer, audio) -> None:
        # The microphone remains open continuously. During JARVIS speech we
        # discard captured audio so the speaker's own TTS cannot become a command.
        if self.speaking.is_set():
            return
        try:
            self.queue.put_nowait(audio)
            self._last_audio_at = time.monotonic()
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(audio)
            except queue.Full:
                pass

    def start(self) -> None:
        if not sr or not self.core.recognizer:
            raise RuntimeError("SpeechRecognition/PyAudio is required for continuous voice mode.")

        self.configure_microphone()
        self.source = sr.Microphone()
        with self.source as source:
            print("[JARVIS Voice] Calibrating microphone once...")
            self.core.recognizer.adjust_for_ambient_noise(source, duration=0.8)
            print(
                "[JARVIS Voice] Continuous microphone active. "
                "Speak naturally; no repeated mic startup."
            )
            print(f"[JARVIS Voice] Energy threshold: {self.core.recognizer.energy_threshold:.0f}")

        self.stop_background = self.core.recognizer.listen_in_background(
            self.source,
            self._callback,
            phrase_time_limit=14,
        )
        self.running = True

    def stop(self) -> None:
        self.running = False
        if self.stop_background:
            try:
                self.stop_background(wait_for_stop=False)
            except Exception:
                pass
            self.stop_background = None
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def _transcribe(self, audio) -> str:
        if getattr(self.core, "_whisper_model", None):
            return self.core._listen_with_whisper(audio)
        return self.core._listen_with_google(audio)

    def _speak(self, text: str, force: bool = True) -> None:
        self.speaking.set()
        try:
            self.core.speak(text, force=force)
        finally:
            self.speaking.clear()
            # Drop anything captured during the response before the next turn.
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break

    def _wake_match(self, text: str) -> bool:
        return any(p.search(text) for p in WAKE_PHRASES)

    def _handle_text(self, text: str) -> bool:
        """Return False when the session should terminate."""
        text = text.strip().lower()
        if not text:
            return True

        if text in ("stop", "exit", "quit", "goodbye jarvis"):
            self._speak("Okay, bye!")
            try:
                self.core.save_memory()
            finally:
                return False

        if self.asleep:
            if self._wake_match(text):
                self.asleep = False
                self._speak("I'm listening, boss.")
            return True

        if SLEEP_PHRASE.search(text):
            self.asleep = True
            self._speak("Going quiet. Say wake up Jarvis when you need me.")
            return True

        if any(p in text for p in self.core.DICTATION_START_PHRASES):
            self.dictation_mode = True
            self.core.open_application("notepad")
            time.sleep(0.8)
            self._speak("Dictation on. Say stop dictation when you're done.")
            return True

        if self.dictation_mode:
            if any(p in text for p in self.core.DICTATION_STOP_PHRASES):
                self.dictation_mode = False
                self._speak("Dictation off.")
            else:
                self.core.type_text(text + " ")
            return True

        if text in {"i'm leaving", "im leaving", "jarvis i'm leaving", "i am leaving"}:
            self.core.set_quiet_mode(True)
            self.core.add_task_memory("User stepped away; resume the previous context when they return.")
            self._speak("Got it. Quiet mode on, and I'll remember where we left off.", force=True)
            return True

        if text in {"i'm going to sleep", "im going to sleep", "good night", "going to sleep"}:
            self.core.set_quiet_mode(True)
            self._speak("Good night. I'll stay quiet and keep the essentials watched.", force=True)
            return True

        if "where did we leave off" in text or "continue what we were doing" in text:
            self._speak(self.core.continue_last_task(), force=True)
            return True

        self.core.set_status("thinking")
        reply = self.core.think_and_act(text)
        self.core.set_status(
            "success" if not reply.lower().startswith(("sorry", "i hit", "that action failed")) else "failure"
        )
        self._speak(reply, force=True)
        return True

    def run(self) -> None:
        self.start()
        try:
            while self.running:
                try:
                    audio = self.queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                try:
                    text = self._transcribe(audio).strip().lower()
                except Exception as exc:
                    print(f"[JARVIS Voice] Transcription error: {exc}")
                    continue

                if text:
                    print(f"[JARVIS Voice] You: {text}")
                    if not self._handle_text(text):
                        break
        finally:
            self.stop()


def run(core) -> None:
    """Run one persistent hands-free voice session using core's brain."""
    ContinuousVoiceSession(core).run()
