from __future__ import annotations

from uuid import uuid4

from .domain import (
    InstitutionCode,
    Kostentraeger,
    ProcedureCapability,
    ProcedureCode,
    RoutingTarget,
    TransportFamily,
)
from .store import PlatformStore
from .transport import TiBridge


class PayerMasterDataService:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def register_payer(
        self,
        name: str,
        ik: str,
        kassenart: str,
        capabilities: dict[ProcedureCode, ProcedureCapability],
        data_acceptance_changes: list[str] | None = None,
    ) -> Kostentraeger:
        payer = Kostentraeger(
            id=f"payer-{uuid4().hex[:12]}",
            name=name,
            ik=InstitutionCode(ik),
            kassenart=kassenart,
            capabilities=capabilities,
            data_acceptance_changes=data_acceptance_changes or [],
        )
        self.store.payers[payer.id] = payer
        return payer

    def resolve_route(
        self,
        payer_id: str,
        procedure: ProcedureCode,
        transport: TransportFamily,
        ti_bridge: TiBridge | None = None,
    ) -> RoutingTarget:
        try:
            payer = self.store.payers[payer_id]
        except KeyError as exc:
            raise ValueError(f"Unknown payer: {payer_id}") from exc
        try:
            capability = payer.capabilities[procedure]
        except KeyError as exc:
            raise ValueError(f"Payer {payer_id} does not expose capability for {procedure.value}") from exc
        if transport not in capability.allowed_transports:
            raise ValueError(f"{procedure} does not support transport {transport}")
        if transport == TransportFamily.CLASSIC_DTA:
            if not capability.classic_address:
                raise ValueError("Classic DTA route missing")
            return RoutingTarget(
                transport=transport,
                procedure=procedure,
                receiver_ik=payer.ik.value,
                receiver_name=payer.name,
                address=capability.classic_address,
                channel="dakota" if capability.requires_dakota else "email",
                requires_dakota=capability.requires_dakota,
                metadata={"payer_kassenart": payer.kassenart},
            )
        if not capability.kim_address:
            raise ValueError("KIM route missing")
        kim_address = capability.kim_address
        metadata = {"payer_kassenart": payer.kassenart}
        if kim_address == "VZD":
            if ti_bridge is None:
                raise ValueError("VZD resolution requires a TI bridge")
            kim_address = ti_bridge.lookup_vzd(domain_id=payer.ik.value, entry_type="5")
            metadata["kim_resolution"] = "vzd"
        else:
            metadata["kim_resolution"] = "file"
        return RoutingTarget(
            transport=transport,
            procedure=procedure,
            receiver_ik=payer.ik.value,
            receiver_name=payer.name,
            address=kim_address,
            channel="kim",
            metadata=metadata,
        )

    def add_data_acceptance_change(self, payer_id: str, note: str) -> None:
        try:
            self.store.payers[payer_id].data_acceptance_changes.append(note)
        except KeyError as exc:
            raise ValueError(f"Unknown payer: {payer_id}") from exc
