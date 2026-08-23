# ST-1703 — SELF_HOSTED_MINIMUM_START_V1

This directory owns one reversible, owner-local preparation slice for the
self-hosted site `https://kurashinoshirube.com` and brand
`暮らしのしるべ`. It is separate from the historical WordPress.com target
`kurashierabinote.wordpress.com` and does not change any historical exact-hash
handoff or artifact.

The base durable design record is `DESIGN_HANDOFF_V1.yaml`. The separate
`DESIGN_HANDOFF_V1_AMBIGUOUS_DRAFT_RECOVERY.yaml` owns only the one-use
read-before-recovery amendment. These records do not resolve the Canonical Open
Decision registry, complete ST-1703, authorize a provider call, or constitute
staging, formal TST, publication, release, or Production evidence.

## Owned boundaries

- `content/first-suitcase-comparison.v1.json` is the first self-hosted
  article packet. It is bound to the exact origin, draft-only authority, three
  provider-issued official Rakuten affiliate destinations, audit-safe Result
  V3 provenance, editorial/affiliate disclosure,
  source records, freshness caveats, and a closed SEO/structured-data policy.
  Its generated review body starts with exactly one packet-owned
  `[kurashinoshirube_first_article_lead_image]` token. The packet's source
  `content_html` may contain neither a raw image nor any shortcode; this
  preserves exact reviewed body bytes while granting no media-upload or
  `featured_media` capability.
- `theme/kurashinoshirube-child/` is the Twenty Twenty-Five child-theme source.
  The current replacement package is version `1.0.1`.
  It contains presentation only: no tracking, remote font/script/image load,
  publication, upload, taxonomy, plugin activation, or generic HTTP behavior.
  Reveal motion is progressive enhancement: content is visible without
  JavaScript and is hidden for entrance motion only after successful script
  initialization; failure and reduced-motion paths retain/restore visibility.
  The `front-page` and `single` template-part wrappers alone own the semantic
  `header` and `footer` landmarks; their part-root groups remain presentation
  `div` elements so the rendered page does not nest duplicate landmarks.
- `theme/kurashinoshirube-child/raos-assets.v1.json` owns the two final image
  requirements, closed delivery modes and prompts. The suitcase-guide image is
  delivered only by the first-article shortcode. Its handler accepts no
  attributes and permits only WordPress's empty callback forms (`null` for
  compatibility or the empty string supplied for a standalone shortcode);
  non-empty enclosing content is refused. It requires the exact raw article
  title, exact post slug,
  and active child theme, derives the URI from
  `get_stylesheet_directory_uri()`, and refuses a
  non-HTTPS/different-host/unsafe theme path or a missing, unreadable, or
  symlinked local asset. It does not guess a `/wp-content` prefix. Both images
  are `FINAL`: opaque 1600x900 static WebP files below 4 MiB with exact
  lowercase SHA-256 values recorded in the manifest. Their reviewed originals
  remain outside the repository; this encoding/finalization slice made no
  image-provider call. Every `FINAL` byte stream must satisfy the closed,
  bounded static
  WebP profile: exact RIFF length, complete chunks and odd padding, one
  structurally valid VP8/VP8L image, or one non-animated VP8X image whose
  canvas, reserved bits, feature flags and ordered chunks agree. Hash and
  magic bytes alone do not make an asset final. For lossy VP8 transparency,
  the closed profile accepts only uncompressed `ALPH` (`C=0`) with exactly one
  alpha sample per canvas pixel; compressed alpha requires a future pinned
  decoder contract and is refused.
- `.secrets/self-hosted-theme-packages/kurashinoshirube-child.zip` is the only
  theme package output. It is ignored, owner-private, and deliberately outside
  `.secrets/wordpress-owner-local/`, whose closed inventory belongs to the
  credential runtime. The package directory is mode `0700`; the regular,
  single-link ZIP is mode `0600` and at most 16 MiB. It is absent until both
  final images are present and SHA-256-bound. The generator repeatedly rebinds
  its held output-directory descriptor to that exact no-symlink path and,
  after atomic publication and directory fsync, stably reopens the ZIP and
  requires its bytes to equal the intended deterministic package.
- `.secrets/wordpress-owner-local/state/draft-recovery.v1.json` is created only
  by the explicit `recover-create-draft` operation after it proves the existing
  journal contains the exact pending first-article create. It is an
  integrity-bound, owner-private, one-use sidecar. Its presence in any valid,
  partial, failed, or terminal state permanently blocks another recovery run.
  It stores only closed state, hashes and an exact draft ID/status on success;
  it stores no credential, Authorization header, title, slug, content, URL,
  response body, browser data, or private pathname.
