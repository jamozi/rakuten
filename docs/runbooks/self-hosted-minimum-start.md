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
The inventory has 26 fixed base paths and zero to two optional image paths.
Optional paths are not caller input: they can only be the two exact WebP paths
declared by the committed `raos-assets.v1.json`, and are included only when the
corresponding record is `FINAL` with a matching lowercase SHA-256. A pending
image must be absent. Unlisted, tracked, untracked, dirty, symlinked, malformed,
missing, or hash-mismatched image state is refused before any RAOS import.
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

## Evidence and action layers

These states are independent. Never promote an earlier layer into a later
claim.

| Layer | Meaning in this slice | Current state |
| --- | --- | --- |
| Offline/local ready | Content contract and theme source can be checked without secrets or network | Implemented; final affiliate/image blockers remain visible |
| Credential metadata ready | Exact fixed file exists with trusted owner/type/mode/size metadata; values are not read | Owner action pending |
| Live read-only proof | Credentials and exact site route are proven through an explicit read-only provider action | No command implemented; `NOT_EXECUTED` |
| Draft write | One create protected by durable INTENT/COMMITTED journal; live update is disabled | Implemented interface; separate owner operation, `NOT_EXECUTED` here |
| Theme activation | Packaged child theme is installed and activated with Twenty Twenty-Five present | Human operator gate; final images/package pending |
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
or activate the theme, enable analytics, or publish. Expected blockers before
launch are:

- `AFFILIATE_SLOTS_PENDING` until all three official Rakuten destinations are
  separately completed and validated;
- `FINAL_THEME_ASSETS_MISSING` until both final editorial WebP files are
  generated under the separate external/cost gate and hash-bound;
- `WORDPRESS_CREDENTIAL_INSTALL_REQUIRED` until the owner performs the hidden
  installer.

`LOCAL_READY`, if reached later, is still only local evidence and grants no
provider-call or publication authority.

## 2. Theme source and final-asset gate

The source-only, read-only check is:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-source-check
```

The current expected state is `SOURCE_VALID`, `PENDING_FINAL_ASSETS`, and
`package_ready=false`. The two closed prompts are in
`changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/raos-assets.v1.json`.
They require original, unbranded editorial visuals; a placeholder, product
logo, recognizable product, or fabricated use scene must not be marked final.

Image generation is an external/cost action and is not authorized by this
runbook. After a separately approved process supplies the two real WebP files,
record each exact SHA-256 and change its manifest state to `FINAL`, then use:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check
```

After the source and final images are reviewed and committed, regenerate and
review `runtime-manifest.v1.json`; its inventory will add exactly those
manifest-declared `FINAL` WebP paths. Never add image rows manually or use
another filename. `PENDING_FINAL_ASSET` continues to require that its path does
not exist.

The package generator is deterministic and the check is no-write. Never edit
the generated zip manually. Theme installation and activation remain manual
operator actions after visual/mobile/accessibility review; neither command
contacts WordPress.

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

## 4. First article and affiliate blocker

The owned packet is
`changes/st-1703/self-hosted-minimum-start-v1/content/first-suitcase-comparison.v1.json`.
It contains:

- sourced facts and separately labeled editorial interpretation;
- no claimed first-person purchase/use experience;
- affiliate and AI-assistance/editorial-policy disclosures;
- price, inventory, point, campaign and freshness caveats;
- three exact pending slots for ACE クレスタ 06316, ace.TOKYO LABEL
  ディフェレンス 05721, and PROTECA マックスパス4 01471;
- direct Rakuten affiliate URL policy and required
  `rel="sponsored nofollow"`;
- Article/BreadcrumbList SEO metadata requirements and explicit rejection of
  fabricated Product, Review, AggregateRating, or FAQPage markup.

Commission/rate, price, points, inventory and revenue must not influence the
ranking. Official affiliate destinations and current product facts require a
separately reviewed completion step; this slice intentionally does not invent
them. A review draft may contain the visible pending markers, but it is not
publication-ready while any marker remains.

## 5. Draft create — separate owner operation

Only after the owner separately decides to contact the exact live site, no
other writer is active, credential metadata is trusted, and journal state has
been reviewed, the fixed commands are:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile create-draft
```

Create uses `POST` only because that is the official Posts REST draft
operation. The request body has exactly title, content, and
`status="draft"`. The transport attempts once, follows no redirect, inherits
no proxy, and performs no automatic retry or path fallback.

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

After a real draft and separately completed affiliate/assets work, the owner
must review in WordPress at minimum:

- the exact target site, `draft` state, title/body, disclosures and three
  destinations;
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
draft create; official affiliate-link completion; final image generation;
theme installation/activation; consent/GA4/Search Console activation; legal
and editorial review; human publication; ST-1704's 14-day/five-article pilot;
formal TST-021/TST-022/TST-032; hosted CI; staging; release; revenue evidence;
and Production.

Do not label local pytest/source-check results as any of those states.
