# TaskMaster Planner (SPEC-001)

This repository now contains the headless TaskMaster Planner service described in SPEC-001 / SPEC-001-vNext. It replaces the original Node.js CLI with a Python 3.11 FastAPI backend that produces contract-anchored execution plans for downstream coding agents.

## Highlights

- Contract-first planning with OpenAPI 3.1/GraphQL ingestion
- Window-safe DAG generation across DB/BE/FE/Test/Package domains
- Research-aware complexity scoring (CCS) and subtask recommendations
- Context Card orchestration and executor webhook bridge
- Intelligence Studio integration for all LLM/tool calls

See [README.md](README.md) for setup instructions and API details.
