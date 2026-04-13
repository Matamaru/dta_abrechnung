from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status

from ..domain import Leistungserbringer, Mandant
from ..persistence import PersistenceRuntime, build_runtime
from ..planning import PlanningSnapshot
from ..runtime import ApplicationSettings, DeploymentEnvironment
from ..security import AuditEventView, PrincipalRole
from ..storage import LocalObjectStore, ObjectStore
from .auth import AuthContext, JwtCodec
from .realtime import RealtimeBroker
from .schemas import (
    AuditEventResponse,
    DatabaseHealthResponse,
    PlanningSnapshotCreateRequest,
    PlanningSnapshotResponse,
    ProjectionFreshnessResponse,
    ProjectionHealthResponse,
    ProviderCreateRequest,
    ProviderResponse,
    TenantCreateRequest,
    TenantResponse,
)
from .services import ApiServices


@dataclass(slots=True)
class ApiState:
    settings: ApplicationSettings
    primary_runtime: PersistenceRuntime
    projection_runtime: PersistenceRuntime
    services: ApiServices
    jwt_codec: JwtCodec
    realtime_broker: RealtimeBroker


def create_app(
    settings: ApplicationSettings,
    *,
    primary_runtime: PersistenceRuntime | None = None,
    projection_runtime: PersistenceRuntime | None = None,
    object_store: ObjectStore | None = None,
) -> FastAPI:
    settings.validate()
    primary = primary_runtime or build_runtime(settings.primary_database)
    projection = projection_runtime or build_runtime(settings.read_replica_database or settings.primary_database)
    resolved_object_store = object_store or _build_object_store(settings)
    broker = RealtimeBroker()
    state = ApiState(
        settings=settings,
        primary_runtime=primary,
        projection_runtime=projection,
        services=ApiServices(
            primary_runtime=primary,
            projection_runtime=projection,
            object_store=resolved_object_store,
            realtime_broker=broker,
            realtime_channel_prefix=settings.api.realtime_channel_prefix,
        ),
        jwt_codec=JwtCodec(
            issuer=settings.jwt.issuer,
            audience=settings.jwt.audience,
            signing_key=settings.jwt.signing_key,
        ),
        realtime_broker=broker,
    )

    app = FastAPI(
        title="DTA Abrechnung Private API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.api_state = state

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment.value, "api_version": "v1"}

    @app.get("/api/v1/health/primary-db", response_model=DatabaseHealthResponse)
    async def primary_db_health(request: Request) -> DatabaseHealthResponse:
        api_state = get_api_state(request)
        return DatabaseHealthResponse(**api_state.services.check_database(api_state.primary_runtime))

    @app.get("/api/v1/health/read-replica", response_model=DatabaseHealthResponse)
    async def read_replica_health(request: Request) -> DatabaseHealthResponse:
        api_state = get_api_state(request)
        runtime = api_state.projection_runtime
        return DatabaseHealthResponse(**api_state.services.check_database(runtime))

    @app.get("/api/v1/health/projections", response_model=ProjectionHealthResponse)
    async def projection_health(
        request: Request,
        tenant_id: str,
        hub_id: str | None = None,
        auth: AuthContext = Depends(require_auth),
    ) -> ProjectionHealthResponse:
        _ensure_tenant_access(auth, tenant_id)
        api_state = get_api_state(request)
        freshness = api_state.services.projection_freshness(tenant_id, hub_id, auth)
        if freshness is None:
            return ProjectionHealthResponse(ok=False, freshness=None)
        return ProjectionHealthResponse(
            ok=True,
            freshness=ProjectionFreshnessResponse(
                tenant_id=freshness.tenant_id,
                hub_id=freshness.hub_id,
                snapshot_id=freshness.snapshot_id,
                extracted_at=freshness.extracted_at,
                age_seconds=freshness.age_seconds,
            ),
        )

    @app.post("/api/v1/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
    async def create_tenant(
        payload: TenantCreateRequest,
        request: Request,
        auth: AuthContext = Depends(require_roles(PrincipalRole.PLATFORM_ADMIN)),
    ) -> TenantResponse:
        tenant = get_api_state(request).services.create_tenant(payload.name, payload.mode, auth, payload.reason, payload.legal_basis)
        return _tenant_response(tenant)

    @app.get("/api/v1/tenants", response_model=list[TenantResponse])
    async def list_tenants(
        request: Request,
        auth: AuthContext = Depends(require_roles(PrincipalRole.PLATFORM_ADMIN)),
    ) -> list[TenantResponse]:
        tenants = get_api_state(request).services.list_tenants(auth)
        return [_tenant_response(tenant) for tenant in tenants]

    @app.get("/api/v1/tenants/{tenant_id}", response_model=TenantResponse)
    async def get_tenant(
        tenant_id: str,
        request: Request,
        auth: AuthContext = Depends(require_auth),
    ) -> TenantResponse:
        _ensure_tenant_access(auth, tenant_id)
        tenant = get_api_state(request).services.get_tenant(tenant_id, auth)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        return _tenant_response(tenant)

    @app.post("/api/v1/providers", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
    async def create_provider(
        payload: ProviderCreateRequest,
        request: Request,
        auth: AuthContext = Depends(
            require_roles(
                PrincipalRole.PLATFORM_ADMIN,
                PrincipalRole.TENANT_ADMIN,
                PrincipalRole.BILLING_OPERATOR,
            )
        ),
    ) -> ProviderResponse:
        _ensure_tenant_access(auth, payload.tenant_id)
        try:
            provider = get_api_state(request).services.create_provider(
                tenant_id=payload.tenant_id,
                name=payload.name,
                ik=payload.ik,
                billing_ik=payload.billing_ik,
                auth=auth,
                reason=payload.reason,
                legal_basis=payload.legal_basis,
            )
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return _provider_response(provider)

    @app.get("/api/v1/tenants/{tenant_id}/providers", response_model=list[ProviderResponse])
    async def list_providers(
        tenant_id: str,
        request: Request,
        auth: AuthContext = Depends(require_auth),
    ) -> list[ProviderResponse]:
        _ensure_tenant_access(auth, tenant_id)
        providers = get_api_state(request).services.list_providers(tenant_id, auth)
        return [_provider_response(provider) for provider in providers]

    @app.get("/api/v1/providers/{provider_id}", response_model=ProviderResponse)
    async def get_provider(
        provider_id: str,
        request: Request,
        auth: AuthContext = Depends(require_auth),
    ) -> ProviderResponse:
        provider = get_api_state(request).services.get_provider(provider_id, auth)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
        _ensure_tenant_access(auth, provider.tenant_id)
        return _provider_response(provider)

    @app.post("/api/v1/planning/snapshots", response_model=PlanningSnapshotResponse, status_code=status.HTTP_201_CREATED)
    async def create_planning_snapshot(
        payload: PlanningSnapshotCreateRequest,
        request: Request,
        auth: AuthContext = Depends(
            require_roles(
                PrincipalRole.PLATFORM_ADMIN,
                PrincipalRole.TENANT_ADMIN,
                PrincipalRole.BILLING_OPERATOR,
                PrincipalRole.SERVICE_PRINCIPAL,
            )
        ),
    ) -> PlanningSnapshotResponse:
        _ensure_tenant_access(auth, payload.tenant_id)
        snapshot = await get_api_state(request).services.store_planning_snapshot(
            tenant_id=payload.tenant_id,
            hub_id=payload.hub_id,
            planning_date=payload.planning_date,
            mission_count=payload.mission_count,
            payload=payload.payload,
            source_job_id=payload.source_job_id,
            auth=auth,
            reason=payload.reason,
            legal_basis=payload.legal_basis,
        )
        return _snapshot_response(snapshot)

    @app.get("/api/v1/planning/snapshots/latest", response_model=PlanningSnapshotResponse)
    async def latest_planning_snapshot(
        tenant_id: str,
        request: Request,
        hub_id: str | None = None,
        auth: AuthContext = Depends(require_auth),
    ) -> PlanningSnapshotResponse:
        _ensure_tenant_access(auth, tenant_id)
        snapshot = get_api_state(request).services.latest_planning_snapshot(tenant_id, hub_id, auth)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning snapshot not found")
        return _snapshot_response(snapshot)

    @app.get("/api/v1/planning/snapshots", response_model=list[PlanningSnapshotResponse])
    async def list_planning_snapshots(
        tenant_id: str,
        request: Request,
        hub_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        auth: AuthContext = Depends(require_auth),
    ) -> list[PlanningSnapshotResponse]:
        _ensure_tenant_access(auth, tenant_id)
        snapshots = get_api_state(request).services.list_planning_snapshots(tenant_id, hub_id, auth, limit=limit)
        return [_snapshot_response(snapshot) for snapshot in snapshots]

    @app.get("/api/v1/audit/events", response_model=list[AuditEventResponse])
    async def list_audit_events(
        request: Request,
        tenant_id: str | None = None,
        auth: AuthContext = Depends(require_roles(PrincipalRole.PLATFORM_ADMIN, PrincipalRole.AUDITOR)),
    ) -> list[AuditEventResponse]:
        scoped_tenant = tenant_id or auth.tenant_id
        if scoped_tenant is None and not auth.has_role(PrincipalRole.PLATFORM_ADMIN):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant auditors require a tenant scope")
        if scoped_tenant is not None:
            _ensure_tenant_access(auth, scoped_tenant)
        events = get_api_state(request).services.list_audit_events(auth, tenant_id=scoped_tenant)
        return [_audit_event_response(event) for event in events]

    @app.websocket("/api/v1/realtime/planning")
    async def planning_realtime(websocket: WebSocket, tenant_id: str) -> None:
        try:
            auth = _authenticate_websocket(websocket)
            _ensure_tenant_access(auth, tenant_id)
        except HTTPException:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        api_state = get_api_state(websocket)
        channel = api_state.services.planning_channel(tenant_id)
        api_state.services.record_realtime_subscription(channel, auth)
        await websocket.accept()
        queue = await api_state.realtime_broker.subscribe(channel)
        try:
            await websocket.send_json({"event_type": "subscription.ready", "tenant_id": tenant_id})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    await websocket.send_json(
                        {
                            "event_type": event.event_type,
                            "tenant_id": event.tenant_id,
                            "payload": event.payload,
                            "emitted_at": event.emitted_at.isoformat(),
                        }
                    )
                except TimeoutError:
                    await websocket.send_json({"event_type": "keepalive", "tenant_id": tenant_id})
        except WebSocketDisconnect:
            pass
        finally:
            await api_state.realtime_broker.unsubscribe(channel, queue)

    return app


def create_default_app() -> FastAPI:
    return create_app(ApplicationSettings.from_env())


def main() -> None:
    settings = ApplicationSettings.from_env()
    app = create_app(settings)
    uvicorn.run(app, host=settings.api.host, port=settings.api.port)


def get_api_state(scope_owner: Request | WebSocket) -> ApiState:
    return scope_owner.app.state.api_state


async def require_auth(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> AuthContext:
    api_state = get_api_state(request)
    token = _extract_bearer_token(authorization)
    try:
        claims = api_state.jwt_codec.decode(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AuthContext.from_claims(claims, request_id or f"req-{uuid4().hex[:12]}")


def require_roles(*roles: PrincipalRole):
    async def dependency(auth: AuthContext = Depends(require_auth)) -> AuthContext:
        if not auth.has_role(*roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role scope")
        return auth

    return dependency


def _authenticate_websocket(websocket: WebSocket) -> AuthContext:
    api_state = get_api_state(websocket)
    bearer = websocket.headers.get("authorization")
    token = websocket.query_params.get("token")
    if token is None:
        token = _extract_bearer_token(bearer)
    try:
        claims = api_state.jwt_codec.decode(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    request_id = websocket.headers.get("x-request-id") or f"req-{uuid4().hex[:12]}"
    return AuthContext.from_claims(claims, request_id=request_id)


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
    return token


def _ensure_tenant_access(auth: AuthContext, tenant_id: str) -> None:
    try:
        auth.ensure_tenant_access(tenant_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def _build_object_store(settings: ApplicationSettings) -> ObjectStore:
    root = settings.object_storage.root
    if root is None:
        if settings.environment not in {DeploymentEnvironment.LOCAL_DEV, DeploymentEnvironment.TEST}:
            raise ValueError("Non-local environments require an explicit object store implementation or configured root")
        root = Path(".local-object-store/api")
    return LocalObjectStore(
        root=root,
        bucket=settings.object_storage.bucket,
        encryption_key_id=settings.object_storage.kms_key_id,
        residency=settings.object_storage.residency,
        immutable=True,
    )


def _tenant_response(tenant: Mandant) -> TenantResponse:
    return TenantResponse(id=tenant.id, name=tenant.name, mode=tenant.mode, created_at=tenant.created_at)


def _provider_response(provider: Leistungserbringer) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        tenant_id=provider.tenant_id,
        name=provider.name,
        ik=provider.ik.value,
        billing_ik=provider.billing_ik.value if provider.billing_ik else None,
    )


def _snapshot_response(snapshot: PlanningSnapshot) -> PlanningSnapshotResponse:
    return PlanningSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        tenant_id=snapshot.tenant_id,
        hub_id=snapshot.hub_id,
        planning_date=snapshot.planning_date,
        mission_count=snapshot.mission_count,
        extracted_at=snapshot.extracted_at,
        source_job_id=snapshot.source_job_id,
    )


def _audit_event_response(event: AuditEventView) -> AuditEventResponse:
    return AuditEventResponse(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        table_name=event.table_name,
        row_pk=event.row_pk,
        actor_id=event.actor_id,
        actor_type=event.actor_type.value,
        operation=event.operation.value,
        request_id=event.request_id,
        tenant_id=event.tenant_id,
        reason=event.reason,
        legal_basis=event.legal_basis,
        changed_fields=event.changed_fields,
        before_state=event.before_state,
        after_state=event.after_state,
        sensitive_read_target=event.sensitive_read_target.value if event.sensitive_read_target else None,
    )
