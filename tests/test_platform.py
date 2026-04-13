from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dta_abrechnung.domain import EvidenceKind, ProcedureCapability, ProcedureCode, TenantMode, TransportFamily
from dta_abrechnung.platform import NationalDtaPlatform


class NationalDtaPlatformTest(unittest.TestCase):
    def build_pflege_setup(self) -> tuple[NationalDtaPlatform, str]:
        platform = NationalDtaPlatform()
        tenant = platform.care_ops.create_tenant("Nord Pflege", TenantMode.BILLING_CENTER)
        platform.care_ops.create_billing_center(tenant.id, "Nord Billing", "987654321")
        provider = platform.care_ops.create_provider(tenant.id, "Pflegedienst Nord", "123456789", billing_ik="223456789")
        payer = platform.master_data.register_payer(
            name="AOK Nord",
            ik="109876543",
            kassenart="AOK",
            capabilities={
                ProcedureCode.PFLEGE: ProcedureCapability(
                    procedure=ProcedureCode.PFLEGE,
                    allowed_transports={TransportFamily.CLASSIC_DTA, TransportFamily.TI_KIM},
                    classic_address="pflege@classic.aok.example",
                    kim_address="pflege@aok.kim.telematik",
                    requires_dakota=True,
                )
            },
        )
        contract = platform.care_ops.register_contract(
            provider_id=provider.id,
            payer_id=payer.id,
            procedure=ProcedureCode.PFLEGE,
            version="6.4.0",
            allowed_transports=[TransportFamily.CLASSIC_DTA, TransportFamily.TI_KIM],
            billing_codes={"P-01": "72.50"},
        )
        prescription = platform.care_ops.create_prescription(
            provider_id=provider.id,
            patient_id="patient-1",
            procedure=ProcedureCode.PFLEGE,
            valid_from=date(2026, 4, 1),
            valid_to=date(2026, 4, 30),
            service_code="P-01",
            signed_at=datetime(2026, 4, 1, 9, 0, 0),
        )
        document = platform.care_ops.add_evidence(
            provider_id=provider.id,
            kind=EvidenceKind.IMAGE_SCAN,
            filename="leistungsnachweis.pdf",
            content_type="application/pdf",
            content=b"scan-data",
        )
        service = platform.care_ops.record_service(
            provider_id=provider.id,
            prescription_id=prescription.id,
            patient_id="patient-1",
            service_date=date(2026, 4, 3),
            service_code="P-01",
            quantity=1,
            performed_by="nurse-1",
            document_ids=[document.id],
            signed=True,
        )
        invoice = platform.billing.create_invoice(contract.id, service_ids=[service.id])
        return platform, invoice.id

    def test_pflege_classic_submission_builds_auftragsdatei_and_payload(self) -> None:
        platform, invoice_id = self.build_pflege_setup()

        submission = platform.submit_invoice(invoice_id, transport=TransportFamily.CLASSIC_DTA)

        self.assertEqual(submission.transport, TransportFamily.CLASSIC_DTA)
        self.assertEqual(submission.envelope.routing_target.channel, "dakota")
        artifact_names = [artifact.filename for artifact in submission.envelope.artifacts]
        self.assertIn("EPFL0001", artifact_names)
        self.assertIn("EPFL0001.AUF", artifact_names)
        auftragsdatei = next(
            artifact.content.decode("iso-8859-1")
            for artifact in submission.envelope.artifacts
            if artifact.filename.endswith(".AUF")
        )
        self.assertIn("VERFAHRENSKENNUNG=EPFL0", auftragsdatei)
        self.assertIn("DAKOTA=required", auftragsdatei)

    def test_hkp_ti_submission_uses_vzd_and_service_identifier(self) -> None:
        platform = NationalDtaPlatform()
        tenant = platform.care_ops.create_tenant("HKP Direct", TenantMode.SELF_BILLER)
        provider = platform.care_ops.create_provider(tenant.id, "HKP Mitte", "333333333")
        payer = platform.master_data.register_payer(
            name="Ersatzkasse Mitte",
            ik="444444444",
            kassenart="EK",
            capabilities={
                ProcedureCode.HKP: ProcedureCapability(
                    procedure=ProcedureCode.HKP,
                    allowed_transports={TransportFamily.TI_KIM},
                    kim_address="VZD",
                )
            },
        )
        platform.external_ti_bridge.directory[payer.ik.value] = "abrechnung@ersatzkasse.kim.telematik"
        contract = platform.care_ops.register_contract(
            provider_id=provider.id,
            payer_id=payer.id,
            procedure=ProcedureCode.HKP,
            version="1.1.0",
            allowed_transports=[TransportFamily.TI_KIM],
            billing_codes={"HKP-01": "54.25"},
        )
        prescription = platform.care_ops.create_prescription(
            provider_id=provider.id,
            patient_id="patient-2",
            procedure=ProcedureCode.HKP,
            valid_from=date(2027, 2, 1),
            valid_to=date(2027, 2, 28),
            service_code="HKP-01",
            signed_at=datetime(2027, 2, 1, 8, 0, 0),
        )
        signature = platform.care_ops.add_evidence(
            provider_id=provider.id,
            kind=EvidenceKind.SIGNATURE,
            filename="eln.xml",
            content_type="application/xml",
            content=b"<eln/>",
            signed=True,
        )
        service = platform.care_ops.record_service(
            provider_id=provider.id,
            prescription_id=prescription.id,
            patient_id="patient-2",
            service_date=date(2027, 2, 3),
            service_code="HKP-01",
            quantity=2,
            performed_by="nurse-2",
            document_ids=[signature.id],
            signed=True,
        )
        invoice = platform.billing.create_invoice(contract.id, service_ids=[service.id])

        submission = platform.submit_invoice(invoice.id, transport=TransportFamily.TI_KIM, ti_mode="external")

        self.assertEqual(submission.envelope.routing_target.address, "abrechnung@ersatzkasse.kim.telematik")
        self.assertEqual(submission.envelope.metadata["service_identifier"], "HKP;ABR_0000;V1.1.0")
        self.assertTrue(submission.envelope.artifacts[0].filename.startswith("EHKP0_ABR_0000_"))
        outbox_message = platform.external_ti_bridge.outbox[-1]
        self.assertEqual(outbox_message.recipient, "abrechnung@ersatzkasse.kim.telematik")
        self.assertEqual(outbox_message.service_identifier, "HKP;ABR_0000;V1.1.0")
        for attachment in outbox_message.attachments:
            self.assertTrue(platform.external_ti_bridge.verify_blob(attachment.artifact.content, attachment.signature))

    def test_correction_chain_and_accounting_export(self) -> None:
        platform = NationalDtaPlatform()
        tenant = platform.care_ops.create_tenant("Therapie Verbund", TenantMode.SELF_BILLER)
        provider = platform.care_ops.create_provider(tenant.id, "Therapie Verbund", "555555555")
        payer = platform.master_data.register_payer(
            name="BKK Therapie",
            ik="666666666",
            kassenart="BK",
            capabilities={
                ProcedureCode.HEILMITTEL: ProcedureCapability(
                    procedure=ProcedureCode.HEILMITTEL,
                    allowed_transports={TransportFamily.CLASSIC_DTA},
                    classic_address="heilmittel@bkk.example",
                )
            },
        )
        contract = platform.care_ops.register_contract(
            provider_id=provider.id,
            payer_id=payer.id,
            procedure=ProcedureCode.HEILMITTEL,
            version="21",
            allowed_transports=[TransportFamily.CLASSIC_DTA],
            billing_codes={"HM-01": "35.00"},
        )
        prescription = platform.care_ops.create_prescription(
            provider_id=provider.id,
            patient_id="patient-3",
            procedure=ProcedureCode.HEILMITTEL,
            valid_from=date(2026, 6, 1),
            valid_to=date(2026, 6, 30),
            service_code="HM-01",
        )
        document = platform.care_ops.add_evidence(
            provider_id=provider.id,
            kind=EvidenceKind.PDF,
            filename="verordnung.pdf",
            content_type="application/pdf",
            content=b"pdf",
        )
        original_service = platform.care_ops.record_service(
            provider_id=provider.id,
            prescription_id=prescription.id,
            patient_id="patient-3",
            service_date=date(2026, 6, 5),
            service_code="HM-01",
            quantity=1,
            performed_by="therapist-1",
            document_ids=[document.id],
        )
        original_invoice = platform.billing.create_invoice(contract.id, service_ids=[original_service.id])
        platform.apply_payment(original_invoice.id, "10.00", "partial-1")

        correction_invoice = platform.billing.create_invoice(
            contract.id,
            service_ids=[original_service.id],
            previous_invoice_id=original_invoice.id,
            correction_reason="Nachforderung",
        )

        self.assertEqual(correction_invoice.processing_code, "05")
        self.assertEqual(correction_invoice.correction_level, 1)
        self.assertEqual(len(platform.store.corrections), 1)
        csv_export = platform.export_open_items()
        self.assertIn(original_invoice.id, csv_export)
        self.assertIn(correction_invoice.id, csv_export)
        original_open_item = next(item for item in platform.store.open_items.values() if item.invoice_id == original_invoice.id)
        self.assertEqual(original_open_item.status.value, "partially_paid")

    def test_billing_center_scopes_provider_specific_invoices(self) -> None:
        platform = NationalDtaPlatform()
        tenant = platform.care_ops.create_tenant("Zentralservice", TenantMode.BILLING_CENTER)
        platform.care_ops.create_billing_center(tenant.id, "Zentralservice Billing", "777777777")
        provider_a = platform.care_ops.create_provider(tenant.id, "Provider A", "101010101", billing_ik="202020202")
        provider_b = platform.care_ops.create_provider(tenant.id, "Provider B", "303030303", billing_ik="404040404")
        payer = platform.master_data.register_payer(
            name="Hilfsmittelkasse",
            ik="505050505",
            kassenart="IK",
            capabilities={
                ProcedureCode.HILFSMITTEL: ProcedureCapability(
                    procedure=ProcedureCode.HILFSMITTEL,
                    allowed_transports={TransportFamily.CLASSIC_DTA},
                    classic_address="hilfsmittel@kasse.example",
                )
            },
        )
        contract_a = platform.care_ops.register_contract(
            provider_id=provider_a.id,
            payer_id=payer.id,
            procedure=ProcedureCode.HILFSMITTEL,
            version="21",
            allowed_transports=[TransportFamily.CLASSIC_DTA],
            billing_codes={"HI-01": "20.00"},
        )
        contract_b = platform.care_ops.register_contract(
            provider_id=provider_b.id,
            payer_id=payer.id,
            procedure=ProcedureCode.HILFSMITTEL,
            version="21",
            allowed_transports=[TransportFamily.CLASSIC_DTA],
            billing_codes={"HI-01": "45.00"},
        )
        prescription_a = platform.care_ops.create_prescription(
            provider_id=provider_a.id,
            patient_id="patient-a",
            procedure=ProcedureCode.HILFSMITTEL,
            valid_from=date(2026, 5, 1),
            valid_to=date(2026, 5, 31),
            service_code="HI-01",
        )
        prescription_b = platform.care_ops.create_prescription(
            provider_id=provider_b.id,
            patient_id="patient-b",
            procedure=ProcedureCode.HILFSMITTEL,
            valid_from=date(2026, 5, 1),
            valid_to=date(2026, 5, 31),
            service_code="HI-01",
        )
        doc_a = platform.care_ops.add_evidence(provider_a.id, EvidenceKind.PDF, "a.pdf", "application/pdf", b"a")
        doc_b = platform.care_ops.add_evidence(provider_b.id, EvidenceKind.PDF, "b.pdf", "application/pdf", b"b")
        platform.care_ops.record_service(
            provider_id=provider_a.id,
            prescription_id=prescription_a.id,
            patient_id="patient-a",
            service_date=date(2026, 5, 2),
            service_code="HI-01",
            quantity=1,
            performed_by="staff-a",
            document_ids=[doc_a.id],
        )
        platform.care_ops.record_service(
            provider_id=provider_b.id,
            prescription_id=prescription_b.id,
            patient_id="patient-b",
            service_date=date(2026, 5, 2),
            service_code="HI-01",
            quantity=1,
            performed_by="staff-b",
            document_ids=[doc_b.id],
        )

        invoice_a = platform.billing.create_invoice(contract_a.id)
        invoice_b = platform.billing.create_invoice(contract_b.id)

        self.assertEqual(invoice_a.total_amount, Decimal("20.00"))
        self.assertEqual(invoice_b.total_amount, Decimal("45.00"))
        self.assertNotEqual(invoice_a.provider_id, invoice_b.provider_id)

    def test_inbound_rejection_creates_error_message(self) -> None:
        platform, invoice_id = self.build_pflege_setup()
        submission = platform.submit_invoice(invoice_id, transport=TransportFamily.CLASSIC_DTA)

        events = platform.process_inbound(submission.id, b"FEHLER|INBOUND|Technischer Fehler")

        self.assertEqual(len(events), 1)
        self.assertEqual(platform.store.submissions[submission.id].status.value, "rejected")
        self.assertEqual(len(platform.store.error_messages), 1)


if __name__ == "__main__":
    unittest.main()
