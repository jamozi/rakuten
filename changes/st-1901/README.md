# ST-1901 — disabled recorded model-Judge calibration

Classification:
`MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_MODEL_JUDGE_CALIBRATION_V1`.

## Preflight

- Story: ST-1901, “Human labelでJudgeを校正し限定利用”.
- Dependency: current ST-0707 deterministic recorded evaluation harness.
- Read: Canonical precedence and decisions, ST-1901/ST-0707 backlog entries,
  RAOS-AI-001 Judge/evaluation/human-label design, current Judge schemas and
  rubric, TST-018/TST-019/TST-032, security/privacy design, SEC-AI-001..007,
  THR-009/010, and the current ST-0707 implementation/contracts/tests.
- Ambiguity: no Canonical provider, model, real label corpus, reviewer identity,
  or release decision is available. The safe interface-only implementation keeps
  every operational state disabled and every such binding unavailable.
- Planned files: additive domain/application/port/recorded adapter modules,
  versioned owner contract, generated synthetic label fixture/report/manifest,
  focused tests, ExecPlan, worklog, and local completion record.
- Tests: owner generate/check, ST-1901 focused positives and critical negatives,
  direct ST-0707 regressions, Ruff format/check, strict mypy, compile/import,
  focused secret scan, and `git diff --check`.
- Out of scope: provider/model selection, live calls, credentials, real human
  labeling, persistence, route mutation, activation, approval, publication,
  staging, release, Production, and formal TST-032 evidence.

## Closed feature and authority boundary

`DEFAULT_MODEL_JUDGE_CALIBRATION_SCOPE` is exactly `DISABLED`. The only other
closed state is `RECORDED_SYNTHETIC_CALIBRATION_ONLY`; no live-enabled state or
activation/configuration method exists. Disabled evaluation fails before the
inward port is read. The port contains no provider/model SDK, URL, credential,
filesystem path, raw content, persistence, or mutation type.

The generated fixture has 200 opaque, double-labeled synthetic records. It has
no prompt, source packet, model output, rationale, review body, affiliate
economics, personal data, or actual reviewer identity. Human-side adjudicated
labels are the immutable gold authority *inside this fixture*; Judge predictions
can never replace or modify them. `actual_human_activity=false`,
`representative_dataset=false`, and `release_eligible=false` prevent the fixture
from being represented as real calibration evidence.

The deterministic harness calculates a quadratic weighted kappa and exact
critical false-pass/false-fail rates using integer/rational arithmetic. It also
checks the Canonical minimum of 200 double-labeled cases plus local fixture-only
balance guards. Malformed, duplicate, ambiguous, noncanonical, oversized, leaky,
or hash-drifting records fail with one redacted closed error. Insufficient or
unbalanced evidence and threshold failures produce refusal-only reports.

Even when local synthetic metrics meet their thresholds, the result is
`REFUSED_UNVERIFIABLE_CALIBRATION`: real human provenance, a representative
dataset, and exact resolved model/route/prompt scope are unavailable. No
accepted, active, approved, release-ready, publication, or Production outcome
exists. A separate human Release Decision remains mandatory.

Canonical ST-1901 remains `DEFERRED_POST_MVP` / `NOT_EXECUTED`; local evidence
does not constitute `VALIDATED` or Story acceptance.

Owner commands:

```text
PYTHONPATH=python:. .venv/bin/python scripts/build_st1901_model_judge_calibration.py
PYTHONPATH=python:. .venv/bin/python scripts/build_st1901_model_judge_calibration.py --check
PYTHONPATH=python:. .venv/bin/pytest -q tests/st1901
```
