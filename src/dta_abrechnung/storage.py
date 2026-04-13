from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


@dataclass(slots=True, frozen=True)
class ObjectStorageRef:
    bucket: str
    key: str
    checksum_sha256: str
    size_bytes: int
    media_type: str
    encryption_key_id: str
    retention_class: str
    legal_hold: bool
    immutable: bool
    residency: str
    version_id: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class BackupPolicy:
    name: str
    retention_days: int
    immutable: bool
    residency: str


@dataclass(slots=True, frozen=True)
class RecoveryPolicy:
    target_rpo_minutes: int
    target_rto_minutes: int
    single_az_failover_required: bool
    manual_region_failover: bool


class ObjectStore(Protocol):
    def put_blob(
        self,
        key: str,
        content: bytes,
        media_type: str,
        retention_class: str,
        legal_hold: bool = False,
    ) -> ObjectStorageRef:
        raise NotImplementedError

    def get_blob(self, ref: ObjectStorageRef) -> bytes:
        raise NotImplementedError


class LocalObjectStore:
    def __init__(
        self,
        root: Path,
        bucket: str = "local-dev",
        encryption_key_id: str = "local-dev-kms-key",
        immutable: bool = True,
        residency: str = "germany",
    ) -> None:
        self.root = root
        self.bucket = bucket
        self.encryption_key_id = encryption_key_id
        self.immutable = immutable
        self.residency = residency
        self.root.mkdir(parents=True, exist_ok=True)

    def put_blob(
        self,
        key: str,
        content: bytes,
        media_type: str,
        retention_class: str,
        legal_hold: bool = False,
    ) -> ObjectStorageRef:
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and self.immutable:
            raise ValueError(f"Object key already exists and store is immutable: {key}")
        destination.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        return ObjectStorageRef(
            bucket=self.bucket,
            key=key,
            checksum_sha256=checksum,
            size_bytes=len(content),
            media_type=media_type,
            encryption_key_id=self.encryption_key_id,
            retention_class=retention_class,
            legal_hold=legal_hold,
            immutable=self.immutable,
            residency=self.residency,
            created_at=datetime.now(UTC),
        )

    def get_blob(self, ref: ObjectStorageRef) -> bytes:
        return (self.root / ref.key).read_bytes()
