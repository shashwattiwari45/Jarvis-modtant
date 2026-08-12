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
    PAINT_COLOR_POSITIONS values near draw_circle_paint() - this is expected
    to need a bit of calibration on your specific machine.
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
except ImportError:
    load_dotenv = lambda: None
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if OpenAI else None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
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
    recognizer.non_speaking_duration = 0.4
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_damping = 0.15
    recognizer.dynamic_energy_ratio = 1.5


def listen() -> str:
    global CURRENT_LANG
    if not sr or not recognizer:
        print("[STT Error] Install SpeechRecognition and PyAudio for voice input.")
        time.sleep(1)
        return ""
    with AUDIO_LOCK, sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        print("Listening... (speak now)")
        try:
            audio = recognizer.listen(source, timeout=6, phrase_time_limit=14)
        except sr.WaitTimeoutError:
            return ""

    if _whisper_model:
        return _listen_with_whisper(audio)
    return _listen_with_google(audio)


def _listen_with_whisper(audio) -> str:
    global CURRENT_LANG
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    try:
        with open(temp_path, "wb") as f:
            f.write(audio.get_wav_data())

        # language=None lets Whisper auto-detect Hindi vs English per clip,
        # instead of guessing ahead of time like the old two-pass Google loop did
        segments, info = _whisper_model.transcribe(temp_path, language=None, vad_filter=True)
        text = " ".join(seg.text for seg in segments).strip().lower()

        if not text:
            return ""

        CURRENT_LANG = "hi-IN" if info.language == "hi" else "en-IN"
        print(f"You said ({CURRENT_LANG}, whisper): {text}")
        return text
    except Exception as e:
        print(f"[Whisper STT error] {e}")
        return _listen_with_google(audio)
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


def _listen_with_google(audio) -> str:
    global CURRENT_LANG
    for lang in STT_LANGUAGES:
        try:
            result = recognizer.recognize_google(audio, language=lang, show_all=True)
            if not result or not result.get("alternative"):
                continue
            text = result["alternative"][0]["transcript"].lower()
            print(f"You said ({lang}, google): {text}")
            CURRENT_LANG = lang
            return text
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            speak("Speech recognition service is unavailable right now.")
            print(f"[STT error] {e}")
            return ""
    return ""


# ---------------------------------------------------------------------------
# UNDO SYSTEM (kept instant/local - immediacy matters when correcting a mistake)
# ---------------------------------------------------------------------------

def record_action(action_type: str, data=None):
    global LAST_ACTION
    LAST_ACTION = (action_type, data)


def undo_last_action() -> str:
    global LAST_ACTION
    if not LAST_ACTION:
        return "There's nothing to undo."
    action_type, data = LAST_ACTION
    if action_type == "close_app" and data:
        close_app_by_name(data)
    elif action_type == "hotkey" and keyboard and data:
        keyboard.send(data)
    elif action_type == "delete_file" and data and os.path.exists(data):
        try:
            os.remove(data)
        except Exception:
            pass
    LAST_ACTION = None
    return "Undid the last action."

# ---------------------------------------------------------------------------
# PERSISTENT MEMORY (survives closing/reopening Jarvis)
# ---------------------------------------------------------------------------
MEMORY_FILE = os.path.join(os.path.expanduser("~"), "jarvis_memory.json")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), "jarvis_config.json")
STATE_FILE = os.path.join(os.path.expanduser("~"), "jarvis_state.json")
DEVICE_FILE = os.path.join(os.path.expanduser("~"), "jarvis_devices.json")
SOCIAL_DB_FILE = os.path.join(os.path.expanduser("~"), "jarvis_social_agent.json")
SOCIAL_AUDIT_FILE = os.path.join(os.path.expanduser("~"), "jarvis_social_audit.jsonl")
AUTOSTART_NAME = "JarvisPersonalAI"

DEFAULT_CONFIG = {
    "start_with_windows": True,
    "background_mode": True,
    "quiet_mode": False,
    "proactive_enabled": True,
    "proactive_frequency": "balanced",
    "voice_personality": "warm futuristic",
    "preferred_name": "boss",
    "awareness_poll_seconds": 20,
    "device_network_enabled": True,
    "device_network_port": 8765,
    "social_agent": {
        "mode": "APPROVAL",
        "instagram_enabled": False,
        "whatsapp_enabled": False,
        "niche": "Indian relatable tech/lifestyle humor",
        "personality": "transparent AI assistant, witty, helpful, never pretending to be human",
        "themes": ["Indian relatable content", "productivity", "student/work life", "light tech humor"],
        "reply_mode": "APPROVAL",
        "max_autonomous_replies_per_hour": 5,
        "require_approval_for_bio": True,
        "hard_blocks": ["delete_content", "credentials", "financial", "mass_messaging", "suspicious_activity"],
    },
}

def load_config() -> dict:
    data = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception as e:
            print(f"[Config load error] {e}")
    return data

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(JARVIS_CONFIG, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Config save error] {e}")

JARVIS_CONFIG = load_config()


def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("facts", {})
                data.setdefault("history", [])
                data.setdefault("profile", {})
                data.setdefault("preferences", {})
                data.setdefault("routines", {})
                data.setdefault("projects", {})
                data.setdefault("tasks", [])
                data.setdefault("conversation_summaries", [])
                return data
        except Exception as e:
            print(f"[Memory load error] {e}")
    return {"facts": {}, "history": [], "profile": {}, "preferences": {}, "routines": {}, "projects": {}, "tasks": [], "conversation_summaries": []}


def save_memory():
    try:
        MEMORY_DATA["history"] = CONVO_HISTORY
        MEMORY_DATA["last_saved_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(MEMORY_DATA, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memory save error] {e}")


MEMORY_DATA = load_memory()


def remember_fact(key: str, value: str) -> str:
    if is_sensitive_text(key) or is_sensitive_text(value):
        return "I can remember preferences and facts, but not passwords, OTPs, tokens, or other secrets."
    MEMORY_DATA["facts"][key.strip().lower()] = value
    save_memory()
    return f"Got it, I'll remember that {key} is {value}."


def recall_fact(key: str) -> str:
    value = MEMORY_DATA["facts"].get(key.strip().lower())
    if value:
        return f"{key}: {value}"
    return f"I don't have anything saved for '{key}'."


def remember_personal_context(category: str, key: str, value: str) -> str:
    """Store long-term personal context beyond simple facts."""
    category = (category or "facts").strip().lower()
    if category not in {"profile", "preferences", "routines", "projects", "facts"}:
        category = "facts"
    if is_sensitive_text(key) or is_sensitive_text(value):
        return "I can remember useful personal context, but not passwords, OTPs, tokens, or other secrets."
    MEMORY_DATA.setdefault(category, {})[key.strip().lower()] = {"value": value, "updated_at": datetime.datetime.now().isoformat(timespec="seconds")}
    save_memory()
    return f"Remembered under {category}: {key} is {value}."

def add_task_memory(task: str, status: str = "open") -> str:
    if is_sensitive_text(task):
        return "I won't store that because it looks sensitive."
    task_item = {"id": str(uuid.uuid4())[:8], "task": task.strip(), "status": status, "updated_at": datetime.datetime.now().isoformat(timespec="seconds")}
    MEMORY_DATA.setdefault("tasks", []).append(task_item)
    MEMORY_DATA["tasks"] = MEMORY_DATA["tasks"][-50:]
    SESSION_MEMORY["current_task"] = task.strip()
    save_memory()
    return f"Saved task {task_item['id']}: {task}."

def continue_last_task() -> str:
    open_tasks = [t for t in MEMORY_DATA.get("tasks", []) if t.get("status") != "done"]
    if open_tasks:
        task = open_tasks[-1]
        SESSION_MEMORY["current_task"] = task.get("task", "")
        return f"We left off with: {task.get('task')}"
    if SESSION_MEMORY.get("current_task"):
        return f"We were working on: {SESSION_MEMORY['current_task']}"
    return "I don't have an unfinished task saved yet."

def set_quiet_mode(enabled: bool) -> str:
    JARVIS_CONFIG["quiet_mode"] = bool(enabled)
    save_config()
    return "Quiet mode on. I'll stay silent unless you wake me or something critical happens." if enabled else "Quiet mode off. I'll speak up only when useful."

def set_proactive_frequency(frequency: str) -> str:
    frequency = (frequency or "balanced").lower()
    if frequency not in {"low", "balanced", "high"}:
        frequency = "balanced"
    JARVIS_CONFIG["proactive_frequency"] = frequency
    JARVIS_CONFIG["proactive_enabled"] = frequency != "low" or JARVIS_CONFIG.get("proactive_enabled", True)
    save_config()
    return f"Proactive personality set to {frequency}."


# ---------------------------------------------------------------------------
# APP AUTO-DETECTION, OPEN/CLOSE (stripped of internal speech - just do the
# thing and return a plain description; Jarvis's model composes the spoken reply)
# ---------------------------------------------------------------------------
_app_index = {}
_app_index_last_built = 0


