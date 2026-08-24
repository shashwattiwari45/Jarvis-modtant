"""Text-model provider adapter for Jarvis Cloud."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / "web_ui" / ".env")
    load_dotenv(project_root / ".env")
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROVIDER = os.getenv("JARVIS_TEXT_PROVIDER", "gemini").strip().lower()


class ProviderError(RuntimeError):
    pass


def parse_provider_json(raw: str) -> dict[str, Any]:
    """Normalize a provider response into Jarvis's object-shaped contract."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"mode": "chat", "reply": raw, "memory_updates": []}
    if not isinstance(parsed, dict):
        return {"mode": "chat", "reply": str(parsed), "memory_updates": []}
    return parsed


def _gemini_text(system: str, prompt: str, web: bool) -> str:
    if not genai or not types or not GEMINI_API_KEY:
        raise ProviderError("Gemini is not configured")
    client = genai.Client(api_key=GEMINI_API_KEY)
    config_kwargs: dict[str, Any] = {
        "system_instruction": system,
        "temperature": 0.2,
        "response_mime_type": "application/json",
    }
    if web:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    text = (response.text or "").strip()
    if not text:
        raise ProviderError("Gemini returned an empty response")
    return text


def _openai_text(system: str, prompt: str, web: bool) -> tuple[str, str]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ProviderError("OpenAI is not configured")
    model = os.getenv("JARVIS_CLOUD_MODEL", os.getenv("JARVIS_REASONING_MODEL", "gpt-5-mini"))
    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": system,
        "input": prompt,
        "verbosity": "medium",
    }
    if web:
        kwargs["tools"] = [{"type": "web_search", "search_context_size": os.getenv("JARVIS_WEB_SEARCH_CONTEXT", "medium")}]
    response = OpenAI(api_key=key).responses.create(**kwargs)
    text = (response.output_text or "").strip()
    if not text:
        raise ProviderError("OpenAI returned an empty response")
    return text, model


def generate_json(system: str, prompt: str, web: bool = False) -> tuple[dict[str, Any], str, bool]:
    """Generate Jarvis JSON, preferring Gemini with OpenAI fallback."""
    attempts = []
    if PROVIDER in {"gemini", "auto"}:
        attempts.append(("gemini", lambda: (_gemini_text(system, prompt, web), GEMINI_MODEL, web)))
    if PROVIDER in {"openai", "auto", "gemini"}:
        attempts.append(("openai", lambda: (*_openai_text(system, prompt, web), web)))

    errors = []
    for name, attempt in attempts:
        try:
            raw, model, used_web = attempt()
            parsed = parse_provider_json(raw)
            return parsed, model, used_web
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    raise ProviderError("; ".join(errors) or "No text provider is configured")
