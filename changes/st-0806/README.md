# ST-0806 recorded AI draft integration

Status: `LOCAL_IMPLEMENTATION_COMPLETE` (V2 local evidence only). Canonical
registry and formal TST-018/TST-020 remain unchanged and `NOT_EXECUTED`.

## Boundary

This Story adds one development/CI-only, one-call integration seam from a
successful ST-0706 `AiJobResult` to one synthetic ST-0802 draft article-version
candidate. The candidate remains human editable and is never approved,
applied, merged, persisted, published, released, or made Production eligible.

The original V1 seam remains compatible and intentionally reports ST-0605 as
`UNEVALUABLE`. The additive V2 seam accepts only `ENV_DEV` or `CI`, one exact
`ai.article_draft.v1` success validated `PASS`, and hash-bound identifiers for
the output artifact, source packet version, article, version, site, category,
and before/after Content AST bodies.

V2 consumes an exact canonical ST-0706 V2 state snapshot and its matching
successful recorded outcome. It verifies the command, completion receipt,
validation plan, artifacts, cost, and succeeded outbox intent without owning
the ST-0706 CAS/runtime. A generated synthetic fixture supplies one canonical
after Content AST plus an exact ST-0605 snapshot/report/receipt. Coverage is
recomputed: a matching PASS creates one effect-free human-editable proposal;
policy/evidence failure is `BLOCKED`; missing or structurally unevaluable
coverage is `UNAVAILABLE`. Zero denominators never pass.

## Owned implementation

- `python/raos/domain/editorial/ai_draft_integration.py`
- `python/raos/ports/ai_draft_integration.py`
- `python/raos/application/editorial/ai_draft_integration.py`
- `python/raos/adapters/recorded_ai_draft_integration.py`
- `python/raos/domain/editorial/ai_draft_integration_v2.py`
- `python/raos/ports/ai_draft_integration_v2.py`
- `python/raos/application/editorial/ai_draft_integration_v2.py`
- `python/raos/adapters/recorded_ai_draft_integration_v2.py`
- `scripts/build_st0806_ai_draft_integration_v2.py`
- `changes/st-0806/contracts/ai-draft-integration.v2.yaml`
- `changes/st-0806/generated/`
- `changes/st-0806/manifest.v2.yaml`
- `tests/st0806/`

The adapter is a bounded deterministic fixture. The application service makes
exactly one port call and has no retry or fallback. All failures are closed,
redacted, immutable, non-pickleable, and suppress collaborator exception cause
and context.

## Explicitly not executed

Database, generic queue dispatch/redrive, event dispatch, provider, network,
credentials, filesystem runtime reads, clock, randomness, sleep, subprocess,
logging, background work, raw prompts, review bodies, raw HTML, arbitrary URLs,
and finance/affiliate economics are outside this Story. Approval, publication,
merge, apply, persistence, recommendation-order mutation, release, formal
validation, live validation, staging, and Production remain false or
`NOT_EXECUTED`.
