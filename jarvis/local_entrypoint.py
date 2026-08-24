"""Stable local launcher for JARVIS.

Use the mature core microphone/STT pipeline. The newer local VAD wrapper was
causing speech-detection regressions by replacing core.listen at startup.
Local deterministic actions remain available through the action router.
"""
from __future__ import annotations

import inspect
import os

from .hardware_profile import PROFILE, apply_process_tuning

# Keep CPU settings conservative without replacing core's voice pipeline.
os.environ.setdefault("OMP_NUM_THREADS", str(PROFILE.whisper_threads))
os.environ.setdefault("CT2_INTER_THREADS", "1")
os.environ.setdefault("CT2_INTRA_THREADS", str(PROFILE.whisper_threads))
apply_process_tuning()

from . import core  # noqa: E402
from .intelligence import install as install_intelligence  # noqa: E402
from .local_actions import try_execute  # noqa: E402


def _install_action_router() -> None:
    original = getattr(core, "think_and_act", None)
    if not callable(original) or getattr(original, "_jarvis_local_router", False):
        return

    if inspect.iscoroutinefunction(original):
        async def routed_async(text, *args, **kwargs):
            result = try_execute(text)
            if result is not None:
                return result
            return await original(text, *args, **kwargs)
        routed_async._jarvis_local_router = True
        core.think_and_act = routed_async
    else:
        def routed(text, *args, **kwargs):
            result = try_execute(text)
            if result is not None:
                return result
            return original(text, *args, **kwargs)
        routed._jarvis_local_router = True
        core.think_and_act = routed


def main() -> None:
    # IMPORTANT: do not monkey-patch core.listen. Core already has Whisper STT,
    # Google fallback, adaptive SpeechRecognition settings, Hindi detection,
    # interruption-aware TTS, and the complete voice/tool loop.
    install_intelligence(core)
    _install_action_router()
    print(
        f"[JARVIS Local] Stable core voice / Whisper + Google fallback / "
        f"{PROFILE.whisper_threads} CPU threads"
    )
    print("[JARVIS Local] Voice + local Windows action routing enabled.")
    print("[JARVIS Intelligence] Tool calling + selective memory + live web research enabled.")
    core.main()


if __name__ == "__main__":
    main()
