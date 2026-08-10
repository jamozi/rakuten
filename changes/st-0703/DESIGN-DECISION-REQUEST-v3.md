# ST-0703 DESIGN_HANDOFF_V1 V3 correction request

Status: `PROPOSAL_REQUEST_ONLY`
Authority: `NOT_IMPLEMENTATION_AUTHORITY`
Human approval: `APPROVED_ST0703_V3_D1_THROUGH_D5`
Canonical reconciliation: `READY_FOR_EXACT_HANDOFF_RECONCILIATION`
Implementation: `AWAITING_EXACT_HANDOFF_BYTE_APPROVAL`
Formal TST-017: `NOT_EXECUTED`
Live provider, staging, and production: `NOT_EXECUTED`

## Why this request exists

The approved recorded-scope handoff
`DESIGN_HANDOFF_V1_ST0703_v2.yaml` has SHA-256
`f768571d5f56a313437cc108485f21a7c3a8a9226016bee7830ab3709a90f08f`.
Its implementation audit found that it does not completely specify the exact
matrices required by its own source authority,
`DESIGN-DECISION-REQUEST-v2.md`. Therefore its `open_decisions: []` cannot be
used to authorize the omitted policy choices.

The current partial adapter SHA-256 is
`d9175398c6c73ec2e8b32cd3424cb7a38a42b9ca9e78388428ebb854fc48f85a`.
It is implementation evidence only, not design authority.

The gated Pro escalation stopped before submission:

- run ID: `20260809T084221Z-d51eeaa7e1a9`
- status: `BLOCKED_PRO_REQUIRED`
- reason: `SELECTOR_AMBIGUITY`
- submission attempted: `false`
- advice captured: none

This request supports repository-owner decisions in conversation. Each
decision remains pending until the owner explicitly says `承認`. Approval of
one item does not approve any later item.

## Ordered correction decisions

1. `ST0703-V3-D1`: closed provider-error and retryability matrix.
2. `ST0703-V3-D2`: exact recorded-exchange byte schema and artifact disposition.
3. `ST0703-V3-D3`: exact synthetic pricing formula, time validity, and binding.
4. `ST0703-V3-D4`: mechanical predecessor-manifest propagation rule.
5. `ST0703-V3-D5`: exact static, denied-network, generator, and CI gate wiring.

`ST0703-V3-D1` and `ST0703-V3-D2` are approved. `ST0703-V3-D3` through
`ST0703-V3-D5` are presented together as the final exact correction package.

## ST0703-V3-D1 proposed decision

### Closed provider mapping

The adapter shall classify provider exceptions using this exact table:

| Provider signal | Stable code | Retryable |
| --- | --- | --- |
| HTTP 429 or `RateLimitError` | `RATE_LIMIT` | `true` |
| HTTP 408 or `APITimeoutError` or built-in `TimeoutError` | `TIMEOUT` | `true` |
| HTTP 401 or `AuthenticationError` | `AUTHENTICATION` | `false` |
| HTTP 403 or `PermissionDeniedError` | `PERMISSION` | `false` |
| HTTP 400, 404, 409, or 422, or `BadRequestError`, `ConflictError`, `NotFoundError`, or `UnprocessableEntityError` | `INVALID_REQUEST` | `false` |
| HTTP 502, 503, or 504, or `APIConnectionError` | `UNAVAILABLE` | `true` |
| Any other integer HTTP status at least 500 or `InternalServerError` | `SERVER_ERROR` | `true` |
| Every unlisted signal | `UNKNOWN` | `false` |

Classification shall additionally obey these closed rules:

1. If both a recognized exception class and a recognized HTTP status exist and
   they select different rows, classify as `UNKNOWN`, retryable `false`.
2. If status extraction raises, returns a boolean, or returns any non-integer
   value, classify as `UNKNOWN`, retryable `false`, even when the class would
   otherwise be recognized.
3. If no status is present, a recognized exception class may select its row.
4. A provider-neutral `ProviderError` raised by an injected client is not
   passed through verbatim. The adapter creates a new sanitized error using
   only its recognized stable code; retryability is derived from the closed
   RAOS table, and any unrecognized or malformed value becomes `UNKNOWN` and
   `false`.
