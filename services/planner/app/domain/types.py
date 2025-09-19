"""Domain-level dataclasses for building plans."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..persistence.models import NodeDomain


@dataclass
class NodeSpec:
    domain: NodeDomain
    title: str
    description: str
    instructions: dict[str, Any]
    acceptance_criteria: list[str]
    artifacts_in: list[dict[str, Any]] = field(default_factory=list)
    artifacts_out: list[dict[str, Any]] = field(default_factory=list)
    contract_refs: list[str] = field(default_factory=list)
    requirements_refs: list[str] = field(default_factory=list)


@dataclass
class EdgeSpec:
    from_index: int
    to_index: int
    description: str | None = None
    artifact_type: str | None = None


@dataclass
class PlanBuildResult:
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]


