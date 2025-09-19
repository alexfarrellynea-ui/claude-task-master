"""Token budgeting utilities and partitioning helpers."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil
from typing import Dict, Iterable, List, Sequence

from ..config import get_settings
from .types import EdgeSpec, NodeSpec


@dataclass
class BudgetResult:
    """Summary of per-node token budgets."""

    budgets: list[int]
    capacity: int
    violations: list[int]


@dataclass
class PlanBudgetingResult:
    """Container for updated plan graph and associated budget data."""

    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    budget: BudgetResult


def estimate_tokens(text: str) -> int:
    return max(32, int(len(text.split()) * 1.5) + 128)


def _estimate_node_budget(node: NodeSpec, floor: int) -> int:
    estimate = estimate_tokens(node.description)
    estimate += 40 * len(node.instructions.get("tasks", []))
    estimate += 20 * len(node.acceptance_criteria)
    return max(estimate, floor)


def _split_sequence(seq: Sequence[str], parts: int) -> list[list[str]]:
    if parts <= 0:
        return [[]]
    total = len(seq)
    base = total // parts
    remainder = total % parts
    result: list[list[str]] = []
    index = 0
    for i in range(parts):
        size = base + (1 if i < remainder else 0)
        if size <= 0:
            result.append([])
            continue
        result.append(list(seq[index : index + size]))
        index += size
    while len(result) < parts:
        result.append([])
    return result


def _fit_words_to_capacity(
    words: Sequence[str],
    capacity: int,
    task_count: int,
    criteria_count: int,
    floor: int,
) -> list[str]:
    if capacity <= 0:
        return []

    def estimate_with_count(word_count: int) -> int:
        desc_tokens = estimate_tokens(" ".join(words[:word_count])) if word_count else estimate_tokens("")
        # estimate_tokens already includes baseline for the provided words.
        total = desc_tokens + task_count * 40 + criteria_count * 20
        return max(total, floor)

    low, high = 0, len(words)
    best: list[str] = []
    while low <= high:
        mid = (low + high) // 2
        budget = estimate_with_count(mid)
        if budget <= capacity:
            best = list(words[:mid])
            low = mid + 1
        else:
            high = mid - 1

    return best


def _partition_node(node: NodeSpec, capacity: int, floor: int) -> list[tuple[NodeSpec, int]]:
    base_budget = _estimate_node_budget(node, floor)
    if base_budget <= capacity:
        return [(node, base_budget)]

    tasks = list(node.instructions.get("tasks", []))
    acceptance = list(node.acceptance_criteria)
    desc_words = node.description.split()

    required_parts = max(2, ceil(base_budget / capacity))
    max_parts = min(
        128,
        max(
            required_parts * 2,
            len(tasks) + len(acceptance) if tasks or acceptance else required_parts,
            len(desc_words) if desc_words else required_parts,
        ),
    )
    summary_words = desc_words[: min(len(desc_words), 40)] if desc_words else []

    for part_count in range(required_parts, max_parts + 1):
        desc_chunks = _split_sequence(desc_words, part_count)
        task_chunks = _split_sequence(tasks, part_count)
        criteria_chunks = _split_sequence(acceptance, part_count)
        partitions: list[tuple[NodeSpec, int]] = []
        valid = True
        for idx in range(part_count):
            part_tasks = list(task_chunks[idx])
            part_criteria = list(criteria_chunks[idx])
            note_words: list[str] = []
            if part_count > 1:
                note_words = (
                    f"Subtask {idx + 1} of {part_count} continuing {node.title}."
                ).split()
            base_words = desc_chunks[idx] if desc_chunks[idx] else summary_words
            words_for_partition = list(base_words) + note_words
            fitted_words = _fit_words_to_capacity(
                words_for_partition,
                capacity,
                len(part_tasks),
                len(part_criteria),
                floor,
            )
            if not fitted_words and words_for_partition:
                fitted_words = list(words_for_partition[:1])
            description = " ".join(fitted_words).strip()
            instructions = deepcopy(node.instructions)
            instructions["tasks"] = part_tasks
            part_node = NodeSpec(
                domain=node.domain,
                title=f"{node.title} (part {idx + 1} of {part_count})",
                description=description,
                instructions=instructions,
                acceptance_criteria=part_criteria,
                artifacts_in=deepcopy(node.artifacts_in),
                artifacts_out=deepcopy(node.artifacts_out),
                contract_refs=list(node.contract_refs),
                requirements_refs=list(node.requirements_refs),
            )
            part_budget = _estimate_node_budget(part_node, floor)
            if part_budget > capacity:
                valid = False
                break
            partitions.append((part_node, part_budget))
        if valid and partitions:
            return partitions

    # Final fallback: attempt a greedy assignment to ensure coverage.
    partitions: list[tuple[NodeSpec, int]] = []
    remaining_tasks = list(tasks)
    remaining_criteria = list(acceptance)
    remaining_words = list(desc_words)
    part_index = 0
    while remaining_tasks or remaining_criteria or remaining_words:
        part_index += 1
        part_tasks: list[str] = []
        part_criteria: list[str] = []
        part_words: list[str] = []
        changed = True
        while changed:
            changed = False
            if remaining_tasks:
                tentative_tasks = part_tasks + [remaining_tasks[0]]
                budget = _estimate_budget_from_counts(len(part_words), len(tentative_tasks), len(part_criteria), floor)
                if budget <= capacity:
                    part_tasks.append(remaining_tasks.pop(0))
                    changed = True
            if remaining_criteria:
                tentative_criteria = part_criteria + [remaining_criteria[0]]
                budget = _estimate_budget_from_counts(len(part_words), len(part_tasks), len(tentative_criteria), floor)
                if budget <= capacity:
                    part_criteria.append(remaining_criteria.pop(0))
                    changed = True
            if remaining_words:
                tentative_words = part_words + [remaining_words[0]]
                budget = _estimate_budget_from_counts(len(tentative_words), len(part_tasks), len(part_criteria), floor)
                if budget <= capacity:
                    part_words.append(remaining_words.pop(0))
                    changed = True
        if not (part_tasks or part_criteria or part_words):
            # Cannot assign more content without exceeding capacity; break to avoid infinite loop.
            break
        instructions = deepcopy(node.instructions)
        instructions["tasks"] = part_tasks
        description_words = part_words if part_words else summary_words
        note = f"Subtask {part_index} of partition for {node.title}.".split()
        description_words = list(description_words) + note
        fitted = _fit_words_to_capacity(description_words, capacity, len(part_tasks), len(part_criteria), floor)
        description = " ".join(fitted).strip()
        part_node = NodeSpec(
            domain=node.domain,
            title=f"{node.title} (part {part_index})",
            description=description,
            instructions=instructions,
            acceptance_criteria=part_criteria,
            artifacts_in=deepcopy(node.artifacts_in),
            artifacts_out=deepcopy(node.artifacts_out),
            contract_refs=list(node.contract_refs),
            requirements_refs=list(node.requirements_refs),
        )
        part_budget = _estimate_node_budget(part_node, floor)
        partitions.append((part_node, min(part_budget, capacity)))

    if not partitions:
        return [(node, min(base_budget, capacity))]
    return partitions


def _estimate_budget_from_counts(word_count: int, task_count: int, criteria_count: int, floor: int) -> int:
    dummy_text = " ".join(["token"] * word_count)
    desc_tokens = estimate_tokens(dummy_text)
    total = desc_tokens + task_count * 40 + criteria_count * 20
    return max(total, floor)


def _rewire_edges(
    edges: Iterable[EdgeSpec],
    mapping: Dict[int, list[int]],
    original_nodes: Sequence[NodeSpec],
    new_nodes: Sequence[NodeSpec],
) -> list[EdgeSpec]:
    new_edges: list[EdgeSpec] = []
    for edge in edges:
        from_indices = mapping.get(edge.from_index)
        to_indices = mapping.get(edge.to_index)
        if not from_indices or not to_indices:
            continue
        new_edges.append(
            EdgeSpec(
                from_index=from_indices[-1],
                to_index=to_indices[0],
                description=edge.description,
                artifact_type=edge.artifact_type,
            )
        )

    for original_index, new_indices in mapping.items():
        if len(new_indices) <= 1:
            continue
        for current, nxt in zip(new_indices, new_indices[1:]):
            new_edges.append(
                EdgeSpec(
                    from_index=current,
                    to_index=nxt,
                    description=f"Partition order for {original_nodes[original_index].title}",
                    artifact_type=None,
                )
            )

    return new_edges


def plan_budgets(nodes: List[NodeSpec], edges: Sequence[EdgeSpec] | None = None) -> PlanBudgetingResult:
    settings = get_settings()
    capacity = int(settings.tuning.default_model_window * (1 - settings.tuning.window_headroom_pct))
    token_floor = settings.tuning.token_budget_floor

    partitions_per_node = [_partition_node(node, capacity, token_floor) for node in nodes]

    new_nodes: list[NodeSpec] = []
    budgets: list[int] = []
    index_mapping: Dict[int, list[int]] = {}
    for original_index, partition in enumerate(partitions_per_node):
        start = len(new_nodes)
        for part_node, part_budget in partition:
            new_nodes.append(part_node)
            budgets.append(part_budget)
        index_mapping[original_index] = list(range(start, len(new_nodes)))

    violations = [idx for idx, budget in enumerate(budgets) if budget > capacity]
    new_edges = _rewire_edges(edges or [], index_mapping, nodes, new_nodes)

    budget_result = BudgetResult(budgets=budgets, capacity=capacity, violations=violations)
    return PlanBudgetingResult(nodes=new_nodes, edges=new_edges, budget=budget_result)


__all__ = ["BudgetResult", "PlanBudgetingResult", "estimate_tokens", "plan_budgets"]


