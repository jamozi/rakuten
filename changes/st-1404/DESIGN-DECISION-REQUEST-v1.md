# ST-1404 Job/Outbox/Inbox runtime DESIGN_HANDOFF_V1 request

Status: `PROPOSAL_REQUEST_ONLY`  
Authority: `UNAPPROVED_PROPOSAL_INPUT`  
Implementation authority: `NOT_GRANTED`  
Human approval: `NOT_PROVIDED`  
Canonical reconciliation: `PENDING`  
Formal TST-013/TST-028: `NOT_EXECUTED`  
CI/staging validation: `NOT_EXECUTED`  
Production readiness: `NOT_READY`

## Task

Produce one complete, self-contained, implementation-ready
`DESIGN_HANDOFF_V1` proposal for the single canonical Story `ST-1404`.
Resolve exactly `ST1404-D1` through `ST1404-D14`. Do not implement code, add a
dependency, change a database or role, access an external queue/provider, close
an unrelated Open Decision, or broaden the Story.

The exact returned bytes remain unapproved until they are reconciled against
canonical precedence and explicitly approved by the repository owner. This
request, packet, alternatives, and local audit are review evidence only and
grant no implementation authority.

## Canonical scope

- Story: `ST-1404` — Job/Outbox/Inbox runtime
- Objective: dispatcher/worker/lease/retry/DLQ
- Exact declared dependencies: `ST-0303`, `ST-0203`
- Requirement IDs: `[]`
- Design references: `[]`
- Deliverable: runtime
- Acceptance criteria: duplicate safe; deadline/cancel
- Required suites: `TST-013`, `TST-028`
- Story open decisions: `[]`
- Canonical status: design approved; implementation `NOT_STARTED`;
  verification `NOT_EXECUTED`

The absence of Story-level `requirement_ids`, `design_refs`, and backlog Open
Decisions does not authorize the implementer to invent runtime semantics. The
installed Job-state contract explicitly assigns two decisions to ST-1404, and
the installed physical schema leaves Outbox/Inbox ownership and recovery
mechanics under-specified. This handoff must supply that bounded precision
without silently changing the exact dependency set.

## Predecessor and implementation checkpoint

### ST-0203

The predecessor supplies a synchronous provider-neutral `QueuePort` with
`send`, `receive`, `acknowledge`, `retry`, and `extend_lease`; immutable
`QueueMessage`/`QueueDelivery` values; and a deterministic manual-clock fake.
The fake supports duplicates, out-of-order delivery, lease expiry/redelivery,
lease extension, delayed retry, and terminal dead-letter observations. It
implements no external broker, provider adapter, worker runtime, durable
persistence, or consumer-idempotency store.

### ST-0303

The predecessor supplies the physical PostgreSQL 18.4 contract and migration
for `ops.job`, `ops.job_attempt`, `ops.outbox_event`, and
`ops.inbox_receipt`. It explicitly excludes runtime Job dispatch, runtime Job
transition, and lease/retry/DLQ behavior. It does not grant ST-1404 authority to
modify schema, migrations, roles, grants, RLS, or default privileges.

### Local candidate evidence

The attached preflight records the following current local checks:

- canonical import verification: PASS;
- ST-0203 deterministic generation check: PASS;
- isolated ST-0203 pytest: 55 passed;
- current cumulative IAM/OPS deterministic generation check: PASS;
- isolated ST-0303 contract/generation pytest: 26 passed;
- formal TST-013/TST-028: `NOT_EXECUTED`;
- PostgreSQL 18.4 runtime integration was not re-executed for this packet.

These are candidate facts only. They do not constitute formal CI, staging,
Production, TST-013, or TST-028 evidence.

## Installed physical and state constraints

### Job state graph

The exact installed `job-state.v1.yaml` has SHA-256
`9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a`
and permits exactly these sixteen directed edges:

1. `REQUESTED -> QUEUED`
2. `REQUESTED -> CANCELLED`
3. `REQUESTED -> EXPIRED`
4. `QUEUED -> RUNNING`
5. `QUEUED -> CANCELLED`
6. `QUEUED -> EXPIRED`
7. `RUNNING -> SUCCEEDED`
8. `RUNNING -> FAILED_RETRYABLE`
9. `RUNNING -> FAILED_TERMINAL`
10. `RUNNING -> QUARANTINED`
11. `RUNNING -> CANCELLED`
12. `RUNNING -> EXPIRED`
13. `FAILED_RETRYABLE -> RETRY_SCHEDULED`
14. `FAILED_RETRYABLE -> FAILED_TERMINAL`
15. `RETRY_SCHEDULED -> QUEUED`
16. `QUARANTINED -> QUEUED`

The graph forbids self-transitions. RUNNING requires a valid lease; success
requires an Inbox receipt; retry never mutates a prior attempt; Job mutations
use optimistic concurrency. The following exact deferred semantics must be
resolved, not ignored:

- `QUARANTINE_RELEASE_TIMESTAMPS`: clear versus supersede the prior
  `completed_at` value;
