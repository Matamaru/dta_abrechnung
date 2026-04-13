# Procedures And Transports

## First-Class Procedure Coverage

The scaffold currently models these billing lanes:

- `§ 105 SGB XI` ambulante Pflege
- `§ 302 SGB V` Häusliche Krankenpflege
- `§ 302 SGB V` Haushaltshilfe
- `§ 302 SGB V` Heilmittel
- `§ 302 SGB V` Hilfsmittel
- `§ 302 SGB V` Krankentransport

## Transport Families

### `classic_dta`

Used for:

- classic Pflege submissions
- current classic-first `§ 302` lanes in this scaffold

Implemented concepts:

- KKS-style routing metadata
- `Auftragsdatei` generation
- payer route selection
- Dakota compatibility flagging
- evidence packaging as additional artifacts

### `ti_kim`

Used for:

- `HKP` in the current scaffold
- TI-based Pflege submissions

Implemented concepts:

- KIM recipient resolution
- optional `VZD` lookup through the TI bridge
- attachment signing and signature verification
- procedure-specific service identifier resolution
- pluggable external or native TI operation mode

## Current Procedure Mapping

- `PflegeProcedureAdapter`
  - supports `classic_dta`
  - supports `ti_kim`
  - emits simplified classic EDIFACT-like payloads and simplified XML for TI
- `HkpProcedureAdapter`
  - supports `ti_kim` only
  - emits simplified XML payloads with `EHKP0` and `ABR_0000`
- `Classic302ProcedureAdapter`
  - supports `classic_dta` only
  - is reused for Haushaltshilfe, Heilmittel, Hilfsmittel, and Krankentransport

## Important Boundaries

- The serializers are structural scaffolds, not full legal conformance implementations.
- `dakota.le` is modeled only as a classic transport compatibility concern.
- TI/Gematik logic is abstracted behind the TI bridge and transport adapter, not scattered through business logic.
- Payer routing decisions should come from master data, not hardcoded procedure logic.

## Next Hardening Steps

- replace simplified payloads with exact spec-conform formats
- version official constraints per procedure and effective date
- snapshot payer routing data and `Kostenträgerdatei` imports
- integrate real KIM/TI infrastructure and operational credential handling
- define exact inbound parser behavior per official response type
