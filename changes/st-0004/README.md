# ST-0004 content canonical revision

This bundle implements formal canonical decision `INT-DEC-005`, with
`INT-DEC-006` recorded separately as the supporting Content Repository/CMS
authority decision, on the hash-pinned ST-0003 v0.3 candidate.
It is an implementation candidate for later installation by ST-0104/ST-0301;
it is not a production migration, CMS integration, publication approval, or
release.

## Build

Run from the repository root:

```bash
python3 scripts/build_st0004_revision.py
python3 scripts/build_st0004_revision.py --check
```

The CLI accepts only the owned `changes/st-0004` destination. It verifies the
complete ST-0003 manifest inventory and pinned RAOS-CONTENT-001 package/proposal
hashes, renders the complete generated tree in sibling staging, and restores
the previous owned tree if installation fails. `--check` rebuilds in a
temporary directory and fails on any missing, unexpected, or changed generated
artifact.

## Source and generated ownership

Source-owned artifacts are edited directly and recorded by the manifest:

- `scripts/build_st0004_revision.py`;
- this `README.md`;
- the six versioned files under `database/`;
- `database/forward-recovery.md`.

Generated artifacts are owned exclusively by the builder and must not be
edited in place:

- `job-state.v1.yaml`, copied byte-for-byte from ST-0003;
- `contracts/**`, the complete self-contained v0.4 contract candidate;
- `manifest.yaml`, which records every immutable input, source artifact, and
  generated artifact with its byte length and SHA-256 digest.

The expected source inventory is nine artifacts. The generated count is not a
fixed documentation constant; the manifest is authoritative after generation.

## Immutable inputs and adoption boundary

The predecessor is `RAOS-AI-GOVERNANCE-REVISION-001@0.3`. Its pinned manifest
SHA-256 is
`142d27a392ab5ecd2362327d231c9f8ea2a8d716e3f6fcd7bb15440697a50482`.
The builder verifies that manifest and every artifact it declares before
reading any candidate contract. The carried Job-state contract must retain
SHA-256
`9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a`.

The RAOS-CONTENT-001 archive has 111 regular members and 110 checksum
declarations; the checksum inventory excludes itself. A build must reject
unsafe, duplicate, case-fold-colliding, undeclared, missing, or hash-mismatched
members. The accepted frozen contract corpus contains exactly 77 artifacts:

- 18 top-level artifacts: 16 machine-readable content
  master/catalog/policy/implementation YAML documents and two CSV matrices;
- 33 Draft 2020-12 JSON Schemas, including 24 content Block schemas;
- five article templates;
- 21 fixture-area artifacts: five valid JSON fixtures, 15 invalid JSON
  fixtures, and `fixtures/invalid/expected_results.yaml`;
- a generated canonical-adoption document that binds the frozen content
  corpus to the v0.4 DB/API/AI revision. This generated document is not part of
  the 77-artifact frozen count.

Frozen RAOS_05 and RAOS_06 catalogs, schemas, templates, and fixtures remain
byte-identical. Integration uses new v0.4 registries, wrappers, and resource
contracts rather than rewriting a frozen artifact in place.

## Database checkpoints

Apply and record each file as a separate checkpoint:

1. `202607300013_content_expand.sql` adds additive content tables, nullable
   bindings, migration-window guards, and fail-closed ACLs atomically.
2. `202607300014_content_expand_validate.sql` validates constraints outside the
   Expand transaction and creates side-by-side indexes concurrently with exact
   preflight and postflight definition checks.
3. Repeat `202607300015_content_migrate_batch.sql` until its automatic backlog
   is zero. Each transaction processes at most 1,000 rows. It never guesses an
   article type, methodology, schema, SEO, disclosure, or manifest binding;
   unresolved rows remain visible for evidence-based operator classification.
4. Deploy canonical-compatible writers only after that classification, then
   run `202607300016_content_contract_prepare.sql` to assert readiness and add
   `NOT VALID` required-field checks for new writes.
5. Run `202607300017_content_contract.sql` to validate prepared constraints and
   perform only the short metadata contract, canonical rename/index, and
   nullability changes.
