"""
Jarvis autonomous Instagram content pipeline.

This module is intentionally separate from jarvisvav1.py so the large legacy
assistant file does not need to be rewritten in one risky commit.

Flow:
    strategy -> quality selection -> GPT image generation -> Cloudinary upload
    -> official Meta Graph publish -> local audit/history

Environment:
    OPENAI_API_KEY
    OPENAI_IMAGE_MODEL=gpt-image-1.5
    INSTAGRAM_ACCESS_TOKEN
    INSTAGRAM_ACCOUNT_ID
    META_GRAPH_API_VERSION=v20.0
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

Optional:
    JARVIS_INSTAGRAM_HIGH_QUALITY_RATE=0.15
    JARVIS_INSTAGRAM_MEDIUM_QUALITY_RATE=0.65
    JARVIS_INSTAGRAM_LOW_QUALITY_RATE=0.20
    JARVIS_INSTAGRAM_IMAGE_SIZE=1024x1024
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5")
OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"

META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}"
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

HIGH_RATE = float(os.getenv("JARVIS_INSTAGRAM_HIGH_QUALITY_RATE", "0.15"))
MEDIUM_RATE = float(os.getenv("JARVIS_INSTAGRAM_MEDIUM_QUALITY_RATE", "0.65"))
LOW_RATE = float(os.getenv("JARVIS_INSTAGRAM_LOW_QUALITY_RATE", "0.20"))
IMAGE_SIZE = os.getenv("JARVIS_INSTAGRAM_IMAGE_SIZE", "1024x1024")

DATA_DIR = Path(os.path.expanduser("~")) / "jarvis_instagram"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
AUDIT_FILE = DATA_DIR / "audit.jsonl"


def _load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": [], "ideas": [], "performance": []}


HISTORY = _load_history()


def _save_history():
    HISTORY_FILE.write_text(json.dumps(HISTORY, ensure_ascii=False, indent=2), encoding="utf-8")


def _audit(action, details):
    entry = {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "details": details,
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _meta_post(path, payload):
    if not requests:
        return {"error": "requests package is required"}
    payload = dict(payload)
    payload["access_token"] = INSTAGRAM_ACCESS_TOKEN
    try:
        r = requests.post(
            f"{META_GRAPH_BASE}/{path.lstrip('/')}",
            data=payload,
            timeout=40,
        )
        data = r.json()
        if r.status_code >= 400:
            return {"error": data.get("error", {}).get("message", r.text)}
        return data
    except Exception as exc:
        return {"error": str(exc)}


def choose_image_quality(strategy):
    """Mostly inexpensive images, with occasional flagship images."""
    # Content can explicitly request a flagship image; otherwise use the
    # configured weighted distribution.
    text = json.dumps(strategy, ensure_ascii=False).lower()
    flagship_words = ("flagship", "hero", "campaign", "important", "announcement", "milestone")
    if any(word in text for word in flagship_words):
        return "high"

    roll = random.random()
    if roll < HIGH_RATE:
        return "high"
    if roll < HIGH_RATE + MEDIUM_RATE:
        return "medium"
    return "low"


def generate_instagram_image(prompt, quality="medium", size=None):
    """Generate an image and save it locally. Returns the local path."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if not requests:
        raise RuntimeError("requests package is required")

    quality = quality if quality in {"low", "medium", "high", "auto"} else "medium"
    size = size or IMAGE_SIZE
    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "output_format": "jpeg",
    }

    r = requests.post(
        OPENAI_IMAGES_URL,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(data.get("error", {}).get("message", r.text))

    item = (data.get("data") or [{}])[0]
    b64 = item.get("b64_json")
    if not b64:
        raise RuntimeError("Image API returned no b64_json image")

    filename = DATA_DIR / f"post_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
    filename.write_bytes(base64.b64decode(b64))
    _audit("image_generated", {"file": str(filename), "quality": quality, "size": size})
    return str(filename)


def _cloudinary_signature(params):
    serialized = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    return hmac.new(
        CLOUDINARY_API_SECRET.encode("utf-8"),
        serialized.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()


def upload_image(image_path):
    """Upload generated media to a public HTTPS URL for Meta to fetch."""
    if not all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)):
        raise RuntimeError(
            "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET."
        )
    if not requests:
        raise RuntimeError("requests package is required")

    timestamp = int(time.time())
    public_id = f"jarvis/{Path(image_path).stem}"
    params = {"public_id": public_id, "timestamp": timestamp}
    signature = _cloudinary_signature(params)

    with open(image_path, "rb") as image_file:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload",
            data={
                "api_key": CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "public_id": public_id,
                "signature": signature,
            },
            files={"file": image_file},
            timeout=90,
        )

    data = r.json()
    if r.status_code >= 400 or not data.get("secure_url"):
        raise RuntimeError(data.get("error", {}).get("message", r.text))

    _audit("image_uploaded", {"public_id": public_id})
    return data["secure_url"]


