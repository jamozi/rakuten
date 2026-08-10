# ST-0703 V3 canonical reconciliation

Status: `PASS_APPROVED_FOR_RECORDED_IMPLEMENTATION`
Story: `ST-0703`
Implementation authority: `GRANTED_ST0703_RECORDED_SCOPE_ONLY`
Formal TST-017: `NOT_EXECUTED`
Live provider, staging, and production: `NOT_EXECUTED`

## Exact proposal identity

- Handoff: `changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v3.yaml`
- Handoff SHA-256:
  `a510526678190b0512a5d28e016f1ab978469e10cc5063d6a2482f93b6ce43c8`
- Approved decision source:
  `changes/st-0703/DESIGN-DECISION-REQUEST-v3.md`
- Approved decision-source SHA-256:
  `ed65ac3237b60be87eed02bb296799e3da764052f4b4820dfaec4d3d9a367166`
- Exact approval: `changes/st-0703/DESIGN-HANDOFF-APPROVAL-v3.yaml`
- Exact approval SHA-256:
  `df9b39bf9969618a34a58fc0dfab679467ab02a360f22c306d4d408a8ecd5eae`
- Superseded V2 handoff SHA-256:
  `f768571d5f56a313437cc108485f21a7c3a8a9226016bee7830ab3709a90f08f`

The repository owner explicitly approved D1 through D5 and then approved the
exact V3 handoff SHA-256 in the connected Codex conversation at
`2026-08-09T10:31:10Z`. The separate approval artifact preserves the immutable
handoff bytes. Implementation authority is granted only for the recorded
ST-0703 scope and authorized mechanical owner regeneration.

## Canonical evidence compared

| Evidence | SHA-256 | Reconciliation use |
| --- | --- | --- |
| `docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml` | `4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d` | ST-0703 scope, dependencies, FR-018, deliverable, required suite |
| `docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml` | `7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b` | recorded TST-017 boundary |
| `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md` | `540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a` | canonical precedence and one-Story implementation boundary |
| `docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml` | `c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8` | secret, logging, provider, artifact, and fail-closed controls |
| `changes/st-0204/manifest.yaml` | `712ac8ca53618ec05a05de6ada2ccaacf9e782377d8d9913c655999f4df9df05` | direct runtime-config predecessor evidence |
| `changes/st-0701/manifest.yaml` | `4fc7f1936462b89a249a595fd6eb89c2162cbf176eb8ada43f29245639bb06e7` | direct AI-contract predecessor evidence |
| `changes/st-0703/contracts/openai-responses-adapter.v1.yaml` | `8b32a862ce58fe17da931012be7c5d1ab71c0630b5bc6bb20234391d8323b97c` | pre-implementation candidate contract reconciled by D1 through D5 |
| `pyproject.toml` | `d7a03c351a2ef20d6aaf45b4dff7775b3ce9dbb7e051323cfbf35d295344814e` | exact OpenAI dependency input |
| `uv.lock` | `90d79255a5bd0a6d0c918b8f496dec0a1bd11fb25316cdc5b1a9526c2eed3729` | exact reviewed offline resolution closure |

## Scope reconciliation

| Canonical requirement | V3 decision | Result |
| --- | --- | --- |
| Single Story `ST-0703` | No other Story receives a semantic implementation change | `PASS` |
| Exact dependencies `ST-0701`, `ST-0204` | Both remain the only declared Story dependencies | `PASS` |
| Requirement `FR-018` | Structured Responses request/result, refusal, usage, estimated JPY, and sanitized errors are retained | `PASS` |
| Provider-neutral inward Port and outward adapter | OpenAI SDK types remain outside Domain, Application, and inward signatures | `PASS` |
| Recorded suite `TST-017` | Fixtures, fake injected client, denied network, and no credentials only | `PASS` |
| `store=false`, `tools=[]`, bounded output and reasoning | Exact request mapping and negative checks are binding | `PASS` |
| No implicit adapter retry | `max_retries=0`; retryability is classification data only | `PASS` |
| Raw provider material must not escape | Closed errors and content-free record schema prohibit it | `PASS` |
| `raw_artifact` without new storage authority | Injected recorder returns provider-neutral `ArtifactRef`; ST-0601 remains owner | `PASS` |
| Estimated fixture cost without resolving production pricing | Expiring synthetic quote, deterministic formula, and independent recomputation only | `PASS` |