def build_app_index() -> dict:
    index = {}
    for base_dir in APP_SEARCH_DIRS:
        if not base_dir or not os.path.isdir(base_dir):
            continue
        for path in glob.glob(os.path.join(base_dir, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(path))[0].strip().lower()
            index[name] = path
    return index


def get_app_index() -> dict:
    global _app_index, _app_index_last_built
    now = time.time()
    if not _app_index or (now - _app_index_last_built) > APP_INDEX_REFRESH_SECONDS:
        _app_index = build_app_index()
        _app_index_last_built = now
    return _app_index


def find_app(name: str):
    index = get_app_index()
    name = name.strip().lower()
    if name in index:
        return index[name]

    # exact substring match first (fast, reliable when it hits)
    for app_name, path in index.items():
        if name in app_name or app_name in name:
            return path

    # fuzzy fallback for typos/partial names ("chrom", "vs code" -> "vscode")
    close = difflib.get_close_matches(name, index.keys(), n=1, cutoff=0.6)
    if close:
        return index[close[0]]
    return None


def open_application(name: str) -> str:
    name_key = name.strip().lower()
    if name_key == "chrome":
        try:
            subprocess.Popen(["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"])
        except FileNotFoundError:
            webbrowser.open("https://www.google.com")
        record_action("close_app", "chrome")
        time.sleep(1.5)
        return "Opened Chrome."
    if name_key == "notepad":
        subprocess.Popen(["notepad.exe"])
        record_action("close_app", "notepad")
        time.sleep(1.0)
        return "Opened Notepad."
    path = find_app(name_key)
    if path:
        os.startfile(path)
        record_action("close_app", name_key)
        time.sleep(1.5)
        return f"Opened {name}."
    return f"Couldn't find an installed app matching '{name}'."


PROCESS_NAME_MAP = {
    "chrome": "chrome.exe", "google": "chrome.exe", "notepad": "notepad.exe",
    "zoom": "Zoom.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE", "spotify": "Spotify.exe", "vlc": "vlc.exe",
}

try:
    import win32com.client as _win32com_client
except ImportError:
    _win32com_client = None


def resolve_exe_from_shortcut(lnk_path: str):
    if not _win32com_client or not lnk_path:
        return None
    try:
        shell = _win32com_client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        target = shortcut.Targetpath
        if target:
            return os.path.basename(target)
    except Exception as e:
        print(f"[shortcut resolve error] {e}")
    return None


def close_app_by_name(name: str) -> str:
    name_key = name.strip().lower()
    process_name = PROCESS_NAME_MAP.get(name_key)
    if not process_name:
        process_name = resolve_exe_from_shortcut(find_app(name_key))
    if not process_name:
        process_name = f"{name_key}.exe"
    try:
        result = subprocess.run(["taskkill", "/IM", process_name, "/F"],
                                 capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return f"Closed {name}."
        return f"{name} wasn't running, or I couldn't close it."
    except Exception as e:
        print(f"[close_app error] {e}")
        return f"Something went wrong closing {name}."

def list_running_apps() -> str:
    if not psutil:
        return "The 'psutil' package isn't installed, so I can't check running apps."
    names = set()
    for proc in psutil.process_iter(["name"]):
        try:
            n = proc.info["name"]
            if n and not n.lower().startswith(("system", "svchost", "registry")):
                names.add(n.replace(".exe", ""))
        except Exception:
            continue
    return ", ".join(sorted(names)[:25])  # cap so it doesn't flood the reply


# ---------------------------------------------------------------------------
# WEB: SEARCH / OPEN WEBSITE / YOUTUBE
# ---------------------------------------------------------------------------

def web_search(query: str) -> str:
    webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
    return f"Searched Google for '{query}'."


def open_website(site: str) -> str:
    site_key = site.strip().lower()
    if site_key in SMART_WEB_APPS:
        webbrowser.open(SMART_WEB_APPS[site_key])
        return f"Opened {site}."
    domain = site_key.replace(" ", "")
    if "." not in domain:
        domain += ".com"
    webbrowser.open(f"https://{domain}")
    return f"Opened {domain}."


def play_youtube(query: str) -> str:
    webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
    return f"Opened YouTube search results for '{query}'."


def take_screenshot() -> str:
    folder = os.path.join(os.path.expanduser("~"), "Pictures", "JarvisScreenshots")
    os.makedirs(folder, exist_ok=True)
    filename = datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = os.path.join(folder, filename)
    if not ImageGrab:
        return "Pillow ImageGrab is not available, so I could not take a screenshot."
    ImageGrab.grab().save(path)
    record_action("delete_file", path)
    return f"Saved a screenshot to {path}."


def type_text(text: str) -> str:
    """Types text into whatever window currently has focus (e.g. a Notepad
    document or a browser search box) via clipboard+paste, which handles
    Hindi/Unicode far more reliably than simulated keystrokes.

    NOTE: if this is called right after open_application() in the same turn,
    the target window may not have finished gaining focus yet - a short pause
    here avoids the text landing in the wrong window (or nowhere)."""
    time.sleep(1.0)
    try:
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
    except Exception as e:
        return f"Couldn't copy text to type: {e}"
    if keyboard:
        keyboard.send("ctrl+v")
        return f"Typed: {text[:60]}"
    return "The 'keyboard' package is needed to paste text - pip install keyboard."


def get_time() -> str:
    return datetime.datetime.now().strftime("It's %I:%M %p on %A, %B %d.")

def get_weather(city: str = "") -> str:
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%C+%t+(feels+like+%f)"
    try:
        if not requests:
            return "The requests package is needed for weather."
        resp = requests.get(url, timeout=8, headers={"User-Agent": "curl"})  # wttr.in needs a real UA or it returns HTML
        return resp.text.strip()
    except Exception as e:
        print(f"[Weather error] {e}")
        return "Couldn't fetch the weather right now."    


# ---------------------------------------------------------------------------
# MS PAINT DRAWING (real execution via mouse automation - this is what was
# MISSING before, which is why Nova used to just claim it had drawn something)
#
# HONESTY NOTE: pixel-based automation like this is inherently approximate -
# it depends on your screen resolution, DPI scaling, and exact Paint version.
# Coordinates below are relative to your screen size (not hardcoded pixels),
# which makes it reasonably portable, but the color palette click positions
# in particular (PAINT_COLOR_POSITIONS) are calibrated for classic Windows 7
# Paint and may need small adjustment on your machine - if colors land wrong,
# that's the first thing to tweak.
# ---------------------------------------------------------------------------

# Relative (0.0-1.0) positions of common color swatches in classic MS Paint's
# palette row. Adjust these if clicks land on the wrong color on your setup.
PAINT_COLOR_POSITIONS = {
    "black": (0.365, 0.098), "red": (0.372, 0.083), "green": (0.379, 0.098),
    "blue": (0.386, 0.083), "yellow": (0.393, 0.098), "white": (0.365, 0.083),
    "orange": (0.400, 0.083), "purple": (0.407, 0.098),
    "gray": (0.414, 0.083), "brown": (0.421, 0.098),
    "cyan": (0.428, 0.083), "magenta": (0.435, 0.098),
}
def _paint_ready() -> bool:
    if not pyautogui:
        return False
    return True


def open_paint() -> str:
    if not _paint_ready():
        return "The 'pyautogui' package is needed for Paint drawing - pip install pyautogui."
    subprocess.Popen(["mspaint.exe"])
    time.sleep(2.0)
    try:
        pyautogui.hotkey("win", "up")  # maximize, so canvas coordinates are consistent
        time.sleep(0.5)
    except Exception:
        pass
    return "Opened MS Paint (maximized)."


def select_paint_color(color: str) -> str:
    if not _paint_ready():
        return "pyautogui not available."
    color_key = color.strip().lower()
    pos = PAINT_COLOR_POSITIONS.get(color_key)
    if not pos:
        return f"Don't have a palette position for '{color}' - defaulting to black outline."
    w, h = pyautogui.size()
    pyautogui.click(int(w * pos[0]), int(h * pos[1]))
    return f"Selected {color}."

def fill_area(x_offset: int = 0, y_offset: int = 0, color: str = "black") -> str:
    """Fills a CLOSED shape (circle/rectangle you already drew) with color.
    Click position for the paint-bucket tool icon needs the same calibration
    caveat as PAINT_COLOR_POSITIONS - adjust FILL_TOOL_POSITION if it misses."""
    if not _paint_ready():
        return "pyautogui not available."
    w, h = pyautogui.size()
    FILL_TOOL_POSITION = (0.045, 0.11)  # bucket icon in classic toolbox
    pyautogui.click(int(w * FILL_TOOL_POSITION[0]), int(h * FILL_TOOL_POSITION[1]))
    select_paint_color(color)
    cx, cy = w // 2, h // 2
    pyautogui.click(cx + x_offset, cy + y_offset)
    return f"Filled the shape at ({x_offset}, {y_offset}) with {color}."


def draw_circle_paint(radius_px: int = 100, color: str = "black", filled: bool = False) -> str:
    if not _paint_ready():
        return "pyautogui not available."
    if color != "black":
        select_paint_color(color)
    w, h = pyautogui.size()
    cx, cy = w // 2, h // 2
    steps = 48
    pyautogui.moveTo(cx + radius_px, cy)
    pyautogui.mouseDown()
    for i in range(1, steps + 1):
        angle = (2 * math.pi / steps) * i
        x = cx + int(radius_px * math.cos(angle))
        y = cy + int(radius_px * math.sin(angle))
        pyautogui.moveTo(x, y, duration=0.015)
    pyautogui.mouseUp()
    if filled:
        # Paint's fill/bucket tool is the 2nd icon in the classic toolbox -
        # approximate position; click it, then click inside the circle.
        pyautogui.click(int(w * 0.045), int(h * 0.11))
        pyautogui.click(cx, cy)
    return f"Drew a circle (radius ~{radius_px}px, {color}{', filled' if filled else ', outline'})."


def draw_rectangle_paint(x_offset: int = -150, y_offset: int = 0, width: int = 300, height: int = 150, color: str = "black") -> str:
    if not _paint_ready():
        return "pyautogui not available."
    if color != "black":
        select_paint_color(color)
    w, h = pyautogui.size()
    x0, y0 = w // 2 + x_offset, h // 2 + y_offset
    x1, y1 = x0 + width, y0 + height
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    pyautogui.moveTo(*corners[0])
    pyautogui.mouseDown()
    for pt in corners[1:]:
        pyautogui.moveTo(*pt, duration=0.2)
    pyautogui.mouseUp()
    return f"Drew a rectangle ({color})."


def draw_line_paint(x1_off: int, y1_off: int, x2_off: int, y2_off: int, color: str = "black") -> str:
    if not _paint_ready():
        return "pyautogui not available."
    if color != "black":
        select_paint_color(color)
    w, h = pyautogui.size()
    cx, cy = w // 2, h // 2
    pyautogui.moveTo(cx + x1_off, cy + y1_off)
    pyautogui.mouseDown()
    pyautogui.moveTo(cx + x2_off, cy + y2_off, duration=0.2)
    pyautogui.mouseUp()
    return f"Drew a line ({color})."

def draw_freehand(points: list, color: str = "black") -> str:
    """points = list of [x_offset, y_offset] pairs relative to canvas center.
    Lets Nova draw ANY shape, not just circle/rectangle/line - e.g. a star,
    an arrow, a custom outline - by connecting a sequence of points."""
    if not _paint_ready():
        return "pyautogui not available."
    if not points or len(points) < 2:
        return "Need at least 2 points to draw a freehand shape."
    if color != "black":
        select_paint_color(color)
    w, h = pyautogui.size()
    cx, cy = w // 2, h // 2
    start = points[0]
    pyautogui.moveTo(cx + start[0], cy + start[1])
    pyautogui.mouseDown()
    for pt in points[1:]:
        pyautogui.moveTo(cx + pt[0], cy + pt[1], duration=0.08)
    pyautogui.mouseUp()
    return f"Drew a freehand shape with {len(points)} points ({color})."

PAINT_TEXT_TOOL_POSITION = (0.30, 0.045)  # "A" text icon in classic toolbox - calibrate

def add_text_paint(text: str, x_offset: int = 0, y_offset: int = 0) -> str:
    if not _paint_ready():
        return "pyautogui not available."
    w, h = pyautogui.size()
    pyautogui.click(int(w * PAINT_TEXT_TOOL_POSITION[0]), int(h * PAINT_TEXT_TOOL_POSITION[1]))
    cx, cy = w // 2, h // 2
    # drag out a text box before typing, or Paint ignores keystrokes
    pyautogui.moveTo(cx + x_offset, cy + y_offset)
    pyautogui.mouseDown()
    pyautogui.moveTo(cx + x_offset + 200, cy + y_offset + 60, duration=0.2)
    pyautogui.mouseUp()
    time.sleep(0.3)
    type_text(text)  # reuses your existing clipboard-paste typing, keeps Hindi/Unicode support
    pyautogui.click(cx + x_offset + 300, cy + y_offset + 200)  # click outside to commit the text box
    return f"Added text: {text}"

def paint_undo() -> str:
    if not keyboard:
        return "The 'keyboard' package is needed."
    keyboard.send("ctrl+z")
    return "Undid the last Paint action."

def paint_redo() -> str:
    if not keyboard:
        return "The 'keyboard' package is needed."
    keyboard.send("ctrl+y")
    return "Redid the last Paint action."

def clear_canvas() -> str:
    if not keyboard:
        return "The 'keyboard' package is needed."
    keyboard.send("ctrl+a")
    time.sleep(0.1)
    keyboard.send("delete")
    return "Cleared the canvas."

def save_paint_drawing(filename: str = "nova_drawing") -> str:
    if not keyboard:
        return "The 'keyboard' package is needed."
    keyboard.send("ctrl+s")
    time.sleep(1.0)  # wait for the Save As dialog on first save
    keyboard.write(filename)
    time.sleep(0.2)
    keyboard.send("enter")
    return f"Saved drawing as '{filename}'."

def draw_scenery_paint() -> str:
    """A quick default scene: sun, ground, a house, and a tree. Uses the
    default black outline (color selection is the least reliable part of
    Paint automation, so scenery defaults to plain outlines for reliability)."""
    if not _paint_ready():
        return "pyautogui not available."
    open_paint()
    w, h = pyautogui.size()
    cx, cy = w // 2, h // 2

    # ground line
    draw_line_paint(-350, 150, 350, 150)
    # sun (small circle, top-left area)
    old_center = (cx, cy)
    pyautogui.moveTo(cx - 300, cy - 200)
    draw_circle_paint(radius_px=40)
    # house body
    draw_rectangle_paint(x_offset=50, y_offset=0, width=180, height=150)
    # roof (two lines forming a triangle)
    draw_line_paint(50, 0, 140, -90)
    draw_line_paint(140, -90, 230, 0)
    # tree trunk + leaves
    draw_rectangle_paint(x_offset=-250, y_offset=60, width=20, height=90)
    pyautogui.moveTo(cx - 240, cy - 20)
    draw_circle_paint(radius_px=50)
    return "Drew a simple scenery: sun, ground, a house, and a tree."


# ---------------------------------------------------------------------------
# ZOOM CONTROL
# ---------------------------------------------------------------------------
ZOOM_HOTKEYS = {
    "toggle_mic": "alt+a", "toggle_video": "alt+v", "mute_all": "alt+m",
    "stop_share": "alt+s", "pause_resume_share": "alt+t", "toggle_recording": "alt+r",
    "speaker_view": "alt+f1", "gallery_view": "alt+f2", "toggle_chat": "alt+h",
    "toggle_participants": "alt+u", "raise_hand": "alt+y", "leave_meeting": "alt+q",
}


def open_zoom() -> str:
    path = find_app("zoom")
    if path:
        os.startfile(path)
        return "Opened Zoom."
    zoom_path = os.path.expandvars(r"%appdata%\Zoom\bin\Zoom.exe")
    if os.path.exists(zoom_path):
        subprocess.Popen(zoom_path)
        return "Opened Zoom."
    os.system("start zoom")
    return "Tried opening Zoom."


def control_zoom(action: str) -> str:
    if not keyboard:
        return "The 'keyboard' package is needed for Zoom control - pip install keyboard."
    if action == "open":
        return open_zoom()
    if action == "new_meeting":
        open_zoom()
        time.sleep(3)
        keyboard.send("alt+v")
        return "Opened Zoom and started an instant meeting."
    if action == "share_screen":
        keyboard.send("alt+s")
        time.sleep(0.5)
        keyboard.send("enter")
        return "Started sharing the screen."
    hotkey = ZOOM_HOTKEYS.get(action)
    if not hotkey:
        return f"Unknown Zoom action: {action}"
    keyboard.send(hotkey)
    return f"Sent Zoom action '{action}'."


# ---------------------------------------------------------------------------
# CHROME CONTROL
# ---------------------------------------------------------------------------
CHROME_HOTKEYS = {
    "new_tab": ("ctrl+t", "ctrl+w"), "close_tab": ("ctrl+w", "ctrl+shift+t"),
    "reopen_tab": ("ctrl+shift+t", "ctrl+w"), "new_window": ("ctrl+n", "ctrl+shift+w"),
    "incognito": ("ctrl+shift+n", "ctrl+shift+w"), "next_tab": ("ctrl+tab", "ctrl+shift+tab"),
    "previous_tab": ("ctrl+shift+tab", "ctrl+tab"), "address_bar": ("ctrl+l", None),
    "go_back": ("alt+left", "alt+right"), "go_forward": ("alt+right", "alt+left"),
    "refresh": ("ctrl+r", None), "hard_refresh": ("ctrl+shift+r", None),
    "stop_loading": ("esc", None), "zoom_in": ("ctrl+=", "ctrl+-"),
    "zoom_out": ("ctrl+-", "ctrl+="), "reset_zoom": ("ctrl+0", None),
    "full_screen": ("f11", "f11"), "find_on_page": ("ctrl+f", "esc"),
    "bookmark_page": ("ctrl+d", None), "open_bookmarks": ("ctrl+shift+o", "ctrl+w"),
    "open_history": ("ctrl+h", "ctrl+w"), "open_downloads": ("ctrl+j", "ctrl+w"),
    "dev_tools": ("ctrl+shift+i", "ctrl+shift+i"), "view_source": ("ctrl+u", "ctrl+w"),
    "print_page": ("ctrl+p", "esc"), "save_page": ("ctrl+s", "esc"),
    "close_window": ("ctrl+shift+w", None),
}


def control_chrome(action: str) -> str:
    if not keyboard:
        return "The 'keyboard' package is needed for Chrome control - pip install keyboard."
    entry = CHROME_HOTKEYS.get(action)
    if not entry:
        return f"Unknown Chrome action: {action}"
    hotkey, undo_hotkey = entry
    keyboard.send(hotkey)
    if undo_hotkey:
        record_action("hotkey", undo_hotkey)
    return f"Sent Chrome action '{action}'."


# ---------------------------------------------------------------------------
# VOLUME & MEDIA CONTROL
# ---------------------------------------------------------------------------
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _press_media_key(vk_code: int):
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def control_volume(direction: str) -> str:
    if direction == "up":
        for _ in range(5):
            _press_media_key(VK_VOLUME_UP)
        return "Volume up."
    if direction == "down":
        for _ in range(5):
            _press_media_key(VK_VOLUME_DOWN)
        return "Volume down."
    if direction == "mute":
        _press_media_key(VK_VOLUME_MUTE)
        return "Toggled mute."
    return f"Unknown volume direction: {direction}"


def control_media(action: str) -> str:
    mapping = {
        "play_pause": VK_MEDIA_PLAY_PAUSE,
        "next": VK_MEDIA_NEXT_TRACK,
        "previous": VK_MEDIA_PREV_TRACK,
    }
    vk = mapping.get(action)
    if not vk:
        return f"Unknown media action: {action}"
    _press_media_key(vk)
    return f"Media action '{action}' done."

def control_brightness(direction: str, amount: int = 10) -> str:
    if not sbc:
        return "The 'screen_brightness_control' package is needed - pip install screen-brightness-control."
    try:
        current = sbc.get_brightness(display=0)[0]
        if direction == "up":
            new_level = min(100, current + amount)
        elif direction == "down":
            new_level = max(0, current - amount)
        elif direction == "set":
            new_level = max(0, min(100, amount))
        else:
            return f"Unknown brightness direction: {direction}"
        sbc.set_brightness(new_level)
        return f"Brightness set to {new_level}%."
    except Exception as e:
        print(f"[Brightness error] {e}")
        return "Couldn't change screen brightness on this display."


# ---------------------------------------------------------------------------
# OCR, PDF, VISION
# ---------------------------------------------------------------------------

def _preprocess_for_ocr(img):
    """Light preprocessing that noticeably helps OCR accuracy on textbook
    pages, whiteboard photos, or low-contrast screenshots."""
    try:
        from PIL import ImageOps, ImageEnhance
        gray = ImageOps.grayscale(img)
        gray = ImageEnhance.Contrast(gray).enhance(1.6)
        gray = ImageEnhance.Sharpness(gray).enhance(1.4)
        return gray
    except Exception:
        return img


def ocr_screen_text() -> str:
    if not pytesseract:
        return ""
    try:
        if not ImageGrab:
            return ""
        img = ImageGrab.grab()
        img.thumbnail((1600, 900))
        processed = _preprocess_for_ocr(img)
        # Try English+Hindi combined first (needs Hindi traineddata installed
        # alongside Tesseract); fall back to English-only if that's missing.
        try:
            return pytesseract.image_to_string(processed, lang="eng+hin").strip()
        except Exception:
            return pytesseract.image_to_string(processed, lang="eng").strip()
    except Exception as e:
        print(f"[OCR error] {e}")
        return ""


def capture_screen_base64() -> str:
    if not ImageGrab:
        return ""
    img = ImageGrab.grab()
    img.thumbnail((1280, 720))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def analyze_screen(question: str = "Describe what's on my screen briefly.") -> str:
    if not OPENAI_API_KEY:
        return "Need an OpenAI API key set up to analyze the screen."
    try:
        if not requests:
            return "The requests package is needed for OpenAI screen analysis."
        response = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "max_completion_tokens": 300,
                "reasoning_effort": "low",
                "messages": [
                    {"role": "user", "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{capture_screen_base64()}"}}
                    ]}
                ]
            }, timeout=30
        )
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Vision Error] {e}")
        return "Couldn't look at the screen right now."

