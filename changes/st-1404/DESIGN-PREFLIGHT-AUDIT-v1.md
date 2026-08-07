# ST-1404 design-authority preflight

Status: `DESK_REVIEW_COMPLETE`  
Authority: `LOCAL_NONCANONICAL_EVIDENCE`  
Implementation authority: `NOT_GRANTED`  
Formal TST-013/TST-028: `NOT_EXECUTED`  
PostgreSQL 18.4 runtime verification in this preflight: `NOT_EXECUTED`

## Result

`ST-1404` has both declared predecessors in the local repository, but it is not
sufficiently specified for a safe implementation. The canonical Story fixes the
runtime objective, the exact two predecessors, the two acceptance phrases, and
the required suites. It supplies no `requirement_ids` or `design_refs`, while the
installed Job contract explicitly delegates two runtime semantics to ST-1404.
The physical Outbox and Inbox shapes also leave material concurrency and crash
recovery choices unresolved.

Selecting a worker loop, transaction protocol, lease algorithm, retry policy,
Outbox publication protocol, Inbox recovery rule, or the two deferred Job-state
semantics would be new architecture and reliability design. One exact
`DESIGN_HANDOFF_V1` is therefore required before an `implementation_worker`
edits production code.

## Canonical facts

| Item | Canonical fact |
| --- | --- |
| Story | `ST-1404` — Job/Outbox/Inbox runtime |
| Objective | dispatcher/worker/lease/retry/DLQ |
| Exact dependencies | `ST-0303`, `ST-0203` |
| Requirement IDs | `[]` |
| Design references | `[]` |
| Deliverable | runtime |
| Acceptance | duplicate safe; deadline/cancel |
| Required suites | `TST-013`, `TST-028` |
| Backlog open decisions | `[]` |
| Canonical status | `APPROVED_FOR_IMPLEMENTATION`; implementation `NOT_STARTED`; verification `NOT_EXECUTED` |

`TST-013` covers duplicate, out-of-order, retry, DLQ, and lease behavior using a
queue fake plus LocalStack/recorded candidates in CI. `TST-028` covers provider,
queue, database, timeout, retry, and kill-switch failure injection in staging.
Both are release-blocking and remain `NOT_EXECUTED`. ST-1404 cannot claim
kill-switch runtime ownership merely because TST-028 includes it; `ST-1405` is
the separate owning Story and depends on ST-1404.

Relevant canonical security and reliability facts include:

- `THR-017` identifies duplicate execution from queue replay and names
  idempotency, Inbox, and unique constraints as controls;
- `THR-022` identifies retry storms and cost blowout and names circuit breaker,
  budget, backoff, and DLQ as controls;
- `SEC-APP-011` binds an idempotency key to actor, operation, and payload hash;
- `SEC-INFRA-008` separates producer and consumer queue permissions;
- `SEC-APP-010` prohibits Stack, SQL, and Secret leakage to clients;
- canonical operations guidance requires bounded retry, Circuit Breaker,
  Budget, and DLQ, and identifies queue age, attempt, deadline, retry, DLQ, and
  cost as the Worker observability surface.

These controls are traceability input. Because ST-1404 has no declared
requirement IDs, the handoff must not silently claim ownership of a broader
security requirement or a later operations Story.

## Verified predecessor checkpoint

### ST-0203 queue boundary

The pinned predecessor supplies a provider-neutral synchronous `QueuePort`,
deterministic `QueueFake`, manual aware-datetime clock, duplicate and
out-of-order injection, delivery-occurrence receipt handles, lease expiry and
extension, delayed retry, and fake DLQ inspection.

It deliberately supplies no provider adapter, external broker, worker runtime,
durable persistence, or consumer-idempotency store. Its payload is generic and
caller-owned. The fake starts no thread, sleeps, opens no socket, and imports no
provider SDK.

Current local read-only verification on 2026-08-06:

- ST-0203 deterministic generation check: PASS;
- isolated ST-0203 pytest: 55 passed;
- formal TST-013: `NOT_EXECUTED`.

### ST-0303 OPS persistence boundary

The pinned predecessor supplies PostgreSQL 18.4 migration/contract bytes for
`ops.job`, `ops.job_attempt`, `ops.outbox_event`, and `ops.inbox_receipt`. It
expressly excludes runtime Job dispatch, runtime Job transition, and
lease/retry/DLQ behavior.

