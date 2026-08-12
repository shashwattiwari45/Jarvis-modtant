"""
NOVA - AI Voice Assistant (Tool-Calling Architecture)
------------------------------------------------------
Nova no longer works by matching your sentence against a big list of fixed
trigger phrases. Instead, every non-trivial thing you say goes to GPT-5-mini,
which decides - using OpenAI's function/tool calling - which action(s) to run
(if any), with what parameters, based on natural phrasing. It also keeps a
short rolling memory of the conversation, so it's a real back-and-forth, not
a stateless command parser.

Only two things are still handled instantly, without an API call at all:
  - "stop" / "exit" / "quit"          -> quits immediately, no network round trip
  - sleep / "wake up nova" handling   -> pure local state, zero cost

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

import speech_recognition as sr
import requests
from PIL import ImageGrab

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

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
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
    remote = "/sdcard/nova_screenshot.png"
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
            pygame.time.wait(20)
        pygame.mixer.music.unload()
    except Exception as err:
        print(f"[Audio Error] {err}")
    finally:
        
        try:
            os.remove(temp_path)
        except Exception:
            pass


def speak(text: str):
    print(f"Nova: {text}")
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
recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.7
recognizer.non_speaking_duration = 0.4
recognizer.dynamic_energy_threshold = True
recognizer.dynamic_energy_adjustment_damping = 0.15
recognizer.dynamic_energy_ratio = 1.5


def listen() -> str:
    global CURRENT_LANG
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
# PERSISTENT MEMORY (survives closing/reopening Nova)
# ---------------------------------------------------------------------------
MEMORY_FILE = os.path.join(os.path.expanduser("~"), "nova_memory.json")


def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("facts", {})
                data.setdefault("history", [])
                return data
        except Exception as e:
            print(f"[Memory load error] {e}")
    return {"facts": {}, "history": []}


def save_memory():
    try:
        MEMORY_DATA["history"] = CONVO_HISTORY
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(MEMORY_DATA, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memory save error] {e}")


MEMORY_DATA = load_memory()


def remember_fact(key: str, value: str) -> str:
    MEMORY_DATA["facts"][key.strip().lower()] = value
    save_memory()
    return f"Got it, I'll remember that {key} is {value}."


def recall_fact(key: str) -> str:
    value = MEMORY_DATA["facts"].get(key.strip().lower())
    if value:
        return f"{key}: {value}"
    return f"I don't have anything saved for '{key}'."


# ---------------------------------------------------------------------------
# APP AUTO-DETECTION, OPEN/CLOSE (stripped of internal speech - just do the
# thing and return a plain description; Nova's model composes the spoken reply)
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
    folder = os.path.join(os.path.expanduser("~"), "Pictures", "NovaScreenshots")
    os.makedirs(folder, exist_ok=True)
    filename = datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = os.path.join(folder, filename)
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
    img = ImageGrab.grab()
    img.thumbnail((1280, 720))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def analyze_screen(question: str = "Describe what's on my screen briefly.") -> str:
    if not OPENAI_API_KEY:
        return "Need an OpenAI API key set up to analyze the screen."
    try:
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
    is - needed before Nova can click on it."""
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

# ---------------------------------------------------------------------------
# PHONE BRIDGE - LAPTOP CONTROLS PHONE (via ADB over WiFi)
# ---------------------------------------------------------------------------
PHONE_IP = os.environ.get("PHONE_ADB_IP", "")  # set once you know your phone's local IP, e.g. "192.168.1.42:5555"

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
    # package_name examples: "com.whatsapp", "com.google.android.youtube"
    _adb("monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1")
    return f"Opened {package_name} on your phone."

def phone_volume(direction: str) -> str:
    key = "24" if direction == "down" else "25"  # KEYCODE_VOLUME_DOWN/UP
    _adb("input", "keyevent", key)
    return f"Turned phone volume {direction}."

