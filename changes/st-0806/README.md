# ST-0806 recorded AI draft integration

## Boundary

This Story adds one development/CI-only, one-call integration seam from a
successful ST-0706 `AiJobResult` to one synthetic ST-0802 draft article-version
candidate. The candidate remains human editable and is never approved,
applied, merged, persisted, published, released, or made Production eligible.

ST-0605 coverage is intentionally `UNEVALUABLE`: explicit ordered Claim-to-Fact
references are carried without inferring identity, support, eligibility, or a
coverage result. The seam accepts only `ENV_DEV` or `CI`, one exact
`ai.article_draft.v1` success validated `PASS`, and hash-bound identifiers for
the output artifact, source packet version, article, version, site, category,
and before/after Content AST bodies.

## Owned implementation

- `python/raos/domain/editorial/ai_draft_integration.py`
- `python/raos/ports/ai_draft_integration.py`
- `python/raos/application/editorial/ai_draft_integration.py`
- `python/raos/adapters/recorded_ai_draft_integration.py`
- `tests/st0806/`

The adapter is a bounded deterministic fixture. The application service makes
exactly one port call and has no retry or fallback. All failures are closed,
redacted, immutable, non-pickleable, and suppress collaborator exception cause
and context.

## Explicitly not executed

Repository, database, queue, event, provider, network, filesystem, environment,
clock, randomness, subprocess, logging, background work, raw prompts, and raw
source content are outside this Story. Approval, publication, merge, apply,
persistence, event emission, release, formal validation, live validation,
staging, and Production remain false or `NOT_EXECUTED`.
