# ST-0705 AI output validation reference plan

This Story owns a deterministic, source-derived, non-executable reference plan
for the AI output validation gates already defined by the approved RAOS design.
It does not implement a validator runtime, evaluate candidate content, emit an
event, or satisfy ST-0705 acceptance.

The owner source is
`contracts/ai-output-validation-reference-plan.v1.yaml`. The generated JSON and
manifest are written only by
`scripts/build_st0705_ai_output_validation_reference_plan.py`.

The plan remains fail closed:

- `executable` is `false`;
- candidate and content validation are `UNEVALUABLE`;
- the release decision is `NOT_READY`;
- Story acceptance is `false` and cannot be established by schema validation;
- all validation, runtime, provider, job, event, formal, and live actions are
  `NOT_EXECUTED`, with action counts fixed at zero;
- candidates, context, facts, claims, mappings, findings, evidence, and reports
  remain empty, while observed counts remain unknown (`null`).

No algorithm, threshold, model, provider, cost, identity, persistence,
approval, or live operation is selected by this artifact.

Local generation and drift checks use the pinned repository Python environment:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0705_ai_output_validation_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0705_ai_output_validation_reference_plan.py --check
```

These commands provide local deterministic artifact evidence only. They do not
constitute formal TST-019/TST-020, runtime, provider, staging, release, or
production evidence.
