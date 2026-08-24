"""Local JARVIS launcher with a persistent hands-free voice session."""
from __future__ import annotations

import inspect
import os
import socket
import threading

from .hardware_profile import PROFILE, apply_process_tuning

# Conservative CPU tuning only; never replace the voice pipeline.
os.environ.setdefault("OMP_NUM_THREADS", str(PROFILE.whisper_threads))
os.environ.setdefault("CT2_INTER_THREADS", "1")
os.environ.setdefault("CT2_INTRA_THREADS", str(PROFILE.whisper_threads))
apply_process_tuning()

from . import core  # noqa: E402
from .intelligence import install as install_intelligence  # noqa: E402
from .local_actions import try_execute  # noqa: E402
from .voice_session import run as run_voice_session  # noqa: E402


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
    install_intelligence(core)
    _install_action_router()

    # Preserve JARVIS background awareness and proactive behaviour without
    # using core.main(), whose old loop reopened/calibrated the microphone on
    # every turn.
    try:
        core.ensure_autostart()
        core.update_device_presence(
            socket.gethostname(),
            "pc",
            "online",
            ["computer_control", "voice", "memory", "screen", "files"],
        )
        threading.Thread(target=core.awareness_watcher, daemon=True).start()
        threading.Thread(target=core.proactive_watcher, daemon=True).start()
        core.set_status("listening", "continuous voice ready")
    except Exception as exc:
        print(f"[JARVIS Background] {exc}")

    print(
        f"[JARVIS Local] Continuous voice / Whisper + Google fallback / "
        f"{PROFILE.whisper_threads} CPU threads"
    )
    print("[JARVIS Local] Microphone stays open for the entire voice session.")
    print("[JARVIS Intelligence] Tool calling + selective memory + live web research enabled.")
    run_voice_session(core)


if __name__ == "__main__":
    main()
