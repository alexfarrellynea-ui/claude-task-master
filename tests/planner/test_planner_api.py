import json
import os
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("PLANNER_STORAGE__DATABASE_URL", "sqlite+aiosqlite:///./test_planner.db")
os.environ.setdefault("PLANNER_INTELLIGENCE_STUDIO__API_KEY", "test-key")
os.environ.setdefault("PLANNER_INTELLIGENCE_STUDIO__FLOW_URL", "http://localhost:9999/mock")

from services.planner.app.main import app  # noqa: E402
from services.planner.app.persistence.db import init_db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    if os.path.exists("test_planner.db"):
        os.remove("test_planner.db")
    await init_db()
    yield
    if os.path.exists("test_planner.db"):
        os.remove("test_planner.db")


def sample_contract() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Sample API", "version": "1.0.0"},
        "paths": {
            "/widgets": {
                "get": {"operationId": "listWidgets", "summary": "List widgets"},
                "post": {"operationId": "createWidget", "summary": "Create widget"},
            }
        },
        "components": {
            "schemas": {
                "Widget": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_create_plan_and_retrieve():
    request_payload = {
        "projectId": "proj-123",
        "runId": str(uuid.uuid4()),
        "prd": {"text": "# Overview\nThe service manages widgets."},
        "contract": {"document": sample_contract()},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/plans", json=request_payload)
        assert response.status_code == 201, response.text
        data = response.json()
        plan_id = data["id"]
        assert data["coverage"]["missingOperations"] == []

        tasks_resp = await client.get(f"/plans/{plan_id}/tasks.json")
        assert tasks_resp.status_code == 200
        tasks = tasks_resp.json()
        assert any(task["title"].startswith("Request: provision") for task in tasks)

        graph_resp = await client.get(f"/plans/{plan_id}/graph")
        assert graph_resp.status_code == 200
        graph = graph_resp.json()
        assert graph["nodes"]

        report_resp = await client.get(f"/plans/{plan_id}/report")
        assert report_resp.status_code == 200


@pytest.mark.asyncio
async def test_executor_callback_creates_context_card():
    request_payload = {
        "projectId": "proj-123",
        "runId": str(uuid.uuid4()),
        "prd": {"text": "# Overview\nNo UI."},
        "contract": {"document": sample_contract()},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/plans", json=request_payload)
        plan_id = create_resp.json()["id"]
        tasks_resp = await client.get(f"/plans/{plan_id}/tasks.json")
        node_id = tasks_resp.json()[0]["id"]
        callback_resp = await client.post(
            f"/executor/callbacks/{node_id}",
            json={"status": "completed", "artifactsOut": [{"ref": "s3://bucket/artifact"}]},
        )
        assert callback_resp.status_code == 200
        payload = callback_resp.json()
        assert "contextCardId" in payload


