"""
Cloud-first launcher for the existing Jarvis desktop agent.

Run this instead of jarvisvav1.py when the cloud connector is configured:
    python cloud_jarvis.py

Behavior:
- Sends normal conversation to Jarvis Cloud first.
- If Cloud says the request needs the PC, the existing local GPT/tool brain executes it.
- Falls back to the local brain automatically if Cloud is unavailable.
- Keeps a persistent Cloud session id.
- Sends PC heartbeats in the background.
- Pulls shared Cloud memory into the local context snapshot.
- Mirrors safe local memory writes to the Cloud memory store.
"""

import json
import os
import threading
import time
from pathlib import Path

import jarvisvav1 as local_jarvis

from cloud.jarvis_cloud_client import ask_cloud, configured, get_memory, heartbeat, set_memory

SESSION_FILE = Path(os.path.expanduser("~")) / "jarvis_cloud_session.json"
_SESSION_ID = None


def _load_session():
    global _SESSION_ID
    try:
        if SESSION_FILE.exists():
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            _SESSION_ID = data.get("session_id")
    except Exception as exc:
        print(f"[Cloud session load] {exc}")


def _save_session(session_id: str):
    global _SESSION_ID
    _SESSION_ID = session_id
    try:
        SESSION_FILE.write_text(json.dumps({"session_id": session_id}), encoding="utf-8")
    except Exception as exc:
        print(f"[Cloud session save] {exc}")


def _cloud_heartbeat_loop():
    while True:
        if configured():
            heartbeat("pc")
        time.sleep(60)


def _sync_cloud_memory_into_local():
    if not configured():
        return
    try:
        memory = get_memory()
        local_jarvis.SESSION_MEMORY.setdefault("background_state", {})["cloud_memory"] = memory
        local_jarvis.SESSION_MEMORY["background_state"]["cloud_connected"] = True
    except Exception as exc:
        print(f"[Cloud memory sync] {exc}")


def _mirror_memory_write(original_fn, category: str, key: str, value: str):
    result = original_fn(category, key, value)
    if configured() and result.lower().startswith(("remembered", "got it")):
        set_memory(f"{category}.{key}", value)
    return result


def _mirror_fact_write(original_fn, key: str, value: str):
    result = original_fn(key, value)
    if configured() and result.lower().startswith("got it"):
        set_memory(f"facts.{key}", value)
    return result


def cloud_first_think_and_act(user_text: str) -> str:
    """Cloud first for conversation; local GPT/tool execution for PC actions."""
    if configured():
        global _SESSION_ID
        result = ask_cloud(user_text, _SESSION_ID)
        if result:
            _save_session(result.get("session_id", _SESSION_ID or ""))
            mode = result.get("mode", "chat")
            if mode == "chat":
                return result.get("reply") or "I'm here, boss."
            # Cloud identified a PC-only request. Preserve existing full local tool brain.
            local_result = LOCAL_THINK_AND_ACT(user_text)
            return local_result
    return LOCAL_THINK_AND_ACT(user_text)


# Preserve the original implementation before replacing the global symbol used by main().
LOCAL_THINK_AND_ACT = local_jarvis.think_and_act

# Mirror safe memory writes without changing the existing tool schema.
_ORIGINAL_REMEMBER_FACT = local_jarvis.remember_fact
_ORIGINAL_REMEMBER_PERSONAL_CONTEXT = local_jarvis.remember_personal_context
local_jarvis.remember_fact = lambda key, value: _mirror_fact_write(_ORIGINAL_REMEMBER_FACT, key, value)
local_jarvis.remember_personal_context = lambda category, key, value: _mirror_memory_write(_ORIGINAL_REMEMBER_PERSONAL_CONTEXT, category, key, value)

# main() looks up think_and_act globally, so replacing the module symbol is enough.
local_jarvis.think_and_act = cloud_first_think_and_act


def main():
    _load_session()
    if configured():
        online = heartbeat("pc")
        print(f"[Jarvis Cloud] {'ONLINE' if online else 'OFFLINE - local fallback active'}")
        _sync_cloud_memory_into_local()
        threading.Thread(target=_cloud_heartbeat_loop, daemon=True).start()
    else:
        print("[Jarvis Cloud] Not configured - running local Jarvis only.")

    local_jarvis.main()


if __name__ == "__main__":
    main()
