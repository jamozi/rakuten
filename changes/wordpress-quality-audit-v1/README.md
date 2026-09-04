# WordPress quality audit v1

This slice separates two audit phases that cannot truthfully run at the same
time. `PRE_PUBLICATION` applies the independent two-round rule to 37 surfaces
before a proposal is created. `POST_APPLY` applies a separate, single fresh-pass
contract to production migration parity only after a release is applied. This
validator does not run WordPress, approve a review, or create clean evidence.
The tracked pre-publication ledger is deliberately `BLOCKED`; every tracked
external/live boundary remains `NOT_EXECUTED`.

The exact repository state is bound through five fingerprints: editorial and
WordPress source, the child-theme tree, local WordPress fixtures, navigation,
and the browser-audit inventory. The source group deliberately includes the
quality gates and their focused tests, plus product-media and runtime manifests;
changing a test or evidence contract therefore invalidates an earlier streak.
Each review round also binds every gate receipt to its round, reviewer, and
fingerprint bundle. Receipt, round, previous-round, contract, and ledger hashes
are recomputed by the validator. Executed evidence hashes must also be unique
across every gate and round, so a previously captured artifact cannot be copied
and relabeled as an independent rerun.

The WordPress MCP runtime manifest is a downstream consumer that hashes this
contract and tracked ledger, so it is intentionally not a quality-audit
fingerprint input. The non-cyclic generation order is: ST-1704 runtime manifest,
then this honest ledger, then the WordPress MCP runtime manifest.

Required surfaces are:

1. code, focused/full/tamper tests, publication authorization/default-off and
   kill-switch invariants, and secret detection;
2. reader-visible candidate and selection claims mapped to source-packet claims
   and locators, including packet completeness, conflicts, reproducible snapshot
   locators, every contributing locator for a multi-source claim, and required
   `llms.txt` absence;
3. explicit official evidence for negative claims such as absent, unsupported or
   not included; preservation of UNKNOWN; and superlative/difference calculations
   limited to the same scope, unit, dimension axis, model, sales state, and time;
4. natural Japanese; a first-50-word hook; one clear takeaway; a
   comparison-to-judgment-to-action story; a useful heading-only scan; deliberate
   category and internal-link intent; a closing that resolves the opening;
   the formal product name at first mention; article classification; existing
   ID/slug and no-new-post invariants; and local category-term identity;
5. on all ten articles: audience, comparison scope, writer, fact-checker, final
   verification date, no-hands-on disclosure and Who/How/Why; concrete
   responsibility without invented credentials; reader-visible AI-assistance and
   independent-audit explanations; editorial-policy and AI links;
   `contact@kurashinoshirube.com`; correction/update/history ownership; and
   byline/schema consistency;
6. independent originality and near-duplicate phrase checks across sibling and
   source text, quotation limits, attribution, and copyright-safe paraphrasing;
   third-party blogs are limited to discovering candidate/selection axes, never
   converted into editorial hands-on experience or recommendation evidence;
   quotes must be explicit and minimal; a third-party report must identify the
   exact model, publisher, publication/check dates, use conditions, original
   HTTPS URL and an exact locator. It can never become recommendation evidence,
   this site's Review label, or a `best` claim. An editorial hands-on label
   requires direct use plus acquisition, provision/loan state, conflict,
   duration, environment, method and original-device evidence. The formal
   `editorial-evidence.schema.json`, current ten-article non-hands-on register,
   and repository validator reject missing fields. Review or AggregateRating
   schema is prohibited for non-hands-on articles;
7. operational contact deliverability, inbox ownership, correction triage and
   escalation, bounce monitoring, response ownership, and execution of update
   history, with assumptions kept distinct from proof;
8. search-intent ownership, cannibalization and orphan detection, plus deliberate
   primary-secondary internal routes;
9. the currently blocked 0/33 final-product seven-axis due-diligence state;
   reader/audit-material product-name and sales-state consistency;
   product-by-product use fit, Japan warranty, maintenance, consumables/repair,
   model-end/successor status; and no-buy/keep-existing conclusions;
10. for every cross-brand article: multi-brand `official_category_sources`;
    selected+external candidate universe with current direct peers separated from
    lifecycle references; non-arbitrary four-slot compression; same-axis,
    reader-visible exclusion tradeoffs; zero price/reward/Rakuten selection
    weight; and no dominant direct peer excluded only for role overlap;
11. product-specific safety/important-notice/compatibility/Japan-warranty
    locators and a recall-query receipt recording query, period and ambiguity;
    generic safety pages cannot pass, and `NONE_FOUND` is only an observation,
    never proof that a product is safe;
