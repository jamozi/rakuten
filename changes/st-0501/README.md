# ST-0501 — local recorded portfolio workflow seam

Classification: `MAXIMUM_SAFE_LOCAL_RECORDED_NON_PERSISTENT_PORTFOLIO_WORKFLOW_SEAM`

This implementation-first slice is a partial, source-derived, non-authoritative
local interface candidate. It projects the sixteen canonical list/create/get/
update operations for Category, IntentCluster, Keyword, and ArticlePlan through
one ordered recorded exchange. It is not full CRUD, a repository, a unit of
work, a transaction boundary, or a persistence implementation. Delete is not
represented.

## Closed behavior

- The application accepts one immutable, pre-resolved `TEST_ONLY` request. It
  requires an exact committed ST-0403 `AuthorizationGrant` for the canonical
  resource action and matching site/resource before the exchange can be called.
- The only inward port is `PortfolioWorkflowExchange.exchange(request)`. The
  ENV-DEV adapter consumes immutable ordered scripts, returns only pre-scripted
  identifiers, timestamps, normalized text, versions, and strong ETags, and
  exposes metadata-only history.
- UUIDv7 identifiers, canonical display prefixes (`CAT-`, `INT-`, `KW-`, and
  `PLAN-`), UTC timestamps, nonnegative lock versions, explicit pagination,
  explicit idempotency keys, and strong ETags are validated without generating
  any value.
- ArticlePlan exposes the canonical state vocabulary and graph relationships,
  but this slice accepts only `IDEA`. Every transition that needs a completed
  brief, source packet, accepted AI job, quality pass, human approval, or other
  external evidence remains disabled. Category `APPROVED` and `ACTIVE` are also
  disabled because no approval evidence belongs in this seam.
- Collaborator exceptions, malformed outcomes, reordered scripts, and exhausted
  scripts fail closed with stable local codes. Request values, outcomes, scripts,
  and history are redacted and not pickleable.

The adapter has no environment lookup, file or network I/O, database/provider
client, mutable business-state map, identifier or ETag generator, actor binding,
normalization algorithm, audit coupling, publication action, finance action, AI
execution, or external side effect.

## Authority and status boundary

The projection follows the canonical ST-0501 operation catalog and current
Category, IntentCluster, Keyword, and ArticlePlan vocabularies, with ST-0308 and
ST-0403 retained as read-only predecessors. It does not select a real site,
category, domain, actor, source packet, approval, normalized-keyword algorithm,
display-ID suffix algorithm, storage model, or deployment target.

Story acceptance remains false. Runtime/provider work, persistence, migration,
hosted CI, formal TST execution, staging, release, and Production are
`NOT_EXECUTED` and `NOT_AUTHORIZED`. Local pytest results are development
evidence only and do not establish delivery, validation, or release eligibility.

## Local focused check

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  pytest -q tests/st0501
```