def find_text_on_screen(target: str):
    """Returns (x, y) center coordinates of the first on-screen match for
    `target`, or None. Unlike ocr_screen_text(), this knows WHERE something
    is - needed before Jarvis can click on it."""
    if not pytesseract:
        return None
    try:
        img = ImageGrab.grab()
        img.thumbnail((1600, 900))
        processed = _preprocess_for_ocr(img)
        data = pytesseract.image_to_data(processed, lang="eng", output_type=pytesseract.Output.DICT)
    except Exception as e:
        print(f"[OCR bbox error] {e}")
        return None

    # thumbnail() shrinks the image, so boxes are in shrunk coords - scale
    # back up to real screen pixels before returning
    screen_w, screen_h = pyautogui.size() if pyautogui else img.size
    scale_x = screen_w / processed.width
    scale_y = screen_h / processed.height

    target_lower = target.strip().lower()
    for i, word in enumerate(data["text"]):
        if word.strip() and target_lower in word.strip().lower():
            x = data["left"][i] + data["width"][i] // 2
            y = data["top"][i] + data["height"][i] // 2
            return (int(x * scale_x), int(y * scale_y))
    return None


def click_on_text(target: str) -> str:
    if not pyautogui:
        return "The 'pyautogui' package is needed to click screen elements."
    pos = find_text_on_screen(target)
    if not pos:
        return f"Couldn't find '{target}' anywhere on screen."
    pyautogui.click(*pos)
    return f"Clicked on '{target}'."

def read_screen_text() -> str:
    extracted = ocr_screen_text()
    if extracted and len(extracted) > 15:
        return extracted[:1500]
    return analyze_screen("Read and repeat back any text visible on this screen.")


def find_pdf(name_hint: str):
    name_hint = name_hint.strip().lower()
    for base_dir in PDF_SEARCH_DIRS:
        if os.path.isdir(base_dir):
            for fname in os.listdir(base_dir):
                if fname.lower().endswith(".pdf") and name_hint in fname.lower():
                    return os.path.join(base_dir, fname)
    return None


def read_pdf_text(path: str, max_chars: int = 6000) -> str:
    """max_chars raised from 2000 to 6000 - enough for the model to actually
    summarize/analyze a document, not just read the first paragraph."""
    if not PdfReader:
        return ""
    try:
        reader = PdfReader(path)
        text = "".join([(page.extract_text() or "") + "\n" for page in reader.pages])
        return text.strip()[:max_chars]
    except Exception as e:
        print(f"[PDF read error] {e}")
        return ""


def read_pdf(name_hint: str) -> str:
    path = find_pdf(name_hint)
    if not path:
        return f"Couldn't find a PDF matching '{name_hint}' in Downloads or Documents."
    content = read_pdf_text(path)
    if content:
        return content
    return (f"Found {os.path.basename(path)} but couldn't extract any text - it's likely a "
            f"scanned image PDF, which needs OCR rather than text extraction (not yet supported here).")


def explain_clipboard() -> str:
    try:
        root = tk.Tk()
        root.withdraw()
        copied = root.clipboard_get()
        root.destroy()
    except Exception:
        copied = ""
    if not copied:
        return "The clipboard is empty."
    return copied[:1200]



