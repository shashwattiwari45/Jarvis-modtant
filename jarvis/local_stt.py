"""Low-latency local microphone STT for JARVIS."""
from __future__ import annotations

import os
import time
import wave
import tempfile
from typing import Optional

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


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    x = samples.astype(np.float32)
    return float(np.sqrt(np.mean(x * x)))


def get_input_device():
    if sd is None:
        return None
    value = os.getenv("JARVIS_INPUT_DEVICE", "").strip()
    if value:
        try:
            return int(value)
        except ValueError:
            wanted = value.casefold()
            for index, info in enumerate(sd.query_devices()):
                if int(info.get("max_input_channels", 0)) > 0 and wanted in str(info.get("name", "")).casefold():
                    return index
            raise RuntimeError(f"Microphone '{value}' was not found.")
    default = sd.default.device[0]
    return int(default) if default is not None and int(default) >= 0 else None


def get_input_sample_rate(device: Optional[int] = None) -> int:
    if sd is None:
        return 16000
    try:
        info = sd.query_devices(device, "input")
        return int(round(float(info.get("default_samplerate", 16000))))
    except Exception:
        return 16000


def record_until_silence(
    sample_rate: Optional[int] = None,
    max_seconds: float = 10.0,
    start_timeout: float = 5.0,
    silence_seconds: float = 0.85,
):
    """Capture one utterance using the microphone's native rate."""
    if sd is None:
        raise RuntimeError("sounddevice is not installed.")

    device = get_input_device()
    if device is None:
        raise RuntimeError("No input microphone is configured.")
    rate = int(sample_rate or get_input_sample_rate(device))

    block_seconds = 0.1
    block_size = int(rate * block_seconds)
    calibration_blocks = max(1, int(0.5 / block_seconds))
    blocks = []
    noise_samples = []

    try:
        with sd.InputStream(
            samplerate=rate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
            device=device,
            latency="low",
        ) as stream:
            for _ in range(calibration_blocks):
                data, _ = stream.read(block_size)
                noise_samples.append(data[:, 0].copy())

            noise = rms(np.concatenate(noise_samples))
            threshold = max(350.0, noise * 2.2)
            started = False
            last_voice_at = time.monotonic()
            deadline = time.monotonic() + max_seconds
            start_deadline = time.monotonic() + start_timeout

            while time.monotonic() < deadline:
                data, _ = stream.read(block_size)
                mono = data[:, 0].copy()
                level = rms(mono)
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
    except Exception as exc:
        raise RuntimeError(f"Microphone capture failed at {rate} Hz: {exc}") from exc

    if not blocks:
        return np.empty(0, dtype=np.int16), rate
    return np.concatenate(blocks), rate


def _to_16k(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    """Convert capture to Whisper's 16 kHz input locally."""
    target = 16000
    if sample_rate == target:
        return samples, target
    duration = samples.size / float(sample_rate)
    target_len = max(1, int(round(duration * target)))
    indices = np.linspace(0, samples.size - 1, target_len)
    converted = np.interp(indices, np.arange(samples.size), samples.astype(np.float32))
    return converted.astype(np.int16), target


def transcribe(samples: np.ndarray, sample_rate: int, model=None) -> str:
    if samples.size == 0:
        return ""
    active_model = _get_model(model)
    if active_model is None:
        raise RuntimeError("faster-whisper is not installed.")

    samples, sample_rate = _to_16k(samples, sample_rate)
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
            temperature=0.0,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def listen(existing_model=None) -> str:
    """Capture one utterance and return its transcription."""
    try:
        samples, rate = record_until_silence()
        text = transcribe(samples, rate, existing_model)
        if text:
            print(f"[JARVIS STT] You: {text}")
        return text
    except Exception as exc:
        print(f"[JARVIS STT] {exc}")
        return ""