- `RETRY_STATE_EXPIRY`: the current graph contains no expiry edge from
  FAILED_RETRYABLE or RETRY_SCHEDULED, and no implementation may invent one.

### Physical limitations that constrain the answer

- `ops.job` has `lock_version` and a trigger that increments it for every
  distinct UPDATE. It has a nullable pair `lease_owner`/`lease_expires_at`, but
  no separate lease token or heartbeat column.
- `ops.job_attempt` has no version or lease token. It has unique
  `(job_id, attempt_no)` and lifecycle statuses RUNNING, SUCCEEDED, FAILED,
  CANCELLED, and TIMED_OUT.
- `ops.outbox_event` has statuses PENDING, DISPATCHING, PUBLISHED, FAILED, and
  DEAD, but no lease owner, lease expiry, fencing token, row version, updated
  timestamp, or unique event identity. Its ready index covers PENDING/FAILED.
- `ops.inbox_receipt` has unique
  `(consumer_name, handler_version, event_id)` and statuses PROCESSING,
  PROCESSED, FAILED, and IGNORED, but no lease, owner, version, or update
  timestamp. ST-0303 labels the relation APPEND_ONLY even though its lifecycle
  statuses imply a terminal update; ST-0303 installs no immutable trigger on
  this relation.
- Existing columns, constraints, and indexes are authoritative. A runtime need
  does not authorize a hidden DDL or migration change.

If the installed shape cannot safely express a required protocol, the handoff
must identify the exact schema-story gap and keep that portion blocked rather
than fabricate a column, overload an unrelated field, or weaken correctness.

### Cross-contract mismatches that must be reconciled

The handoff must resolve, rather than merely restate, these mismatches:

1. ST-0203 redelivers an expired queue lease with a new receipt, but the Job
   graph has neither `RUNNING -> QUEUED` nor `RUNNING -> RUNNING`. A stale DB
   Job can remain RUNNING when its delivery is redelivered.
2. `QueueDelivery.delivery_attempt`, `ops.job.attempt_count`,
   `ops.job_attempt.attempt_no`, and `ops.outbox_event.publish_attempts` are
   independent counters with no approved binding rule.
3. Queue `available_at`, Job `available_at`, Outbox `available_at`, and Attempt
   `retry_after_at` have no approved authority/propagation rule.
4. Job success requires an Inbox receipt, but Inbox uniqueness uses `event_id`,
   while Job and Queue use `job_id` and `message_id`; no FK or identity equality
   rule binds them. Including `handler_version` in Inbox uniqueness also permits
   reprocessing under a new version unless policy forbids it.
5. `jp.raos.ops.job_requested.v1` does not carry every field required by the
   canonical Job message. Loading and mapping the authoritative Job row is a
   choreography decision, not a mechanical serialization.
6. “Outbox dispatcher” can mean publishing an Outbox row to an event channel or
   consuming `job_requested` and sending a Job queue message. The packet shows
   no approved one-stage versus two-stage topology.
7. Provider DLQ channels, the in-memory fake `DeadLetter`, Outbox DEAD, and Job
   QUARANTINED are distinct mechanisms. There is no physical DLQ table and the
   current Queue Port has no DLQ triage/replay method.
8. The Queue Port combines producer and consumer operations, while
   `SEC-INFRA-008` requires permission separation. The runtime must expose
   composition capabilities narrowly without breaking the predecessor Port.
9. Only Job requested, succeeded, failed-terminal, and quarantined event schemas
   currently exist. There is no approved retry-scheduled, cancelled, or expired
   event schema.
10. The database permits `cancel_requested_at` in any state other than
    SUCCEEDED, but canonical cancellability is limited to REQUESTED, QUEUED, and
    RUNNING. Runtime predicates must enforce the stronger canonical rule.

## Decisions to resolve

### ST1404-D1 — exact Story cut, ownership, and reuse strategy

Define the smallest complete ST-1404 cut and an exact ownership matrix for Job
creation/dispatch/execution, attempts, Outbox, Inbox, queue/provider adapters,
handler registration, audit intents, kill-switch checks, module persistence,
and process composition.

Candidate A (recommended for review): implement provider-neutral runtime
services, explicit framework-neutral persistence/handler Ports, deterministic
clock/fakes, and adapters over the exact ST-0303 relations plus existing
ST-0203 `QueuePort`. Defer a production broker adapter and deployment loop to
their owning provider/IaC/composition Stories. Do not import ST-0308 as an
undeclared dependency.

Candidate B: include a concrete SQS/LocalStack adapter and long-running worker
composition. This requires exact SDK, version, endpoint, identity, timeout,
retry, shutdown, and operational ownership decisions and must not depend on a
Production credential.

Candidate C: adopt an existing worker framework.

Compare the no-new-framework design with at least Celery, RQ, Dramatiq, and
Temporal. For each, evaluate compatibility with the already installed Job
state graph, existing `QueuePort`, transaction and Inbox/Outbox semantics,
lease fencing, deterministic tests, PostgreSQL schema, provider neutrality,
supply-chain cost, and scope. Select exactly one approach. A framework must not
be added merely to replace a small bounded loop; if selected, pin exact package
versions/provenance and state every lockfile/change.