Current local read-only verification on 2026-08-06:

- current cumulative IAM/OPS deterministic generation check: PASS;
- isolated ST-0303 contract and generation pytest: 26 passed;
- exact PostgreSQL 18.4 integration was not re-executed by this preflight;
- formal TST-008/TST-011/TST-013 remain `NOT_EXECUTED`.

The local PASS results are candidate evidence only. They do not promote a
canonical status, formal suite, CI, staging, or Production result.

## Exact installed Job-state checkpoint

`changes/st-0002/job-state.v1.yaml` and
`contracts/raos-v0.4/job-state.v1.yaml` are byte-identical with SHA-256
`9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a`.
They define the following exact directed edges:

1. `REQUESTED -> QUEUED | CANCELLED | EXPIRED`
2. `QUEUED -> RUNNING | CANCELLED | EXPIRED`
3. `RUNNING -> SUCCEEDED | FAILED_RETRYABLE | FAILED_TERMINAL | QUARANTINED | CANCELLED | EXPIRED`
4. `FAILED_RETRYABLE -> RETRY_SCHEDULED | FAILED_TERMINAL`
5. `RETRY_SCHEDULED -> QUEUED`
6. `QUARANTINED -> QUEUED`

The contract requires a valid lease for entry to RUNNING, an Inbox receipt and
completion time for success, immutable prior attempts for retry, completion
time for terminal/quarantine/cancel/expire, operator release for quarantine,
and optimistic concurrency on Job `lock_version`.

Two exact semantics are delegated to ST-1404 and remain unresolved:

- `QUARANTINE_RELEASE_TIMESTAMPS`: whether release clears or supersedes the
  prior `completed_at` value;
- `RETRY_STATE_EXPIRY`: the approved graph has no expiry edge from retry
  states, so implementation must not invent one.

## Physical runtime inventory and material gaps

| Relation | Installed facts | Material design gap |
| --- | --- | --- |
| `ops.job` | 35 columns; ten states; `lock_version`; update trigger increments once per distinct update; ready, lease, and deadline indexes | Exact claim/heartbeat/complete/recover/retry/cancel/deadline predicates and SET lists; ownership token; attempt-count invariant; zero-row diagnosis; coalesced version increments |
| `ops.job_attempt` | 17 columns; RUNNING/SUCCEEDED/FAILED/CANCELLED/TIMED_OUT; unique `(job_id, attempt_no)` | No row version or lease token; append-versus-lifecycle completion rule; mapping from generic attempt FAILED to Job retryable/terminal states |
| `ops.outbox_event` | 19 columns; PENDING/DISPATCHING/PUBLISHED/FAILED/DEAD; ready index on PENDING/FAILED | No lease owner, lease expiry, token, row version, update timestamp, or unique event identity; exact claim/send/recover/retry/dead protocol cannot be inferred |
| `ops.inbox_receipt` | 10 columns; PROCESSING/PROCESSED/FAILED/IGNORED; unique `(consumer_name, handler_version, event_id)` | Contract labels it APPEND_ONLY while terminal states imply mutation; no lease/owner/version; exact duplicate, abandoned PROCESSING, and handler-output atomicity rules are absent |

An external queue call cannot safely be held open inside a database transaction,
yet `ops.outbox_event` has no physical lease fields. A handoff must choose a
protocol that is mechanically expressible by the existing table or identify a
separate approved schema gap. ST-1404 has no DDL authority merely because the
runtime needs a missing primitive.

## Missing design decisions

