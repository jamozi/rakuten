# ST-0709 recorded AI governance workspace model

Status: `LOCAL_IMPLEMENTATION_COMPLETE`

This Story provides a dependency-free, headless, deeply immutable model for the
approved `GOV-001` AI Governance screen. Canonical Story status and formal
browser `TST-022` remain unchanged and `NOT_EXECUTED`.

The original V1 compatibility model remains byte-for-byte unchanged. It
continues to expose only the historical disabled/unavailable shell. The
additive V2 surface projects content-addressed, repository-recorded data from
ST-0701, ST-0707, and ST-0708 without adding a route, provider, credential,
network, persistence, approval, activation, publication, or release capability.

## Implemented local boundary

- Exact `GOV-001` catalog metadata and the ST-0709 Cost-visibility objective.
- Fixed read-only Task, Prompt, Route, Evaluation, Release, and Cost sections.
- Twelve Task rows, twelve Prompt rows, five unique Route rows, one recorded
  synthetic Evaluation row, one recorded refusal-only Release row, and twelve
  configured candidate cost-ceiling rows.
- Exact source bindings for Canonical design/security/test sources and current
  ST-0701, ST-0706, ST-0707, ST-0708, ST-1101, and V1 bytes.
- Semantic captions, column metadata, row-header keys, and text/code/icon status
  metadata which never depends on color alone.
- Explicit actual-cost `UNAVAILABLE` values; unknown spend is never rewritten
  to zero, and OD-009 remains unresolved.
- Catalog `enabled` metadata is displayed only as a candidate configuration;
  activation and release authorization are always false.
- Detached, deeply frozen, JSON-safe public values through the ST-1101
  `createJsonValue` trust boundary.
- Stable closed errors without rejected-value echo if input or candidate
  validation fails.
- A deterministic owner generator which re-runs the exact recorded ST-0707 and
  ST-0708 evaluation paths, verifies all declared hashes, and publishes the
  fixture, TypeScript binding, and runtime manifest atomically.

The V2 model is display metadata only. GOV-001 remains unregistered beneath the
ST-1101 shell. The projected ST-0707 report is
`REFUSED_INCOMPLETE_EVIDENCE`; the projected ST-0708 release-decision proposal
is also `REFUSED_INCOMPLETE_EVIDENCE` with authority `NONE` and human-only
approval. No live value is inferred.

## Owner generation

```text
PYTHONPATH=python:. .venv/bin/python scripts/build_st0709_ai_governance_workspace.py
PYTHONPATH=python:. .venv/bin/python scripts/build_st0709_ai_governance_workspace.py --check
```

Generated outputs:

- `changes/st-0709/generated/ai-governance-workspace.v2.json`
- `packages/web-ui/src/ai-governance-recorded.v2.ts`
- `changes/st-0709/runtime-manifest.v2.json`

## Explicit exclusions

There is no React, Next.js, JSX, DOM, browser, route registration, API client,
network, environment, storage, authentication transport, provider adapter,
effect callback, runtime registration, persistence, approval, activation,
release, publication, deployment, staging, or Production behavior.

## Evidence boundary

Focused Node/Python tests and static/type checks are local implementation
evidence only. Browser functional `TST-022`, rendered accessibility
verification, hosted CI, live provider evaluation, staging, release,
deployment, and Production remain `NOT_EXECUTED`.