State exact in-scope deliverables, exclusions, owner Stories, consumed existing
artifacts, and why no undeclared dependency is promoted. Reconcile, at minimum:

- ST-0308 persistence repositories/UoW: not a declared dependency and not
  approved implementation authority;
- ST-0306 database roles/grants: candidate evidence only;
- ST-0405 Audit service: separate owner;
- ST-0706 AI-specific Job orchestration/handlers: separate owner;
- ST-1405 kill-switch runtime: separate owner that depends on ST-1404;
- ST-1502 provider queue infrastructure/IAM: separate owner.

Provide an exact two-topology routing matrix covering every AsyncAPI Domain
Event channel and every Job/DLQ queue relevant to this Story. For each Outbox
event type, name the closed registry source, event channel, wire schema,
message identity, and whether the runtime only publishes a Domain Event or also
materializes/enqueues a Job. Unknown event types, channels, Job types, and queue
names must fail closed.

### ST1404-D2 — runtime process, lifecycle, and composition

Choose synchronous, asynchronous, or split runtime semantics and provide exact
reasoning. Define process objects, construction paths, polling/receive entry
points, one-iteration deterministic methods, long-running loop ownership,
concurrency units, task/thread/process use, startup validation, graceful drain,
hard shutdown, cancellation, clock injection, random/jitter injection, and
resource close behavior.

Specify whether ST-1404 implements only deterministic one-step runtime services
while an outer composition Story owns the forever loop. If it implements a
loop, define bounded wait, wakeup, signal handling, exception containment,
maximum concurrent work, backpressure, and shutdown deadline. No import-time
thread/task/process, global singleton, ambient event loop, unbounded sleep,
wall-clock dependency, or hidden network call is allowed.

Define how API, dispatcher, and worker compositions receive only the capabilities
they require. Application/Domain code must not receive a SQLAlchemy Session,
Engine, provider client, raw connection, queue SDK object, or arbitrary handler
mapping.

### ST1404-D3 — exact inward Ports, Domain values, and error model

Provide exact module paths, exported symbols, method signatures, argument and
return types, sync/async behavior, context-manager behavior, errors, and side
effects for every public runtime boundary. Include at least:

- Job runtime persistence;
- Job handler/registry lookup;
- Outbox dispatcher persistence;
- Inbox consumer persistence;
- queue send/receive/ack/retry/lease extension reuse or extension;
- clock and deterministic jitter/random source;
- cancellation/deadline signal;
- transaction boundary or exact transaction-owned callback;
- sanitized Audit intent sink if required;
- metrics/tracing sink if implemented in this Story.

Use immutable named values for identifiers, versions, lease ownership,
timestamps, durations, message/event identity, attempts, retry decisions,
handler results, and errors. Specify strict payload/JSON values and maximum
sizes. Do not export generic dictionaries, arbitrary SQL/filter objects,
framework exceptions, SQLAlchemy/provider rows, or `Any` at a trust boundary.

Define a closed error taxonomy with retryability and sanitization. At minimum
cover not found, stale Job version/state, lost lease, stale queue receipt,
duplicate Inbox, handler missing/version mismatch, invalid payload/contract,
deadline, cancellation, timeout, transient database/queue/provider failure,
permanent failure, quarantine, retry budget exhaustion, ambiguous publish or
commit outcome, schema drift, persisted corruption, and ownership misuse.

### ST1404-D4 — Job selection, lease, heartbeat, fencing, and recovery

Define exact selection and claim semantics for REQUESTED/QUEUED/
RETRY_SCHEDULED work and distinguish dispatcher acceptance from worker lease
acquisition. For every operation provide:

- exact input and result type;
- allowed states and time predicates;
- complete SQL WHERE predicate and atomic SET list;
- whether `FOR UPDATE`, `SKIP LOCKED`, a single UPDATE/RETURNING, or another
  mechanically specified strategy is used;
- expected `lock_version` behavior under the ST-0303 trigger;
- worker/lease owner format, maximum length, sensitivity, and cardinality;
- lease duration bounds and whether renewal is from transaction time or prior
  expiry;
- stale owner, stolen lease, late heartbeat, expired lease, and clock-skew
  behavior;
- whether a lease owner may reenter and whether that is a forbidden
  self-transition;
- zero-row diagnosis without unguarded retry;
- database transaction and queue receipt ownership.

Because no physical fence token exists, prove how a stale worker is prevented
from committing completion after lease expiry/reassignment. If
`lease_owner + lease_expires_at + lock_version` is insufficient for safe
fencing across the required crash windows, identify an exact schema gap and do
not claim the lease protocol complete.

Define expired RUNNING recovery: who discovers it, whether it appends/finishes
an attempt, how attempt count and max attempts are enforced, and which exact
existing Job transition is used. The installed graph has no direct RUNNING to
QUEUED or RETRY_SCHEDULED edge; do not invent one.

