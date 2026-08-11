# ST-1701 non-authoritative MVP business-input decision package

This Story-owned package records the repository owner's selected MVP business
inputs without changing canonical Open Decision status. The completed source
contract preserves its internal `PENDING_EXACT_REPOSITORY_OWNER_APPROVAL`
proposal field, while the detached exact-hash approval is effective. The result
is an owner-approved `NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE` with authority
limited to `OWNER_APPROVED_CANONICAL_REVISION_EVIDENCE_CANDIDATE_ONLY`; it is
still `NOT_READY` and is not a canonical resolution record.

The existing unresolved registry remains active and byte-preserved. Canonical
ST-1701 acceptance is still not achieved, ST-0006 still reports fourteen
global unresolved blockers and six blocked targets, GATE-0 through GATE-4 stay
blocked, ST-1702 stays unready, and formal TST-032 remains `NOT_EXECUTED`.

The separately approved Gold Evidence handoff currently reaches only its
fail-closed preapproval interface boundary. The deterministic result is
`EVIDENCE_INSUFFICIENT` / `STOP_EVIDENCE_INSUFFICIENT`: the current official
ranking snapshot was accessible for ranks 1 through 20, but the required
same-snapshot ranks 21 through 50 were not available through the authorized
ordinary public route. No complete ledger, Domain Editor approval, resolution
candidate, or canonical-revision bundle exists. Current Gold evidence
authority is `NONE`; the handoff's owner-reviewed evidence-candidate authority
is only a maximum reachable after a valid exact-ledger Domain Editor approval.

## Implementation authority and preflight

- Story: `ST-1701` only, in `STRICT_STORY` mode.
- Dependency read: canonical ST-0006 plus its owner generator, decision-gate
  policy, blocker report, and current generated truth.
- Canonical inputs read: integration precedence and boundaries, Canonical and
  Open Decisions, ST-1701 and ST-1702 backlog rows, TST-032, the security
  control catalog, and the canonical Codex implementation rules.
- Approved handoff:
  `DESIGN_HANDOFF_V1_ST1701_MVP_DECISION_PACKAGE_v1.yaml`, 20,695 bytes,
  SHA-256
  `f5e8f70b74fd26c68b0dfd8a47dd35fc59b1651e9e553dad738d90b00acd1790`.
- Detached handoff approval: `DESIGN-HANDOFF-APPROVAL-v1.yaml`, 1,478 bytes,
  SHA-256
  `8a9029410bdad475eca2da7d0ab0f87cf0d3e1a8019e6102522d7cb18ac3dbd0`,
  status `APPROVED_FOR_IMPLEMENTATION`, authority
  `ST1701_MVP_DECISION_PACKAGE_V1_ONLY`, and `open_decisions: []`.
- Immutable final source package:
  `contracts/mvp-business-decision-package.v1.yaml`, 10,678 bytes, SHA-256
  `7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f`.
- Detached final-package approval:
  `MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml`, 2,098 bytes, SHA-256
  `749a9296837c58ea25a5a3e4a57b0aefd2dc41e94a0b5b34871ddce353d95c34`,
  status `APPROVED_AS_NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE`, authority
  `OWNER_APPROVED_CANONICAL_REVISION_EVIDENCE_CANDIDATE_ONLY`, and
  `open_decisions: []`.
- Approved Gold Evidence and proposal-only canonical-revision handoff:
  `DESIGN_HANDOFF_V1_ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_v1.yaml`,
  26,483 bytes, SHA-256
  `c45bea63891448be4af4d696d7d164ea37f246b76f5acce91de791638f49c17f`.
- Detached Gold handoff approval:
  `DESIGN-HANDOFF-APPROVAL-GOLD-EVIDENCE-v1.yaml`, 1,876 bytes, SHA-256
  `288e96b9e4814e1a3d9409addcee2bf1b5bdf12ab9e0a8e756ec66846f057197`,
  status `APPROVED_FOR_IMPLEMENTATION`, authority
  `ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_V1_ONLY`, and
  `open_decisions: []`.
- The ten source hashes and byte counts listed by the approved handoff were
  verified before implementation edits. The handoff and detached approval are
  immutable authority inputs and are not generated or normalized here.
- The thirteen preimplementation source rows in the approved Gold handoff were
  likewise verified before this slice. The historical README and generator
  hashes in that handoff are provenance anchors, while the manifest records
  their current generated-package source bytes after this implementation.
- Migrations: none.
- External mutation, login, browser automation, API, account, credential,
  domain, publication, staging, release, and Production actions: none. The only
  external observation was the authorized, ordinary read-only public ranking
  feasibility check described below.

