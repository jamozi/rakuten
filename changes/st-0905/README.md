# ST-0905 publication-command/event reference plan

## Result

This Story slice is a deterministic, source-derived, **non-executable** and
**non-authoritative** reference plan. It records the installed publish,
unpublish, and rollback HTTP, job, event, state, security, and traceability
surfaces without connecting or executing them.

- no command handler accepts a request;
- no job is enqueued or consumed;
- no event or audit record is emitted;
- no database, read-model, CMS, external, or public state is mutated;
- no approval or publication authority is created;
- Story acceptance is `false` and readiness is `NOT_READY`;
- runtime, formal TST, live, staging, release, and production results remain
  `NOT_EXECUTED`.

`pro_required_for_reference_slice` is `false`. No Pro run, response,
diagnostic, or proposal is recorded or used. Any executable work remains
gated on an owner-approved `DESIGN_HANDOFF_V1` with no open decisions.

## Why execution remains gated

The direct dependencies deliberately stop before publication execution:

- ST-0903 supplies no authoritative Publication Snapshot builder or instance.
- ST-0904 supplies no projector, public row, current route, database mutation,
  job, or event runtime.
- ST-0402 supplies only provider-neutral, development-only synthetic step-up;
  it supplies no production identity/MFA mapping or public authority.

The installed contracts also leave material boundaries unresolved: publish
candidate path/body identity; route-derived publish idempotency; scheduled
publish despite MVP auto-publish being disabled; rollback source-snapshot
resolution; unpublish current-snapshot/reason-class derivation; cross-key,
job, outbox, and event deduplication; event-envelope allocation; and the
atomic unit of work joining publication, readmodel, job, audit, outbox, and
events. The role matrix contains publish and rollback, but no unpublish action.

## Exact preserved surfaces

The plan keeps the following installed surfaces distinct:

- `PUBADM-009` / `publishing.publish_snapshot.v1` /
  `jp.raos.publishing.article_published.v1`;
- `PUBADM-013` / `publishing.unpublish.v1` /
  `jp.raos.publishing.article_unpublished.v1`;
- `PUBADM-012` / `publishing.rollback.v1` /
  `jp.raos.publishing.article_rolled_back.v1`.

Their request fields, scopes, headers, job payloads, idempotency bases, locks,
event data fields, state transitions, and security rows are projected exactly.
Recorded conflicts are facts, not reconciliation or implementation choices.

## Hard gates and empty records

Every unresolved approval, policy, legal, rights, freshness, kill-switch,
authorization, idempotency, concurrency, unit-of-work, audit, outbox, event,
public-isolation, external, or publication gate fails closed. The safe result
is no command, no job, no event, no mutation, and no side effect.

Command, job, event, audit, database-mutation, external-action, publication,
and rollback records are empty and `NOT_EVALUATED`. Empty command records mean:

`NO_COMMAND_OR_EVIDENCE_NOT_ZERO_VALID_COMMANDS`

They do not prove zero invalid commands or any successful execution.

## Generation

The owning source is:

`changes/st-0905/contracts/publication-commands-reference-plan.v1.yaml`

Generate only through:

```sh
uv run --locked --no-sync python scripts/build_st0905_publication_commands_reference_plan.py
```

Verify without writes through:

```sh
uv run --locked --no-sync python scripts/build_st0905_publication_commands_reference_plan.py --check
```

The generator verifies the pinned helper bytes before lazy import, rejects
duplicate/aliased YAML and duplicate-key JSON, validates exact authority,
dependency, command, job, event, security, state, and conflict rows, constrains
paths and symlinks, sanitizes malformed nested shapes, and stages the generated
JSON/manifest pair before replacement. A failed replacement restores the exact
prior pair.

## Explicitly out of scope

- modifications to any existing repository file;
- runtime/domain/application/port/adapter implementation;
- API routes, command handlers, workers, jobs, event publishers, outbox, inbox,
  audit, idempotency, database repositories, unit of work, or migrations;
- snapshot/projector/current-route implementation or public rows;
- real publish, unpublish, rollback, CMS, database, event, or external action;
- approval, publication, policy, legal, rights, freshness, security, finance,
  credential, kill-switch, release, or production authority;
- canonical, upstream, contract bundle, status, or generated-binding changes;
- formal TST-012/TST-013/TST-021, browser, live, staging, release, or
  production claims.
