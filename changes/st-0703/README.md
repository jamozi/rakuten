# ST-0703 OpenAI Responses recorded adapter

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

Authority: `DESIGN_HANDOFF_V1_ST0703_v2.yaml`

This Story implements only the recorded, provider-neutral OpenAI Responses boundary approved for ST-0703. It does not resolve credentials, create a client, activate a route, retry a provider call, perform a live request, approve AI output, publish content, or claim formal TST/staging/production evidence.

## Implemented boundary

- exact `openai==2.52.0` dependency and lock closure;
- injected synchronous client and one `responses.create` invocation;
- `store=false`, `tools=[]`, strict JSON Schema output, `max_retries=0`, and bounded timeout;
- structured success, refusal, two incomplete reasons, and stable sanitized provider failures;
- exact usage including cached input tokens;
- canonical allowlisted exchange recording through `ProviderExchangeRecorder`;
- deterministic synthetic fixture cost through `RecordedCostCalculator`;
- no provider SDK type across the inward port;
- no environment, Secret, network, database, queue, or object-store access in recorded tests.

The local in-memory recorder is test/local infrastructure only. Production raw artifact storage remains ST-0601. Production model selection, budget, fallback, circuit breaking, and retry remain ST-0704/ST-0706. Credential resolution and client construction remain ST-0407/application wiring.

## Commands

Hydrate the exact locked environment separately, then run the isolated commands
directly:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --locked --offline --no-cache --no-sync \
  --no-env-file --no-python-downloads \
  python scripts/build_st0703_recorded_adapter.py --check
PYTHONDONTWRITEBYTECODE=1 uv run --locked --offline --no-cache --no-sync \
  --no-env-file --no-python-downloads \
  pytest -p no:cacheprovider -q tests/st0703
```

## Evidence boundary

A local pass is implementation-candidate evidence only. The following remain separate and unexecuted:

- formal TST-017 application and human review;
- live OpenAI account and credential validation;
- live model evaluation and release decision;
- production pricing and FX;
- production artifact storage;
- staging, publication, release, and production readiness.
