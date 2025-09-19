"""Backend planning utilities."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .ingest import ContractArtifact
from .types import NodeSpec
from ..persistence.models import NodeDomain


def build_backend_nodes(contract: ContractArtifact) -> List[NodeSpec]:
    grouped: Dict[str, list] = defaultdict(list)
    for op in contract.operations:
        tag = op.tags[0] if op.tags else "default"
        grouped[tag].append(op)

    nodes: List[NodeSpec] = []
    for tag, ops in grouped.items():
        op_ids = [op.operation_id for op in ops]
        title = f"Implement backend handlers for {tag}"
        description = f"Implement API handlers covering operations: {', '.join(op_ids)}"
        instructions = {
            "contractOps": op_ids,
            "tasks": [
                "Implement FastAPI route handlers aligned with contract",
                "Integrate with database models and validations",
                "Emit Context Cards upon completion",
            ],
        }
        acceptance = [
            "All endpoints return contract-compliant schemas",
            "Unit tests cover success and error paths",
            "Token budget respected with context reuse",
        ]
        nodes.append(
            NodeSpec(
                domain=NodeDomain.be,
                title=title,
                description=description,
                instructions=instructions,
                acceptance_criteria=acceptance,
                contract_refs=[f"operation:{op_id}" for op_id in op_ids],
            )
        )
    return nodes