12. smart-device app/cloud/account dependency, offline degradation, data flow,
    privacy, security-update/vulnerability commitments, and app/cloud/device EOL;
13. Japan-specific official battery/large-appliance disposal, recycling and
    collection duties, battery removal, damaged-cell handling, and transport;
14. claim expiry, sales/specification/recall/warranty/model-end/successor
    revalidation triggers, named maintenance owner and cadence, snapshot expiry,
    and consumables/repair continuity;
15. comparison independence and conflict disclosure; proof-before-action CTA
    order, count, density, prominence, neutral labels, equal exposure for all
    selected products, and dark-pattern absence;
16. clear affiliate or nonaffiliate monetization-status disclosure at the start
    of every article (a global notice alone is insufficient), copyright/image
    rights provenance, and controls against product misidentification;
17. WordPress REST-to-DB-to-REST/HTML content round-trip; KSES/Gutenberg
    preservation of required class, data, ARIA, `details`, table and CTA
    attributes; source-snapshot reconstruction; deterministic generation;
    acyclic predecessor/successor lineage; semantic-independent runtime
    revisions; and manifest completeness;
18. checksum-bound WordPress backup/restore in a fresh local environment,
    content/theme/plugin/options rollback, same-fixture resync idempotency,
    RPO/RTO evidence, deterministic post-restore verification, cache/CDN
    invalidation, and proof that stale HTML is no longer served;
19. Yoast checksum/version pinning, plugin/theme/package provenance, parent-theme,
    PHP and WordPress version compatibility, and dependency supply-chain
    integrity;
20. author/date/tag/media-attachment/feed/REST exposure and indexability, XML
    sitemap and robots, pagination/home/legacy canonical behavior, one
    title/description/OG/Twitter set on each core URL, HTML language,
    timezone/date formatting, and JSON-LD relations, including rejection of
    Product/Offer/Review claims;
21. local/production policy-profile isolation and the accuracy of operator,
    contact, Cookie UI, and retention statements;
22. actual cookie and browser-storage behavior, analytics default-off state,
    consent withdrawal, data minimization, and retention accuracy;
23. responsive UI, axe, keyboard/focus, reduced motion, 200% text zoom, contrast,
    screen-reader table-header relationships, and image/control accessible names;
24. cognitive accessibility and Japanese readability, including understandable
    labels, decision aids, heading length, repeated CTA pressure, and cognitive
    load;
25. old-slug and trailing-slash redirects, internal/external tracking,
    sponsored/nofollow rel, opener isolation, final-target, mixed-content, CSP,
    and security-header behavior;
26. 37 product-card placements covering 33 unique products, 74 CTA, and 130
    required runtime screenshots; verified image MIME/dimensions/alt and
    accessible names; fallback absence; activation freshness; exactly one hero
    per page; and runtime verification of ten article-specific header comparison
    semantics;
27. search, archive, pagination, category, and 404 behavior;
28. JavaScript and no-JavaScript behavior, console/network failures, error and
    empty states, state reset, and user recovery paths;
29. target-browser compatibility plus no-storage/no-cookie/private and
    restricted-network modes, third-party blocking, print/no-CSS information
    retention, font/image/CTA failure, and recoverable degradation; and
30. repeated mobile Lighthouse runs, median LCP/CLS/TBT thresholds, and current
    local-browser artifacts;
31. representative task-based reader research that measures correct product or
    no-buy outcomes, time to decision, misread paths, confidence and decision
    reversals; static proxies cannot pass this surface;
32. Japanese locale and measurement semantics: units, dimension axes, rounding,
    tax and sales-region scope, dates, full-/half-width notation, terminology and
    inclusive non-stereotyping language;
33. touch and gesture alternatives, portrait/landscape orientation, 400% reflow,
    target size/spacing and accidental activation, independently of keyboard and
    200% zoom;
34. the WordPress public attack/abuse surface, including runtime absence of
    comment forms/feeds and `X-Pingback`, XML-RPC and REST-user exposure, oEmbed,
    admin/auth, CORS/CSRF, uploads/MIME and debug leakage. Closed local seed
    defaults are not production proof;
35. operations and observability for broken links/availability, TLS/domain/email
    expiry, cron and updates, alert routing, incident ownership, escalation and
    rollback triggers;
36. affiliate-program and image-use terms plus destination integrity: redirect
    chains, referrer/query leakage, SKU/variant landing consistency, expiry
    detection and replacement, without asserting formal legal compliance;
37. slow-device/network request, byte, font, image, server, cache-header and
    third-party budgets, independently of median Lighthouse thresholds.