5. No error message, exception argument, status object, response, request,
   header, URL, body, credential, prompt, source, output, or provider identifier
   from the exception is copied to the public error.
6. Every mapped error is raised `from None`; public `__cause__` and
   `__context__` are absent.

### Closed non-provider mapping

| Failure stage | Stable code | Retryable |
| --- | --- | --- |
| Response conversion, shape, identifier, timestamp, usage, status, refusal, incomplete reason, or output extraction/validation | `MALFORMED_RESPONSE` | `false` |
| Requested, resolved, route, or response model mismatch | `ROUTE_MISMATCH` | `false` |
| Request schema or result schema invalid | `INVALID_SCHEMA` | `false` |
| Recorder raises, canonical bytes cannot be built or bounded, or `ArtifactRef` is invalid/mismatched | `RECORDER_FAILURE` | `false` |
| Pricing quote/calculator unavailable or raises before producing a result | `PRICING_MISSING` | `false` |
| Pricing result type, amount binding, quote ID/hash/currency/provider/model/time binding, or recomputation mismatches | `PRICING_MISMATCH` | `false` |
| Clock or latency source fails or produces an invalid value | `UNKNOWN` | `false` |

Validation and classification order shall be deterministic. A later stage must
not reclassify or expose content from an earlier failure. Refusal and
incomplete classification occur before parsing their text as structured
output.

### Security impact

- Retry is permitted only for a closed transient set.
- Conflicting or hostile provider metadata cannot turn a non-retryable failure
  into a retryable one.
- Authentication, permission, request, schema, recording, and pricing failures
  cannot trigger adapter retry.
- Provider exception material cannot cross the inward boundary or enter logs,
  reprs, records, or exception chains.

### Approval question

Approve `ST0703-V3-D1` exactly as written, or identify the exact row or rule to
replace. No implementation resumes from this document until explicit owner
approval and closure of `ST0703-V3-D2` through `ST0703-V3-D5` in a complete
replacement `DESIGN_HANDOFF_V1`.

## ST0703-V3-D1 approval record

- decision: `ST0703-V3-D1`
- status: `APPROVED_BY_REPOSITORY_OWNER`
- approved_at: `2026-08-09T08:52:38Z`
- approval_source: explicit `承認する` in the connected Codex conversation
- approved_scope: the complete `ST0703-V3-D1 proposed decision` section above
- does_not_approve: `ST0703-V3-D2`, `ST0703-V3-D3`, `ST0703-V3-D4`, or
  `ST0703-V3-D5`

## ST0703-V3-D2 proposed decision

### Exact canonical exchange document

The recorder shall receive one strict JSON object with exactly these fields and
no extensions:

```json
{
  "provider": "openai",
  "request": {
    "request_sha256": "<64 lowercase hexadecimal characters>",
    "task_code": "<validated request task code>",
    "model_route_version": "<validated request route version>",
    "prompt_version": "<validated request prompt version>",
    "input_artifact_sha256": "<64 lowercase hexadecimal characters>",
    "output_schema_sha256": "<64 lowercase hexadecimal characters>"
  },
  "response": {
    "response_id": "<validated safe identifier>",
    "requested_model_id": "<validated safe identifier>",
    "resolved_model_id": "<validated safe identifier>",
    "status": "<completed or incomplete>",
    "created_at": "<UTC datetime.isoformat() value>",
    "received_at": "<UTC datetime.isoformat() value>",
    "latency_ms": 0,
    "usage": {
      "input_tokens": 0,
      "cached_input_tokens": 0,
      "output_tokens": 0
    },
    "outcome": {"kind": "success"}
  }
}
```

The outcome object shall be exactly one of:

```json
{"kind":"success"}
{"kind":"refusal","refusal":true}
{"kind":"incomplete","reason":"max_output_tokens"}
{"kind":"incomplete","reason":"content_filter"}
```

