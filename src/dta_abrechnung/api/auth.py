from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from ..security import ActorType, AuditContext, PrincipalRole


class TokenKind(StrEnum):
    USER = "user"
    SERVICE = "service"


@dataclass(slots=True, frozen=True)
class PrincipalClaims:
    subject: str
    actor_type: ActorType
    roles: frozenset[PrincipalRole]
    token_kind: TokenKind
    tenant_id: str | None
    source_system: str
    email: str | None = None


@dataclass(slots=True, frozen=True)
class AuthContext:
    subject: str
    actor_type: ActorType
    roles: frozenset[PrincipalRole]
    token_kind: TokenKind
    tenant_id: str | None
    source_system: str
    request_id: str
    email: str | None = None

    @classmethod
    def from_claims(cls, claims: PrincipalClaims, request_id: str) -> "AuthContext":
        return cls(
            subject=claims.subject,
            actor_type=claims.actor_type,
            roles=claims.roles,
            token_kind=claims.token_kind,
            tenant_id=claims.tenant_id,
            source_system=claims.source_system,
            request_id=request_id,
            email=claims.email,
        )

    def has_role(self, *roles: PrincipalRole) -> bool:
        return any(role in self.roles for role in roles)

    def ensure_tenant_access(self, tenant_id: str | None) -> None:
        if self.has_role(PrincipalRole.PLATFORM_ADMIN):
            return
        if tenant_id is None:
            raise PermissionError("Tenant-scoped access requires a tenant_id")
        if self.tenant_id != tenant_id:
            raise PermissionError("Token is not authorized for this tenant")

    def to_audit_context(
        self,
        reason: str | None = None,
        legal_basis: str | None = None,
        tenant_id: str | None = None,
    ) -> AuditContext:
        return AuditContext(
            actor_id=self.subject,
            actor_type=self.actor_type,
            request_id=self.request_id,
            source_system=self.source_system,
            tenant_id=tenant_id if tenant_id is not None else self.tenant_id,
            reason=reason,
            legal_basis=legal_basis,
        )


class JwtCodec:
    def __init__(self, issuer: str, audience: str, signing_key: str) -> None:
        self.issuer = issuer
        self.audience = audience
        self.signing_key = signing_key.encode("utf-8")

    def issue_token(
        self,
        *,
        subject: str,
        actor_type: ActorType,
        roles: set[PrincipalRole] | frozenset[PrincipalRole],
        token_kind: TokenKind,
        source_system: str,
        tenant_id: str | None = None,
        email: str | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": subject,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
            "actor_type": actor_type.value,
            "roles": sorted(role.value for role in roles),
            "token_kind": token_kind.value,
            "source_system": source_system,
        }
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id
        if email is not None:
            payload["email"] = email
        return self._encode(payload)

    def decode(self, token: str) -> PrincipalClaims:
        try:
            header_segment, payload_segment, signature_segment = token.split(".")
        except ValueError as exc:
            raise ValueError("Malformed JWT token") from exc
        try:
            signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
            expected = _b64url_encode(hmac.new(self.signing_key, signing_input, hashlib.sha256).digest())
            if not hmac.compare_digest(expected, signature_segment):
                raise ValueError("Invalid token signature")
            header = json.loads(_b64url_decode(header_segment))
            if header.get("alg") != "HS256":
                raise ValueError("Unsupported JWT algorithm")
            payload = json.loads(_b64url_decode(payload_segment))
            if payload.get("iss") != self.issuer:
                raise ValueError("Invalid token issuer")
            if payload.get("aud") != self.audience:
                raise ValueError("Invalid token audience")
            expires_at = int(payload.get("exp", 0))
            if expires_at < int(datetime.now(UTC).timestamp()):
                raise ValueError("Token has expired")
            roles = frozenset(PrincipalRole(role) for role in payload.get("roles", []))
            return PrincipalClaims(
                subject=str(payload["sub"]),
                actor_type=ActorType(payload["actor_type"]),
                roles=roles,
                token_kind=TokenKind(payload["token_kind"]),
                tenant_id=payload.get("tenant_id"),
                source_system=str(payload.get("source_system", "api")),
                email=payload.get("email"),
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Malformed JWT payload") from exc

    def _encode(self, payload: dict[str, Any]) -> str:
        header = {"typ": "JWT", "alg": "HS256"}
        header_segment = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        signature = hmac.new(self.signing_key, signing_input, hashlib.sha256).digest()
        return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
