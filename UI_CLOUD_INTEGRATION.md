# JARVIS HUD ↔ Cloud Integration

The `web_ui/` application is the presentation layer. Its server-side routes proxy requests to Jarvis Cloud so secrets remain outside the browser.

## Flow

Browser HUD → `web_ui/server.ts` → Jarvis Cloud `/ask` → Cloud brain → response

For PC-capable requests, Jarvis Cloud returns `mode: "pc_action"`. The existing Windows `cloud_jarvis.py` agent remains responsible for executing local PC actions; this UI integration does not invent a browser-side PC executor.

Instagram uses the same private cloud brain through `/api/instagram/brief`. The briefing is for the owner only and does not expose the public account identity or move Meta credentials into the React app.

## Environment

Copy `web_ui/.env.example` to `.env` and set:

- `JARVIS_CLOUD_URL`
- `JARVIS_CLOUD_SECRET`
- `JARVIS_DEVICE_ID`
- `PORT`

Never put `JARVIS_CLOUD_SECRET`, OpenAI credentials, Meta credentials, or Cloudinary credentials in frontend source.

## Routes

- `GET /api/health` — checks Cloud availability.
- `POST /api/chat` — sends HUD chat to Cloud and preserves the Cloud session ID.
- `POST /api/device/heartbeat` — registers the web UI as an online device.
- `POST /api/instagram/brief` — returns a private Instagram briefing through Cloud.
