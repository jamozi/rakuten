# ST-0807 — deterministic local SEO and structured-data renderer

Classification:
`PURE_DETERMINISTIC_LOCAL_SEO_RENDERER`.

This Story implements one strict, in-memory rendering boundary over complete,
caller-resolved editorial inputs. It produces a raw-candidate-preserving local
SEO result, visible-field binding ledger, compact JSON-LD candidate, local
Structured Data Manifest projection, conditional local eligibility, and an
implementation-local digest. It performs no I/O and grants no approval,
publication, release, or production authority.

## Exact authority boundary

- The renderer pins `RAOS-CONTENT-SEO-001` version `1.0.0`, SHA-256
  `2fa67e012c67f8a6a90b39cfd64f27da9fb76534e57ebbff60ccd78ba51bb98a`.
- It pins the SEO metadata schema
  `https://schemas.raos.local/content/v1/seo-metadata.schema.json`, SHA-256
  `347820081caec76faea9d44d379b86bfacb539c69e048a55c658f3a78b2263ad`.
- It pins the Structured Data Manifest schema
  `https://schemas.raos.local/content/v1/structured-data-manifest.schema.json`,
  SHA-256
  `6a564e994b9ccfbefca62e3ef2245a56b96514ba35608ae3a1919bf27c7d312e`.
- It pins the content test matrix SHA-256
  `9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564`.
- The implementation contains the exact semantic inventories it uses and does
  not read policy, schema, registry, matrix, environment, or site configuration
  files at runtime.

The frozen Structured Data Manifest schema names enabled and disabled
top-level types. It does not canonically define a nested author-object shape.
The caller therefore resolves `Article` versus `BlogPosting`, plus the visible
author's `Person` or `Organization` kind and display name. That nested author
projection and the JSON serialization profile are implementation-local, not a
new canonical contract or inference of author kind.

## Strict input and URL boundary

The public boundary is exactly one `SeoRenderRequest`, one `SeoRenderResult`,
and one `render_seo` function. All request records are frozen, slotted,
exact-type-checked value objects. Collections must be immutable tuples. Runtime
subclasses, mutable collections, tampered wrappers, malformed closed values,
unknown or duplicate coordinates, article/version/route/hash mismatches, and
incomplete inventories fail closed with redacted finding codes.

The closed `OriginMode` is either `ROUTE_ONLY` or
`CALLER_SUPPLIED_ORIGIN`. Route-only requires `caller_origin=None`; caller
origin requires one non-null valid HTTPS origin. Contradictory mode/value pairs
fail as invalid input before rendering and expose no absolute URL. A supplied
origin is normalized only by lower-level URL validation and removal of one root
slash; it must contain a valid host, no userinfo, no non-root path, no query,
and no fragment. There is no default origin, environment lookup, DNS or network
access, allowlist decision, persistence, activation, or selected site/domain
configuration. Route-only input emits no invented absolute URL and is
conditionally ineligible.

When an origin is present, canonical and breadcrumb URLs are the exact origin
plus caller-bound routes. Current-route versus canonical-route equality remains
an explicit local candidate and ledger result. It is not HTTP, redirect,
canonical-graph, public-indexing, or deployed-route proof.

## Metadata, JSON-LD, and visible binding

The raw SEO metadata candidate is retained independently from the rendered
copy. Title and meta description are exact pass-through values: there is no
copywriting, site-name suffix, keyword invention, Article/BlogPosting inference,
site-config invention, or business-value enrichment.

Preview mode derives `noindex,nofollow` and excludes the rendered candidate
from sitemap inclusion without mutating the raw candidate. Public candidates
retain the caller's explicit index intent only when the index state, robots,
and sitemap intent are internally consistent. This is a local consistency
check and makes no claim about a live robots header, route, sitemap, index, or
search engine.

The minimal JSON-LD candidate contains only explicitly bound visible values:

- the caller-resolved `Article` or `BlogPosting` type;
- the exact visible H1 as `headline`;
- the explicit visible author kind and display name;
- supplied, visibly bound publication and modification timestamps;
- URL and `mainEntityOfPage` only when a caller origin is present;
- ordered `BreadcrumbList` positions and items only when usable absolute URLs
  can be formed; and
- optional `Organization` and `WebSite` nodes only from one complete,
  pre-resolved site projection and a caller origin.

`Product`, `Offer`, `FAQPage`, `Review`, and `AggregateRating` are recursively
forbidden. Unbound description, image, publisher, logo, `sameAs`, keywords,
price, availability, rating, offer, author, review, and other business values
are omitted and rejected if injected anywhere in the candidate tree. JSON is
compact, key-sorted, ASCII-safe, and script-context-safe. UTC timestamps use
six fractional digits and `Z`.

