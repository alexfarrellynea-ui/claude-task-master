"""High-level plan graph construction."""
from __future__ import annotations

from typing import List

from ..persistence.models import NodeDomain
from .deps_be import build_backend_nodes
from .deps_db import build_db_nodes
from .deps_fe import build_frontend_nodes
from .ingest import IngestionResult
from .types import EdgeSpec, NodeSpec, PlanBuildResult


def build_plan(ingestion: IngestionResult) -> PlanBuildResult:
    nodes: List[NodeSpec] = []
    edges: List[EdgeSpec] = []

    # Repo scaffold request must be first node
    repo_node = NodeSpec(
        domain=NodeDomain.package,
        title="Request: provision repository scaffold",
        description="Request infra to prepare Git repository scaffold with CI/CD hooks and base directories.",
        instructions={
            "tasks": [
                "Provision repository with FastAPI service skeleton",
                "Set up infrastructure IaC directories",
                "Bootstrap Alembic migrations and Dockerfiles",
            ],
            "contractOps": [],
        },
        acceptance_criteria=[
            "Repository skeleton ready with FastAPI app",
            "Continuous integration pipeline stub available",
            "Secrets placeholders documented",
        ],
        artifacts_out=[{"type": "repo-scaffold", "description": "Repository template request"}],
    )
    nodes.append(repo_node)
    repo_idx = 0

    db_nodes = build_db_nodes(ingestion.contract)
    db_start = len(nodes)
    nodes.extend(db_nodes)

    for offset in range(len(db_nodes)):
        edges.append(EdgeSpec(from_index=repo_idx, to_index=db_start + offset, description="Repo ready"))

    backend_nodes = build_backend_nodes(ingestion.contract)
    be_start = len(nodes)
    nodes.extend(backend_nodes)

    for offset in range(len(backend_nodes)):
        for db_idx in range(db_start, db_start + len(db_nodes)):
            edges.append(EdgeSpec(from_index=db_idx, to_index=be_start + offset, description="DB schema available"))

    fe_nodes: List[NodeSpec] = []
    if ingestion.prd.has_ui:
        fe_nodes = build_frontend_nodes(ingestion.contract)
        fe_start = len(nodes)
        nodes.extend(fe_nodes)
        for offset in range(len(fe_nodes)):
            for be_idx in range(be_start, be_start + len(backend_nodes)):
                edges.append(EdgeSpec(from_index=be_idx, to_index=fe_start + offset, description="API ready"))
    else:
        fe_start = len(nodes)

    test_node = NodeSpec(
        domain=NodeDomain.test,
        title="Construct integration and contract tests",
        description="Author integration tests ensuring API and data contract coverage with regression hooks.",
        instructions={
            "tasks": [
                "Generate contract conformance tests",
                "Create end-to-end scenarios across domains",
                "Produce coverage diff artifact",
            ],
            "contractOps": [op.operation_id for op in ingestion.contract.operations],
        },
        acceptance_criteria=[
            "100% contract operations exercised",
            "Regression matrix documented",
            "Test artifacts stored with hash references",
        ],
    )
    test_idx = len(nodes)
    nodes.append(test_node)

    for be_idx in range(be_start, be_start + len(backend_nodes)):
        edges.append(EdgeSpec(from_index=be_idx, to_index=test_idx, description="Backend complete"))
    if fe_nodes:
        for fe_idx in range(fe_start, fe_start + len(fe_nodes)):
            edges.append(EdgeSpec(from_index=fe_idx, to_index=test_idx, description="UI ready"))
    for db_idx in range(db_start, db_start + len(db_nodes)):
        edges.append(EdgeSpec(from_index=db_idx, to_index=test_idx, description="DB migrations ready"))

    package_node = NodeSpec(
        domain=NodeDomain.package,
        title="Finalize deployment package",
        description="Assemble deployment manifests, Helm chart updates, and release plan with rollback procedures.",
        instructions={
            "tasks": [
                "Produce Helm values and Terraform diffs",
                "Update OTEL + metrics dashboards",
                "Document release readiness and runbooks",
            ],
            "contractOps": [],
        },
        acceptance_criteria=[
            "Deployment artifacts content-hashed and stored",
            "Operational readiness checklist signed",
            "Audit log entry generated with correlation ID",
        ],
    )
    package_idx = len(nodes)
    nodes.append(package_node)
    edges.append(EdgeSpec(from_index=test_idx, to_index=package_idx, description="Tests green"))

    return PlanBuildResult(nodes=nodes, edges=edges)


__all__ = ["build_plan"]
