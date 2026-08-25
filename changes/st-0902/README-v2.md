# ST-0902 V2: gate-bound recorded human final approval

This additive runtime completes the maximum-safe local implementation of the
ST-0902 final-approval domain. It preserves the V1 non-executable reference
plan and binds one immutable Article Version to the exact ST-0605 coverage
report/receipt, ST-0805 policy report/receipt and Finding snapshot, and
ST-0901 completed human `APPROVE` result.

The V2 profile is `ST0902_FINAL_APPROVAL_RECORDED_LOCAL_V2`. It is executable
only in `ENV_DEV` and `CI` with an owner-generated recorded-synthetic fixture.
It performs no network, credential, provider, database, event-bus, public API,
staging, release, publication, or Production operation.

## Human and separation boundary

The application service exposes only `execute(request)`. A caller cannot
supply an actor, role, MFA state, site grant, or step-up claim. The recorded
authorization source supplies a hash-bound identity which is revalidated as:

- an `ACTIVE` `HUMAN` managing editor within the exact site scope;
- recorded-synthetic MFA and step-up state with explicit reauthentication no
  more than 300 seconds before the recorded decision; and
- a principal different from the Article author, last editor, and ST-0901
  reviewer.

There is no solo-editor exception. The security design's step-up requirement
is retained as the fail-closed resolution of the role-matrix conflict. These
checks are deterministic local self-consistency, not real authentication,
durable RBAC evidence, or permission to take an external action.

## Approval gate

The command reconstructs every dependency and refuses final approval unless:

- Article Version ID/number, body hash, canonical AST hash, source packet,
  claim set, methodology, recommendation, and evaluation hashes all agree;
- ST-0605 is `PASS`, both coverage requirements are true, and its report and
  process-local receipt match;
- ST-0805 is `LOCAL_EVALUATED`, every quality/policy gate is explicitly clear,
  and no policy Finding or waiver evaluation exists;
- ST-0901 is completed with the review-level `APPROVE` decision and exact
  policy/Finding/checklist bindings; and
- a complete contemporaneous Finding snapshot contains zero open blocking
  Finding IDs and no waiver.

Any open blocking Finding rejects the request. The runtime has no waiver
interface and does not infer Finding clearance from a count or an absent
field.

## No publication authority

Success creates immutable in-memory hashes for the recorded decision, audit
artifact, and idempotency receipt. It does not create a durable transaction,
write a database, emit an event, create or mutate a publication snapshot, or
authorize real final approval. `publication_snapshot_authorized`,
`publication_authorized`, `release_authorized`, and `production_authorized`
remain false in the contract, fixture, domain result, generated manifest, and
tests.

Formal TST-012/TST-021, hosted CI, live validation, staging, release,
publication, Production, and Canonical registry APPLY remain `NOT_EXECUTED`.

## Determinism and provenance

The owner contract generates a bounded JSON fixture, importable byte constant,
and content-addressed runtime manifest. The fixture loader independently
rebuilds ST-0605, ST-0805, and ST-0901 evidence before accepting the approval
seed. The adapter provides exact replay, refuses same-key changed requests,
and consumes at most one scripted step under a process-local lock. Generation
uses the shared atomic, foreign-preserving publication helper and supports a
no-write `--check` mode.
