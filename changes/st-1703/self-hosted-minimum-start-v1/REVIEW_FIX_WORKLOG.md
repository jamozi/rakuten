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
6. The theme package previously targeted an unignored Story-local `generated`
   path. A successful package would therefore make the launcher's exact Git
   clean-head gate reject every later owner command. The fixed output is now
   the ignored, owner-private
   `.secrets/self-hosted-theme-packages/kurashinoshirube-child.zip`, separate
   from the credential directory, with closed directory/file modes and the
   existing atomic/fsync protections. Package followed by no-write check now
   leaves the launcher Git-status predicate clean without weakening it.
   Follow-up hostile-filesystem review found directory-rename and same-inode,
   same-size staging-content races. The writer now terminally rebinds its held
   directory to the exact fixed path and stably reopens the published ZIP after
   replace/fsync to require the intended bytes before reporting success.
7. Global indigo links and warm hover/focus colors had insufficient contrast
   on the dark footer. Footer-scoped normal/visited paper and
   hover/active/focus light-warm colors now exceed AA contrast on both the
   footer and filled-button backgrounds, and focus-visible keeps a contrasting
   outline plus the existing width and offset. A follow-up review demonstrated
   that a later equal-specificity declaration could override the reviewed
   block. Additional review reproduced inline custom-property, higher-specificity
   background, opacity, and browser-specific text-fill bypasses. The source
   validator now closes foreground, background, focus-outline and custom-property
   inventories and binds the complete reviewed stylesheet bytes, rejecting all
   of those exact cascade/effective-color bypasses.
8. FINAL image acceptance previously stopped at SHA-256 plus the first twelve
   RIFF/WEBP bytes. A truncated, size-inconsistent, incomplete, mis-padded, or
   structurally invalid codec container could therefore become package-ready
   when its manifest hash matched. Theme source/package, runtime-manifest
   maintenance, pre-import runtime and verified-byte offline doctor now apply
   the same bounded static single-image profile: exact RIFF size, complete
   maximum-16-chunk walk, zero odd padding, valid VP8/VP8L headers, or a
   non-animated VP8X header whose canvas, flags and ordered chunks agree. The
   VP8X+VP8 alpha profile is limited to uncompressed `ALPH` (`C=0`) and requires
   exactly one sample byte per canvas pixel; compressed alpha is refused
   without a pinned decoder. The
   fixed positive fixtures were decoder-confirmed before capture; no decoder
   executable or native library was added to the owner runtime. The validator
   attests to complete container/header structure, not full entropy decode, so
   final visual/decode review and activation remain operator gates.

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

### Private-package and footer-contrast follow-up freeze (2026-08-23)

- focused theme/CLI: `66 passed, 1 skipped`; the skip remains the intentional
  exact-root launcher integration boundary for a linked worktree;
- complete isolated `tests/st1703`: `961 passed, 1 skipped` for the same reason;
- the synthetic finalized-asset flow proves deterministic package/check,
  ignored clean-head compatibility, exact private modes/path, atomic fsync
  ordering, directory terminal rebinding, and final intended-byte comparison;
- hostile tests reject ancestor/leaf symlinks, wrong modes, hardlinks,
  directories, FIFO, oversized output, stale stage, target swaps, directory
  renames, and same-inode/same-size stage mutation;
- calculated foreground/background contrast plus exact reviewed CSS-byte tests
  reject low-contrast direct, later, inline, higher-specificity, opacity,
  browser-specific text-fill, background, and focus-outline mutations;
- runtime-manifest generation/no-write check, theme source check, Ruff
  lint/format, mypy, Pyright, Bash/BusyBox syntax, workspace check, Canonical
  import verification, and `git diff --check`: pass;
- exact changed-path sensitive-data scan: 10 paths, 0 findings;
- the real asset/package check remains closed with the expected
  `THEME_FINAL_ASSET_MISSING`; no package was written in the worktree.

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
