# ST-0407 design-authority preflight

Status: `DESK_REVIEW_COMPLETE`  
Authority: `LOCAL_NONCANONICAL_EVIDENCE`  
Implementation authority: `NOT_GRANTED`  
Formal TST-026/TST-031: `NOT_EXECUTED`  
Live Secret provider, database, and CI validation: `NOT_EXECUTED`

## Result

`ST-0407` is dependency-ready but is not sufficiently specified for a safe
implementation. The canonical Story fixes the objective, predecessor, high-level
deliverables, security baseline, and evidence suites. It does not fix the inward
Port contract, Secret-material lifetime, workload-identity proof, provider and
database integration boundaries, rotation state machine, concurrency behavior,
or sanitized failure model. Selecting those details would be new security and
architecture design, so an exact `DESIGN_HANDOFF_V1` is required before an
`implementation_worker` edits production code.

## Canonical facts

| Item | Canonical fact |
| --- | --- |
| Story | `ST-0407` — Secret and workload identity integration |
| Objective | Provider/DB/CI short-lived, separated credentials |
| Exact dependency | `ST-0204` |
| Design reference | `RAOS-SEC-001` |
| Deliverables | Secret Port; rotation hooks |
| Acceptance | No Secret in logs or repository |
| Required suites | `TST-026`, `TST-031` |
| Backlog open decisions | `[]` |
| Canonical status | `APPROVED_FOR_IMPLEMENTATION`; implementation `NOT_STARTED`; verification `NOT_EXECUTED` |

The security baseline additionally requires distinct Worker, CI, Migration,
Projection, and Public Web workload identities; GitHub Actions short-lived OIDC
credentials; no long-lived Cloud key in repository secrets; no RESTRICTED
Secret in Database, Prompt, or Application Log; Secret-access metadata logging;
and a rotation drill. `THR-001`, `THR-005`, `THR-008`, `THR-010`, and `THR-020`
are the directly relevant threat records.

## Verified predecessor checkpoint

The pinned ST-0204 checkpoint provides:

- an immutable `RuntimeConfig` and logical `SecretReference`;
- a bounded `RAOS_SECRET_REFERENCES` map with caller-owned aliases;
- redacted display, serialization, parser, error, and diagnostic behavior;
- no provider SDK, network access, Secret value, workload identity, or rotation
  implementation.

The logical reference intentionally exposes no public clear-text accessor. A
resolver therefore cannot be implemented safely without deciding whether the
inward Port accepts an alias, an opaque reference, or an adapter-only capability
and who is authorized to unwrap it.

Current local read-only verification on 2026-08-06:

- canonical import verification: PASS (104 package checksums, 103 manifest
  entries);
- ST-0204 deterministic generation check: PASS;
- isolated ST-0204 pytest: 178 passed;
- ST-0005 status drift check: PASS;
- ST-0407 effective implementation/verification remains
  `NOT_STARTED` / `NOT_EXECUTED` with no applied request.

These are local candidate facts, not formal TST-026/TST-031 evidence.

## Missing design decisions

| ID | Missing decision | Risk if inferred |
| --- | --- | --- |
| ST0407-D1 | Exact Story cut and ownership relative to ST-1504 GitHub OIDC deployment, ST-0308 database engine/persistence wiring, provider adapters, and infrastructure/IAM stories | Dependency and authority expansion |
| ST0407-D2 | Exact inward Port paths, method signatures, value/lease types, and safe handoff from ST-0204 `SecretReference` | Secret-reference disclosure or framework leakage |
| ST0407-D3 | Secret material encoding, maximum size, lease/expiry, copy and serialization policy, consumer callback/context boundary, and realistic zeroization claims | Long-lived or accidentally retained Secret bytes |
| ST0407-D4 | Workload identity taxonomy, proof source, binding to service/environment/purpose, fail-closed validation, and confused-deputy prevention | Cross-workload credential use |
| ST0407-D5 | Provider selection/routing, official SDK boundary, endpoint/region ownership, authentication source, retry/timeout behavior, and dependency policy | Ambient credentials, SSRF, or unpinned runtime behavior |
| ST0407-D6 | Cache/refresh/rotation state machine, concurrency collapse, expiry and revocation handling, last-known-good policy, hook ordering, failure and rollback rules | Stale credentials or split-brain rotation |
| ST0407-D7 | Database credential and connection-pool rotation boundary without implementing ST-0308 repositories or changing roles/grants | Invalid sessions, connection reuse across identities, or Story overlap |
| ST0407-D8 | CI boundary: what ST-0407 defines versus ST-1504's workflow/IAM trust and environment approval | Privileged PR credentials or duplicated deployment scope |
| ST0407-D9 | Sanitized errors, audit metadata allowlist, metrics, tracing, exception chaining, and provider-response handling | Secret/reference leakage through diagnostics |
| ST0407-D10 | Exact acceptance matrix, fake/recorded adapters, time and concurrency tests, negative canaries, static scans, and formal-evidence boundary | Untestable or overstated security claims |

## Existing implementation shape

- No `changes/st-0407`, `tests/st0407`, ST-0407 worklog, Secret resolver Port,
  workload-identity Port, rotation hook, or Secret-manager adapter existed at
  preflight start.
- The root runtime dependencies contain no AWS, Google, or Azure Secret-manager
  SDK. Adding one and selecting a version is therefore a supply-chain and
  adapter decision, not a mechanical edit.
- Existing inward Ports use framework-neutral `Protocol` definitions and
  sanitized closed errors. Provider types remain in outward adapters.
- The repository has an intentionally dirty multi-Story worktree. A later
  worker must own only the exact ST-0407 paths approved by the handoff and must
  preserve all unrelated changes.

## Scope conflicts that the handoff must prevent

1. ST-0407 must not implement GitHub deployment workflows, IAM trust, or
   Production environment approval owned by ST-1504.
2. ST-0407 must not implement repositories, SQLAlchemy Sessions, database
   grants, roles, RLS, migrations, or Secret resolution inside ST-0308.
3. ST-0407 must not choose a human OIDC provider or close OD-010.
4. ST-0407 must not issue Production Secrets, create Cloud resources, or claim
   a live rotation drill from local fakes.
5. ST-0407 must not make Domain code depend on a provider SDK or expose Secret
   values through configuration, diagnostics, logs, events, evidence, or
   generated artifacts.

## Preflight disposition

Prepare a canonical-pinned Pro request that resolves ST0407-D1 through
ST0407-D10 into one implementation-ready `DESIGN_HANDOFF_V1`. The returned
bytes remain a proposal until conflict-free reconciliation and exact-byte human
approval. Until then, implementation authority remains `NOT_GRANTED`.
