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
9. The suitcase-guide WebP could become a reviewed/package-ready theme asset
   without any binding into the first article, while the create request sent no
   media or featured-image field. The content owner now generates one exact
   leading first-article shortcode into the hashed outbound body and rejects
   missing, duplicate, attributed, closing, or additional shortcode material.
   The theme owns the only renderer: it accepts no caller input, requires the
   exact raw article title, exact post slug, and active child-theme slug, derives the configured
   stylesheet URI, closes scheme/host/path and local file state, and appends
   only the manifest-bound WebP path and exact alt text. Create revalidates the
   verified theme payload and requires the article asset plus the complete
   package to be final before credential metadata or transport construction.
   No media upload, attachment, `featured_media`, guessed `/wp-content` URL,
   theme activation, live draft, or publication authority was added; actual
   visibility remains a human WordPress preview gate. Because titles are not
   unique, the follow-up binds the packet's fixed slug into the content hash
   and the four-field create body, requires the same slug in the sole response,
   and checks both raw title and raw post slug before shortcode rendering.

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

### First-article theme-asset binding follow-up freeze (2026-08-23)

- focused content/REST/journal/HTTPS/theme/CLI/runtime identity:
  `381 passed, 1 skipped`; the skip remains the intentional exact-root launcher
  integration boundary for a linked worktree;
- complete isolated `tests/st1703`: `1107 passed, 1 skipped` for the same
  reason;
- affected predecessor `tests/st0502`: `167 passed`; affected predecessor
  `tests/st0805`: `361 passed`;
- theme source check and runtime-manifest generation/no-write check: pass; the
  current two pending assets still make the real package check close with the
  expected `THEME_FINAL_ASSET_MISSING` reason;
- Ruff lint/format, mypy and Pyright pass for the seven affected source files;
  Bash and BusyBox launcher syntax remain pass. PHP lint is `NOT_EXECUTED`
  because the owner environment has no PHP executable;
- the request keeps predecessor slug absence byte-compatible, permits one
  strict create-only slug for the self-hosted path, includes it in the content
  hash, and treats missing/different/duplicate response slug as one-attempt
  ambiguous evidence with a durable pending INTENT and no resend;
- the self-hosted response validator rejects an externally supplied generic
  three-field create request, even when both that request and the response omit
  `slug`; only its exact four-field request contract reaches slug comparison;
- the child-theme handler requires both exact raw title and exact raw post slug,
  while cross-owner tests bind title, shortcode tag, post slug, theme slug,
  target origin, asset path, alt, usage and delivery constants.
- workspace check, Canonical import verification, structured JSON/YAML parsing,
  and `git diff --check`: pass;
- exact changed-path sensitive-data scan: 23 paths, 0 findings. The aggregate
  worktree scan was attempted but stopped before scanning because its
  physical-Git safety check returns `unsafe-git-metadata` in this linked
  worktree; no gate was weakened or bypassed.

The integrated exact-root doctor, credential access, provider/network call,
draft write, browser operation, hosted CI, activation, publication, formal
TST, staging, release, and Production remain `NOT_EXECUTED`.

## Final assets and affiliate completion slice (2026-08-23)

- Two already reviewed originals were mechanically encoded as opaque
  1600x900 static WebP assets, structurally validated, and bound as `FINAL` by
  exact lowercase SHA-256. The originals remain outside the repository.
- A one-way local generator recomputed the three exact ST-0505 request
  fingerprints and consumed one matching sanitized Result V3 success per
  slot from the fixed owner-local store. It made zero credential reads and
  zero network requests and printed no provider destination.
- The generator requires the reviewed 2026-07-01 item-search evidence shape,
  one request, zero retry/pagination, a unique `ace-store` model match, equal
  provider URL fields, a direct closed Rakuten destination, and fresh
  fingerprint/hash/time provenance. Partial, duplicate, stale, mismatched,
  unsafe, and manually injected states fail closed.
- The reviewed article now contains three exact CTA anchors with
  `rel="sponsored nofollow"` and the official unmodified Rakuten Developers
  credit snippet exactly once. Draft create rejects pending affiliate state
  before theme, credential metadata, or transport construction.
