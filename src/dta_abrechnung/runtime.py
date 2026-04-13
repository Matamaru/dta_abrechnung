from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit


class DeploymentEnvironment(StrEnum):
    LOCAL_DEV = "local_dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class DatabaseProfile(StrEnum):
    LOCAL_SQLITE = "local_sqlite"
    PROD_POSTGRES = "prod_postgres"
    POSTGRES_READ_REPLICA = "postgres_read_replica"


class DatabaseRole(StrEnum):
    PRIMARY = "primary"
    READ_REPLICA = "read_replica"


class DurabilityClass(StrEnum):
    BEST_EFFORT = "best_effort"
    STRONG_SYNC = "strong_sync"


@dataclass(slots=True, frozen=True)
class BackendCapabilities:
    supports_rls: bool
    supports_trigger_audit: bool
    supports_partitioning: bool
    supports_synchronous_commit: bool
    supports_read_replicas: bool


@dataclass(slots=True, frozen=True)
class ObjectStorageSettings:
    bucket: str
    kms_key_id: str
    residency: str
    root: Path | None = None


@dataclass(slots=True, frozen=True)
class JwtSettings:
    issuer: str
    audience: str
    signing_key: str
    access_token_ttl_seconds: int = 3600


@dataclass(slots=True, frozen=True)
class ApiSettings:
    public_base_url: str
    private_base_url: str
    host: str = "127.0.0.1"
    port: int = 8000
    realtime_channel_prefix: str = "planning"


@dataclass(slots=True, frozen=True)
class DatabaseSettings:
    profile: DatabaseProfile
    url: str
    environment: DeploymentEnvironment
    role: DatabaseRole = DatabaseRole.PRIMARY
    echo_sql: bool = False
    application_name: str = "dta_abrechnung"

    @property
    def dialect(self) -> str:
        return urlsplit(self.url).scheme.split("+", 1)[0]

    @property
    def is_sqlite(self) -> bool:
        return self.dialect == "sqlite"

    @property
    def is_postgres(self) -> bool:
        return self.dialect in {"postgres", "postgresql"}

    def validate(self) -> None:
        if self.role == DatabaseRole.READ_REPLICA and self.profile != DatabaseProfile.POSTGRES_READ_REPLICA:
            raise ValueError("Read-replica connections must use the postgres_read_replica profile")
        if self.role == DatabaseRole.PRIMARY and self.profile == DatabaseProfile.POSTGRES_READ_REPLICA:
            raise ValueError("Primary connections cannot use the postgres_read_replica profile")
        if self.profile == DatabaseProfile.LOCAL_SQLITE:
            if self.environment not in {DeploymentEnvironment.LOCAL_DEV, DeploymentEnvironment.TEST}:
                raise ValueError("SQLite is only allowed in local_dev or test environments")
            if not self.is_sqlite:
                raise ValueError("local_sqlite profile requires a sqlite URL")
            return
        if not self.is_postgres:
            raise ValueError(f"{self.profile.value} requires a PostgreSQL URL")
        if self.environment == DeploymentEnvironment.TEST and self.profile == DatabaseProfile.POSTGRES_READ_REPLICA:
            raise ValueError("postgres_read_replica is not a valid write profile for tests")


