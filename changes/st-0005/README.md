# ST-0005 status registry workflow

This bundle adds a hash-pinned operational overlay and strict transition
validator without editing the immutable RAOS v1.0 canonical package. The
canonical Registry, Story catalog, Test catalog, and taxonomy remain the
effective base. The validator declares the complete structural transition
grammar and can replay structurally valid committed non-deployment `APPLY`
history. Implementation transitions into or out of a deployed status remain
blocked pending typed deployment gates, and every newly added authoritative
live `APPLY` remains fail-closed pending the deferred governance prerequisites
below. Verification-only regression or expiry while implementation remains
deployed is still part of the offline replay model.

## Build and validation

Run from the repository root:

```bash
python3 scripts/build_st0005_status.py
python3 scripts/build_st0005_status.py --check
python3 scripts/build_st0005_status.py \
  --validate-request changes/st-0005/requests/0001-st-0001.yaml
```

The builder first verifies the complete ST-0001 imported file set and hashes.
It then pins the canonical Registry, Story catalog, Test catalog, and Status
Taxonomy, validates every request, renders in sibling staging, and replaces
only its owned generated files. A generation or install failure preserves the
previous complete generated tree. `--check` compares a clean generation
byte-for-byte with the committed bundle.

## Ownership

Source-owned files are the generator, this README, append-only request and
evidence YAML files, ST-0005 tests and documentation, and the narrow GitHub
workflow. Test-only snapshot fixtures are also source-owned and manifest
hashed. Generated files must not be edited directly:

- `contracts/status-transition-request.schema.json`;
- `contracts/status-policy.v1.yaml`;
- `status-overlay.v1.yaml`;
- `manifest.yaml`.

The generated manifest records exact byte lengths and SHA-256 values for every
source and generated payload artifact. It deliberately excludes
`manifest.yaml` from its own generated-artifact inventory to avoid recursive
self-hashing; `--check` verifies that file by deterministic byte-for-byte
regeneration instead. The owned-tree check rejects partial output, foreign
ownership, symlinks, unlisted files, missing files, and hash drift.
After the initial introduction, an existing `requests/*.yaml` or
`evidence/*.yaml` file may not be modified, deleted, or renamed. A correction
is a new evidence snapshot plus a new request. This modify/delete/rename
enforcement belongs to the base-owned PR workflow; the PR check rejects
history changes other than file additions.

## Effective status and proposals

The overlay preserves every canonical source row: 129 Stories, 32 Test Suites,
and six environments. Every row carries a SHA-256 of its complete immutable
base record. Missing, duplicated, unknown, or mutated source rows fail
generation. Proposal metadata may be appended, but effective Story status
fields change only through a validated `APPLY`.

The five bootstrap request files and any later local implementation records are
append-only `PROPOSE` requests. A `PROPOSE` never changes effective status and
must not contain PR, approval, production, or scope governance fields. They reference
append-only evidence snapshots rather than using mutable work logs or
generator sources as the request evidence object. Each snapshot is bound to
its Story, evidence class, Suite, environment, result, recorded time, and
formal status. Replay verifies immutable content-addressed captures. When a
snapshot is newly introduced in a live PR, each capture must also match its
declared repository-local, regular-file original; later offline replay does
not depend on that mutable original. Orphan snapshots and captures are
rejected. The bootstrap proposals record local implementation evidence for
ST-0001 through ST-0005; later Story proposals use the same append-only
contract. They propose `IMPLEMENTED_NOT_VALIDATED / NOT_EXECUTED` and do not
change effective canonical status. There is no real Git repository, pull
request, CI run, or human approval in this workspace, so every proposed Story
retains its canonical effective status and remains pending.

