import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import psycopg
from fastapi import FastAPI, Header, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

APP_NAME = "Jarvis Cloud"
DB_PATH = Path(os.getenv("JARVIS_CLOUD_DB", "./jarvis_cloud.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DEVICE_SECRET = os.getenv("JARVIS_CLOUD_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FAST_MODEL = os.getenv("JARVIS_FAST_MODEL", "gpt-5.4-nano")
REASONING_MODEL = os.getenv("JARVIS_REASONING_MODEL", "gpt-5.4-mini")
DEFAULT_MODEL = os.getenv("JARVIS_CLOUD_MODEL", REASONING_MODEL)
WEB_SEARCH_SIZE = os.getenv("JARVIS_WEB_SEARCH_CONTEXT", "medium")
OWNER_SCOPE = os.getenv("JARVIS_OWNER_ID", "owner")

if not DEVICE_SECRET:
    raise RuntimeError("JARVIS_CLOUD_SECRET is required")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is required")

client = OpenAI(api_key=OPENAI_API_KEY)
app = FastAPI(title=APP_NAME)


def _sql(query: str) -> str:
    return query.replace("?", "%s") if DATABASE_URL else query


def _connect():
    if DATABASE_URL:
        return psycopg.connect(DATABASE_URL)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute(_sql("CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at BIGINT NOT NULL)"))
        conn.execute(_sql("CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, last_seen BIGINT NOT NULL)"))
        conn.execute(_sql("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)"))


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


def memory_snapshot(limit: int = 50):
    with db() as conn:
        rows = conn.execute(_sql("SELECT key,value FROM memory ORDER BY updated_at DESC LIMIT ?"), (limit,)).fetchall()
    return {row[0]: row[1] for row in rows}


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
            blocked = (
                "password", "passcode", "otp", "api key", "apikey", "secret",
                "credit card", "card number", "cvv", "bank account", "ifsc",
                "private key", "token"
            )
            if any(term in lowered for term in blocked):
                continue
            now = int(time.time())
            conn.execute(
                _sql("INSERT INTO memory(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at"),
                (key, value, now),
            )
            saved.append(key)
    return saved


def get_or_create_session(session_id: Optional[str], device_id: str) -> str:
    sid = session_id or secrets.token_urlsafe(18)
    now = int(time.time())
    with db() as conn:
        existing = conn.execute(_sql("SELECT session_id FROM sessions WHERE session_id=?"), (sid,)).fetchone()
        if existing:
            conn.execute(_sql("UPDATE sessions SET updated_at=? WHERE session_id=?"), (now, sid))
        else:
            conn.execute(_sql("INSERT INTO sessions(session_id,device_id,created_at,updated_at) VALUES(?,?,?,?)"), (sid, device_id, now, now))
    return sid


def needs_web_search(message: str) -> bool:
    text = message.lower()
    patterns = (
        r"\btoday\b", r"\btonight\b", r"\byesterday\b", r"\btomorrow\b", r"\blatest\b",
        r"\bcurrent\b", r"\brecent\b", r"\bnews\b", r"\bheadline", r"\bheadlines\b",
        r"\bwhat happened\b", r"\bwhat's happening\b", r"\bweather\b", r"\bscore\b",
        r"\bresults\b", r"\btrending\b", r"\bmarket\b", r"\bprice\b", r"\bupdate\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def choose_model(message: str, web: bool) -> str:
    words = re.findall(r"\b\w+\b", message)
    simple = len(words) <= 6 and not web and not any(
        term in message.lower() for term in ("debug", "explain", "compare", "plan", "why", "how", "remember")
    )
    return FAST_MODEL if simple else (REASONING_MODEL or DEFAULT_MODEL)


def cloud_brain(message: str, memories: dict) -> dict:
    web = needs_web_search(message)
    model = choose_model(message, web)
    system = (
        "You are Jarvis, a capable private personal AI for the user's phone and PC. "
        "Return ONLY valid JSON with keys mode, reply, and memory_updates. mode must be exactly 'chat' or 'pc_action'. "
        "Use pc_action when the user asks to open/control/debug/read/change something on the Windows PC or anything requiring local files, apps, mouse, keyboard, OCR, screen vision, or other PC-only tools. "
        "Use chat for normal conversation, planning, memory discussion, social-media discussion, translation, general explanation, and current-information questions. "
        "Answer first. Do not ask follow-up questions when the request is answerable with sensible defaults. Ask at most one clarifying question only when the missing detail makes the task genuinely impossible or unsafe. "
        "Never produce a questionnaire. Never make the user repeat information already present in long-term memory. "
        "For current, latest, today's, news, headlines, weather, prices, results, or other time-sensitive questions, use web search when available and provide the actual answer rather than saying you cannot access current information. "
        "When web results are available, synthesize them and distinguish confirmed facts from uncertainty. "
        "Speak like a confident, concise personal AI: direct, composed, slightly witty, not customer-service-like. "
        "Do not over-apologize. Do not narrate internal reasoning. "
        "If the user asks for a large answer, give the useful answer completely but structure it with short sections or bullets. "
        "memory_updates must be an array. Store ONLY stable personal details/preferences/facts the user explicitly asks Jarvis to remember, or clearly stable profile statements. "
        "Never store passwords, OTPs, API keys, tokens, financial credentials, private authentication data, or transient conversation. "
        "Each memory entry must be {\"key\": \"short_key\", \"value\": \"remembered_fact\"}; maximum 5 entries."
    )
    prompt = (
        f"OWNER SCOPE: {OWNER_SCOPE}\n"
        f"LONG-TERM MEMORY:\n{json.dumps(memories, ensure_ascii=False)}\n\n"
        f"USER:\n{message}"
    )

    request_kwargs = {
        "model": model,
        "instructions": system,
        "input": prompt,
        "verbosity": "medium",
    }
    if model != FAST_MODEL:
        request_kwargs["reasoning_effort"] = "medium"
    if web:
        request_kwargs["tools"] = [{"type": "web_search", "search_context_size": WEB_SEARCH_SIZE}]

    response = client.responses.create(**request_kwargs)
    raw = (response.output_text or "").strip()
    try:
        parsed = json.loads(raw)
        if parsed.get("mode") not in {"chat", "pc_action"}:
            raise ValueError("invalid mode")
        updates = parsed.get("memory_updates", [])
        if not isinstance(updates, list):
            updates = []
        return {
            "mode": parsed["mode"],
            "reply": str(parsed.get("reply", "")),
            "memory_updates": updates[:5],
            "model": model,
            "web_search": web,
        }
    except Exception:
        return {
            "mode": "chat",
            "reply": raw or "I'm here, boss.",
            "memory_updates": [],
            "model": model,
            "web_search": web,
        }


@app.get("/")
def root():
    return {"service": APP_NAME, "status": "online", "model": DEFAULT_MODEL}


@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME, "timestamp": int(time.time()), "persistent_db": bool(DATABASE_URL)}


@app.post("/device/heartbeat")
def heartbeat(payload: DeviceHeartbeat, authorization: Optional[str] = Header(default=None)):
    authenticate(authorization.replace("Bearer ", "", 1) if authorization else None)
    now = int(time.time())
    with db() as conn:
        conn.execute(
            _sql("INSERT INTO devices(device_id,kind,status,last_seen) VALUES(?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET kind=excluded.kind,status=excluded.status,last_seen=excluded.last_seen"),
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
        "model": result.get("model"),
        "web_search": result.get("web_search", False),
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
