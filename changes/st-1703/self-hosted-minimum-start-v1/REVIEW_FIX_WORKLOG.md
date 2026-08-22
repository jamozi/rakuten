# PR #113 exact-head review fix worklog

Scope: `ST-1703 / SELF_HOSTED_MINIMUM_START_V1` only. Review baseline:
`7598e127adee6027d086619a720071a550b7a290`.

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

## Authority and evidence boundary

This is reversible local implementation evidence. It does not execute or
authorize a credential read, provider request, draft write, theme activation,
browser action, publication, formal TST, staging, release, or Production.
Final command results and the committed head are recorded in the commit/PR
report, not promoted to any external status.

## Local verification freeze (2026-08-23)

- focused runtime/CLI/theme/content: `79 passed, 1 skipped`; the skip is the
  intentional exact-root launcher integration test in a linked worktree;
- complete isolated `tests/st1703`: `907 passed, 1 skipped` for the same reason;
- affected predecessor suites: `tests/st0502` `167 passed`; `tests/st0805`
  `361 passed`;
- runtime-manifest no-write check, theme source check, BusyBox/Bash syntax,
  Ruff lint/format, mypy (4 source files), and Pyright (4 source files): pass;
- workspace check, Canonical import verification, and historical WordPress.com
  runtime-manifest no-write check: pass;
- exact changed-path sensitive-data scan: 19 paths, 0 findings;
- independent security review: no remaining material P1/P2 product-code
  finding.

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
