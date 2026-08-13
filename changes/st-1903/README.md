# ST-1903 autonomous-publication policy revision candidate

This Story-owned package serializes one proposed post-MVP policy revision. Its
immutable handoff and contract retain their original internal
`UNAPPROVED_POLICY_REVISION_CANDIDATE` and
`PENDING_OWNER_SHA256_APPROVAL` fields, while a detached exact-byte record now
classifies the package only as an
`OWNER_APPROVED_INERT_POLICY_CANDIDATE_ONLY`. Activation remains disabled. The
approval authorizes no canonical mutation, status promotion, publication,
unpublication, merge, release, provider call, external write, staging, or
production action.

Canonical ST-1903 remains `DEFERRED_POST_MVP` and depends on ST-1805, which is
not implemented or verified. TST-032 is `NOT_EXECUTED`. The candidate conflicts
with the current human-publication boundary in INT-DEC-009, INT-DEC-013, the
integration design, the repository instructions, and the security/step-up
controls. Canonical reconciliation and a separate release decision remain
mandatory. No local artifact can satisfy either gate.

## Authority boundary

- The detached approval record binds the byte-identical 18,189-byte handoff at
  SHA-256
  `f7bda7008d10ecf5e1b980602495e487f694552a15b31ca60ec45eb0c61d810b`.
  It records only owner approval of the inert candidate and grants canonical
  mutation authority `NONE`.
- The owner statement is preserved verbatim as 114 UTF-8 bytes with SHA-256
  `88e64c18e6a0034369468e8ecd26955a6a55f3e08579212259d71e59fed8a35c`.
  The approval was observed at `2026-08-13T14:16:02Z`; its message-authored
  time was not supplied.
- The handoff is the acyclic root approval target. It binds the exact contract
  bytes, contract SHA-256, and order-preserving semantic SHA-256; the contract
  does not point back to the handoff hash. Therefore any policy-source change
  necessarily changes the owner-visible handoff SHA-256.
- The detached record does not rewrite the immutable pending fields in the
  handoff, contract, or generated policy projection. Any future policy revision
  requires a new exact handoff SHA-256 and a new owner decision.
- The generator, optimizer, Codex, Pro, CI, CMS, and publication engine cannot
  approve themselves or one another.
- The prior bounded Pro attempt yielded no usable review. This package records
  only `REVIEW_NOT_OBTAINED`; it includes no prompt, response, browser, or run
  material and does not authorize another attempt.
- `open_decisions: []` in the handoff means only that serialization of this
  candidate has no additional design choice. All inherited canonical Open
  Decisions remain unchanged; fourteen blocking decisions continue to block
  their related Gate or production boundary.

## Exact Git boundary

The candidate is based on commit
`acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d`, tree
`85620e53419b65e3053e4454c6c1cb522de4459b`.

Parallel Wave-3 lineage commit
`6c014bee7004a9f1dfa726686b91f436fc9cd2f7`, tree
`9a1824f948b0bceb416417bfedaf101f1a452ebf`, is bound only as
`REFERENCE_ONLY_PARALLEL_LINEAGE_NOT_MERGED`. No file from that lineage is an
input, dependency, or copied source for this package.

## Candidate scope

If a future owner-approved canonical revision and release boundary permit it,
the proposed deterministic policy would limit unattended publication to
eligible low-risk articles, at most one new article per Asia/Tokyo calendar
day, with no catch-up. Medical, financial, legal, safety, and minors content is
denied before drafting. Pro review is mandatory and outage results queue.
After a separately approved canonical revision and activation, an ordinary
article that satisfies every deterministic gate would not require a separate
per-article owner approval. Owner review remains an exception for ambiguous
risk, owner-gated code changes, root-policy revisions, credentials, and new
external-cost decisions; it is not the normal article path.

Evidence, user fit, quality, and safety determine eligibility first. A
separately decomposed and disclosed commercial component may contribute at
most ten percent only after eligibility, and estimated contribution profit
remains non-confirmed. This commercial proposal conflicts with the current
canonical prohibition on economics as a recommendation input and is therefore
inert unless canonical authority is explicitly revised.

Only an official Rakuten API `affiliateUrl` may be used, directly. Hand-built
affiliate URLs and RAOS redirects are forbidden. Stale or invalid calls to
action are disabled. Ambiguous WordPress writes stop for reconciliation and
must never be blindly replayed; duplicate prevention is mandatory. Critical
evidence or policy defects may eventually cause deterministic safety
contraction, but this candidate grants no current unpublish authority.

The candidate also describes a separate low-risk code auto-merge boundary:
terminal CI, an independent Codex review, Pro review, rollback readiness, and
closed change classification are mandatory. Secrets, permissions, databases,
canonical files, publication behavior, and release-policy changes always stay
owner-gated. None of that automation is implemented here.

## Owned files

Owner sources:

- `README.md`
- `DESIGN_HANDOFF_V1_ST1903_AUTONOMOUS_PUBLICATION_POLICY_V1.yaml`
- `DESIGN-HANDOFF-APPROVAL-AUTONOMOUS-PUBLICATION-POLICY-v1.yaml`
- `contracts/autonomous-publication-policy.v1.yaml`
- `../../scripts/build_st1903_autonomous_publication_policy.py`
- `../../tests/st1903/conftest.py`
- `../../tests/st1903/test_contract.py`
- `../../tests/st1903/test_generation.py`
- `../../tests/st1903/test_negative_cases.py`
- `../../tests/st1903/test_approval.py`

Generator-owned files:

- `generated/autonomous-publication-policy.v1.json`
- `manifest.yaml`

Generated files must not be hand-edited. The generator accepts no arguments or
the exact `--check` option, uses no network, environment-derived policy input,
clock, random source, credential, or provider, and installs its two outputs as
one rollback-protected staged unit.

## Local generation and verification

Use the already hydrated pinned repository Python; do not install or
synchronize from an isolated worktree:

```bash
PYTHON=/home/minami/rakuten/.venv/bin/python

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" \
  scripts/build_st1903_autonomous_publication_policy.py

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" \
  scripts/build_st1903_autonomous_publication_policy.py --check

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PYTHON" -m pytest \
  -p no:cacheprovider -q tests/st1903
```

Passing local checks will show only deterministic candidate consistency. It
will not execute TST-032 or establish formal CI, live-provider, browser,
staging, release, publication, or production evidence.
