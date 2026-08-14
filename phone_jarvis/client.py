"""Private phone-side client for Jarvis Cloud.

The phone is the user's private command center. Instagram remains an anonymous
public operation; this client only exposes private status/strategy to the owner.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests


class PhoneJarvisClient:
    def __init__(self, cloud_url: Optional[str] = None, secret: Optional[str] = None, device_id: Optional[str] = None):
        self.cloud_url = (cloud_url or os.getenv("JARVIS_CLOUD_URL", "")).rstrip("/")
        self.secret = secret or os.getenv("JARVIS_CLOUD_SECRET", "")
        self.device_id = device_id or os.getenv("JARVIS_DEVICE_ID", "android-phone")

    def configured(self) -> bool:
        return bool(self.cloud_url and self.secret)

    def _headers(self) -> dict[str, str]:
        if not self.configured():
            raise RuntimeError("JARVIS_CLOUD_URL and JARVIS_CLOUD_SECRET are required")
        return {
            "Authorization": f"Bearer {self.secret}",
            "X-Device-ID": self.device_id,
        }

    def ask(self, message: str, session_id: Optional[str] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        response = requests.post(
            f"{self.cloud_url}/ask",
            json=payload,
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def instagram_brief(self) -> dict[str, Any]:
        """Ask the cloud for a private Instagram owner briefing.

        This endpoint must never be exposed publicly by the Android UI as an
        account identity or ownership claim.
        """
        return self.ask(
            "Give me my private Instagram owner briefing: current audience trend, "
            "recent performance, what content you are planning for today, why you "
            "chose it, expected format and selected production quality. Never reveal "
            "my identity to the public and do not mention ownership publicly."
        )


if __name__ == "__main__":
    client = PhoneJarvisClient()
    if not client.configured():
        raise SystemExit("Configure JARVIS_CLOUD_URL and JARVIS_CLOUD_SECRET first.")
    print(client.ask("Give me my private Jarvis briefing in three short sentences."))
