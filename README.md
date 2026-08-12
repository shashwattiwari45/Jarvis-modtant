# Jarvis Modtant

A Windows-7-friendly, low-overhead personal assistant upgraded from the existing Nova/Jarvis script without replacing its working features.

## What is implemented

- Local wake-word gate for **“Jarvis”** so idle audio does not call OpenAI.
- Continuous conversation window after wake-up; follow-ups use short chat history plus a compact local context snapshot.
- OCR-first screen intelligence with approximate UI coordinates, screen reading, click-by-label, and vision fallback when OpenAI is configured.
- Mouse/keyboard computer control with action history and conservative verification notes for UI clicks.
- Proactive battery/morning checks that avoid speaking while audio is active.
- Tool-calling brain using `gpt-5-mini`, able to execute multiple tools in sequence and summarize results.
- Persistent long-term memory in `~/jarvis_memory.json`, with secret/OTP/token/password filtering.
- Context awareness for active window, clipboard, recent actions, and visual notes.
- Universal dictation via clipboard paste, preserving Hindi/Hinglish text.
- Android/ADB bridge for apps, volume, screenshots, media/YouTube content, URLs, battery/info and safe dialer handoff.
- Safe WhatsApp reply drafting boundary: drafts only, explicit review required before sending.
- PDF text extraction, larger document context, and scanned-PDF OCR boundary/fallback messaging.
- Live translation boundary: OCR screen text, translate with OpenAI, show a lightweight HUD overlay.
- System diagnostics for CPU, RAM, battery, storage and network when `psutil` is installed.
- Improved Start Menu app discovery and fuzzy app matching.
- Lightweight Jarvis-style HUD status: listening, thinking, success, failure and sleeping.

## Setup

```bash
pip install python-dotenv openai edge-tts pygame keyboard SpeechRecognition pyaudio pillow pytesseract pypdf requests pyautogui psutil pywin32 screen-brightness-control
```

Optional but recommended:

1. Install Tesseract OCR from <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Include Hindi language data for mixed English/Hindi OCR.
3. Set `OPENAI_API_KEY` in your environment or `.env` for GPT/vision/translation.
4. Set `PHONE_ADB_IP` after pairing Android ADB over Wi-Fi.
5. Set `YOUTUBE_API_KEY` if you want higher-quality YouTube phone playback selection.

## Run

```bash
python jarvisvav1.py
```

Jarvis starts asleep to avoid accidental API usage. Say **“Jarvis”** or **“Jarvis, <command>”**. After activation, you can continue naturally for a short window without repeating the wake word.

## Security notes

- Secrets are read from environment/config, not hardcoded.
- Jarvis refuses to remember obvious passwords, OTPs, tokens, API keys and card details.
- Sensitive messaging/calling-style capabilities are designed to ask for confirmation and/or draft only.
- The future phone-call/WebSocket/telephony interface should authenticate before connecting to the same `think_and_act` brain and must not expose unauthenticated computer control.
