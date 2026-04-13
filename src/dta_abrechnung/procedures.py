from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring

from .domain import (
    EvidenceBundle,
    ProcedureCode,
    RoutingTarget,
    SerializedPayload,
    SubmissionArtifact,
    TransportFamily,
)
from .masterdata import PayerMasterDataService
from .store import PlatformStore
from .transport import TiBridge


class ProcedureAdapter(ABC):
    procedure: ProcedureCode
    supported_transports: set[TransportFamily]
    version: str

    @abstractmethod
    def validate(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def serialize(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
        sequence_number: int,
    ) -> SerializedPayload:
        raise NotImplementedError

    @abstractmethod
    def package_evidence(
        self,
        invoice_id: str,
        transport: TransportFamily,
        evidence_bundle: EvidenceBundle,
    ) -> list[SubmissionArtifact]:
        raise NotImplementedError

    def route(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        master_data: PayerMasterDataService,
        ti_bridge: TiBridge | None = None,
    ) -> RoutingTarget:
        invoice = store.invoices[invoice_id]
        return master_data.resolve_route(invoice.payer_id, invoice.procedure, transport, ti_bridge=ti_bridge)

    @abstractmethod
    def parse_inbound(
        self,
        invoice_id: str,
        raw_message: bytes,
        transport: TransportFamily,
    ) -> list[dict[str, str | bool]]:
        raise NotImplementedError

    def _invoice_lines(self, invoice_id: str, store: PlatformStore) -> list[tuple[str, Decimal, Decimal, Decimal]]:
        invoice = store.invoices[invoice_id]
        return [
            (line.service_code, line.quantity, line.unit_price, line.amount)
            for line in invoice.line_items
        ]


class PflegeProcedureAdapter(ProcedureAdapter):
    procedure = ProcedureCode.PFLEGE
    supported_transports = {TransportFamily.CLASSIC_DTA, TransportFamily.TI_KIM}
    version = "6.4.0"

    def validate(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
    ) -> None:
        if not evidence_bundle.documents:
            raise ValueError("Pflege invoices require linked evidence")
        if transport not in self.supported_transports:
            raise ValueError("Transport not supported for Pflege")

    def serialize(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
        sequence_number: int,
    ) -> SerializedPayload:
        invoice = store.invoices[invoice_id]
        provider = store.providers[invoice.provider_id]
        payer = store.payers[invoice.payer_id]
        if transport == TransportFamily.CLASSIC_DTA:
            filename = f"EPFL0{sequence_number:03d}"
            control_ref = f"{sequence_number:06d}"
            segments = [
                f"UNB+UNOA:3+{provider.ik.value}+{payer.ik.value}+{invoice.issue_date.strftime('%y%m%d')}:{datetime.now(UTC).strftime('%H%M')}+{control_ref}'",
                "UNH+1+PLGA:D:96A:UN:PFLEGE'",
                f"BGM+380+{invoice.id}+9'",
                f"DTM+137:{invoice.issue_date.isoformat()}:102'",
            ]
            for service_code, quantity, unit_price, amount in self._invoice_lines(invoice_id, store):
                segments.append(f"LIN+{service_code}'")
                segments.append(f"QTY+47:{quantity}'")
                segments.append(f"PRI+AAA:{unit_price}'")
                segments.append(f"MOA+203:{amount}'")
            segments.append(f"MOA+9:{invoice.total_amount}'")
            segments.append("UNT+9+1'")
            segments.append(f"UNZ+1+{control_ref}'")
            return SerializedPayload(
                artifact=SubmissionArtifact(
                    filename=filename,
                    content="\n".join(segments).encode("iso-8859-1"),
                    media_type="application/edifact",
                    description="Pflege classic payload",
                ),
                verfahrenskennung="EPFL0",
                message_type="PLGA",
                version=self.version,
            )
        filename = f"EPFL0_ABR_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.xml"
        root = Element("PflegeAbrechnung")
        header = SubElement(root, "Header")
        SubElement(header, "Verfahrenskennung").text = "EPFL0"
        SubElement(header, "Version").text = self.version
        SubElement(header, "RechnungID").text = invoice.id
        body = SubElement(root, "Body")
        for service_code, quantity, unit_price, amount in self._invoice_lines(invoice_id, store):
            line = SubElement(body, "Leistung")
            SubElement(line, "Code").text = service_code
            SubElement(line, "Menge").text = str(quantity)
            SubElement(line, "Preis").text = str(unit_price)
            SubElement(line, "Betrag").text = str(amount)
        return SerializedPayload(
            artifact=SubmissionArtifact(
                filename=filename,
                content=tostring(root, encoding="utf-8", xml_declaration=True),
                media_type="application/xml",
                description="Pflege TI payload",
            ),
            verfahrenskennung="EPFL0",
            message_type="ABR",
            version=self.version,
        )

    def package_evidence(
        self,
        invoice_id: str,
        transport: TransportFamily,
        evidence_bundle: EvidenceBundle,
    ) -> list[SubmissionArtifact]:
        suffix = "sig" if transport == TransportFamily.TI_KIM else "scan"
        return [
            SubmissionArtifact(
                filename=f"{document.id}_{suffix}_{document.filename}",
                content=document.content,
                media_type=document.content_type,
                description=f"Pflege evidence {document.kind.value}",
            )
            for document in evidence_bundle.documents
        ]

    def parse_inbound(
        self,
        invoice_id: str,
        raw_message: bytes,
        transport: TransportFamily,
    ) -> list[dict[str, str | bool]]:
        text = raw_message.decode("utf-8", errors="replace")
        if "FEH" in text or "ERROR" in text:
            return [{"kind": "error", "message": text, "technical": True, "status": "rejected"}]
        return [{"kind": "ack", "message": text, "technical": False, "status": "acknowledged"}]


class HkpProcedureAdapter(ProcedureAdapter):
    procedure = ProcedureCode.HKP
    supported_transports = {TransportFamily.TI_KIM}
    version = "1.1.0"

    def validate(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
    ) -> None:
        if transport != TransportFamily.TI_KIM:
            raise ValueError("HKP requires TI/KIM")
        if not evidence_bundle.documents:
            raise ValueError("HKP invoices require electronic evidence")

    def serialize(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
        sequence_number: int,
    ) -> SerializedPayload:
        del sequence_number
        invoice = store.invoices[invoice_id]
        provider = store.providers[invoice.provider_id]
        payer = store.payers[invoice.payer_id]
        root = Element("HKPAbrechnungsnachricht")
        header = SubElement(root, "Header")
        SubElement(header, "Verfahrenskennung").text = "EHKP0"
        SubElement(header, "Nachrichtentyp").text = "ABR_0000"
        SubElement(header, "RechnungID").text = invoice.id
        SubElement(header, "AbsenderIK").text = provider.ik.value
        SubElement(header, "EmpfaengerIK").text = payer.ik.value
        SubElement(header, "LogischeVersion").text = self.version
        body = SubElement(root, "Body")
        for case_id in invoice.case_ids:
            billing_case = store.billing_cases[case_id]
            case_element = SubElement(body, "Abrechnungsfall")
            SubElement(case_element, "PatientID").text = billing_case.patient_id
            for service_id in billing_case.service_ids:
                service = store.services[service_id]
                line = SubElement(case_element, "Position")
                SubElement(line, "Code").text = service.service_code
                SubElement(line, "Menge").text = str(service.quantity)
                price = service.unit_price or Decimal("0.00")
                SubElement(line, "Preis").text = str(price)
        filename = f"EHKP0_ABR_0000_{invoice.message_id}.xml"
        return SerializedPayload(
            artifact=SubmissionArtifact(
                filename=filename,
                content=tostring(root, encoding="utf-8", xml_declaration=True),
                media_type="application/xml",
                description="HKP TI payload",
            ),
            verfahrenskennung="EHKP0",
            message_type="ABR_0000",
            version=self.version,
        )

    def package_evidence(
        self,
        invoice_id: str,
        transport: TransportFamily,
        evidence_bundle: EvidenceBundle,
    ) -> list[SubmissionArtifact]:
        del invoice_id, transport
        return [
            SubmissionArtifact(
                filename=document.filename,
                content=document.content,
                media_type=document.content_type,
                description=f"HKP evidence {document.kind.value}",
            )
            for document in evidence_bundle.documents
        ]

    def parse_inbound(
        self,
        invoice_id: str,
        raw_message: bytes,
        transport: TransportFamily,
    ) -> list[dict[str, str | bool]]:
        del invoice_id, transport
        text = raw_message.decode("utf-8", errors="replace")
        if "FEH_TECH" in text or "Fehler" in text:
            return [{"kind": "error", "message": text, "technical": True, "status": "rejected"}]
        return [{"kind": "dsn", "message": text, "technical": False, "status": "acknowledged"}]


class Classic302ProcedureAdapter(ProcedureAdapter):
    supported_transports = {TransportFamily.CLASSIC_DTA}
    version = "21"
    verfahrenskennung = "ESOL0"

    def __init__(self, procedure: ProcedureCode, segment_label: str) -> None:
        self.procedure = procedure
        self.segment_label = segment_label

    def validate(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
    ) -> None:
        del invoice_id, store
        if transport != TransportFamily.CLASSIC_DTA:
            raise ValueError("This TP5 lane is classic-first")
        if not evidence_bundle.documents:
            raise ValueError("TP5 lanes require linked evidence")

    def serialize(
        self,
        invoice_id: str,
        transport: TransportFamily,
        store: PlatformStore,
        evidence_bundle: EvidenceBundle,
        sequence_number: int,
    ) -> SerializedPayload:
        del transport, evidence_bundle
        invoice = store.invoices[invoice_id]
        provider = store.providers[invoice.provider_id]
        payer = store.payers[invoice.payer_id]
        filename = f"{self.verfahrenskennung}{sequence_number:03d}"
        control_ref = f"{sequence_number:06d}"
        segments = [
            f"UNB+UNOA:3+{provider.ik.value}+{payer.ik.value}+{invoice.issue_date.strftime('%y%m%d')}:{datetime.now(UTC).strftime('%H%M')}+{control_ref}'",
            f"UNH+1+{self.segment_label}:D:96A:UN:TP5'",
            f"BGM+380+{invoice.id}+9'",
        ]
        for service_code, quantity, unit_price, amount in self._invoice_lines(invoice_id, store):
            segments.append(f"LIN+{service_code}'")
            segments.append(f"QTY+47:{quantity}'")
            segments.append(f"PRI+AAA:{unit_price}'")
            segments.append(f"MOA+203:{amount}'")
        segments.append(f"MOA+9:{invoice.total_amount}'")
        segments.append(f"UNZ+1+{control_ref}'")
        return SerializedPayload(
            artifact=SubmissionArtifact(
                filename=filename,
                content="\n".join(segments).encode("iso-8859-1"),
                media_type="application/edifact",
                description=f"{self.procedure.value} classic payload",
            ),
            verfahrenskennung=self.verfahrenskennung,
            message_type=self.segment_label,
            version=self.version,
        )

    def package_evidence(
        self,
        invoice_id: str,
        transport: TransportFamily,
        evidence_bundle: EvidenceBundle,
    ) -> list[SubmissionArtifact]:
        del invoice_id, transport
        return [
            SubmissionArtifact(
                filename=document.filename,
                content=document.content,
                media_type=document.content_type,
                description=f"{self.procedure.value} evidence",
            )
            for document in evidence_bundle.documents
        ]

    def parse_inbound(
        self,
        invoice_id: str,
        raw_message: bytes,
        transport: TransportFamily,
    ) -> list[dict[str, str | bool]]:
        del invoice_id, transport
        text = raw_message.decode("utf-8", errors="replace")
        if "FEHLER" in text:
            return [{"kind": "error", "message": text, "technical": True, "status": "rejected"}]
        return [{"kind": "ack", "message": text, "technical": False, "status": "acknowledged"}]
