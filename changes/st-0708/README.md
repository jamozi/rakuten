# ST-0708 — Recorded-only live-evaluation boundary

Status: `LOCAL_IMPLEMENTATION_COMPLETE`

This Story implements the maximum safe local part of the Canonical “Live bounded
AI evaluation” Story. It is executable only with repository-recorded synthetic
evidence. It does not execute formal `TST-018`, contact OpenAI, read a credential,
select a production model, mutate a route, approve a candidate, publish content,
release software, or write to staging/Production.

## Exact evaluation boundary

- Target: `AIT-004` / `ai.article_draft.v1`, risk `CRITICAL`.
- Threshold source: `suite.ai.article_draft.v1.release.v1` from the content-addressed
  evaluation catalog: minimum 200 adjudicated cases, all five required splits,
  nine task metrics, and eight non-waivable zero-tolerance classes.
- Recorded candidate binding: the exact ST-0703 synthetic test binding
  `AIT-004` / `route.synthetic.recorded.v1` / `PRM-004-v1` /
  `raos-synthetic-model-v1`. This is closed provenance and is explicitly not a
  Canonical production route/model/prompt selection.
- Evaluation evidence: the exact ST-0707 bundle and report are reconstructed from
  their content-addressed runtime. That report is for
  `ai.opportunity_assessment.v1`, contains one synthetic plumbing HOLDOUT case,
  has no human-label provenance, and is already
  `REFUSED_INCOMPLETE_EVIDENCE`.

The target/source task mismatch, synthetic non-release dataset, missing human
labels, insufficient denominator, missing splits, unresolved OD-015, and
unexecuted formal TST-018 therefore remain `UNAVAILABLE` or failing gates. They
are never converted to zero or `PASS`. The installed deterministic result is
`REFUSED_INCOMPLETE_EVIDENCE`. A zero-tolerance observation can only produce a
stronger `REFUSED_ZERO_TOLERANCE`; no waiver exists.

## Runtime and generated artifacts

- `contracts/recorded-live-evaluation-runtime.v2.yaml` is the owner contract.
- `generated/recorded-live-evaluation-request.v2.json` is a closed IDs-and-hashes
  request/evidence envelope. It contains no URL, secret, raw prompt, source body,
  review body, or provider response body.
- `generated/recorded-live-evaluation-report.v2.json` is a deterministic
  proposal/refusal report with no operational authority.
- `runtime-manifest.v2.json` binds all inputs, sources, generated outputs, formal
  non-execution status, and the hardened publication helper.
- `generated/openai-live-bounded-evaluation-reference-plan.v1.json` remains as a
  byte-compatible historical interface-only plan; it is not the V2 runtime.

The public application surface accepts only a bounded `RecordedLiveEvaluationRequest`.
The recorded adapter validates exact ST-0703 bindings, reconstructs and verifies
the exact ST-0707 report, validates target thresholds, and returns an immutable
result. It has no provider client, socket, credential, filesystem-write,
activation, approval, or release capability.

## Owner generation

```bash
PYTHONPATH=python:. uv run --locked --offline --no-sync --no-env-file \
  python scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py
PYTHONPATH=python:. uv run --locked --offline --no-sync --no-env-file \
  python scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py --check
```

Publication uses `scripts/secure_generated_publication.py` at exact SHA-256
`38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e`.
Its descriptor-relative transaction preserves foreign files and refuses target,
missing-target, and parent-directory races.

## Evidence level

Only repository-local implementation and local test evidence are claimed.
Canonical registry values remain unchanged: ST-0708 is still Canonically
`NOT_STARTED` / `NOT_EXECUTED`; OD-015 remains blocking; formal TST-018, live,
staging, release, and Production are all `NOT_EXECUTED`.
