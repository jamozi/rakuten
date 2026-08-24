# ST-1908 — disabled recorded fine-tuning evaluation seam

Canonical ST-1908 remains `DEFERRED_POST_MVP`. This local implementation is a
provider-neutral, metadata-only research harness; it is not fine-tuning, live
evaluation, TST-032 evidence, a release decision, or Production readiness.

## Preflight and authority

- Objective: consider fine-tuning only after dataset rights, governance,
  independent quality evidence, and lifecycle cost benefit are available.
- Read inputs: Canonical precedence, decisions and open decisions; ST-1908 and
  dependency ST-0707; RAOS-AI-001 evaluation and fine-tuning policy; dataset
  manifest/evaluation contracts; TST-032; security, privacy, data classification,
  control, threat, and acceptance designs; and the current ST-0707 runtime.
- Unresolved inputs: dataset licensing/sanitization, retention/deletion,
  reviewer labor cost, provider/model/cost facts, representative data, actual
  candidate evaluation, and a separate release decision remain unavailable.
- Out of scope: raw examples, training, provider/network/credentials,
  persistence, personal data, tracking, model/route mutation, editorial or
  recommendation mutation, publication, staging, release, and Production.

## Maximum-safe implementation

`DEFAULT_FINE_TUNING_SCOPE` is exactly `DISABLED`. The only executable state is
`RECORDED_SYNTHETIC_EVALUATION_ONLY`, accepted only in `ENV-DEV` and `ENV-CI`.
Disabled evaluation fails before the inward port is called. No live, training,
activation, provider, persistence, or release state exists.

The one-shot adapter consumes exact caller-supplied canonical JSON. It rejects
unknown/duplicate keys, floats, noncanonical bytes, oversize data, prohibited
source classes, personal data, Rakuten review bodies, unlicensed content,
secrets, release eligibility, actual training claims, and source/hash drift.
Rejected bytes never appear in values, errors, logs, or generated evidence.

The pure evaluator applies explicit gates for prompt/route optimization,
repeated errors, dataset rights, governance, holdout integrity, representative
coverage, minimum sample, baseline/candidate binding, zero tolerance, strict
quality Pareto improvement, and lifecycle cost Pareto improvement. Missing or
unverified metrics and costs remain `null`/`UNAVAILABLE`; they are never
converted to numeric zero. Affiliate commission, reward, EPC, RPM, and profit
are structurally absent and cannot affect editorial or recommendation order.

Because the recorded fixture is synthetic metadata, has no representative or
licensed dataset evidence, no verified evaluation or cost inputs, and no actual
training, its deterministic result is `REFUSED_UNAVAILABLE_EVIDENCE`. The report
has no consideration, training, provider-call, mutation, publication, release,
or Production authority. A separate human release decision remains mandatory.

## Owner commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1908_fine_tuning_evaluation.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1908_fine_tuning_evaluation.py --check
```

Only the owner writes the report and manifest. Local evidence is not formal
TST-032, legal/privacy approval, a real dataset or model evaluation, staging,
release, Production, or Story acceptance.
