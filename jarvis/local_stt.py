"""Local microphone STT for JARVIS.

Uses sounddevice for capture and faster-whisper for offline transcription.
It avoids the SpeechRecognition/PyAudio dependency for the primary local path.
"""
from __future__ import annotations

import os
import time
import wave
import tempfile

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

from .hardware_profile import PROFILE, whisper_kwargs

_MODEL = None


def _get_model(existing=None):
    global _MODEL
    if existing is not None:
        return existing
    if _MODEL is None and WhisperModel is not None:
        _MODEL = WhisperModel(PROFILE.whisper_model, **whisper_kwargs())
    return _MODEL


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    x = samples.astype(np.float32)
    return float(np.sqrt(np.mean(x * x)))


def record_until_silence(
    sample_rate: int = 16000,
    max_seconds: float = 10.0,
    start_timeout: float = 5.0,
    silence_seconds: float = 0.85,
):
    if sd is None:
        raise RuntimeError("sounddevice is not installed.")

    block_seconds = 0.1
    block_size = int(sample_rate * block_seconds)
    calibration_blocks = max(1, int(0.5 / block_seconds))
    blocks = []
    noise_samples = []

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=block_size,
    ) as stream:
        for _ in range(calibration_blocks):
            data, _ = stream.read(block_size)
            noise_samples.append(data[:, 0].copy())

        noise = _rms(np.concatenate(noise_samples))
        threshold = max(350.0, noise * 2.2)
        started = False
        last_voice_at = time.monotonic()
        deadline = time.monotonic() + max_seconds
        start_deadline = time.monotonic() + start_timeout

        while time.monotonic() < deadline:
            data, _ = stream.read(block_size)
            mono = data[:, 0].copy()
            level = _rms(mono)
            now = time.monotonic()

            if level >= threshold:
                started = True
                last_voice_at = now

            if started:
                blocks.append(mono)
                if now - last_voice_at >= silence_seconds:
                    break
            elif now >= start_deadline:
                break

    if not blocks:
        return np.empty(0, dtype=np.int16), sample_rate
    return np.concatenate(blocks), sample_rate


def transcribe(samples: np.ndarray, sample_rate: int, model=None) -> str:
    if samples.size == 0:
        return ""
    active_model = _get_model(model)
    if active_model is None:
        raise RuntimeError("faster-whisper is not installed.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name

    try:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())

        segments, _ = active_model.transcribe(
            path,
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def listen(existing_model=None) -> str:
    """Capture one natural utterance and return its transcription."""
    try:
        samples, rate = record_until_silence()
        text = transcribe(samples, rate, existing_model)
        if text:
            print(f"You: {text}")
        return text
    except Exception as exc:
        print(f"[Local STT] {exc}")
        return ""
