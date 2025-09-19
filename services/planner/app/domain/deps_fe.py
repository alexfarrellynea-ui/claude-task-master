"""Front-end planning with gating."""
from __future__ import annotations

from typing import List

from .ingest import ContractArtifact
from .types import NodeSpec
from ..persistence.models import NodeDomain


UI_BASE_TASKS = [
    "Establish design system primitives",
    "Implement API client bound to contract schemas",
    "Ensure layout covers responsive breakpoints",
]


def build_frontend_nodes(contract: ContractArtifact) -> List[NodeSpec]:
    nodes: List[NodeSpec] = []
    if not contract.operations:
        return nodes

    nodes.append(
        NodeSpec(
            domain=NodeDomain.fe,
            title="Create shared frontend foundation",
            description="Set up design system, routing shell, and API client",
            instructions={"tasks": UI_BASE_TASKS, "contractOps": [op.operation_id for op in contract.operations]},
            acceptance_criteria=[
                "Design tokens defined",
                "API client generated from contract",
                "Context card summarizing FE primitives emitted",
            ],
        )
    )

    for op in contract.operations:
        nodes.append(
            NodeSpec(
                domain=NodeDomain.fe,
                title=f"Build UI flow for {op.operation_id}",
                description=f"Implement UI to surface {op.summary or op.operation_id}",
                instructions={
                    "contractOps": [op.operation_id],
                    "tasks": [
                        "Create route + view",
                        "Integrate API client with optimistic states",
                        "Instrument analytics hooks",
                    ],
                },
                acceptance_criteria=[
                    "UI renders contract-backed data",
                    "Error and loading states covered",
                    "Accessibility checklist satisfied",
                ],
                contract_refs=[f"operation:{op.operation_id}"],
            )
        )
    return nodes


