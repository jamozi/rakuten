# ST-0106 hosted Secrets high-confidence classifier — approval handoff

This document explains the inert design proposal in
`DESIGN_HANDOFF_V1_ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V1.yaml`. It is not
an approval record, implementation artifact, CI waiver, status transition,
release decision, or Production authority.

## Sole approval target

- Path: `changes/st-0106/DESIGN_HANDOFF_V1_ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V1.yaml`
- Bytes: `26930`
- SHA-256: `849705be6fba2a205275bb3c4f393f2bfb99ddd77dc30386dcf958de1344c5cf`
- Base commit: `6f8dafb511ed9492a51d7c831a3c212f8f52deae`
- Base tree: `9f263246f5aca387d30f6050b508c209eb148f1c`

The Markdown bytes are deliberately not referenced by the YAML. This one-way
relationship prevents an approval cycle. Any YAML byte change creates a new
approval target and requires this document to be updated.

## What is actually failing

The exact scanner was run in a disposable clean, non-shallow clone of the
current base over the maintained worktree, supported archives, and complete
fetched Git blob inventory. It exited 1 with 80 findings across 26 sources.
Every finding used the closed `GENERIC_CREDENTIAL` rule; no AWS, GitHub,
OpenAI, or private-key rule fired. Scanner output remained redacted.

Ten current maintained sources account for the live-tree false positives.
Historical blobs account for the remainder. The approved design therefore
forbids changing, deleting, rewriting, or allowlisting any of those sources or
objects. The classifier must be corrected uniformly for worktree, archive, and
history input.

## Approved design direction

The proposal keeps the provider-specific rules first and unchanged. Generic
assignment values then pass through closed whole-value checks before any
credential-evidence decision:

1. anchored placeholders and exact external references;
2. one exact credential-kind-specific not-real fixture grammar;
3. complete bare source expressions proven with a closed standard-library AST
   inventory, with suspicious embedded string/bytes literals rejected;
4. complete lower-case symbolic credential references;
5. deterministic high-confidence evidence for digit-bearing credentials,
   digit-free opaque credentials, or lower-case hyphenated passphrases.

Substring markers are not exemptions. A strong value containing words such as
`fake`, `sample`, `fixture`, or `example`, or containing source/reference-like
text, remains detectable. Quoted source expressions are not treated as source
expressions. No path, line, filename, extension, blob, commit, archive member,
or exact-value allowlist is permitted.

Findings continue to expose only sanitized source, line number, and closed rule
identifier. Candidate bytes, assignment bytes, surrounding source, entropy,
AST data, prompts, responses, and environment values remain forbidden from
stdout, stderr, artifacts, and documentation.

## Current Unit boundary is protected

Current main already includes the independently owner-approved ST-0101 hosted
Unit hybrid boundary through PR 46. A clean hosted-like clone at the exact base
reproduced `1897 passed, 7 deselected` with the approved non-private selector.

This proposal makes `.github/workflows/**`, `Makefile`, `pyproject.toml`, all
`tests/st0101/**`, all `changes/st-0101/**`, the network wrapper, and the CI job
wrapper immutable. It neither adds a marker nor changes a Unit selection. The
remaining implementation slice is Secrets-only.

## Pro advisory boundary

Three response imports were bound to their already-submitted ST-0106 runs.
They were classified as `PRO_ADVICE_V1` with `UNAPPROVED_ADVICE`; they grant no
authority. The third run returned `CONVERGED_NO_MATERIAL_DELTA`, so the same gap
must not be retried or rephrased. No raw request, response, gap, or UI material
is copied into the proposal.

The selected design reconciles those advisory categories with current
canonical sources, the exact-base failure inventory, the already-merged Unit
boundary, and a local in-memory feasibility prototype. The prototype changed
no repository file and is not implementation or validation evidence.

## Closed implementation slice after exact approval

The YAML and this Markdown are created before approval and become immutable
after exact approval. One detached approval record may then be added at:

`changes/st-0106/DESIGN-HANDOFF-APPROVAL-HOSTED-SECRETS-HIGH-CONFIDENCE-v1.yaml`

Implementation may modify exactly these six paths:

1. `scripts/scan_secrets.py`
2. `tests/st0106/test_secret_scanner.py`
3. `changes/st-0106/README.md`
4. `docs/execplans/ST-0106.md`
5. `docs/worklogs/ST-0106.md`
6. `README.md`

No other path may change. In particular, workflows, Make targets, toolchain or
lock files, network isolation, ST-0101, status/evidence history, canonical and
upstream sources, ZIP imports, private responses, credentials, ST-0202, and
prior ST-0106 handoffs are protected.

After approval, implementation must be delegated to the repository's pinned
`implementation_worker`. It must produce the hostile threshold and near-miss
tables, complete ST-0106 regressions, clean-clone full-history scan, protected
path/hash checks, and an independently reviewed frozen commit. Local success is
not formal TST-001/TST-002 or hosted CI evidence.

## Exact approval statement

To authorize implementation of these exact YAML bytes, reply with:

> SHA-256 849705be6fba2a205275bb3c4f393f2bfb99ddd77dc30386dcf958de1344c5cf の ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V1 handoff を承認します。