- `.secrets/wordpress-owner-local/state/draft-recovery.v1.guard` is the
  permanent recovery-budget tombstone. Before any recovery network access, the
  command fsyncs this owner-private single-link guard and the sidecar, while
  retaining the exact pending journal byte-for-byte through the network window
  and all controlled failure paths before an exact success transition. The
  permanent guard, sidecar and ordinary pending no-retry rule are independent
  fail-closed blockers: never remove, edit, chmod, relink or replace any of
  them.

The generated package identifies its owner through the embedded
`raos-assets.v1.json`:

- owner generator: `scripts/build_st1703_self_hosted_theme.py`
- generation command:
  `make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package`
- no-write check:
  `make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check`

Do not edit or relocate the zip by hand. Update the owned theme
source/manifest, then run the generator. The fixed ignored output means a
successful `theme-package` followed by `theme-check` does not dirty the Git
worktree or weaken the launcher's exact clean-head gate. The source-only check
is also available without creating a package:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-source-check
```

The expected result in this slice is `SOURCE_VALID` with `package_ready=true`
and the first article asset reported as `FINAL`. `create-draft` applies the
same verified theme check before credential metadata or network construction;
it cannot proceed unless both required images remain `FINAL` and the
deterministic theme package is ready.

The owner-local toolchain has no PHP executable, so this offline gate does not
claim PHP lint or WordPress runtime execution. Instead, it byte-pins the complete
handler, requires the exact strict null-or-empty PHP guard, and exercises the
same closed truth table in the deterministic Python validator tests. Actual
rendering remains part of the separately human-gated WordPress preview.

The footer contrast contract closes the expected foreground, background,
focus-outline and custom-property declarations, then binds the complete
reviewed stylesheet bytes. A later or alternate low-contrast cascade,
opacity, or browser-specific text-fill override therefore fails source
validation instead of silently defeating the reviewed state colors.

## Affiliate verification boundary

`scripts/finalize_st1703_affiliate_links.py` is the import-only read-only
verifier used by the verified exact-root runtime for the already-FINAL tracked
packet. Direct Python execution is disabled before argument parsing, repository
path resolution, shadowable imports, or private-file access; only builtin
`sys` is imported before the fixed refusal. Only the launcher supplies the
three exact owner-private request files. The verifier decodes only the bounded
bytes already obtained through its no-follow descriptor snapshot; it never
reopens a request pathname through the adapter. Its ST-1703-local closed decoder
accepts only the exact keys and reviewed values for these three slots, then uses
the existing domain request types to recompute each canonical fingerprint. This
keeps the fixed ST-0505 installed-runtime bundle unchanged. The verifier scans
only the fixed owner-local sanitized Result V3 store, reads no credential,
performs no network request, and has no tracked-file writer.

The verifier requires the exact successful 2026-07-01 item-search Result V3
record whose request fingerprint, response hash, complete Result hash and
retrieval time are already committed in each FINAL slot. It requires one
request and zero retry/pagination and exactly one matching `ace-store`
item/model record. The unchanged provider destination must be a
public HTTPS Rakuten affiliate URL whose embedded desktop target is the exact
Rakuten item path and whose mobile target is the exact reviewed item identity
for that slot. It runs the full runtime loader, compares all three exact CTA
and evidence records before private Result selection, rescans the Result store,
and proves the complete file-name/hash/inode inventory and content bytes did not
change during verification. The runtime recomputes the fixed ST-0505 request
fingerprint and requires the reviewed destination/evidence attestation digest.
An exact committed Result remains verifiable after 24 hours; this command does
not assert current product freshness or perform live re-attestation. A stable,
valid newer Result with the same request fingerprint is not selected and does
not replace the committed evidence. PENDING, a missing/replaced exact Result,
future-skewed exact committed evidence, mixed or mismatched state, manual
injection, unsafe material, or any mid-verification store mutation fails
closed. An unselected same-fingerprint Result has no authority to impose its
timestamp on the committed evidence. URLs and private result paths are never
logged, and every receipt reports `external_writes: 0`.

Verify the reviewed FINAL packet. The Make target supplies only the three fixed
owner-private request paths under `.secrets/rakuten-owner-local/requests/`;
caller-provided paths are not accepted:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile affiliate-verify
```

