# ST-0707 evaluation harness — LOCAL_IMPLEMENTATION_COMPLETE

ST-0707 provides a deterministic, recorded/synthetic-only evaluation harness
that consumes the exact ST-0705 output-validation fixture and report. The
historical `BootstrapEvaluationRunner` remains available as a non-authoritative
smoke surface; it is not treated as release evidence.

The runtime owner contract and generator produce two immutable inputs:

- a suite registry copied from the pinned Canonical evaluation catalog with
  exact metric kinds, directions, units, threshold operators and values, eight
  zero-tolerance failure classes, minimum sample size, and required splits;
- one locked `HOLDOUT` plumbing case with provenance exactly
  `SYNTHETIC_PLUMBING_ONLY` and explicit `false` values for canonical,
  representative, human-labeled, release-eligible, and Production-eligible
  claims.

The artifact loader validates canonical JSON bytes, schemas, sizes, duplicate
keys, all declared hashes, dataset/case/holdout identities, the current ST-0705
contract/profile/runtime/fixture/schema bindings, and the re-evaluated ST-0705
report. It never repairs an artifact or coerces missing evidence into a value.

The pure runner reports exact integer-millionth point estimates and a one-sided
95% Wilson lower bound for every available ratio metric. Higher-is-better
thresholds use that lower bound. Canonical zero-tolerance thresholds use exact
observed counts with no waiver. Human-label metrics, resolved-model identity,
and any other missing evidence remain `UNAVAILABLE`, never numeric zero.

This synthetic fixture has one case, only the `HOLDOUT` split, no human labels,
and no resolved-model binding. Its deterministic outcome is therefore always a
release-decision `PROPOSAL` with `REFUSED_INCOMPLETE_EVIDENCE`, even when every
locally observable zero-tolerance count is zero. An observed zero-tolerance
finding takes precedence as `REFUSED_ZERO_TOLERANCE`; unavailable zero-tolerance
evidence also refuses as incomplete. There is no accepted or release-ready
outcome in this local runtime.

The application and adapter accept only `ENV-DEV` or `ENV-CI`. They expose no
provider, credential, network, persistence, route/model mutation, activation,
approval, publication, release, staging, or Production method. Every report
keeps formal TST-018/TST-019, live, staging, release, and Production at
`NOT_EXECUTED` and all authority booleans false.

Local owner commands:

```text
PYTHONPATH=python:. .venv/bin/python scripts/build_st0707_evaluation_harness_runtime.py
PYTHONPATH=python:. .venv/bin/python scripts/build_st0707_evaluation_harness_runtime.py --check
PYTHONPATH=python:. .venv/bin/pytest -q tests/st0707 tests/st0707_runtime
```