The Job touch trigger—not application code—sets `updated_at` and increments
`lock_version` for every distinct UPDATE. Every predicate must compare the
expected version and every result must obtain the trigger-produced post-version
through RETURNING. Heartbeat/lease/cancel/state operations must thread that
post-version forward as their next fence. Do not assign `lock_version` in an
application SET list or perform avoidable multiple UPDATEs for one logical
operation.

### ST1404-D5 — Job and attempt transition matrices

Provide one normative `job_transition_matrix` row for each of the sixteen
installed directed edges and every exposed non-edge operation such as cancel
request and heartbeat. Each row must contain:

- exact method/signature;
- command owner and required authorization/capability;
- expected from/to state;
- expected `lock_version` and lease/owner preconditions;
- all deadline, cancel, timestamp, attempt, evidence, Inbox, and operator
  guards;
- complete WHERE predicate and complete atomic SET list;
- whether one physical UPDATE causes exactly one trigger-driven version
  increment;
- returned post-version and fields;
- zero-row mapping to not-found, stale-version, state-conflict, lost-lease,
  deadline, or cancellation;
- attempt row and Audit/event effects in the same transaction;
- rollback and idempotent re-invocation behavior.

The matrix must also enumerate all 84 forbidden ordered state pairs across the
ten-state Cartesian product. No pair may be left to an implicit default or
implementer judgment.

Resolve `QUARANTINE_RELEASE_TIMESTAMPS` exactly. Explain the invariant involving
the prior terminal-like `completed_at`, the installed completion check, and the
new QUEUED state without adding a new column.

Resolve `RETRY_STATE_EXPIRY` exactly while preserving the current graph. If
deadline expiry in FAILED_RETRYABLE/RETRY_SCHEDULED cannot be represented by an
approved edge, define a safe non-mutating hold/escalation or identify a required
contract revision. Do not add a hidden edge.

Provide an `attempt_lifecycle_matrix` for insert RUNNING and finish as
SUCCEEDED/FAILED/CANCELLED/TIMED_OUT. Specify whether terminalization is an
allowed UPDATE despite attempts being described as immutable/append-oriented,
the full predicate without a version column, who owns it, how stale workers are
fenced, how `attempt_no`, `attempt_count`, and `max_attempts` remain consistent,
and how generic attempt FAILED maps to retryable/terminal Job outcomes.

Provide exact counter and time-authority rules binding Queue delivery attempt,
Job `attempt_count`, Attempt `attempt_no`, Outbox `publish_attempts`, and the
four scheduling timestamps: Queue/Job/Outbox `available_at` and Attempt
`retry_after_at`. State each increment/write point, rollback behavior, maximum,
source clock, and which value is authoritative after duplicate delivery.

Define manual retry separately from the sixteen state edges. Reconcile the
installed Admin API manual-retry command, If-Match, Idempotency-Key, Audit
action, and `reset_attempt_budget` with absorbing SUCCEEDED,
FAILED_TERMINAL, CANCELLED, and EXPIRED states. Select whether retry creates a
new Job rather than mutating the original; define `parent_job_id`, correlation,
causation, new identity/idempotency, attempt budget, immutable history,
QUARANTINED release distinction, and whether the API command itself belongs to
ST-1404 or a separate API Story.

### ST1404-D6 — Outbox dispatcher protocol

Define complete PENDING/DISPATCHING/PUBLISHED/FAILED/DEAD semantics using only
the installed columns, or state an exact blocked schema gap. Cover:

- selection eligibility, stable ordering, batching, fairness, and contention;
- claim ownership and recovery without lease/token/version columns;
- increment timing and semantics for `publish_attempts`;
- external queue send outside a database transaction;
- status change and crash windows before claim, after claim, before send, after
  send but before persistence, after persistence but before return, and during
  ambiguous queue outcome;
- message identity and idempotency key derivation from immutable Outbox data;
- duplicate send behavior and downstream deduplication obligation;
- FAILED scheduling through `available_at`, retry classification, max attempts,
  and DEAD terminalization;
- PUBLISHED `published_at` and forbidden mutation afterward;
- explicit NULL/non-NULL rules for `published_at` in every state, because the
  installed check enforces only PUBLISHED implies non-NULL;
- recovery of orphaned DISPATCHING rows with no updated/lease timestamp;
- schema hash/payload validation and corruption/quarantine behavior;
- queue ack semantics if Outbox dispatch consumes a database-ready row rather
  than a queue delivery.

Do not hold a transaction across a provider call. Do not claim exactly once.
Do not overload `last_error`, `available_at`, `created_at`,
`publish_attempts`, or a business envelope field as a secret lease token unless
the physical/canonical contract explicitly supports that meaning.

If safe multi-worker DISPATCHING recovery is not expressible, choose one of:

1. a bounded single-dispatcher/no-crash-recovery local implementation with an
   explicit not-Production gate;
2. an insert/direct-send protocol that does not use DISPATCHING, with all
   duplicate consequences proved;
3. a separately approved schema revision adding the missing concurrency
   primitive.

Select one exact disposition and do not represent an incomplete variant as
Production-ready.

