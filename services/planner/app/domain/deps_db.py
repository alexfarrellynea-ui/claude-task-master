"""Database dependency planning."""
from __future__ import annotations

import json
from typing import List

from .ingest import ContractArtifact
from .types import NodeSpec
from ..persistence.models import NodeDomain


def build_db_nodes(contract: ContractArtifact) -> List[NodeSpec]:
    nodes: List[NodeSpec] = []
    schemas = contract.schemas or {}
    for name, schema in schemas.items():
        title = f"Design and migrate {name} table"
        description = f"Create migrations and data model for {name}."
        instructions = {
            "schemaDefinition": schema,
            "contractOps": [
                op.operation_id
                for op in contract.operations
                if name.lower() in json.dumps(op.__dict__).lower()
            ],
            "tasks": [
                "Define table columns and constraints",
                "Create migration scripts with reversible operations",
                "Document seed data requirements if any",
            ],
        }
        acceptance = [
            f"Postgres migration covering {name} entity is generated",
            "Unit tests cover migration up/down",
            "Context Card emitted summarizing schema",
        ]
        nodes.append(
            NodeSpec(
                domain=NodeDomain.db,
                title=title,
                description=description,
                instructions=instructions,
                acceptance_criteria=acceptance,
                contract_refs=[f"schema:{name}"],
            )
        )
    return nodes


