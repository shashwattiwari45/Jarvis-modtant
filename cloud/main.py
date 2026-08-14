import os
import sqlite3
import time
import secrets
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

APP_NAME = "Jarvis Cloud"
DB_PATH = Path(os.getenv("JARVIS_CLOUD_DB", "./jarvis_cloud.db"))
DEVICE_SECRET = os.getenv("JARVIS_CLOUD_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("JARVIS_CLOUD_MODEL", "gpt-5-mini")

if not DEVICE_SECRET:
    raise RuntimeError("JARVIS_CLOUD_SECRET is required")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is required")

client = OpenAI(api_key=OPENAI_API_KEY)
app = FastAPI(title=APP_NAME)


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, last_seen INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
        db.commit()


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


init_db()


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    session_id: Optional[str] = None


class DeviceHeartbeat(BaseModel):
    device_id: str
    kind: str = "pc"


class MemoryRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)


def authenticate(token: Optional[str]):
    if not token or not secrets.compare_digest(token, DEVICE_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_or_create_session(session_id: Optional[str], device_id: str) -> str:
    sid = session_id or secrets.token_urlsafe(18)
    now = int(time.time())
    with db() as conn:
        existing = conn.execute("SELECT session_id FROM sessions WHERE session_id=?", (sid,)).fetchone()
        if existing:
            conn.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (now, sid))
        else:
            conn.execute("INSERT INTO sessions(session_id,device_id,created_at,updated_at) VALUES(?,?,?,?)", (sid, device_id, now, now))
    return sid


def memory_snapshot(limit: int = 30):
    with db() as conn:
        rows = conn.execute("SELECT key,value FROM memory ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return {k: v for k, v in rows}


def save_memory_updates(updates):
    saved = []
    if not isinstance(updates, list):
        return saved
    with db() as conn:
        for item in updates[:5]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()[:200]
            value = str(item.get("value", "")).strip()[:4000]
            if not key or not value:
                continue
            lowered = f"{key} {value}".lower()
            if any(term in lowered for term in ("password", "passcode", "otp", "api key", "secret", "credit card", "bank account")):
                continue
            now = int(time.time())
            conn.execute(
                "INSERT INTO memory(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, value, now),
            )
            saved.append(key)
    return saved


def cloud_brain(message: str, memories: dict) -> dict:
    system = (
        "You are Jarvis Cloud, the shared personal AI brain for the user's phone and PC. "
        "Return ONLY valid JSON with keys mode, reply, and memory_updates. mode must be exactly 'chat' or 'pc_action'. "
        "Use 'pc_action' when the user asks to open/control/debug/read/change something on the Windows PC, "
        "or any task that needs local files, applications, mouse, keyboard, OCR, screen vision, or other PC-only tools. "
        "Use 'chat' for normal conversation, planning, memory discussion, social-media discussion, weather discussion, "
        "translation questions, or anything that can be answered without direct PC access. "
        "For pc_action, reply should briefly acknowledge and say the PC agent will execute it. "
        "For chat, answer naturally, directly, confidently and concisely with a subtle Jarvis-style wit; do not sound like customer support. "
        "memory_updates must be an array. Add entries ONLY for stable personal details/preferences/facts the user explicitly asks you to remember, "
        "or clear stable profile statements such as a preferred voice or how they want Jarvis to address them. "
        "Do not store secrets, passwords, OTPs, API keys, financial credentials, transient requests, or ordinary conversation. "
        "Each entry must be {\"key\": \"short_key\", \"value\": \"remembered_fact\"}. Use at most 5 entries."
    )
    prompt = f"LONG-TERM MEMORY:\n{json.dumps(memories, ensure_ascii=False)}\n\nUSER:\n{message}"
    response = client.responses.create(model=MODEL, instructions=system, input=prompt)
    raw = (response.output_text or "").strip()
    try:
        parsed = json.loads(raw)
        if parsed.get("mode") not in {"chat", "pc_action"}:
            raise ValueError("invalid mode")
        updates = parsed.get("memory_updates", [])
        if not isinstance(updates, list):
            updates = []
        return {"mode": parsed["mode"], "reply": str(parsed.get("reply", "")), "memory_updates": updates[:5]}
    except Exception:
        return {"mode": "chat", "reply": raw or "I'm here, boss.", "memory_updates": []}


@app.get("/")
def root():
    return {"service": APP_NAME, "status": "online", "model": MODEL}


@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME, "timestamp": int(time.time())}


@app.post("/device/heartbeat")
def heartbeat(payload: DeviceHeartbeat, authorization: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    now = int(time.time())
    with db() as conn:
        conn.execute(
            "INSERT INTO devices(device_id,kind,status,last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(device_id) DO UPDATE SET kind=excluded.kind,status=excluded.status,last_seen=excluded.last_seen",
            (payload.device_id, payload.kind, "online", now),
        )
    return {"ok": True, "device_id": payload.device_id, "status": "online", "timestamp": now}


@app.post("/ask")
def ask(payload: AskRequest, authorization: Optional[str] = Header(default=None), x_device_id: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    if not x_device_id:
        raise HTTPException(status_code=400, detail="X-Device-ID header is required")
    sid = get_or_create_session(payload.session_id, x_device_id)
    result = cloud_brain(payload.message, memory_snapshot())
    saved_keys = save_memory_updates(result.get("memory_updates", []))
    return {
        "ok": True,
        "session_id": sid,
        "mode": result["mode"],
        "reply": result["reply"],
        "device_id": x_device_id,
        "memory_saved": saved_keys,
    }


@app.get("/memory")
def get_memory(authorization: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    return {"memory": memory_snapshot()}


@app.post("/memory")
def set_memory(payload: MemoryRequest, authorization: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    saved = save_memory_updates([{"key": payload.key, "value": payload.value}])
    if not saved:
        raise HTTPException(status_code=400, detail="Memory value rejected")
    return {"ok": True, "key": payload.key}
