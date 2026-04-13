from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .domain import (
    Abrechnungsfall,
    Abrechnungszentrum,
    EvidenceDocument,
    Fehlernachricht,
    InboundEvent,
    Kostentraeger,
    Korrektur,
    Leistungsnachweis,
    Leistungserbringer,
    Mandant,
    OffenerPosten,
    Rechnung,
    SubmissionJob,
    Vertrag,
    Verordnung,
    Zahlung,
)


@dataclass(slots=True)
class PlatformStore:
    tenants: dict[str, Mandant] = field(default_factory=dict)
    billing_centers: dict[str, Abrechnungszentrum] = field(default_factory=dict)
    providers: dict[str, Leistungserbringer] = field(default_factory=dict)
    payers: dict[str, Kostentraeger] = field(default_factory=dict)
    contracts: dict[str, Vertrag] = field(default_factory=dict)
    prescriptions: dict[str, Verordnung] = field(default_factory=dict)
    evidence_documents: dict[str, EvidenceDocument] = field(default_factory=dict)
    services: dict[str, Leistungsnachweis] = field(default_factory=dict)
    billing_cases: dict[str, Abrechnungsfall] = field(default_factory=dict)
    invoices: dict[str, Rechnung] = field(default_factory=dict)
    corrections: dict[str, Korrektur] = field(default_factory=dict)
    error_messages: dict[str, Fehlernachricht] = field(default_factory=dict)
    payments: dict[str, Zahlung] = field(default_factory=dict)
    open_items: dict[str, OffenerPosten] = field(default_factory=dict)
    submissions: dict[str, SubmissionJob] = field(default_factory=dict)
    inbound_events: dict[str, InboundEvent] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def next_counter(self, name: str) -> int:
        self.counters[name] += 1
        return self.counters[name]
