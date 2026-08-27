# ST-1704 self-hosted editorial pilot

This owner-local integration slice prepares exactly five evidence-led articles for
the existing `https://kurashinoshirube.com` WordPress site. It succeeds the fixed
single-article `ST-1703` path without widening or changing that runtime.

The slice owns five things:

1. five closed article/resource packets covering all MVP article types;
2. a deterministic renderer and draft-only WordPress review boundary;
3. a credential-free, allowlisted official-source capture boundary;
4. child theme 1.3.3 with the five-article editorial UI and RAOS/Yoast bridge;
5. local/CI evidence and a handoff for the remaining human-controlled actions.

It does **not** publish, activate plugins or themes, enter credentials, accept terms,
enable analytics, call a live provider without the owner gate, or claim staging,
release, or Production evidence.

The 2026-08-26 editorial/UX improvement artifacts are:

- `BENCHMARK_2026-08-26.md` — ten-site observation log, twelve-axis assessment,
  public RAOS baseline, and abstracted principles;
- `DESIGN_SYSTEM.md` and `BRAND_VOICE.md` — reusable visual and editorial rules;
- `UI_REVIEW.md` and `IMPLEMENTATION_REPORT.md` — browser evidence, gate results,
  external exclusions, handoff, and rollback;
- `visual-fixtures/` — explicitly non-production home/article states; and
- `visual-evidence/` — RAOS-only public-before/local-after screenshots with source,
  viewport, HTTP status where applicable, and SHA-256. No competitor image is stored.

## Editorial portfolio

The public brand remains `暮らしのしるべ`. The umbrella category is
`暮らしの道具`, with the reader-facing clusters `移動`, `家事`, and `備え`.
The existing suitcase comparison is slot one; four new packets cover portable
power selection, small-household countertop dishwashers, Anker Solix model
differences, and compact robot-vacuum filtering.

All articles use the same decision sequence: visible disclosure, reader problem,
30-second conditional conclusion, methodology and criteria, comparison, product
cards, exclusions/cautions, primary sources, and related navigation. Product order is
editorial and never receives finance, commission, EPC, RPM, or profit inputs. Related
navigation is fixed theme chrome: it exposes only a target that is already public and
bound to its own valid RAOS snapshot, so a later human publication cannot create an
earlier broken link or mutate the article-copy hash.

## Bounded owner-authorized Rakuten capture

The owner explicitly authorized the already-installed owner-private Rakuten
credentials for the five pilot articles on 2026-08-24. The separate
`scripts/st1704_rakuten_product_capture.py` command accepts one fixed article ID and
derives every product selector, provider origin, response field, image size, and
output path from verified tracked documents. It performs no publication or
WordPress request and exposes no caller URL or generic HTTP interface. Zero or
multiple exact product identities stop the affected article.

Run it only through the isolated command in `OPERATIONS_RUNBOOK.md`. Its separate
runtime manifest remains independent from the closed five-command WordPress runtime
and leaves the ST-1703 predecessor unchanged.

## External action boundary

The following remain human-gated and are intentionally absent from repository
automation:

- bounded live Rakuten link/image retrieval beyond the exact owner-authorized capture command;
- WordPress theme and Yoast 28.3 installation/activation/configuration;
- consent or analytics changes;
- every update or publication of public content;
- rollback, release, and Production status.

Until exact Rakuten image/link evidence is present, the corresponding resource is
`PENDING` and preparation must refuse publication readiness. Missing evidence is
never replaced with a guessed URL, copied manufacturer image, screenshot, or AI
product depiction.

Official-source capture is automated separately from the WordPress runtime by
`scripts/st1704_official_source_capture.py`. It accepts only one tracked `source_ref`
or one allowlisted `article_id`, issues credential-free read-only HTTPS GET requests
to the exact registry URLs, refuses redirects and caller-selected network material,
and installs owner-private body/evidence pairs only after every reviewed claim
locator matches. It has no Rakuten, WordPress, publication, plugin, theme, media, or
generic HTTP capability. The WordPress CLI remains limited to its four closed
commands.

Run source capture only from the repository root with the repository interpreter
and the isolated, environment-free process boundary used by `CLEAN_PYTHON`:

```sh
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
  "$PWD/.venv/bin/python" -B -I -S -X pycache_prefix=/dev/null \
  scripts/st1704_official_source_capture.py capture-source \
  --source-ref SRC-ANKER-SOLIX-C300
```

The CLI verifies that exact process boundary and byte-compares the worktree
runtime manifest to its current `HEAD` blob before loading any RAOS module or
reading a registry/locator document. A direct shebang invocation is therefore a
closed refusal rather than an alternate execution path.

The four WordPress commands use the same repository-root `CLEAN_PYTHON` boundary.
For example, preparation is invoked only as:

```sh
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
  "$PWD/.venv/bin/python" -B -I -S -X pycache_prefix=/dev/null \
  scripts/st1704_self_hosted_editorial_pilot.py prepare \
  --article-id st1704-portable-power-station-guide
```

