# Jarvis Cloud

This is the always-online cloud layer for Jarvis. It keeps the shared AI brain, lightweight memory, sessions and device presence available when the Windows laptop is OFF.

## What it does

- FastAPI gateway for phone/PC clients
- GPT-5-mini cloud conversation
- Shared lightweight memory
- Device heartbeat/presence
- Authenticated requests using `JARVIS_CLOUD_SECRET`
- Ready to host Instagram/WhatsApp agents alongside the cloud brain

## What it does NOT do

Windows-only actions such as mouse control, local files, OCR and application launching stay on the Windows agent. The cloud routes/coordinates those capabilities when the PC is online.

## Deploy on Render

This repository includes `render.yaml`. Render can deploy a FastAPI service directly from GitHub and redeploy it when the linked branch changes. The included config uses a persistent disk for the SQLite memory database because Render service filesystems are ephemeral by default. citeturn240156search0turn240156search1turn240156search11

1. Create a Render Web Service from this repository.
2. Select the `cloud-jarvis-connector` branch while testing; switch to `main` after merge.
3. The root directory is `cloud`.
4. Build: `pip install -r requirements.txt`
5. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Set `OPENAI_API_KEY` and a long random `JARVIS_CLOUD_SECRET` in Render's environment settings.
7. After deployment, test `/health`.
8. Put the deployed HTTPS URL into the PC/Android clients as `JARVIS_CLOUD_URL`.

Render supports FastAPI deployment and HTTPS, and its persistent disks preserve filesystem changes across restarts/deploys when attached. citeturn240156search3turn240156search11

## Local client variables

```text
JARVIS_CLOUD_URL=https://your-service.onrender.com
JARVIS_CLOUD_SECRET=the_same_secret_as_render
JARVIS_DEVICE_ID=shashwat-pc
```

Then import `cloud/jarvis_cloud_client.py` from the Windows Jarvis process. The first integration should call `heartbeat()` on startup and use `ask_cloud()` for cloud-first conversation when the service is reachable.

## Important

Do not commit API keys or `JARVIS_CLOUD_SECRET`. The `.env.example` file is only a template.
