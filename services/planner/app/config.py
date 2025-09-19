"""Application configuration using Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseModel):
    oidc_issuer_url: str | None = None
    oidc_audience: str | None = None
    role_claim: str = "roles"
    webhook_hmac_secret: str | None = None
    max_request_bytes: int = 10_000_000
    rate_limit_qps: int = 5


class PlannerTuning(BaseModel):
    window_headroom_pct: float = Field(default=0.1, ge=0.05, le=0.1)
    default_model_window: int = 200_000
    default_model_class: str = "Class-200K"
    optional_model_class: str | None = "Class-1M"
    allow_research: bool = False
    ucb1_c: float = Field(default=2 ** 0.5)
    search_max_iters: int = 128
    search_walltime_ms: int = 60_000
    abort_if_nodes_gt: int = 10_000
    token_budget_floor: int = 2_000

    model_config = SettingsConfigDict(populate_by_name=True)


class ObservabilitySettings(BaseModel):
    otel_service_name: str = "taskmaster-planner"
    otel_exporter_otlp_endpoint: str | None = None
    log_level: str = "INFO"


class IntelligenceStudioSettings(BaseModel):
    flow_url: str = Field(
        default="https://intelligence-studio.qa.apteancloud.dev/api/v1/run/d80f7013-474a-4946-9c67-9c014e5d763d",
        description="Base URL for Intelligence Studio flow execution",
    )
    api_key: str = Field(default="", description="API key for Intelligence Studio access")


class StorageSettings(BaseModel):
    database_url: str = Field(
        default="sqlite+aiosqlite:///./taskmaster.db",
        description="SQLAlchemy async database URL (Postgres 15 in production)",
    )
    redis_url: str | None = None
    s3_endpoint: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None


class PlannerSettings(BaseSettings):
    security: SecuritySettings = SecuritySettings()
    tuning: PlannerTuning = PlannerTuning()
    observability: ObservabilitySettings = ObservabilitySettings()
    intelligence_studio: IntelligenceStudioSettings = IntelligenceStudioSettings()
    storage: StorageSettings = StorageSettings()
    environment: Literal["dev", "qa", "prod"] | str = "dev"

    model_config = SettingsConfigDict(env_nested_delimiter="__", env_prefix="PLANNER_", case_sensitive=False)


@lru_cache(maxsize=1)
def get_settings(**kwargs: Any) -> PlannerSettings:
    """Return cached settings instance."""
    return PlannerSettings(**kwargs)


__all__ = ["PlannerSettings", "get_settings"]
