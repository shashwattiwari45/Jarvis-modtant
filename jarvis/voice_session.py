"""Local voice-session runtime for JARVIS."""
from __future__ import annotations

import re
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / "web_ui" / ".env")
except ImportError:
    pass

from . import local_stt


WAKE_PHRASES = (
    re.compile(r"\bwake up\s+jarvis\b", re.I),
    re.compile(r"\bhey\s+jarvis\b", re.I),
    re.compile(r"\bokay\s+jarvis\b", re.I),
    re.compile(r"\bok\s+jarvis\b", re.I),
)
SLEEP_PHRASE = re.compile(r"\b(?:go to sleep|sleep|stand by|standby)\s+jarvis\b", re.I)


class ContinuousVoiceSession:
    """Feed one VAD-bounded utterance at a time into the existing JARVIS brain."""

    def __init__(self, core, dictation_mode=False):
        self.core = core
        self.running = False
        self.asleep = False
        self.dictation_mode = dictation_mode

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def _listen(self) -> str:
        """Capture one VAD-bounded utterance without competing with TTS."""
        audio_lock = getattr(self.core, "AUDIO_LOCK", None)
        if audio_lock is None:
            return local_stt.listen()
        with audio_lock:
            return local_stt.listen()

    def _speak(self, text: str, force: bool = True) -> None:
        self.core.speak(text, force=force)

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
                pass
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
                    text = self._listen().strip().lower()
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