6. Use `202607300018_content_guarded_downgrade.sql` only as a separate,
   explicitly requested recovery checkpoint. It refuses data loss and must
   restore the exact ST-0003 database shape before reporting success.

The reusable migration runner/history/advisory-lock ABI belongs to ST-0301.
Do not concatenate these checkpoints into one transaction. Read
`database/forward-recovery.md` before recovery or downgrade. Once Contract
begins, forward recovery is the default; a downgrade refusal must never be
bypassed by deleting content, evidence, approval, or publication provenance.

## Contract contents

The generated candidate contains:

- the complete verified ST-0003 contract set promoted to v0.4 without losing
  any predecessor schema, operation, event, or security invariant;
- frozen RAOS-CONTENT-001 catalogs, schemas, templates, and fixtures with their
  original hashes;
- formal Article Type, Content Schema, Template, Methodology, SEO, Structured
  Data, Media, First-hand Experience, Review, Disclosure, and Publication
  Manifest resource contracts;
- ten API resources and ten commands backed by 11 database tables;
- 19 additive OpenAPI operations: 15 Admin operations `ED-016` through
  `ED-030` and four Internal operations `INT-005` through `INT-008`, with
  strict schemas, OIDC scopes, RFC 9457 errors, Idempotency-Key on commands,
  and If-Match/ETag on mutable resources;
- content bindings for the eight affected AI tasks, expressed as versioned
  input/output constraints without changing frozen RAOS_05 artifacts;
- seven v0.4 root contract/catalog revisions. AsyncAPI carries no new event,
  channel, operation, message, or event schema and declares
  `x-raos-wire-change: NONE`;
- the public OpenAPI copied byte-for-byte from the immutable v0.1 contract with
  SHA-256
  `8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797`.

No content, evidence, finance, AI, review, or editorial-internal field is added
to the public contract.

## Proposal, CMS, and publication boundary

The following accepted design deltas remain `PROPOSAL_ONLY` evidence:

- `RAOS_06_001_data_alignment_patch_v0.1.sql`;
- `RAOS_06_002_api_alignment_patch_v0.1.yaml`;
- `RAOS_06_003_ai_alignment_patch_v0.1.yaml`.

They are hash-pinned and retained for provenance but are never executed,
copied as migrations, or treated as runtime configuration. Only the formal
versioned SQL and generated v0.4 contracts in this bundle are candidates for a
later installer.

Under supporting decision `INT-DEC-006`, RAOS's structured Content Repository
remains the content source of truth. A CMS, including WordPress, is only a
publication adapter. This story performs no
CMS navigation or write, creates no draft, and cannot publish, unpublish, or
approve content. Any publication action remains behind an explicit human
approval gate and its owning release/publication story.

## Handoff and status boundary

- ST-0005 installs the aggregate status workflow; until then, status is
  proposed only in the story work log.
- ST-0104 installs this hash-pinned contract bundle.
- ST-0105 generates Python/TypeScript types and clients.
- ST-0301 binds these SQL payloads to the migration runner/history/lock ABI.
- ST-0701 and later AI stories load and enforce the content task bindings.
- ST-0801 and later content stories implement runtime loaders, validators,
  renderers, review workflows, and publication manifests.

The current story state is `IMPLEMENTED_NOT_VALIDATED`. Local implementation
verification passed: importer verification, build, `--check`, Ruff, and
`py_compile` reported `PASS`, while Pyright reported `0 errors`. With
`RAOS_PG_BIN` selecting PostgreSQL 18.3, `tests/st0004` reported `64 passed`;
database coverage comprised 11 static tests, five live tests, and
behavior/lifecycle coverage. Independent audit regressions cover declared
OAuth scopes, templated path parameters, command idempotency, human-only and
distinct-reviewer gates, active-human testers and binders, media provenance,
and the frozen methodology/AST/traceability invariants. Compatibility checks
confirmed that the public OpenAPI and Job-state artifacts remain
byte-identical to their pinned inputs.

This is artifact-local implementation evidence only and does not modify the
canonical aggregate Registry/backlog. Formal CI `TST-002`, `TST-003`,
`TST-008`, and `TST-020`, PostgreSQL 18.4, application HTTP integration,
staging, CMS integration, publication approval, and production deployment
remain `NOT_EXECUTED`.
