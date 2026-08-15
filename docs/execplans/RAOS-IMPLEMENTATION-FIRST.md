# Standing ExecPlan: RAOS implementation-first completion waves

## Standing authorization and objective

- Status: `ACTIVE_UNDER_STANDING_DEVELOPMENT_AUTHORIZATION`
- Authority source: root `AGENTS.md`. Reversible repository development and the
  normal GitHub development workflow do not require per-Story, per-slice,
  handoff, exact-hash, patch, head, or commit approval.
- Objective: finish every locally implementable RAOS capability in canonical
  dependency order, defer non-hard audit and provenance closure while source is
  moving, then perform one exhaustive local integration, review, and test phase.
- Integration owner: the root Codex agent operating `/home/minami/rakuten`.
- Implementation role: a fresh project `implementation_worker` after this
  ExecPlan and worker configuration are committed.

This standing authorization changes implementation sequencing, not product truth. It does
not alter canonical requirements, resolve an Open Decision, approve a provider
account or price, authorize a credential, apply infrastructure, publish
content, merge a release, or make a production write.

## Fixed planning snapshot

- Planning branch at approval: `codex/st-0703-recorded-v4`.
- Approval checkpoint: `4e0a75f658c08a8d124255b522d23e59ac457163`.
- Canonical backlog: 129 Stories.
- Append-only local evidence: 27 unique Stories.
- Remaining implementation queue: 102 Stories.
- The counts are planning inputs only. Effective canonical implementation and
  verification status remain unchanged until the normal status workflow is
  applied.

Before resuming after any compaction or external edit, recalculate the live
branch, status overlay, evidence inventory, dependency graph, and dirty paths.
Do not redo a capability already present and still consistent with canonical
requirements merely because its effective status is `NOT_STARTED`.

## Operating contract

### Implementation phase

1. Select only dependency-ready Stories from the current Wave.
2. Implement one coherent Story or cross-Story mechanical slice per commit.
3. Prefer existing ports, adapters, generators, wrappers, schemas, fixtures,
   and test patterns.
4. For unresolved Open Decisions, implement the provider-neutral interface,
   disabled feature flag, fake/recorded adapter, synthetic fixture, validation
   boundary, and documented safe default. Do not invent the missing real value.
5. Run the fast checks required below. Record any non-hard failure in the
   deferred-verification ledger and continue with dependency-independent work.
6. Push recoverable checkpoints to the dedicated implementation branch. Merge
   only after the root `AGENTS.md` scope, exact-head, local-check, and terminal
   CI conditions are met. Do not publish, release, deploy, or apply
   infrastructure.

### Fast checks required for every slice

- parse/import/compile or equivalent for every changed source language;
- focused unit tests for the changed behavior and its critical negative path;
- directly owned generator check when its source set is stable enough to run;
- sensitive-data/static boundary check when auth, provider, upload, public,
  finance, or security code changes;
- `git diff --check` and a scoped ownership/diff review;
- an explicit record of skipped affected, aggregate, formal, live, staging,
  release, and production checks.

A focused check failure in changed runtime behavior must be fixed before the
slice is committed. A failure caused only by known transitive source hashes,
an unrelated affected suite, deferred environment capability, or a later
owner-generation wave may be recorded and deferred.

### Deferred during active implementation

- exhaustive cross-Story review;
- full affected-suite and repository-wide regression;
- transitive owner-manifest and provenance regeneration while sources move;
- append-only local-evidence and status-overlay closure;
- formal CI/TST evidence;
- live providers, credentials, runtime environments, staging, release, and
  production.

Generated output is never hand-edited. If it becomes stale during active
implementation, record the exact owner, generator, affected paths, and closure
Wave. Regenerate only after the relevant source set is frozen.

### Hard stops

Stop local implementation only when progress would require one of these:

1. reading, exposing, committing, or inventing a Secret, credential, personal
   data, production data, raw prompt, or prohibited provider material;
2. an external provider or user-facing write outside the authorized GitHub
   development workflow, publication, live-provider request, staging action,
   release, production action, or infrastructure apply;
3. an irreversible/destructive migration, deletion, or data transformation
   being applied; reversible local migration code, rollback logic, fixtures,
   and recovery tests remain authorized;
4. weakening authentication, authorization, Canonical publication approval,
   public/internal isolation, editorial/finance separation, disclosure, kill
   switch, or another Canonical safety boundary;
5. choosing a real Open Decision value when no safe interface-only or disabled
   implementation exists;
6. an active file-ownership collision that cannot be isolated without
   discarding another worker's changes.

Ordinary ambiguity, an unlisted but reversible local file, manifest hash
fan-out, a non-formal affected-suite failure, or missing advisory Pro output is
not a hard stop. Follow the closest established repository pattern, record the
assumption/debt, and continue.

## Git and concurrency rules

- The root agent is the only integration owner.
- Use one shared-worktree writer at a time. Parallel agents are read-only unless
  the root has verified isolated worktrees and disjoint ownership.
- Inspect `git status` before every patch and stage only owned paths.
- Preserve unrelated user or external-Codex changes. Never clean, reset,
  checkout, delete, or stage them.
- Keep commits bisectable and identify the Story or integration-debt IDs.
- Checkpoint/push at least every ten completed Story slices or at a macro-Wave
  boundary, whichever happens first.

## Macro-Wave queue

