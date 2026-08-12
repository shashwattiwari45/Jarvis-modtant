import os
import socket
import time
from typing import Optional

import requests

CLOUD_URL = os.getenv("JARVIS_CLOUD_URL", "").rstrip("/")
CLOUD_SECRET = os.getenv("JARVIS_CLOUD_SECRET", "")
DEVICE_ID = os.getenv("JARVIS_DEVICE_ID", socket.gethostname())


def configured() -> bool:
    return bool(CLOUD_URL and CLOUD_SECRET)


def _headers() -> dict:
    if not configured():
        raise RuntimeError("Set JARVIS_CLOUD_URL and JARVIS_CLOUD_SECRET")
    return {"Authorization": f"Bearer {CLOUD_SECRET}", "X-Device-ID": DEVICE_ID}


def heartbeat(kind: str = "pc") -> bool:
    try:
        r = requests.post(f"{CLOUD_URL}/device/heartbeat", json={"device_id": DEVICE_ID, "kind": kind}, headers=_headers(), timeout=10)
        return r.ok
    except requests.RequestException as exc:
        print(f"[Cloud heartbeat] {exc}")
        return False


def ask_cloud(message: str, session_id: Optional[str] = None) -> Optional[dict]:
    try:
        payload = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        r = requests.post(f"{CLOUD_URL}/ask", json=payload, headers=_headers(), timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        print(f"[Cloud ask] {exc}")
        return None


def get_memory() -> dict:
    try:
        r = requests.get(f"{CLOUD_URL}/memory", headers=_headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("memory", {})
    except requests.RequestException as exc:
        print(f"[Cloud memory] {exc}")
        return {}


def set_memory(key: str, value: str) -> bool:
    try:
        r = requests.post(f"{CLOUD_URL}/memory", json={"key": key, "value": value}, headers=_headers(), timeout=15)
        return r.ok
    except requests.RequestException as exc:
        print(f"[Cloud memory write] {exc}")
        return False


def cloud_mode() -> bool:
    if not configured():
        return False
    return heartbeat("pc")


if __name__ == "__main__":
    if not configured():
        raise SystemExit("Set JARVIS_CLOUD_URL and JARVIS_CLOUD_SECRET first.")
    print("Cloud connector:", "online" if heartbeat() else "offline")
    result = ask_cloud("Say hello in one short sentence.")
    print(result or "Cloud unavailable")
