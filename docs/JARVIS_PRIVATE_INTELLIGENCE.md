# JARVIS private intelligence setup

This branch upgrades JARVIS in four areas: private owner access, persistent memory, intelligent routing, and voice control.

## Render Cloud environment

Set these on the Jarvis Cloud service:

- `OPENAI_API_KEY`
- `JARVIS_CLOUD_SECRET`
- `JARVIS_CLOUD_MODEL=gpt-5.4-mini`
- `JARVIS_REASONING_MODEL=gpt-5.4-mini`
- `JARVIS_FAST_MODEL=gpt-5.4-nano`
- `JARVIS_WEB_SEARCH_CONTEXT=medium`
- `JARVIS_OWNER_ID=owner`
- `DATABASE_URL=<managed Postgres connection string>`

`DATABASE_URL` is strongly recommended in production. The SQLite file is only a local-development fallback because Render Free storage is ephemeral.

## Render Web UI environment

Set these on the Web UI service:

- `JARVIS_CLOUD_URL=https://jarvis-modtant.onrender.com`
- `JARVIS_CLOUD_SECRET=<same cloud secret>`
- `JARVIS_DEVICE_ID=web-ui`
- `JARVIS_OWNER_PASSWORD=<private owner passphrase>`
- `JARVIS_AUTH_SECRET=<long random authentication secret>`

The browser only receives an HttpOnly owner-session cookie. The cloud secret stays server-side.

## Behavior

- Simple greetings use the fast model.
- Complex reasoning, planning, debugging and time-sensitive questions use the reasoning model.
- Current-news/headline/weather/price/result queries can invoke the Responses API web-search tool automatically.
- Explicit stable personal facts can be remembered, while secrets and credentials are rejected from memory writes.
- The owner gate appears before the HUD is loaded.
- `wake up Jarvis`, `hey Jarvis`, and `okay Jarvis` enable continuous wake listening after the microphone has been granted permission.
- `sleep Jarvis` returns to standby.
- Interim speech recognition can interrupt Jarvis speech immediately.
- Long TTS responses are split into manageable chunks so the browser is less likely to truncate them.

## Browser limitation

A browser cannot reliably obtain microphone access before a user gesture. The intended flow is: click the microphone once, say `wake up Jarvis`, then JARVIS keeps listening for the wake phrase and commands while the page remains open. Chrome/Edge are recommended.