@dataclass(slots=True, frozen=True)
class ApplicationSettings:
    environment: DeploymentEnvironment
    primary_database: DatabaseSettings
    read_replica_database: DatabaseSettings | None
    object_storage: ObjectStorageSettings
    jwt: JwtSettings
    api: ApiSettings
    source_system: str = "dta_private_api"

    def validate(self) -> None:
        self.primary_database.validate()
        if self.primary_database.role != DatabaseRole.PRIMARY:
            raise ValueError("primary_database must use the primary role")
        if self.primary_database.environment != self.environment:
            raise ValueError("primary_database environment must match the application environment")
        if self.read_replica_database is not None:
            self.read_replica_database.validate()
            if self.read_replica_database.role != DatabaseRole.READ_REPLICA:
                raise ValueError("read_replica_database must use the read_replica role")
            if self.read_replica_database.environment != self.environment:
                raise ValueError("read_replica_database environment must match the application environment")
        if not self.jwt.signing_key:
            raise ValueError("JWT signing key must not be empty")
        if not self.api.private_base_url:
            raise ValueError("private_base_url must not be empty")

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: str | Path | None = None,
    ) -> "ApplicationSettings":
        file_values = load_env_file(env_file or ".env")
        merged: dict[str, str] = {**file_values, **dict(env or os.environ)}
        environment = DeploymentEnvironment(merged.get("DTA_ENVIRONMENT", DeploymentEnvironment.LOCAL_DEV.value))
        primary_profile = DatabaseProfile(merged.get("DTA_DATABASE_PROFILE", DatabaseProfile.LOCAL_SQLITE.value))
        primary_database = DatabaseSettings(
            profile=primary_profile,
            url=merged.get("DTA_DATABASE_URL", "sqlite:///local-dev.db"),
            environment=environment,
            role=DatabaseRole.PRIMARY,
            echo_sql=_parse_bool(merged.get("DTA_ECHO_SQL")),
            application_name=merged.get("DTA_APP_NAME", "dta_abrechnung"),
        )
        read_replica_url = merged.get("DTA_READ_REPLICA_URL")
        read_replica_database = None
        if read_replica_url:
            read_replica_database = DatabaseSettings(
                profile=DatabaseProfile.POSTGRES_READ_REPLICA,
                url=read_replica_url,
                environment=environment,
                role=DatabaseRole.READ_REPLICA,
                echo_sql=_parse_bool(merged.get("DTA_ECHO_SQL")),
                application_name=f"{merged.get('DTA_APP_NAME', 'dta_abrechnung')}_read_replica",
            )
        object_storage_root = merged.get("DTA_OBJECT_STORAGE_ROOT")
        settings = cls(
            environment=environment,
            primary_database=primary_database,
            read_replica_database=read_replica_database,
            object_storage=ObjectStorageSettings(
                bucket=merged.get("DTA_OBJECT_STORAGE_BUCKET", "local-dev"),
                kms_key_id=merged.get("DTA_KMS_KEY_ID", "local-dev-kms-key"),
                residency=merged.get("DTA_DATA_RESIDENCY", "germany"),
                root=Path(object_storage_root) if object_storage_root else None,
            ),
            jwt=JwtSettings(
                issuer=merged.get("DTA_JWT_ISSUER", "dta_abrechnung"),
                audience=merged.get("DTA_JWT_AUDIENCE", "dta_private_api"),
                signing_key=merged.get("DTA_JWT_SIGNING_KEY", "local-dev-signing-key"),
                access_token_ttl_seconds=int(merged.get("DTA_JWT_TTL_SECONDS", "3600")),
            ),
            api=ApiSettings(
                public_base_url=merged.get("DTA_API_BASE_URL", "http://127.0.0.1:8000"),
                private_base_url=merged.get("DTA_API_PRIVATE_BASE_URL", merged.get("DTA_API_BASE_URL", "http://127.0.0.1:8000")),
                host=merged.get("DTA_API_HOST", "127.0.0.1"),
                port=int(merged.get("DTA_API_PORT", "8000")),
                realtime_channel_prefix=merged.get("DTA_REALTIME_CHANNEL_PREFIX", "planning"),
            ),
            source_system=merged.get("DTA_API_SOURCE_SYSTEM", "dta_private_api"),
        )
        settings.validate()
        return settings


def capabilities_for_profile(profile: DatabaseProfile) -> BackendCapabilities:
    if profile == DatabaseProfile.LOCAL_SQLITE:
        return BackendCapabilities(
            supports_rls=False,
            supports_trigger_audit=False,
            supports_partitioning=False,
            supports_synchronous_commit=False,
            supports_read_replicas=False,
        )
    if profile == DatabaseProfile.PROD_POSTGRES:
        return BackendCapabilities(
            supports_rls=True,
            supports_trigger_audit=True,
            supports_partitioning=True,
            supports_synchronous_commit=True,
            supports_read_replicas=True,
        )
    return BackendCapabilities(
        supports_rls=True,
        supports_trigger_audit=True,
        supports_partitioning=True,
        supports_synchronous_commit=False,
        supports_read_replicas=True,
    )


def load_env_file(path: str | Path) -> dict[str, str]:
    resolved = Path(path)
    if not resolved.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
