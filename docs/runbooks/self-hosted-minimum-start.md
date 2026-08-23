# Self-hosted Minimum Start — owner-local runbook

## Purpose and exact target

This runbook separates the owner-local preparation for
`https://kurashinoshirube.com` (`暮らしのしるべ`) from the existing
WordPress.com workflow for `kurashierabinote.wordpress.com`. Never use a
`wordpresscom-*` command for the self-hosted site, and never substitute a
different origin, route, proxy, numeric site ID, or credential scheme.

This implementation can prepare one review draft only. It cannot publish,
schedule, delete, upload media, change taxonomy, activate a theme/plugin,
enable tracking, or make a generic HTTP request. Human publication remains a
separate WordPress dashboard action after editorial and legal review.

Run operational commands only from the physical root `/home/minami/rakuten`.
Linked worktrees are for development/testing and are intentionally refused by
the launcher.
The launcher requires the exact clean `HEAD` to descend from the guaranteed
shipped PR base `b5a6157b878ca0435ee4120d33162aba5ae51f77`; it does not require
a branch-local review implementation commit that can disappear during squash
or cherry-pick integration. It also refuses staged/unstaged/untracked drift, a
runtime-manifest mismatch, a non-`HEAD` runtime blob, or an unsafe pinned
toolchain. This binding happens before RAOS imports, credential reads, or
network construction. Do not bypass it or use Git index flags to hide an edit.
The inventory has 31 fixed base paths and zero to two optional image paths.
Optional paths are not caller input: they can only be the two exact WebP paths
declared by the committed `raos-assets.v1.json`, and are included only when the
corresponding record is `FINAL` with a matching lowercase SHA-256. A pending
image must be absent. Unlisted, tracked, untracked, dirty, symlinked, malformed,
missing, or hash-mismatched image state is refused before any RAOS import.
For `FINAL`, malformed includes a RIFF-size mismatch, truncated/incomplete or
mis-padded chunk, more than 16 chunks, unknown/duplicate/misordered image
chunks, invalid VP8/VP8L headers, or invalid/animated/inconsistent VP8X state.
Before Python starts, the launcher also verifies the generator-owned standard
library code inventory, the absent `python314.zip` import path, the pinned
executable/venv config, both managed `bin/` path sets, absent optional
`._pth`/`pybuilddir.txt` startup landmarks, the root-owned loader/library set,
and a fully captured committed CLI blob. Python is launched through that
pinned loader with the executable RPATH and loader cache disabled. Its stage
`HEAD`, blob ID and SHA-256 must continue into the same-process verifier. A
Python reinstall, standard-library source change, managed-bin entry change,
startup-landmark change, system loader/library update, or venv config change is
a closed maintenance event: inspect it, regenerate through the Story target
and review the resulting inventory diff; never regenerate merely to bypass
drift. Do not run the launcher concurrently with a same-UID Python/venv
maintenance process.
All examples use the Story-local
`changes/st-1703/self-hosted-minimum-start-v1/Makefile`. The root Makefile has
no self-hosted target because it remains byte/hash-bound by the active
historical WordPress.com runtime inventory.

The read-only affiliate evidence check uses the same exact-root launcher and
does not accept caller-selected files. Install the three owner-only request
records as mode `0600` regular single-link files in the fixed
`.secrets/rakuten-owner-local/requests/` directory (mode `0700`), then run:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile affiliate-verify
```

The launcher refuses dirty/untracked state or runtime drift before Python, and
the verified CLI refuses content drift before reading those request records.
The check is read-only: it performs no provider, browser, or WordPress call and
never prints affiliate URLs. Do not invoke the verifier module with Python
directly: direct execution is intentionally disabled before argv or private
files are inspected. The refusal imports only builtin `sys` before it runs, so
a dirty or untracked shadow module beside the script cannot execute first.
Only the exact-root launcher has operational access.

## Evidence and action layers

These states are independent. Never promote an earlier layer into a later
claim.

| Layer | Meaning in this slice | Current state |
| --- | --- | --- |
| Offline/local ready | Content contract and theme source can be checked without secrets or network | Implemented; affiliate slots and both images are locally final |
| Credential metadata ready | Exact fixed file exists with trusted owner/type/mode/size metadata; values are not read | Owner action pending |
| Live read-only proof | Credentials and exact site route are proven through an explicit read-only provider action | No command implemented; `NOT_EXECUTED` |
| Draft write | One create protected by durable INTENT/COMMITTED journal; live update is disabled | Implemented interface; separate owner operation, `NOT_EXECUTED` here |
| Theme activation | Packaged child theme is installed and activated with Twenty Twenty-Five present | Human operator gate; not executed |
| Human publication | Owner reviews disclosures, facts, links, layout, privacy and then publishes | Human owner gate; `NOT_EXECUTED` |
| Formal staging/TST | Required environment and TST-021/TST-022/TST-032 evidence exists | `NOT_EXECUTED` |
| Production | Canonical production, security, approval and release gates are satisfied | Not claimed and not authorized by this slice |

The absence of a live read-only probe is intentional: this slice does not add
a second credential-using capability without a reviewed need. Offline doctor
output is never proof that the Application Password works or that the live
site accepts the fixed REST route.

## 1. Offline doctor

After integrating a reviewed runtime-source change into the exact root, first
confirm the generator-owned inventory without writing:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile runtime-manifest-check
```

