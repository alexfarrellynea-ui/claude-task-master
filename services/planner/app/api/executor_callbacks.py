"""Executor webhook endpoints."""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.cards import ContextCardService
from ..persistence.models import ContextCard, Plan, PlanNode
from .deps import get_db_session

router = APIRouter(prefix="/executor", tags=["executor"])


class ExecutorCallback(BaseModel):
    status: str
    artifactsOut: List[dict[str, Any]] = Field(default_factory=list)
    reflections: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)


@router.post("/callbacks/{task_id}")
async def executor_callback(task_id: str, payload: ExecutorCallback, session: AsyncSession = Depends(get_db_session)):
    node = await session.get(PlanNode, task_id)
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    plan = await session.get(Plan, node.plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    node.artifacts_out = list(node.artifacts_out or []) + payload.artifactsOut
    session.add(node)

    contract_slice = {
        "contractOps": node.instructions.get("contractOps", []),
        "planId": plan.id,
    }
    card_service = ContextCardService()
    summary = await card_service.summarize(node, contract_slice)
    card = ContextCard(
        node_id=node.id,
        contract_slice_ref=",".join(node.instructions.get("contractOps", [])) or plan.contract_hash,
        interfaces={"domain": node.type.value},
        schema_hashes={"contract": plan.contract_hash},
        summary=summary,
        citations=payload.citations,
    )
    session.add(card)

    return {"status": payload.status, "contextCardId": card.id}


