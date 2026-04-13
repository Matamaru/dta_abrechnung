from __future__ import annotations

from .domain import EvidenceBundle, EvidenceDocument, Rechnung
from .store import PlatformStore


class EvidenceService:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def bundle_for_invoice(self, invoice: Rechnung) -> EvidenceBundle:
        case_ids = set(invoice.case_ids)
        documents: list[EvidenceDocument] = []
        seen_document_ids: set[str] = set()
        for case_id in case_ids:
            billing_case = self.store.billing_cases[case_id]
            for service_id in billing_case.service_ids:
                service = self.store.services[service_id]
                for document_id in service.document_ids:
                    if document_id in seen_document_ids:
                        continue
                    documents.append(self.store.evidence_documents[document_id])
                    seen_document_ids.add(document_id)
        manifest = {
            "invoice_id": invoice.id,
            "document_count": str(len(documents)),
            "procedure": invoice.procedure.value,
        }
        return EvidenceBundle(invoice_id=invoice.id, documents=documents, manifest=manifest)
