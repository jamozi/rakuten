# ST-0804 — deterministic local recommendation engine

Classification:
`PURE_DETERMINISTIC_LOCAL_RECOMMENDATION_ENGINE`.

This Story implements the approved recommendation calculation downstream of
the ST-0803 comparison validator. It accepts one already validated comparison
matrix plus strict pre-resolved inputs; it does not resolve identity, normalize
raw product facts, invent penalty policy, persist state, expose an API, call a
provider, approve content, render public content, or publish.

## Closed calculation boundary

- The exact canonical methodology ID, version, and source SHA-256 are pinned.
  Every hard-constraint, weighting, normalization, coverage, conflict,
  staleness, and tie rule is supplied as a version/hash-bound reference.
- Candidate-universe, article/version, reader/use-case/budget context, and
  dimension definitions are explicit immutable version/hash-bound records.
  The candidate universe and every dimension must exactly match the validated
  ST-0803 product/axis sets.
- Every product/dimension assessment binds its comparison coordinate and exact
  evidence ID. Duplicate, missing, foreign, or mismatched coordinates block.
- Dimension weights are exact finite positive `Decimal` values no greater than
  1. Their total need not equal 1; coverage and score calculations normalize
  deterministically by the applicable total.
- Normalized scores are pre-resolved exact finite `Decimal` values in `[0, 1]`.
  This Story does not select or implement a normalization algorithm.
- Conflict and staleness components are explicit finite nonnegative `Decimal`
  values capped at 20 and bound to the methodology rule references. A
  `CONFLICTING`, `NEAR_EXPIRY`, or `STALE` state requires a positive component;
  `NONE` and `CURRENT` require zero. This Story does not author their magnitude.
- A failed or unknown hard constraint is ineligible before score calculation.
  A stale critical fact is `INELIGIBLE` until refresh. Unknown or conflicting
  critical evidence remains eligible-but-unranked within the canonical
  alternative boundary. A noncritical unknown contributes no score or
  current-evidence coverage and is disclosed.
- Weighted current-evidence coverage gates ranking at 0.80 and primary
  recommendation eligibility at 0.90. `NEAR_EXPIRY` remains current but carries
  its explicit penalty; conflicting or stale evidence is not current.
- Base score, uncertainty penalty, and clamped final score follow
  `RAOS-CONTENT-RECO-001`. Internal values use four decimals with
  `ROUND_HALF_EVEN`; the public integer projection is present only in the
  explanation-bearing local result.
- Ranked candidates are sorted by score and grouped against each group's
  highest-score anchor. A difference at or below 2.0 co-recommends without a
  manufactured winner; members use stable product-ID order. A difference of
  2.01 begins a new ordered group.

## Explanation and finance separation

The engine emits deterministic canonical JSON and its SHA-256. The artifact
binds the validated comparison hash, article and decision context, candidate
universe, methodology and rules, dimension definitions and weights, all
coordinate assessments, eligibility reasons, coverage, score and penalty
components, tie groups, rank order, precision, and disabled authority states.
Input collection order is intentionally canonicalized, so all permutations of
the same semantic input produce byte-identical output.

Canonical forbidden recommendation vocabulary and the established safety
equivalents are independently rejected across ST-0804 references and every
ST-0803 axis field. This includes `affiliate_rate`, `commission`, `epc`, `rpm`,
`revenue`, `confirmed_commission`, `contribution_profit`, `sponsor_benefit`, and
the finance/cost/profit/rate/sponsorship token families. Mutable collections,
runtime subclasses, booleans used as numbers, non-finite or out-of-range
decimals, malformed exact values, and structural-injection shapes fail closed.
Findings and construction errors contain closed codes only and never echo input.

## Canonical test-matrix coverage

The isolated local suite covers the implementation-safe behavior in
CT-0887 through CT-0906: hard pass/fail, critical unknown, exact coverage
thresholds, deterministic weight normalization, missing noncritical evidence,
conflict and near-expiry penalty paths, penalty cap and score clamp, 2.0/2.01
tie boundaries, finance-field rejection, identical recalculation, four-decimal
internal/public-integer rounding, and cross-article/context hash separation.
It also exercises all input permutations and negative type, subclass,
coordinate, rule-binding, comparison-report, redaction, and side-effect paths.

CT-0901 through CT-0903 human override/reason/evidence review are deliberately
not implemented or claimed as PASS. Human override and approval, public
explanation rendering, persistence, API/provider integration, and OD-006
identity-resolution policy remain outside this Story.

## Local verification

Environment: Linux worktree, CPython 3.14.6, pinned uv 0.12.1, pytest 9.1.1,
Ruff 0.16.1, and mypy 2.3.0. The environment was synchronized only through:

```bash
scripts/python_toolchain.sh \
  --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv sync
```

Local checks executed in separate processes from exact working directory
`/home/minami/rakuten/.worktrees/st-0804`:

```text
pytest -p no:cacheprovider -q tests/st0804
  PASS — 75 passed
pytest -p no:cacheprovider -q tests/st0803
  PASS — 31 passed
ruff check --no-cache <ST-0804 source and exact test files>
  PASS
ruff format --check --no-cache <ST-0804 source and exact test files>
  PASS — 5 files already formatted
PYTHONDONTWRITEBYTECODE=1 MYPYPATH=python:tests/st0804 \
  /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  run --locked --no-sync --no-env-file \
  mypy --strict --explicit-package-bases --cache-dir=/dev/null \
  python/raos/domain/editorial/recommendation.py \
  tests/st0804/conftest.py \
  tests/st0804/test_recommendation.py \
  tests/st0804/test_boundaries.py \
  tests/st0804/test_negative_cases.py
  PASS — no issues in 5 source files
make --no-builtin-rules --no-builtin-variables check-workspace
  PASS — no workspace drift
scripts/python_toolchain.sh --uv <pinned-uv> contract-gate
  PASS on final unopposed rerun — reconstruction 306 artifacts; verifier PASS;
  isolated ST-0104 166 passed in 222.12s
python3 scripts/scan_secrets.py --worktree
  OPERATIONAL ERROR in linked worktree — exit 2,
  ERROR code=unsafe-git-metadata source="."
same scanner --worktree on non-git fallback snapshot from git archive HEAD
overlaid with the exact six ST-0804 files
  PASS — exit 0, no findings or output
git diff --check
  PASS — unstaged and staged exact-six-file checks emitted no output
```

The scanner intentionally requires `.git` to be a directory before using Git
enumeration, so the linked-worktree `.git` file is rejected before any file is
read. The documented non-git fallback was therefore exercised against a full
temporary repository snapshot with the exact ST-0804 files overlaid. This is a
linked-worktree tooling limitation, not a secret finding; no scanner rule or
repository file was changed.

One preceding composite contract-gate attempt returned `1 failed, 165 passed`
because the AsyncAPI half of
`test_openapi_and_asyncapi_structure_drift_fails` received the existing
secure-capture refusal `contract repository root changed during secure capture`
instead of its expected structure-validation refusal. The unchanged failing
test passed alone (`1 passed in 9.99s`), and the complete unopposed composite
rerun then passed all 166 tests. No contract, verifier, or ST-0104 file was
changed to obtain that result.

These are local implementation checks only. Formal TST-007/TST-020, hosted CI,
live validation, runtime/persistence, staging, release, publication, and
Production work remain `NOT_EXECUTED`. The result always retains
`publication_authorized=false` and `production_eligible=false`; no local result
constitutes formal validation or release authority.