Also define the closed event-type-to-channel resolver. The Outbox has no channel
column, so routing must be derived from a hash-pinned AsyncAPI/schema-registry
entry, never a caller-provided destination or naming convention inferred at
runtime. State whether publishing `jp.raos.ops.job_requested.v1` to
`ops.events` ends the Outbox operation or whether a separately owned consumer
loads the Job and emits the canonical Job message to a Job queue.

### ST1404-D7 — Inbox duplicate and recovery protocol

Define exact insert-first claim semantics around unique
`(consumer_name, handler_version, event_id)`, including whether
`INSERT ... ON CONFLICT DO NOTHING RETURNING` is required and how an existing
row is interpreted.

For PROCESSING/PROCESSED/FAILED/IGNORED define:

- allowed transition operations and exact predicates/SET lists;
- whether and why lifecycle UPDATE is allowed despite APPEND_ONLY
  classification;
- duplicate delivery behavior for each stored state;
- handler-version upgrade behavior;
- abandoned PROCESSING recovery without lease/updated timestamp;
- result hash derivation and strict supported representation;
- deterministic failure versus infrastructure failure persistence;
- poison/invalid event disposition;
- interaction with queue acknowledge/retry;
- whether a FAILED receipt may ever be retried under the same unique identity;
- whether IGNORED means successful consumption for acknowledgement;
- zero-row/unique-conflict/error mappings.

Define the atomicity boundary between Inbox terminal state, handler-owned
database outputs, Job success, Domain events/Outbox rows, and external side
effects. ST-1404 cannot expose another module's repository or silently adopt an
unapproved generic ST-0308 UoW. If cross-module atomic output is not possible
under declared dependencies, define the narrow transaction-owned callback or
defer handler-specific integration explicitly.

### ST1404-D8 — queue/database/handler ordering and crash matrix

Provide a normative crash-consistency matrix for every boundary among:

1. queue receive;
2. Inbox claim;
3. Job lease/attempt start;
4. payload validation;
5. handler execution;
6. database output commit;
7. Inbox/Job terminal commit;
8. Outbox append;
9. queue acknowledgement;
10. queue retry/DLQ action;
11. lease extension;
12. process termination.

For each pre/post operation crash, state the durable rows, queue visibility,
next actor action, duplicate behavior, fencing rule, and proof that neither
message loss nor duplicate business effect occurs. Distinguish database
`outbox_event.status = DEAD`, the ST-0203 fake's dead-letter observation, and a
provider DLQ; decide which component owns each and how identities correlate.

The ST-0203 `QueuePort` has no DLQ receive, inspect, redrive, replay, discard,
or disposition operation. Select exactly whether ST-1404 owns only automatic
dead-lettering, adds an operator replay Port under explicit cross-Story
authority, or defers the management plane to a provider/IaC/operations owner.
Do not claim DLQ triage/replay coverage when the selected Port cannot perform
it.

Resolve stale/unknown receipt behavior after a successful database commit. A
failed acknowledgement must not roll back an already committed handler result;
the subsequent duplicate must be neutralized by the Inbox protocol.

### ST1404-D9 — retry, backoff, budget, circuit breaker, and cost

Define a closed retry decision union and exact classification matrix for
handler/domain rejection, validation/policy quarantine, database unavailable,
deadlock/serialization, queue timeout/unavailable, provider 429/5xx/timeout,
authentication/authorization, schema drift, cancellation, deadline, lost
lease, ambiguous outcome, and unknown exception.

Specify:

- maximum attempts source and relation to Job/Queue budgets;
- deterministic exponential/other backoff formula;
- base, multiplier, cap, jitter algorithm, injected entropy, and overflow rule;
- `retry_after_at` versus Job `available_at` ownership;
- exact clock source and UTC/monotonic use;
- global/provider/route budgets and the unresolved Product budget boundary;
- circuit-breaker state ownership, persistence, window, thresholds, half-open
  behavior, concurrency, reset, and restart semantics;
- cost/budget checks and behavior when `budget_jpy` is NULL;
- retry-storm and poison-message containment;
- terminal DEAD/FAILED_TERMINAL/QUARANTINED selection;
- no retry after cancellation, expiry, nonretryable invariant failure, stale
  lease, or known business rejection unless specifically justified.

If a durable circuit breaker or retry budget requires state not present in the
declared predecessors, identify it as a deferred owner/gap; do not store it in
an unrelated column or add a process-global best-effort mechanism while claiming
the canonical control complete.

### ST1404-D10 — deadline and cooperative cancellation

Define exact behavior for `deadline_at` and `cancel_requested_at` at selection,
before queue send, before lease acquisition, before handler invocation, at
handler checkpoints, before each database commit, during an external call,
after handler output, before acknowledgement, and after an ambiguous commit.

Specify:

- transaction timestamp versus injected wall/monotonic clock;
- deadline equality boundary;
- cancellation signal/token contract;
- which installed Job edges are used from REQUESTED/QUEUED/RUNNING;
- behavior in FAILED_RETRYABLE and RETRY_SCHEDULED without an expiry edge;
- attempt terminal status for cancel/deadline;
- lease extension denial near/after deadline;
- maximum blocking call and timeout propagation;
- late external response and committed external side-effect behavior;
- cancellation precedence over retryable failure;
- whether a cancel request itself mutates only `cancel_requested_at` before the
  cooperative terminal transition, including version/CAS semantics;