No successful output object, refusal text, partial output, reasoning content,
prompt, message, source material, provider request ID, header, URL, credential,
exception, error body, pricing value, or unlisted provider field is recordable.

### Field validation

1. Request fields are copied only from an already valid immutable
   `StructuredTaskRequest`; no raw SDK or caller mapping is accepted by the
   recorder builder.
2. Every SHA-256 value is the exact lowercase 64-character digest held by an
   existing `Sha256Digest` value object.
3. `response_id`, `requested_model_id`, and `resolved_model_id` must match
   `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$` before record construction.
4. `status` is exactly `completed` for success/refusal and exactly `incomplete`
   for either incomplete outcome.
5. Both timestamps are timezone-aware UTC values serialized with Python
   `datetime.isoformat()`; `received_at` must not precede `created_at` where
   that comparison is meaningful for the recorded provider response.
6. `latency_ms` and every token count are exact integers, not booleans, in the
   inclusive range 0 through 2^63-1. Cached input tokens must not exceed input
   tokens.
7. Every value is validated before the document is constructed. Any value
   object or canonicalization failure is sanitized according to
   `ST0703-V3-D1` and is never copied into an error.

### Canonical bytes and hash

1. The document is encoded once as UTF-8 strict JSON with sorted object keys,
   separators `,` and `:`, `ensure_ascii=false`, `allow_nan=false`, no BOM, no
   trailing newline, no duplicate keys, and no non-JSON scalar.
2. The root must be a JSON object. The frozen object graph is bounded to
   100,000 visits and depth 100.
3. Canonical bytes must be non-empty and at most 4,194,304 bytes.
4. `ProviderExchange.sha256` is SHA-256 of those exact bytes. Parsing and
   canonical reserialization must reproduce the exact same bytes.
5. Construction, size, parse, canonicalization, or digest failure maps to
   `RECORDER_FAILURE`, retryable `false`, raised from `None`.

### Recording order and artifact disposition

1. Response normalization, route matching, usage validation, outcome
   classification, structured-output validation when applicable, and the
   complete `ST0703-V3-D3` pricing validation all finish before record
   construction or the recorder call.
2. Success, refusal, and either incomplete outcome call the injected
   `ProviderExchangeRecorder` exactly once, after all preceding validation and
   immediately before constructing the provider-neutral result.
3. Provider-call errors, malformed responses, route mismatches, invalid
   schemas, and pricing failures make zero recorder calls and produce no
   `ArtifactRef`.
4. Recorder failure or an invalid returned reference produces no result and no
   exposed artifact reference. ST-0703 performs no compensating storage delete;
   atomicity and orphan handling belong to the recorder's owning persistence
   Story.
5. A successful recorder result must be an exact `ArtifactRef`. Its SHA-256 and
   byte size equal the exchange bytes and its content type is exactly
   `application/json`. The provider result's `response_sha256`, artifact
   SHA-256, and exchange SHA-256 are identical.
6. The adapter does not constrain a production recorder URI or persistence
   scheme beyond the provider-neutral `ArtifactRef` contract; ST-0601 retains
   that authority.

### Recorded-fixture recorder

The local in-memory recorder is permitted only for tests and local recorded
execution. For one digest it shall retain one immutable byte string and return
one stable reference:

- `artifact_id`: UUIDv5 of the lowercase digest in namespace
  `a6ac02c7-2f99-41dd-a918-8c54633e2f1d`
- `sha256`: the exact exchange digest
- `uri`: `file://recorded/<lowercase-sha256>.json`
- `content_type`: `application/json`
- `byte_size`: exact canonical byte length

Recording the same digest and same bytes is idempotent and returns the same
reference. The same digest with different bytes fails closed as
`RECORDER_FAILURE`. The in-memory URI is not production storage authority.

### Security impact

- Raw model output and refusal/partial text never enter the recorded artifact.
- A pricing or validation failure cannot leave a returned artifact/result.
- The exchange is content-addressed and byte-for-byte reproducible.
- The adapter cannot select a production storage location or deletion policy.

### Approval question