# ---------------------------------------------------------------------------
# JARVIS STATE, SECURITY, HUD, CONTEXT, AND SCREEN INTELLIGENCE HELPERS
# ---------------------------------------------------------------------------
ASSISTANT_NAME = "Jarvis"
SENSITIVE_TOOL_NAMES = {"call_person", "dial_number_on_phone", "type_on_phone", "send_whatsapp_message", "change_instagram_bio"}
SENSITIVE_WORDS = {"password", "otp", "token", "secret", "api key", "credit card", "cvv", "pin"}
SESSION_MEMORY = {"recent_actions": [], "visual_notes": [], "current_task": ""}
_LAST_SCREEN_TEXT = ""
_HUD_ROOT = None
_HUD_LABEL = None

def is_sensitive_text(text: str) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in SENSITIVE_WORDS)

def set_status(state: str, detail: str = ""):
    """Lightweight Windows-7-friendly status HUD; silently degrades in headless/non-GUI runs."""
    print(f"[Jarvis:{state}] {detail}".strip())
    global _HUD_ROOT, _HUD_LABEL
    try:
        if _HUD_ROOT is None:
            _HUD_ROOT = tk.Tk()
            _HUD_ROOT.overrideredirect(True)
            _HUD_ROOT.attributes("-topmost", True)
            _HUD_ROOT.geometry("360x44+20+20")
            _HUD_ROOT.configure(bg="#06121f")
            _HUD_LABEL = tk.Label(_HUD_ROOT, fg="#7df9ff", bg="#06121f", font=("Segoe UI", 11, "bold"))
            _HUD_LABEL.pack(fill="both", expand=True)
        _HUD_LABEL.config(text=f"JARVIS • {state.upper()} {detail[:80]}")
        _HUD_ROOT.update_idletasks()
        _HUD_ROOT.update()
    except Exception:
        _HUD_ROOT = None
        _HUD_LABEL = None

def remember_session_note(kind: str, text: str):
    if text:
        SESSION_MEMORY.setdefault(kind, []).append({"time": datetime.datetime.now().isoformat(timespec="seconds"), "text": text[:1000]})
        SESSION_MEMORY[kind] = SESSION_MEMORY[kind][-10:]

def get_active_window_title() -> str:
    if sys.platform != "win32":
        return "Active-window detection is only available on Windows."
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or "Unknown active window"
    except Exception as e:
        return f"Couldn't read active window: {e}"

def context_snapshot() -> str:
    clip = explain_clipboard()
    if len(clip) > 250:
        clip = clip[:250] + "..."
    return json.dumps({
        "active_window": get_active_window_title(),
        "clipboard": clip if clip != "The clipboard is empty." else "",
        "current_task": SESSION_MEMORY.get("current_task", ""),
        "recent_actions": SESSION_MEMORY.get("recent_actions", [])[-5:],
        "visual_notes": SESSION_MEMORY.get("visual_notes", [])[-3:],
        "personal_memory": {k: MEMORY_DATA.get(k, {}) for k in ("profile", "preferences", "routines", "projects")},
        "open_tasks": [t for t in MEMORY_DATA.get("tasks", []) if t.get("status") != "done"][-5:],
        "quiet_mode": JARVIS_CONFIG.get("quiet_mode"),
        "proactive_frequency": JARVIS_CONFIG.get("proactive_frequency"),
        "device_network": DEVICE_DATA.get("devices", {}) if "DEVICE_DATA" in globals() else {},
        "background_state": SESSION_MEMORY.get("background_state", {}),
        "social_agent": social_config() if "social_config" in globals() else {},
    }, ensure_ascii=False)



def save_background_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(SESSION_MEMORY, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[State save error] {e}")

def seconds_since_user_input() -> int:
    if sys.platform != "win32":
        return 0
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0, int(millis / 1000))
    except Exception:
        return 0

def awareness_snapshot() -> dict:
    idle_seconds = seconds_since_user_input()
    return {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "active_window": get_active_window_title(),
        "idle_seconds": idle_seconds,
        "activity": "idle" if idle_seconds >= 300 else "active",
        "current_task": SESSION_MEMORY.get("current_task", ""),
        "last_action": SESSION_MEMORY.get("recent_actions", [])[-1:] or [],
    }

def awareness_watcher():
    last_window = ""
    while True:
        time.sleep(max(10, int(JARVIS_CONFIG.get("awareness_poll_seconds", 20))))
        snap = awareness_snapshot()
        SESSION_MEMORY["background_state"] = snap
        if snap["active_window"] != last_window:
            last_window = snap["active_window"]
            remember_session_note("recent_actions", f"active window: {last_window}")
        save_background_state()

def install_windows_autostart() -> str:
    if sys.platform != "win32":
        return "Autostart registry setup is only available on Windows."
    script = os.path.abspath(__file__)
    cmd = f'"{sys.executable}" "{script}" --background'
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return "Jarvis will start automatically with Windows."
    except Exception as e:
        return f"Couldn't set Windows autostart: {e}"

def ensure_autostart():
    if JARVIS_CONFIG.get("start_with_windows"):
        result = install_windows_autostart()
        print(f"[Autostart] {result}")

def ocr_screen_layout() -> str:
    """OCR with approximate word positions, useful for clicking buttons before using vision."""
    if not pytesseract:
        return "OCR package isn't installed."
    try:
        img = ImageGrab.grab()
        img.thumbnail((1600, 900))
        processed = _preprocess_for_ocr(img)
        data = pytesseract.image_to_data(processed, lang="eng", output_type=pytesseract.Output.DICT)
        screen_w, screen_h = pyautogui.size() if pyautogui else img.size
        sx, sy = screen_w / processed.width, screen_h / processed.height
        items = []
        for i, word in enumerate(data.get("text", [])):
            word = (word or "").strip()
            if len(word) < 2:
                continue
            x = int((data["left"][i] + data["width"][i] / 2) * sx)
            y = int((data["top"][i] + data["height"][i] / 2) * sy)
            items.append(f"{word}@({x},{y})")
        result = "; ".join(items[:120])
        remember_session_note("visual_notes", result)
        return result or "No readable text detected on screen."
    except Exception as e:
        return f"Couldn't inspect screen layout: {e}"

def click_ui_target(target: str) -> str:
    before = get_active_window_title()
    result = click_on_text(target)
    time.sleep(0.4)
    after = get_active_window_title()
    verify = "verified window changed" if before != after else "click sent; no window-title change detected"
    remember_session_note("recent_actions", f"click {target}: {result} ({verify})")
    return f"{result} Verification: {verify}."

def system_diagnostics() -> str:
    if not psutil:
        return "Install psutil for CPU/RAM/battery/storage/network diagnostics."
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.expanduser("~"))
    batt = psutil.sensors_battery()
    net = psutil.net_if_stats()
    online = any(v.isup for v in net.values()) if net else False
    b = f"battery {batt.percent}% ({'charging' if batt.power_plugged else 'not charging'})" if batt else "no battery reported"
    return f"CPU {cpu}%, RAM {ram.percent}% ({ram.available//(1024**2)} MB free), storage {disk.percent}% used, network {'up' if online else 'down'}, {b}."

def draft_whatsapp_reply(message: str, tone: str = "friendly") -> str:
    if is_sensitive_text(message):
        return "This looks sensitive, so I can draft only after you approve the context."
    return f"Draft ({tone}): Thanks, I saw this. I'll reply properly in a moment. [Review before sending]"

def translate_screen_overlay(target_language: str = "Hindi") -> str:
    text = ocr_screen_text()
    if not text:
        return "Couldn't read screen text to translate."
    if not OPENAI_API_KEY:
        return "I can read the screen, but OPENAI_API_KEY is needed for translation."
    messages = [{"role": "system", "content": "Translate faithfully. Preserve names, numbers, and mixed Hinglish where useful."}, {"role": "user", "content": f"Translate to {target_language}:\n{text[:2000]}"}]
    data, err = _call_openai(messages, max_tokens=600)
    if err:
        return f"Translation failed: {err}"
    translated = (data["choices"][0]["message"].get("content") or "").strip()
    set_status("translation", translated[:120])
    remember_session_note("visual_notes", f"translated screen: {translated[:500]}")
    return translated

# ---------------------------------------------------------------------------
# TELEGRAM PHONE-CALL BRIDGE & ZOOM MEETING LINKS
# ---------------------------------------------------------------------------

def call_person(name: str) -> str:
    name_key = name.strip().lower()
    number = CONTACTS.get(name_key)
    if not number:
        return f"I don't have a saved number for {name}. Add them to CONTACTS in the script."
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return "The Telegram bridge isn't configured yet."
    try:
        if not requests:
            return "The requests package is needed for the Telegram bridge."
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"CALL:{number}"}, timeout=10
        )
        return f"Told your phone to call {name}."
    except Exception as e:
        print(f"[Telegram error] {e}")
        return "Couldn't reach Telegram."


def join_meeting(name: str) -> str:
    link = ZOOM_LINKS.get(name.strip().lower())
    if not link:
        return f"I don't have a saved Zoom link for '{name}'. Add it to ZOOM_LINKS."
    webbrowser.open(link)
    return f"Joined the {name} meeting."

# Existing ADB helpers above are reused here; duplicate bridge definitions removed.


def _dump_ui():
    """Dump Android UI hierarchy through ADB; returns an ElementTree root or empty hierarchy."""
    try:
        import xml.etree.ElementTree as ET
        _adb("uiautomator", "dump", "/sdcard/window_dump.xml")
        raw = subprocess.run(["adb", "-s", PHONE_IP, "exec-out", "cat", "/sdcard/window_dump.xml"], capture_output=True, text=True, timeout=10)
        return ET.fromstring(raw.stdout.strip() or "<hierarchy />")
    except Exception as e:
        print(f"[ADB UI dump error] {e}")
        import xml.etree.ElementTree as ET
        return ET.fromstring("<hierarchy />")

def _bounds_center(bounds: str):
    nums = [int(n) for n in re.findall(r"\d+", bounds or "")]
    if len(nums) >= 4:
        return (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2
    return 540, 960

def play_youtube_on_phone(query: str) -> str:
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={encoded_query}"
    _adb("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    time.sleep(3)  # let the YouTube app open and search results load

    root = _dump_ui()
    # first video thumbnail in the results list - resource-id varies by YouTube app version,
    # "thumbnail" is the common substring across most recent builds
    video_node = next((n for n in root.iter("node")
                        if "thumbnail" in n.get("resource-id", "").lower()), None)
    if video_node is None:
        return f"Searched '{query}' on YouTube but couldn't auto-tap the first result - you'll need to tap it."

    x, y = _bounds_center(video_node.get("bounds"))
    _adb("input", "tap", str(x), str(y))
    return f"Playing '{query}' on YouTube."

def _clean_content_request(text: str) -> str:
    cleaned = text.lower()
    for word in _QUERY_FILLER_WORDS:
        cleaned = cleaned.replace(word, "")
    return cleaned.strip()

def youtube_api_search(query: str, live_only: bool = False):
    if not YOUTUBE_API_KEY:
        return None
    params = {"part": "snippet", "q": query, "type": "video", "maxResults": 1, "key": YOUTUBE_API_KEY}
    if live_only:
        params["eventType"] = "live"
    try:
        if not requests:
            return None
        resp = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=10)
        items = resp.json().get("items", [])
        if not items and live_only:
            # nothing live right now - retry without the live filter rather than failing outright
            params.pop("eventType")
            items = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=10).json().get("items", [])
        if not items:
            return None
        return items[0]["id"]["videoId"], items[0]["snippet"]["title"]
    except Exception as e:
        print(f"[YouTube API error] {e}")
        return None

def resolve_content_request(request: str) -> dict:
    cleaned = _clean_content_request(request)
    for category, info in CONTENT_CATEGORIES.items():
        if category in cleaned:
            return info
    close = difflib.get_close_matches(cleaned, CONTENT_CATEGORIES.keys(), n=1, cutoff=0.6)
    if close:
        return CONTENT_CATEGORIES[close[0]]
    return {"query": cleaned if cleaned else request, "live": False}