After generation, an independent local-profile validator compares exact graph
order, cardinality, per-node allowed shape, Article/BlogPosting type, author,
headline, dates, origin-dependent URL/mainEntity, every breadcrumb
name/item/position, and optional Organization/WebSite values against the
request. Any wrong value, allowed property in the wrong node, extra/missing or
reordered node, or enabled-type mismatch makes the manifest fail and local
eligibility false. The field ledger is calculated from the actual generated
tree, using a closed source-pointer, comparison-kind, result, and
ordered-position vocabulary; it never hardcodes a false `MATCH` for a faulted
tree. The caller's visible content hash, source hash, and profile are opaque
provenance coordinates; the renderer does not recompute them, call them
verified, inspect a DOM, or prove a publication snapshot.

## Change and external-assessment boundary

The caller supplies an explicit closed change classification. Initial or
substantive changes may advance `substantive_updated_at` to the exact visible
modification time. `PRICE_ONLY` and `NONE` may not advance it. The renderer does
not classify changes or infer price semantics.

Every external check must appear exactly once with a closed `assessor_ref` and
one state: `PASS`, `FAIL`, or `NOT_EVALUATED`. `PASS` and `FAIL` additionally
require bound evidence; `NOT_EVALUATED` requires no evidence. The caller must
pre-resolve missing or stale assessor/evidence material to `NOT_EVALUATED`; the
renderer never promotes it to `PASS`.

The exact implementation-local external inventory is title uniqueness,
canonical graph, ST-0805 policy eligibility, browser-visible equality,
substantive-change classification, route existence, HTTP 200, runtime
indexability, pause-or-redirect source state, Publication Snapshot currency,
image publicability, auth/cache/CTA behavior, affiliate `rel`, and affiliate
redirect behavior. These are separate facts rather than one ambiguous runtime
or outbound-link flag. A missing record is invalid input. A `FAIL` or
`NOT_EVALUATED` makes conditional local eligibility false while preserving the
raw candidate, external assessment, ledger, JSON-LD, manifest, and local
diagnostics. No local assessment represents actual graph, corpus, DOM, HTTP,
publication, pause, image, outbound-link, redirect, or snapshot truth.

## Deterministic local result and authority

The versioned profile is `ST0807_LOCAL_RENDER_V1`. Its compact, sorted JSON and
SHA-256 are implementation-local diagnostics only: they are noncanonical,
nonaudit, nonformal, and nonrelease artifacts. Top-level collection,
breadcrumb, robots, and external-assessment permutations that preserve
semantics produce the same local bytes and digest; authority-relevant changes
change the digest.

`origin_source` is the closed value `NONE` or
`CALLER_SUPPLIED_UNAPPROVED`. Even a supplied origin never selects or approves a
production domain. All result paths unconditionally retain
`domain_approved=false`, `production_domain_selected=false`,
`approval_authorized=false`, `publication_authorized=false`,
`release_authorized=false`, `production_authorized=false`,
`production_eligible=false`, and `formal_evidence=false`. Formal test, TST-020,
TST-022, runtime, live validation, browser, staging, release, and production
statuses remain `NOT_EXECUTED`; `browser_executed`, `staging_executed`,
`tst_020_executed`, and `tst_022_executed` also remain false.

## Local test coverage

The isolated ST-0807 suite covers both `Article` and `BlogPosting`; explicit
Person and Organization authors; route-only and caller-origin paths; exact
canonical and breadcrumb URLs; preview robots; public/noindex intent
consistency; complete optional site projection and absent projection; field
ledger bindings; explicit date, lastmod, substantive, none, and price-only
change paths; plus raw-candidate retention under external `FAIL` and
`NOT_EVALUATED`.

Every synthetic external `PASS` fixture is pre-resolved and non-semantic. It
does not execute or prove a detector, integration, browser, ST-0805 evaluator,
CT oracle, TST suite, or any live/runtime fact.

It also covers the locally applicable pure oracle portions of CT-0907 through
CT-0942 without claiming those formal labels: recursive forbidden
type/property rejection; coordinate, hash, version, mode, origin, route,
breadcrumb, and assessment duplication/mismatch; mutable collections and
runtime subclasses; hostile untrusted strings and redaction; stable
permutation-independent JSON/digest and digest sensitivity; and proof that
rendering performs no filesystem, environment, clock, random, network,
database, adapter, event, job, browser, publication, redirect, cache, CTA, or
outbound-link side effect. Every authority flag and execution-status boundary
is asserted.

