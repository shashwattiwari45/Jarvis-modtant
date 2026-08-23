"""Local-first JARVIS launcher.

Keeps the existing cloud brain/tool system while preferring local Whisper +
sounddevice for microphone input on capable Windows laptops. Common Windows
app launches are handled locally first; everything else remains on the normal
JARVIS tool-calling path.
"""
from __future__ import annotations

import inspect
import os

from .hardware_profile import PROFILE, apply_process_tuning

# Tune the CPU backend before importing jarvis.core/faster-whisper.
os.environ.setdefault("OMP_NUM_THREADS", str(PROFILE.whisper_threads))
os.environ.setdefault("CT2_INTER_THREADS", "1")
os.environ.setdefault("CT2_INTRA_THREADS", str(PROFILE.whisper_threads))

apply_process_tuning()

from . import core  # noqa: E402
from .local_actions import try_execute  # noqa: E402
from .local_stt import listen as local_listen  # noqa: E402


def _install_action_router() -> None:
    """Give voice commands the same action path as HUD commands.

    A few latency-sensitive Windows commands are deterministic and do not need
    an LLM round trip. Unmatched requests are delegated untouched to core's
    existing think_and_act implementation.
    """
    original = getattr(core, "think_and_act", None)
    if not callable(original):
        print("[JARVIS Local] Existing think_and_act() was not found; keeping core unchanged.")
        return

    if getattr(original, "_jarvis_local_router", False):
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
    # Reuse core's already-loaded Whisper model when available so the local
    # runtime does not keep two large speech models in memory.
    core.listen = lambda: local_listen(getattr(core, "_whisper_model", None))
    _install_action_router()
    print(
        f"[JARVIS Local] {PROFILE.whisper_model} Whisper / "
        f"{PROFILE.whisper_threads} CPU threads"
    )
    print("[JARVIS Local] Voice + local Windows action routing enabled.")
    core.main()


if __name__ == "__main__":
    main()