- No WordPress/provider/browser call, credential access, theme activation,
  draft write, publication, ST-1704 implementation, release, staging, or
  Production action was performed.

## Review diagnostic incident

An independent read-only review diagnostic accidentally emitted inherited
environment data into retained tool output. It performed no network call or
external write. No names or values are recorded here. Any affected credentials
must be treated as compromised and rotated or revoked. External Git/PR activity
is suspended; this slice is limited to a local atomic commit until the owner
completes that response.

## Affiliate verification capability-removal follow-up (2026-08-23)

- Review showed that a plain tracked-file replace could not provide an atomic
  compare-and-swap against concurrent target changes, and no Result-store
  snapshot could atomically authorize a later Git commit. The PENDING-to-FINAL
  mutation path, stage/replace/cleanup writer, and legacy upgrade were therefore
  removed instead of adding more race logic.
- `affiliate-verify` is read-only and accepts only the already-FINAL tracked
  packet. It validates a stable first Result snapshot, the full runtime packet,
  a second Result snapshot with the same store identity and three records, and
  a terminally identical content snapshot. PENDING fails closed. Success and
  failure receipts report `external_writes: 0`.
- Each final slot now carries a destination attestation over its unchanged
  provider URL and exact audit-safe evidence. The runtime recomputes the closed
  ST-0505 request fingerprint from its byte-identical closed canonical
  projection and requires the reviewed attestation digest, rejecting coherent
  destination/CTA/self-attestation mutation and arbitrary evidence hashes.
- These are local file/runtime changes only. Credential access, provider or
  network calls, WordPress/browser operations, activation, draft creation,
  publication, release, staging and Production remain outside this follow-up.

## Affiliate launcher, mobile identity and disclosure follow-up (2026-08-23)

- The affiliate verifier is now reachable only through the exact-root launcher
  with three fixed owner-private request paths. Clean committed HEAD, runtime
  manifest/code inventory, `-B -I -S`, verified source loading and verified
  content bytes all precede private request/Result reads.
- Each slot binds both its desktop model path and reviewed mobile item identity;
  the matching Result V3 `itemCode` must name that same item. Coherent alternate
  mobile targets fail closed without URL reflection.
- The FINAL article uses a present-tense affiliate disclosure. The content
  loader requires exact, mutually exclusive PENDING and FINAL disclosure text.
- The verifier remains read-only with zero credential reads, network calls,
  external writes, browser/WordPress actions and URL output.
- A final exact-head review found that the verifier module still exposed its
  predecessor standalone CLI. That parser/main capability was removed. Direct
  Python execution now emits one fixed non-reflective refusal before repository
  path resolution or private request/Result reads; only verified-loader import
  of `verify()` remains operational.
- A follow-up moved that refusal directly after the sole builtin `sys` import.
  Normal Python startup with a hostile sibling `dataclasses.py` now proves the
  shadow module, request files and Result store remain unopened before refusal.

## Immutable affiliate evidence verification follow-up (2026-08-23)

- The predecessor 24-hour Result-age limit made the immutable FINAL packet
  permanently unverifiable even though `affiliate-verify` has no writer or
  re-attestation capability. Verification now loads the reviewed FINAL packet
  first and treats its exact request fingerprint, response hash, Result hash,
  retrieval time, destination and attestation as the selection key.
- A committed Result remains valid historical evidence after 24 hours. This
  command does not claim product freshness and does not promote a newer Result.
  A stable, valid newer record with the same request fingerprint may coexist in
  the store but is not selected; removal or replacement of the exact committed
  record fails closed.
- Both Result scans now bind every file name to its raw SHA-256 and inode/file
  identity in addition to the store directory identity. Mid-run insert,
  removal, byte mutation, inode replacement or store replacement therefore
  fails before a success receipt. Future clock skew remains a closed failure.