`runtime-manifest-generate` is repository maintenance for the implementation
owner, not a daily recovery command. Never regenerate merely to make unknown
or unreviewed drift pass. Manifest check and doctor results are local evidence
only. The two manifest maintenance targets use the fixed root-owned system
Python in a sanitized empty environment so the check does not first execute
the owner-writable managed-Python startup surface it is intended to inventory.

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile doctor
```

The doctor reads repository content and credential **metadata only**. It does
not read username/password bytes, perform DNS/HTTP, mutate WordPress, package
or activate the theme, enable analytics, or publish. The affiliate and image
blockers are absent only while all three reviewed provider links and both
hash-bound WebP assets remain valid. Before credential installation, the
remaining expected blocker is `WORDPRESS_CREDENTIAL_INSTALL_REQUIRED`.

`LOCAL_READY`, if reached later, is still only local evidence and grants no
provider-call or publication authority.

## 2. Theme source and final-asset gate

The source-only, read-only check is:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-source-check
```

The current expected state is `SOURCE_VALID`, both assets `FINAL`, and
`package_ready=true`. The two closed prompts are in
`changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/raos-assets.v1.json`.
They require original, unbranded editorial visuals; a placeholder, product
logo, recognizable product, or fabricated use scene must not be marked final.
The source check also enforces one `header` and one `footer` landmark per
template: the `front-page` and `single` template-part wrappers own those
semantic elements, while the referenced part-root groups remain `div`.

The accepted image profile is a bounded static single-image WebP. The source,
package, runtime-manifest generator, pre-import launcher and offline doctor all
require an exact RIFF length, complete chunk walk and zero odd-byte padding,
then a structurally valid VP8/VP8L image or a non-animated VP8X image with
matching canvas, feature flags and ordered chunks. Matching SHA-256 and the
first twelve RIFF/WEBP bytes are not sufficient. This stdlib-only runtime has
no pinned full decoder. Lossy alpha is therefore accepted only as
uncompressed `ALPH` (`C=0`) with one byte per canvas pixel; compressed alpha is
refused rather than partially parsed. The check does not claim that every
entropy-coded pixel was decoded. Human review must still open the exact final
files in a trusted local viewer before committing them and before manual
activation.