The handoff and source package internal proposal fields intentionally remain
pending. Their respective detached exact-hash approvals are the effective
authority layers. None of these files grants canonical mutation or Open
Decision resolution authority.

## Scoped owner-decision candidates

The source package contains exactly seven rows in canonical order. These
record statuses describe the owner candidate only; they are not canonical
decision statuses.

| ID | Candidate status | Selected input | Still pending or disabled |
| --- | --- | --- | --- |
| OD-001 | `OWNER_APPROVED` | `suitcase_and_carry_bags` / スーツケース・キャリーバッグ | Runtime activation disabled; synthetic fixtures only |
| OD-002 | `EXECUTION_PENDING` | 旅具比較ノート; `tabigu-note.jp`; individual sole proprietor with trade name | Domain purchase and control evidence not obtained; public activation forbidden; `example.invalid` remains the fallback |
| OD-005 | `PARTIAL` | Primary reviewer `REPOSITORY_OWNER`; JPY 3,000/hour | Alternate reviewer is absent; publication remains blocked without an alternate or separately approved exception |
| OD-006 | `EVIDENCE_PENDING` | Exact-SKU, exact-field identity candidate | External Gold Evidence and Domain Editor review absent; automatic merge disabled |
| OD-007 | `OWNER_APPROVED` | Price 72h, availability 48h, affiliate link 72h, major specifications 90d, image 30d | Runtime activation disabled pending canonical revision |
| OD-008 | `OWNER_APPROVED` | Identified-issue professional consultation; affected-scope stop by default | AI/developer legal judgment forbidden; unresolved issues block the affected operation |
| OD-009 | `OWNER_APPROVED` | JPY 30,000/month; 60/80/100 percent thresholds; three-month JPY 90,000 loss window | Production activation disabled pending canonical revision and account setup |

The only allowed record statuses are `OWNER_APPROVED`, `PARTIAL`,
`EVIDENCE_PENDING`, and `EXECUTION_PENDING`. Candidate status values such as
`RESOLVED`, `VALIDATED`, `ACTIVE`, `RELEASED`, and `PRODUCTION_READY` are
rejected.

## OD-006 evidence, feasibility, and fail-closed boundary

Automatic identity merge is proposed only when brand, manufacturer model,
size, capacity, external dimensions, color or variant, and set count are all
present and exactly equal. If either JAN is present, both must be present,
syntactically valid, and exactly equal. Both absent JAN values neither
authorize nor veto an otherwise exact match. Missing values, variants,
bundles, conflicts, fuzzy similarity, or inferred equivalence go to Human
Review.

For the closed internal validator primitive, a present JAN must be an eight-
or thirteen-digit JAN/EAN value with a valid standard check digit. Any other
length, character set, or check digit fails closed to Human Review. The Gold
vocabulary maps an otherwise exact pair to `AUTOMATIC_MERGE` and every
non-exact or invalid pair to `HUMAN_REVIEW`. This helper is not ST-1702 runtime
identity configuration.

The authorized public feasibility observation used the official Rakuten
daily suitcase ranking at
`https://ranking.rakuten.co.jp/daily/301577/`. It was observed at
`2026-08-12T02:30:56+09:00`; the page identified a 2026-08-11 update from a
2026-08-10 aggregation. The permitted public rendering exposed one contiguous
rank block from 1 through 20. No permitted route exposed ranks 21 through 50
from that same snapshot. Older or unrelated cached rankings were refused, the
Top-100 expansion was not reached, and candidate-bound exhaustion is not
claimed. Ranking entries are family seeds, not exact-SKU observations.

A complete Gold ledger still requires exactly 30 listings, ten families and
three listings per family; at least two shops per family, five shops overall,
and five brands; no more than two families per brand; four low-, four mid-,
and two high-price families; all six required case tags; 435 unordered pairs;
official manufacturer corroboration; Domain Editor review; and zero false
automatic merges. No incomplete rows are stored as a Gold ledger. The sole new
preapproval result is the generated non-promoting validation report.

The approved handoff does not fix eleven observable contract mappings needed
to accept a real ledger and safely cross its later approval boundary: the
ledger `schema` literal; ID types and formats;
candidate qualification and reason vocabularies; nested required-case and
Domain Editor review schemas; the provenance/relation/distinction value
shapes; the canonical-JSON observation hash profile; the derived expected-pair
row structure and ordering; and an independent manufacturer-host and redirect
proof contract; the exact Domain Editor approval record layout; the exact
postapproval Gold summary, resolution, revision, and bundle schemas; and
per-result URL/outcome evidence sufficient to prove first-three qualifying
results and first-eligible tuple selection. A versioned, owner-approved
handoff addendum must fix those mappings before the production ledger loader,
Gold approval loader, or postapproval aggregator may be enabled. Until then,
any present ledger or Gold approval fails closed.