| ID | Missing decision | Risk if inferred |
| --- | --- | --- |
| ST1404-D1 | Exact Story cut and ownership relative to ST-0308 persistence, ST-0306 grants, ST-0405 Audit, ST-0706 AI orchestration, ST-1405 kill switch, and provider/IaC Stories | Hidden dependency or scope expansion |
| ST1404-D2 | Runtime process and composition model, sync/async choice, lifecycle, clock, concurrency, shutdown, and cancellation | Deadlock, leaked leases, or unbounded worker processes |
| ST1404-D3 | Exact inward handler/runtime/queue/persistence Port paths, signatures, value types, errors, and transaction ownership | Framework leakage or unusable contracts |
| ST1404-D4 | Job selection, lease acquisition/renewal/expiry/recovery, worker identity, fencing, CAS, and heartbeat behavior | Concurrent execution or stale-owner completion |
| ST1404-D5 | Every Job transition predicate/effect, attempt lifecycle, version increment, zero-row mapping, and both deferred Job-state semantics | Invalid state graph or lost update |
| ST1404-D6 | Outbox selection, claim, ownership, publish, ambiguous outcome, retry, recovery, and terminal DEAD semantics with the installed columns | Duplicate publication, stuck DISPATCHING, or fabricated lease |
| ST1404-D7 | Inbox claim/duplicate/PROCESSING recovery/terminal behavior and atomicity with handler outputs | Duplicate effects or permanent poison receipts |
| ST1404-D8 | Queue ack/retry/DLQ ordering and every database/queue/handler crash window | Message loss or unbounded replay |
| ST1404-D9 | Retry taxonomy, backoff, jitter, budgets, circuit breaker, cost limits, overflow, and deterministic clock | Retry storm or non-deterministic tests |
| ST1404-D10 | Deadline and cooperative cancellation semantics before, during, and after handler/external side effects | False cancellation claims or committed work after deadline |
| ST1404-D11 | Handler registry, payload validation, idempotency identity, output/event ownership, and transaction boundary around external work | Cross-module writes or unsafe replay |
| ST1404-D12 | Batching, fairness, queue/partition ordering, contention algorithm, and multi-process/thread behavior | Starvation or accidental global ordering claims |
| ST1404-D13 | Sanitized errors, Audit intent, metrics/tracing allowlist, workload identity, and security boundaries | Sensitive data leakage or role confusion |
| ST1404-D14 | Exact file plan, generator/contract matrices, acceptance assertions, fault injection, and formal evidence boundary | Incomplete or overstated verification |

## Existing implementation shape and reuse assessment

- No ST-1404 runtime package, Story contract, test directory, worklog, or
  generated manifest existed at preflight start.
- The existing `QueuePort`/`QueueFake` and PostgreSQL schema are strong reusable
  foundations and should not be replaced without a measured gap.
- The current Python dependency set does not establish Celery, RQ, Dramatiq,
  Temporal, or another worker framework as canonical authority.
- A thin runtime over existing Ports and explicit persistence protocols is the
  lowest-dependency candidate. A framework may reduce boilerplate only if the
  handoff proves that it preserves the installed state graph, transaction and
  lease rules, deterministic fake, bounded evidence surface, and provider-neutral
  boundary.
- The handoff must compare reuse of existing code with at least Celery, RQ,
  Dramatiq, and Temporal, plus a no-new-framework option. It must select one
  exact approach and state any dependency/lock/provenance delta. This comparison
  is design advice, not permission to install a package.
- The repository has an intentionally dirty multi-Story worktree. A later
  worker must own only exact ST-1404 paths and preserve unrelated changes.

## Scope conflicts the handoff must prevent

1. Do not import an unapproved ST-0308 repository/UoW proposal as authority or
   promote ST-0308 to an undeclared dependency.
2. Do not change DDL, migrations, roles, grants, RLS, or default privileges.
   ST-0306 artifacts may be candidate evidence only.
3. Do not implement ST-1405 kill-switch runtime, ST-0405 Audit service,
   ST-0706 AI-specific handlers, an operations UI, or Cloud/IaC resources.
4. Do not perform external/provider calls inside an open database transaction.
5. Do not claim exactly-once delivery. Required behavior is duplicate-safe over
   an at-least-once queue boundary.
6. Do not invent Job transitions, Outbox lease columns, Inbox mutable semantics,
   event ordering, retry budgets, or Production provider behavior.
7. Do not log raw payloads, event bodies, provider responses, source/review
   content, credentials, Secrets, SQL/bind values, or high-cardinality worker
   identities.
8. Do not represent local fakes or local PostgreSQL checks as formal TST-013,
   TST-028, CI, staging, or Production evidence.

## Preflight disposition

Prepare a hash-pinned Pro request that resolves ST1404-D1 through ST1404-D14
into one implementation-ready `DESIGN_HANDOFF_V1`. The returned bytes remain a
proposal until conflict-free canonical reconciliation and explicit exact-byte
repository-owner approval. Until then, implementation authority remains
`NOT_GRANTED`.
