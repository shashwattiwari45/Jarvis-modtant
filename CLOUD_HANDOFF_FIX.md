# Cloud handoff fix

The cloud `/ask` endpoint now returns an explicit `mode` field: `chat` or `pc_action`.

`cloud_jarvis.py` uses that field as the routing contract:

- `chat` -> answer directly from Jarvis Cloud.
- `pc_action` -> execute through the existing local Windows Jarvis tool brain.
- Cloud unavailable -> local fallback.

This keeps cloud conversation available when the PC is offline while preserving local-only capabilities when the PC is online.
