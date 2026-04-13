from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from .domain import OpenItemStatus, Zahlung
from .store import PlatformStore


class AccountingExportService:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def apply_payment(self, invoice_id: str, amount: Decimal | str | int | float, reference: str) -> Zahlung:
        payment = Zahlung(
            id=f"pay-{uuid4().hex[:12]}",
            invoice_id=invoice_id,
            amount=Decimal(str(amount)),
            reference=reference,
            booked_at=datetime.now(UTC),
        )
        self.store.payments[payment.id] = payment
        open_item = next(item for item in self.store.open_items.values() if item.invoice_id == invoice_id)
        open_item.paid_amount += payment.amount
        if open_item.paid_amount >= open_item.due_amount:
            open_item.status = OpenItemStatus.PAID
        elif open_item.paid_amount > Decimal("0.00"):
            open_item.status = OpenItemStatus.PARTIALLY_PAID
        return payment

    def export_open_items_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "invoice_id",
                "procedure",
                "payer_ik",
                "provider_ik",
                "due_amount",
                "paid_amount",
                "open_amount",
                "status",
            ]
        )
        for open_item in sorted(self.store.open_items.values(), key=lambda item: item.invoice_id):
            invoice = self.store.invoices[open_item.invoice_id]
            payer = self.store.payers[invoice.payer_id]
            provider = self.store.providers[invoice.provider_id]
            writer.writerow(
                [
                    invoice.id,
                    invoice.procedure.value,
                    payer.ik.value,
                    provider.effective_billing_ik.value,
                    str(open_item.due_amount),
                    str(open_item.paid_amount),
                    str(open_item.due_amount - open_item.paid_amount),
                    open_item.status.value,
                ]
            )
        return buffer.getvalue()
