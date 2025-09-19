"""PRD and contract ingestion utilities."""
from __future__ import annotations

import hashlib
import json
import re
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
_GENERIC_HEADINGS = {
    "overview",
    "introduction",
    "summary",
    "goals",
    "objectives",
    "requirements",
    "scope",
    "non-goals",
    "appendix",
    "future work",
    "out of scope",
}
_DEFAULT_TAG = "Core"


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


def ingest(prd_text: str, contract_document: dict[str, Any] | None = None) -> IngestionResult:
    prd = parse_prd(prd_text)
    document = contract_document or synthesize_contract(prd)
    contract = load_contract(document)
    return IngestionResult(prd=prd, contract=contract)


@dataclass
class _EntitySpec:
    display: str
    plural_display: str
    schema_name: str
    path_segment: str
    param_name: str
    operation_singular: str
    operation_plural: str
    description: str
    tag: str
    constraints: list[str]


def synthesize_contract(prd: PRDArtifact) -> dict[str, Any]:
    """Construct a minimal OpenAPI 3.1 contract derived from a PRD."""

    tags = _derive_tags(prd)
    entities = _derive_entities(prd, tags)

    operation_ids: set[str] = set()
    paths: dict[str, Any] = {}
    schemas: dict[str, Any] = {}

    for entity in entities:
        schemas[entity.schema_name] = _build_schema(entity)
        _add_entity_operations(paths, entity, operation_ids)

    info_description = _compose_info_description(prd, entities)
    tag_definitions = [
        {"name": tag, "description": f"Derived from PRD section '{tag}'."}
        for tag in tags
    ]

    return {
        "openapi": "3.1.0",
        "info": {
            "title": prd.headings[0] if prd.headings else "Synthesized TaskMaster API",
            "version": "0.1.0",
            "description": info_description,
            "x-generated-by": "taskmaster.contract.synthesizer",
        },
        "tags": tag_definitions,
        "paths": paths,
        "components": {"schemas": schemas},
        "x-taskmaster-prd": {
            "headings": prd.headings,
            "hasUi": prd.has_ui,
            "glossaryCount": len(prd.glossary),
            "constraintCount": len(prd.constraints),
        },
    }


def _derive_tags(prd: PRDArtifact) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for heading in prd.headings:
        cleaned = heading.strip()
        if not cleaned:
            continue
        if cleaned.lower() in _GENERIC_HEADINGS:
            continue
        if cleaned not in seen:
            tags.append(cleaned)
            seen.add(cleaned)
    if not tags:
        tags = [_DEFAULT_TAG]
    return tags


def _derive_entities(prd: PRDArtifact, tags: list[str]) -> list[_EntitySpec]:
    entities: list[_EntitySpec] = []
    used_schema_names: set[str] = set()
    used_path_segments: set[str] = set()
    seen_keys: set[str] = set()

    def _register_entity(name: str, description: str) -> None:
        display = _normalize_display(name)
        key = display.lower()
        if not display or key in seen_keys:
            return
        seen_keys.add(key)

        plural_display = _pluralize_display(display)
        schema_name = _unique_name(_to_pascal(display), used_schema_names)
        path_segment = _unique_slug(_to_slug(plural_display), used_path_segments)
        param_name = f"{_to_camel(display)}Id"
        tag = _choose_tag(display, tags)
        constraints = _collect_constraints(prd.constraints, display, plural_display)

        entities.append(
            _EntitySpec(
                display=display,
                plural_display=plural_display,
                schema_name=schema_name,
                path_segment=path_segment,
                param_name=param_name,
                operation_singular=_to_pascal(display),
                operation_plural=_to_pascal(plural_display),
                description=description or f"{display} entity synthesized from PRD.",
                tag=tag,
                constraints=constraints,
            )
        )

    for entry in prd.glossary:
        term, _, desc = entry.partition(":")
        _register_entity(term.strip(), desc.strip())

    if not entities:
        for heading in prd.headings:
            cleaned = heading.strip()
            if not cleaned or cleaned.lower() in _GENERIC_HEADINGS:
                continue
            _register_entity(cleaned, f"Feature derived from PRD section '{cleaned}'.")
        if not entities:
            _register_entity("Core Resource", "Fallback entity synthesized from PRD text.")

    _distribute_remaining_constraints(prd.constraints, entities)
    return entities