def take_phone_screenshot() -> str:
    if not PHONE_IP:
        return "Phone IP isn't configured."
    remote = "/sdcard/nova_screenshot.png"
    local = os.path.join(os.path.expanduser("~"), "Pictures", "phone_screenshot.png")
    _adb("screencap", "-p", remote)
    subprocess.run(["adb", "-s", PHONE_IP, "pull", remote, local], capture_output=True, timeout=15)
    os.startfile(local)
    return "Grabbed a screenshot from your phone."

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
# NOVA'S BRAIN: tool-calling dispatch
# ---------------------------------------------------------------------------
NOVA_SYSTEM_PROMPT = """You are Nova, a witty, warm personal voice assistant running on the
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
jokes, opinions, whatever fits; you can refer back to things said earlier in this session."""

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
    {"type": "function", "function": {"name": "switch_voice", "description": "Switch Nova's speaking voice.",
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
]

# Tools whose result is simple/short enough that Nova can just speak a plain
# confirmation directly, skipping the second GPT round-trip entirely (saves
# tokens on the common case - opening an app doesn't need an AI-written summary).
SIMPLE_ACTION_TOOLS = {
    "open_application", "close_application", "control_zoom", "control_chrome",
    "control_volume", "control_media", "take_screenshot", "switch_voice",
    "get_time", "web_search", "open_website", "play_youtube", "call_person",
    "join_meeting", "system_status", "type_text", "open_paint",
    "draw_circle_paint", "draw_rectangle_paint", "draw_line_paint", "draw_scenery_paint", "control_brightness" ,
    "get_weather", "fill_area", "draw_freehand", "add_text_paint",
    "paint_undo", "paint_redo", "clear_canvas", "save_paint_drawing", "open_app_on_phone", "phone_volume", "take_phone_screenshot", "play_youtube_on_phone"
    "play_content_on_phone" ,
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
}


def execute_tool(name: str, args: dict) -> str:
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
    """One OpenAI call with automatic retry at a higher token budget if the
    model got cut off mid-response (gpt-5-mini's reasoning can eat into the
    budget before it even gets to the visible answer)."""
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

    resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
    data = resp.json()

    if resp.status_code != 200:
        err = data.get("error", {}).get("message", resp.text)
        # Truncated-output errors are recoverable - just retry once with more room.
        if "max_tokens" in err.lower() or "output limit" in err.lower():
            payload["max_completion_tokens"] = max_tokens * 2
            resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
            data = resp.json()
            if resp.status_code != 200:
                return None, data.get("error", {}).get("message", resp.text)
            return data, None
        return None, err

    choice = data["choices"][0]
    if choice.get("finish_reason") == "length" and not choice["message"].get("tool_calls"):
        # Ran out of room without actually finishing - retry with double budget.
        payload["max_completion_tokens"] = max_tokens * 2
        resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
        data = resp.json()
        if resp.status_code != 200:
            return None, data.get("error", {}).get("message", resp.text)

    return data, None


def think_and_act(user_text: str) -> str:
    """Nova's brain: send the user's natural-language input (plus recent
    conversation history) to GPT-5-mini with tool definitions. The model
    decides whether to call tool(s), and Python executes whatever it picks."""
    if not OPENAI_API_KEY:
        return "I need an OpenAI API key set (OPENAI_API_KEY) before I can think."

    messages = [{"role": "system", "content": NOVA_SYSTEM_PROMPT}] + CONVO_HISTORY + [
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
WAKE_PHRASES = ["wake up nova", "nova wake up", "wake up", "nova utho"]
SILENT_ROUNDS_BEFORE_SLEEP = 4

# ---------------------------------------------------------------------------
# PROACTIVE BEHAVIOR (Nova speaks up without being asked)
# ---------------------------------------------------------------------------
def _already_said_today(key: str) -> bool:
    return _proactive_said_today.get(key) == datetime.date.today().isoformat()

def _mark_said_today(key: str):
    _proactive_said_today[key] = datetime.date.today().isoformat()

def check_battery_proactive():
    if not psutil:
        return
    batt = psutil.sensors_battery()
    if batt and not batt.power_plugged and batt.percent <= 15 and not _already_said_today("low_battery"):
        speak(f"Your battery's at {int(batt.percent)} percent. Might want to plug in.")
        _mark_said_today("low_battery")

def check_morning_greeting():
    hour = datetime.datetime.now().hour
    if 6 <= hour < 11 and not _already_said_today("morning"):
        speak("Morning. I'm up and listening if you need anything.")
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
    briefing = morning_briefing()
    speak(f"Hi boss! {briefing} Nova's online - just talk to me normally.")

    asleep = False
    silent_rounds = 0
    threading.Thread(target=proactive_watcher, daemon=True).start()
    while True:
        text = listen()

        if not text:
            silent_rounds += 1
            if not asleep and silent_rounds >= SILENT_ROUNDS_BEFORE_SLEEP:
                asleep = True
                speak("Going to sleep. Say 'wake up nova' when you need me.")
            continue

        silent_rounds = 0

        if asleep:
            if any(w in text for w in WAKE_PHRASES):
                asleep = False
                speak("Yeah, I'm listening!")
            continue

        # Instant, zero-API-cost meta controls
        if text.strip() in ("stop", "exit", "quit", "goodbye nova"):
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

        # Everything else goes through Nova's brain
        reply = think_and_act(text)
        speak(reply)


if __name__ == "__main__":
    main()
