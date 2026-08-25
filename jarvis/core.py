"""
JARVIS - AI Voice Assistant (Tool-Calling Architecture)
------------------------------------------------------
Jarvis no longer works by matching your sentence against a big list of fixed
trigger phrases. Instead, every non-trivial thing you say goes to GPT-5-mini,
which decides - using OpenAI's function/tool calling - which action(s) to run
(if any), with what parameters, based on natural phrasing. It also keeps a
short rolling memory of the conversation, so it's a real back-and-forth, not
a stateless command parser.

Only two things are still handled instantly, without an API call at all:
  - "stop" / "exit" / "quit"          -> quits immediately, no network round trip
  - sleep / "wake up jarvis" handling   -> pure local state, zero cost

Everything else - opening/closing apps, Zoom/Chrome control, volume, reading
the screen or a PDF, general chat, whatever - goes through Nova's "brain":
think_and_act(). The model decides what to do; Python just executes it.

SETUP:
    pip install edge-tts pygame keyboard SpeechRecognition pyaudio pillow pytesseract pypdf requests openai pyautogui psutil pywin32

    OCR requires the actual Tesseract engine, not just the pytesseract wrapper
    (your logs show "tesseract is not installed" - this is why screen-reading
    keeps falling back to the slower/costlier vision API):
    1. Download & install Tesseract-OCR for Windows:
       https://github.com/UB-Mannheim/tesseract/wiki
    2. During install, make sure to tick the "Hindi" language pack (needed for
       eng+hin OCR) - it's under "Additional language data" in the installer.
    3. Confirm TESSERACT_CMD below matches your install path (usually
       C:\\Program Files\\Tesseract-OCR\\tesseract.exe - default already set).

    PAINT DRAWING is pixel-based mouse automation (pyautogui) - it's inherently
    approximate and depends on your screen resolution/Paint version. If shapes
draw in the wrong place or colors don't select correctly, adjust the
PAINT_COLOR_POSITIONS values near draw_circle_paint() - this is expected to
need a bit of calibration on your specific machine.
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import os
import sys
import io
import re
import json
import glob
import threading
import time
import math
import difflib
import ctypes
import base64
import tempfile
import webbrowser
import subprocess
import datetime
import asyncio
import urllib.parse
import uuid
import hashlib
import hmac
import socket
from pathlib import Path

try:
    import speech_recognition as sr
except ImportError:
    sr = None
try:
    import requests
except ImportError:
    requests = None
try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None

try:
    import edge_tts
    import pygame
except ImportError:
    edge_tts = None
    pygame = None

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

try:
    from faster_whisper import WhisperModel
    # "small" is a good balance of speed/accuracy on CPU; use "base" if this
    # feels sluggish on your machine, or "medium" if you have a GPU (device="cuda")
    _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
except ImportError:
    _whisper_model = None

import tkinter as tk

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
except ImportError as exc:
    raise RuntimeError("python-dotenv is required to load the JARVIS .env file") from exc
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
if OpenAI and not OPENAI_API_KEY:
    raise RuntimeError(
        f"OPENAI_API_KEY was not loaded. Expected it in: {ENV_FILE}"
    )
client = OpenAI(api_key=OPENAI_API_KEY) if OpenAI else None
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-5-mini"   # real model id - "gpt-5o-mini" does NOT exist

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

STT_LANGUAGES = ["en-IN", "hi-IN"]

VOICE_NOVA = "en-GB-RyanNeural"
VOICE_FEMALE = "en-US-AvaNeural"
VOICE_HINDI_MALE = "hi-IN-MadhurNeural"
VOICE_HINDI_FEMALE = "hi-IN-SwaraNeural"
CURRENT_VOICE_MODE = "nova"
DICTATION_MODE = False
DICTATION_START_PHRASES = ["start dictation", "start typing", "dictation mode on"]
DICTATION_STOP_PHRASES = ["stop dictation", "stop typing", "dictation mode off"]

LAST_ACTION = None
CURRENT_LANG = "en-IN"

AUDIO_LOCK = threading.Lock()  # prevents proactive speech from colliding with a live listen()/speak() cycle
_proactive_said_today = {}     # e.g. {"low_battery": "2026-08-04"} - stops it repeating itself all day


SMART_WEB_APPS = {
    "whatsapp": "https://web.whatsapp.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "instagram": "https://www.instagram.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "canva": "https://www.canva.com",
    "spotify web": "https://open.spotify.com",
}

_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
if pytesseract:
    for _cand in _TESSERACT_CANDIDATES:
        if os.path.exists(_cand):
            pytesseract.pytesseract.tesseract_cmd = _cand
            break

PDF_SEARCH_DIRS = [
    os.path.join(os.path.expanduser("~"), "Downloads"),
    os.path.join(os.path.expanduser("~"), "Documents"),
]

APP_SEARCH_DIRS = [
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
]
APP_INDEX_REFRESH_SECONDS = 300

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CONTACTS = {}       # "mom": "+91xxxxxxxxxx"
ZOOM_LINKS = {}      # "office": "https://zoom.us/j/xxxx"

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

def _is_hindi_text(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))

# ---------------------------------------------------------------------------
# PHONE BRIDGE - LAPTOP CONTROLS PHONE (via ADB over WiFi)
# ---------------------------------------------------------------------------
PHONE_IP = os.getenv("PHONE_ADB_IP")  # set once you know your phone's local IP, e.g. "192.168.1.42:5555"
PHONE_APP_PACKAGES = {
    "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome",
    "gmail": "com.google.android.gm",
    "instagram": "com.instagram.android",
}
CONTENT_CATEGORIES = {
    "news": {"query": "India news", "live": True},
    "hindi news": {"query": "Aaj Tak Hindi news", "live": True},
    "english news": {"query": "India English news", "live": True},
    "cricket": {"query": "cricket live", "live": True},
    "bhajans": {"query": "bhajans hindi devotional songs", "live": False},
    "music": {"query": "trending Hindi songs playlist", "live": False},
    "lofi": {"query": "lofi study music", "live": True},
    "workout": {"query": "gym workout motivation music", "live": False},
    "comedy": {"query": "standup comedy hindi", "live": False},
    "meditation": {"query": "guided meditation relaxing", "live": False},
    "motivation": {"query": "motivational speech hindi", "live": False},
    "cartoons": {"query": "cartoon for kids hindi", "live": False},
    "cooking": {"query": "indian recipe cooking", "live": False},
    "movies trailer": {"query": "latest bollywood trailer", "live": False},
}

_QUERY_FILLER_WORDS = ["on youtube", "please", "for me", "video of", "play", "open", "some", "the"]
def _adb(*args) -> str:
    if not PHONE_IP:
        return "Phone IP isn't configured. Set PHONE_ADB_IP once you've paired via wireless debugging."
    try:
        subprocess.run(["adb", "connect", PHONE_IP], capture_output=True, timeout=5)
        result = subprocess.run(["adb", "-s", PHONE_IP, "shell", *args], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or result.stderr.strip()
    except FileNotFoundError:
        return "ADB isn't installed or not on PATH."
    except Exception as e:
        return f"Phone command failed: {e}"

def open_app_on_phone(package_name: str) -> str:
    package_name = PHONE_APP_PACKAGES.get(package_name.strip().lower(), package_name)
    _adb("monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1")
    return f"Opened {package_name} on your phone."

def phone_volume(direction: str) -> str:
    key = "24" if direction == "down" else "25"  # KEYCODE_VOLUME_DOWN/UP
    _adb("input", "keyevent", key)
    return f"Turned phone volume {direction}."

def take_phone_screenshot() -> str:
    if not PHONE_IP:
        return "Phone IP isn't configured."
    remote = "/sdcard/jarvis_screenshot.png"
    local = os.path.join(os.path.expanduser("~"), "Pictures", "phone_screenshot.png")
    _adb("screencap", "-p", remote)
    subprocess.run(["adb", "-s", PHONE_IP, "pull", remote, local], capture_output=True, timeout=15)
    os.startfile(local)
    return "Grabbed a screenshot from your phone."
    
ANDROID_KEYCODES = {
    "power": "26", "home": "3", "back": "4", "recent_apps": "187",
    "volume_up": "25", "volume_down": "24", "mute": "164",
    "camera": "27", "play_pause": "85", "next_track": "87", "prev_track": "88",
}

def phone_key(action: str) -> str:
    code = ANDROID_KEYCODES.get(action)
    if not code:
        return f"Unknown phone action: {action}"
    _adb("input", "keyevent", code)
    return f"Sent '{action}' to your phone."

def phone_battery() -> str:
    output = _adb("dumpsys", "battery")
    for line in output.splitlines():
        if "level" in line.lower():
            level = line.split(":")[-1].strip()
            return f"Phone battery is at {level}%."
    return "Couldn't read phone battery level."

def phone_info() -> str:
    model = _adb("getprop", "ro.product.model")
    version = _adb("getprop", "ro.build.version.release")
    return f"Phone: {model}, Android {version}."

def type_on_phone(text: str) -> str:
    # adb's input text can't handle raw spaces - encode them as %s
    safe_text = text.replace(" ", "%s")
    _adb("input", "text", safe_text)
    return f"Typed on phone: {text}"

def open_url_on_phone(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    _adb("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    return f"Opened {url} on your phone's browser."

def toggle_wifi(state: str) -> str:
    _adb("svc", "wifi", "enable" if state == "on" else "disable")
    return f"Turned phone WiFi {state}."

def toggle_bluetooth(state: str) -> str:
    _adb("svc", "bluetooth", "enable" if state == "on" else "disable")
    return f"Turned phone Bluetooth {state}."

def dial_number_on_phone(number: str) -> str:
    # ACTION_DIAL opens the dialer pre-filled but does NOT auto-call -
    # ACTION_CALL would auto-dial but needs a runtime permission grant, skipping that on purpose
    _adb("am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{number}")
    return f"Opened the dialer with {number} - tap call to confirm."

def list_installed_apps_on_phone() -> str:
    output = _adb("pm", "list", "packages", "-3")  # -3 = third-party apps only, skips system clutter
    packages = [line.replace("package:", "") for line in output.splitlines()]
    return ", ".join(packages[:20]) if packages else "Couldn't list phone apps."

def find_my_phone() -> str:
    for _ in range(15):
        _adb("input", "keyevent", ANDROID_KEYCODES["volume_up"])
    _adb("input", "keyevent", ANDROID_KEYCODES["play_pause"])
    return "Cranked your phone's volume to max - listen for it."
# ---------------------------------------------------------------------------
# TEXT TO SPEECH (Edge-TTS neural voices + Pygame playback)
# ---------------------------------------------------------------------------
if pygame:
    try:
        pygame.mixer.init()
    except Exception:
        pass

# Splits text into runs of (Devanagari) vs (everything else), so a mixed
# Hinglish sentence like "Chrome खोल रहा हूँ boss" gets each part voiced by
# the RIGHT language's neural voice instead of one voice mangling the other.
_SCRIPT_RUN_RE = re.compile(r"[\u0900-\u097F]+|[^\u0900-\u097F]+")


def _split_by_script(text: str):
    runs = []
    for run in _SCRIPT_RUN_RE.findall(text):
        is_hindi = bool(_DEVANAGARI_RE.search(run))
        if run.strip():
            runs.append((run, is_hindi))
    return runs


async def _play_segment(text: str, is_hindi: bool):
    if is_hindi:
        voice = VOICE_HINDI_FEMALE if CURRENT_VOICE_MODE == "female" else VOICE_HINDI_MALE
    else:
        voice = VOICE_FEMALE if CURRENT_VOICE_MODE == "female" else VOICE_NOVA
    communicate = edge_tts.Communicate(text, voice, volume="+25%", rate="+6%", pitch="+2Hz")
    temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    await communicate.save(temp_path)
    try:
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.set_volume(1.0)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if keyboard and keyboard.is_pressed("esc"):
                pygame.mixer.music.stop()
                break
            pygame.time.wait(20)
        pygame.mixer.music.unload()
    except Exception as err:
        print(f"[Audio Error] {err}")
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


def speak(text: str, force: bool = False):
    print(f"Jarvis: {text}")
    if JARVIS_CONFIG.get("quiet_mode") and not force:
        return
    if not edge_tts or not pygame:
        print("[TTS Error] Please install edge-tts and pygame.")
        return
    

    segments = _split_by_script(text)
    if not segments:
        return

    # Merge tiny/short runs (like a lone comma or single word) into the
    # neighbouring run of the SAME language so we don't get a voice-swap
    # every couple of words - only switch voice on genuinely mixed phrases.
    merged = []
    for seg_text, seg_hindi in segments:
        if merged and merged[-1][1] == seg_hindi:
            merged[-1] = (merged[-1][0] + seg_text, seg_hindi)
        else:
            merged.append([seg_text, seg_hindi])

    async def _play_all():
        for seg_text, seg_hindi in merged:
            if seg_text.strip():
                await _play_segment(seg_text, seg_hindi)

    try:
        with AUDIO_LOCK:
            asyncio.run(_play_all())
    except Exception as e:
        print(f"[TTS Execution Error] {e}")


# ---------------------------------------------------------------------------
# SPEECH TO TEXT (Google Speech Recognition)
# ---------------------------------------------------------------------------
recognizer = sr.Recognizer() if sr else None
if recognizer:
    recognizer.pause_threshold = 0.7
