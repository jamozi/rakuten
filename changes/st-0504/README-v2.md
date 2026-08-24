# ST-0504 durable recorded-local V2

This additive V2 keeps the original V1 non-executable reference plan intact
while implementing the maximum-safe local portion of ST-0504.

An exact persisted ST-0503 V2 normalization record is projected into every
deterministic unordered candidate pair.  Every pair remains `HUMAN_REVIEW` and
`NOT_READY`; no similarity, identity, category rule, threshold, confidence,
rank, automatic merge, or automatic split exists.

Human `MERGE` and `SPLIT` decisions are recorded as append-only history.  A
later decision points to the prior pair head and supersedes it without updating
or deleting the earlier decision.  A recorded decision is not grouping
execution: it creates no canonical product, changes no readiness, and affects
no recommendation order.

Decision recording rechecks an active ST-0401 session through the exact
`DurableAuthorizationService.recover_admin` surface and revalidates the exact
ST-0403 result, request digest, audit chain, `CAT-006` operation,
`manage_product_identity` action, PRODUCT target, stateless target, and site.
The canonical CAT-006 resource mapping remains blocked, so the runtime never
issues a new authorization and infers no resource ID.  Without a previously
durable exact allow record, processing stops at the generic review queue.

The local DEV/CI SQLite adapter uses owner-only `0700`/`0600` paths, an exact
STRICT schema, CAS, an idempotency journal, a local outbox, a per-queue hash
chain, restart recovery, and ambiguous-commit recovery.  Network, provider,
credentials, workers, publication, staging, release, Production, and external
actions are structurally absent.

Formal TST-005/TST-007/TST-008/TST-020, live, staging, release, and Production
evidence remain `NOT_EXECUTED`; local checks are not promoted to those states.
