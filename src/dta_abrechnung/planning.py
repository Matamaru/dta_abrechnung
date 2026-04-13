from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from .storage import ObjectStorageRef


@dataclass(slots=True, frozen=True)
class PlanningSnapshot:
    snapshot_id: str
    tenant_id: str
    hub_id: str | None
    planning_date: date
    mission_count: int
    extracted_at: datetime
    source_job_id: str | None = None
    object_ref: ObjectStorageRef | None = None


class PlanningReadModel(Protocol):
    def store_snapshot(self, snapshot: PlanningSnapshot) -> PlanningSnapshot:
        raise NotImplementedError

    def latest_snapshot(self, tenant_id: str, hub_id: str | None = None) -> PlanningSnapshot | None:
        raise NotImplementedError
