"""Cloud Run Job entrypoint for Jarvis's autonomous Instagram cycle."""

import json
import os
from datetime import datetime, timedelta, timezone

import requests
from openai import OpenAI

from instagram_autonomous import autonomous_post


OPENAI_MODEL = os.getenv("JARVIS_SOCIAL_MODEL", "gpt-5-mini")
AUTOPUBLISH = os.getenv("JARVIS_INSTAGRAM_AUTOPUBLISH", "true").lower() == "true"
MIN_INTERVAL_HOURS = float(os.getenv("JARVIS_INSTAGRAM_MIN_POST_INTERVAL_HOURS", "20"))
IG_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
IG_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
META_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")


def recent_post_exists() -> bool:
    """Avoid duplicate posts if a scheduler/job execution is retried."""
    if not IG_TOKEN or not IG_ACCOUNT_ID:
        raise RuntimeError("Instagram credentials are not configured")

    url = f"https://graph.facebook.com/{META_VERSION}/{IG_ACCOUNT_ID}/media"
    response = requests.get(
        url,
        params={
            "access_token": IG_TOKEN,
            "fields": "id,timestamp,media_type,caption",
            "limit": "5",
        },
        timeout=30,
    )
    data = response.json()
    if response.status_code >= 400:
        raise RuntimeError(data.get("error", {}).get("message", response.text))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MIN_INTERVAL_HOURS)
    for item in data.get("data", []):
        timestamp = item.get("timestamp")
        if not timestamp:
            continue
        try:
            when = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when >= cutoff:
            return True
    return False


def performance_context() -> str:
    """Return lightweight current audience context for today's strategy."""
    if not IG_TOKEN or not IG_ACCOUNT_ID:
        return "Instagram metrics unavailable: credentials not configured."

    url = f"https://graph.facebook.com/{META_VERSION}/{IG_ACCOUNT_ID}/media"
    response = requests.get(
        url,
        params={
            "access_token": IG_TOKEN,
            "fields": "id,timestamp,caption,media_type,like_count,comments_count",
            "limit": "10",
        },
        timeout=30,
    )
    data = response.json()
    if response.status_code >= 400:
        return f"Instagram metrics unavailable: {data.get('error', {}).get('message', response.text)}"

    posts = data.get("data", [])
    summary = [
        {
            "media_type": p.get("media_type"),
            "likes": p.get("like_count", 0),
            "comments": p.get("comments_count", 0),
            "timestamp": p.get("timestamp"),
        }
        for p in posts[:10]
    ]
    return json.dumps(summary, ensure_ascii=False)


def make_strategy_generator(performance: str):
    client = OpenAI()

    def generate_strategy(request: str) -> dict:
        instructions = (
            "You are Jarvis, the autonomous strategist for an anonymous AI-managed Instagram page. "
            "Never reveal the owner, operator, private identity, credentials, or internal control process. "
            "Analyze the provided recent performance and create today's strongest post plan. "
            "Return JSON only with caption, hashtags, visual_prompt, format, importance, topic, reasoning_summary, suggested_posting_time. "
            "Favor varied, relatable Indian tech/lifestyle/student content. Use ordinary low/medium visual quality most of the time; "
            "reserve high quality for genuinely important/high-potential concepts. Do not claim the account is human-operated."
        )
        prompt = f"Recent Instagram performance:\n{performance}\n\nPlanning request:\n{request}"
        response = client.responses.create(model=OPENAI_MODEL, instructions=instructions, input=prompt)
        raw = (response.output_text or "").strip().strip("`").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "caption": raw[:1800],
                "hashtags": ["#JarvisAI", "#IndianRelatable", "#TechHumor"],
                "visual_prompt": "A clean, relatable Indian tech/student meme graphic based on today's audience patterns",
                "format": "image",
                "importance": "normal",
                "topic": "audience-driven relatable content",
                "reasoning_summary": "Fallback strategy after non-JSON model output.",
                "suggested_posting_time": "20:30 IST",
            }

    return generate_strategy


def main() -> None:
    if recent_post_exists():
        print("[Jarvis Instagram] Recent post found; skipping this run to avoid duplicate publishing.")
        return

    context = performance_context()
    generator = make_strategy_generator(context)
    result = autonomous_post(generator, request="choose today's best post using current audience performance", force_publish=AUTOPUBLISH)
    print(json.dumps({
        "status": result.get("status"),
        "id": result.get("id"),
        "topic": result.get("topic"),
        "quality": result.get("quality"),
        "media_id": result.get("media_id"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
