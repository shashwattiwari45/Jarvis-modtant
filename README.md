# Jarvis Modtant

A Windows-7-friendly, low-overhead personal assistant upgraded from the existing Nova/Jarvis script without replacing its working features.

## What is implemented

- Local wake-word gate for **“Jarvis”** so idle audio does not call OpenAI.
- Continuous conversation window after wake-up; follow-ups use short chat history plus a compact local context snapshot.
- **Always-available background Jarvis:** `--background` mode, quiet startup, lightweight polling, and Windows Current User Run-key autostart via `~/jarvis_config.json`.
- **Personal AI / companion memory:** persistent profile, preferences, routines, projects, open tasks, conversation history and personal context in `~/jarvis_memory.json` with secret/OTP/token/password filtering.
- **Proactive self-talk controls:** low/balanced/high proactive personality, quiet mode, daily de-duplication, and useful-only checks such as low battery and morning availability.
- **Continuous awareness:** low-frequency active-window, idle/active, current-task and recent-action snapshots in `~/jarvis_state.json`, avoiding heavy OCR/vision unless requested.
- OCR-first screen intelligence with approximate UI coordinates, screen reading, click-by-label, and vision fallback when OpenAI is configured.
- Mouse/keyboard computer control with action history and conservative verification notes for UI clicks.
- Tool-calling brain using `gpt-5-mini`, able to execute multiple tools in sequence and summarize results.
- Universal dictation via clipboard paste, preserving Hindi/Hinglish text.
- **Phone-first Android companion architecture:** ADB bridge for apps, volume, screenshots, media/YouTube content, URLs, battery/info and safe dialer handoff.
- **Jarvis device network foundation:** shared identity file, authenticated HMAC token helper, device presence/status, persistent reconnect-friendly state, and command-routing stubs for PHONE ↔ PC ↔ future devices.
- Safe WhatsApp reply drafting boundary: drafts only, explicit review required before sending.
- PDF text extraction, larger document context, and scanned-PDF OCR boundary/fallback messaging.
- Live translation boundary: OCR screen text, translate with OpenAI, show a lightweight HUD overlay.
- System diagnostics for CPU, RAM, battery, storage and network when `psutil` is installed.
- Improved Start Menu app discovery and fuzzy app matching.
- Lightweight Jarvis-style HUD status: sleeping, listening, thinking, speaking/working results, device/memory context and quiet background status.
- Natural voice improvements: wake-word activation, short spoken replies, follow-up conversation without repeating “Jarvis”, and ESC barge-in while Jarvis is speaking when the `keyboard` package is available.

## Setup

```bash
pip install python-dotenv openai edge-tts pygame keyboard SpeechRecognition pyaudio pillow pytesseract pypdf requests pyautogui psutil pywin32 screen-brightness-control
```

Optional but recommended:

1. Install Tesseract OCR from <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Include Hindi language data for mixed English/Hindi OCR.
3. Set `OPENAI_API_KEY` in your environment or `.env` for GPT/vision/translation.
4. Set `PHONE_ADB_IP` after pairing Android ADB over Wi-Fi.
5. Set `JARVIS_DEVICE_SECRET` to the same strong secret on every Jarvis device that should share the trusted network identity.
6. Set `YOUTUBE_API_KEY` if you want higher-quality YouTube phone playback selection.

## Run

```bash
python jarvisvav1.py
```

Jarvis starts in low-noise background mode by default and listens for the wake word. Say **“Jarvis”** or **“Jarvis, <command>”**. After activation, you can continue naturally for a short window without repeating the wake word.

To explicitly start the quiet background service used by Windows autostart:

```bash
python jarvisvav1.py --background
```

## Personal commands

- “Jarvis, remember this …” stores safe long-term context through the personal memory tools.
- “Jarvis, remind me later …” or “remember this task …” saves an open task.
- “Jarvis, continue what we were doing” and “Jarvis, where did we leave off?” recall unfinished work.
- “Jarvis, I’m leaving” enables quiet mode and preserves the current context.
- “Jarvis, I’m going to sleep” enables quiet mode and keeps only essential proactive checks.
- “Jarvis, quiet mode off” or proactive-frequency requests are handled by the tool-calling brain.

## Configuration files

Jarvis keeps lightweight local state in your home directory:

- `~/jarvis_config.json` — background mode, Windows autostart, quiet mode, proactive frequency, device-network settings.
- `~/jarvis_memory.json` — profile, preferences, routines, projects, facts, open tasks and conversation history.
- `~/jarvis_state.json` — current lightweight awareness snapshot.
- `~/jarvis_devices.json` — device presence and shared Jarvis identity metadata.

## Windows 7 / low-end hardware notes

- Idle work is limited to short sleeps and low-frequency status checks.
- Heavy OCR, screen vision, PDF work and phone UI dumps load only when a command requires them.
- Autostart uses the per-user Windows Run key, not a heavy service installer.
- The HUD is a simple Tkinter label and silently degrades in headless or restricted desktop sessions.

## Security notes

- Secrets are read from environment/config, not hardcoded.
- Jarvis refuses to remember obvious passwords, OTPs, tokens, API keys and card details.
- Sensitive messaging/calling-style capabilities are designed to ask for confirmation and/or draft only.
- Device-network helpers use a shared HMAC secret; expose future network listeners only on trusted LANs and keep computer-control commands authenticated.
