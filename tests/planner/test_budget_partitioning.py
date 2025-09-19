import pathlib
import sys
from types import ModuleType, SimpleNamespace

APP_PATH = pathlib.Path(__file__).resolve().parents[2] / "services" / "planner" / "app"
stub = ModuleType("services.planner.app")
stub.__path__ = [str(APP_PATH)]
sys.modules.setdefault("services.planner.app", stub)
import services.planner as planner_pkg
planner_pkg.app = stub

import pytest

from services.planner.app.domain.budget import plan_budgets
from services.planner.app.domain.types import EdgeSpec, NodeSpec
from services.planner.app.persistence.models import NodeDomain


@pytest.fixture
def tuned_settings(monkeypatch):
    settings = SimpleNamespace(
        tuning=SimpleNamespace(
            default_model_window=500,
            window_headroom_pct=0.2,
            token_budget_floor=64,
        )
    )
    monkeypatch.setattr(
        "services.planner.app.domain.budget.get_settings", lambda: settings
    )
    return settings


def _heavy_node(title: str, task_count: int, criteria_count: int) -> NodeSpec:
    description = " ".join(["detailed"] * 120)
    tasks = [f"Task {i}" for i in range(task_count)]
    criteria = [f"Criteria {i}" for i in range(criteria_count)]
    return NodeSpec(
        domain=NodeDomain.be,
        title=title,
        description=description,
        instructions={"tasks": tasks, "contractOps": []},
        acceptance_criteria=criteria,
    )


def test_plan_budgets_splits_oversized_node(tuned_settings):
    node = _heavy_node("Massive feature", task_count=12, criteria_count=6)

    result = plan_budgets([node], [])

    assert len(result.nodes) > 1, "Expected node to be partitioned"
    assert result.budget.capacity == int(
        tuned_settings.tuning.default_model_window
        * (1 - tuned_settings.tuning.window_headroom_pct)
    )
    assert result.budget.violations == []
    assert all(budget <= result.budget.capacity for budget in result.budget.budgets)

    aggregated_tasks = sum(len(n.instructions.get("tasks", [])) for n in result.nodes)
    aggregated_criteria = sum(len(n.acceptance_criteria) for n in result.nodes)

    assert aggregated_tasks == len(node.instructions["tasks"])
    assert aggregated_criteria == len(node.acceptance_criteria)


def test_plan_budgets_rewires_edges_for_partition(tuned_settings):
    start = NodeSpec(
        domain=NodeDomain.db,
        title="Initialize schema",
        description="prep",
        instructions={"tasks": ["bootstrap"], "contractOps": []},
        acceptance_criteria=["tables defined"],
    )
    oversized = _heavy_node("Backend epic", task_count=9, criteria_count=5)
    end = NodeSpec(
        domain=NodeDomain.test,
        title="Validate flows",
        description="ensure coverage",
        instructions={"tasks": ["write tests"], "contractOps": []},
        acceptance_criteria=["coverage met"],
    )

    edges = [
        EdgeSpec(from_index=0, to_index=1, description="Start to backend"),
        EdgeSpec(from_index=1, to_index=2, description="Backend to tests"),
    ]

    result = plan_budgets([start, oversized, end], edges)

    capacity = result.budget.capacity
    assert all(budget <= capacity for budget in result.budget.budgets)
    assert result.budget.violations == []

    titles = [node.title for node in result.nodes]
    start_index = titles.index(start.title)
    end_index = titles.index(end.title)
    part_indices = [
        idx for idx, node in enumerate(result.nodes) if node.title.startswith("Backend epic (part")
    ]

    assert part_indices, "Backend epic should have been partitioned"

    # All sequential partitions must be wired together.
    edge_pairs = {(edge.from_index, edge.to_index): edge.description for edge in result.edges}
    for current, nxt in zip(part_indices, part_indices[1:]):
        assert (
            current,
            nxt,
        ) in edge_pairs, "Expected sequential dependency between partitioned nodes"
        assert edge_pairs[(current, nxt)] == "Partition order for Backend epic"

    # Upstream and downstream dependencies should attach to first/last parts.
    assert (start_index, part_indices[0]) in edge_pairs
    assert edge_pairs[(start_index, part_indices[0])] == "Start to backend"
    assert (part_indices[-1], end_index) in edge_pairs
    assert edge_pairs[(part_indices[-1], end_index)] == "Backend to tests"