- ambiguous commit/publish behavior that cannot be reported as confirmed
  cancellation.

Do not claim instant cancellation of a synchronous provider/driver call. Do not
implement ST-1405 kill-switch semantics as a substitute for cancellation.

### ST1404-D11 — handler registry, payload, idempotency, and output boundary

Define exact handler registration and lookup keys, version compatibility,
duplicate registration behavior, immutable snapshot/lifecycle, and composition
ownership. Define the handler callable signature and input context, including
Job identity/version, attempt, correlation/causation, actor/source, deadline,
cancellation, lease check capability, strict payload, and output/event intent.

Specify:

- payload schema/version lookup and validation before side effects;
- maximum inline payload and artifact-reference behavior without implementing
  object storage;
- idempotency identity and relationship among Job idempotency key, queue
  message ID/key, Inbox event identity, handler version, and actor/operation/
  payload hash from `SEC-APP-011`;
- handler result union for success/retryable/permanent/quarantine/cancelled/
  expired;
- handler-owned database output through its public Application Interface or a
  narrow joined transaction capability, never direct repository access;
- external provider calls outside database transactions;
- compensation/reconciliation for external side effects;
- event/Outbox ownership and post-commit continuation;
- prohibition on dynamic import paths, arbitrary callables from payloads,
  eval/exec, pickle, provider objects, and untrusted exception formatting.

The physical Job unique identity is only `(job_type, idempotency_key)` and
cannot alone prove the actor/operation/payload-hash binding required by
`SEC-APP-011`. Define the producer-side canonical identity, the boundary with
`ops.idempotency_record`, mismatch detection, and the owning Story if ST-1404
does not implement HTTP/Application idempotency. Do not put a raw actor
fingerprint or payload hash into error/log fields as a workaround.

State whether each Job/Event boundary is validated directly against the
installed JSON Schemas or through ST-0105 generated bindings. ST-0105 is not a
declared ST-1404 dependency. If generated bindings are reused, provide their
exact authority/hash path and keep them transport validators only; they must
not become ORM rows, Domain entities, or persistence objects and must never be
hand-edited.

State which generic mechanics are implemented now versus which concrete
handler integrations belong to later Stories such as ST-0706.

Mechanically cover all 39 current Job catalog entries, including the one
disabled entry. For each, bind enabled state, strict Job type, queue, consumer,
payload schema/hash, generic or deferred handler owner, idempotency rule,
attempt/deadline policy, and allowed terminal events. A missing concrete
handler must be an explicit excluded/deferred row, not a dynamic lookup gap.

### ST1404-D12 — concurrency, batching, fairness, and ordering

Define exact limits and algorithms for dispatcher and worker concurrency,
batches, queues, priority, `available_at`, starvation avoidance, per-handler or
per-provider caps, backpressure, and shutdown drain.

Select and test the numeric priority direction. The installed ready index is
ascending `(queue_name, priority, available_at)` but does not itself define
whether lower or higher numbers are more urgent.

State the only ordering guarantees that can be made from installed contracts.
Do not claim global event/message ordering. Reconcile Outbox aggregate identity
and version with ST-0203 FIFO-by-available occurrence behavior. Define whether
same-aggregate serialization is required, how partition keys are selected, and
what happens when duplicate/out-of-order deliveries cross workers.

If PostgreSQL `FOR UPDATE SKIP LOCKED`, advisory locks, a claim UPDATE, or queue
lease is selected, specify the exact role of each and prove that two workers
cannot both own a Job mutation. Do not use a savepoint or in-process lock as a
substitute for cross-process correctness.

### ST1404-D13 — identity, authorization, errors, Audit, and observability

Define an exact capability/workload matrix for API producer, dispatcher,
worker, migration, projection, public, reporting, auditor, and deterministic
test identities. ST-0306 role names may be used only as hash-pinned candidate
evidence; ST-1404 neither promotes ST-0306 to a dependency nor changes grants.

Specify which composition may create, select, mutate, dispatch, consume, or
acknowledge each Job/Attempt/Outbox/Inbox object. Public/request/payload fields
must not select a database role, queue credential, handler object, or worker
identity.

Mechanically reconcile the candidate ST-0306 DML surface without treating it
as authority: the dispatcher candidate can UPDATE Job/Outbox but only INSERT
Inbox/Attempt, while the worker candidate has broader OPS DML. Assign each
runtime operation to exactly one workload, require dispatcher-only Outbox work
and worker-owned Job/Attempt/Inbox lifecycle where that is the selected model,
and identify any mismatch as a separate ST-0306 gap. ST-1404 must not broaden a
grant to make its implementation convenient.