- A final request-read review found that the adapter pathname reader reopened
  a request after the verifier had already captured descriptor-bound bytes.
  The verifier now uses an ST-1703-local closed decoder on only its original
  no-follow snapshot; swap/restore cannot substitute the fingerprint input.
  It accepts only the three reviewed exact request mappings and rebuilds the
  canonical fingerprint through the existing domain request types, leaving the
  fixed ST-0505 installed-runtime bundle unchanged.
- Future skew now applies only after a Result matches every packet-bound
  provider-evidence field. A structurally valid but unselected future-dated
  same-fingerprint Result is inventory-bound and ignored, while a future-dated
  exact committed Result still fails closed.
- The existing same-UID owner-local maintenance rule still applies: do not run
  another repository/private-store mutator concurrently. No provider call,
  credential read, external write, tracked packet writer, browser/WordPress
  action, publication, release, staging or Production authority was added.

## First-article lead-image overflow follow-up preflight (2026-08-23)

- Story and objective: ST-1703 only; keep the packet-bound 1600x900 lead image
  inside the WordPress post-content width at desktop and mobile viewports.
- Read before implementation: Canonical integration precedence, ST-1703 and
  its TST-021/TST-022/TST-032 boundaries, the self-hosted design handoff,
  theme source/package generator, runtime-manifest owner, focused theme tests,
  and the accessibility/publication constraints.
- Ambiguities and open decisions: none. This is a reversible presentation fix
  under the existing exact shortcode/theme/article/image binding; it does not
  resolve a Canonical Open Decision or alter publication authority.
- Planned files: the tracked child-theme CSS, shortcode handler and version;
  their exact source validator and focused negative tests; the minimum README
  contract note; this worklog; and the generator-owned runtime manifest.
- Planned evidence: theme source/package/check, runtime-manifest regeneration
  and no-write check, focused and complete isolated ST-1703 tests, Ruff,
  mypy, Pyright, diff checks, and a changed-path sensitive-data scan.
- Out of scope: browser/provider/WordPress access, theme installation or
  activation, draft mutation, publication, ST-1704, staging, release and
  Production. The intentional comparison-table overflow wrapper and all other
  images remain unchanged.

### Local implementation evidence

- The shortcode output now adds one unique lead-image figure class and exact
  `1600x900` intrinsic dimensions while retaining the title, slug, active
  theme, origin, URI-path, filesystem, alt and empty-content guards.
- Only that figure and its direct image receive the closed margin, max-width,
  display, width and height declarations. The existing comparison-table
  `overflow-x: auto` rule remains exact and separate. Theme version `1.0.2`
  also changes the existing enqueue version used for cache invalidation.
- The source validator binds the complete CSS and PHP bytes, the exact scoped
  top-level active rules, returned markup, enqueue-version wiring, and the
  structurally validated `1600x900` WebP canvas. Hash-rebound negative tests
  reject selector, declaration, additive cascade, inactive media placement,
  parked output literals, stale cache version, duplicate class/dimensions,
  intrinsic-dimension and responsive-scope mutations.
- Theme source/package/check passed. The ignored worktree-local package is
  212969 bytes with SHA-256
  `36601453b385acf7ed0a34a236fceeccfc8d119f827e91aa2ee971ab2cc485bb`.
- The owner generator regenerated `runtime-manifest.v1.json`; its no-write
  check passed against the final generator and tracked theme bytes.
- Focused theme tests passed (`145 passed`); focused runtime/content/CLI tests
  passed (`165 passed, 1 skipped`); complete isolated `tests/st1703` passed
  (`1275 passed, 1 skipped`). Both skips are the existing linked-worktree
  exact-root launcher boundary for post-integration verification.
- Ruff format/lint, mypy, Pyright, Python compile, `git diff --check`, and the
  project scanner over the eight exact changed paths passed; the scanner found
  zero sensitive-data findings.
- PHP lint is `NOT_EXECUTED` because no PHP executable is installed. No
  browser, provider, WordPress, credential, draft, activation or publication
  action was performed. The updated package's actual live desktop/mobile
  layout and formal TST-021/TST-022/TST-032 remain separate human/integration
  evidence and are not established by these local checks.
