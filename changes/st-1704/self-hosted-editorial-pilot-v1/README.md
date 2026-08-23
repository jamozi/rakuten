# ST-1704 self-hosted editorial pilot

This owner-local integration slice prepares exactly five evidence-led articles for
the existing `https://kurashinoshirube.com` WordPress site. It succeeds the fixed
single-article `ST-1703` path without widening or changing that runtime.

The slice owns five things:

1. five closed article/resource packets covering all MVP article types;
2. a deterministic renderer and draft-only WordPress review boundary;
3. a credential-free, allowlisted official-source capture boundary;
4. child theme 1.1.0 with the five-article editorial UI and RAOS/Yoast bridge;
5. local/CI evidence and a handoff for the remaining human-controlled actions.

It does **not** publish, activate plugins or themes, enter credentials, accept terms,
enable analytics, call a live provider without the owner gate, or claim staging,
release, or Production evidence.

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

## External action boundary

The following remain human-gated and are intentionally absent from repository
automation:

- bounded live Rakuten link/image retrieval with owner-managed credentials;
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

The Yoast lock records a local SHA-256 of the official HTTPS archive, but WordPress's
official checksum endpoint did not provide a checksum at the observation time. That
local digest is not promoted to an official checksum: plugin activation remains
blocked until a human binds an authoritative 28.3 checksum and the post-activation
Site Health readback confirms the exact persisted configuration.

The existing suitcase post is never replaced by a clone. Its reviewed draft uses a
digest-bound temporary slug, and theme 1.1.0 exposes one POST-only administrator
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
