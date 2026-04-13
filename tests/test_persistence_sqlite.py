from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dta_abrechnung.domain import InstitutionCode, Leistungserbringer, Mandant, TenantMode
from dta_abrechnung.persistence import SqlAlchemyUnitOfWork, build_runtime, create_schema, drop_schema
from dta_abrechnung.planning import PlanningSnapshot
from dta_abrechnung.runtime import DatabaseProfile, DatabaseSettings, DeploymentEnvironment
from dta_abrechnung.security import ActorType, AuditContext
from dta_abrechnung.storage import LocalObjectStore


class SqlitePersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tempdir.name) / "app.sqlite3"
        self.settings = DatabaseSettings(
            profile=DatabaseProfile.LOCAL_SQLITE,
            url=f"sqlite:///{self.database_path}",
            environment=DeploymentEnvironment.TEST,
        )
        self.runtime = build_runtime(self.settings)
        create_schema(self.runtime.engine)
        self.object_store = LocalObjectStore(Path(self.tempdir.name) / "objects")
        self.audit_context = AuditContext(
            actor_id="svc-test",
            actor_type=ActorType.SERVICE,
            request_id="req-1",
            source_system="unit-test",
            tenant_id="tenant-1",
            reason="test fixture",
        )

    def tearDown(self) -> None:
        drop_schema(self.runtime.engine)
        self.tempdir.cleanup()

    def test_sqlite_uow_persists_core_entities_and_audits_reads_and_writes(self) -> None:
        tenant = Mandant(
            id="tenant-1",
            name="Nord Verbund",
            mode=TenantMode.BILLING_CENTER,
            created_at=datetime(2026, 4, 13, 12, 0, tzinfo=UTC),
        )
        provider = Leistungserbringer(
            id="provider-1",
            tenant_id=tenant.id,
            name="Pflege Nord",
            ik=InstitutionCode("123456789"),
            billing_ik=InstitutionCode("223456789"),
        )
        object_ref = self.object_store.put_blob(
            key="tenant-1/evidence/proof.pdf",
            content=b"binary-proof",
            media_type="application/pdf",
            retention_class="regulated",
            legal_hold=True,
        )
        snapshot = PlanningSnapshot(
            snapshot_id="plan-1",
            tenant_id=tenant.id,
            hub_id="hub-a",
            planning_date=date(2026, 4, 13),
            mission_count=4200,
            extracted_at=datetime(2026, 4, 13, 13, 30, tzinfo=UTC),
            source_job_id="job-1",
            object_ref=object_ref,
        )

        with SqlAlchemyUnitOfWork(self.runtime, audit_context=self.audit_context) as uow:
            uow.tenants.add(tenant, self.audit_context)
            uow.providers.add(provider, self.audit_context)
            uow.object_storage_refs.add("obj-1", tenant.id, object_ref, self.audit_context)
            uow.planning_snapshots.store_snapshot(snapshot, "obj-1", self.audit_context)
            uow.commit()

        read_context = AuditContext(
            actor_id="user-auditor",
            actor_type=ActorType.USER,
            request_id="req-2",
            source_system="unit-test",
            tenant_id=tenant.id,
            reason="compliance review",
        )
        with SqlAlchemyUnitOfWork(self.runtime, audit_context=read_context) as uow:
            loaded_tenant = uow.tenants.get(tenant.id)
            loaded_provider = uow.providers.get(provider.id, context=read_context, sensitive=True)
            loaded_ref = uow.object_storage_refs.get("obj-1", context=read_context, sensitive=True)
            loaded_snapshot = uow.planning_snapshots.latest_snapshot(tenant.id, "hub-a", context=read_context)
            loaded_snapshot_without_hub_filter = uow.planning_snapshots.latest_snapshot(tenant.id, context=read_context)
            uow.commit()

        self.assertEqual(loaded_tenant.name, "Nord Verbund")
        self.assertEqual(loaded_provider.billing_ik.value, "223456789")
        self.assertEqual(loaded_ref.checksum_sha256, object_ref.checksum_sha256)
        self.assertEqual(loaded_snapshot.mission_count, 4200)
        self.assertEqual(loaded_snapshot_without_hub_filter.snapshot_id, snapshot.snapshot_id)

        with SqlAlchemyUnitOfWork(self.runtime, audit_context=read_context) as uow:
            events = uow.audit.list_events(tenant_id=tenant.id)
            names = {(event.table_name, event.operation.value) for event in events}
            ordered = [tenant_record.name for tenant_record in uow.tenants.list(sort_field="name")]

        self.assertIn(("tenants", "insert"), names)
        self.assertIn(("providers", "insert"), names)
        self.assertIn(("object_storage_refs", "insert"), names)
        self.assertIn(("planning_snapshots", "insert"), names)
        self.assertIn(("providers", "read"), names)
        self.assertIn(("object_storage_refs", "read"), names)
        self.assertIn(("planning_snapshots", "read"), names)
        self.assertEqual(ordered, ["Nord Verbund"])

    def test_sort_whitelist_blocks_injection_like_input(self) -> None:
        with SqlAlchemyUnitOfWork(self.runtime, audit_context=self.audit_context) as uow:
            uow.tenants.add(
                Mandant(
                    id="tenant-2",
                    name="Alpha",
                    mode=TenantMode.SELF_BILLER,
                    created_at=datetime(2026, 4, 13, 12, 5, tzinfo=UTC),
                ),
                self.audit_context,
            )
            uow.commit()

        with SqlAlchemyUnitOfWork(self.runtime, audit_context=self.audit_context) as uow:
            with self.assertRaises(ValueError):
                uow.tenants.list(sort_field="name; DROP TABLE tenants")


@unittest.skipUnless(os.getenv("DTA_TEST_POSTGRES_URL"), "requires DTA_TEST_POSTGRES_URL")
class PostgresSmokeTest(unittest.TestCase):
    def test_runtime_builds_for_postgres_profile(self) -> None:
        settings = DatabaseSettings(
            profile=DatabaseProfile.PROD_POSTGRES,
            url=os.environ["DTA_TEST_POSTGRES_URL"],
            environment=DeploymentEnvironment.STAGING,
        )

        runtime = build_runtime(settings)

        with runtime.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT 1").scalar_one(), 1)
