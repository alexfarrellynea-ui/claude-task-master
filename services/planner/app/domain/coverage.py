"""Coverage utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ingest import Operation


@dataclass
class CoverageResult:
    total_operations: int
    covered_operations: int
    missing_operations: list[str]


def compute_coverage(operations: Iterable[Operation], covered_operation_ids: Iterable[str]) -> CoverageResult:
    all_ops = {op.operation_id for op in operations}
    covered = set(covered_operation_ids)
    missing = sorted(all_ops - covered)
    return CoverageResult(
        total_operations=len(all_ops),
        covered_operations=len(all_ops) - len(missing),
        missing_operations=missing,
    )


