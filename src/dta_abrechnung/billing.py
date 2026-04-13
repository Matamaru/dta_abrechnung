from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from .domain import (
    Abrechnungsfall,
    Korrektur,
    OffenerPosten,
    ProcedureCode,
    Rechnung,
    RechnungLine,
)
from .store import PlatformStore


@dataclass(slots=True)
class RulePack:
    procedure: ProcedureCode
    line_prefix: str

    def describe(self, service_code: str) -> str:
        return f"{self.line_prefix} {service_code}"


class BillingEngine:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store
        self.rule_packs = {
            ProcedureCode.PFLEGE: RulePack(ProcedureCode.PFLEGE, "Pflegeleistung"),
            ProcedureCode.HKP: RulePack(ProcedureCode.HKP, "HKP-Leistung"),
            ProcedureCode.HAUSHALTSHILFE: RulePack(ProcedureCode.HAUSHALTSHILFE, "Haushaltshilfe"),
            ProcedureCode.HEILMITTEL: RulePack(ProcedureCode.HEILMITTEL, "Heilmittel"),
            ProcedureCode.HILFSMITTEL: RulePack(ProcedureCode.HILFSMITTEL, "Hilfsmittel"),
            ProcedureCode.KRANKENTRANSPORT: RulePack(ProcedureCode.KRANKENTRANSPORT, "Krankentransport"),
        }

    def create_invoice(
        self,
        contract_id: str,
        service_ids: list[str] | None = None,
        previous_invoice_id: str | None = None,
        correction_reason: str | None = None,
    ) -> Rechnung:
        contract = self.store.contracts[contract_id]
        provider = self.store.providers[contract.provider_id]
        services = self._select_services(contract_id, service_ids, previous_invoice_id)
        if not services:
            raise ValueError("No services selected for invoice")
        rule_pack = self.rule_packs[contract.procedure]
        grouped_lines: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"quantity": Decimal("0.00"), "amount": Decimal("0.00"), "unit_price": Decimal("0.00")}
        )
        grouped_cases: dict[str, list[str]] = defaultdict(list)
        period_start = min(service.service_date for service in services)
        period_end = max(service.service_date for service in services)
        for service in services:
            unit_price = service.unit_price or contract.billing_codes.get(service.service_code)
            if unit_price is None:
                raise ValueError(f"No price for service code {service.service_code}")
            amount = unit_price * service.quantity
            bucket = grouped_lines[service.service_code]
            bucket["quantity"] += service.quantity
            bucket["amount"] += amount
            bucket["unit_price"] = unit_price
            grouped_cases[service.patient_id].append(service.id)
            service.invoice_id = previous_invoice_id or "pending"
        line_items = [
            RechnungLine(
                service_code=service_code,
                description=rule_pack.describe(service_code),
                quantity=data["quantity"],
                unit_price=data["unit_price"],
                amount=data["amount"],
            )
            for service_code, data in grouped_lines.items()
        ]
        total_amount = sum((line.amount for line in line_items), Decimal("0.00"))
        correction_level = 0
        processing_code = "01"
        if previous_invoice_id is not None:
            previous = self.store.invoices[previous_invoice_id]
            correction_level = previous.correction_level + 1
            processing_code = "05"
        invoice = Rechnung(
            id=f"inv-{uuid4().hex[:12]}",
            tenant_id=provider.tenant_id,
            provider_id=contract.provider_id,
            payer_id=contract.payer_id,
            contract_id=contract.id,
            procedure=contract.procedure,
            period_start=period_start,
            period_end=period_end,
            issue_date=date.today(),
            line_items=line_items,
            case_ids=[],
            total_amount=total_amount,
            currency="EUR",
            message_version=contract.version,
            message_id=str(uuid4()),
            previous_invoice_id=previous_invoice_id,
            correction_level=correction_level,
            processing_code=processing_code,
        )
        self.store.invoices[invoice.id] = invoice
        case_ids: list[str] = []
        for patient_id, patient_service_ids in grouped_cases.items():
            case_total = sum(
                (
                    (self.store.services[service_id].unit_price or contract.billing_codes[self.store.services[service_id].service_code])
                    * self.store.services[service_id].quantity
                )
                for service_id in patient_service_ids
            )
            billing_case = Abrechnungsfall(
                id=f"case-{uuid4().hex[:12]}",
                invoice_id=invoice.id,
                tenant_id=provider.tenant_id,
                provider_id=contract.provider_id,
                payer_id=contract.payer_id,
                patient_id=patient_id,
                procedure=contract.procedure,
                service_ids=patient_service_ids,
                total_amount=case_total,
            )
            self.store.billing_cases[billing_case.id] = billing_case
            case_ids.append(billing_case.id)
            for service_id in patient_service_ids:
                self.store.services[service_id].invoice_id = invoice.id
        invoice.case_ids = case_ids
        open_item = OffenerPosten(
            id=f"op-{uuid4().hex[:12]}",
            invoice_id=invoice.id,
            due_amount=total_amount,
        )
        self.store.open_items[open_item.id] = open_item
        if previous_invoice_id is not None:
            correction = Korrektur(
                id=f"corr-{uuid4().hex[:12]}",
                replacement_invoice_id=invoice.id,
                original_invoice_id=previous_invoice_id,
                reason=correction_reason or "Correction",
                created_at=datetime.now(UTC),
            )
            self.store.corrections[correction.id] = correction
        return invoice

    def _select_services(
        self,
        contract_id: str,
        service_ids: list[str] | None,
        previous_invoice_id: str | None,
    ) -> list:
        contract = self.store.contracts[contract_id]
        if service_ids is not None:
            services = [self.store.services[service_id] for service_id in service_ids]
        else:
            services = [
                service
                for service in self.store.services.values()
                if service.provider_id == contract.provider_id
                and service.procedure == contract.procedure
                and service.invoice_id is None
            ]
        if previous_invoice_id is None:
            return services
        return services
