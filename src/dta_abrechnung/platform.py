from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .accounting import AccountingExportService
from .billing import BillingEngine
from .care_ops import CareOpsService
from .domain import ProcedureCode, SubmissionJob, SubmissionStatus, TenantMode, TransportFamily
from .evidence import EvidenceService
from .inbound import InboundProcessingService
from .masterdata import PayerMasterDataService
from .persistence import PersistenceRuntime, build_runtime
from .procedures import Classic302ProcedureAdapter, HkpProcedureAdapter, PflegeProcedureAdapter, ProcedureAdapter
from .runtime import DatabaseProfile, DatabaseSettings
from .store import PlatformStore
from .storage import LocalObjectStore, ObjectStore
from .transport import ClassicDtaTransportAdapter, ExternalTiBridge, NativeTiBridge, TiKimTransportAdapter


class NationalDtaPlatform:
    def __init__(
        self,
        runtime: PersistenceRuntime | None = None,
        object_store: ObjectStore | None = None,
    ) -> None:
        self.runtime = runtime
        self.object_store = object_store
        self.store = PlatformStore()
        self.care_ops = CareOpsService(self.store)
        self.master_data = PayerMasterDataService(self.store)
        self.evidence = EvidenceService(self.store)
        self.billing = BillingEngine(self.store)
        self.inbound = InboundProcessingService(self.store)
        self.accounting = AccountingExportService(self.store)
        self.external_ti_bridge = ExternalTiBridge()
        self.native_ti_bridge = NativeTiBridge()
        self.classic_transport = ClassicDtaTransportAdapter(self.store)
        self.procedure_adapters: dict[ProcedureCode, ProcedureAdapter] = {
            ProcedureCode.PFLEGE: PflegeProcedureAdapter(),
            ProcedureCode.HKP: HkpProcedureAdapter(),
            ProcedureCode.HAUSHALTSHILFE: Classic302ProcedureAdapter(ProcedureCode.HAUSHALTSHILFE, "SLGA"),
            ProcedureCode.HEILMITTEL: Classic302ProcedureAdapter(ProcedureCode.HEILMITTEL, "SLGA"),
            ProcedureCode.HILFSMITTEL: Classic302ProcedureAdapter(ProcedureCode.HILFSMITTEL, "SLGA"),
            ProcedureCode.KRANKENTRANSPORT: Classic302ProcedureAdapter(ProcedureCode.KRANKENTRANSPORT, "SLGA"),
        }

    @classmethod
    def with_database(
        cls,
        settings: DatabaseSettings,
        object_store: ObjectStore | None = None,
        local_object_root: Path | None = None,
    ) -> "NationalDtaPlatform":
        runtime = build_runtime(settings)
        resolved_object_store = object_store
        if resolved_object_store is None and settings.profile == DatabaseProfile.LOCAL_SQLITE:
            resolved_object_store = LocalObjectStore(local_object_root or Path(".local-object-store"))
        return cls(runtime=runtime, object_store=resolved_object_store)

    def pick_transport(self, invoice_id: str, requested: TransportFamily | None = None) -> TransportFamily:
        invoice = self.store.invoices[invoice_id]
        contract = self.store.contracts[invoice.contract_id]
        adapter = self.procedure_adapters[invoice.procedure]
        if requested is not None:
            if requested not in contract.allowed_transports:
                raise ValueError("Requested transport not allowed by contract")
            if requested not in adapter.supported_transports:
                raise ValueError("Requested transport not supported by adapter")
            return requested
        for transport in contract.allowed_transports:
            if transport in adapter.supported_transports:
                return transport
        raise ValueError("No compatible transport found")

    def submit_invoice(
        self,
        invoice_id: str,
        transport: TransportFamily | None = None,
        ti_mode: str = "external",
    ) -> SubmissionJob:
        invoice = self.store.invoices[invoice_id]
        adapter = self.procedure_adapters[invoice.procedure]
        selected_transport = self.pick_transport(invoice_id, transport)
        evidence_bundle = self.evidence.bundle_for_invoice(invoice)
        adapter.validate(invoice_id, selected_transport, self.store, evidence_bundle)
        ti_bridge = None
        if selected_transport == TransportFamily.TI_KIM:
            ti_bridge = self.external_ti_bridge if ti_mode == "external" else self.native_ti_bridge
        route = adapter.route(invoice_id, selected_transport, self.store, self.master_data, ti_bridge=ti_bridge)
        sequence_number = self.store.next_counter(f"serialize:{invoice.procedure.value}:{selected_transport.value}")
        payload = adapter.serialize(invoice_id, selected_transport, self.store, evidence_bundle, sequence_number)
        evidence_artifacts = adapter.package_evidence(invoice_id, selected_transport, evidence_bundle)
        provider = self.store.providers[invoice.provider_id]
        sender_ik = (provider.billing_ik or provider.ik).value
        if selected_transport == TransportFamily.CLASSIC_DTA:
            envelope, tracking_reference = self.classic_transport.submit(
                invoice_id=invoice_id,
                routing_target=route,
                main_artifact=payload.artifact,
                evidence_artifacts=evidence_artifacts,
                sender_ik=sender_ik,
            )
        else:
            envelope, tracking_reference = TiKimTransportAdapter(ti_bridge).submit(
                routing_target=route,
                main_artifact=payload.artifact,
                evidence_artifacts=evidence_artifacts,
                procedure=invoice.procedure,
                message_type=payload.message_type,
                version=payload.version,
            )
        submission = SubmissionJob(
            id=f"sub-{self.store.next_counter('submission'):06d}",
            invoice_id=invoice_id,
            procedure=invoice.procedure,
            transport=selected_transport,
            envelope=envelope,
            status=SubmissionStatus.SUBMITTED,
            tracking_reference=tracking_reference,
            created_at=datetime.now(UTC),
        )
        self.store.submissions[submission.id] = submission
        return submission

    def process_inbound(self, submission_id: str, raw_message: bytes) -> list:
        submission = self.store.submissions[submission_id]
        adapter = self.procedure_adapters[submission.procedure]
        return self.inbound.process(
            adapter=adapter,
            invoice_id=submission.invoice_id,
            submission_id=submission_id,
            raw_message=raw_message,
            transport=submission.transport,
        )

    def apply_payment(self, invoice_id: str, amount, reference: str):
        return self.accounting.apply_payment(invoice_id, amount, reference)

    def export_open_items(self) -> str:
        return self.accounting.export_open_items_csv()

    @staticmethod
    def tenant_modes() -> tuple[TenantMode, TenantMode]:
        return (TenantMode.SELF_BILLER, TenantMode.BILLING_CENTER)
