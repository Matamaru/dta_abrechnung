from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from .domain import (
    Abrechnungszentrum,
    EvidenceDocument,
    EvidenceKind,
    InstitutionCode,
    Leistungsnachweis,
    Leistungserbringer,
    Mandant,
    ProcedureCode,
    TenantMode,
    Vertrag,
    Verordnung,
)
from .store import PlatformStore


class CareOpsService:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def create_tenant(self, name: str, mode: TenantMode) -> Mandant:
        tenant = Mandant(
            id=f"tenant-{uuid4().hex[:12]}",
            name=name,
            mode=mode,
            created_at=datetime.now(UTC),
        )
        self.store.tenants[tenant.id] = tenant
        return tenant

    def create_billing_center(
        self,
        tenant_id: str,
        name: str,
        ik: str,
    ) -> Abrechnungszentrum:
        self._require_tenant(tenant_id)
        center = Abrechnungszentrum(
            id=f"az-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            ik=InstitutionCode(ik),
        )
        self.store.billing_centers[center.id] = center
        return center

    def create_provider(
        self,
        tenant_id: str,
        name: str,
        ik: str,
        billing_ik: str | None = None,
    ) -> Leistungserbringer:
        self._require_tenant(tenant_id)
        provider = Leistungserbringer(
            id=f"provider-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            ik=InstitutionCode(ik),
            billing_ik=InstitutionCode(billing_ik) if billing_ik else None,
        )
        self.store.providers[provider.id] = provider
        return provider

    def register_contract(
        self,
        provider_id: str,
        payer_id: str,
        procedure: ProcedureCode,
        version: str,
        allowed_transports: list,
        billing_codes: dict[str, Decimal | str | int | float],
    ) -> Vertrag:
        self._require_provider(provider_id)
        if payer_id not in self.store.payers:
            raise ValueError(f"Unknown payer: {payer_id}")
        contract = Vertrag(
            id=f"contract-{uuid4().hex[:12]}",
            provider_id=provider_id,
            payer_id=payer_id,
            procedure=procedure,
            version=version,
            allowed_transports=allowed_transports,
            billing_codes={code: Decimal(str(price)) for code, price in billing_codes.items()},
        )
        self.store.contracts[contract.id] = contract
        return contract

    def create_prescription(
        self,
        provider_id: str,
        patient_id: str,
        procedure: ProcedureCode,
        valid_from: date,
        valid_to: date,
        service_code: str,
        signed_at: datetime | None = None,
    ) -> Verordnung:
        self._require_provider(provider_id)
        prescription = Verordnung(
            id=f"rx-{uuid4().hex[:12]}",
            provider_id=provider_id,
            patient_id=patient_id,
            procedure=procedure,
            valid_from=valid_from,
            valid_to=valid_to,
            service_code=service_code,
            signed_at=signed_at,
        )
        self.store.prescriptions[prescription.id] = prescription
        return prescription

    def add_evidence(
        self,
        provider_id: str,
        kind: EvidenceKind,
        filename: str,
        content_type: str,
        content: bytes,
        signed: bool = False,
    ) -> EvidenceDocument:
        provider = self._require_provider(provider_id)
        document = EvidenceDocument(
            id=f"doc-{uuid4().hex[:12]}",
            tenant_id=provider.tenant_id,
            provider_id=provider_id,
            kind=kind,
            filename=filename,
            content_type=content_type,
            content=content,
            created_at=datetime.now(UTC),
            signed=signed,
        )
        self.store.evidence_documents[document.id] = document
        return document

    def record_service(
        self,
        provider_id: str,
        prescription_id: str,
        patient_id: str,
        service_date: date,
        service_code: str,
        quantity: Decimal | str | int | float,
        performed_by: str,
        unit_price: Decimal | str | int | float | None = None,
        document_ids: list[str] | None = None,
        signed: bool = False,
        source_system: str = "care_ops",
    ) -> Leistungsnachweis:
        provider = self._require_provider(provider_id)
        prescription = self._require_prescription(prescription_id)
        if prescription.provider_id != provider_id:
            raise ValueError("Prescription does not belong to provider")
        entry = Leistungsnachweis(
            id=f"svc-{uuid4().hex[:12]}",
            tenant_id=provider.tenant_id,
            provider_id=provider_id,
            prescription_id=prescription_id,
            procedure=prescription.procedure,
            patient_id=patient_id,
            service_date=service_date,
            service_code=service_code,
            quantity=Decimal(str(quantity)),
            performed_by=performed_by,
            unit_price=Decimal(str(unit_price)) if unit_price is not None else None,
            document_ids=document_ids or [],
            signed=signed,
            source_system=source_system,
        )
        self.store.services[entry.id] = entry
        return entry

    def link_document_to_service(self, service_id: str, document_id: str) -> Leistungsnachweis:
        if document_id not in self.store.evidence_documents:
            raise ValueError(f"Unknown evidence document: {document_id}")
        service = self._require_service(service_id)
        updated = replace(service, document_ids=[*service.document_ids, document_id])
        self.store.services[service_id] = updated
        return updated

    def _require_tenant(self, tenant_id: str) -> Mandant:
        try:
            return self.store.tenants[tenant_id]
        except KeyError as exc:
            raise ValueError(f"Unknown tenant: {tenant_id}") from exc

    def _require_provider(self, provider_id: str) -> Leistungserbringer:
        try:
            return self.store.providers[provider_id]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {provider_id}") from exc

    def _require_prescription(self, prescription_id: str) -> Verordnung:
        try:
            return self.store.prescriptions[prescription_id]
        except KeyError as exc:
            raise ValueError(f"Unknown prescription: {prescription_id}") from exc

    def _require_service(self, service_id: str) -> Leistungsnachweis:
        try:
            return self.store.services[service_id]
        except KeyError as exc:
            raise ValueError(f"Unknown service: {service_id}") from exc
