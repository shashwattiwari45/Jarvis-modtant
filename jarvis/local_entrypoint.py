"""Local-first JARVIS launcher using the unified voice engine."""
from __future__ import annotations

import os

from .hardware_profile import PROFILE, apply_process_tuning

os.environ.setdefault("OMP_NUM_THREADS", str(PROFILE.whisper_threads))
os.environ.setdefault("CT2_INTER_THREADS", "1")
os.environ.setdefault("CT2_INTRA_THREADS", str(PROFILE.whisper_threads))
apply_process_tuning()

from . import core  # noqa: E402
from .voice_session import run as run_voice_session  # noqa: E402


def main() -> None:
    print(
        f"[JARVIS Local] {PROFILE.whisper_model} Whisper / "
        f"{PROFILE.whisper_threads} CPU threads"
    )
    run_voice_session(core)


if __name__ == "__main__":
    main()
