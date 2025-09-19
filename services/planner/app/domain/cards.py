"""Context card helpers."""
from __future__ import annotations

from typing import Any

from ..persistence.models import PlanNode
from .ai_client import AIClient


class ContextCardService:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self._ai_client = ai_client or AIClient()

    async def summarize(self, node: PlanNode, contract_slice: dict[str, Any]) -> str:
        system_prompt = (
            "You are TaskMaster Planner. Summarize the completed node so downstream agents can reuse context. "
            "Focus on schema or endpoint impacts, highlight artifacts, and stay under 120 words."
        )
        user_prompt = (
            f"Node label: {node.label}\n"
            f"Domain: {node.type.value}\n"
            f"Instructions: {node.instructions}\n"
            f"Contract slice: {contract_slice}\n"
        )
        try:
            content, _ = await self._ai_client.chat(system_prompt, user_prompt, session_id=f"{node.plan_id}:{node.id}")
            return content.strip()
        except Exception:
            # Offline fallback for tests or missing credentials
            return f"{node.label} ({node.type.value}) covering {', '.join(node.instructions.get('contractOps', []))}"[:512]


__all__ = ["ContextCardService"]
