from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dta_abrechnung.platform import NationalDtaPlatform
from dta_abrechnung.runtime import (
    ApplicationSettings,
    DatabaseProfile,
    DatabaseRole,
    DatabaseSettings,
    DeploymentEnvironment,
    capabilities_for_profile,
)
from dta_abrechnung.storage import LocalObjectStore


class RuntimeProfilesTest(unittest.TestCase):
    def test_local_sqlite_is_rejected_in_production(self) -> None:
        settings = DatabaseSettings(
            profile=DatabaseProfile.LOCAL_SQLITE,
            url="sqlite:///prod.db",
            environment=DeploymentEnvironment.PRODUCTION,
        )

        with self.assertRaises(ValueError):
            settings.validate()

    def test_prod_postgres_requires_postgres_url(self) -> None:
        settings = DatabaseSettings(
            profile=DatabaseProfile.PROD_POSTGRES,
            url="sqlite:///local.db",
            environment=DeploymentEnvironment.STAGING,
        )

        with self.assertRaises(ValueError):
            settings.validate()

    def test_backend_capabilities_match_profile(self) -> None:
        sqlite_caps = capabilities_for_profile(DatabaseProfile.LOCAL_SQLITE)
        postgres_caps = capabilities_for_profile(DatabaseProfile.PROD_POSTGRES)

        self.assertFalse(sqlite_caps.supports_rls)
        self.assertFalse(sqlite_caps.supports_trigger_audit)
        self.assertTrue(postgres_caps.supports_rls)
        self.assertTrue(postgres_caps.supports_partitioning)
        self.assertTrue(postgres_caps.supports_synchronous_commit)

    def test_platform_with_database_builds_local_object_store_for_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            settings = DatabaseSettings(
                profile=DatabaseProfile.LOCAL_SQLITE,
                url=f"sqlite:///{tempdir}/app.db",
                environment=DeploymentEnvironment.LOCAL_DEV,
            )

            platform = NationalDtaPlatform.with_database(settings, local_object_root=Path(tempdir) / "objects")

        self.assertIsNotNone(platform.runtime)
        self.assertIsInstance(platform.object_store, LocalObjectStore)

    def test_application_settings_from_env_supports_read_replica(self) -> None:
        settings = ApplicationSettings.from_env(
            {
                "DTA_ENVIRONMENT": "staging",
                "DTA_DATABASE_PROFILE": "prod_postgres",
                "DTA_DATABASE_URL": "postgresql+psycopg://app:secret@localhost:5432/dta_abrechnung",
                "DTA_READ_REPLICA_URL": "postgresql+psycopg://app:secret@localhost:5432/dta_abrechnung_rr",
                "DTA_OBJECT_STORAGE_BUCKET": "dta-objects",
                "DTA_KMS_KEY_ID": "kms-key-1",
                "DTA_JWT_SIGNING_KEY": "jwt-secret",
                "DTA_API_PRIVATE_BASE_URL": "https://private.example.internal",
            },
            env_file=Path(self.id() + ".missing"),
        )

        self.assertEqual(settings.primary_database.role, DatabaseRole.PRIMARY)
        self.assertEqual(settings.read_replica_database.role, DatabaseRole.READ_REPLICA)
        self.assertEqual(settings.read_replica_database.profile, DatabaseProfile.POSTGRES_READ_REPLICA)
        self.assertEqual(settings.object_storage.bucket, "dta-objects")
