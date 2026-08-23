"""Local hardware profile and safe tuning for JARVIS.

Designed for a Windows laptop around 16 GB RAM / 8th-gen i5-class CPU.
The goal is responsiveness, not maximum benchmark throughput.
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None


@dataclass(frozen=True)
class HardwareProfile:
    ram_gb: float
    logical_cpus: int
    physical_cpus: int
    whisper_model: str
    whisper_threads: int
    max_workers: int


def detect_hardware() -> HardwareProfile:
    ram_gb = (psutil.virtual_memory().total / (1024 ** 3)) if psutil else 16.0
    logical = os.cpu_count() or 4
    physical = (psutil.cpu_count(logical=False) or max(1, logical // 2)) if psutil else max(1, logical // 2)

    # 16 GB / mobile 4C-8T class: small multilingual Whisper in int8 is a
    # sensible quality/speed point. Drop to base only when RAM is constrained.
    if ram_gb < 10:
        model = "base"
        threads = max(2, min(physical, 4))
    elif ram_gb < 24:
        model = "small"
        threads = max(2, min(logical - 1, 6))
    else:
        model = "small"
        threads = max(2, min(logical, 8))

    return HardwareProfile(
        ram_gb=round(ram_gb, 1),
        logical_cpus=logical,
        physical_cpus=physical,
        whisper_model=model,
        whisper_threads=threads,
        max_workers=max(2, min(4, physical)),
    )


PROFILE = detect_hardware()


def apply_process_tuning() -> None:
    """Apply conservative Windows process settings; never fail startup."""
    if not psutil:
        return
    try:
        process = psutil.Process()
        if platform.system() == "Windows":
            # Above-normal is deliberately avoided: JARVIS should not starve
            # Chrome, audio drivers, VS Code, or the desktop.
            process.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def whisper_kwargs() -> dict:
    return {
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": PROFILE.whisper_threads,
        "num_workers": 1,
    }


def summary() -> str:
    return (
        f"{PROFILE.ram_gb} GB RAM | "
        f"{PROFILE.physical_cpus} physical / {PROFILE.logical_cpus} logical CPUs | "
        f"Whisper {PROFILE.whisper_model} int8 / {PROFILE.whisper_threads} threads"
    )
