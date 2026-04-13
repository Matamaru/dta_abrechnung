from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dta_abrechnung.api import create_app
from dta_abrechnung.api.auth import TokenKind
from dta_abrechnung.persistence import build_runtime, create_schema, drop_schema
from dta_abrechnung.runtime import (
    ApiSettings,
    ApplicationSettings,
    DatabaseProfile,
    DatabaseSettings,
    DeploymentEnvironment,
    JwtSettings,
    ObjectStorageSettings,
)
from dta_abrechnung.security import ActorType, PrincipalRole


class _WebSocketSession:
    def __init__(self, app, path: str, query_params: dict[str, str]) -> None:
        query_string = urlencode(query_params).encode("ascii")
        self.app = app
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query_string,
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
            "state": {},
        }
        self._incoming: asyncio.Queue[dict] = asyncio.Queue()
        self._outgoing: asyncio.Queue[dict] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def connect(self) -> None:
        async def receive() -> dict:
            return await self._incoming.get()

        async def send(message: dict) -> None:
            await self._outgoing.put(message)

        self._task = asyncio.create_task(self.app(self.scope, receive, send))
        await self._incoming.put({"type": "websocket.connect"})
        message = await asyncio.wait_for(self._outgoing.get(), timeout=1)
        if message["type"] != "websocket.accept":
            raise AssertionError(f"Expected websocket.accept, got {message}")

    async def receive_json(self) -> dict:
        message = await asyncio.wait_for(self._outgoing.get(), timeout=2)
        if message["type"] == "websocket.send":
            return json.loads(message.get("text") or message["bytes"].decode("utf-8"))
        raise AssertionError(f"Expected websocket.send, got {message}")

    async def close(self) -> None:
        await self._incoming.put({"type": "websocket.disconnect", "code": 1000})
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


class PrivateApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tempdir.name) / "api.sqlite3"
        self.settings = ApplicationSettings(
            environment=DeploymentEnvironment.TEST,
            primary_database=DatabaseSettings(
                profile=DatabaseProfile.LOCAL_SQLITE,
                url=f"sqlite:///{self.database_path}",
                environment=DeploymentEnvironment.TEST,
            ),
            read_replica_database=None,
            object_storage=ObjectStorageSettings(
                bucket="test-bucket",
                kms_key_id="test-kms-key",
                residency="germany",
                root=Path(self.tempdir.name) / "objects",
            ),
            jwt=JwtSettings(
                issuer="tests",
                audience="dta-private-api",
                signing_key="super-secret-test-key",
                access_token_ttl_seconds=3600,
            ),
            api=ApiSettings(
                public_base_url="http://testserver",
                private_base_url="http://testserver",
            ),
            source_system="api-tests",
        )
        self.runtime = build_runtime(self.settings.primary_database)
        create_schema(self.runtime.engine)
        self.app = create_app(self.settings, primary_runtime=self.runtime, projection_runtime=self.runtime)

    async def asyncSetUp(self) -> None:
        transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    def tearDown(self) -> None:
        drop_schema(self.runtime.engine)
        self.tempdir.cleanup()

    def _token(self, *, subject: str, roles: set[PrincipalRole], tenant_id: str | None = None, actor_type: ActorType = ActorType.USER) -> str:
        codec = self.app.state.api_state.jwt_codec
        return codec.issue_token(
            subject=subject,
            actor_type=actor_type,
            roles=roles,
            token_kind=TokenKind.SERVICE if actor_type == ActorType.SERVICE else TokenKind.USER,
            source_system="tests",
            tenant_id=tenant_id,
            ttl_seconds=3600,
        )

    async def test_tenant_provider_and_audit_flow(self) -> None:
        admin_headers = {"Authorization": f"Bearer {self._token(subject='admin', roles={PrincipalRole.PLATFORM_ADMIN})}"}
        tenant_response = await self.client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "Nord Verbund", "mode": "billing_center", "reason": "bootstrap"},
        )
        self.assertEqual(tenant_response.status_code, 201)
        tenant_id = tenant_response.json()["id"]

        tenant_headers = {
            "Authorization": f"Bearer {self._token(subject='tenant-admin', roles={PrincipalRole.TENANT_ADMIN}, tenant_id=tenant_id)}"
        }
        provider_response = await self.client.post(
            "/api/v1/providers",
            headers=tenant_headers,
            json={
                "tenant_id": tenant_id,
                "name": "Pflege Nord",
                "ik": "123456789",
                "billing_ik": "223456789",
                "reason": "provider onboarding",
            },
        )
        self.assertEqual(provider_response.status_code, 201)
        provider_id = provider_response.json()["id"]

        detail_response = await self.client.get(f"/api/v1/providers/{provider_id}", headers=tenant_headers)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["billing_ik"], "223456789")

        list_response = await self.client.get(f"/api/v1/tenants/{tenant_id}/providers", headers=tenant_headers)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([provider["id"] for provider in list_response.json()], [provider_id])

        audit_response = await self.client.get(f"/api/v1/audit/events?tenant_id={tenant_id}", headers=admin_headers)
        self.assertEqual(audit_response.status_code, 200)
        operations = {(event["table_name"], event["operation"]) for event in audit_response.json()}
        self.assertIn(("tenants", "insert"), operations)
        self.assertIn(("providers", "insert"), operations)
        self.assertIn(("providers", "read"), operations)
        self.assertIn(("audit_ledger", "read"), operations)

    async def test_tenant_isolation_blocks_cross_tenant_provider_access(self) -> None:
        admin_headers = {"Authorization": f"Bearer {self._token(subject='admin', roles={PrincipalRole.PLATFORM_ADMIN})}"}
        tenant_a = (
            await self.client.post(
                "/api/v1/tenants",
                headers=admin_headers,
                json={"name": "Tenant A", "mode": "self_biller"},
            )
        ).json()["id"]
        tenant_b = (
            await self.client.post(
                "/api/v1/tenants",
                headers=admin_headers,
                json={"name": "Tenant B", "mode": "self_biller"},
            )
        ).json()["id"]

        tenant_a_headers = {
            "Authorization": f"Bearer {self._token(subject='tenant-a', roles={PrincipalRole.TENANT_ADMIN}, tenant_id=tenant_a)}"
        }
        forbidden_response = await self.client.post(
            "/api/v1/providers",
            headers=tenant_a_headers,
            json={"tenant_id": tenant_b, "name": "Cross Tenant", "ik": "333333333"},
        )
        self.assertEqual(forbidden_response.status_code, 403)

    async def test_planning_snapshot_projection_health_and_realtime(self) -> None:
        admin_headers = {"Authorization": f"Bearer {self._token(subject='admin', roles={PrincipalRole.PLATFORM_ADMIN})}"}
        tenant_id = (
            await self.client.post(
                "/api/v1/tenants",
                headers=admin_headers,
                json={"name": "Operations Nord", "mode": "billing_center"},
            )
        ).json()["id"]
        operator_token = self._token(
            subject="planner",
            roles={PrincipalRole.BILLING_OPERATOR},
            tenant_id=tenant_id,
        )
        operator_headers = {"Authorization": f"Bearer {operator_token}"}

        websocket = _WebSocketSession(
            self.app,
            "/api/v1/realtime/planning",
            {"tenant_id": tenant_id, "token": operator_token},
        )
        await websocket.connect()
        ready = await websocket.receive_json()
        self.assertEqual(ready["event_type"], "subscription.ready")

        create_response = await self.client.post(
            "/api/v1/planning/snapshots",
            headers=operator_headers,
            json={
                "tenant_id": tenant_id,
                "hub_id": "hub-nord",
                "planning_date": "2026-04-13",
                "mission_count": 4200,
                "source_job_id": "job-42",
                "payload": {"routes": 120, "workers": 85},
            },
        )
        self.assertEqual(create_response.status_code, 201)

        event = await websocket.receive_json()
        self.assertEqual(event["event_type"], "planning.snapshot.stored")
        self.assertEqual(event["payload"]["mission_count"], 4200)
        await websocket.close()

        latest_response = await self.client.get(
            f"/api/v1/planning/snapshots/latest?tenant_id={tenant_id}&hub_id=hub-nord",
            headers=operator_headers,
        )
        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(latest_response.json()["source_job_id"], "job-42")

        list_response = await self.client.get(
            f"/api/v1/planning/snapshots?tenant_id={tenant_id}&hub_id=hub-nord&limit=10",
            headers=operator_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        health_response = await self.client.get(
            f"/api/v1/health/projections?tenant_id={tenant_id}&hub_id=hub-nord",
            headers=operator_headers,
        )
        self.assertEqual(health_response.status_code, 200)
        self.assertTrue(health_response.json()["ok"])

    async def test_missing_jwt_is_rejected(self) -> None:
        response = await self.client.get("/api/v1/tenants/tenant-1")
        self.assertEqual(response.status_code, 401)