Approve `ST0703-V3-D2` exactly as written, or identify the exact field,
validation rule, recording order, or disposition to replace. Approval does not
authorize implementation until `ST0703-V3-D3` through `ST0703-V3-D5` are
closed in a complete replacement `DESIGN_HANDOFF_V1`.

## ST0703-V3-D2 approval record

- decision: `ST0703-V3-D2`
- status: `APPROVED_BY_REPOSITORY_OWNER`
- approved_at: `2026-08-09T10:04:49Z`
- approval_source: explicit `すべて承認する` in the connected Codex conversation
- approval_interpretation: applies to every fully specified decision available
  at that time, `ST0703-V3-D1` and `ST0703-V3-D2`; it is not prospective
  approval of then-unspecified D3 through D5
- approved_scope: the complete `ST0703-V3-D2 proposed decision` section above
- does_not_approve: `ST0703-V3-D3`, `ST0703-V3-D4`, or `ST0703-V3-D5`

## ST0703-V3-D3 proposed decision

### Synthetic quote and validity interval

`SyntheticPricingQuote` remains recorded-fixture-only and shall contain exact:

- `quote_id`: bounded safe identifier
- `provider`: exactly `openai`
- `model_id`: exact approved route model identifier
- `native_currency`: exactly three uppercase ASCII letters
- `input_per_million`: finite non-negative Decimal
- `cached_input_per_million`: finite non-negative Decimal
- `output_per_million`: finite non-negative Decimal
- `jpy_per_native_unit`: finite positive Decimal
- `observed_at`: timezone-aware UTC datetime
- `expires_at`: timezone-aware UTC datetime strictly after `observed_at`
- derived `quote_sha256`: exact hash defined below

Every Decimal has at most 38 significant digits and exponent in the inclusive
range -18 through 18. Floats, booleans, NaN, infinities, negative zero, and
implicit string coercion are rejected.

The quote hash is SHA-256 of canonical UTF-8 JSON with exactly:

```json
{
  "kind": "SYNTHETIC_TEST_ONLY",
  "quote_id": "<quote id>",
  "provider": "openai",
  "model_id": "<model id>",
  "native_currency": "<currency>",
  "input_per_million": "<canonical Decimal text>",
  "cached_input_per_million": "<canonical Decimal text>",
  "output_per_million": "<canonical Decimal text>",
  "jpy_per_native_unit": "<canonical Decimal text>",
  "observed_at": "<UTC datetime.isoformat()>",
  "expires_at": "<UTC datetime.isoformat()>"
}
```

The adapter captures one `evaluated_at` from its injected UTC clock at entry,
before the provider call. A quote is usable only when
`observed_at <= evaluated_at < expires_at`. Recorded tests inject the exact
clock value; no wall clock, network price source, or FX lookup is permitted.

### Exact calculator input and binding

The outward `RecordedCostCalculator` receives keyword-only exact values:

- `usage: ProviderUsage`
- `provider: str`, exactly `openai`
- `model_id: str`, equal to the requested route and resolved response model
- `quote: SyntheticPricingQuote`
- `evaluated_at: datetime`, the exact captured UTC instant

Usage contains exact integers in 0 through 2^63-1 and requires
`cached_input_tokens <= input_tokens`. Its binding digest is SHA-256 of
canonical JSON with exactly `input_tokens`, `cached_input_tokens`, and
`output_tokens`.

The returned `PricingResult` contains exact:

- `estimated_cost_jpy`
- `provider_cost_native`
- `native_currency`
- `quote_id`
- `quote_sha256`
- `provider`
- `model_id`
- `usage_sha256`
- `evaluated_at`
- `calculation_sha256`

`calculation_sha256` binds the canonical quote digest, usage digest, provider,
model, evaluated instant, native amount, currency, and integer JPY result in a
closed canonical JSON object.

### Exact calculation

The calculation uses a local Decimal context with precision 50 and
`ROUND_HALF_EVEN` for intermediate arithmetic. No ambient Decimal context is
used.