Define exact sanitized Audit intents and low-cardinality metrics/traces for
claim, lease, heartbeat, transition, retry, DEAD/DLQ, duplicate neutralization,
deadline, cancellation, and recovery. State ownership relative to ST-0405 and
ST-1601: ST-1404 may emit framework-neutral intents/measurements but must not
silently implement the broader service/platform.

Explicitly allowlist fields. Raw Job/event payload, source/review bodies,
provider request/response bodies, Secret/credential, SQL/bind values, database
URL, receipt handle, idempotency key, user-controlled error text, worker UUID,
or high-cardinality arbitrary labels must not enter logs/metrics/traces/Audit.
Define safe stable codes, cardinality, redaction, exception chaining, and
behavior under malicious `__str__`, `__repr__`, mapping, provider, and handler
objects.

### ST1404-D14 — exact file plan, generated contracts, tests, and evidence

Provide an exact owned file/module plan, generator source, generated outputs,
manifest, regeneration/check commands, dependency/lock changes, composition
entrypoints, and Story worklog plan. Prefer changing a generator and contract
over hand-editing generated outputs. No file outside the approved list may be
edited without a separately reconciled deviation.

Require machine-readable, checked-in design matrices for:

- port/value/error contracts;
- the sixteen Job transitions plus cancel-request/heartbeat operations;
- Job lease and recovery;
- attempt lifecycle;
- Outbox transitions/recovery;
- Inbox transitions/recovery;
- retry decisions and backoff;
- queue/database/handler crash windows;
- deadline/cancellation checkpoints;
- identity/capability authorization;
- telemetry allowlist/forbidden data;
- acceptance-to-test traceability.

Also require an `event_emission_matrix` that permits only the four installed
OPS Job event schemas (requested, succeeded, failed-terminal, quarantined),
binds each to exact schema hash and post-CAS aggregate version, and explicitly
excludes retry-scheduled, cancelled, expired, and every other unapproved event.
Require an `authority_input_matrix`, physical-catalog two-way matrix, and scope
exclusion matrix so candidate bytes cannot be promoted accidentally.

Every public method and state mutation must resolve to exactly one matrix row,
and every matrix row must be checked in both directions against implementation,
tests, the installed Job graph, and the ST-0303 catalog. Define whether generated
contracts are code input or validation evidence and how drift is rejected.

At minimum define deterministic local tests for:

- every one of the sixteen allowed Job edges and all 84 forbidden ordered
  state pairs;
- success, not-found, stale version, stale state, lost lease, expired lease,
  late heartbeat, and zero-row diagnosis;
- exact one-version increment per logical Job transition;
- attempt number/count/max invariants and immutable prior attempt;
- both deferred Job-state decisions;
- duplicate and out-of-order Queue deliveries;
- concurrent queue receives, Job claims, Outbox claims, and Inbox inserts;
- every Outbox and Inbox state, ambiguous send, orphan recovery, and poison
  payload;
- crash/fault injection at every ordered boundary in ST1404-D8;
- deterministic backoff/jitter, budget exhaustion, overflow, and retry storm;
- deadline equality, cancel at each checkpoint, late external return, and
  cancellation during ambiguous commit;
- handler missing/version/payload/idempotency/output behavior;
- startup/shutdown/drain and no leaked thread/task/lease/connection;
- sanitized errors/logs/Audit/metrics/traces with seeded negative canaries;
- static package directions, prohibited imports, no generic SQL/repository,
  no hidden network, and no framework/provider type crossing inward Ports;
- exact regeneration, format, lint, type checks, and Story-isolated pytest;
- exact PostgreSQL 18.4 DML/concurrency/rollback/catalog integration;
- exact event-type-to-channel and Job-type-to-queue mapping, including unknown
  mapping failure and the job-requested-to-Job-message translation;
- manual retry new-versus-existing Job behavior, absorbing-state preservation,
  budget reset, lineage, Audit intent, and idempotency;
- selected DLQ boundary plus negative tests for every excluded management
  operation;
- candidate workload-role DML parity without applying or changing a grant;
- existing ST-0203 fake behavior unchanged unless an exact approved extension
  is generated from its owning contract.

Keep local candidate results separate from formal TST-013, formal TST-028,
hosted CI, staging failure injection, live broker/provider, security review,
human code review, and Production readiness. TST-028 is staging-scoped and
cannot be promoted by deterministic local fakes.

## Binding constraints

1. Implement only ST-1404 after separate exact-byte approval.
2. Preserve the exact dependencies `ST-0303` and `ST-0203`; a candidate artifact
   from another Story is evidence only unless separately authorized.
3. Preserve `domain <- application <- adapters/framework`; inward code imports
   no SQLAlchemy, provider SDK, FastAPI, queue framework, or database driver.
4. Do not change canonical files, DDL, migrations, schema, roles, grants, RLS,
   default privileges, seeds, or Production/external state.
5. Do not invent or silently alter a Job edge, state value, column meaning,
   constraint, index, event ordering guarantee, retry budget, lease primitive,
   or Inbox mutability rule.