def play_content_on_phone(request: str) -> str:
    info = resolve_content_request(request)
    result = youtube_api_search(info["query"], live_only=info["live"])

    if result:
        video_id, title = result
        url = f"https://www.youtube.com/watch?v={video_id}"
        _adb("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
        return f"Playing: {title}"

    # no API key set, or API call failed - fall back to the old UI-tap search approach
    return play_youtube_on_phone(info["query"])

# ---------------------------------------------------------------------------
# SYSTEM STATUS / MORNING BRIEFING / VOICE SWITCH
# ---------------------------------------------------------------------------

def system_status() -> str:
    if not psutil:
        return "The 'psutil' package isn't installed, so I can't read system stats."
    battery = psutil.sensors_battery()
    ram = psutil.virtual_memory()
    bat_str = f"battery at {battery.percent}%" if battery else "connected to AC power"
    return f"{bat_str}, RAM usage at {ram.percent}%."


def morning_briefing() -> str:
    now_time = datetime.datetime.now().strftime("%I:%M %p")
    bat_status = ""
    if psutil:
        battery = psutil.sensors_battery()
        bat_status = f" Battery is at {battery.percent}%." if battery else " Power is connected."
    return f"It's {now_time}.{bat_status}"


def switch_voice(mode: str) -> str:
    global CURRENT_VOICE_MODE
    mode = mode.strip().lower()
    if mode not in ("nova", "female"):
        mode = "nova"
    CURRENT_VOICE_MODE = mode
    return f"Switched to the {mode} voice."



# ---------------------------------------------------------------------------
# JARVIS DEVICE NETWORK (lightweight authenticated presence/command routing)
# ---------------------------------------------------------------------------

def _device_secret() -> str:
    secret = os.getenv("JARVIS_DEVICE_SECRET")
    if secret:
        return secret
    seed = os.path.expanduser("~") + socket.gethostname()
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()

def _device_token(payload: str) -> str:
    return hmac.new(_device_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def load_devices() -> dict:
    if os.path.exists(DEVICE_FILE):
        try:
            with open(DEVICE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("devices", {})
            return data
        except Exception as e:
            print(f"[Device load error] {e}")
    return {"identity": "jarvis", "devices": {}}

def save_devices(data: dict):
    try:
        with open(DEVICE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Device save error] {e}")

DEVICE_DATA = load_devices()

def update_device_presence(name: str, kind: str, status: str, capabilities=None) -> str:
    DEVICE_DATA.setdefault("devices", {})[name] = {
        "kind": kind,
        "status": status,
        "capabilities": capabilities or [],
        "last_seen": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    save_devices(DEVICE_DATA)
    return f"{name} is {status}."

def device_status() -> str:
    update_device_presence(socket.gethostname(), "pc", "online", ["computer_control", "voice", "memory", "screen", "files"])
    phone = "configured" if PHONE_IP else "not configured"
    devices = DEVICE_DATA.get("devices", {})
    return f"Jarvis network: phone bridge {phone}; devices: " + ", ".join(f"{n}={d.get('status')}" for n, d in devices.items())

def route_device_command(command: str, capability: str = "") -> str:
    if capability in {"phone", "android", "mobile"} or "phone" in command.lower():
        return "I'll route that through the Android companion bridge when the phone is reachable."
    return "This PC can handle that command locally; if it can't, I'll fall back to a connected device."



# ---------------------------------------------------------------------------
# AUTONOMOUS SOCIAL-MEDIA AGENT (official Meta APIs only)
# ---------------------------------------------------------------------------
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}"
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
SOCIAL_STRATEGY_MODEL = os.getenv("JARVIS_SOCIAL_MODEL", OPENAI_MODEL)
SOCIAL_MODERATION_KEYWORDS = {
    "spam": ["free followers", "crypto giveaway", "investment guaranteed", "click this link", "dm to earn"],
    "toxic": ["kill yourself", "hate you", "idiot", "stupid", "scam"],
    "unsafe": ["password", "otp", "credit card", "bank details", "send money"],
}

def load_social_db() -> dict:
    if os.path.exists(SOCIAL_DB_FILE):
        try:
            with open(SOCIAL_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("posts", [])
            data.setdefault("drafts", [])
            data.setdefault("insights", [])
            data.setdefault("messages", [])
            data.setdefault("strategy_notes", [])
            return data
        except Exception as e:
            print(f"[Social DB load error] {e}")
    return {"posts": [], "drafts": [], "insights": [], "messages": [], "strategy_notes": []}

def save_social_db():
    try:
        with open(SOCIAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(SOCIAL_DB, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Social DB save error] {e}")

def social_audit(action: str, details: dict):
    entry = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "action": action, "details": details}
    try:
        with open(SOCIAL_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Social audit error] {e}")

SOCIAL_DB = load_social_db()

def social_config() -> dict:
    cfg = dict(JARVIS_CONFIG.get("social_agent", {}))
    cfg["instagram_ready"] = bool(INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID)
    cfg["whatsapp_ready"] = bool(WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID)
    return cfg

def set_social_mode(platform: str, mode: str) -> str:
    platform = (platform or "instagram").lower()
    mode = (mode or "APPROVAL").upper()
    if mode not in {"MANUAL", "APPROVAL", "AUTONOMOUS", "OFF"}:
        return "Use MANUAL, APPROVAL, AUTONOMOUS, or OFF."
    cfg = JARVIS_CONFIG.setdefault("social_agent", dict(DEFAULT_CONFIG["social_agent"]))
    if platform == "whatsapp":
        cfg["whatsapp_enabled"] = mode != "OFF"
        cfg["reply_mode"] = "MANUAL" if mode == "OFF" else mode
    else:
        cfg["instagram_enabled"] = mode != "OFF"
        cfg["mode"] = "MANUAL" if mode == "OFF" else mode
    save_config()
    social_audit("set_social_mode", {"platform": platform, "mode": mode})
    return f"{platform.title()} automation set to {mode}."

def _meta_get(path: str, params=None) -> dict:
    if not requests:
        return {"error": "The requests package is required."}
    params = dict(params or {})
    params["access_token"] = INSTAGRAM_ACCESS_TOKEN
    try:
        resp = requests.get(f"{META_GRAPH_BASE}/{path.lstrip('/')}", params=params, timeout=20)
        data = resp.json()
        if resp.status_code >= 400:
            return {"error": data.get("error", {}).get("message", resp.text)}
        return data
    except Exception as e:
        return {"error": str(e)}

def _meta_post(path: str, payload=None, token=None) -> dict:
    if not requests:
        return {"error": "The requests package is required."}
    payload = dict(payload or {})
    payload["access_token"] = token or INSTAGRAM_ACCESS_TOKEN
    try:
        resp = requests.post(f"{META_GRAPH_BASE}/{path.lstrip('/')}", data=payload, timeout=30)
        data = resp.json()
        if resp.status_code >= 400:
            return {"error": data.get("error", {}).get("message", resp.text)}
        return data
    except Exception as e:
        return {"error": str(e)}

def analyze_instagram_performance(days: int = 7) -> str:
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return "Instagram Graph API is not configured. Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID from Meta OAuth."
    metrics = "reach,profile_views,follower_count,website_clicks"
    data = _meta_get(f"{INSTAGRAM_ACCOUNT_ID}/insights", {"metric": metrics, "period": "day"})
    media = _meta_get(f"{INSTAGRAM_ACCOUNT_ID}/media", {"fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count", "limit": min(50, max(5, days * 3))})
    snapshot = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "insights": data, "recent_media": media}
    SOCIAL_DB.setdefault("insights", []).append(snapshot)
    SOCIAL_DB["insights"] = SOCIAL_DB["insights"][-60:]
    save_social_db()
    social_audit("instagram_analyze", {"days": days, "ok": "error" not in data and "error" not in media})
    if "error" in data or "error" in media:
        return f"Instagram analysis failed: {data.get('error') or media.get('error')}"
    best = sorted(media.get("data", []), key=lambda m: int(m.get("like_count", 0)) + int(m.get("comments_count", 0)) * 3, reverse=True)[:3]
    best_lines = [f"{m.get('media_type')} {m.get('id')}: {m.get('like_count', 0)} likes, {m.get('comments_count', 0)} comments" for m in best]
    return "Instagram performance saved. Top recent posts: " + ("; ".join(best_lines) or "no media returned")

def _social_strategy_prompt(request: str) -> str:
    cfg = social_config()
    history = SOCIAL_DB.get("posts", [])[-12:] + SOCIAL_DB.get("drafts", [])[-12:]
    return ("Create a safe Instagram content plan for a transparent AI-managed professional account. "
            "Do not claim to be human. Focus on Indian relatable content. Include caption, hashtags, visual_prompt, "
            "format (image/carousel/reel), suggested posting_time, reply_rules, and trending_audio_suggestion as text only. "
            "If music is needed, suggest audio to add manually because the official API may not expose trending audio attachment.\n"
            f"Config: {json.dumps(cfg, ensure_ascii=False)}\nHistory: {json.dumps(history, ensure_ascii=False)[:4000]}\nRequest: {request}")

def generate_social_strategy(request: str) -> dict:
    if OPENAI_API_KEY and requests:
        messages = [{"role": "system", "content": "You are Jarvis's social-media strategist. Return compact JSON only."}, {"role": "user", "content": _social_strategy_prompt(request)}]
        data, err = _call_openai(messages, max_tokens=900)
        if not err:
            raw = (data["choices"][0]["message"].get("content") or "{}").strip()
            try:
                return json.loads(raw.strip("` \n"))
            except Exception:
                return {"caption": raw[:1800], "hashtags": ["#JarvisAI", "#IndianRelatable", "#TechHumor"], "visual_prompt": request, "format": "image", "suggested_posting_time": "20:30 IST", "trending_audio_suggestion": "Pick a currently trending Instagram audio manually in-app."}
    return {"caption": f"Built by Jarvis: {request}\n\nNot human, just your AI co-pilot thinking out loud.", "hashtags": ["#JarvisAI", "#IndianRelatable", "#AIAssistant"], "visual_prompt": f"Indian relatable meme/graphic about {request}", "format": "image", "suggested_posting_time": "20:30 IST", "trending_audio_suggestion": "Pick a currently trending Instagram audio manually in-app."}

def create_instagram_post(request: str = "today's Instagram post", publish: bool = False, image_url: str = "") -> str:
    cfg = social_config()
    mode = cfg.get("mode", "APPROVAL")
    if not cfg.get("instagram_enabled"):
        return "Instagram automation is off. Say 'enter autonomous Instagram mode' or set APPROVAL/MANUAL first."
    strategy = generate_social_strategy(request)
    caption = (strategy.get("caption") or "").strip()
    hashtags = strategy.get("hashtags") or []
    if isinstance(hashtags, list):
        caption = caption + "\n\n" + " ".join(hashtags)
    draft = {"id": str(uuid.uuid4())[:8], "time": datetime.datetime.now().isoformat(timespec="seconds"), "request": request, "strategy": strategy, "caption": caption, "image_url": image_url, "status": "draft"}
    if publish and mode != "AUTONOMOUS":
        publish = False
        draft["needs_approval"] = True
    if publish and not image_url:
        draft["needs_media_url"] = True
        publish = False
    if publish:
        result = publish_instagram_media(caption, image_url)
        draft["publish_result"] = result
        draft["status"] = "published" if "Published" in result else "publish_failed"
    SOCIAL_DB.setdefault("drafts", []).append(draft)
    if draft["status"] == "published":
        SOCIAL_DB.setdefault("posts", []).append(draft)
    save_social_db()
    social_audit("instagram_create_post", {"draft_id": draft["id"], "publish_requested": publish, "status": draft["status"]})
    if draft["status"] == "published":
        return f"Published Instagram post {draft['id']}. {draft.get('publish_result')}"
    return f"Prepared Instagram draft {draft['id']} for {strategy.get('suggested_posting_time')}. Caption ready. Visual prompt: {strategy.get('visual_prompt')} Trending audio suggestion: {strategy.get('trending_audio_suggestion')}"

def publish_instagram_media(caption: str, image_url: str) -> str:
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return "Instagram publishing is not configured. Set Meta OAuth access token and IG account id."
    create = _meta_post(f"{INSTAGRAM_ACCOUNT_ID}/media", {"image_url": image_url, "caption": caption})
    if "error" in create:
        social_audit("instagram_publish_failed", {"stage": "create", "error": create["error"]})
        return f"Instagram media container failed: {create['error']}"
    creation_id = create.get("id")
    publish = _meta_post(f"{INSTAGRAM_ACCOUNT_ID}/media_publish", {"creation_id": creation_id})
    social_audit("instagram_publish", {"creation_id": creation_id, "result": publish})
    if "error" in publish:
        return f"Instagram publish failed: {publish['error']}"
    return f"Published media id {publish.get('id')}."

def show_social_history(limit: int = 10) -> str:
    posts = SOCIAL_DB.get("posts", [])[-limit:]
    drafts = SOCIAL_DB.get("drafts", [])[-limit:]
    lines = [f"Published: {len(posts)} recent, Drafts: {len(drafts)} recent."]
    for item in posts[-5:] + drafts[-5:]:
        lines.append(f"{item.get('id')} [{item.get('status')}]: {item.get('request')} @ {item.get('time')}")
    return "\n".join(lines)

def moderate_social_text(text: str) -> str:
    lowered = (text or "").lower()
    hits = [kind for kind, words in SOCIAL_MODERATION_KEYWORDS.items() if any(w in lowered for w in words)]
    return ",".join(hits) if hits else "safe"

def generate_social_reply(platform: str, incoming_text: str, sender: str = "") -> str:
    verdict = moderate_social_text(incoming_text)
    if verdict != "safe":
        social_audit("social_reply_blocked", {"platform": platform, "sender": sender, "verdict": verdict})
        return f"Blocked reply draft because message looks {verdict}."
    prompt = f"Draft a short, appropriate {platform} reply as Jarvis, an AI-managed account. Be transparent that this is AI-assisted. Message: {incoming_text}"
    strategy = generate_social_strategy(prompt)
    reply = strategy.get("caption", str(strategy))[:900]
    cfg = social_config()
    mode = cfg.get("reply_mode", "APPROVAL") if platform == "whatsapp" else cfg.get("mode", "APPROVAL")
    SOCIAL_DB.setdefault("messages", []).append({"time": datetime.datetime.now().isoformat(timespec="seconds"), "platform": platform, "sender": sender, "incoming": incoming_text, "reply": reply, "mode": mode})
    save_social_db()
    social_audit("social_reply_draft", {"platform": platform, "sender": sender, "mode": mode})
    return f"Reply draft ({mode}): {reply}"

def send_whatsapp_message(to_number: str, message: str, confirmed: bool = False) -> str:
    cfg = social_config()
    if cfg.get("reply_mode") != "AUTONOMOUS" and not confirmed:
        return "WhatsApp reply drafted only. Say confirm before sending."
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return "WhatsApp Cloud API is not configured. Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID."
    verdict = moderate_social_text(message)
    if verdict != "safe":
        return f"I won't send that WhatsApp message because it looks {verdict}."
    if not requests:
        return "The requests package is required for WhatsApp Cloud API."
    url = f"{META_GRAPH_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": message}}
    try:
        resp = requests.post(url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}, json=payload, timeout=20)
        data = resp.json()
        social_audit("whatsapp_send", {"to": to_number[-4:], "status_code": resp.status_code, "result": data})
        if resp.status_code >= 400:
            return f"WhatsApp send failed: {data.get('error', {}).get('message', resp.text)}"
        return "WhatsApp message sent through the official Cloud API."
    except Exception as e:
        return f"WhatsApp send failed: {e}"

