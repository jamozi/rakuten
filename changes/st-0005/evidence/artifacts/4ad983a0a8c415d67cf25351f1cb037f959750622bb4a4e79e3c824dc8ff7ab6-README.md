# RAOS design source of truth

This directory is the repository import of **RAOS Complete Design Package
v1.0** (baseline 2026-07-30). It was imported by `ST-0001`; importing the
design does not mean that the RAOS product, runtime tests, provider
integrations, or production environment are implemented.

## Layout

- [`canonical/`](canonical/) contains the v1.0 master, integration, UI,
  analytics, security, test, operations, backlog, Codex, and reference
  artifacts.
- [`upstream/`](upstream/) contains the six original v0.1 design packages,
  selected source documents, and accepted-but-not-applied proposal patches.
- [`manifest.json`](manifest.json) maps every original package path to its
  repository path and records the expected size and SHA-256 digest.

Files below `canonical/` and `upstream/` are immutable imported evidence. Do
not edit them in place. A correction or adopted design change must be added as
a new versioned artifact, migration, contract, or decision so that the
original remains auditable.

The repository layout deliberately separates the original package's
`upstream/` tree from the v1.0 canonical tree. Package-relative paths are
preserved in `manifest.json`, and the verifier applies that mapping when it
checks the original `SHA256SUMS.txt`.

## Required reading order

Before selecting or implementing a story, read:

1. [`canonical/00_master/RAOS_MASTER_README_v1.0.md`](canonical/00_master/RAOS_MASTER_README_v1.0.md)
2. [`canonical/08_codex/AGENTS.md`](canonical/08_codex/AGENTS.md)
3. [`canonical/01_integration/RAOS_07_integration_design_v1.0.md`](canonical/01_integration/RAOS_07_integration_design_v1.0.md)
4. [`canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml`](canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml)
5. [`canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml`](canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml)
6. [`canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml`](canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml)
7. [`canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml`](canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml)
8. The selected story's `design_refs`, contracts, test suites, security
   controls, and operations references.

For conflicts, use the precedence in
[`RAOS-INTEGRATION-001`](canonical/01_integration/RAOS_07_integration_design_v1.0.md):
current law and official provider/platform terms; integration decisions and
status sources; requirements and hard constraints; current domain designs;
generated contracts; then implementation code. Never silently resolve an
open decision.

## Integrity verification

From the repository root, run:

```bash
python3 scripts/import_raos_design.py verify
```

The command fails if:

- a source archive changed;
- a standalone 01-05 package differs from the copy embedded in the complete
  package;
- an imported file is missing, added, replaced, or converted to a symlink;
- size or SHA-256 differs from `docs/manifest.json`;
- a package checksum differs from the original `SHA256SUMS.txt`; or
- the imported package manifest is not RAOS v1.0.

The importer refuses to overwrite an existing destination. Import a future
design baseline as a new version instead of mutating this one.
