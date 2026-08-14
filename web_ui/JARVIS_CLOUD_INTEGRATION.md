# JARVIS HUD cloud integration

The web UI uses `web_ui/server.ts` as a server-side bridge to Jarvis Cloud.

Required environment variables:

- `JARVIS_CLOUD_URL` — deployed Jarvis Cloud base URL
- `JARVIS_CLOUD_SECRET` — same secret configured on the Cloud service
- `JARVIS_DEVICE_ID` — unique UI device id, e.g. `web-ui`
- `PORT` — optional, defaults to `3000`

The browser never receives the Cloud secret. `/api/chat` and `/api/health` proxy through the server.
