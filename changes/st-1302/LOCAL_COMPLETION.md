# ST-1302 local implementation completion record

Record class: `LOCAL_IMPLEMENTATION_EVIDENCE_ONLY`.

The maximum-safe implementation owned by ST-1302 is present for the recorded
synthetic profile. It contains the domain model, inward ports, application
service, strict recorded fixture loader, process-local atomic adapter, V2
contract, deterministic owner generator, generated projection/manifest, and
focused/adversarial tests.

Local behavior implemented:

- exact reconstruction and validation of the accepted ST-1301 dry-run rows;
- explicit local preview binding without claiming canonical `preview_hash`
  equivalence;
- exact integral `Decimal` JPY, missing-value preservation, and separate
  generated/confirmed/cancelled/adjusted source statuses;
- typed recorded active-human, role, MFA, step-up, site-scope, and local
  preparer/committer separation checks;
- same-key/same-request replay, changed-request conflict rejection, and
  duplicate-source rejection;
- one process-local atomic swap producing immutable provider facts, unmapped
  commission observations, audit, and outbox-like records;
- fail-before-swap verification proving that no partial local result becomes
  visible;
- false authority and `NOT_EXECUTED` values for database, provider, network,
  publication, live, staging, release, and Production paths.

The V1 source pins were repaired only for the exact current ST-0308 contract,
plan, and manifest bytes. V1 remains non-executable. V2 is additive and does
not redefine OD-003, provider semantics, canonical event mapping, or the
canonical preview-hash contract.

Formal and external debt intentionally remains:

- OD-003 real provider evidence and attribution semantics;
- canonical resolution of the commit-job `preview_hash` inconsistency;
- durable database transaction and real outbox integration;
- live provider, TST-008, TST-030, staging, release, and Production evidence.

Those items are `NOT_EXECUTED`; none is represented as zero, pass, ready,
validated, approved, or Production-authorized. This record proposes no
Canonical status transition.

## Local verification evidence

- both ST-1302 owner generators accept their exact installed output in
  no-write `--check` mode;
- the complete ST-1302 local suite passes normally and under the repository
  network-denied wrapper: `254 passed` in each mode;
- the ST-1301 predecessor suite passes: `58 passed`;
- the ST-0308 handoff suite passes: `165 passed`, and its exact reference-plan
  suite passes: `134 passed`;
- the locally runnable ST-0305 portion reports `6 passed, 35 skipped`; every
  skip is the documented absence of exact PostgreSQL 18.4 runtime input and is
  not database or TST-008 evidence;
- focused Pyright, Ruff check/format, and strict mypy for the four runtime
  modules pass;
- both owner generators pass strict mypy with external helper imports skipped;
- canonical import verification and workspace drift verification pass;
- an exact 22-file ST-1302-owned scan through the repository secret scanner
  reports zero findings.

The broad `scan_secrets.py --worktree` command cannot traverse this linked Git
worktree and returns the inherited sanitized `unsafe-git-metadata` operational
error. The exact owned-file scan above closes the introduced sensitive-data
check without treating that environment limitation as a clean broad scan.

ST-1303 continues to bind predecessor ST-1302 bytes from its older artifact
binding commit. Its suite therefore stops at its expected `INPUT_HASH_DRIFT`
after this Story changes ST-1302-owned bytes. Rebinding and reevaluating that
downstream Story belongs to ST-1303; it is not repaired or claimed here.
