# TaskMaster Planner (Headless)

TaskMaster Planner is a headless planning/orchestration service that ingests a PRD and contract (OpenAPI/GraphQL) and produces a contract-anchored execution plan. Plans include dependency-tracked DAGs of atomic tasks, token budgets, research-aware complexity scores, and context artifacts for downstream code-generation agents.

The service is implemented as a Python 3.11 FastAPI application backed by PostgreSQL/pgvector (metadata + memory graph), Redis (indices/locks), and S3/MinIO (artifact storage). All LLM/tool calls are routed through Intelligence Studio.

## Core Capabilities

- **Contract-first planning** – imports OpenAPI 3.1 or GraphQL, enforces 100% endpoint/entity coverage, and auto-synthesizes repo-scaffold requests.
- **Front-end gating** – omits FE tasks when the PRD lacks UI/UX signals.
- **Graph-of-Thought candidate generation** – produces ≥3 candidate DAGs, persists UCB1 search traces, and records winner/fallback plans.
- **Research-aware complexity scoring (CCS)** – blends dependency load, surface area, novelty, ambiguity, and research friction with configurable weights and recommended subtask counts.
- **Window-safe token budgeting** – applies formal budgeting with headroom and automatic capping for every task payload.
- **Context Cards & Project Memory Graph** – records compact summaries after task execution so downstream agents pull only the slices they need.
- **REST API** – exposes `/plans`, `/plans/{id}`, `/plans/{id}/graph`, `/plans/{id}/tasks.json`, `/plans/{id}/report`, `/plans/{id}/rerun`, and `/executor/callbacks/{taskId}` endpoints with OpenAPI 3.1 documentation.

## Repository Layout

```
services/planner/
├── app/
│   ├── api/                 # FastAPI routers (plans, executor callbacks)
│   ├── auth/                # OIDC/JWT helpers
│   ├── domain/              # Planning, ingestion, complexity, budgeting
│   ├── observability/       # OpenTelemetry configuration
│   ├── persistence/         # SQLAlchemy models, DB session, artifact storage
│   └── main.py              # FastAPI application factory
├── migrations/              # (placeholder for Alembic migrations)
└── ...
```

Tests live in `tests/planner/` and exercise the public HTTP surface.

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 15 (production), pgvector extension
- Redis 7+
- MinIO/S3-compatible storage for artifacts
- Intelligence Studio flow URL + API key (all AI calls are proxied through this endpoint)

For local development the service defaults to a SQLite database and local file-backed artifact storage.

### Installation

```bash
# create & activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# install dependencies
default pip install -e .[dev]
```

### Configuration

Settings are provided through environment variables prefixed with `PLANNER_`.

```bash
export PLANNER_INTELLIGENCE_STUDIO__FLOW_URL="https://intelligence-studio.qa.apteancloud.dev/api/v1/run/..."
export PLANNER_INTELLIGENCE_STUDIO__API_KEY="your-key"
export PLANNER_STORAGE__DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/taskmaster"
export PLANNER_STORAGE__REDIS_URL="redis://localhost:6379/0"
export PLANNER_STORAGE__S3_BUCKET="taskmaster-artifacts"
export PLANNER_SECURITY__OIDC_ISSUER_URL="https://issuer/.well-known/openid-configuration"
export PLANNER_SECURITY__OIDC_AUDIENCE="planner-api"
```

Run the API locally:

```bash
uvicorn services.planner.app.main:app --reload
```

### API Overview

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/plans` | Ingest PRD + contract, return winner plan summary |
| GET    | `/plans/{id}` | Fetch plan summary with coverage metrics |
| GET    | `/plans/{id}/tasks.json` | Retrieve task list JSON (contract-first plan) |
| GET    | `/plans/{id}/graph` | Retrieve DAG nodes/edges |
| GET    | `/plans/{id}/report` | Retrieve plan report (JSON artifact) |
| POST   | `/plans/{id}/rerun` | Re-run planning with stored inputs |
| POST   | `/executor/callbacks/{taskId}` | Executor reflection hook with Context Card emission |

The OpenAPI 3.1 document is available at `/docs` (Swagger UI).

### Testing

```bash
pytest
```

Tests spin up the FastAPI app against a temporary SQLite database and validate plan creation, DAG generation, and executor callbacks.

### Migrations

Alembic migrations should be added under `migrations/` (not included in this snapshot). Production deployments must run migrations before exposing the API.

## Observability & Security

- OpenTelemetry tracing is wired with optional OTLP exporters.
- Structured error envelopes include remediation messages and correlation IDs.
- JWT validation uses OIDC client-credentials; role mapping gates privileged endpoints when an issuer is configured.
- Artifacts are content-hashed before upload to MinIO/S3.
- Audit logs persist planner actions with principal and correlation ID.

## License

MIT with Commons Clause – see [LICENSE](LICENSE).
