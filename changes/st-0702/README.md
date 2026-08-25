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

## 2026-08-24 local audit preflight

- Story/objective: ST-0702, building Canonical input only from allowlisted Facts.
- Read inputs: Canonical precedence/decisions/open decisions, ST-0702, ST-0604,
  ST-0701, FR-006 traceability, TST-005/TST-019, SEC-AI-001 through SEC-AI-007,
  both predecessor owner contracts/manifests, and their focused suites.
- Safe interpretation: Canonical sources still provide no Fact-field mapping,
  manifest schema, canonical JSON/token estimator, or scope-reduction algorithm,
  so the implementation remains a non-executable interface boundary. No open
  decision is inferred.
- Local change: rebind the now-current ST-0701 owner manifest at base
  `679ccdc4a49fca8e1bee8827177be7130d6d45b6`, remove the resolved manifest-drift
  marker, strengthen semantic checks for typed allowlisted input, Source Packet
  requirements, forbidden fields, disabled tools/network/state mutation/provider
  storage, strict output, and non-fallback safety failures, then regenerate only
  the two ST-0702 owner outputs.
- Checks: owner no-write generation, ST-0702 focused/negative tests, predecessor
  and downstream affected suites, Ruff format/lint, mypy, static/secret/canonical/
  workspace/diff checks.
- Out of scope: runtime Facts or packing, provider calls, credentials, formal
  TST-005/TST-019 evidence, staging, release, publication, and Production writes.

## 2026-08-25 provenance reconciliation

- Rebound ST-0604 to the exact owner commit
  `89d8074951ce73a5c76ca55f0ea3b2c129559d81` and its current reference-plan
  bytes. The durable ST-0604 runtime does not create an approved packet for
  this recorded projection, so packet, Fact, mapping, approval, and generation
  inputs remain unavailable.
- Rebound the shared filesystem/YAML helper to its current exact bytes and
  added hostile coverage proving helper drift fails closed.
- ST-0605 is not a Canonical dependency or an ST-0702 pinned input and is not
  added to the owner inventory. ST-0701 bytes and historical base binding are
  unchanged.
- This reconciliation performs no packing, runtime, provider, network,
  credential, publication, staging, release, or Production action and does not
  elevate formal TST or Canonical status.
