"""Private Instagram owner briefing helpers.

Nothing in this module publishes, replies, or exposes the owner's identity.
It only turns internal Instagram metrics/strategy into a private phone summary.
"""
from __future__ import annotations

from typing import Any


def build_instagram_brief(data: dict[str, Any]) -> str:
    audience = data.get("audience_trend") or "No audience trend available yet."
    performance = data.get("performance_summary") or "No recent performance summary available."
    plan = data.get("today_plan") or "No post has been planned yet."
    reason = data.get("reason") or "No planning rationale available."
    quality = data.get("production_quality") or "medium"
    fmt = data.get("format") or "image"

    return (
        "Private Instagram briefing:\n"
        f"Audience: {audience}\n"
        f"Performance: {performance}\n"
        f"Today's plan: {plan}\n"
        f"Why: {reason}\n"
        f"Format: {fmt}\n"
        f"Production quality: {quality}\n"
        "Public identity: anonymous AI-managed page."
    )
