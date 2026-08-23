"""Local-first JARVIS launcher.

This entry point keeps the existing cloud brain/tool system but prefers local
Whisper + sounddevice for microphone input on capable Windows laptops.
"""
from __future__ import annotations

import os

from .hardware_profile import PROFILE, apply_process_tuning

# Tune the CPU backend before importing jarvis.core/faster-whisper.
os.environ.setdefault("OMP_NUM_THREADS", str(PROFILE.whisper_threads))
os.environ.setdefault("CT2_INTER_THREADS", "1")
os.environ.setdefault("CT2_INTRA_THREADS", str(PROFILE.whisper_threads))

apply_process_tuning()

from . import core  # noqa: E402
from .local_stt import listen as local_listen  # noqa: E402


def main() -> None:
    # Reuse core's already-loaded Whisper model when available so the local
    # runtime does not keep two large speech models in memory.
    core.listen = lambda: local_listen(getattr(core, "_whisper_model", None))
    print(
        f"[JARVIS Local] {PROFILE.whisper_model} Whisper / "
        f"{PROFILE.whisper_threads} CPU threads"
    )
    core.main()


if __name__ == "__main__":
    main()