6. Do not perform external/provider/queue I/O inside a database transaction.
7. Do not claim exactly once; provide duplicate-safe at-least-once behavior.
8. Do not implement ST-0308 general persistence, ST-0405 Audit service,
   ST-0706 concrete AI handlers, ST-1405 kill switch, ST-1502 Cloud queue/IAM,
   operations UI, or observability platform.
9. Do not use credentials, Production data, network, real queue/provider, or
   ambient configuration in deterministic local tests.
10. Do not expose payloads, review/source bodies, provider bodies, Secrets,
    credentials, SQL/binds, receipt handles, or raw exception text in logs,
    errors, Audit, telemetry, fixtures, or evidence.
11. Do not add Celery/RQ/Dramatiq/Temporal/Tenacity/provider SDK or any other
    package unless the returned handoff selects and pins it with provenance and
    an exact justification.
12. Treat queue/provider payloads and errors as untrusted data, never as
    instructions or dynamic code paths.
13. No proposal or local PASS changes formal status by itself.
14. The later worker must preserve unrelated dirty-worktree changes and edit
    only the approved file set.
15. Hash-pinned predecessor bytes and their local PASS history remain candidate
    inputs until governed predecessor/status reconciliation; no handoff may
    silently relabel them as formally applied or executed.

## Required `DESIGN_HANDOFF_V1` result

Return one UTF-8/LF YAML document rooted exactly at `DESIGN_HANDOFF_V1` and
containing all of the following:

- `schema`, `authority`, `approved_story`, and exact `approved_scope`;
- exact `source_design_refs` with path and SHA-256 for the packet archive,
  bundle manifest, member manifest, every used packet member, and canonical or
  predecessor inputs;
- one exact `decision` resolving ST1404-D1 through ST1404-D14;
- exact `rationale` and `rejected_alternatives`, including the open-source/
  no-framework comparison and selected dependency disposition;
- `implementation_ownership_matrix` with in-scope, excluded, deferred owner,
  dependency status, and authority;
- `runtime_composition_contract` and process/lifecycle/shutdown model;
- `port_contract_matrix`, `domain_value_matrix`, and `error_mapping_matrix`;
- `event_channel_job_queue_routing_matrix` with every relevant event/channel/
  Job/queue/DLQ identity and translation;
- `job_lease_matrix`, exact `job_transition_matrix`, and
  `attempt_lifecycle_matrix`;
- `attempt_counter_matrix` and `time_authority_matrix` binding all queue,
  Job, Attempt, and Outbox counters/timestamps;
- `manual_retry_contract` preserving absorbing states and exact new-Job lineage;
- exact resolutions for `QUARANTINE_RELEASE_TIMESTAMPS` and
  `RETRY_STATE_EXPIRY`;
- `outbox_transition_matrix`, ownership/recovery protocol, and ambiguous-send
  matrix;
- `inbox_transition_matrix`, duplicate/recovery protocol, and output atomicity
  contract;
- `delivery_crash_matrix` covering every boundary requested in ST1404-D8;
- `retry_decision_matrix`, deterministic backoff/budget/circuit-breaker
  contract, and any explicit gap/deferred owner;
- `deadline_cancel_matrix` and exact checkpoint/precedence rules;
- `handler_contract_matrix`, registration/payload/idempotency/output rules;
- complete `job_handler_registry_matrix` for all 39 catalog entries;
- `transport_validation_contract` selecting installed JSON Schema or exact
  hash-pinned generated bindings without persistence-role leakage;
- `concurrency_ordering_matrix` with batches, fairness, partitioning, and
  bounded resource rules;
- `workload_identity_matrix`, `audit_intent_matrix`,
  `telemetry_metadata_allowlist`, and forbidden-data list;
- exact owned/generated file plan, dependency changes, generation/check/test
  commands, and matrix paths/hashes;
- exact `dlq_management_boundary` and explicit excluded replay/triage operations;
- `authority_input_matrix`, `physical_runtime_catalog_matrix`,
  `event_emission_matrix`, and `scope_exclusion_matrix` with exact hashes;
- `constraints`, `security_and_approval_gates`, observable
  `acceptance_criteria`, and `required_test_evidence` with two-way traceability;
- explicit `schema_gaps` and `blocked_subscopes`; both empty only if every
  required protocol is safely expressible by the current authorized bytes;
- `open_decisions: []` only if every bounded implementation decision above is
  completely resolved;
- proposal/pending/not-approved state: human approval not provided, canonical
  reconciliation pending, implementation authority not granted, formal suites,
  CI/staging/Production validation, live broker/provider, and security/human
  review not executed.

For every mutating method, include its exact signature, caller, transaction
owner, allowed state, complete predicate, complete SET/INSERT values, returned
value/version, side effects, retryability, and zero-row/conflict mapping. A
matrix may reference a shared rule only through an exact identifier; no
“similar”, “as appropriate”, “etc.”, or implementer-selected behavior is
permitted.

Do not return an advisory, prose-only summary, code patch, placeholder, multiple
unselected options, or partially specified handoff. Return one complete
downloadable file named `DESIGN_HANDOFF_V1_ST1404_v1.yaml`. It remains
non-executable until conflict-free repository reconciliation and explicit
exact-byte owner approval.