The separately mandatory `POST_APPLY` surface is production migration
parity/readback for IDs, slugs, metadata, taxonomy, options, menus, media GUIDs
and permalinks, with a dry-run diff and rollback rehearsal. Local mappings and a
completed pre-publication ledger cannot substitute for this evidence.

Each item has its own gate receipt and freshness limit. Static contracts may
support a receipt, but cannot substitute for a runtime, current-source, recovery
rehearsal, rights, or external readback that the gate requires. When that
evidence is unavailable, the surface stays `NOT_EXECUTED`/`BLOCKED` with an open
actionable finding; a generic aggregate pass is not a completion signal.
In particular, fixture HTML alone cannot pass the content-integrity gate. Local
evidence must include a real WordPress REST-to-database-to-REST/HTML round-trip
and a second identical sync, with required attributes compared after WordPress
sanitization. Production cache/CDN invalidation and production round-trip
readback remain separately `NOT_EXECUTED`; a local pass cannot promote them.
The easily obscured concerns--negative-claim/calculation semantics, editorial
accountability, originality, operational corrections contact, candidate
universe/brand blind spots, smart-device dependencies, disposal/transport,
legal/media rights, consumer safety, freshness ownership, cognitive
accessibility, dependency supply chain, browser/restricted-environment
resilience, WordPress restoration, analytics minimization, and search-intent
overlap--are deliberately separate surfaces. They cannot share a receipt or
inherit another surface's freshness. The tracked legal/media-rights surface
remains blocked because no independent review receipt exists. A future surface
pass would record the evidence review only; the fixed
`legal_review: NOT_EXECUTED` boundary means this validator does not assert
statutory compliance or a formal legal opinion.

For `consumer_safety_recall_compatibility`, a generic aggregate state such as
`EVALUATED_NOT_DIFFERENTIATING` is not product-level evidence. Safety and recall
notices, compatibility, and Japan-region warranty need product-specific official
locators. Each product also needs a structured recall search receipt with the
query, searched period, and ambiguous result; a generic safety article cannot
substitute, and `NONE_FOUND` records only what the search observed. It is not a
claim that the product is safe. The current all-ten-article safety state is
`RECHECK_REQUIRED`, not a completed review.
Receipts are stored once in the central
`product-safety-query-receipts.v1.json` owner document and keyed by exact
`(product_id, authority_kind)`. Every selected product requires a current,
hash-bound `MANUFACTURER_OFFICIAL` observation and a separate
`JAPAN_ADMINISTRATIVE_OFFICIAL` observation. Article packets declare only their
required products and authorities; they cannot embed a receipt or author their
own completion status. The tracked central document is intentionally empty, so
all selected products currently derive `BLOCKED_MISSING_RECEIPT`.
The predecessor V2 selection input also records safety, warranty/support, and
maintainability as `SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED`; its loader
rejects the former aggregate state so a downstream reader cannot accidentally
promote it to completed product evidence.
`freshness_maintenance_ownership` separately
requires consumables and repair continuity plus dated recheck triggers and an
accountable owner. An unverified item keeps its own receipt blocked and prevents
publication completion.

A pre-publication round is structurally clean only when all thirty-seven surfaces are
`EXECUTED` and `PASS`, every gate receipt is hash-valid and fresh, and there are
no open actionable findings. Every executed receipt must point beneath
`changes/wordpress-quality-audit-v1/evidence/` to its own canonical manifest in
`manifests/` and regular, non-symlink artifacts in `artifacts/`. The validator
recomputes the manifest-file hash, every artifact hash and size, the manifest
aggregate, and exact command-record/gate-result bindings. It also requires the
gate-specific evidence type declared in the contract. Manifest IDs, paths and
hashes, artifact paths and hashes, and aggregate evidence hashes cannot be
reused by another gate or round. The ledger itself is outside the evidence root
and cannot be cited as its own evidence.

Two adjacent structurally clean rounds must use identical current fingerprints
and distinct reviewer, round, receipt, manifest and artifact identities. A
blocked round or fingerprint change resets the streak. Distinct reviewer strings
are self-asserted metadata, not proof that two independent people reviewed the
work. Completion therefore also requires an Ed25519 detached signature from a
reviewer public key explicitly trusted by the tracked quality contract. The
signed canonical payload binds the trusted reviewer key and reviewer identities,
the last two round IDs/reviewer IDs/hashes, the raw audit-contract hash, current
repository-fingerprint bundle, ledger evaluation/completion time, an expiry, and
the fixed independence statement. The latest-round reviewer must be the reviewer
bound to that trusted key. The latest fingerprints must match the repository at
validation time.