```text
regular_input_tokens = input_tokens - cached_input_tokens

provider_cost_native =
    (regular_input_tokens * input_per_million
     + cached_input_tokens * cached_input_per_million
     + output_tokens * output_per_million)
    / Decimal(1_000_000)

estimated_cost_jpy =
    ceil(provider_cost_native * jpy_per_native_unit)
```

The final ceiling is Decimal `ROUND_CEILING`. `estimated_cost_jpy` must be an
exact integer in 0 through 2^63-1. `provider_cost_native` is the exact Decimal
produced by the specified context and formula; no display rounding is applied.
Cached input is never priced again at the regular input rate.

### Independent verification and failure behavior

1. A pure deterministic reference function owned by the recorded-fixture
   domain contract computes the expected result from the exact inputs.
2. The injected calculator returns its result independently. The adapter
   compares every result field and both binding digests with the reference
   result before recording or returning any provider result.
3. A missing quote or calculator exception before a result maps to
   `PRICING_MISSING`, retryable `false`.
4. A malformed quote/result, wrong type, not-yet-valid or expired quote,
   provider/model/currency/usage/time/hash mismatch, wrong amount, overflow, or
   any reference comparison mismatch maps to `PRICING_MISMATCH`, retryable
   `false`.
5. Success, refusal, and incomplete responses with valid usage are all priced.
   Provider-call or malformed-response failures have no pricing result and no
   recorded artifact.
6. Every pricing error is sanitized and raised from `None` before the recorder
   is called.

This calculation is marked `SYNTHETIC_TEST_ONLY`. It does not choose a
production price source, update FX, reserve or enforce a budget, approve a
model, or resolve AI-OD-008. Those remain outside ST-0703.

## ST0703-V3-D4 proposed decision

### Mechanical provenance rule

The root `openai==2.52.0` dependency and its exact offline lock closure are
semantic ST-0703 inputs. Their byte changes may mechanically invalidate
manifests owned by earlier or unrelated implemented Stories.

The following regeneration is permitted within this integration only when all
conditions hold:

1. The owning existing generator is used; no generated manifest, registry, or
   catalog is hand-edited.
2. The generated semantic payload remains byte-identical and the diff is
   limited to source inventory, byte size, SHA-256, provenance chain, or other
   mechanically derived self-integrity fields caused by approved current-tree
   bytes.
3. No canonical, upstream, ZIP, status overlay, append-only evidence, status
   request, approval, or formal result is changed.
4. If regeneration changes any semantic contract, behavior, fixture, policy,
   schema, identifier, or status, it stops and requires its own Story
   authority.
5. Every regenerated owner output must pass its exact no-write check afterward.

Under that rule, ST-0204, ST-0701, and ST-0801 manifests may be regenerated and
retained. ST-0801 must be regenerated again after the current ST-0102 toolchain
test inventory change so its manifest is not left stale.

The partial ST-0204 pin edits currently present in the ST-1203 contract,
ST-1203 generator, and ST-1204 contract shall be reverted to their exact
pre-ST-0703 values. They are not a coherent mechanical closure because those
Stories also contain a pre-existing unrelated stale ST-0305 pin. ST-0703 shall
not partially migrate or claim validation of ST-1203/ST-1204.

The pre-existing ST-1203/ST-1204 provenance debt shall be recorded as a
separate production-readiness blocker and resolved under separately approved
maintenance authority. It does not become an ST-0703 dependency and cannot be
silently waived for overall production readiness.

### Required closure evidence

- exact `pyproject.toml` and `uv.lock` parity with the approved dependency;
- owner-generation and no-write checks for every mechanically changed output;
- byte comparison proving no unapproved semantic payload changed;
- ST-0204, ST-0701, ST-0801, and ST-0102 isolated suites after final
  regeneration/synchronization;
- canonical import verification and workspace drift verification;
- explicit report of the still-separate ST-1203/ST-1204 blocker.

## ST0703-V3-D5 proposed decision

### Local command contract

Add these narrow Make targets using the existing pinned `UV_READONLY_RUN`
environment after explicit hydration:

- `openai-recorded-generate`: the only mutating target; run
  `scripts/build_st0703_recorded_adapter.py` through pinned uv after
  `python-sync`.
