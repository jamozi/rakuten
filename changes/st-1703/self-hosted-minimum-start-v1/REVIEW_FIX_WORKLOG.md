# PR #113 exact-head review fix worklog

Scope: `ST-1703 / SELF_HOSTED_MINIMUM_START_V1` only. The first
runtime-binding implementation was reviewed at:
`7598e127adee6027d086619a720071a550b7a290`.

Runtime lineage anchor:
`b5a6157b878ca0435ee4120d33162aba5ae51f77`, the guaranteed shipped PR base.
That review commit is evidence context only and is not required to
remain in deployed squash/cherry-pick ancestry.

## Material findings addressed

1. The self-hosted launcher previously pinned filesystem metadata and Python,
   but did not bind executable repository bytes to a reviewed clean committed
   head before application imports. The fix adds a generator-owned 26-path
   runtime manifest and 657-file standard-library code inventory, a pre-Python
   sanitized Git/toolchain stage zero, complete committed-blob capture, and
   continuous shell/Python `HEAD` + blob + SHA-256 binding. The same-process
   bootstrap validates the closed manifest path set before payload reads and
   uses descriptor-relative stable reads, a verified-byte module loader, a
   closed package namespace, disabled site startup and repository-pyc
   suppression. The generator also binds both managed `bin/` path sets, the
   observed absent `._pth`/`pybuilddir.txt` startup landmarks, and an exact
   root-owned loader/library digest. The launcher invokes that loader with the
   owner-writable executable RPATH and system loader cache disabled. Drift
   fails before credential or network code.
2. `.raos-reveal` previously defaulted to hidden, so blocked or failed
   JavaScript could make editorial content disappear. The default is now
   visible. The initialized root class gates hiding/animation, and
   reduced-motion plus exception fallback retain or restore visibility.
3. The first runtime-binding revision incorrectly used the branch-local review
   implementation commit as its ancestry anchor. That would reject a reviewed
   synthetic commit, squash, or cherry-pick deployed directly above the shipped
   PR base. The generator, manifest, shell stage, and Python verifier now bind
   lineage to the guaranteed shipped base while retaining exact clean `HEAD`,
   committed-blob capture, closed byte inventory, and pre-capability refusal.
4. The fixed 26-path inventory omitted future finalized theme-image bytes, so
   a valid `FINAL` asset manifest could still leave offline doctor without the
   WebP payloads it must validate. The generator and pre-import verifier now
   derive zero to two optional rows only from the fixed committed asset
   manifest and its two exact allowlisted paths. They bind declared and actual
   SHA-256, RIFF/WEBP shape, exact tracked image inventory, pending-path absence,
   matching `HEAD` blobs, and clean working bytes. Arbitrary paths, globs,
   symlinks, undeclared tracked files, untracked/dirty bytes and stale rows fail
   closed; the current two-pending/no-image state remains unchanged.
5. The `front-page` and `single` template-part blocks and their referenced part
   root groups both requested the same semantic `header` / `footer` elements,
   creating nested duplicate landmarks. The template-part wrappers now remain
   the sole landmark owners, the part roots use presentation `div` groups, and
   the owner source check rejects either a missing wrapper landmark or a
   semantic header/footer reintroduced in a part.

## Authority and evidence boundary

This is reversible local implementation evidence. It does not execute or
authorize a credential read, provider request, draft write, theme activation,
browser action, publication, formal TST, staging, release, or Production.
Final command results and the committed head are recorded in the commit/PR
report, not promoted to any external status.

## Local verification freeze (2026-08-23)

- focused runtime/CLI/theme: `88 passed, 1 skipped`; the skip is the
  intentional exact-root launcher integration test in a linked worktree;
- complete isolated `tests/st1703`: `939 passed, 1 skipped` for the same reason;
- lineage regression imports only the shipped `b5a6157b` base into a temporary
  repository, accepts its one-commit synthetic squash descendant without the
  branch-local review object, and rejects an unrelated identical-tree `HEAD`
  before any manifest payload read even when the shipped base object is
  present;
- affected predecessor suites: `tests/st0502` `167 passed`; `tests/st0805`
  `361 passed`;
- runtime-manifest no-write check, theme source check, BusyBox/Bash syntax,
  Ruff lint/format, mypy (4 source files), and Pyright (4 source files): pass;
- workspace check, Canonical import verification, and historical WordPress.com
  runtime-manifest no-write check: pass;
- exact changed-path sensitive-data scan: 19 paths, 0 findings;
- follow-up lineage-fix changed-path sensitive-data scan: 10 paths, 0 findings;
- independent security review: no remaining material P1/P2 product-code
  finding.
- independent follow-up runtime-lineage review: `PASS`, with no remaining
  material P1 finding; Ruff/format, mypy, Pyright, and shell syntax also pass
  for the follow-up delta.
- independent finalized-theme-asset inventory security review: `PASS`, with no
  remaining material P1/P2 finding; the reviewer confirmed committed-manifest
  derivation, fixed-path closure, pending absence, descriptor-bound reads,
  clean-byte enforcement, and verified-byte doctor/theme projection.
- semantic-landmark follow-up theme source/package fixtures, runtime-manifest
  generation/no-write check, Ruff lint/format, mypy, and Pyright: pass; the
  real pending-asset package check remains closed with the expected
  `THEME_FINAL_ASSET_MISSING` reason;
- semantic-landmark follow-up changed-path sensitive-data scan: 9 paths, 0
  findings;
- independent semantic-landmark correctness/accessibility/security review:
  `PASS`, with no remaining material P1/P2 finding.

The integrated exact-root doctor, credential access, provider/network call,
draft write, browser operation, hosted CI, activation, publication, formal
TST, staging, release, and Production remain `NOT_EXECUTED`.

## Review diagnostic incident

An independent read-only review diagnostic accidentally emitted inherited
environment data into retained tool output. It performed no network call or
external write. No names or values are recorded here. Any affected credentials
must be treated as compromised and rotated or revoked. External Git/PR activity
is suspended; this slice is limited to a local atomic commit until the owner
completes that response.
