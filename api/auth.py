"""API-key authentication and server-side role authorization."""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import Settings

Role = Literal["viewer", "operator", "evaluator", "administrator"]
ROLE_ORDER: tuple[Role, ...] = ("viewer", "operator", "evaluator", "administrator")
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity and explicitly assigned roles."""

    subject: str
    roles: frozenset[Role]

    def can(self, role: Role) -> bool:
        """Return whether any assigned role meets the requested privilege level."""

        required = ROLE_ORDER.index(role)
        return any(ROLE_ORDER.index(candidate) >= required for candidate in self.roles)


class APIKeyAuthenticator:
    """Validate bearer keys from a JSON configuration without logging secrets."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.auth_enabled
        self.records = self._parse(settings.api_keys_json)

    @staticmethod
    def _parse(raw: str) -> dict[str, Principal]:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("API_KEYS_JSON must contain valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("API_KEYS_JSON must be an object keyed by API key")
        records: dict[str, Principal] = {}
        for key, value in payload.items():
            if not isinstance(key, str) or not key:
                raise ValueError("API key entries must use non-empty string keys")
            if isinstance(value, str):
                subject, raw_roles = key[-8:], [value]
            elif isinstance(value, dict):
                subject = str(value.get("subject") or key[-8:])
                raw_roles = value.get("roles", [])
            else:
                raise ValueError("API key records must be a role string or object")
            roles = frozenset(str(role) for role in raw_roles)
            if not roles or not roles.issubset(ROLE_ORDER):
                raise ValueError("API key roles must use the documented role names")
            records[key] = Principal(subject=subject, roles=roles)  # type: ignore[arg-type]
        return records

    def authenticate(self, token: str | None) -> Principal:
        """Return a demo administrator when auth is disabled, otherwise validate a key."""

        if not self.enabled:
            return Principal("local-demo", frozenset({"administrator"}))
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="bearer API key is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        for candidate, principal in self.records.items():
            if hmac.compare_digest(candidate, token):
                return principal
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def dependency(self, minimum_role: Role):
        """Build a FastAPI dependency that enforces a minimum role."""

        def require(
            credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
        ) -> Principal:
            principal = self.authenticate(credentials.credentials if credentials else None)
            if not principal.can(minimum_role):
                raise HTTPException(status_code=403, detail="role does not permit this operation")
            return principal

        return require
