# Switchable strategies for all RAOS Story boundaries

Status: `IMPLEMENTATION_CANDIDATE`

This change implements a typed strategy switchboard for every canonical
`ST-xxxx` Story and each unresolved `OD-001` through `OD-015` boundary. It does
not resolve an Open Decision, invent a production value, create a credential,
claim human approval, apply infrastructure, publish content, or claim formal
TST/Staging/Production evidence.

## Alternatives

Every boundary has exactly three independently selectable implementations:

- **safe** — deterministic recorded or plan-only execution; no external or
  production side effect;
- **standard** — reviewed local/manual input or a bounded injected verifier;
- **advanced** — an injected external adapter requiring explicit approval,
  evidence, capability, and environment eligibility.

The Open Decision alternatives are domain-specific. Examples include synthetic,
manual anonymized, and verified provider finance reports; no-merge, versioned
rules, and verified product identity resolution; local fake, generic OIDC, and
Cognito authentication; and recorded-only, secret-provider, and workload-
identity credentials.

## Switching model

`StrategyProfile` performs a coordinated switch across boundaries. A profile
may also contain exact per-boundary overrides, and a call may supply one
one-shot override without mutating the profile.

Built-in profiles:

| Profile | Preferred tier | Failure behavior |
| --- | --- | --- |
| `safe-local` | safe | always select the local safe default |
| `balanced-staging` | standard | try lower tiers, but only when the candidate is valid in the current environment |
| `advanced-external` | advanced | fail closed; never downgrade silently |

Selection never reads environment variables, files, Secrets, browser state, or
provider configuration. The application must inject a `GateContext` containing
only approved identifiers for the current environment.

```python
from raos.strategy_switchboard import (
    ADVANCED_EXTERNAL_PROFILE,
    Environment,
    GateContext,
    StrategyRuntime,
    StrategySwitchboard,
    build_complete_catalog,
)

catalog = build_complete_catalog(("ST-0001", "ST-0002"))
switchboard = StrategySwitchboard(catalog)
runtime = StrategyRuntime(
    switchboard=switchboard,
    adapters={"category.portfolio": approved_category_adapter},
)
result = runtime.execute(
    boundary_id="OD-001",
    profile=ADVANCED_EXTERNAL_PROFILE,
    context=GateContext(
        environment=Environment.PRODUCTION,
        approvals=frozenset({"OD-001", "production-use"}),
        evidence=frozenset({"category-portfolio-evidence"}),
        capabilities=frozenset({"external-io"}),
    ),
    payload={"portfolio_version": "reviewed-v1"},
)
```

The same call without any required gate material fails with the stable code
`STRATEGY_REQUIREMENTS_UNSATISFIED`. If the adapter is not wired, it fails with
`STRATEGY_ADAPTER_MISSING`. Adapter exceptions are replaced by
`STRATEGY_ADAPTER_FAILED` and are not exposed as public messages.

## Generation and validation

The complete catalog is generated from the canonical Story backlog and Open
Decision inventory:

```bash
python scripts/build_all_story_strategy_catalog.py --write
python scripts/build_all_story_strategy_catalog.py --check
pytest -p no:cacheprovider -q tests/strategy_switchboard
```

The generator requires every canonical Story and all fifteen Open Decisions,
requires exactly one safe, one standard, and one advanced candidate per
boundary, records source hashes, and produces deterministic canonical JSON.

## Production boundary

Safe candidates are local-only. Standard candidates are local/Staging-only.
Advanced candidates may be eligible for Production only when all candidate
requirements are present. A Production selection can never fall back to a
local or Staging candidate.

Credentials, provider clients, database connections, queues, object stores,
notification services, human-review systems, legal systems, consent systems,
and infrastructure apply engines remain injected ports. Their candidate
implementations are complete at the selection and execution boundary, but no
real external operation occurs until separately approved wiring supplies the
adapter and gate evidence.
