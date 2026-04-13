# Coding Standards

This project should stay modular, explicit, and easy to change. The codebase handles billing, persistence, audit, and API boundaries, so structure matters more than cleverness.

## Core Rules

- Keep modules single-purpose.
- Do not build monolithic service layers that mix domain logic, persistence, transport, and API concerns.
- Prefer explicit domain names over generic helpers.
- Keep orchestration thin and business logic close to the responsible service or adapter.
- Favor simple control flow over deep abstraction.
- Make dependencies visible through constructor parameters and typed interfaces.

## File And Module Boundaries

- A module should have one clear reason to change.
- If a file starts to own multiple workflows, split it.
- Shared domain concepts belong in stable boundary modules such as `domain.py`, `runtime.py`, `security.py`, or a dedicated shared module.
- API handlers should validate input, enforce auth, call services, and shape responses. They must not hold business rules or raw SQL.
- Repositories should handle persistence concerns only. They must not become business-rule engines.
- Procedure-specific rules belong in `procedures.py` or a dedicated procedure module, not in generic platform orchestration.

## Classes And Functions

- Each class should have one primary responsibility.
- Each function or method should do one well-bounded thing.
- Prefer small methods over long internal branches.
- Avoid hidden side effects. If a method writes data, emits events, or audits access, that should be clear from the name or docstring.
- Prefer returning well-typed domain objects or response models over loose dictionaries unless a dictionary is the deliberate interface.

## Docstrings

Every class, function, and method must have a short, precise docstring.

Docstrings must include:

- a one-line description of behavior or responsibility
- `Args:` with parameter names and short descriptions
- `Returns:` with the return type or result description

If a function raises important errors, add `Raises:` when it helps the caller.

### Recommended Style

```python
def create_provider(tenant_id: str, name: str, ik: str) -> Leistungserbringer:
    """Create a provider inside an existing tenant.

    Args:
        tenant_id: Target tenant identifier.
        name: Display name of the provider.
        ik: Institution code used for billing and routing.

    Returns:
        The created provider entity.
    """
```

Docstrings should explain intent and contract, not restate the code mechanically.

## Naming

- Use domain terminology consistently: `tenant`, `provider`, `payer`, `routing`, `snapshot`, `audit`, `submission`.
- Avoid vague names like `data`, `payload2`, `tmp`, `helper`, or `manager` when a more precise name exists.
- Name booleans as booleans, for example `is_active`, `requires_dakota`, `supports_ti_kim`.
- Prefer full words unless the domain strongly standardizes an abbreviation such as `IK`, `KIM`, `HKP`, or `DTA`.

## Error Handling

- Fail early with explicit errors when required inputs or state are missing.
- Do not rely on incidental `KeyError`, `AttributeError`, or `assert` for production control flow.
- Raise domain-appropriate exceptions and convert them into API errors at the API boundary.

## Persistence And Security

- Use `SQLAlchemy` ORM/Core with bound parameters only.
- Do not build SQL strings from user input.
- Raw SQL is allowed only in migrations, DDL, triggers, and reviewed Postgres-specific setup.
- Pass `AuditContext` through all audited write flows and sensitive read flows.
- Keep tenant scoping explicit in repository and service interfaces.

## Tests

- Add or update tests with each behavior change.
- Prefer focused tests around a single rule or workflow.
- Keep unit tests fast and deterministic.
- Run Postgres-backed tests for features that depend on audit triggers, `RLS`, or other Postgres-only behavior.

## Refactoring Triggers

Refactor before extending when:

- a file mixes unrelated responsibilities
- a method needs long comments to stay understandable
- the same branching rules appear in multiple places
- transport logic leaks into domain services
- persistence-specific code leaks into pure domain flows

## Documentation Rule

Code and docs must evolve together.

- Update the end-user manual when user-facing behavior changes.
- Update contributor docs when boundaries, workflows, or coding rules change.
- Update architecture/security docs when persistence, runtime, or deployment assumptions change.