The two reviewed originals have been mechanically encoded as opaque 1600x900
static WebP files and are lowercase-SHA-256-bound in the manifest. The
originals remain outside the repository. To build and verify the deterministic
owner-private package, use:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check
```

Both commands use the fixed ignored owner-private output
`.secrets/self-hosted-theme-packages/kurashinoshirube-child.zip`. The package
directory must remain current-owner mode `0700`, and the ZIP current-owner
mode `0600`, regular, single-link, non-empty, and at most 16 MiB. Do not place
it inside `.secrets/wordpress-owner-local/`; that directory has a separate
closed credential/state inventory. A successful package/check sequence leaves
`git status --porcelain=v1 --untracked-files=all` empty, so a later exact-head
`doctor` or separately authorized `create-draft` is not refused merely because
the reviewed theme package exists. Directory identity is rebound to the exact
fixed path before and after publication; after atomic replace and parent fsync,
the bounded no-follow ZIP is stably reopened and must equal the intended bytes.
A directory rename or same-size staging mutation therefore returns a closed
failure rather than a misleading successful package hash.

After the source and final images are reviewed and committed, regenerate and
review `runtime-manifest.v1.json`; its inventory will add exactly those
manifest-declared `FINAL` WebP paths. Never add image rows manually or use
another filename. `PENDING_FINAL_ASSET` continues to require that its path does
not exist.

The package generator is deterministic and the check is no-write. Never edit
the generated zip manually. Theme installation and activation remain manual
operator actions after visual/mobile/accessibility review; neither command
contacts WordPress. Install and activate the exact package before the separate
draft-create operation, because the first-article image is rendered by that
child theme rather than uploaded to the media library.

The footer-specific link states override the global link color on the dark
footer: paper for normal/visited, light warm for hover/active/focus-visible,
with the same light-warm focus outline. Keep these scoped colors and the
global focus width/offset. The source check closes the relevant foreground,
background, focus-outline and custom-property declarations and binds the
complete reviewed stylesheet bytes. The contrast regressions therefore reject
direct drift as well as later cascade, opacity, or browser-specific text-fill
overrides back to a low-contrast rendering.

## 3. Credential metadata setup

Create a dedicated least-privilege WordPress draft-writer principal and its
Application Password through WordPress administration. Do not use an
owner/administrator/editor credential. The principal must be limited to
creating its own drafts and must lack publish, edit-published, delete,
media-upload, plugin/theme, user-management and administration capabilities.
Role/capability proof is a live owner security gate; offline doctor cannot
attest to it. Do not send the credential in chat or place it
in shell history, argv, environment variables, a repository file, clipboard
automation log, or a generic secret path.

Use only the hidden controlling-terminal installer:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile install-credentials
```

It prompts through `/dev/tty` with echo disabled and exclusively creates:

```text
.secrets/wordpress-owner-local/credentials.v1.json
```

Required storage is current-owner, non-symlink, regular JSON with `0700`
directories, `0600` file, bounded size, and exactly the fixed origin, username,
and Application Password fields. The installer does not overwrite an existing
file. Re-run the offline doctor after installation; it still does not read the
values.

Credential creation, rotation, revocation, and deletion are owner security
operations outside this repository slice. Do not edit or print the JSON to
repair it.

## 4. First article and affiliate evidence

The owned packet is
`changes/st-1703/self-hosted-minimum-start-v1/content/first-suitcase-comparison.v1.json`.
It contains:

- one exact lead-image binding whose generated body begins with
  `[kurashinoshirube_first_article_lead_image]` exactly once;
- sourced facts and separately labeled editorial interpretation;
- no claimed first-person purchase/use experience;
- affiliate and AI-assistance/editorial-policy disclosures;
- price, inventory, point, campaign and freshness caveats;
- three exact finalized slots for ACE クレスタ 06316, ace.TOKYO LABEL
  ディフェレンス 05721, and PROTECA マックスパス4 01471, each bound to
  sanitized Result V3 fingerprint/hash/time provenance and one reviewed
  destination/evidence attestation digest;
- direct Rakuten affiliate URL policy and required
  `rel="sponsored nofollow"`;
- Article/BreadcrumbList SEO metadata requirements and explicit rejection of
  fabricated Product, Review, AggregateRating, or FAQPage markup.

Commission/rate, price, points, inventory and revenue must not influence the
ranking. The packet contains unchanged provider-issued destinations and the
official unmodified Rakuten Developers credit snippet exactly once. It has no
pending marker.

