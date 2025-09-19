"""Plan management API."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.planner_service import PlanCreateParams, PlannerOrchestrator
from ..domain.ingest import load_contract
from ..domain.coverage import compute_coverage
from ..persistence.models import ComplexityFeatures, Plan, PlanEdge, PlanNode
from .deps import get_db_session

router = APIRouter(prefix="/plans", tags=["plans"])


class PRDPayload(BaseModel):
    text: str | None = Field(default=None, description="Raw PRD text")
    ref: str | None = Field(default=None, description="Reference to PRD location")

    def require_text(self) -> str:
        if self.text:
            return self.text
        if self.ref and os.path.exists(self.ref):
            with open(self.ref, "r", encoding="utf-8") as handle:
                return handle.read()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PRD text or accessible ref required")


class ContractPayload(BaseModel):
    document: dict[str, Any] | None = Field(default=None)
    ref: str | None = None

    def require_document(self) -> dict[str, Any]:
        if self.document:
            return self.document
        if self.ref and os.path.exists(self.ref):
            with open(self.ref, "r", encoding="utf-8") as handle:
                return json.load(handle)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contract document required")


class PlanOptions(BaseModel):
    headroom_pct: float | None = Field(default=None, alias="headroomPct")
    allow_research: bool | None = Field(default=None, alias="allowResearch")
    model_class: str | None = Field(default=None, alias="modelClass")

    model_config = ConfigDict(populate_by_name=True)


class PlanCreateRequest(BaseModel):
    project_id: str = Field(alias="projectId")
    run_id: str = Field(alias="runId")
    prd: PRDPayload
    contract: ContractPayload
    options: PlanOptions | None = None

    model_config = ConfigDict(populate_by_name=True)


class PlanSummaryResponse(BaseModel):
    id: str
    project_id: str = Field(alias="projectId")
    run_id: str = Field(alias="runId")
    status: str
    report_ref: str | None = Field(alias="reportRef")
    coverage: dict[str, Any]
    created_at: str | None = Field(alias="createdAt")
    updated_at: str | None = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, ser_json_t="alias")


class TaskListItem(BaseModel):
    id: str
    title: str
    domain: str
    description: str
    requirementsRefs: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    acceptanceCriteria: List[str] = Field(default_factory=list)
    artifactsIn: List[dict[str, Any]] = Field(default_factory=list)
    artifactsOut: List[dict[str, Any]] = Field(default_factory=list)
    contextBudgetTokens: int
    complexity: dict[str, Any]
    modelClass: str
    citations: List[str] = Field(default_factory=list)
    riskClass: str = "Medium"

    model_config = ConfigDict(populate_by_name=True, ser_json_t="alias")


def _plan_not_found(plan_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan {plan_id} not found")


@router.post("", response_model=PlanSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: PlanCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    orchestrator = PlannerOrchestrator(session)
    prd_text = request.prd.require_text()
    contract_document = request.contract.require_document()
    plan = await orchestrator.create_plan(
        PlanCreateParams(
            project_id=request.project_id,
            run_id=request.run_id,
            prd_text=prd_text,
            contract_document=contract_document,
            principal="api",
            correlation_id=str(uuid.uuid4()),
            options=request.options.model_dump(by_alias=True) if request.options else None,
        )
    )
    return await _build_summary(session, plan)


async def _build_summary(session: AsyncSession, plan: Plan) -> PlanSummaryResponse:
    params = plan.params or {}
    ingest_params = params.get("ingest", {})
    contract = ingest_params.get("contract")
    prd_text = ingest_params.get("prdText", "")
    if contract:
        contract_artifact = load_contract(contract)
        covered_ops = await _covered_ops(session, plan.id)
        coverage = compute_coverage(contract_artifact.operations, covered_ops)
    else:
        coverage = compute_coverage([], [])
    return PlanSummaryResponse(
        id=plan.id,
        projectId=plan.project_id,
        runId=plan.run_id,
        status=plan.status.value,
        reportRef=plan.report_ref,
        coverage={
            "missingOperations": coverage.missing_operations,
            "totalOperations": coverage.total_operations,
        },
        createdAt=plan.created_at.isoformat() if plan.created_at else None,
        updatedAt=plan.updated_at.isoformat() if plan.updated_at else None,
    )


async def _covered_ops(session: AsyncSession, plan_id: str) -> List[str]:
    result = await session.execute(
        select(PlanNode).where(PlanNode.plan_id == plan_id).order_by(PlanNode.order_hint)
    )
    nodes = result.scalars().all()
    ops: List[str] = []
    for node in nodes:
        ops.extend(node.instructions.get("contractOps", []))
    return ops


@router.get("/{plan_id}", response_model=PlanSummaryResponse)
async def get_plan(plan_id: str, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise _plan_not_found(plan_id)
    return await _build_summary(session, plan)


@router.get("/{plan_id}/tasks.json", response_model=List[TaskListItem])
async def get_task_list(plan_id: str, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise _plan_not_found(plan_id)
    nodes_result = await session.execute(
        select(PlanNode).where(PlanNode.plan_id == plan_id).order_by(PlanNode.order_hint)
    )
    nodes = nodes_result.scalars().all()
    complexities_result = await session.execute(
        select(ComplexityFeatures).where(ComplexityFeatures.node_id.in_([node.id for node in nodes]))
    )
    complexities = {row.node_id: row for row in complexities_result.scalars()}
    edges_result = await session.execute(select(PlanEdge).where(PlanEdge.plan_id == plan_id))
    dependency_map: Dict[str, List[str]] = {node.id: [] for node in nodes}
    for edge in edges_result.scalars():
        dependency_map[edge.to_node].append(edge.from_node)

    items: List[TaskListItem] = []
    for node in nodes:
        features = complexities.get(node.id)
        node_score = node.score or {}
        complexity = {
            "score_0_100": node_score.get("ccs", 0),
            "score_1_10": node_score.get("score_1_10", 0),
            "recommendedSubtasks": node_score.get("recommendedSubtasks", 1),
            "confidence": node_score.get("confidence", 0.75),
        }
        model_class = node_score.get("modelClass", "Class-200K")
        items.append(
            TaskListItem(
                id=node.id,
                title=node.label,
                domain=node.type.value,
                description=node.summary or node.label,
                requirementsRefs=node.instructions.get("requirementsRefs", []),
                dependencies=dependency_map[node.id],
                acceptanceCriteria=node.instructions.get("acceptanceCriteria", []),
                artifactsIn=node.artifacts_in,
                artifactsOut=node.artifacts_out,
                contextBudgetTokens=node.token_budget,
                complexity=complexity,
                modelClass=model_class,
            )
        )
    return items


@router.get("/{plan_id}/graph")
async def get_graph(plan_id: str, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise _plan_not_found(plan_id)
    nodes_result = await session.execute(
        select(PlanNode).where(PlanNode.plan_id == plan_id).order_by(PlanNode.order_hint)
    )
    edges_result = await session.execute(select(PlanEdge).where(PlanEdge.plan_id == plan_id))
    nodes = [
        {
            "id": node.id,
            "label": node.label,
            "domain": node.type.value,
            "tokenBudget": node.token_budget,
            "order": node.order_hint,
        }
        for node in nodes_result.scalars()
    ]
    edges = [
        {"from": edge.from_node, "to": edge.to_node, "description": edge.description}
        for edge in edges_result.scalars()
    ]
    return {"nodes": nodes, "edges": edges}


@router.get("/{plan_id}/report")
async def get_report(plan_id: str, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise _plan_not_found(plan_id)
    if not plan.report_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not generated")
    if plan.report_ref.startswith("file://"):
        path = plan.report_ref[len("file://") :]
        if not os.path.exists(path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file missing")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {"reportRef": plan.report_ref}


@router.post("/{plan_id}/rerun", response_model=PlanSummaryResponse)
async def rerun_plan(plan_id: str, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise _plan_not_found(plan_id)
    params = plan.params or {}
    ingest_params = params.get("ingest")
    if not ingest_params:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan does not contain rerunnable payloads")
    orchestrator = PlannerOrchestrator(session)
    new_plan = await orchestrator.create_plan(
        PlanCreateParams(
            project_id=plan.project_id,
            run_id=str(uuid.uuid4()),
            prd_text=ingest_params.get("prdText", ""),
            contract_document=ingest_params.get("contract"),
            principal="api",
            correlation_id=str(uuid.uuid4()),
            options=params.get("requestOptions"),
        )
    )
    return await _build_summary(session, new_plan)


