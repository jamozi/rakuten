# ST-0702 context-pack reference plan

This directory contains the owner-authored input and deterministic projection for the
`SOURCE_DERIVED_NON_EXECUTABLE_CONTEXT_PACK_REFERENCE_PLAN` slice.

The slice is deliberately non-executable. It projects the exact committed ST-0701
registry task bindings and the limited packing rules that can be derived from their
canonical metadata. It does not build a context pack or manifest, choose a task,
prompt, route, provider, model, source packet, Fact, schema, estimator, or algorithm,
and it does not call a provider or runtime.

ST-0604 remains a hard input boundary: no approved Source Packet, Facts, field
mapping, or generation permission is available. The unavailable manifest schema,
canonical-JSON algorithm, token estimator and overhead, scope-reduction algorithm,
important-to-required promotion rule, recursive scan rule, and packing algorithm are
kept null. Empty collections and null counts are absence of executable inputs and
evidence, not successful packing or zero work.

The generated JSON is a reviewable inventory/reference projection only. It is not a
context-pack artifact, provider request, runtime manifest, validation result, or
formal evidence. Story acceptance, activation, runtime, provider, staging, release,
and Production remain false, unavailable, or `NOT_EXECUTED`.

## Owner generation

Use the pinned repository Python environment:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0702_context_pack_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0702_context_pack_reference_plan.py --check
```

Only the builder owns:

- `changes/st-0702/generated/context-pack.reference-plan.v1.json`
- `changes/st-0702/manifest.yaml`

Local generation and tests do not constitute formal TST execution or authorization
for a provider, live runtime, staging, release, or Production action.