The JSON receipt contains hashes and counts only. This command runs through the
same exact-root, clean-HEAD, `-B -I -S`, manifest-bound launcher as doctor and
draft create. It cannot fill a PENDING packet or mutate the reviewed FINAL
packet. Run owner-private maintenance commands without another same-UID
repository/private-store mutator; this is the existing owner-local maintenance
boundary, not an additional live-provider authority.

## Runtime boundary

Every owner command is bound before RAOS imports or credential access to the
physical `/home/minami/rakuten` repository, an exact committed clean `HEAD`
descending from the guaranteed shipped PR base `b5a6157b`, and the 32 ordered
base source/input files in `runtime-manifest.v1.json`. When either of the two
fixed `required_images` records is explicitly `FINAL`, that manifest-declared,
lowercase-SHA-256-bound WebP is added to the reviewed inventory; pending images
remain absent. No glob, caller-provided path, or arbitrary manifest path can
expand the inventory. The BusyBox launcher performs the first sanitized Git
check before starting Python. It also validates the
generator-owned 657-file Python standard-library code inventory, absence of
the leading `python314.zip` import path, the pinned executable and venv config,
and the exact managed-Python/venv `bin/` path sets. Optional startup landmarks
(`._pth` and `pybuilddir.txt`) must remain absent. The executable is started
only through the hash-bound root-owned glibc loader and library set, with its
owner-writable RPATH and the system loader cache disabled. The launcher then
captures and hash-checks the complete committed CLI blob before Python is
started. The shell-stage `HEAD`, blob ID and CLI SHA-256 are carried into the
stdlib-only Python bootstrap and must match the same current `HEAD`. The
bootstrap first binds the runtime manifest to the matching `HEAD` blob, then
derives an exact 32-plus-zero-to-two path inventory from the fixed committed
asset manifest before opening any listed working payload. It checks every
bounded SHA-256, the same complete static WebP container/profile used by the
package and offline doctor, matching `HEAD` blob, the exact tracked
image-directory inventory, pending-path absence, tracked state and clean worktree before
installing the narrow self-hosted package namespaces. The fifteen leaf modules
execute only through a closed loader backed by the already verified bytes;
source paths are not reopened. Site
startup processing is disabled, live repository import roots are not added to
`sys.path`, repository bytecode lookup is redirected away from the checkout,
and bytecode writes are disabled. Any manifest, source, standard-library code,
startup landmark, managed-bin path set, dynamic-loader/library set, index,
staged, unstaged, untracked, skip-worktree, root, ancestry, stage or toolchain
drift fails closed before WordPress modules, credential values or network code
are reached. Run the launcher only while no same-UID Python/venv maintenance
process is mutating these owner-local runtime directories.

No pinned full-pixel WebP decoder exists in this stdlib-only owner runtime.
The closed validator proves container completeness and codec-header structure,
not entropy decode completion. Final visual/decode review and theme activation
therefore remain human/operator gates; a later decoder dependency would need a
separate reviewed runtime and resource-limit contract.

The manifest is generated output owned by
`scripts/build_st1703_self_hosted_runtime_manifest.py`; do not edit it by hand.
The same generator owns
`python-runtime-code-inventory.v1.sha256`; its metadata and checksum rows are
one closed artifact and must not be edited or regenerated independently.
After a reviewed runtime-source change, regenerate and then run the no-write
check from the Story-local Makefile:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile runtime-manifest-generate
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile runtime-manifest-check
```

Both operations are offline. Regeneration records bytes only; it grants no
credential, provider, publication, staging, release, or Production authority.
These two maintenance targets run the generator with the fixed root-owned
system Python in an empty environment; they do not start the owner-writable
managed Python whose startup surface they are checking.

The implementation keeps `domain <- application <- adapters/framework`:

- domain/journal values can represent `CREATE_DRAFT` and an exact-positive-ID
  future `UPDATE_DRAFT`, always with `status=draft`. Update is
  `LOCAL_INTERFACE_ONLY_ACTIVATION_DISABLED` in this slice;
- the application port exposes one draft operation and no publish, schedule,
  delete, media, taxonomy, theme, plugin, or generic HTTP capability;
- the self-hosted create adapter reuses the existing pure official WordPress
  Posts REST request/response value boundary, while credentials, HTTPS, and
  the durable journal are independent
  of the WordPress.com OAuth/numeric-site runtime;
- the outward HTTPS adapter exposes create only and rejects update before
  credential access or network construction. It uses Application Password
  Basic authentication only for the exact origin, one direct POST, system TLS,
  bounded timeouts/response
  bytes, strict JSON, no redirect/proxy inheritance, and zero retry;
- the separate recovery probe exposes one exact authenticated Posts collection
  GET only. Its fixed query uses `context=edit`, the exact candidate slug, all
  relevant post statuses, exact raw fields, one bounded page and strict total/
  page headers. It has no write method, redirect, proxy, retry, pagination or
  fallback;
- the journal durably fsyncs `INTENT` before the sole attempt and `COMMITTED`
  after strict response validation. Exact committed replay reads no credential
  and performs no network operation. Pending, ambiguous, mismatched, or
  tampered state fails closed.

## One-use ambiguous create recovery

`create-draft` has not changed: an exact pending journal still blocks and is
never replayed automatically. The only recovery surface is the distinct,
human-invoked command:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile recover-create-draft
```

