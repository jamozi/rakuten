# ST-0704 synthetic development routing and budget controls

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the maximum reversible local portion of the approved
ST-0704 boundary. It authorizes only an explicitly certified synthetic
`ENV_DEV` route, reserves an injected direct-JPY test quote against a
process-local cap, and exposes default-open one-way circuit controls. It never
executes a model or calls a provider.

`OD-009` remains unresolved. Every amount, route, model identifier,
certification, and circuit state in this candidate is explicit synthetic test
data; none is a Production budget, price, FX rate, provider capability, or
release decision.

## Implemented safe boundary

- Route, certification, quote, request, reservation, authorization, and receipt
  values are immutable, strictly validated, hash-bound, and redacted. They
  contain no prompt, source content, provider response, credential, account, or
  free-form error text.
- The service loads an exact ST-0701 task/route candidate but never treats
  `CANDIDATE` metadata as executable authority. A separately injected,
  time-bounded synthetic certification must bind the exact task, route version,
  model, task-binding hash, and route hash.
- Route selection is deterministic and closed. Unknown task, route, version, or
  model; duplicate identity; ineligible certification; stale quote; mismatched
  binding; malformed value; and unavailable registry fail closed with stable
  sanitized codes.
- `InMemoryDevelopmentAiControls` is construction- and operation-guarded to the
  exact `RuntimeEnvironment.ENV_DEV` enum member. Its injected cap is only test
  control data. A process-local lock makes reserve, commit, release, replay,
  mismatch, and cap checks atomic within one process.
- The circuit starts open/deny unless the test fixture explicitly supplies a
  closed route. It may be irreversibly tripped open for the adapter lifetime;
  there is no reset, half-open state, automatic recovery, retry, or fallback.
- Reservation intent includes the task/route/certification/quote hashes and is
  rebound when an authorization is accepted. Commit and release verify exact
  semantic receipts returned by the outward control port.
- The only fallback policy is `DENY_ALL` with zero fallbacks.

The owned runtime contains no OpenAI/provider SDK or call, network, file,
process environment, database, HTTP, credential, background worker, sleep,
actual pricing/FX lookup, route activation, release action, or Production
configuration.

## Local commands

After the locked Python environment has been hydrated, run the isolated Story
suite through the pinned repository uv in offline/no-sync mode:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st0704
```

Focused Ruff lint/format and strict mypy use the same uv prefix over the five
owned source modules and `tests/st0704`. Shared exports, Make routing, owner
manifests, generated evidence, and status application are intentionally
deferred to Wave integration.

## Evidence and deferred boundaries

This local candidate does not select a real monthly or per-request budget,
automatic-stop threshold, model/provider route, price/FX source, approved
fallback, durable ledger, multi-process fence, persistent circuit, provider
account, live credential, or deployment configuration. It does not execute a
model and cannot authorize any non-development environment.

Local pytest/static results are not formal `TST-005`, `TST-017`, or `TST-019`
evidence and do not represent hosted CI, live provider/account/credential
validation, staging, deployment, release, or Production readiness. Current
ST-0701 and ST-0703 manifest drift is recorded for topological owner
regeneration at W1 freeze. These boundaries are tracked as `DEBT-W1-012`
through `DEBT-W1-015` in the implementation-first ledger.
