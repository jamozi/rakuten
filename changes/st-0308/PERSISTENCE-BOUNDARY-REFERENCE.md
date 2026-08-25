# ST-0308 source-bound persistence boundary reference

> Historical pre-runtime artifact. The current local implementation entry
> point is `changes/st-0308/contracts/persistence-runtime.v2.yaml`; this
> document remains immutable in meaning and does not describe current runtime
> readiness or grant formal/external authority.

Status: `MAXIMUM_SAFE_REFERENCE_ONLY_LOCAL_SLICE`

Authority: `NON_AUTHORITATIVE`

This Story-owned slice records the exact boundary that can be implemented
without choosing any of the six unresolved local persistence-design gaps. It
is a deterministic reference artifact only. It is not a `DESIGN_HANDOFF_V1`,
canonical reconciliation, repository-owner approval, Repository or Unit of
Work implementation, database behavior, formal test evidence, or activation
authority.

## Boundary represented

The canonical Story remains **ST-0308 — Persistence ports and repositories**,
with dependencies `ST-0304` and `ST-0105`, deliverables `repositories` and
`transaction boundary`, acceptance criterion `cross-module write rules`, and
required Suites `TST-005` and `TST-008`. Its canonical Story has no Open
Decision and remains `APPROVED_FOR_IMPLEMENTATION`, `NOT_STARTED`, and
`NOT_EXECUTED`.

The existing local design request separately identifies `ST0308-D1` through
`ST0308-D6`. Those six records are noncanonical design gaps, not canonical Open
Decisions. All six remain unresolved. The reference contract therefore keeps
every design selection, payload, approved handoff identity, reconciliation,
and owner approval exactly null.

## Deliberately absent implementation

This slice contains none of the following:

- Repository Protocols, signatures, adapters, or fake repositories;
- Unit of Work Protocols, implementations, or session lifecycle;
- Domain models, persistence mappers, runtime factories, or executable code;
- migrations, schema changes, roles, grants, or database behavior;
- database connections, reads, writes, transactions, or subprocesses;
- credentials, network calls, external actions, staging, release, or
  Production actions.

Those absences are enforced as exact zero-count inventories. A zero inventory
does not satisfy either ST-0308 deliverable or its acceptance criterion.

## Source and predecessor bindings

The contract binds sixteen current source artifacts by ordered repository URI,
byte count, and SHA-256. It also binds exactly twenty-one ST-0304 files as
`OPAQUE_CONTEXT_ONLY`; no table, relationship, locking, state, identity, or
other persistence semantic is projected from those bytes.

Exactly eleven ST-0105 files are bound as
`API_BINDINGS_ONLY_NOT_PERSISTENCE_DESIGN`. The only projected ST-0105 facts
come from its current manifest: its exact top-level keys, 306 source artifacts,
224 schema bindings, three OpenAPI documents, one AsyncAPI document, three
clients, 185 HTTP operations, 22 channels, 37 operations, 105 messages, and
354 generated outputs below two declared roots. Current output presence and
hash equality are recorded without claiming that the ST-0105 owner gate ran.

The known ST-0304 owner-manifest render drift and the unavailable canonical
Node/npm runtime for the ST-0105 owner gate remain outside this slice. This
reference neither repairs nor hides either boundary.

## Owned artifacts

The contract and implementation notes are owner sources. The reference-plan
JSON and manifest are generated outputs and must not be edited directly.

| Classification | Path |
| --- | --- |
| Contract source | `changes/st-0308/contracts/persistence-boundary-reference.v1.yaml` |
| Reference explanation | `changes/st-0308/PERSISTENCE-BOUNDARY-REFERENCE.md` |
| Story ExecPlan | `docs/execplans/ST-0308.md` |
| Owner generator | `scripts/build_st0308_persistence_boundary_reference.py` |
| Focused tests | `tests/st0308_reference/` |
| Generated reference plan | `changes/st-0308/generated/persistence-boundary.reference-plan.v1.json` |
| Generated inventory | `changes/st-0308/manifest.yaml` |

## Local commands

Generate the owner outputs:

```bash
uv run --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0308_persistence_boundary_reference.py
```

Verify the complete source and output tree without writing:

```bash
uv run --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0308_persistence_boundary_reference.py --check
```

The builder accepts no other arguments. It uses the pinned ST-1506 helper only
for strict YAML loading, safe repository-path resolution, output-path checks,
and atomic mode-`0644` replacement. It does not read ambient configuration,
inspect credentials, invoke a subprocess, access a database, use Git, browse,
call MCP, or access the network.

## Evidence and completion boundary

Local generation, focused pytest, formatting, typing, import/compile, canonical
import verification, workspace drift checks, and a scoped secret scan can show
only that this reference boundary is deterministic and fail closed. They are
not formal TST-005 or TST-008, PostgreSQL runtime evidence, security approval,
human approval, canonical reconciliation, acceptance evidence, staging,
release, or Production evidence.

ST-0308 runtime and acceptance readiness stay false. Dependent Stories may not
interpret these artifacts as persistence behavior or implementation authority.
