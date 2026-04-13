from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import uuid4

from .domain import (
    KimAttachment,
    KimMessage,
    ProcedureCode,
    RoutingTarget,
    SubmissionArtifact,
    SubmissionEnvelope,
)
from .store import PlatformStore


class TiBridge(ABC):
    @abstractmethod
    def lookup_vzd(self, domain_id: str, entry_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def sign_blob(self, blob: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    def verify_blob(self, blob: bytes, signature: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def send_kim(self, message: KimMessage) -> str:
        raise NotImplementedError

    @abstractmethod
    def resolve_service_identifier(
        self,
        procedure: ProcedureCode,
        message_type: str,
        version: str,
    ) -> str:
        raise NotImplementedError


class BaseTiBridge(TiBridge):
    def __init__(self, mode: str, directory: dict[str, str] | None = None) -> None:
        self.mode = mode
        self.directory = directory or {}
        self.outbox: list[KimMessage] = []

    def lookup_vzd(self, domain_id: str, entry_type: str) -> str:
        try:
            return self.directory[domain_id]
        except KeyError as exc:
            raise ValueError(f"No VZD entry for domain {domain_id} / entry type {entry_type}") from exc

    def sign_blob(self, blob: bytes) -> str:
        return hashlib.sha256(blob).hexdigest()

    def verify_blob(self, blob: bytes, signature: str) -> bool:
        return self.sign_blob(blob) == signature

    def send_kim(self, message: KimMessage) -> str:
        self.outbox.append(message)
        return f"{self.mode.upper()}-KIM-{uuid4().hex[:12]}"

    def resolve_service_identifier(
        self,
        procedure: ProcedureCode,
        message_type: str,
        version: str,
    ) -> str:
        if procedure == ProcedureCode.HKP:
            return f"HKP;{message_type};V{version}"
        if procedure == ProcedureCode.PFLEGE:
            return f"PFL;{message_type};V{version}"
        return f"TP5;{message_type};V{version}"


class ExternalTiBridge(BaseTiBridge):
    def __init__(self, directory: dict[str, str] | None = None) -> None:
        super().__init__(mode="external", directory=directory)


class NativeTiBridge(BaseTiBridge):
    def __init__(self, directory: dict[str, str] | None = None) -> None:
        super().__init__(mode="native", directory=directory)


class ClassicDtaTransportAdapter:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def submit(
        self,
        invoice_id: str,
        routing_target: RoutingTarget,
        main_artifact: SubmissionArtifact,
        verfahrenskennung: str,
        evidence_artifacts: list[SubmissionArtifact],
        sender_ik: str,
    ) -> tuple[SubmissionEnvelope, str]:
        auftrag_filename = f"{main_artifact.filename}.AUF"
        auftragsdatei = "\n".join(
            [
                f"ABSENDER_IK={sender_ik}",
                f"EMPFAENGER_IK={routing_target.receiver_ik}",
                f"DATEINAME={main_artifact.filename}",
                f"VERFAHRENSKENNUNG={verfahrenskennung}",
                "KKS_VERSION=2.2",
                f"KANAL={routing_target.channel}",
                f"ROUTE={routing_target.address}",
                f"DAKOTA={'required' if routing_target.requires_dakota else 'optional'}",
                f"INVOICE_ID={invoice_id}",
                f"CREATED_AT={datetime.now(UTC).isoformat()}",
            ]
        ).encode("iso-8859-1")
        envelope = SubmissionEnvelope(
            routing_target=routing_target,
            artifacts=[
                main_artifact,
                SubmissionArtifact(
                    filename=auftrag_filename,
                    content=auftragsdatei,
                    media_type="text/plain",
                    description="Auftragsdatei",
                ),
                *evidence_artifacts,
            ],
            metadata={
                "submission_family": "classic_dta",
                "dakota_mode": "required" if routing_target.requires_dakota else "optional",
            },
        )
        tracking_reference = f"CLASSIC-{self.store.next_counter('classic_submission'):06d}"
        return envelope, tracking_reference


class TiKimTransportAdapter:
    def __init__(self, bridge: TiBridge) -> None:
        self.bridge = bridge

    def submit(
        self,
        routing_target: RoutingTarget,
        main_artifact: SubmissionArtifact,
        evidence_artifacts: list[SubmissionArtifact],
        procedure: ProcedureCode,
        message_type: str,
        version: str,
    ) -> tuple[SubmissionEnvelope, str]:
        artifacts = [main_artifact, *evidence_artifacts]
        attachments: list[KimAttachment] = []
        for artifact in artifacts:
            signature = self.bridge.sign_blob(artifact.content)
            if not self.bridge.verify_blob(artifact.content, signature):
                raise ValueError(f"Bridge signature verification failed for artifact {artifact.filename}")
            attachments.append(KimAttachment(artifact=artifact, signature=signature))
        service_identifier = self.bridge.resolve_service_identifier(
            procedure=procedure,
            message_type=message_type,
            version=version,
        )
        message = KimMessage(
            subject=main_artifact.filename.rsplit(".", 1)[0],
            recipient=routing_target.address,
            service_identifier=service_identifier,
            attachments=attachments,
            headers={"X-KIM-Dienstkennung": service_identifier},
        )
        tracking_reference = self.bridge.send_kim(message)
        envelope = SubmissionEnvelope(
            routing_target=routing_target,
            artifacts=artifacts,
            metadata={
                "submission_family": "ti_kim",
                "service_identifier": service_identifier,
            },
        )
        return envelope, tracking_reference
