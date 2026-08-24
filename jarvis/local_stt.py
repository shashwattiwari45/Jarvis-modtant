"""Reliable local microphone STT for JARVIS.

Designed for the user's i5-class Windows laptop with 16 GB RAM. Capture is
continuous at the call level, uses adaptive voice activity detection, keeps a
small pre-roll so the first syllable is not clipped, and leaves transcription
to faster-whisper. The caller can repeatedly invoke ``listen`` for an
always-ready wake-word loop without relying on PyAudio/SpeechRecognition.
"""
from __future__ import annotations

import os
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / "web_ui" / ".env")
except ImportError:
    pass

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
_LAST_AUDIO_DETECTED = False


def audio_was_detected() -> bool:
    """Return whether the most recent capture contained audio above the floor."""
    return _LAST_AUDIO_DETECTED


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


def _input_devices() -> list[dict]:
    if sd is None:
        return []
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) > 0:
            devices.append({"index": index, "name": str(info.get("name", ""))})
    return devices


def _resolve_input_device():
    """Resolve JARVIS_INPUT_DEVICE as an index or case-insensitive name."""
    configured = os.getenv("JARVIS_INPUT_DEVICE", "").strip()
    if not configured:
        try:
            default = sd.default.device[0]
            if default is not None and int(default) >= 0:
                return int(default)
        except Exception:
            pass
        return None

    try:
        return int(configured)
    except ValueError:
        wanted = configured.casefold()
        for item in _input_devices():
            if wanted in item["name"].casefold():
                return item["index"]
    raise RuntimeError(
        f"Microphone '{configured}' was not found. Available inputs: "
        + ", ".join(f"{d['index']}: {d['name']}" for d in _input_devices())
    )


def _voice_threshold(noise_rms: float) -> float:
    """Choose a speech threshold that works across quiet and noisy laptops."""
    configured = os.getenv("JARVIS_VOICE_THRESHOLD", "").strip()
    if configured:
        try:
            return max(50.0, min(500.0, float(configured)))
        except ValueError:
            pass
    # Keep the threshold close to the measured noise floor so quiet speech is
    # detected on laptop microphones without making fan noise count as speech.
    return max(50.0, min(500.0, noise_rms * 1.15 + 5.0))


def record_until_silence(
    sample_rate: int = 16000,
    max_seconds: float = 15.0,
    start_timeout: float = 10.0,
    silence_seconds: float = 0.80,
):
    """Capture one utterance with adaptive VAD and first-word protection."""
    global _LAST_AUDIO_DETECTED
    _LAST_AUDIO_DETECTED = False
    if sd is None:
        raise RuntimeError("sounddevice is not installed. Run: pip install sounddevice")

    block_seconds = 0.10
    block_size = int(sample_rate * block_seconds)
    calibration_blocks = 10  # 1 second of real microphone noise calibration
    pre_roll_blocks = 4       # 400 ms; protects the beginning of "Jarvis"
    blocks: list[np.ndarray] = []
    pre_roll: list[np.ndarray] = []
    noise_samples: list[np.ndarray] = []
    device = _resolve_input_device()

    device_name = "default"
    try:
        if device is not None:
            device_name = str(sd.query_devices(device)["name"])
    except Exception:
        pass

    print(f"[JARVIS STT] Listening... mic={device_name}")

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
            device=device,
            latency="low",
        ) as stream:
            for _ in range(calibration_blocks):
                data, overflowed = stream.read(block_size)
                if overflowed:
                    print("[JARVIS STT] Mic buffer overflow during calibration; continuing.")
                noise_samples.append(data[:, 0].copy())

            noise = _rms(np.concatenate(noise_samples))
            threshold = _voice_threshold(noise)
            print(f"[JARVIS STT] Ready (noise={noise:.0f}, threshold={threshold:.0f})")

            started = False
            consecutive_voice = 0
            last_voice_at = time.monotonic()
            deadline = time.monotonic() + max_seconds
            start_deadline = time.monotonic() + start_timeout

            while time.monotonic() < deadline:
                data, overflowed = stream.read(block_size)
                if overflowed:
                    print("[JARVIS STT] Mic buffer overflow; recovering automatically.")
                mono = data[:, 0].copy()
                level = _rms(mono)
                now = time.monotonic()

                if not started:
                    pre_roll.append(mono)
                    if len(pre_roll) > pre_roll_blocks:
                        pre_roll.pop(0)

                    if level >= threshold:
                        consecutive_voice += 1
                    else:
                        consecutive_voice = 0

                    if consecutive_voice >= 2:
                        started = True
                        _LAST_AUDIO_DETECTED = True
                        blocks.extend(pre_roll)
                        print("[JARVIS STT] Voice detected - transcribing...")
                        last_voice_at = now

                else:
                    # Slowly adapt only upward to sustained background noise;
                    # never raise the threshold while the user is speaking.
                    if level >= threshold:
                        last_voice_at = now
                    blocks.append(mono)
                    if now - last_voice_at >= silence_seconds:
                        break

                if not started and now >= start_deadline:
                    print("[JARVIS STT] No speech detected; staying ready for the next utterance.")
                    break
    except Exception as exc:
        if os.getenv("JARVIS_INPUT_DEVICE", "").strip():
            raise RuntimeError(f"Configured microphone failed: {exc}") from exc
        raise RuntimeError(f"Microphone capture failed: {exc}") from exc

    if not blocks:
        return np.empty(0, dtype=np.int16), sample_rate
    return np.concatenate(blocks), sample_rate


def transcribe(samples: np.ndarray, sample_rate: int, model=None) -> str:
    if samples.size == 0:
        return ""
    active_model = _get_model(model)
    if active_model is None:
        raise RuntimeError("faster-whisper is not installed. Run: pip install faster-whisper")

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
            language=None,
            beam_size=5,
            best_of=5,
            vad_filter=False,
            condition_on_previous_text=False,
            temperature=0.0,
            initial_prompt="Jarvis, wake up. Hinglish conversation in Hindi and English.",
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def listen(existing_model=None) -> str:
    """Capture one utterance; callers can invoke repeatedly for always-on mode."""
    try:
        samples, rate = record_until_silence()
        text = transcribe(samples, rate, existing_model)
        if text:
            print(f"[JARVIS STT] You: {text}")
        return text.lower().strip()
    except Exception as exc:
        print(f"[JARVIS STT] {exc}")
        return ""
