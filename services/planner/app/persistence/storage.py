"""Artifact storage helpers (S3/MinIO)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import aioboto3

from ..config import get_settings


class ArtifactStorage:
    """Persist artifacts to S3/MinIO using content-hash identifiers."""

    def __init__(self) -> None:
        self._settings = get_settings().storage

    async def put_json(self, data: dict[str, Any]) -> str:
        """Store JSON data and return content-hash reference."""
        payload = json.dumps(data, sort_keys=True).encode("utf-8")
        return await self._put_bytes(payload, suffix=".json")

    async def _put_bytes(self, payload: bytes, suffix: str = "") -> str:
        hasher = hashlib.sha256()
        hasher.update(payload)
        digest = hasher.hexdigest()
        key = f"artifacts/{digest}{suffix}"

        if not self._settings.s3_bucket:
            # Dev mode: write to local file system for traceability
            path = f"./.artifacts/{digest}{suffix}"
            import os

            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(payload)
            return f"file://{path}"

        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint,
            region_name=self._settings.s3_region,
        ) as client:
            await client.put_object(Bucket=self._settings.s3_bucket, Key=key, Body=payload)
        return f"s3://{self._settings.s3_bucket}/{key}"


__all__ = ["ArtifactStorage"]
