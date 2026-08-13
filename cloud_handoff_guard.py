"""Small helpers for validating the Cloud -> PC routing contract."""

VALID_MODES = {"chat", "pc_action"}


def normalize_cloud_result(result):
    if not isinstance(result, dict):
        return {"mode": "chat", "reply": "I'm here, boss."}
    mode = result.get("mode")
    reply = str(result.get("reply") or "").strip()
    if mode not in VALID_MODES:
        mode = "chat"
    return {"mode": mode, "reply": reply or "I'm here, boss."}
