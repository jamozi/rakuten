# ST-1204 recorded-fixture publication DESIGN_HANDOFF_V1 request

Status: `PROPOSAL_REQUEST_ONLY`  
Authority: `UNAPPROVED_PROPOSAL_INPUT`  
Implementation authority: `NOT_GRANTED`  
Human approval: `NOT_PROVIDED`  
Canonical reconciliation: `PENDING`  
Formal TST-030: `NOT_EXECUTED`  
Live provider validation: `NOT_EXECUTED`  
Staging readiness: `NOT_READY`  
Production readiness: `NOT_READY`

## Task

Produce one complete, self-contained `DESIGN_HANDOFF_V1` proposal for the
bounded recorded-fixture publication hardening of the single canonical Story
`ST-1204`. Resolve only `ST1204-FIXTURE-D1` through
`ST1204-FIXTURE-D3`. Do not implement the GA4 adapter/job, call Google, use a
credential, close OD-012 or OD-015, change a database, or broaden the Story.

The exact returned bytes remain unapproved until they are reconciled with
canonical precedence and explicitly approved by the repository owner. This
request, its archive, the current checkpoint, and the candidate designs below
are evidence for review, not implementation authority.

## Canonical scope and safe boundary

- Story: `ST-1204`
- Objective: import GA4 aggregate facts
- Exact dependencies: `ST-0305`, `ST-0204`
- Requirement: `FR-013`
- Canonical deliverable: adapter/job
- Canonical acceptance criterion: property/config snapshot
- Required suite: `TST-030`
- Open decisions: `OD-012`, `OD-015`
- `OD-012` safe default: optional tracking disabled and only minimal
  first-party events
- `OD-015` safe default: recorded fixtures only

The existing local checkpoint deliberately stops at deterministic synthetic
recorded fixtures and their validator/generator. It implements no Domain Port,
provider adapter, job, persistence, event, network, credential, consent
decision, formal TST evidence, or production behavior. Preserve that boundary.

## Reconciliation baseline

The current candidate checkpoint has:

- source contract
  `changes/st-1204/contracts/ga4-recorded-fixtures.v1.yaml`, SHA-256
  `79d6a335cc0fbacda37b403d60d93c59d1004bf76caa299e94cee8f287166e43`;
- generator `scripts/build_st1204_ga4_recorded_adapter.py`, SHA-256
  `21d7f0ed30935158b60b905b71fc9ffcb43efe41692134be4dcadd9fa188fe96`;
- manifest `changes/st-1204/manifest.json`, SHA-256
  `16d2439bcb097cb45680124a37951711d8b44a5c545b6607bb3345ac34769036`;
- three synthetic fixtures named `baseline.json`, `late-revised.json`, and
  `provider-error-429.json`;
- 63 local isolated tests passing before the independent publication audit.

Provider/schema/provenance/allowlist semantics passed the independent audit.
The single unresolved audit finding is local filesystem publication safety:

1. write-side ancestor checks use full paths before `mkstemp`, `os.replace`,
   and directory open, leaving a same-UID ancestor-swap TOCTOU window; and
2. three fixtures plus the manifest are replaced sequentially, so an injected
   failure or process crash may leave a mixed old/new bundle.

This is not formal TST-030 evidence. The current checkpoint remains a local
candidate, and the audit result is `FAIL` until the publication issue is fixed
and independently re-audited.

## Decisions to resolve

### ST1204-FIXTURE-D1 - authoritative generated artifact layout

Select one exact layout that makes the closed fixture set and its manifest one
coherent publication unit.

Candidate A (recommended for review):

```text
changes/st-1204/generated/
  manifest.json
  fixtures/recorded/baseline.json
  fixtures/recorded/late-revised.json
  fixtures/recorded/provider-error-429.json
```

`contracts/ga4-recorded-fixtures.v1.yaml` remains outside the generated tree
as the hand-maintained source. The generator stages a sibling tree under the
descriptor-opened `changes/st-1204` directory, fsyncs and verifies it, and
publishes the single `generated` namespace entry atomically.

Candidate B: preserve all four current public paths and add a durable
multi-file journal plus mandatory reader locking/recovery. This does not give
uncooperative readers a one-namespace old-or-new view and therefore requires
an explicit explanation of why that weaker observation model is acceptable.

Candidate C: replace the four files with one canonical JSON bundle. This is a
larger consumer/contract change and requires an exact embedded-fixture schema
and migration rule.

The handoff must select exactly one option, define every authoritative path,
state whether hidden staging/journal entries are permitted, define the
closed-inventory rule, and give the old-layout migration/disposition rule.
It must not silently preserve duplicate authoritative copies.

### ST1204-FIXTURE-D2 - publication, locking, rollback, and crash semantics

For the selected layout, define exact behavior for:

