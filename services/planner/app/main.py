"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import executor_callbacks, plans
from .config import get_settings
from .observability.otel import configure_telemetry
from .persistence.db import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TaskMaster Planner",
        version="0.1.0",
        openapi_version="3.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    configure_telemetry()

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - FastAPI lifecycle
        await init_db()

    @app.exception_handler(Exception)
    async def _generic_exception_handler(request: Request, exc: Exception):  # pragma: no cover - fallback
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": str(exc),
                "remediation": "Contact TaskMaster support with correlation ID",
            },
        )

    app.include_router(plans.router)
    app.include_router(executor_callbacks.router)

    @app.get("/healthz")
    async def healthcheck():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()


__all__ = ["app", "create_app"]
