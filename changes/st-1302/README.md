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