## Informational cross-Story inventory

OD-003, OD-004, and OD-010 through OD-015 are stored in that exact order under
`INFORMATION_ONLY_NO_IMPLEMENTATION_OR_STATUS_EFFECT`. They are follow-up
notes only. They cannot change ST-1701 activation, canonical status, Gate
state, generated revision readiness, downstream readiness, or another Story's
implementation status.

Pending informational conditions remain explicit: the Rakuten account/report
sample is absent; Cognito and provider/account setup is unexecuted; the
alternate notification owner is absent; exact public privacy text is not
approved; retention needs professional confirmation; and account/credential
setup is not executed. No account, credential, domain, provider, or public
action is performed by this package.

## Owned artifacts

| Path | Purpose |
| --- | --- |
| `contracts/unresolved-mvp-business-inputs.v1.yaml` | Preserved canonical-source-derived unresolved registry |
| `generated/unresolved-mvp-business-inputs.v1.json` | Byte-preserved deterministic unresolved read model |
| `contracts/mvp-business-decision-package.v1.yaml` | Strict source of the non-authoritative owner-decision candidate |
| `MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml` | Immutable detached approval bound to the exact source-package and handoff hashes; it is not self-approved or generated |
| `DESIGN_HANDOFF_V1_ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_v1.yaml` | Immutable approved design for bounded Gold Evidence collection and proposal-only postapproval artifacts |
| `DESIGN-HANDOFF-APPROVAL-GOLD-EVIDENCE-v1.yaml` | Immutable detached implementation approval for the exact Gold handoff; it grants no canonical mutation authority |
| `generated/mvp-business-decision-package.v1.json` | Deterministic hash-bound read model that projects the effective detached approval while keeping owner candidates separate from canonical truth |
| `generated/canonical-revision-request.v1.md` | Owner-approved evidence candidate with `NOT_READY` readiness, naming all pending conditions and prohibited effects |
| `generated/gold-evidence-validation.v1.json` | Sole new pre-Domain-approval result; deterministic `STOP_EVIDENCE_INSUFFICIENT` evidence-feasibility and non-promotion record |
| `manifest.yaml` | Generated authority, source, predecessor, owned-source, output, and boundary inventory |
| `../../scripts/build_st1701_business_inputs.py` | Sole strict validator and atomic owner generator; accepts only no arguments or exact `--check` |
| `../../tests/st1701/*.py` | Positive parity, preservation, OD-006 matrix, hostile schema/status/path, no-write, drift, and prohibited-surface coverage |

Generated files must never be hand-edited. The source contracts, immutable
authority inputs, README, generator, and tests are owner sources; the generator
writes the three preserved predecessor files, the Gold validation report, and
`manifest.yaml`. It does not create `gold-evidence-ledger.v1.yaml`, a Gold
approval, a Gold summary, resolution records, an Open Decisions revision, or a
canonical-revision bundle before a valid separately approved ledger exists.

## Local generation and verification

From the repository root, use the pinned offline toolchain:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1701_business_inputs.py

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1701_business_inputs.py --check

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st1701

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads mypy --strict --explicit-package-bases \
  --follow-imports=silent --cache-dir=/dev/null \
  scripts/build_st1701_business_inputs.py tests/st1701
```

The implementation evidence also includes pinned Ruff format/lint, the
applicable strict mypy gate over the Story-owned source and tests (imported
predecessor implementations are followed silently), in-memory compile/import, the ST-0006 owner
`--check`, canonical import verification, `make check-workspace`, focused
sensitive-data and prohibited-surface checks, and `git diff --check`.

## Final approval and canonical-revision boundary

The repository owner approved the exact immutable source-package SHA-256
listed above. The detached record supplies only owner-approved canonical-
revision evidence-candidate authority; the generated request remains
`NOT_READY`. The source package's internal pending field is preserved and is
not rewritten after approval.

The Gold handoff records an explicit repository-owner-only, unavailable-owner
fail-closed exception candidate for OD-005. It is not professional legal
review and does not itself change canonical OD-005 status. OD-006 Gold Evidence
has not been completed or accepted by the Domain Editor. Formal TST-032 and
canonical-revision approval/import remain `NOT_EXECUTED`. External execution
is not decision-resolution evidence. A later, separately approved canonical
revision is required to change canonical Open Decision status or unblock any
Gate.

Formal TST-032, complete Gold ledger collection, Domain Editor approval,
browser/provider use, domain purchase/control, account or credential setup,
staging, publication, release, and Production remain unexecuted. The bounded
public ranking feasibility observation and local generation/tests establish
only implementation evidence and must not be reported as canonical resolution,
formal validation, deployment, release, or Production readiness.