## Local verification

Environment: Linux linked worktree, CPython 3.14.6, pinned uv 0.12.1, pytest
9.1.1, Ruff 0.16.1, and mypy 2.3.0. Checks were executed from
`/home/minami/rakuten/.worktrees/st-0807`, with Story suites in separate pytest
processes:

```text
env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 \
  /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  run --locked --no-sync --no-env-file \
  pytest -p no:cacheprovider -q tests/st0807
  PASS — 145 passed

same pinned command, tests/st0802
  PASS — 59 passed
same pinned command, tests/st0805
  PASS — 361 passed

same pinned command, ruff check --no-cache <exact ST-0807 Python files>
  PASS — All checks passed
same pinned command, ruff format --check --no-cache \
  <exact ST-0807 Python files>
  PASS — 6 files already formatted

env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 \
  MYPYPATH=python:tests/st0807 \
  /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  run --locked --no-sync --no-env-file \
  mypy --strict --explicit-package-bases --cache-dir=/dev/null \
  python/raos/domain/editorial/seo_renderer.py \
  tests/st0807/conftest.py \
  tests/st0807/test_contracts.py \
  tests/st0807/test_renderer.py \
  tests/st0807/test_boundaries.py \
  tests/st0807/test_negative_cases.py
  PASS — no issues in 6 source files

env -u MAKEFLAGS -u MAKEFILES \
  make --no-builtin-rules --no-builtin-variables check-workspace
  PASS — no workspace drift; 42 directories checked

scripts/python_toolchain.sh \
  --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  contract-gate
  PASS — reconstruction 306 artifacts; verifier PASS; isolated ST-0104
  166 passed in 222.74s

python3 scripts/scan_secrets.py --worktree
  OPERATIONAL ERROR in linked worktree — exit 2,
  ERROR code=unsafe-git-metadata source="."
same scanner --worktree on a non-git fallback snapshot from git archive HEAD,
overlaid with the exact seven ST-0807 files
  PASS — exit 0, no findings or output

git diff --check and git diff --cached --check
  PASS — no output
```

The secret scanner requires `.git` to be a directory before Git enumeration,
so the linked-worktree `.git` file is rejected before content scanning. The
approved fallback uses a complete temporary snapshot of tracked `HEAD`,
overlays only the seven owned files, and runs the same scanner in deterministic
non-git walk mode. It changes no scanner rule or repository file.

### Strict Pyright closure follow-up — 2026-08-15

The renderer now gives strict static types to hostile tuple, list, and mapping
contents only after the existing exact runtime-type checks accept their
containers. The post-check casts are runtime no-ops: they do not coerce, copy,
filter, or reorder a value. The recursive structured-data walk, exact JSON
comparison, field-ledger evaluation order, compact serialized bytes, digest,
public API, and fail-closed validation behavior therefore remain unchanged.
No `Any`, ignore directive, Pyright configuration change, or relaxed check is
used.

The follow-up was checked with Node 24.18.1, Pyright 1.1.411, CPython 3.14.6,
pytest 9.1.1, Ruff 0.16.1, and mypy 2.3.0. Exact file-level Pyright diagnostics
fell from 44 to zero; the same whole-project invocation fell from 122 to the
78 diagnostics owned by other Stories. The isolated ST-0807 suite remained
145 passed, Ruff check and format-check passed, and strict mypy remained clean
for the renderer and its five test modules. The ST-0802 and ST-0805 dependency
suites remained 59 and 361 passed. The mechanically affected ST-0903,
ST-0904, and ST-0905 suites passed 59, 34, and 43 tests, and each owning
generator passed its no-write check after source-first regeneration. A
standalone tracked snapshot overlaid with the exact 14 changed paths passed the
repository secret scanner inside the network-denied wrapper with no findings.

The exact owned files are:

```text
python/raos/domain/editorial/seo_renderer.py
tests/st0807/conftest.py
tests/st0807/test_contracts.py
tests/st0807/test_renderer.py
tests/st0807/test_boundaries.py
tests/st0807/test_negative_cases.py
changes/st-0807/README.md
```

Actual graph/corpus/DOM/browser/sitemap/public-indexing/HTTP/auth/cache/CTA,
outbound-link/redirect behavior, publication-snapshot currency, hosted CI,
formal TST-020/TST-022, API/adapter/job/event integration, live validation,
staging, human approval, release, publication, and production remain
`NOT_EXECUTED`. No local result or command above grants approval, publication,
release, or production authority.
