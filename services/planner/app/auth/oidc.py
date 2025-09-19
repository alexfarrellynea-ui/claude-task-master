"""OIDC token validation and RBAC helpers."""
from __future__ import annotations

import asyncio
from typing import Sequence

import httpx
from authlib.jose import JsonWebKey, jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import PlannerSettings, get_settings


class OIDCVerifier:
    """Validate JWT tokens using JWKS discovery."""

    def __init__(self, settings: PlannerSettings) -> None:
        self._settings = settings
        self._jwks: JsonWebKey | None = None
        self._lock = asyncio.Lock()
        self._security = HTTPBearer(auto_error=False)

    async def _get_jwks(self) -> JsonWebKey:
        async with self._lock:
            if self._jwks is not None:
                return self._jwks
            issuer = self._settings.security.oidc_issuer_url
            if not issuer:
                raise RuntimeError("OIDC issuer URL is not configured")
            jwks_url = issuer.rstrip("/") + "/.well-known/jwks.json"
            async with httpx.AsyncClient() as client:
                response = await client.get(jwks_url, timeout=10)
                response.raise_for_status()
            data = response.json()
            self._jwks = JsonWebKey.import_key_set(data)
            return self._jwks

    async def verify(self, credentials: HTTPAuthorizationCredentials | None, required_roles: Sequence[str]) -> dict:
        if not self._settings.security.oidc_issuer_url:
            # RBAC disabled in environment; allow request to proceed with placeholder claims
            return {"sub": "anonymous", "roles": ["ADM"]}
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

        token = credentials.credentials
        jwks = await self._get_jwks()
        try:
            claims = jwt.decode(token, jwks)
            claims.validate()
        except Exception as exc:  # pragma: no cover - error path
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

        issuer = self._settings.security.oidc_issuer_url
        audience = self._settings.security.oidc_audience
        if issuer and claims.get("iss") != issuer:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid issuer")
        if audience and audience not in set(claims.get("aud", []) if isinstance(claims.get("aud"), list) else [claims.get("aud")]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid audience")

        if required_roles:
            claim_name = self._settings.security.role_claim
            roles = claims.get(claim_name, [])
            if isinstance(roles, str):
                roles = [roles]
            if not set(required_roles).intersection(roles):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return claims

    async def __call__(self, required_roles: Sequence[str]) -> dict:
        credentials = await self._security(None)
        return await self.verify(credentials, required_roles)


_oidc_singleton: OIDCVerifier | None = None


def get_oidc_verifier() -> OIDCVerifier:
    global _oidc_singleton
    if _oidc_singleton is None:
        _oidc_singleton = OIDCVerifier(get_settings())
    return _oidc_singleton


def require_roles(*roles: str):
    async def dependency(credentials: HTTPAuthorizationCredentials = Security(HTTPBearer(auto_error=False))):
        verifier = get_oidc_verifier()
        return await verifier.verify(credentials, roles)

    return dependency


__all__ = ["require_roles", "get_oidc_verifier", "OIDCVerifier"]
