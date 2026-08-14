# Jarvis Modtant

A Windows-7-friendly, low-overhead personal assistant with a modular package layout.

The public entry point remains:

```bash
python jarvisvav1.py
```

The original implementation now lives in `jarvis/core.py`. Lightweight facades (`jarvis/voice.py`, `jarvis/desktop.py`, `jarvis/memory.py`, `jarvis/phone.py`, `jarvis/vision.py`, `jarvis/social.py`) provide stable import surfaces so deeper extraction can happen incrementally without changing behavior.

Cloud-first mode remains:

```bash
python cloud_jarvis.py
```

Do not commit API keys or other secrets.