Each request changes exactly one Story. The offline `APPLY` model requires a
request to match both the pinned canonical
base digest and the current effective-state digest, match each row's expected
status, contain hash-verifiable append-only evidence for the required Suites,
identify a concrete GitHub pull request and a prior implementation commit, and
include approval by a distinct human. Each PR URI, PR changeset identity, and
immutable approval artifact is globally single-use for `APPLY`; a different
Story or outer approval label cannot reuse those identities. Production
governance identities include Story, governance role, and artifact SHA-256;
scope identities include Story and artifact SHA-256. Those production and
scope artifacts may therefore be reused by a genuine cross-Story batch
decision. `requested_at`, evidence
`observed_at` and
optional `expires_at`, and approval `decided_at` are explicit strict-UTC
RFC3339 values. Explicit nulls, malformed timestamps, change/PR/scope evidence
that postdates its request, approval/production evidence that postdates its
decision, evidence expired when approval takes effect, and other misordering
fail. Explicit-null temporal and governance values also fail. Historical
offline replay is deliberately independent of the current wall clock; live
validation additionally rejects wall-clock-future request, observation, and
decision timestamps and evidence expired at the live reference time. A future
`expires_at` boundary is valid and expected while the evidence is still fresh.
Every later status-changing observation
must strictly postdate both the active evidence it supersedes and the latest
applied approval decision for that Story. An expiry observation may equal, but
cannot precede, the captured `valid_until`. Each source-capture digest names
exactly one file, and evidence identity is computed per
Story/Suite/class/capture tuple and is single-use for `APPLY`, so a superset
capture cannot masquerade as the same evidence. `EXPIRY` must invalidate the
exact active evidence set, and both its request and observation must be at or
after the active `valid_until` boundary.
`VALIDATED` and `DEPLOYED_PRODUCTION` additionally require a human requester;
verification `PASS` is coupled to `VALIDATED` or a deployed state. Structurally
adjacent forward pairs and explicit adjacent demotion pairs define the
implementation grammar, subject to the deployment execution block above. A
verification-only transition changes the verification fact without changing
an already validated/deployed implementation.
A demotion that preserves verification requires a rollback
decision, `PASS` to `PARTIAL`/`FAIL` requires regression evidence, and an
ordinary verification reset to `NOT_EXECUTED` requires expiry evidence. A
scope exit instead resets to `NOT_EXECUTED` under its scope decision. None can
erase append-only history. These checks define the transition contract; they
do not activate a new live `APPLY` in this revision.

`PARTIAL`, `FAIL`, regression, expiry, and demotion use a nonempty subset of
required Suites so one detected failure cannot be masked while waiting for
unrelated evidence. `PASS` and forward `VALIDATED` require the exact complete
required-Suite set. Production promotion additionally requires exactly four
distinct governance artifacts: release decision, Gate report, security
approval, and operations approval. `DEFERRED_POST_MVP` activation and
entry/exit from `OUT_OF_SCOPE` require a human requester, PR, distinct human
approver, and a separate scope-authority artifact. The scope artifact cannot
alias the request's approval artifact, although one genuine scope decision may
govern multiple Stories; `OUT_OF_SCOPE` is coupled to `NOT_APPLICABLE`.

Local evidence uses the operational `LOCAL` label. It is deliberately not a
canonical Test environment and can never produce formal `PASS` or
`VALIDATED`.

## PR-check strategy and deferred boundary

`.github/workflows/status-registry.yml` is intentionally limited to the
importer verification, generated drift check, and strict request validation.
It uses the base-owned `pull_request_target` workflow, pins the checkout action
to a full commit, fetches history, and checks out the exact PR head. A
shell-only guard rejects any status-history change combined with a validator,
workflow, import-boundary, or immutable-source change. The complete `scripts/`
tree is then restored from the exact base SHA before the first isolated Python
process, so candidate-head Python is never imported or executed. Candidate
head data remains available for deterministic offline replay. Historical
requests are replayed offline. Only each newly added request is bound to live
PR context; an `APPLY` PR may add exactly one request file, then is rejected by
the authoritative activation gate. Existing request/evidence mutation,
deletion, or rename is rejected. This is intentional: `ST-0006` must add
open-decision gating and `ST-0107` must add authenticated review/ruleset
governance before live `APPLY` can be enabled.
Deployment transitions additionally require `ST-1505`, `ST-1506`, and
`ST-1607`. The workflow does not install a toolchain,
create a broad base CI, enforce CODEOWNERS, create a Gate pack, or publish an
artifact. Python/PyYAML availability remains a prerequisite until ST-0102 and
ST-0106 install the pinned toolchain and base CI. PR governance belongs to
ST-0107, open-decision gates to ST-0006, and release Gate packs to ST-1607.

After those prerequisites are integrated, an executable `APPLY` uses two
commits in one PR to avoid SHA self-reference:

1. commit A contains the implementation;
2. after the PR URI exists, commit B adds the evidence snapshot, transition
   request, and regenerated overlay;
3. `pr_evidence.implementation_commit_sha` names A, while the workflow proves
   A is an ancestor of the checked-out B/current head. It never requires a
   request to contain the SHA of the commit that contains that request.

The workflow definition was not run against GitHub in this workspace. Formal
TST-001 and the canonical CI environment remain `NOT_EXECUTED` and
`NOT_CONFIGURED` respectively.
