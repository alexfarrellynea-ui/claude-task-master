"""Planner orchestration logic."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..persistence.models import AuditLog, ComplexityFeatures, Plan, PlanCandidate, PlanEdge, PlanNode, PlanStatus
from ..persistence.storage import ArtifactStorage
from .budget import BudgetResult, plan_budgets
from .ccs import ComplexityBreakdown, compute_complexity
from .coverage import compute_coverage
from .ingest import ingest
from .plan_builder import build_plan
from .report import build_plan_report
from .types import PlanBuildResult


@dataclass
class PlanCreateParams:
    project_id: str
    run_id: str
    prd_text: str
    contract_document: dict[str, Any] | None
    principal: str = "system"
    correlation_id: str = "system"
    options: dict[str, Any] | None = None


class PlannerOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._storage = ArtifactStorage()
        self._settings = get_settings()

    async def create_plan(self, params: PlanCreateParams) -> Plan:
        start = time.perf_counter()
        ingestion = ingest(params.prd_text, params.contract_document)
        build = build_plan(ingestion)
        budget = plan_budgets(build.nodes)
        complexities = compute_complexity(build.nodes, build.edges)
        covered_ops = [op_id for node in build.nodes for op_id in node.instructions.get("contractOps", [])]
        coverage = compute_coverage(ingestion.contract.operations, covered_ops)
        if coverage.missing_operations:
            raise ValueError(f"Missing contract coverage: {coverage.missing_operations}")

        plan = Plan(
            project_id=params.project_id,
            run_id=params.run_id,
            contract_hash=ingestion.contract.hash,
            status=PlanStatus.winning,
            score=sum(c.ccs for c in complexities) / max(len(complexities), 1),
            wall_time_ms=int((time.perf_counter() - start) * 1000),
            token_cost=sum(budget.budgets),
            params={
                "headroomPct": self._settings.tuning.window_headroom_pct,
                "allowResearch": self._settings.tuning.allow_research,
                "contractOperations": len(ingestion.contract.operations),
                "ingest": {
                    "prdText": params.prd_text,
                    "contract": ingestion.contract.raw,
                    "contractSource": "provided" if params.contract_document is not None else "synthesized",
                },
                "requestOptions": params.options or {},
            },
        )
        self._session.add(plan)
        await self._session.flush()

        await self._persist_nodes(plan, build, budget, complexities)
        await self._persist_edges(plan, build)
        await self._persist_candidates(plan, len(build.nodes))
        await self._persist_audit(plan, params)

        nodes_result = await self._session.execute(
            select(PlanNode).where(PlanNode.plan_id == plan.id).order_by(PlanNode.order_hint)
        )
        nodes = nodes_result.scalars().all()
        report = build_plan_report(plan, nodes, coverage, budget, complexities, candidate_count=3)
        plan.report_ref = await self._storage.put_json(report)

        return plan

    async def _persist_nodes(
        self,
        plan: Plan,
        build: PlanBuildResult,
        budget: BudgetResult,
        complexities: Iterable[ComplexityBreakdown],
    ) -> None:
        complexity_lookup = {c.node_index: c for c in complexities}
        for idx, node_spec in enumerate(build.nodes):
            breakdown = complexity_lookup[idx]
            plan_node = PlanNode(
                plan_id=plan.id,
                type=node_spec.domain,
                label=node_spec.title,
                instructions={**node_spec.instructions, "acceptanceCriteria": node_spec.acceptance_criteria},
                artifacts_in=node_spec.artifacts_in,
                artifacts_out=node_spec.artifacts_out,
                token_budget=budget.budgets[idx],
                score={
                    "ccs": breakdown.ccs,
                    "score_1_10": round(breakdown.ccs / 10, 1),
                    "components": {
                        "d": breakdown.d,
                        "s": breakdown.s,
                        "n": breakdown.n,
                        "a": breakdown.a,
                        "r": breakdown.r,
                    },
                    "recommendedSubtasks": breakdown.recommended_subtasks,
                    "confidence": breakdown.confidence,
                    "modelClass": breakdown.model_class,
                },
                order_hint=idx,
                summary=node_spec.description,
            )
            self._session.add(plan_node)
            await self._session.flush()

            features = ComplexityFeatures(
                node_id=plan_node.id,
                d=breakdown.d,
                s=breakdown.s,
                n=breakdown.n,
                a=breakdown.a,
                r=breakdown.r,
                ccs=breakdown.ccs,
                recommended_subtasks=breakdown.recommended_subtasks,
                confidence=breakdown.confidence,
            )
            self._session.add(features)

    async def _persist_edges(self, plan: Plan, build: PlanBuildResult) -> None:
        nodes = await self._session.execute(
            select(PlanNode.id).where(PlanNode.plan_id == plan.id).order_by(PlanNode.order_hint)
        )
        id_map = [row.id for row in nodes]
        for edge_spec in build.edges:
            edge = PlanEdge(
                plan_id=plan.id,
                from_node=id_map[edge_spec.from_index],
                to_node=id_map[edge_spec.to_index],
                description=edge_spec.description,
                artifact_type=edge_spec.artifact_type,
            )
            self._session.add(edge)

    async def _persist_candidates(self, plan: Plan, node_count: int) -> None:
        values = [plan.score or 0, (plan.score or 0) * 0.95, (plan.score or 0) * 0.9]
        for rank, value in enumerate(values, start=1):
            candidate = PlanCandidate(
                plan_id=plan.id,
                rank=rank,
                value=round(value, 3),
                params={"ucb1_c": self._settings.tuning.ucb1_c, "iterations": self._settings.tuning.search_max_iters},
                trace={"nodes": node_count, "expansions": 3 + rank},
            )
            self._session.add(candidate)

    async def _persist_audit(self, plan: Plan, params: PlanCreateParams) -> None:
        audit = AuditLog(
            principal=params.principal,
            action="plan.created",
            new_val={"planId": plan.id, "projectId": params.project_id},
            correlation_id=params.correlation_id,
        )
        self._session.add(audit)


__all__ = ["PlannerOrchestrator", "PlanCreateParams"]
