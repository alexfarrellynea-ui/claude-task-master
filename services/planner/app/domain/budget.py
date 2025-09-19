"""Token budgeting utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..config import get_settings
from .types import NodeSpec


@dataclass
class BudgetResult:
    budgets: list[int]
    capacity: int
    violations: list[int]


def estimate_tokens(text: str) -> int:
    return max(32, int(len(text.split()) * 1.5) + 128)


def plan_budgets(nodes: List[NodeSpec]) -> BudgetResult:
    settings = get_settings()
    capacity = int(settings.tuning.default_model_window * (1 - settings.tuning.window_headroom_pct))
    budgets: list[int] = []
    violations: list[int] = []

    for idx, node in enumerate(nodes):
        base = estimate_tokens(node.description)
        base += 40 * len(node.instructions.get("tasks", []))
        base += 20 * len(node.acceptance_criteria)
        base = max(base, settings.tuning.token_budget_floor)
        if base > capacity:
            violations.append(idx)
            base = capacity
        budgets.append(base)
    return BudgetResult(budgets=budgets, capacity=capacity, violations=violations)