def publish_image(caption, image_url):
    """Publish one image through the official Instagram Graph API."""
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        raise RuntimeError("Instagram credentials are not configured")

    container = _meta_post(
        f"{INSTAGRAM_ACCOUNT_ID}/media",
        {"image_url": image_url, "caption": caption},
    )
    if "error" in container:
        raise RuntimeError(container["error"])

    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError("Instagram returned no creation container id")

    # Meta may need a short moment to finish processing the media container.
    for _ in range(6):
        time.sleep(2)
        status = _meta_post(
            f"{creation_id}",
            {},
        )
        # Some Graph API versions do not expose container status through the
        # same endpoint. If the status check is unavailable, continue to publish.
        if status.get("status_code") in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram media container status: {status}")
        break

    published = _meta_post(
        f"{INSTAGRAM_ACCOUNT_ID}/media_publish",
        {"creation_id": creation_id},
    )
    if "error" in published:
        raise RuntimeError(published["error"])

    media_id = published.get("id")
    _audit("instagram_published", {"media_id": media_id, "creation_id": creation_id})
    return media_id


def build_strategy_request(base_request, history):
    return (
        "Create the next post for an AI-managed Instagram page. "
        "The page should feel human-made and varied, not like every post is an expensive AI artwork. "
        "Use ordinary meme/graphic quality most of the time and reserve premium visual quality for "
        "important or high-potential ideas. Do not claim to be human. Avoid repetitive formats. "
        "Return JSON with: caption, hashtags, visual_prompt, format, importance, topic, "
        "reasoning_summary.\n"
        f"Request: {base_request}\n"
        f"Recent history: {json.dumps(history[-15:], ensure_ascii=False)[:7000]}"
    )


def autonomous_post(generate_strategy, request="choose today's best post", force_publish=True):
    """Run one complete autonomous post cycle.

    generate_strategy must be a callable returning a dict. Jarvis's existing
    generate_social_strategy() can be passed directly.
    """
    strategy = generate_strategy(build_strategy_request(request, HISTORY.get("posts", [])))
    quality = choose_image_quality(strategy)
    visual_prompt = strategy.get("visual_prompt") or request

    image_path = generate_instagram_image(visual_prompt, quality=quality)
    image_url = upload_image(image_path)

    caption = (strategy.get("caption") or "").strip()
    hashtags = strategy.get("hashtags") or []
    if isinstance(hashtags, list):
        caption += "\n\n" + " ".join(str(x) for x in hashtags)

    result = {
        "id": uuid.uuid4().hex[:10],
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "topic": strategy.get("topic", ""),
        "strategy": strategy,
        "quality": quality,
        "image_path": image_path,
        "image_url": image_url,
        "caption": caption,
        "status": "generated",
    }

    if force_publish:
        result["media_id"] = publish_image(caption, image_url)
        result["status"] = "published"

    HISTORY.setdefault("posts", []).append(result)
    HISTORY["posts"] = HISTORY["posts"][-100:]
    _save_history()
    _audit("autonomous_post_cycle", {"id": result["id"], "quality": quality, "status": result["status"]})
    return result


def get_status():
    return {
        "instagram_ready": bool(INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID),
        "openai_ready": bool(OPENAI_API_KEY),
        "image_host_ready": bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET),
        "posts_recorded": len(HISTORY.get("posts", [])),
        "quality_mix": {"high": HIGH_RATE, "medium": MEDIUM_RATE, "low": LOW_RATE},
    }