## V2 audit gaps closed

| Gap | V3 closure | Result |
| --- | --- | --- |
| Exact exception/status and retryability matrix | D1 defines closed rows, conflict handling, hostile status behavior, stage mapping, and sanitation | `PASS` |
| Exact recordable bytes and disposition | D2 defines every field, outcome, bound, hash, record order, and no-artifact failure path | `PASS` |
| Exact pricing types, rounding, freshness, and binding | D3 defines quote expiry, Decimal context, formula, ceiling, digests, and independent comparison | `PASS` |
| Predecessor-manifest propagation conflict | D4 permits only owner-generated hash/provenance changes and separates unrelated stale ST-1203/ST-1204 debt | `PASS` |
| Missing local/CI contract | D5 defines exact Make targets and reuses existing denied-network Static and Unit jobs | `PASS` |

## Architecture and ownership reconciliation

- Domain and inward Ports receive no OpenAI SDK object, exception, credential,
  Secret reference, environment variable, or provider client.
- Application composition injects a preconfigured client, recorder, synthetic
  quote/calculator, and deterministic clocks; ST-0703 constructs none of the
  live resources.
- ST-0407 retains Secret resolution and authenticated live-client creation.
- ST-0601 retains physical artifact storage, cleanup, and production URI
  policy.
- ST-0704 and ST-0706 retain routing, fallback, circuit breaker, budget, and
  retry orchestration.
- ST-0705 retains factual, policy, and content-quality validation beyond strict
  JSON Schema.
- Mechanical owner regeneration is not a semantic implementation of another
  Story. Any semantic generator delta stops instead of being absorbed.

## Security reconciliation

- Only stable error code and closed retryability cross the error boundary.
- Conflicting class/status signals fail to non-retryable `UNKNOWN`.
- Errors have no raw cause/context and are raised from `None`.
- Recorded artifacts contain no prompt, source, output, refusal text, partial
  text, reasoning, headers, URLs, credentials, exception, or error body.
- Pricing is synthetic, expiring, exact-input-bound, and independently
  recomputed before any record is written.
- Recorded gates use no network, Secret, credential, provider account, storage,
  queue, database, browser, or external service.

## Deferred external decisions preserved

- `OD-015` remains unresolved and blocks live provider credentials/evidence.
- `AI-OD-001` remains unresolved and blocks live/production account-data and
  ZDR decisions.
- `AI-OD-008` remains unresolved and blocks production pricing, FX, and budget
  enforcement.

The V3 handoff's `open_decisions: []` applies only to the fully specified
recorded ST-0703 scope. It does not close or weaken these external decisions.

## Pro escalation record

The gated Pro run `20260809T084221Z-d51eeaa7e1a9` stopped before submission
with `SELECTOR_AMBIGUITY`, `submission_attempted: false`, and no captured
advice. No Pro output was treated as authority or evidence. The repository
owner subsequently resolved D1 through D5 explicitly in conversation.

## Local structural verification

The exact proposed handoff bytes were parsed read-only with `yaml.safe_load`
and checked without modifying the file. The result was:

```json
{"handoff_sha256":"a510526678190b0512a5d28e016f1ab978469e10cc5063d6a2482f93b6ce43c8","status":"PASS","yaml_root":"DESIGN_HANDOFF_V1","open_decisions":0,"approved_decisions":5,"deferred_external_decisions":3}
```

The check also proved LF-only bytes, the complete required handoff field set,
all six decision blocks, ordered D1-through-D5 decision identities, and the
exact deferred list `OD-015`, `AI-OD-001`, `AI-OD-008`. This is proposal
structure evidence only. It is not implementation, formal TST-017, live,
staging, release, or production evidence.

## Approval closure

Canonical reconciliation finds no material conflict for the recorded scope.
The repository owner approved this exact handoff identity:

```text
a510526678190b0512a5d28e016f1ab978469e10cc5063d6a2482f93b6ce43c8  changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v3.yaml
```

Implementation may resume only for ST-0703 and its authorized mechanical
owner-generated provenance closure. Formal TST-017, live provider evidence,
staging, release, and production remain separate and unexecuted.