Even when two signed pre-publication rounds become `COMPLETE`, their explicit
completion state is only `READY_FOR_PUBLICATION_PROPOSAL`; the same completion
object remains `production_parity_state: REQUIRED_NOT_EVALUATED`. It must never
be presented as production completion. `POST_APPLY` completion is
`PRODUCTION_PARITY_VERIFIED` and requires all nine parity checks, seven live
execution boundaries and nine distinct, non-zero evidence hashes within the
900-second freshness window.

The tracked trust store is deliberately empty. It contains no production key,
test key, caller-selected key, or private key, so the tracked baseline remains
`NOT_EXECUTED`/`BLOCKED`. Onboarding a reviewer means adding only that reviewer's
32-byte raw Ed25519 public key, canonical base64, key ID and reviewer ID to
`independent_reviewer_attestation.trusted_reviewer_keys` in the tracked contract
through normal review. Key IDs, reviewer IDs and public-key bytes must each be
unique. Test keys belong only in isolated test fixtures. A caller cannot supply a
replacement trust key on the command line.

The detached attestation interface is:

```sh
.venv/bin/python scripts/wordpress_quality_audit_v1.py validate \
  --ledger /absolute/path/to/quality-audit-ledger.v1.json \
  --attestation /absolute/owner/path/independent-reviewer-attestation.json \
  --signature /absolute/owner/path/independent-reviewer-attestation.ed25519.b64
```

Both detached inputs are mandatory as a pair and must be exact absolute paths to
regular files with no symlink component and no group/world write permission.
The JSON file is exactly `canonical_json(payload) + "\n"` and the signature file
is exactly canonical base64 plus one newline. The signature covers the canonical
JSON bytes without that newline. Payload and signature sizes are capped at 16 KiB
and 256 bytes respectively. The expiry must be later than completion, no more
than 3,600 seconds later, and still current. `completed_at` must equal the
ledger's `evaluated_at`; this prevents replaying a previously valid signature as
a new completion. Any missing key, wrong key, stale signature, changed round or
fingerprint, non-canonical JSON, unsafe path/mode, or mismatched execution state
fails closed. Only after verification may the ledger record
`independent_reviewer_attestation_verification: EXECUTED` and compute
pre-publication completion with `reviewer_attestation_verified=True`.

Validate the tracked baseline:

```sh
.venv/bin/python scripts/wordpress_quality_audit_v1.py validate
```

After an applied release, validate the separate owner-private canonical
post-apply result (this command cannot authorize a proposal):

```sh
.venv/bin/python scripts/wordpress_quality_audit_v1.py validate-post-apply \
  --result /absolute/owner/path/production-parity-result.v1.json
```

The result must bind the audit contract, pre-publication ledger and release
receipt; record the `POST_APPLY` phase; mark deployment, live read/write,
production, publication, release and migration-parity execution as `EXECUTED`;
and carry PASS plus distinct evidence hashes for ID/slug, metadata, taxonomy,
options, menus, media GUIDs, permalinks, dry-run diff and rollback rehearsal. It
must be canonical JSON in a regular, non-symlink, owner-controlled file.

Exit `0` is reserved for a valid `COMPLETE` ledger. A structurally valid but
incomplete ledger exits `2`; malformed, stale-complete, drifted, or tampered
evidence exits `69`. Current fingerprints can be inspected without mutation:

```sh
.venv/bin/python scripts/wordpress_quality_audit_v1.py fingerprints
```

`render-blocked-baseline` only prints an honest `NOT_EXECUTED` document to
stdout. `write-blocked-baseline` regenerates the tracked ledger with that same
blocked document after repository inputs change. Neither command can emit a clean
round or a reviewer signature. In the tracked `PRE_PUBLICATION` ledger,
publication, deployment, release, staging, production, and all live activity
remain fixed to `NOT_EXECUTED`. The reviewer-attestation boundary is the sole
external state that phase can promote, and only while the tracked-key signature
is supplied and valid. A separately provided `POST_APPLY` result may record only
its closed seven-boundary execution set after the live release; it cannot alter
or replace the pre-publication ledger. Formal legal review is likewise
recorded as `NOT_EXECUTED`. The assumed contact address does not replace the
separately `NOT_EXECUTED` delivery/operations test. Explicit production consent,
robots/indexability, SEO/schema, and taxonomy-term-identity readbacks remain
separate boundaries. Production content round-trip, cache/CDN invalidation,
public-attack surface, observability, affiliate destinations, and migration-
parity readbacks are also fixed external boundaries. Local fixtures, closed
comment/ping seed defaults, mappings, numeric term IDs, or address syntax are
never treated as proof of those current external states.