Within each Wave, compute the dependency-ready queue from the live canonical
backlog. The order below is a complete planning partition of the 102 remaining
Stories at the approval snapshot; it is not permission to violate dependencies.

### W0 — preserve and finish the current candidate

- Finish `ST-0703` local implementation.
- Record the ST-0102 direct-runtime-pin and ST-0301+ provenance fan-out as
  deferred integration debt instead of blocking adapter completion.
- Preserve the unrelated concurrent ST-0101 Pro-runtime work.

### W1 — platform, identity, runtime, infrastructure definitions

`ST-0308`, `ST-0401`, `ST-0402`, `ST-0404`, `ST-0407`, `ST-0703`,
`ST-0704`, `ST-1101`, `ST-1404`, `ST-1501`, `ST-1502`, `ST-1503`,
`ST-1504`, `ST-1505`, `ST-1506`, `ST-1601`, `ST-1603`, `ST-1606`,
`ST-1701`.

Open-Decision and infrastructure Stories remain disabled/synthetic where the
canonical decision, credential, account, region, cost, retention, or external
owner input is absent.

### W2 — core repositories, intake, evidence, provider facts, analytics inputs

`ST-0403`, `ST-0405`, `ST-0406`, `ST-0501`, `ST-0502`, `ST-0503`,
`ST-0504`, `ST-0505`, `ST-0506`, `ST-0601`, `ST-0602`, `ST-0603`,
`ST-0604`, `ST-0605`, `ST-0702`, `ST-0802`, `ST-0808`, `ST-1201`,
`ST-1203`, `ST-1204`, `ST-1205`, `ST-1301`, `ST-1302`, `ST-1602`,
`ST-1604`.

### W3 — AI orchestration, editorial logic, workspaces, freshness

`ST-0606`, `ST-0705`, `ST-0706`, `ST-0707`, `ST-0708`, `ST-0709`,
`ST-0803`, `ST-0804`, `ST-0805`, `ST-0806`, `ST-0807`, `ST-0901`,
`ST-1102`, `ST-1103`, `ST-1401`, `ST-1403`, `ST-1407`, `ST-1702`.

Live AI evaluation stays bounded and disabled unless its existing provider,
credential, account-control, and cost decisions are separately satisfied.

### W4 — approval, publication, public application, resilience

`ST-0902`, `ST-0903`, `ST-0904`, `ST-0905`, `ST-0906`, `ST-1001`,
`ST-1002`, `ST-1003`, `ST-1004`, `ST-1005`, `ST-1006`, `ST-1007`,
`ST-1202`, `ST-1402`, `ST-1405`, `ST-1406`, `ST-1605`.

All publish, unpublish, rollback, identity, domain, consent, and public
activation paths remain locally simulated and default-disabled. No content is
published by this ExecPlan.

### W5 — economics, gate packs, pilot and scale decision code

`ST-1104`, `ST-1105`, `ST-1303`, `ST-1304`, `ST-1305`, `ST-1607`,
`ST-1703`, `ST-1704`, `ST-1705`, `ST-1801`, `ST-1802`, `ST-1803`,
`ST-1804`, `ST-1805`.

Pilot/article/revenue/decision Stories use synthetic or recorded fixtures.
They must not claim a real pilot, observation period, economics result, human
sign-off, or scale decision.

### W6 — post-MVP code behind disabled scope gates

`ST-1206`, `ST-1901`, `ST-1902`, `ST-1903`, `ST-1904`, `ST-1905`,
`ST-1906`, `ST-1907`, `ST-1908`.

This Wave may implement contracts, provider-neutral ports, recorded fixtures,
evaluation harnesses, and disabled feature flags. It does not by itself change
their canonical `DEFERRED_POST_MVP` status, activate an advanced provider,
train a model, automate publication, add a category, or make a release
decision.

## Wave checkpoints and final audit

At each macro-Wave boundary:

1. freeze the Wave source set;
2. snapshot and classify the deferred ledger;
3. run owner generators in topological order where feasible;
4. run focused and affected suites once;
5. fix runtime/contract failures introduced by the Wave;
6. carry only explicitly classified non-hard debt forward;
7. commit and push a recoverable checkpoint;
8. continue automatically to the next Wave without requesting routine user
   confirmation.

After W6 code completion, enter a dedicated audit/fix phase and do not add new
features. Rebuild the source-to-owner dependency graph, regenerate every
affected owner artifact in topological order, close introduced provenance
debt, run canonical import/workspace checks, isolated Story suites, aggregate
static/type/security checks, migration/database tests where locally available,
UI/accessibility tests where locally available, and an independent code and
security review. Iterate fixes until all locally executable mandatory gates are
green or a true hard stop is reached.

## Completion boundary

The Goal may report `LOCAL_CODE_COMPLETE` only when all 102 queued Stories have
either a local implementation or the maximum safe disabled/interface-only
implementation allowed by unresolved external decisions.

The Goal may report `LOCAL_INTEGRATION_COMPLETE` only when all introduced debt
is closed, every generated artifact is reproducible by its owner, all locally
executable mandatory tests pass, the final diff is reviewed, and no unrelated
worktree change is included.

Formal CI/TST, live provider validation, real pilot evidence, staging, human
business/security/release approvals, publication, deployment, and production
remain separately `NOT_EXECUTED` until they actually occur. Their absence does
not erase local implementation progress, but the Goal must not call the system
production-ready.
