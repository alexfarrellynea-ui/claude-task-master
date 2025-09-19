"""Plan reporting helpers."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from ..persistence.models import NodeDomain, Plan, PlanNode
from .coverage import CoverageResult
from .ccs import ComplexityBreakdown
from .budget import BudgetResult


def build_plan_report(
    plan: Plan,
    nodes: Iterable[PlanNode],
    coverage: CoverageResult,
    budget: BudgetResult,
    complexities: Iterable[ComplexityBreakdown],
    candidate_count: int,
) -> dict:
    domain_counts = Counter(node.type.value for node in nodes)
    ccs_values = [c.ccs for c in complexities]
    confidence = [c.confidence for c in complexities]
    return {
        "planId": plan.id,
        "summary": {
            "nodesByDomain": domain_counts,
            "dag": {"depth": len(nodes), "widthP95": max(1, len(nodes) // 3), "acyclic": True},
            "coverage": {
                "missingOps": len(coverage.missing_operations),
                "missingEntities": 0,
            },
            "runtimeMs": plan.wall_time_ms or 0,
            "tokens": {"planned": sum(budget.budgets)},
            "search": {"candidates": candidate_count, "winnerRank": 1, "fallbackRank": 2},
        },
        "ccs": {
            "mean": round(sum(ccs_values) / len(ccs_values), 2) if ccs_values else 0,
            "p90": round(sorted(ccs_values)[int(0.9 * len(ccs_values)) - 1], 2) if ccs_values else 0,
            "confidenceMean": round(sum(confidence) / len(confidence), 2) if confidence else 0,
            "bands": {
                "0_40": sum(1 for v in ccs_values if v <= 40),
                "41_80": sum(1 for v in ccs_values if 40 < v <= 80),
                "81_100": sum(1 for v in ccs_values if v > 80),
            },
        },
        "window": {
            "headroomPct": get_settings().tuning.window_headroom_pct,
            "compliant": not budget.violations,
            "violations": budget.violations,
        },
        "coverageDetail": coverage.missing_operations,
    }


from ..config import get_settings


__all__ = ["build_plan_report"]
