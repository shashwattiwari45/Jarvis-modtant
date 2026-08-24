"""
JARVIS - AI Voice Assistant (Tool-Calling Architecture)
------------------------------------------------------
Jarvis no longer works by matching your sentence against a big list of fixed
trigger phrases. Instead, every non-trivial thing you say goes to GPT-5-mini,
which decides - using OpenAI's function/tool calling - which action(s) to run
(if any), with what parameters, based on natural phrasing. It also keeps a
short rolling memory of the conversation, so it's a real back-and-forth, not
a stateless command parser.
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
    _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
except ImportError:
    _whisper_model = None

import tkinter as tk

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda: None
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / "web_ui" / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if OpenAI else None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-5-mini"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
STT_LANGUAGES = ["en-IN", "hi-IN"]
VOICE_NOVA = "en-GB-RyanNeural"
VOICE_FEMALE = "en-US-AvaNeural"
VOICE_HINDI_MALE = "hi-IN-MadhurNeural"
VOICE_HINDI_FEMALE = "hi-IN-SwaraNeural"
CURRENT_VOICE_MODE = "nova"
SPEAK_LANGUAGE = os.getenv("JARVIS_SPEAK_LANGUAGE", "hi").strip().lower()
DICTATION_MODE = False
DICTATION_START_PHRASES = ["start dictation", "start typing", "dictation mode on"]
DICTATION_STOP_PHRASES = ["stop dictation", "stop typing", "dictation mode off"]
LAST_ACTION = None
CURRENT_LANG = "en-IN"
AUDIO_LOCK = threading.Lock()
_proactive_said_today = {}
SMART_WEB_APPS = {"whatsapp":"https://web.whatsapp.com","youtube":"https://www.youtube.com","gmail":"https://mail.google.com","email":"https://mail.google.com","chatgpt":"https://chatgpt.com","instagram":"https://www.instagram.com","github":"https://github.com","linkedin":"https://www.linkedin.com","canva":"https://www.canva.com","spotify web":"https://open.spotify.com"}
_TESSERACT_CANDIDATES = [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
if pytesseract:
    for _cand in _TESSERACT_CANDIDATES:
        if os.path.exists(_cand):
            pytesseract.pytesseract.tesseract_cmd = _cand
            break
PDF_SEARCH_DIRS = [os.path.join(os.path.expanduser("~"), "Downloads"), os.path.join(os.path.expanduser("~"), "Documents")]
APP_SEARCH_DIRS = [r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs", os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
APP_INDEX_REFRESH_SECONDS = 300
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CONTACTS = {}
ZOOM_LINKS = {}
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
def _is_hindi_text(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))

# ... existing core.py code remains unchanged below ...