Do not run it as a credential or connectivity test. Before any credential value
or network access, it requires the exact current pending `CREATE_DRAFT`, creates
and fsyncs the integrity-bound guard and sidecar under the existing journal
lock, and pins those records plus the unchanged original pending journal by
descriptor. It revalidates their exact identity, bytes, metadata, integrity and
candidate binding immediately before and after each network operation. It
performs exactly one fixed-origin official REST GET. Exactly one matching
`draft` with the same ID-safe type, slug, raw title and raw content is
reconciled to `COMMITTED` with zero POSTs. A strictly proven empty collection
permits exactly one additional invocation of the existing four-field create
POST. Only its exact success receipt is committed.

Any authentication/transport uncertainty, redirect, timeout, bad header,
pagination, malformed or oversized JSON, duplicate, nonzero mismatch, sidecar
or journal drift, crash, or ambiguous second POST leaves no replay path. A
controlled failure records a closed terminal reason when safely possible; an
interrupted partial intent or guard itself remains a permanent block, and the
original pending journal remains unchanged on controlled failure. Named state
replaced during the network window is never overwritten: terminal writes use
only the held, revalidated descriptor. An abrupt process exit during an
in-place successful journal or sidecar terminal write may leave that held inode
partial; it is not repaired or replayed automatically, and the permanent guard
still blocks every further recovery attempt. The independently durable guard
also prevents sidecar unlink or replacement from re-enabling a third POST.
Never edit, remove, chmod, relink, or replace any state file to obtain another
attempt.
The command always reports `publication_authorized=false` and
`production_eligible=false`; it cannot publish, update, delete, upload media,
or alter theme/plugin/taxonomy/publicize state. `doctor` never starts recovery.

The create request has exactly `title`, the fixed `slug`, the reviewed
generated `content`, and `status="draft"`. The slug is included in the content
binding hash, and the sole response must return that exact slug; missing or
different response state is ambiguous and is never retried. The image is not an attachment and no
`featured_media` field is sent. WordPress expands the exact leading shortcode
through the active reviewed child theme. Theme installation/activation and the
subsequent human draft preview must confirm the actual same-origin image,
exact alt text and layout; local package readiness does not attest to the live
theme or rendered URL.

Credentials are accepted only through hidden `/dev/tty` input and stored at
`.secrets/wordpress-owner-local/credentials.v1.json`. The schema is exact and
the path requires owner/current-UID, regular non-symlink storage with `0700`
directories and a `0600` file. No credential value belongs in argv,
environment variables, logs, tracked files, or chat.

The WordPress principal must be a dedicated least-privilege draft writer, not
an owner/administrator/editor account: it must have only the capabilities
needed to create its own draft and must lack publish, edit-published, delete,
media-upload, plugin/theme and administration capabilities. Role/capability
proof is an external owner gate and is not claimed by offline code.

Operational commands and status layers are documented in
`docs/runbooks/self-hosted-minimum-start.md`.
They intentionally live in the Story-local Makefile because the root Makefile
is byte/hash-bound by the active historical WordPress.com runtime inventory.
This slice does not add or replace a root Make target.

## Explicit blockers and exclusions

- The child theme is not installed or activated by this slice, and no live
  draft preview has confirmed the shortcode-rendered first-article image.
- Live read-only credential proof, draft creation or one-use recovery, theme activation,
  consent/analytics activation, human review/publication, formal
  TST-021/TST-022/TST-032, staging, release, and Production are not executed.
- The planned 14-day/five-article pilot belongs to ST-1704, not this slice.

Local unit tests and source checks are implementation evidence only. They do
not attest to the live site, external credentials, a public sitemap, theme
appearance, analytics, revenue, or Production readiness.