The read-only local verifier consumes three exact owner-private request files,
recomputes their ST-0505 fingerprints, and scans only the fixed sanitized
Result V3 store. It reads no credential, makes no network request, never prints
a destination URL or private result path, and reports `external_writes: 0`.
It rejects PENDING, zero/duplicate, stale, mixed, fingerprint-mismatched,
non-HTTPS, non-Rakuten/RAOS redirect, wrong item/shop/model, URL mutation, and
manual/generic injection. Each mobile target must identify the exact reviewed
Result V3 item for its slot. The full packet loader independently requires the
closed request fingerprints, exact state-specific disclosure and
destination/evidence attestations. A second
Result-store scan and terminal content reread must reproduce the same snapshot.
The command cannot finalize or otherwise mutate a packet. Run it against the
already-FINAL packet using only the fixed owner-private request paths:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile affiliate-verify
```

The lead-image token is part of the exact content hash sent to WordPress. The
packet validator rejects a missing, moved/duplicated, attributed, closing, or
additional shortcode and continues to reject raw `<img>` markup. The theme
handler accepts no caller-selected URL/path/alt. It renders only for the exact
raw first-article title and exact `carry-on-suitcase-comparison` post slug while
the exact child theme is active, derives the URL
from WordPress's configured stylesheet directory, requires HTTPS and the exact
`kurashinoshirube.com` host, and appends only
`assets/images/article-suitcase-guide.webp` with the reviewed alt text. A
different article/theme/origin, unsafe content-directory path, missing file, or
symlink produces no image. There is no media upload, attachment ID,
`featured_media`, or assumed `/wp-content` public prefix.

## 5. Draft create — separate owner operation

Only after both manifest assets are `FINAL`, deterministic package/check has
passed, the exact child theme has been manually installed and activated, the
owner separately decides to contact the exact live site, no other writer is
active, credential metadata is trusted, and journal state has been reviewed,
the fixed command is:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile create-draft
```

Create uses `POST` only because that is the official Posts REST draft
operation. The request body has exactly title, fixed slug, reviewed content,
and `status="draft"`. The slug participates in the content hash, and the
response must return the same exact slug. A missing/different/duplicate slug is
an ambiguous post-write outcome and is never retried. The transport attempts
once, follows no redirect, inherits
no proxy, and performs no automatic retry or path fallback.

Before credential metadata or transport construction, create revalidates the
reviewed content bytes and the verified theme inventory, including the
first-article asset's `FINAL` status and complete package readiness. This is a
local byte/readiness gate only; it does not prove that the live theme is active
or that WordPress rendered the shortcode.

Recovery rules are strict:

- exact `COMMITTED` replay returns the stored sanitized receipt without
  reading credentials or contacting WordPress;
- `INTENT`, ambiguous response, timeout after attempt, response mismatch,
  journal mismatch, or tamper means stop; never issue a second request;
- do not delete/edit the journal to force a resend.

The journal stores only operation/content hashes, exact draft ID, draft
status, and response hash. It stores no credential, title, content, or response
body.

API update is deliberately absent from the operational surface. The local
domain/journal keeps an exact-positive-ID update value only as a future
interface contract with state
`LOCAL_INTERFACE_ONLY_ACTIVATION_DISABLED`; the official HTTPS adapter rejects
it before credential access/network construction, and CLI/Make expose no
update command. Improvements remain proposal/diff output and the owner applies
any edit manually in the WordPress dashboard before publication.

## 6. Human site controls

After a real draft, the owner
must review in WordPress at minimum:

- the exact target site, `draft` state, title/body, disclosures and three
  destinations;
- the suitcase guide image is visible above the reviewed body, its actual
  `src` is HTTPS and same-origin under the active
  `kurashinoshirube-child` stylesheet directory, and its alt text exactly
  matches the packet/manifest; absence or drift is corrected manually in the
  dashboard without replaying the create request;
- source accuracy/freshness and the separation of facts from editorial
  interpretation;
- canonical URL, meta title/description, visible breadcrumbs and only
  evidence-supported structured data;
- desktop/mobile layout, keyboard focus, contrast, reduced motion, alt text,
  heading/table semantics and link affordance;
- content remains visible when JavaScript is blocked or fails, while reveal
  motion starts only after the theme script initializes successfully;
- About, advertising/editorial policy, privacy, contact/subscription and error
  paths.

Consent banner/configuration, GA4, and Search Console/Site Kit activation are
human privacy/operator gates. Nonessential tracking must remain disabled until
the consent configuration has been reviewed. The theme contains no tracker or
remote script and does not activate a plugin.

Any observation of `/wp-sitemap.xml`, browser rendering, HTTPS, redirects,
indexing, consent behavior, or analytics is a dated live observation only. It
does not prove this implementation fixed or activated that behavior; repeat
external verification is required after the relevant human site change.

## 7. Remaining gates

The following remain outside this local slice: live credential proof; real
draft create; theme installation/activation and browser preview;
consent/GA4/Search Console activation; legal
and editorial review; human publication; ST-1704's 14-day/five-article pilot;
formal TST-021/TST-022/TST-032; hosted CI; staging; release; revenue evidence;
and Production.

Do not label local pytest/source-check results as any of those states.