- `openai-recorded-check`: read-only; run both generator `--check` and
  `--check-installed` with `PYTHONDONTWRITEBYTECODE=1`, locked, offline,
  no-cache, no-sync, no-env-file, and no Python download.
- `openai-recorded-static`: read-only; run Ruff lint, Ruff format check, and
  strict mypy over the ST-0703 adapter, ports/domain support, generator, and
  isolated tests.
- `openai-recorded-test`: read-only; run isolated
  `pytest -p no:cacheprovider -q tests/st0703`.
- `openai-recorded-gate`: read-only composite of direct predecessor
  `config-check`, `ai-registry-check`, and the ST-0703 check, static, and test
  targets.

The README shall name only these real targets and the equivalent direct pinned
uv commands. It shall continue to state that hydration is separate and that
local PASS is not formal TST-017 or production evidence.

### Existing Base CI integration

No new workflow, credential, secret, environment, provider account, service,
or network-capable job is added.

1. Add `openai-recorded-check` to `ci-repository-policy` so the existing Static
   job validates generator and installed artifact drift under
   `run_network_denied.sh`.
2. Add isolated `tests/st0703` execution to `ci-unit`; the existing Unit job is
   already wrapped by `ci-network-assert` and `run_network_denied.sh`.
3. Existing global `python-lint`, `python-format-check`, and
   `python-typecheck` remain authoritative aggregate static gates.
4. `.github/workflows/ci.yml` needs no semantic job change because its existing
   pinned Static and Unit jobs invoke `scripts/ci_job.sh` and the fixed Make
   targets. If a workflow byte changes only to expose the new target, it must
   retain `contents: read`, no repository secrets, and the existing pinned
   actions/tool versions.

### Required negative coverage

The isolated suite and static checks shall prove:

- every D1 provider and non-provider matrix row, including conflicting
  class/status, hostile status attributes, subclasses, malformed identifiers,
  raw cause/context absence, and retryability;
- every D2 outcome, exact JSON field closure, success/refusal/partial/error
  redaction, canonical bytes, maximum bounds, hash and ArtifactRef mismatch,
  recorder exception, idempotency, and zero recorder calls on failed paths;
- every D3 amount and binding field, cached-token treatment, quote interval
  boundaries, wrong/zero substituted amount, overflow, Decimal-context
  isolation, and every pricing error class;
- exact request flags `store=false`, `tools=[]`, `max_retries=0`, one provider
  call, bounded timeout/output/reasoning, and strict schema bytes;
- runtime-checkable provider-neutral ports and no OpenAI SDK type crossing
  Domain, Application, or inward Port signatures;
- hard denial of socket/network paths and proof that adapter/tests read no
  environment variable, Secret, credential, configuration file, database,
  queue, object store, browser, or external service;
- exact fixture, dependency, lock, contract, registry, manifest, and source
  hash drift detection.

Formal TST-017, live provider validation, provider credentials, model-quality
evaluation, production pricing, staging, release, publication, and production
remain separately approved and unexecuted.

## Final approval question

Approve `ST0703-V3-D3`, `ST0703-V3-D4`, and `ST0703-V3-D5` exactly as written,
or identify the exact rule to replace. Only explicit approval of this now-fully
specified package authorizes creation of a complete replacement
`DESIGN_HANDOFF_V1`; implementation still waits for that handoff's exact hash
and reconciliation record.

## ST0703-V3-D3 through D5 approval record

- decisions: `ST0703-V3-D3`, `ST0703-V3-D4`, `ST0703-V3-D5`
- status: `APPROVED_BY_REPOSITORY_OWNER`
- approved_at: `2026-08-09T10:20:03Z`
- approval_source: explicit `承認する` in the connected Codex conversation
- approved_scope: the complete D3, D4, and D5 proposed-decision sections above
- cumulative_decision_status: `ST0703-V3-D1_THROUGH_D5_APPROVED`
- exact_handoff_status: `NOT_YET_APPROVED`; the generated handoff requires
  separate approval of its exact SHA-256 after canonical reconciliation