Before any RAOS import, owner credential read, journal access, DNS lookup, or HTTP
operation, the entry point verifies its exact direct-script process, standard-library
import path/root/current `HEAD`, the
committed manifest, and every listed worktree byte. It loads RAOS and the complete
generated Content AST tree only from those frozen bytes, and binds article, source,
media, theme-contract, and Content AST schema reads to the same snapshot. Only after
that verification does it append the fixed owner-safe virtual-environment
`site-packages` directory; Python `site`, `.pth`, and customization hooks are never
run. External validation dependencies load before any RAOS package exists, and every
subsequent RAOS module object remains bound to its verified source loader. Runtime
drift returns only `SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID` and cannot reach the
owner credential, journal, or network boundaries.

`create-review-draft` is the only command that can turn a freshly prepared request
into a live draft. Before its single POST, the runtime durably stores the exact
canonical request in an owner-only, no-overwrite artifact and binds that artifact's
name and SHA-256 into the live journal `INTENT`; the journal becomes `COMMITTED` only
after the response is validated. `recover-create-review-draft` loads only the sole
`INTENT`-bound artifact, and `verify-public` loads only the sole `COMMITTED`-bound
artifact. Neither command rebuilds an old public snapshot from refreshed or stale
provider files. An artifact can never authorize a new create, and an ambiguous live
journal, modified binding, or wrong lifecycle state fails closed.

The Yoast lock records a local SHA-256 of the official HTTPS archive. WordPress.org's
official per-file checksum manifest for 28.3 is now hash-bound in the lock, but the
repository cannot read the installed plugin tree. A human WordPress operator must
still verify the installed files against that official inventory, and the
post-activation Site Health readback must confirm the exact persisted configuration.
The archive digest alone is never promoted to installed-file evidence.

The existing suitcase post is never replaced by a clone. Its reviewed draft uses a
digest-bound temporary slug, and theme 1.3.3 exposes one POST-only administrator
screen that can copy only the approved title, excerpt, content, and closed snapshot
back to the exact existing public post. That screen requires an explicit nonce-bound
human action, preserves the target ID/slug/status/date/author/taxonomies, uses a
durable approval receipt/one-operation lock bound to the journal IDs and packet,
request, payload, and pre-state hashes, verifies every resulting byte, and attempts
to roll the four copied fields back on failure. Before the receipt is written, the
operator must record a 10–300 character approval reason and reauthenticate the current
WordPress user; the submitted password is used only for that check and is not stored.
The non-autoloaded receipt also retains the exact old title, excerpt, content, snapshot,
and preserved invariants as a crash-recovery artifact. If an installed save hook changes
a preserved invariant, the action fails visibly; the retained receipt artifact and the
WordPress revision are the manual recovery sources. The CLI cannot invoke this screen
and still has no public update or publish command.

`REVENUE_UNBLOCK_WORKLOG.md` records the sanitized 2026-08-26 containment handoff.
The additive
`../carry-on-single-url-evidence-loop-v1/` overlay closes the read-only carry-on
evidence loop: `verify-public` now requires the exact derived Review URL to be an
anonymous 404 with no redirect, its anonymous public REST projection to be empty,
all home-page hrefs and both post/page sitemaps to exclude `raos-review-*`, and the
clean canonical to appear exactly once in the post sitemap and never in the page
sitemap. Its existing authenticated owner boundary must find retained AT-003 Draft
post ID 26 exactly and zero Draft rows for the other four promoted Review
slugs. Each Review-surface evidence digest binds path, status, content type,
`Location`, REST count headers, and body SHA-256; a nominal 404 containing committed
article fragments, including snapshot JSON interior, payload SHA-256,
HTML-entity-encoded text, and high-signal shortened CTA fragments, is rejected.
Article fragments use visible text rather than HTML attributes; snapshot comparison
excludes only windows or tokens wholly contained in the expected clean canonical URL.
Review routes are strictly percent-decoded once across authority, path, query, and
fragment; malformed, ambiguous, and double-encoded variants fail closed on home and
sitemap surfaces.

AT-003's current owner journal is terminal `RECOVERY_ATTEMPTED`, so ordinary
`verify-public` remains unavailable and `COMMITTED`-only. The separate
`verify-carry-on-single-url` command reads only the worklog-fixed immutable artifact,
public post ID 19, and Review Draft ID 26 without creating or locking journal state.
Its output is explicitly `formal_gate_eligible=false`,
`reconciliation_status=PENDING_HUMAN_EXCEPTION`, and never Production evidence. No
redirect or deletion authority is added. The adapter exposes only the dedicated
`CarryOnSingleUrlReconciliationEvidence` result, whose invariants keep
`public_surface_verified=false` and `strict_public_checks_passed=true`; its internal
strict `PublicVerification` is not returned.
After a final URL is human-published and verified, use
`REVENUE_EXPERIMENT_RUNBOOK.md` with the existing owner-private affiliate-learning
V2 interface; neither document grants live mutation authority.
