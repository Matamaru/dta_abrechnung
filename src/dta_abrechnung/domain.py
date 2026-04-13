from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class TenantMode(StrEnum):
    SELF_BILLER = "self_biller"
    BILLING_CENTER = "billing_center"


class TransportFamily(StrEnum):
    CLASSIC_DTA = "classic_dta"
    TI_KIM = "ti_kim"


class ProcedureCode(StrEnum):
    PFLEGE = "pflege_sgb_xi"
    HKP = "hkp_sgb_v"
    HAUSHALTSHILFE = "haushaltshilfe_sgb_v"
    HEILMITTEL = "heilmittel_sgb_v"
    HILFSMITTEL = "hilfsmittel_sgb_v"
    KRANKENTRANSPORT = "krankentransport_sgb_v"


class EvidenceKind(StrEnum):
    SIGNATURE = "signature"
    IMAGE_SCAN = "image_scan"
    PDF = "pdf"
    XML = "xml"
    OTHER = "other"


class SubmissionStatus(StrEnum):
    CREATED = "created"
    PACKAGED = "packaged"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"


class OpenItemStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"


@dataclass(slots=True, frozen=True)
class InstitutionCode:
    value: str

    def __post_init__(self) -> None:
        if not self.value.isdigit():
            raise ValueError("IK must be numeric")


@dataclass(slots=True)
class Mandant:
    id: str
    name: str
    mode: TenantMode
    created_at: datetime


@dataclass(slots=True)
class Abrechnungszentrum:
    id: str
    tenant_id: str
    name: str
    ik: InstitutionCode


@dataclass(slots=True)
class Leistungserbringer:
    id: str
    tenant_id: str
    name: str
    ik: InstitutionCode
    billing_ik: InstitutionCode | None = None


@dataclass(slots=True)
class ProcedureCapability:
    procedure: ProcedureCode
    allowed_transports: set[TransportFamily]
    classic_address: str | None = None
    kim_address: str | None = None
    requires_dakota: bool = False
    route_notes: list[str] = field(default_factory=list)
    capability_flags: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Kostentraeger:
    id: str
    name: str
    ik: InstitutionCode
    kassenart: str
    capabilities: dict[ProcedureCode, ProcedureCapability]
    data_acceptance_changes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Vertrag:
    id: str
    provider_id: str
    payer_id: str
    procedure: ProcedureCode
    version: str
    allowed_transports: list[TransportFamily]
    billing_codes: dict[str, Decimal]
    national: bool = True


@dataclass(slots=True)
class Verordnung:
    id: str
    provider_id: str
    patient_id: str
    procedure: ProcedureCode
    valid_from: date
    valid_to: date
    service_code: str
    signed_at: datetime | None = None


@dataclass(slots=True)
class EvidenceDocument:
    id: str
    tenant_id: str
    provider_id: str
    kind: EvidenceKind
    filename: str
    content_type: str
    content: bytes
    created_at: datetime
    signed: bool = False


@dataclass(slots=True)
class Leistungsnachweis:
    id: str
    tenant_id: str
    provider_id: str
    prescription_id: str
    procedure: ProcedureCode
    patient_id: str
    service_date: date
    service_code: str
    quantity: Decimal
    performed_by: str
    unit_price: Decimal | None = None
    document_ids: list[str] = field(default_factory=list)
    signed: bool = False
    source_system: str = "care_ops"
    invoice_id: str | None = None


@dataclass(slots=True)
class Abrechnungsfall:
    id: str
    invoice_id: str
    tenant_id: str
    provider_id: str
    payer_id: str
    patient_id: str
    procedure: ProcedureCode
    service_ids: list[str]
    total_amount: Decimal


@dataclass(slots=True)
class RechnungLine:
    service_code: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


@dataclass(slots=True)
class Rechnung:
    id: str
    tenant_id: str
    provider_id: str
    payer_id: str
    contract_id: str
    procedure: ProcedureCode
    period_start: date
    period_end: date
    issue_date: date
    line_items: list[RechnungLine]
    case_ids: list[str]
    total_amount: Decimal
    currency: str
    message_version: str
    message_id: str
    previous_invoice_id: str | None = None
    correction_level: int = 0
    processing_code: str = "01"


@dataclass(slots=True)
class Korrektur:
    id: str
    replacement_invoice_id: str
    original_invoice_id: str
    reason: str
    created_at: datetime


@dataclass(slots=True)
class Fehlernachricht:
    id: str
    invoice_id: str
    procedure: ProcedureCode
    technical: bool
    code: str
    message: str
    created_at: datetime


@dataclass(slots=True)
class Zahlung:
    id: str
    invoice_id: str
    amount: Decimal
    reference: str
    booked_at: datetime


@dataclass(slots=True)
class OffenerPosten:
    id: str
    invoice_id: str
    due_amount: Decimal
    paid_amount: Decimal = Decimal("0.00")
    status: OpenItemStatus = OpenItemStatus.OPEN


@dataclass(slots=True)
class RoutingTarget:
    transport: TransportFamily
    procedure: ProcedureCode
    receiver_ik: str
    receiver_name: str
    address: str
    channel: str
    requires_dakota: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SubmissionArtifact:
    filename: str
    content: bytes
    media_type: str
    description: str


@dataclass(slots=True)
class SubmissionEnvelope:
    routing_target: RoutingTarget
    artifacts: list[SubmissionArtifact]
    metadata: dict[str, str]


@dataclass(slots=True)
class SubmissionJob:
    id: str
    invoice_id: str
    procedure: ProcedureCode
    transport: TransportFamily
    envelope: SubmissionEnvelope
    status: SubmissionStatus
    tracking_reference: str
    created_at: datetime


@dataclass(slots=True)
class EvidenceBundle:
    invoice_id: str
    documents: list[EvidenceDocument]
    manifest: dict[str, str]


@dataclass(slots=True)
class SerializedPayload:
    artifact: SubmissionArtifact
    verfahrenskennung: str
    message_type: str
    version: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class KimAttachment:
    artifact: SubmissionArtifact
    signature: str


@dataclass(slots=True)
class KimMessage:
    subject: str
    recipient: str
    service_identifier: str
    attachments: list[KimAttachment]
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class InboundEvent:
    id: str
    invoice_id: str
    kind: str
    message: str
    technical: bool
    status_transition: SubmissionStatus
    metadata: dict[str, str] = field(default_factory=dict)
