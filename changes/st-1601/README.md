# ST-1601 maximum-safe telemetry seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story-owned slice implements the reversible, provider-neutral portion of
the approved observability foundation. It provides explicit correlation
values, exactly three fixed signal records, one inward sink port, a
best-effort application recorder, and disabled or bounded process-local sinks.
It does not install or configure OpenTelemetry, an exporter, a backend, a
dashboard, an alert, or any external runtime.

## Implemented boundary

- `TelemetryContext` requires a caller-supplied exact UUID
  `correlation_id`. Optional `causation_id`, `job_id`, `article_id`, and
  `snapshot_id` values are also exact UUIDs; `provider_request_id` is an
  explicitly supplied bounded safe identifier. No identifier is generated,
  inferred, copied from another field, or obtained from ambient execution
  state.
- TRACE, METRIC, and LOG are the only signal families. Each has a separate
  immutable record with strict canonical UTC timestamps, exact enums, bounded
  low-cardinality names, and signal-specific closed fields. There is no
  arbitrary metadata or text-bearing diagnostic field.
- Contexts and records use redacted printable forms and reject generic pickle
  serialization. Rejected values are not retained or echoed by the sanitized
  domain failure.
- `TelemetryRecorder.record(...)` attempts exactly one synchronous sink call
  and returns `RECORDED`, `DISABLED`, `DROPPED`, or `SINK_FAILED` separately
  from business work. It converts an ordinary sink exception or malformed sink
  result to `SINK_FAILED` without inspecting the exception, retrying, or
  recursively emitting. `KeyboardInterrupt`, `SystemExit`, and other
  `BaseException` subclasses propagate.
- `DisabledTelemetrySink` retains nothing. `RecordedTelemetrySink` requires an
  explicit positive built-in integer capacity and an exact `ENV-DEV` or
  `ENV-CI` runtime enum. It uses a process-local `RLock`, exposes only an
  ordered immutable tuple snapshot, and drops the newest incoming record when
  full without evicting existing records.

The sinks provide no clear, deletion, eviction, export, flush, retry,
lifecycle, background-work, file, database, network, cloud, HTTP, environment
discovery, process, provider, credential, or retention-policy interface.

## Predecessor bindings

The isolated suite binds the committed ST-1404 public Job states, dispatcher
outcomes, worker outcomes, and exact `JobRecord` field set. ST-1404 currently
has no `correlation_id` or `causation_id` field on its Job or recorded message;
ST-1601 does not patch that predecessor, infer either value, generate one, or
derive correlation from Job/event identity. Tests hold Job result, status,
acknowledgement, retry, and health observations constant across all four
telemetry outcomes.

ST-1505 is read only as a metadata/evidence predecessor. Its committed
reference stays non-executable, default-disabled, unconfigured, zero-action,
external-action-forbidden, and `NOT_EXECUTED` for formal TST-009 and TST-022.
This slice adds no staging or deployment activation.

## Provisional implementation assumption

`PROVISIONAL-W1-ST1601-001`: canonical sources fix the three signal families
and six context identifiers but do not prescribe the initial local record
field names, exact low-cardinality enum members, or an in-process capacity
ceiling. The closed trace outcome/duration, metric value/unit, log level, safe
name grammar, and 10,000-record ceiling follow the closest strict recorded
runtime patterns. They remain reversible local interface details for Wave-end
integration review; they do not select a backend, provider, retention policy,
SLO, or business value.

## Owned paths

| Path | Role |
| --- | --- |
| `python/raos/domain/ops/telemetry.py` | Immutable context, enums, records, outcomes, and sanitized failure |
| `python/raos/domain/ops/__init__.py` | Narrow domain exports |
| `python/raos/ports/telemetry.py` | Inward exact-record sink port |
| `python/raos/application/ops/telemetry.py` | One-attempt best-effort recorder |
| `python/raos/application/ops/__init__.py` | Narrow application export |
| `python/raos/adapters/recorded_telemetry.py` | Disabled and bounded DEV/CI sinks |
| `tests/st1601/conftest.py` | Synthetic fixed-shape fixtures |
| `tests/st1601/test_telemetry.py` | Domain, validation, capacity, redaction, and pickle coverage |
| `tests/st1601/test_failure_isolation.py` | Sink failure and predecessor isolation coverage |
| `tests/st1601/test_boundaries.py` | Architecture and prohibited-surface coverage |
| `changes/st-1601/README.md` | Scope, assumption, verification, and evidence boundary |

No generated output, manifest, status overlay, dependency file, migration,
workflow, infrastructure definition, predecessor, or shared adapter/port export
is owned by this slice.

## Local verification

Use the pinned repository uv without synchronization or network access:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st1601
```

The same pinned/offline prefix is used for focused Ruff, format, mypy, compile,
and import checks. Committed ST-1404 and ST-1505 owner suites and the ST-1505
no-write generator check are read-only predecessor regressions, not new formal
evidence.

## Explicitly unexecuted work

Formal TST-031 privacy/retention execution, Privacy/Security manual review,
hosted CI, OpenTelemetry SDK/exporter/backend and configuration, dashboards and
SLOs owned by ST-1602, provider/runtime configuration, live or staging
observation, release, deployment, credentials, and Production remain
`NOT_EXECUTED` or out of scope. Local checks do not change effective canonical
Story status and do not establish `VALIDATED` or production-ready evidence.