def change_instagram_bio(new_bio: str, confirmed: bool = False) -> str:
    if not confirmed or JARVIS_CONFIG.get("social_agent", {}).get("require_approval_for_bio", True):
        social_audit("instagram_bio_approval_required", {"bio_preview": new_bio[:120]})
        return "Bio change prepared but blocked until explicit approval."
    return "Instagram bio update requires a supported Meta endpoint for this account type; I will not use private or unofficial APIs."

# ---------------------------------------------------------------------------
# NOVA'S BRAIN: tool-calling dispatch
# ---------------------------------------------------------------------------
NOVA_SYSTEM_PROMPT = """You are Jarvis, a witty, warm personal voice assistant running on the
user's Windows laptop. Reply in the SAME language/style the user used - natural casual
English for English, natural Hinglish (Hindi mixed with English, Devanagari script for the
Hindi parts) if they mixed languages, proper Hindi if they spoke Hindi.

Keep spoken replies SHORT: 1-3 sentences, warm and a little playful - this is text-to-speech,
not a document. You have TOOLS to actually control the user's computer. Use them whenever the
user is asking you to DO something, even if phrased casually or indirectly - infer the right
tool and arguments from context. You can call several tools in one turn if asked for multiple
things at once.

IMPORTANT - don't over-clarify: this is the biggest way assistants like you annoy people. For
creative or drawing requests especially, just pick a sensible default (default size, default
color, default style) and DO it rather than asking a chain of clarifying questions. Only ask a
clarifying question when the request is genuinely impossible to act on without it (e.g. "open
a website" with literally no name given) - and even then, ask ONE question, not several rounds.

If a tool returns text extracted from the screen or a PDF, relay it clearly and mostly verbatim
- the user needs the actual content, not your summary of it, unless they asked for a summary.
For everything else, don't just repeat a tool's raw output robotically - acknowledge what
happened in your own natural words. If nothing needs doing, just have a normal conversation -
jokes, opinions, whatever fits; you can refer back to things said earlier in this session.

You have a persistent personal memory/profile and should sound personalized, not generic. Use remembered preferences, routines, projects, unfinished tasks, device presence, quiet mode, and the user's communication style when relevant. You may proactively mention useful things, but never chatter without a reason.

You receive a compact local CONTEXT snapshot on each turn. Use it to resolve "this", "that",
"the second one", visible screen references, clipboard references, and recent-task follow-ups.
For screen/UI work, prefer OCR/layout and keyboard shortcuts first; use vision only when OCR is
insufficient. Never send messages, spend money, delete data, call people, change credentials/settings, mass-message, delete content, or perform sensitive actions without explicit user confirmation. For Instagram/WhatsApp, use official Meta APIs only, never claim access to private ranking algorithms, never pretend to be human, and treat collab requests as notify-the-user events."""

