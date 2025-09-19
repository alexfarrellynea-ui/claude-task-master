"""Client for invoking Intelligence Studio flows."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict

import httpx
import structlog

from ..config import PlannerSettings, get_settings

logger = structlog.get_logger(__name__)


class AIClient:
    """Wrapper around the Intelligence Studio flow endpoint."""

    def __init__(self, settings: PlannerSettings | None = None) -> None:
        self._settings = settings or get_settings()

    async def chat(self, system: str, user: str, session_id: str | None = None, timeout: float = 45.0) -> tuple[str, dict[str, int]]:
        settings = self._settings.intelligence_studio
        if not settings.api_key:
            raise RuntimeError("Intelligence Studio API key is not configured")
        session = session_id or str(uuid.uuid4())
        payload = {
            "output_type": "chat",
            "input_type": "chat",
            "input_value": json.dumps([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]),
            "session_id": session,
        }
        headers = {
            "x-api-key": settings.api_key,
            "Content-Type": "application/json",
        }

        start = time.perf_counter()
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.flow_url, headers=headers, json=payload, timeout=timeout)
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info("intelligence_studio.call", session_id=session, latency_ms=latency_ms, status_code=response.status_code)
        response.raise_for_status()
        data = response.json()

        message: Dict[str, Any] | None = data.get("message")
        if message is None and "choices" in data:
            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message")
        if not message:
            raise RuntimeError("Intelligence Studio response missing message payload")

        content = message.get("content", "")
        usage = data.get("usage") or message.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return content, {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}


__all__ = ["AIClient"]