def _distribute_remaining_constraints(constraints: list[str], entities: list[_EntitySpec]) -> None:
    if not constraints or not entities:
        return
    captured: set[str] = {constraint for entity in entities for constraint in entity.constraints}
    remaining = [line for line in constraints if line not in captured]
    if not remaining:
        return
    targets = [entity for entity in entities if not entity.constraints] or entities
    max_assignments = len(targets) * 2
    for idx, line in enumerate(remaining):
        if idx >= max_assignments:
            break
        targets[idx % len(targets)].constraints.append(line)


def _normalize_display(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text)
    if not parts:
        return ""
    return " ".join(part.capitalize() for part in parts)


def _pluralize_display(display: str) -> str:
    parts = display.split()
    if not parts:
        return display
    last = parts[-1]
    lower = last.lower()
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        plural_last = last[:-1] + "ies"
    elif lower.endswith(tuple(["s", "x", "z", "ch", "sh"])):
        plural_last = last + "es"
    else:
        plural_last = last + "s"
    return " ".join(parts[:-1] + [plural_last])


def _to_pascal(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text)
    if not parts:
        return "Resource"
    return "".join(part.capitalize() for part in parts)


def _to_slug(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text.lower())
    return "-".join(parts) or "resource"


def _to_camel(text: str) -> str:
    pascal = _to_pascal(text)
    if not pascal:
        return "resource"
    return pascal[0].lower() + pascal[1:]


def _unique_name(value: str, used: set[str]) -> str:
    candidate = value or "Resource"
    base = candidate
    index = 2
    while candidate in used:
        candidate = f"{base}{index}"
        index += 1
    used.add(candidate)
    return candidate


def _unique_slug(value: str, used: set[str]) -> str:
    candidate = value or "resource"
    base = candidate
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def _choose_tag(display: str, tags: list[str]) -> str:
    if not tags:
        return _DEFAULT_TAG
    display_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", display) if token}
    for tag in tags:
        tag_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", tag) if token}
        if display_tokens & tag_tokens:
            return tag
    return tags[0]


def _collect_constraints(constraints: list[str], display: str, plural_display: str) -> list[str]:
    if not constraints:
        return []
    names = {display.lower(), plural_display.lower()}
    tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9]+", f"{display} {plural_display}".lower())
        if len(token) >= 3
    }
    collected: list[str] = []
    for line in constraints:
        lowered = line.lower()
        if any(name in lowered for name in names) or any(token in lowered for token in tokens):
            collected.append(line)
    return collected[:4]


def _compose_info_description(prd: PRDArtifact, entities: list[_EntitySpec]) -> str:
    sections = ", ".join(prd.headings[:3]) if prd.headings else "general requirements"
    entity_names = ", ".join(entity.display for entity in entities)
    description_parts = [
        "Synthesized contract derived from product requirements document.",
        f"Key sections: {sections}.",
        f"Primary entities: {entity_names}.",
    ]
    if prd.has_ui:
        description_parts.append("PRD indicates user interface considerations.")
    return " ".join(description_parts)


def _build_schema(entity: _EntitySpec) -> dict[str, Any]:
    properties = {
        "id": {
            "type": "string",
            "description": f"Unique identifier for the {entity.display.lower()}.",
        },
        "name": {
            "type": "string",
            "description": f"Human readable name for the {entity.display.lower()}.",
        },
        "details": {
            "type": "string",
            "description": "Narrative details captured from PRD synthesis.",
        },
    }
    if entity.constraints:
        properties["status"] = {
            "type": "string",
            "description": "Lifecycle state constrained by PRD requirements.",
        }
    return {
        "type": "object",
        "description": entity.description,
        "properties": properties,
        "required": ["id", "name"],
        "additionalProperties": True,
        "x-prd-context": {
            "tag": entity.tag,
            "constraints": entity.constraints,
        },
    }


