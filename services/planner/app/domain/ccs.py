"""Complexity scoring utilities."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List

from ..config import get_settings
from .types import EdgeSpec, NodeSpec


@dataclass
class ComplexityBreakdown:
    node_index: int
    d: float
    s: float
    n: float
    a: float
    r: float
    ccs: float
    recommended_subtasks: int
    confidence: float
    model_class: str


def _score_components(node: NodeSpec, in_degree: int, out_degree: int) -> tuple[float, float, float, float, float]:
    tasks = node.instructions.get("tasks", [])
    contract_refs = node.instructions.get("contractOps", [])
    d = min(1.0, (in_degree + out_degree + len(contract_refs)) / 6)
    s = min(1.0, (len(tasks) + len(node.acceptance_criteria)) / 8)
    n = min(1.0, len(set(tasks)) / 6 or 0.1)
    a = min(1.0, (len(contract_refs) + len(node.requirements_refs)) / 6)
    r = 0.4 if any("research" in step.lower() for step in tasks) else 0.1
    return d, s, n, a, r


def compute_complexity(nodes: List[NodeSpec], edges: Iterable[EdgeSpec]) -> list[ComplexityBreakdown]:
    settings = get_settings()
    in_degrees = [0] * len(nodes)
    out_degrees = [0] * len(nodes)
    for edge in edges:
        out_degrees[edge.from_index] += 1
        in_degrees[edge.to_index] += 1

    breakdowns: list[ComplexityBreakdown] = []
    for idx, node in enumerate(nodes):
        d, s, n, a, r = _score_components(node, in_degrees[idx], out_degrees[idx])
        weighted = 0.30 * d + 0.20 * s + 0.20 * n + 0.15 * a + 0.15 * r
        ccs = round(weighted * 100, 2)
        recommended = max(1, math.ceil(ccs / 15))
        confidence = max(0.5, round(1 - (ccs / 200), 2))
        model_class = settings.tuning.default_model_class
        if ccs >= 81 and settings.tuning.optional_model_class:
            model_class = settings.tuning.optional_model_class
        breakdowns.append(
            ComplexityBreakdown(
                node_index=idx,
                d=round(d * 100, 2),
                s=round(s * 100, 2),
                n=round(n * 100, 2),
                a=round(a * 100, 2),
                r=round(r * 100, 2),
                ccs=ccs,
                recommended_subtasks=recommended,
                confidence=confidence,
                model_class=model_class,
            )
        )
    return breakdowns


