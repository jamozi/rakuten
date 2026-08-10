# ST-0703 OpenAI Responses recorded adapter

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

Authority: `DESIGN_HANDOFF_V1_ST0703_v5.yaml`, exact approval
`DESIGN-HANDOFF-APPROVAL-v5.yaml`, canonical reconciliation
`CANONICAL-RECONCILIATION-v5.md`, and decision source
`DESIGN-DECISION-REQUEST-v5.md`. V5 preserves approved D1 through D4 and
replaces only D5 with `ST0703-V5-D5-CORRECTION`.

This Story implements only the recorded, provider-neutral OpenAI Responses boundary approved for ST-0703. It does not resolve credentials, create a client, activate a route, retry a provider call, perform a live request, approve AI output, publish content, or claim formal TST/staging/production evidence.

## Implemented boundary

- exact `openai==2.52.0` dependency and lock closure;
- injected synchronous client and one `responses.create` invocation;
- `store=false`, `tools=[]`, strict JSON Schema output, `max_retries=0`, and bounded timeout;
- structured success, refusal, two incomplete reasons, and stable sanitized provider failures;
- exact usage including cached input tokens;
- closed class/status provider-error mapping with immutable sanitized errors;
- canonical, bounded, content-free exchange recording through
  `ProviderExchangeRecorder`, after outcome, schema, and pricing validation;
- deterministic expiring synthetic fixture pricing through
  `RecordedCostCalculator`, with usage/quote/calculation digests and independent
  reference recomputation of every result field;
- no provider SDK type across the inward port;
- no environment, Secret, network, database, queue, or object-store access in recorded tests.

The local in-memory recorder is test/local infrastructure only. Production raw artifact storage remains ST-0601. Production model selection, budget, fallback, circuit breaking, and retry remain ST-0704/ST-0706. Credential resolution and client construction remain ST-0407/application wiring.

The recorded exchange never contains prompts, source material, successful or
partial output, refusal text, reasoning, provider request IDs, headers, URLs,
error bodies, credentials, pricing values, or unlisted provider fields. Its
only outcomes are content-free `success`, classified `refusal`, and the two
approved classified `incomplete` reasons.

## Commands

Hydrate the exact locked environment separately. The generate target is the
only mutating ST-0703 target; all other targets below are offline, no-cache,
no-sync, and read-only:

```bash
make python-sync UV=/absolute/path/to/reviewed/uv-0.12.1
make openai-recorded-generate UV=/absolute/path/to/reviewed/uv-0.12.1
make openai-recorded-check UV=/absolute/path/to/reviewed/uv-0.12.1
make openai-recorded-static UV=/absolute/path/to/reviewed/uv-0.12.1
make openai-recorded-test UV=/absolute/path/to/reviewed/uv-0.12.1
make openai-recorded-gate UV=/absolute/path/to/reviewed/uv-0.12.1
```

The equivalent direct read-only checks are:

```bash
UV=/absolute/path/to/reviewed/uv-0.12.1
PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file "$PWD/uv.toml" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads \
  python scripts/build_st0703_recorded_adapter.py --check
PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file "$PWD/uv.toml" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads \
  python scripts/build_st0703_recorded_adapter.py --check-installed
PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file "$PWD/uv.toml" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads \
  python scripts/build_st0204_config_loader.py --check
PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file "$PWD/uv.toml" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads ruff check --no-cache \
  python/raos/adapters/__init__.py \
  python/raos/adapters/openai_responses.py \
  python/raos/adapters/recorded_ai.py python/raos/domain/ai/provider.py \
  python/raos/ports/ai_provider.py \
  scripts/build_st0703_recorded_adapter.py tests/st0703
PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file "$PWD/uv.toml" run \
  --no-env-file --no-python-downloads \
  --locked --offline --no-cache --no-sync \
  pytest -p no:cacheprovider -q tests/st0703
```

The bounded static Make target additionally runs Ruff format checking and
strict mypy. `config-check` retains its owner-defined `python-sync` prerequisite
and is not an `openai-recorded-gate` prerequisite. The gate composes
`ai-registry-check`, `openai-recorded-check`, `openai-recorded-static`, and
`openai-recorded-test`, then invokes the ST-0204 owner generator's existing
`--check` operation exactly once through `UV_READONLY_RUN`. It does not recurse
into Make, hydrate, synchronize, install, access a credential, use the network,
or write a cache.

## Evidence boundary

A local pass is implementation-candidate evidence only. It is not formal
TST-017 or live-provider evidence. The following remain separate and
unexecuted:

- formal TST-017 application and human review;
- live OpenAI account and credential validation;
- live model evaluation and release decision;
- production pricing and FX;
- production artifact storage;
- staging, publication, release, and production readiness.
