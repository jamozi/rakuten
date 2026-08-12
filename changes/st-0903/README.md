# ST-0903 publication manifest/snapshot reference plan

## Result

This Story slice is a deterministic, source-derived, **non-executable** and
**non-authoritative** reference plan. It records the currently installed
ST-0903 surfaces without selecting a runtime design:

- no Publication Manifest or Publication Snapshot is built;
- no digest is represented as the canonical content or snapshot digest;
- no approval, artifact, job, event, audit, publication, or public projection
  is created;
- Story acceptance is `false` and readiness is `NOT_READY`;
- every runtime, TST, live, staging, release, and production result remains
  `NOT_EXECUTED`.

The generated JSON is a reference projection only. Its manifest digest is
classified as `LOCAL_GENERATION_INTEGRITY_ONLY_NONCANONICAL_NONAUDIT`; it is
not `snapshot_sha256`, an artifact attestation, approval evidence, or an audit
record.

## Why this boundary is required

ST-0903 is approved as a Story, but its installed inputs do not authorize an
executable builder. In particular:

- ST-0902 is itself a non-executable final-approval reference plan and cannot
  prove an authoritative, effective, non-revoked final approval.
- ST-0807 is a pure renderer whose caller-resolved version/hash inputs are
  opaque and non-authoritative.
- ST-0808 exposes only an admin-only recorded reference and no public renderer
  input or publication authority.
- ST-0202 defines the private local `raos-raw` bucket, not a publication
  snapshot bucket/key/retention contract; OD-014 remains unresolved.
- ST-0305, ST-0306, and ST-0307 are database candidate/role/fixture seams, not
  an accepted snapshot transaction or public projection runtime.
- ST-0601 is non-attesting and supplies no executable artifact registry.

Folder or contract presence is therefore not treated as dependency acceptance.
Both a pure executable builder and a runtime builder require a separate,
owner-approved `DESIGN_HANDOFF_V1` with no open decisions.

## Preserved unreconciled surfaces

The reference plan keeps these sources distinct:

1. `Publication Content Manifest` requires thirteen version/reference fields,
   a Content AST digest, approval refs, renderer version, and creation time.
2. `Publication Snapshot Contract` embeds renderable content, product refs,
   safe-offer generation, SEO metadata, input hashes, and its own required
   `snapshot_sha256` field.
3. `publishing.publication_snapshot` is a confidential append-only database
   row with artifact, candidate, site, source, policy, quality, approval, path,
   manifest, job, and time bindings.

No precedence, mapping, canonical byte encoding, self-hash exclusion, or
artifact-byte surface is inferred between them. The job catalog, job payload
schema, snapshot-built event, artifact reference, object-artifact row, local
storage contract, and public role boundary are projected independently for the
same reason.

## Hard gates

The plan fails closed on all of the following:

- authoritative, effective, non-revoked final approval;
- complete authoritative input aggregate;
- precedence and reconciliation of manifest, snapshot, and database shapes;
- canonical bytes, hash self-exclusion, Unicode, number, null, and ordering;
- ID/display ID/version/time allocation and replay;
- approval revocation and effectiveness at build time;
- media rights/publicability plus SEO, disclosure, methodology, product,
  safe-offer, quality, policy, source, freshness, and kill-switch binding;
- artifact/object/DB/job/event/audit/idempotency/unit-of-work/outbox/crash
  recovery;
- confidential snapshot handling and an exact public allowlist/redaction rule;
- authority for either executable builder shape.

The safe result of every unresolved gate is no build and no side effect.

## Empty records are not success evidence

Manifest, snapshot, hash, version-link, artifact, job, event, audit, approval,
and publication records are all empty and `NOT_EVALUATED`. In particular, an
empty snapshot list means:

`NO_BUILD_OR_EVIDENCE_NOT_ZERO_VALID_SNAPSHOTS`

It does not mean zero invalid snapshots, a successful validation, an approved
input, or a completed Story.

## Generation

The owning source is:

`changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml`

Generate only through:

```sh
uv run --locked --no-sync python scripts/build_st0903_publication_snapshot_reference_plan.py
```

Verify without writes through:

```sh
uv run --locked --no-sync python scripts/build_st0903_publication_snapshot_reference_plan.py --check
```

The generator pins authority, dependency, and implementation-helper bytes,
rejects duplicate/aliased YAML and duplicate-key JSON, validates the selected
Story/FR/trace/schema/job/event/security semantics, constrains repository paths
and symlinks, emits stable sanitized failures, verifies the pinned helper bytes
before its lazy import, and stages both generated outputs before replacement.
If either replacement fails, it restores the exact prior JSON/manifest pair.
It has no runtime entrypoint or import from domain/application/port/adapter code.

This dedicated worktree intentionally was not installed or synchronized. Local
verification may use the repository owner's already-hydrated pinned interpreter
from its own checkout while keeping the dedicated worktree as the command CWD.
That is local reference-plan evidence only; it does not execute TST-014,
TST-021, storage, database, browser, CI, or any live system.

## Pro assistance record

The only persisted result is `PRO_UNAVAILABLE` / `NONE`, with no proposal and
no content used. No private run identifier, response text, selector diagnostic,
or browser material is stored.

## Explicitly out of scope

- runtime/domain/application/port/adapter implementation;
- API handlers, commands, workers, jobs, events, outbox, audit, or idempotency;
- database migration/repository/unit-of-work or object-storage mutation;
- snapshot serialization, digest calculation, artifact placement, IDs, clocks,
  versions, canonical path resolution, or retry/crash behavior;
- approval/finding/waiver/quality/policy/freshness/kill-switch decisions;
- media acquisition, rights determination, or public URL/path construction;
- public read-model projection, CMS draft/publish/update/stop/rollback;
- canonical/upstream/status/generated-binding modifications;
- formal TST-014/TST-021, affected regression, live, staging, release, or
  production claims.