def _add_entity_operations(paths: dict[str, Any], entity: _EntitySpec, operation_ids: set[str]) -> None:
    base_path = f"/{entity.path_segment}"
    item_path = f"{base_path}/{{{entity.param_name}}}"

    paths.setdefault(base_path, {})
    paths.setdefault(item_path, {})

    list_op = _build_operation(
        operation_ids,
        f"list{entity.operation_plural}",
        summary=f"List {entity.plural_display}",
        description=_operation_description(entity),
        tag=entity.tag,
        responses={
            "200": {
                "description": f"List of {entity.plural_display}",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "array",
                            "items": {"$ref": f"#/components/schemas/{entity.schema_name}"},
                        }
                    }
                },
            }
        },
    )

    create_op = _build_operation(
        operation_ids,
        f"create{entity.operation_singular}",
        summary=f"Create {entity.display}",
        description=_operation_description(entity),
        tag=entity.tag,
        request_body={
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{entity.schema_name}"}
                }
            },
        },
        responses={
            "201": {
                "description": f"Created {entity.display}",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity.schema_name}"}
                    }
                },
            }
        },
    )

    get_op = _build_operation(
        operation_ids,
        f"get{entity.operation_singular}",
        summary=f"Get {entity.display}",
        description=_operation_description(entity),
        tag=entity.tag,
        parameters=[_build_path_parameter(entity)],
        responses={
            "200": {
                "description": f"{entity.display} details",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity.schema_name}"}
                    }
                },
            },
            "404": {"description": f"{entity.display} not found"},
        },
    )

    update_op = _build_operation(
        operation_ids,
        f"update{entity.operation_singular}",
        summary=f"Update {entity.display}",
        description=_operation_description(entity),
        tag=entity.tag,
        parameters=[_build_path_parameter(entity)],
        request_body={
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{entity.schema_name}"}
                }
            },
        },
        responses={
            "200": {
                "description": f"Updated {entity.display}",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity.schema_name}"}
                    }
                },
            },
            "404": {"description": f"{entity.display} not found"},
        },
    )

    paths[base_path]["get"] = list_op
    paths[base_path]["post"] = create_op
    paths[item_path]["get"] = get_op
    paths[item_path]["patch"] = update_op


def _build_operation(
    operation_ids: set[str],
    operation_id: str,
    *,
    summary: str,
    description: str,
    tag: str,
    responses: dict[str, Any],
    parameters: list[dict[str, Any]] | None = None,
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    op_id = _unique_operation_id(operation_id, operation_ids)
    operation: dict[str, Any] = {
        "operationId": op_id,
        "summary": summary,
        "description": description,
        "tags": [tag],
        "responses": responses,
        "x-generated-from-prd": True,
    }
    if parameters:
        operation["parameters"] = parameters
    if request_body:
        operation["requestBody"] = request_body
    constraint_extension: list[str] | None = None
    if "Key constraints:" in description:
        constraint_extension = [line.strip("- ") for line in description.splitlines() if line.strip().startswith("-")]
    if constraint_extension:
        operation["x-prd-constraints"] = constraint_extension
    return operation


def _unique_operation_id(operation_id: str, used: set[str]) -> str:
    base = operation_id
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}{index}"
        index += 1
    used.add(candidate)
    return candidate


def _build_path_parameter(entity: _EntitySpec) -> dict[str, Any]:
    return {
        "name": entity.param_name,
        "in": "path",
        "required": True,
        "description": f"Identifier for the {entity.display.lower()}.",
        "schema": {"type": "string"},
    }


def _operation_description(entity: _EntitySpec) -> str:
    parts: list[str] = []
    if entity.description:
        parts.append(entity.description)
    if entity.constraints:
        constraint_lines = "\n".join(f"- {line}" for line in entity.constraints)
        parts.append(f"Key constraints:\n{constraint_lines}")
    if not parts:
        parts.append(f"Synthesized endpoint for managing {entity.display.lower()}.")
    return "\n\n".join(parts)


