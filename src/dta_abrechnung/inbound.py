from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .domain import Fehlernachricht, InboundEvent, SubmissionStatus, TransportFamily
from .procedures import ProcedureAdapter
from .store import PlatformStore


class InboundProcessingService:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def process(
        self,
        adapter: ProcedureAdapter,
        invoice_id: str,
        submission_id: str,
        raw_message: bytes,
        transport: TransportFamily,
    ) -> list[InboundEvent]:
        events = []
        submission = self.store.submissions[submission_id]
        for parsed in adapter.parse_inbound(invoice_id, raw_message, transport):
            status = (
                SubmissionStatus.ACKNOWLEDGED
                if parsed["status"] == "acknowledged"
                else SubmissionStatus.REJECTED
            )
            event = InboundEvent(
                id=f"inbound-{uuid4().hex[:12]}",
                invoice_id=invoice_id,
                kind=str(parsed["kind"]),
                message=str(parsed["message"]),
                technical=bool(parsed["technical"]),
                status_transition=status,
                metadata={"submission_id": submission_id},
            )
            self.store.inbound_events[event.id] = event
            events.append(event)
            submission.status = status
            if status == SubmissionStatus.REJECTED:
                error = Fehlernachricht(
                    id=f"err-{uuid4().hex[:12]}",
                    invoice_id=invoice_id,
                    procedure=self.store.invoices[invoice_id].procedure,
                    technical=bool(parsed["technical"]),
                    code="INBOUND_ERROR",
                    message=str(parsed["message"]),
                    created_at=datetime.now(UTC),
                )
                self.store.error_messages[error.id] = error
        return events
