# ST-1302 provider-fact commit reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_PROVIDER_FACT_COMMIT_REFERENCE_PLAN`.

This directory defines a deterministic, source-derived inventory of the checks
that a future provider-fact commit boundary would require. It is not a commit
command, fact model, repository, unit of work, transaction, job, event, audit,
outbox, fake persistence layer, provider adapter, or executable runtime.

ST-1301 is bound at commit
`20d1a2649f5b4635d49b970e76d17bd3ef93a1dc`, but that predecessor remains
synthetic-only, non-persistent, mapping `UNVERIFIED`, decision `NOT_READY`, with
no provider total, reconciliation, approval, import/artifact ID, or created
facts. OD-003 remains blocking and `EXTERNAL_EVIDENCE_REQUIRED`. Therefore this
plan cannot select a source hash, preview hash, provider identity, amounts,
period, commit result, actor, authorization, or persistence operation.

The plan preserves three distinct source vocabularies without mapping them:

- canonical row event: `GENERATED`, `CONFIRMED`, `CANCELLED`, `ADJUSTED`;
- commission status: `GENERATED`, `CONFIRMED`, `CANCELLED`, `ADJUSTED`,
  `UNKNOWN`;
- commission event: `GENERATED`, `CONFIRMED`, `CANCELLED`, `AMOUNT_CHANGED`,
  `CORRECTED`.

It also records an unresolved contract inconsistency: the canonical commit-job
catalog includes `preview_hash` in its idempotency basis, while the commit-job
payload and Admin confirm request do not expose that field. No preview hash or
replacement algorithm is selected. `FIN-006`, OAuth
`finance:revenue:confirm`, audit action `revenue_import_confirm`, and RBAC
action `commit_revenue_import` remain separate source namespaces; this plan
infers no equivalence between them.

All canonical rows, provider facts, commission events, emitted events, and
writes remain empty. Their counts, amounts, hashes, identities, times, and
results remain null—not zero. Same-hash, idempotency, reconciliation,
authorization, step-up, and audit-atomicity checks remain unevaluated. JPY is
only a frozen schema literal; FX, conversion, cost, business policy, and
retention remain unspecified.

The generated JSON and manifest are owned only by:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1302_provider_fact_commit_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1302_provider_fact_commit_reference_plan.py --check
```

Local generation and tests do not satisfy Story acceptance or formal
TST-008/TST-030. Runtime, database, provider, live, staging, release, and
Production work remains `NOT_EXECUTED` and unauthorized.

## Maximum-safe recorded implementation (V2)

The V1 reference above remains the fail-closed description of the unresolved
canonical/live boundary. V2 adds a separate executable-local profile,
`RAOS_ST1302_RECORDED_SYNTHETIC_V1`, for `ENV-DEV` and `ENV-CI` only. It does
not replace V1 and does not resolve OD-003.

The V2 fixture reconstructs the exact accepted ST-1301 dry-run artifact and
binds each accepted row by source hash, ST-1301 command fingerprint, row number
and hash, hashed synthetic event key, source event type, event timestamp,
integral `Decimal` JPY, missingness, status summary, and observed period. The
resulting `RAOS_ST1302_LOCAL_PREVIEW_BINDING_SHA256_V1` value is an explicit
reversible local contract. It is not claimed to equal the unresolved canonical
`preview_hash`.

The application boundary validates the recorded typed authorization before one
process-local atomic exchange. It enforces the canonical allowed roles
`PRODUCT_OWNER`/`ANALYST`, recorded active-human, MFA, step-up freshness, and
site scope. A distinct dry-run preparer and committer is an additive local
safety hardening, not a newly inferred canonical role mapping. Same-key,
same-request replay is idempotent; a changed request under the same key and a
second key for an already committed source are rejected.

The exchange produces immutable local provider facts, source-vocabulary
commission observations, one audit record, and outbox-like local records.
`GENERATED`, `CONFIRMED`, `CANCELLED`, and `ADJUSTED` remain source values. The
canonical commission-event vocabulary remains preserved separately and V2
emits no inferred canonical event type: every observation is
`UNVERIFIED_PRESERVED_UNMAPPED`.

The implementation has no provider, network, database, publication, staging,
release, or Production adapter. Every such authority flag is false and every
execution value is `NOT_EXECUTED`. The process-local adapter is an executable
recorded test seam, not durable persistence or evidence for TST-008/TST-030.

V2 artifacts are owned only by:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1302_provider_fact_commit_recorded.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1302_provider_fact_commit_recorded.py --check
```

See `LOCAL_COMPLETION.md` for the exact local completion and external-debt
boundary. Neither document changes Canonical Story status.
