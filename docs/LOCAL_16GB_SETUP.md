# JARVIS local 16 GB laptop runtime

The local runtime is designed for a Windows laptop with roughly 16 GB RAM and an 8th-gen i5-class CPU.

## Install

From the repository root, with the existing `.venv` activated:

```powershell
pip install -r requirements-local.txt
```

## Run

```powershell
python jarvisvav1.py
```

The launcher keeps the existing cloud reasoning/tool architecture but uses `sounddevice` + `faster-whisper` for local microphone transcription. It automatically selects a conservative CPU thread count and uses Whisper `small` with int8 CPU inference on 10-24 GB machines.

## Why this is local-first

- Microphone audio is transcribed locally rather than sent to a speech-recognition web service.
- Cloud/OpenAI remains responsible for reasoning, web search, tool selection, and current-information answers.
- The existing web HUD, persistent memory, phone bridge, and Instagram modules are unchanged.
- No heavyweight local language model is loaded just because the laptop has 16 GB RAM; the available RAM is used where it improves responsiveness most.

## Troubleshooting

If the microphone cannot be opened, run:

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Then select/enable the intended Windows microphone in the system sound settings.
