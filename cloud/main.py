import os
import sqlite3
import time
import secrets
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


def cloud_brain(message: str, memories: dict) -> str:
    system = (
        "You are Jarvis, the user's personal AI. You are the cloud brain shared by the user's phone and PC. "
        "Be concise, natural, and personalized. The cloud can handle conversation, memory, reminders, weather, "
        "social-media strategy, and routing. Never claim the cloud can directly control a Windows PC unless a connected "
        "PC agent is present. If a request requires a device, clearly identify the required device."
    )
    prompt = f"LONG-TERM MEMORY:\n{memories}\n\nUSER:\n{message}"
    response = client.responses.create(model=MODEL, instructions=system, input=prompt)
    return response.output_text.strip()


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
    answer = cloud_brain(payload.message, memory_snapshot())
    return {"ok": True, "session_id": sid, "reply": answer, "device_id": x_device_id}


@app.get("/memory")
def get_memory(authorization: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    return {"memory": memory_snapshot()}


@app.post("/memory")
def set_memory(payload: MemoryRequest, authorization: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    with db() as conn:
        conn.execute("INSERT INTO memory(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (payload.key, payload.value, int(time.time())))
    return {"ok": True, "key": payload.key}