TOOLS = [
    {"type": "function", "function": {"name": "open_application", "description": "Open an installed desktop app by name (Chrome, Notepad, or anything found in the Start Menu).",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "close_application", "description": "Close/kill a running desktop app by name.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "open_website", "description": "Open a website in the default browser, by name (e.g. youtube, whatsapp) or domain.",
        "parameters": {"type": "object", "properties": {"site": {"type": "string"}}, "required": ["site"]}}},
    {"type": "function", "function": {"name": "web_search", "description": "Open a Google search for a query.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "play_youtube", "description": "Search YouTube for a video/song and open results.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "take_screenshot", "description": "Take and save a screenshot.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "type_text", "description": "Type text into whatever window currently has focus (e.g. a Notepad doc or a browser search box).",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "get_time", "description": "Get the current date/time.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "control_zoom", "description": "Control the Zoom desktop app.",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": [
            "open", "new_meeting", "toggle_mic", "toggle_video", "mute_all", "share_screen", "stop_share",
            "pause_resume_share", "toggle_recording", "speaker_view", "gallery_view", "toggle_chat",
            "toggle_participants", "raise_hand", "leave_meeting"]}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "control_chrome", "description": "Control Chrome via keyboard shortcuts (tabs, windows, zoom, dev tools, etc).",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": list(CHROME_HOTKEYS.keys())}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "control_volume", "description": "Adjust system volume.",
        "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down", "mute"]}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "control_media", "description": "Control media playback (play/pause/skip).",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["play_pause", "next", "previous"]}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "read_screen_text", "description": "Read the text currently visible on screen (OCR, falls back to vision if unclear).", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "analyze_screen", "description": "Ask a visual question about what's currently on screen (beyond just reading text).",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
    {"type": "function", "function": {"name": "read_pdf", "description": "Find, read, and/or analyze a PDF from Downloads/Documents by (partial) filename - use for summarizing or answering questions about a document, not just reading it aloud.",
        "parameters": {"type": "object", "properties": {"name_hint": {"type": "string"}}, "required": ["name_hint"]}}},
    {"type": "function", "function": {"name": "explain_clipboard", "description": "Get the current clipboard's text content.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "call_person", "description": "Ask the user's phone (via Telegram bridge) to call a saved contact.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "join_meeting", "description": "Open a saved Zoom meeting link by name.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "system_status", "description": "Get battery and RAM usage.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "switch_voice", "description": "Switch Jarvis's speaking voice.",
        "parameters": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["nova", "female"]}}, "required": ["mode"]}}},
    {"type": "function", "function": {"name": "open_paint", "description": "Open MS Paint, maximized and ready to draw on.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "draw_circle_paint", "description": "Draw a circle in MS Paint at the canvas center. Pick a sensible default radius (~100px) and color (black) unless the user specified otherwise - don't ask.",
        "parameters": {"type": "object", "properties": {
            "radius_px": {"type": "integer", "description": "Radius in pixels, default 100"},
            "color": {"type": "string", "enum": list(PAINT_COLOR_POSITIONS.keys())},            "filled": {"type": "boolean", "description": "Whether to fill the circle with color"}
        }}}},
    {"type": "function", "function": {"name": "draw_rectangle_paint", "description": "Draw a rectangle in MS Paint, offset from canvas center. Pick sensible defaults unless specified.",
        "parameters": {"type": "object", "properties": {
            "x_offset": {"type": "integer"}, "y_offset": {"type": "integer"},
            "width": {"type": "integer"}, "height": {"type": "integer"},
            "color": {"type": "string", "enum": list(PAINT_COLOR_POSITIONS.keys())}
        }}}},
    {"type": "function", "function": {"name": "draw_line_paint", "description": "Draw a straight line in MS Paint between two points offset from canvas center.",
        "parameters": {"type": "object", "properties": {
            "x1_off": {"type": "integer"}, "y1_off": {"type": "integer"},
            "x2_off": {"type": "integer"}, "y2_off": {"type": "integer"},
            "color": {"type": "string", "enum": ["black", "red", "green", "blue", "yellow", "white"]}
        }, "required": ["x1_off", "y1_off", "x2_off", "y2_off"]}}},
    {"type": "function", "function": {"name": "draw_scenery_paint", "description": "Draw a quick default scenery (sun, ground, house, tree) in MS Paint. Use this for vague requests like 'draw a scenery' or 'draw something nice' - don't ask what kind, just draw it.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "remember_fact", "description": "Save a fact/preference about the user permanently (e.g. their name, favorite food, a reminder) so it persists across restarts.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]}}},
    {"type": "function", "function": {"name": "recall_fact", "description": "Look up a previously saved fact about the user by key.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
        {"type": "function", "function": {"name": "list_running_apps", "description": "List apps/processes currently running, to check if something is already open before opening or closing it.",
        "parameters": {"type": "object", "properties": {}}}}, 
        {"type": "function", "function": {"name": "click_on_text", "description": "Find a piece of text/label visible on screen (a button, menu item, etc.) and click it.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
        {"type": "function", "function": {"name": "control_brightness", "description": "Adjust screen brightness up, down, or to a specific percentage.",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["up", "down", "set"]},
            "amount": {"type": "integer", "description": "Step size for up/down (default 10), or target % for set"}
        }, "required": ["direction"]}}},
        {"type": "function", "function": {"name": "get_weather", "description": "Get current weather for a city. Leave city empty to use the user's IP-based location.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "fill_area", "description": "Fill a closed shape already drawn in Paint with a solid color, using the bucket tool.",
        "parameters": {"type": "object", "properties": {
            "x_offset": {"type": "integer"}, "y_offset": {"type": "integer"},
            "color": {"type": "string", "enum": list(PAINT_COLOR_POSITIONS.keys())}
        }}}},
    {"type": "function", "function": {"name": "draw_freehand", "description": "Draw a custom shape in Paint by connecting a list of points - use for anything that isn't a plain circle/rectangle/line (stars, arrows, custom outlines).",
        "parameters": {"type": "object", "properties": {
            "points": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}, "description": "list of [x_offset, y_offset] pairs from canvas center"},
            "color": {"type": "string", "enum": list(PAINT_COLOR_POSITIONS.keys())}
        }, "required": ["points"]}}},
    {"type": "function", "function": {"name": "add_text_paint", "description": "Add text to the Paint canvas at a given position.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "x_offset": {"type": "integer"}, "y_offset": {"type": "integer"}
        }, "required": ["text"]}}},
    {"type": "function", "function": {"name": "paint_undo", "description": "Undo the last Paint action.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "paint_redo", "description": "Redo the last undone Paint action.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "clear_canvas", "description": "Clear the entire Paint canvas.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "save_paint_drawing", "description": "Save the current Paint drawing with a filename.",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "open_app_on_phone", "description": "Open an app on the connected Android phone via its package name.",
        "parameters": {"type": "object", "properties": {"package_name": {"type": "string"}}, "required": ["package_name"]}}},
    {"type": "function", "function": {"name": "phone_volume", "description": "Turn phone volume up or down.",
        "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "take_phone_screenshot", "description": "Take a screenshot on the phone and pull it to the laptop.",
        "parameters": {"type": "object", "properties": {}}}},  
    {"type": "function", "function": {"name": "play_content_on_phone", "description": "Play any requested content on the phone's YouTube - news, bhajans, music genres, workout playlists, comedy, cricket, cartoons, or anything else the user asks for by category or description. Use this instead of play_youtube_on_phone whenever the request is a general 'play/open X' rather than a specific song/video title.",
        "parameters": {"type": "object", "properties": {"request": {"type": "string", "description": "the user's raw request, e.g. 'news', 'some bhajans', 'workout music'"}}, "required": ["request"]}}},
    {"type": "function", "function": {"name": "ocr_screen_layout", "description": "Return OCR text with approximate screen coordinates for visible UI labels/buttons.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "click_ui_target", "description": "Click a visible UI target by label and verify whether the click changed active window state.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "context_snapshot", "description": "Get active window, clipboard, recent actions and current visual/task notes for reference resolution.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "system_diagnostics", "description": "Detailed CPU, RAM, storage, network and battery diagnostics.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "draft_whatsapp_reply", "description": "Prepare a safe WhatsApp reply draft for user review; never sends autonomously.",
        "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "tone": {"type": "string"}}, "required": ["message"]}}},
    {"type": "function", "function": {"name": "translate_screen_overlay", "description": "OCR visible screen text, translate it, and show a lightweight HUD overlay.",
        "parameters": {"type": "object", "properties": {"target_language": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "remember_personal_context", "description": "Store long-term profile, preference, routine, project, or fact memory.",
        "parameters": {"type": "object", "properties": {"category": {"type": "string", "enum": ["profile", "preferences", "routines", "projects", "facts"]}, "key": {"type": "string"}, "value": {"type": "string"}}, "required": ["category", "key", "value"]}}},
    {"type": "function", "function": {"name": "add_task_memory", "description": "Remember an unfinished/current task so Jarvis can continue later.",
        "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "status": {"type": "string"}}, "required": ["task"]}}},
    {"type": "function", "function": {"name": "continue_last_task", "description": "Recall where the user and Jarvis left off.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "set_quiet_mode", "description": "Enable or disable quiet mode.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}}},
    {"type": "function", "function": {"name": "set_proactive_frequency", "description": "Set proactive frequency/personality: low, balanced, high.", "parameters": {"type": "object", "properties": {"frequency": {"type": "string", "enum": ["low", "balanced", "high"]}}, "required": ["frequency"]}}},
    {"type": "function", "function": {"name": "device_status", "description": "Show Jarvis device network status/presence.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "route_device_command", "description": "Route a command to PC, phone, or future device based on capability.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "capability": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "set_social_mode", "description": "Set Instagram or WhatsApp automation mode: MANUAL, APPROVAL, AUTONOMOUS, or OFF.", "parameters": {"type": "object", "properties": {"platform": {"type": "string", "enum": ["instagram", "whatsapp"]}, "mode": {"type": "string", "enum": ["MANUAL", "APPROVAL", "AUTONOMOUS", "OFF"]}}, "required": ["platform", "mode"]}}},
    {"type": "function", "function": {"name": "create_instagram_post", "description": "Plan/create today's Instagram post, meme, carousel/reel concept, caption, hashtags, schedule and optional publish via official Graph API when autonomous and media URL are available.", "parameters": {"type": "object", "properties": {"request": {"type": "string"}, "publish": {"type": "boolean"}, "image_url": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "analyze_instagram_performance", "description": "Fetch Instagram account/media insights through the official Graph API and save performance history.", "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "show_social_history", "description": "Show recent Instagram posts/drafts stored by Jarvis.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "generate_social_reply", "description": "Draft a safe Instagram/WhatsApp DM/comment reply with spam/toxic/unsafe filtering.", "parameters": {"type": "object", "properties": {"platform": {"type": "string"}, "incoming_text": {"type": "string"}, "sender": {"type": "string"}}, "required": ["platform", "incoming_text"]}}},
    {"type": "function", "function": {"name": "send_whatsapp_message", "description": "Send a WhatsApp message using the official WhatsApp Cloud API only after confirmation or autonomous reply mode.", "parameters": {"type": "object", "properties": {"to_number": {"type": "string"}, "message": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["to_number", "message"]}}},
    {"type": "function", "function": {"name": "change_instagram_bio", "description": "Prepare a trend/audience based bio update; requires explicit approval and never changes credentials/settings.", "parameters": {"type": "object", "properties": {"new_bio": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["new_bio"]}}},

]

# Tools whose result is simple/short enough that Jarvis can just speak a plain
# confirmation directly, skipping the second GPT round-trip entirely (saves
# tokens on the common case - opening an app doesn't need an AI-written summary).
SIMPLE_ACTION_TOOLS = {
    "open_application", "close_application", "control_zoom", "control_chrome",
    "control_volume", "control_media", "take_screenshot", "switch_voice",
    "get_time", "web_search", "open_website", "play_youtube", "call_person",
    "join_meeting", "system_status", "type_text", "open_paint",
    "draw_circle_paint", "draw_rectangle_paint", "draw_line_paint", "draw_scenery_paint", "control_brightness" ,
    "get_weather", "fill_area", "draw_freehand", "add_text_paint",
    "paint_undo", "paint_redo", "clear_canvas", "save_paint_drawing", "open_app_on_phone", "phone_volume", "take_phone_screenshot", "play_youtube_on_phone",
    "play_content_on_phone", "click_ui_target", "system_diagnostics", "translate_screen_overlay", "remember_personal_context", "add_task_memory", "continue_last_task", "set_quiet_mode", "set_proactive_frequency", "device_status", "route_device_command", "set_social_mode", "create_instagram_post", "analyze_instagram_performance", "show_social_history", "generate_social_reply", "change_instagram_bio" ,
}

TOOL_FUNCTIONS = {
    "open_application": lambda a: open_application(a.get("name", "")),
    "close_application": lambda a: close_app_by_name(a.get("name", "")),
    "open_website": lambda a: open_website(a.get("site", "")),
    "web_search": lambda a: web_search(a.get("query", "")),
    "play_youtube": lambda a: play_youtube(a.get("query", "")),
    "take_screenshot": lambda a: take_screenshot(),
    "type_text": lambda a: type_text(a.get("text", "")),
    "get_time": lambda a: get_time(),
    "control_zoom": lambda a: control_zoom(a.get("action", "")),
    "control_chrome": lambda a: control_chrome(a.get("action", "")),
    "control_volume": lambda a: control_volume(a.get("direction", "")),
    "control_media": lambda a: control_media(a.get("action", "")),
    "read_screen_text": lambda a: read_screen_text(),
    "analyze_screen": lambda a: analyze_screen(a.get("question", "Describe what's on my screen.")),
    "read_pdf": lambda a: read_pdf(a.get("name_hint", "")),
    "explain_clipboard": lambda a: explain_clipboard(),
    "call_person": lambda a: call_person(a.get("name", "")),
    "join_meeting": lambda a: join_meeting(a.get("name", "")),
    "system_status": lambda a: system_status(),
    "switch_voice": lambda a: switch_voice(a.get("mode", "nova")),
    "open_paint": lambda a: open_paint(),
    "draw_circle_paint": lambda a: draw_circle_paint(a.get("radius_px", 100), a.get("color", "black"), a.get("filled", False)),
    "draw_rectangle_paint": lambda a: draw_rectangle_paint(a.get("x_offset", -150), a.get("y_offset", 0), a.get("width", 300), a.get("height", 150), a.get("color", "black")),
    "draw_line_paint": lambda a: draw_line_paint(a.get("x1_off", 0), a.get("y1_off", 0), a.get("x2_off", 100), a.get("y2_off", 0), a.get("color", "black")),
    "draw_scenery_paint": lambda a: draw_scenery_paint(),
    "remember_fact": lambda a: remember_fact(a.get("key", ""), a.get("value", "")),
    "recall_fact": lambda a: recall_fact(a.get("key", "")),
    "list_running_apps": lambda a: list_running_apps(),
    "click_on_text": lambda a: click_on_text(a.get("target", "")),
    "control_brightness": lambda a: control_brightness(a.get("direction", ""), a.get("amount", 10)),
    "get_weather": lambda a: get_weather(a.get("city", "")),
    "fill_area": lambda a: fill_area(a.get("x_offset", 0), a.get("y_offset", 0), a.get("color", "black")),
    "draw_freehand": lambda a: draw_freehand(a.get("points", []), a.get("color", "black")),
    "add_text_paint": lambda a: add_text_paint(a.get("text", ""), a.get("x_offset", 0), a.get("y_offset", 0)),
    "paint_undo": lambda a: paint_undo(),
    "paint_redo": lambda a: paint_redo(),
    "clear_canvas": lambda a: clear_canvas(),
    "save_paint_drawing": lambda a: save_paint_drawing(a.get("filename", "nova_drawing")),
    "open_app_on_phone": lambda a: open_app_on_phone(a.get("package_name", "")),
    "phone_volume": lambda a: phone_volume(a.get("direction", "")),
    "take_phone_screenshot": lambda a: take_phone_screenshot(),
    "play_youtube_on_phone": lambda a: play_youtube_on_phone(a.get("query", "")),
    "play_content_on_phone": lambda a: play_content_on_phone(a.get("request", "")),
    "ocr_screen_layout": lambda a: ocr_screen_layout(),
    "click_ui_target": lambda a: click_ui_target(a.get("target", "")),
    "context_snapshot": lambda a: context_snapshot(),
    "system_diagnostics": lambda a: system_diagnostics(),
    "draft_whatsapp_reply": lambda a: draft_whatsapp_reply(a.get("message", ""), a.get("tone", "friendly")),
    "translate_screen_overlay": lambda a: translate_screen_overlay(a.get("target_language", "Hindi")),
    "remember_personal_context": lambda a: remember_personal_context(a.get("category", "facts"), a.get("key", ""), a.get("value", "")),
    "add_task_memory": lambda a: add_task_memory(a.get("task", ""), a.get("status", "open")),
    "continue_last_task": lambda a: continue_last_task(),
    "set_quiet_mode": lambda a: set_quiet_mode(a.get("enabled", True)),
    "set_proactive_frequency": lambda a: set_proactive_frequency(a.get("frequency", "balanced")),
    "device_status": lambda a: device_status(),
    "route_device_command": lambda a: route_device_command(a.get("command", ""), a.get("capability", "")),
    "set_social_mode": lambda a: set_social_mode(a.get("platform", "instagram"), a.get("mode", "APPROVAL")),
    "create_instagram_post": lambda a: create_instagram_post(a.get("request", "today's Instagram post"), a.get("publish", False), a.get("image_url", "")),
    "analyze_instagram_performance": lambda a: analyze_instagram_performance(a.get("days", 7)),
    "show_social_history": lambda a: show_social_history(a.get("limit", 10)),
    "generate_social_reply": lambda a: generate_social_reply(a.get("platform", "instagram"), a.get("incoming_text", ""), a.get("sender", "")),
    "send_whatsapp_message": lambda a: send_whatsapp_message(a.get("to_number", ""), a.get("message", ""), a.get("confirmed", False)),
    "change_instagram_bio": lambda a: change_instagram_bio(a.get("new_bio", ""), a.get("confirmed", False)),
}


def execute_tool(name: str, args: dict) -> str:
    if name in SENSITIVE_TOOL_NAMES and not args.get("confirmed"):
        return "I need explicit confirmation before doing that sensitive action."
    if any(is_sensitive_text(str(v)) for v in (args or {}).values()) and name in {"remember_fact", "type_text", "type_on_phone"}:
        return "I will not store or type secrets such as passwords, OTPs, tokens, or card details."
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return fn(args)
    except Exception as e:
        print(f"[Tool execution error - {name}] {e}")
        return f"That action failed: {e}"


MAX_HISTORY_MESSAGES = 12  # ~6 user/assistant exchanges kept for context
CONVO_HISTORY = MEMORY_DATA["history"][-MAX_HISTORY_MESSAGES:]


def _update_history(user_text: str, reply: str):
    global CONVO_HISTORY
    CONVO_HISTORY.append({"role": "user", "content": user_text})
    CONVO_HISTORY.append({"role": "assistant", "content": reply})
    CONVO_HISTORY = CONVO_HISTORY[-MAX_HISTORY_MESSAGES:]
    save_memory()

def _call_openai(messages, tools=None, max_tokens=800):
    """One OpenAI call with automatic retry at a higher token budget if needed."""
    if not requests:
        return None, "The requests package is needed for OpenAI calls."
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": OPENAI_MODEL,
        "max_completion_tokens": max_tokens,
        "reasoning_effort": "low",
        "messages": messages,
    }
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    def _post():
        return requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)

    resp = _post()
    data = resp.json()
    if resp.status_code != 200:
        err = data.get("error", {}).get("message", resp.text)
        if "max_tokens" in err.lower() or "output limit" in err.lower():
            payload["max_completion_tokens"] = max_tokens * 2
            resp = _post()
            data = resp.json()
            if resp.status_code != 200:
                return None, data.get("error", {}).get("message", resp.text)
            return data, None
        return None, err

    choice = data["choices"][0]
    if choice.get("finish_reason") == "length" and not choice["message"].get("tool_calls"):
        payload["max_completion_tokens"] = max_tokens * 2
        resp = _post()
        data = resp.json()
        if resp.status_code != 200:
            return None, data.get("error", {}).get("message", resp.text)
    return data, None

def think_and_act(user_text: str) -> str:
    """Jarvis's brain: send the user's natural-language input (plus recent
    conversation history) to GPT-5-mini with tool definitions. The model
    decides whether to call tool(s), and Python executes whatever it picks."""
    if not OPENAI_API_KEY:
        return "I need an OpenAI API key set (OPENAI_API_KEY) before I can think."

    messages = [{"role": "system", "content": NOVA_SYSTEM_PROMPT}, {"role": "system", "content": "CONTEXT: " + context_snapshot()}] + CONVO_HISTORY + [
        {"role": "user", "content": user_text}
    ]

    try:
        data, err = _call_openai(messages, tools=TOOLS, max_tokens=800)
        if err:
            print(f"[OpenAI error] {err}")
            return f"I hit an API error: {err}"

        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            reply = (msg.get("content") or "").strip() or "..."
            _update_history(user_text, reply)
            return reply

        # Execute every tool call the model requested.
        messages.append(msg)
        results = []
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}
            result = execute_tool(fn_name, args)
            remember_session_note("recent_actions", f"{fn_name}({args}) -> {result}")
            results.append((fn_name, result))
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})

        # Cost-saving shortcut: if every tool called was a "simple action"
        # (open an app, adjust volume, draw a shape, etc.), just speak a
        # plain confirmation directly - no need to spend a second GPT call
        # asking the model to "summarize" something this straightforward.
        only_simple = all(name in SIMPLE_ACTION_TOOLS for name, _ in results)
        if only_simple and len(results) <= 2:
            reply = " ".join(str(r) for _, r in results)
            _update_history(user_text, reply)
            return reply

        # Otherwise (screen/PDF/clipboard content involved, or several
        # actions at once) get the model to weave the results into one
        # natural spoken reply.
        data2, err2 = _call_openai(messages, tools=None, max_tokens=500)
        if err2:
            reply = "Done - though I had trouble summarizing that."
        else:
            reply = (data2["choices"][0]["message"].get("content") or "").strip() or "Done."

        _update_history(user_text, reply)
        return reply

    except Exception as e:
        print(f"[think_and_act error] {e}")
        return "Sorry, I hit a snag processing that."


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
WAKE_WORDS = ["jarvis", "जार्विस", "jervis", "jarves"]
WAKE_PHRASES = ["wake up jarvis", "jarvis wake up", "wake up", "jarvis utho", "जार्विस उठो"]
SILENT_ROUNDS_BEFORE_SLEEP = 4
ACTIVE_CONVERSATION_SECONDS = 45

def extract_wake_command(text: str):
    lowered = (text or "").lower().strip()
    for word in WAKE_WORDS:
        if lowered == word or lowered.startswith(word + " ") or (word in lowered and any(p in lowered for p in WAKE_PHRASES)):
            return lowered.replace(word, "", 1).strip(" ,:-")
    return None

# ---------------------------------------------------------------------------
# PROACTIVE BEHAVIOR (Jarvis speaks up without being asked)
# ---------------------------------------------------------------------------
def _already_said_today(key: str) -> bool:
    return _proactive_said_today.get(key) == datetime.date.today().isoformat()

def _mark_said_today(key: str):
    _proactive_said_today[key] = datetime.date.today().isoformat()

def check_battery_proactive():
    if not psutil or not JARVIS_CONFIG.get("proactive_enabled", True):
        return
    batt = psutil.sensors_battery()
    if batt and not batt.power_plugged and batt.percent <= 15 and not _already_said_today("low_battery"):
        speak(f"{JARVIS_CONFIG.get('preferred_name', 'boss').title()}, your laptop battery is at {int(batt.percent)} percent. Might want to plug in.", force=True)
        _mark_said_today("low_battery")

def check_morning_greeting():
    if not JARVIS_CONFIG.get("proactive_enabled", True) or JARVIS_CONFIG.get("quiet_mode"):
        return
    hour = datetime.datetime.now().hour
    if 6 <= hour < 11 and JARVIS_CONFIG.get("proactive_frequency") != "low" and not _already_said_today("morning"):
        speak("Morning. I'm running quietly in the background if you need anything.")
        _mark_said_today("morning")

PROACTIVE_CHECKS = [check_battery_proactive, check_morning_greeting]

def proactive_watcher():
    while True:
        time.sleep(120)  # check every 2 min - frequent enough to matter, not nagging
        if AUDIO_LOCK.locked():
            continue  # you're mid-conversation, don't interrupt
        for check in PROACTIVE_CHECKS:
            try:
                check()
            except Exception as e:
                print(f"[Proactive check error] {e}")

def main():
    global DICTATION_MODE
    ensure_autostart()
    update_device_presence(socket.gethostname(), "pc", "online", ["computer_control", "voice", "memory", "screen", "files"])
    threading.Thread(target=awareness_watcher, daemon=True).start()
    briefing = morning_briefing()
    if "--background" in sys.argv or JARVIS_CONFIG.get("background_mode", True):
        set_status("sleeping", "background ready")
        print(f"Jarvis background online. {briefing}")
    else:
        speak(f"Hi boss! {briefing} Jarvis online - just talk to me normally.")

    asleep = True
    last_active_at = 0
    silent_rounds = 0
    threading.Thread(target=proactive_watcher, daemon=True).start()
    while True:
        text = listen()

        if not text:
            silent_rounds += 1
            if not asleep and (silent_rounds >= SILENT_ROUNDS_BEFORE_SLEEP or time.time() - last_active_at > ACTIVE_CONVERSATION_SECONDS):
                asleep = True
                set_status("sleeping", "say Jarvis")
                if not JARVIS_CONFIG.get("quiet_mode"):
                    speak("Going quiet. Say Jarvis when you need me.")
            continue

        silent_rounds = 0

        wake_command = extract_wake_command(text)
        if asleep:
            if wake_command is not None:
                asleep = False
                last_active_at = time.time()
                set_status("listening")
                if wake_command:
                    text = wake_command
                else:
                    speak("At your service.")
                    continue
            else:
                continue
        else:
            last_active_at = time.time()

        # Instant, zero-API-cost meta controls
        if text.strip() in ("stop", "exit", "quit", "goodbye jarvis"):
            speak("Okay, bye!")
            save_memory()
            sys.exit(0)

        if text.strip() == "undo" or text.strip().startswith("undo"):
            speak(undo_last_action())
            continue

        if any(p in text for p in DICTATION_START_PHRASES):
            DICTATION_MODE = True
            open_application("notepad")
            time.sleep(1.5)
            speak("Opened Notepad. Dictation on — say 'stop dictation' when done.")
            continue

        if DICTATION_MODE:
            if any(p in text for p in DICTATION_STOP_PHRASES):
                DICTATION_MODE = False
                speak("Dictation off.")
                continue
            type_text(text + " ")  # trailing space so sentences don't run together
            continue

        lowered_text = text.strip().lower()
        if lowered_text in ("i'm leaving", "im leaving", "jarvis i'm leaving", "i am leaving"):
            set_quiet_mode(True)
            add_task_memory("User stepped away; resume the previous context when they return.")
            speak("Got it. Quiet mode on, and I'll remember where we left off.", force=True)
            continue
        if lowered_text in ("i'm going to sleep", "im going to sleep", "good night", "going to sleep"):
            set_quiet_mode(True)
            speak("Good night. I'll stay quiet and keep the essentials watched.", force=True)
            continue
        if "where did we leave off" in lowered_text or "continue what we were doing" in lowered_text:
            speak(continue_last_task(), force=True)
            continue

        # Everything else goes through Jarvis's brain
        set_status("thinking")
        reply = think_and_act(text)
        set_status("success" if not reply.lower().startswith(("sorry", "i hit", "that action failed")) else "failure")
        speak(reply)


if __name__ == "__main__":
    main()