- physical repository-root and ancestor validation;
- descriptor-relative traversal and `O_NOFOLLOW` requirements;
- shared `--check` versus exclusive generate locking;
- same-UID concurrent generator/check behavior;
- durable file and directory fsync ordering;
- fresh installation;
- replacement of an existing nonempty bundle;
- Linux `renameat2(RENAME_EXCHANGE)` availability and fail-closed behavior;
- fault before staging, during any staged write, after staging, immediately
  before publication, immediately after publication, during verification, and
  during old-tree cleanup;
- reverse-exchange rollback and preservation of the primary exception;
- process crash or power loss before and after the namespace operation;
- stale stage or journal detection, automatic recovery versus explicit
  recovery-required state, and evidence retained after rollback failure;
- whether a successfully published new bundle may remain authoritative when
  only old-tree cleanup fails.

Candidate implementation precedent is limited to existing repository code:

- ST-0104: pinned directory identity, durable single staged tree, exact
  pre/post validation, `RENAME_EXCHANGE`, reverse-exchange rollback;
- ST-0105: descriptor-relative managed paths, shared/exclusive `flock`, exact
  tree scanning, durable transaction journal, crash recovery, and terminal
  cleanup.

The handoff must choose the smallest sufficient subset. Do not require a
weaker full-path tempfile path, a non-atomic replacement of a nonempty
directory, a symlink indirection, an external daemon, or a new dependency.

### ST1204-FIXTURE-D3 - exact verification and evidence boundary

Define the acceptance and tests needed before the local audit can change from
`FAIL` to `PASS`:

- successful fresh install and replacement expose one exact complete tree;
- missing, extra, symlink, special, and multiply linked outputs fail closed;
- an ancestor or final-entry swap cannot redirect a write outside the captured
  repository/story directory;
- mid-stage and pre-publication failures leave the installed bundle unchanged;
- post-publication injected failure either reverses atomically to the exact old
  tree or leaves an explicitly committed exact new tree under the approved
  cleanup-failure rule;
- no observable/check-accepted mixed old/new tree exists;
- concurrent generate/check operations follow the selected lock contract;
- stale stage/journal and rollback-failure paths have deterministic tests;
- `--check` is byte-for-byte read-only;
- generator capability tests allow only the exact filesystem/`fcntl`/minimal
  `ctypes` surface needed for the selected design;
- deterministic regeneration, Ruff format/lint, isolated ST-1204 pytest, and
  an independent read-only security audit pass.

Local passing results remain local candidate evidence only. `TST-030`, live
Google validation, CI, staging, privacy approval, human code review, and
production readiness remain separate and unexecuted.

## Binding constraints

1. Keep the change inside ST-1204 and the recorded-fixture checkpoint.
2. Change no canonical/upstream/ZIP bytes, dependency lock, database schema,
   migration, grant, Domain, Port, job, event, status overlay, or provider code.
3. Use existing standard-library and repository patterns; add no dependency.
4. Preserve exact synthetic fixture semantics and all current provider/schema
   validation behavior.
5. Do not access network, credentials, environment-provided secrets, Google
   SDKs, subprocesses, database, object storage, queue, or external state.
6. Never follow a symlink or overwrite an unowned/special/multiply linked
   destination.
7. Generated files identify their source and generation/check commands.
8. Do not delete the legacy generated outputs until the new authoritative
   layout has been generated and byte-verified under the approved migration
   rule.
9. `OD-012` and `OD-015` remain unresolved external decisions; recorded-only
   safe defaults do not close them.
10. Do not claim implementation, formal test, staging, live, or production
    authority from this proposal.

## Required `DESIGN_HANDOFF_V1` result

Return one UTF-8/LF YAML document rooted exactly at `DESIGN_HANDOFF_V1` with:

- `approved_story: ST-1204`;
- an `approved_scope` limited to recorded-fixture publication hardening;
- exact `source_design_refs` paths and SHA-256 values from the attached packet;
- one exact `decision` covering `ST1204-FIXTURE-D1` through
  `ST1204-FIXTURE-D3`;
- an exact `rationale` and exact `rejected_alternatives`;
- exact authoritative paths and legacy-path disposition;
- exact publication state machine, lock ownership, fsync order, rollback,
  crash recovery, cleanup, and error rules;
- exact allowed imports/system capabilities;
- `constraints` and `security_and_approval_gates`;
- observable `acceptance_criteria` and `required_test_evidence`;
- `deferred_external_decisions` containing OD-012 and OD-015 unchanged;
- `open_decisions: []` only if all three bounded fixture-publication decisions
  are fully resolved;
- proposal/pending/not-approved status fields, with implementation authority
  not granted and all formal/live/staging/production evidence unexecuted.

Do not return an advisory summary, prose-only answer, code patch, or partially
specified handoff. The result must be one complete downloadable file named
`DESIGN_HANDOFF_V1_ST1204_FIXTURE_v1.yaml`. It still requires exact-byte
canonical reconciliation and explicit repository-owner approval before an
`implementation_worker` may edit.
