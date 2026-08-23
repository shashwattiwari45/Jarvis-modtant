# JARVIS Windows Desktop Mode

The desktop shell runs the existing HUD in a native Electron window and starts the local Python runtime automatically.

## Development

From `web_ui`:

```powershell
npm install
npm run desktop:dev
```

The desktop shell starts:

1. `jarvis.local_entrypoint` for local Whisper/STT, TTS, memory, automation, and the local brain runtime.
2. The existing Vite/Express HUD on port 3000.
3. A native JARVIS window around the HUD.

The Render cloud service is intentionally independent. Closing JARVIS or shutting down Windows does not stop the deployed cloud service.

## Production Windows build

```powershell
npm install
npm run build:desktop
```

The installer and portable executable are written to `web_ui/release/`.

The packaged app includes the Python source runtime under Electron resources, but it intentionally does **not** package secrets or a Python installation. Python and the JARVIS Python dependencies must therefore exist on the machine. Use `JARVIS_PYTHON` if `python` is not on PATH.

## Environment

Keep secrets in `web_ui/.env` during development. Never commit it.

Required values:

```text
JARVIS_CLOUD_URL=https://your-jarvis-cloud.onrender.com
JARVIS_CLOUD_SECRET=your-cloud-secret
JARVIS_DEVICE_ID=local-pc
JARVIS_OWNER_PASSWORD=your-owner-password
JARVIS_AUTH_SECRET=your-long-auth-secret
PORT=3000
```

Optional microphone override:

```text
JARVIS_INPUT_DEVICE=your-input-device-name-or-index
```

## Speech hardening

The local listener now:

- announces when it is listening;
- waits only about 2.5 seconds for a new utterance before returning to wake mode;
- uses adaptive microphone noise gating;
- keeps a short pre-roll so the first syllable is less likely to be clipped;
- stops recording after a short silence;
- uses INT8 faster-whisper with a lower beam size for better CPU responsiveness;
- prints microphone failures clearly instead of appearing frozen.

The existing TTS path remains Edge-TTS + pygame, including the configured male English/Hindi voices.
