"""PRD and contract ingestion utilities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from openapi_spec_validator import validate_spec


@dataclass
class PRDArtifact:
    text: str
    headings: list[str]
    glossary: list[str]
    constraints: list[str]
    has_ui: bool


@dataclass
class Operation:
    path: str
    method: str
    operation_id: str
    summary: str
    tags: list[str]


@dataclass
class ContractArtifact:
    raw: dict[str, Any]
    operations: list[Operation]
    schemas: dict[str, Any]
    hash: str


@dataclass
class IngestionResult:
    prd: PRDArtifact
    contract: ContractArtifact


_UI_KEYWORDS = {"ui", "screen", "frontend", "interface", "page", "dashboard", "button", "form"}


def parse_prd(text: str) -> PRDArtifact:
    lines = text.splitlines()
    headings: list[str] = []
    glossary: list[str] = []
    constraints: list[str] = []
    has_ui = False
    glossary_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("glossary"):
            glossary_section = True
            continue
        if stripped.startswith("#"):
            heading = stripped.lstrip("# ")
            headings.append(heading)
            glossary_section = False
        if glossary_section and ":" in stripped:
            glossary.append(stripped)
        if any(keyword in stripped.lower() for keyword in ("must", "shall", "should")):
            constraints.append(stripped)
        if any(keyword in stripped.lower() for keyword in _UI_KEYWORDS):
            has_ui = True

    return PRDArtifact(text=text, headings=headings, glossary=glossary, constraints=constraints, has_ui=has_ui)


def _extract_operations(openapi: dict[str, Any]) -> list[Operation]:
    operations: list[Operation] = []
    for path, methods in openapi.get("paths", {}).items():
        for method, spec in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            op_id = spec.get("operationId") or f"{method}_{path.strip('/').replace('/', '_')}"
            tags = spec.get("tags", [])
            summary = spec.get("summary") or spec.get("description", "")
            operations.append(Operation(path=path, method=method.upper(), operation_id=op_id, summary=summary, tags=tags))
    return operations


def load_contract(document: dict[str, Any]) -> ContractArtifact:
    validate_spec(document)
    operations = _extract_operations(document)
    schemas = document.get("components", {}).get("schemas", {})
    digest = hashlib.sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()
    return ContractArtifact(raw=document, operations=operations, schemas=schemas, hash=digest)


def ingest(prd_text: str, contract_document: dict[str, Any]) -> IngestionResult:
    prd = parse_prd(prd_text)
    contract = load_contract(contract_document)
    return IngestionResult(prd=prd, contract=contract)


