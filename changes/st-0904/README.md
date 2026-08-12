# ST-0904 — Public projection reference plan

This Story adds a deterministic, source-derived reference plan for the Public
Read Model boundary. It is deliberately non-executable and non-authoritative.
It does not implement a projector, create public rows, change a database, bind
a job or event, publish content, or satisfy ST-0904 acceptance.

## Authority boundary

Canonical sources establish that an approved immutable Publication Snapshot is
the only publication input and Public Web reads only Public Read Model. ST-0904
depends directly on ST-0903 and ST-0306. The merged ST-0903 artifact expressly
authorizes no executable snapshot builder and defines no authoritative snapshot
instance or exact confidential-snapshot-to-public allowlist. ST-0306 preserves
the `raos_public_ro` readmodel-only boundary but does not select projection
field mappings.

The failed gated Pro attempt ended before submission. The tracked record is
therefore only `PRO_UNAVAILABLE`, authority `NONE`, no proposal, and no content
used. No private run identifier, request text, browser output, or diagnostic is
persisted.

## Preserved surfaces

The reference plan records, without connecting or reconciling them:

- five SLICE-016 tables: `readmodel.public_article`,
  `readmodel.public_article_block`, `readmodel.public_product_card`,
  `readmodel.public_offer`, and `readmodel.public_route`;
- the separate SLICE-022 `readmodel.runtime_control` surface, explicitly out of
  ST-0904 scope;
- `publishing.publish_snapshot.v1`,
  `publishing.rebuild_public_projection.v1`, and
  `ops.rebuild_readmodel.v1` as distinct job surfaces;
- `jp.raos.publishing.public_projection_rebuilt.v1` as a contract surface only;
- unresolved DB/Public OpenAPI differences for heading levels, badge shape,
  destination-host nullability, and projection generation; and
- unresolved catalog/payload idempotency inputs (`snapshot_generation` versus
  `expected_snapshot_hash`).

Every projection, public-row, job, event, audit, and publication record remains
empty and `NOT_EVALUATED`. Empty projections mean no projection or evidence,
not zero valid projections. Formal TST-011/TST-021, runtime, CI, live, staging,
release, and production work remain `NOT_EXECUTED`.

## Generation

Generate only the two derived artifacts:

```bash
uv run --locked --no-sync python scripts/build_st0904_public_projection_reference_plan.py
```

Verify without writing:

```bash
uv run --locked --no-sync python scripts/build_st0904_public_projection_reference_plan.py --check
uv run --locked --no-sync pytest -q tests/st0904
```

The generator hash-binds its authority and dependency inputs, verifies the
pinned staging helper before import, rejects unsafe input/output paths and
duplicate/aliased YAML or JSON keys, and publishes the generated JSON/manifest
as one staged pair with rollback on a partial replacement failure.

## Local evidence

The following read-only checks passed on 2026-08-13 in the dedicated ST-0904
worktree:

- `make check-workspace`: `PASS`, no changed workspace paths, 42 directories;
- `python3 scripts/import_raos_design.py verify`: `PASS`, canonical read order
  and imported package checksums verified; and
- strict mypy for the generator and isolated ST-0904 tests: no issues in five
  source files.

These are local reference/static checks only. They are not formal TST-011 or
TST-021 evidence and do not alter any runtime, CI, staging, release, or
production status recorded above.

## Required future authority

Any pure or runtime projector requires an owner-approved, canonically
reconciled `DESIGN_HANDOFF_V1` with `open_decisions: []`. It must define the
allowlist/redaction mapping, authoritative snapshot selection, public row
shapes, job ownership, scope and generation semantics, atomic replacement,
idempotency/UoW/outbox/audit/event behavior, deletion and rollback, and
safe-offer/freshness/kill-switch bindings. This reference plan supplies none of
those decisions.
