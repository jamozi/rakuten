# Editorial V3 portfolio and owner-private economics

`editorial-portfolio.v3.json` is an additive, generated successor to Editorial
V2. It covers the current ten articles and thirty-three products without changing
the historical V2 contract. `generated/navigation.v3.json` is the single
machine-readable home/related-article source.

`editorial-identities.v1.json` also classifies every existing article as a
category guide, brand/model-family comparison, constraint shortlist, feature
shortlist, or two-product comparison. The generated navigation carries the
reader-facing Japanese role label, the exact comparison scope, and a broader
article route for narrow comparisons so a narrow article cannot silently pose
as a market-wide ranking. It also owns the primary query intent: intents must
be unique within an intent group and the browser audit requires the visible
`記事分類` and `この記事で答えること` values to match this contract exactly.

`market-candidate-audit.v1.json` is the named-candidate negative-space audit.
It records all seven selection axes, concrete current or recently excluded
models, lifecycle evidence, exclusion reasons, and scope separation for all ten
articles. Each article declares non-empty hard filters and official category
sources. Each named candidate binds an exact model and variant scope, use role,
separate model/variant lifecycle, reader-visible and embedded lifecycle
observations, and an `EXCLUDED` or `DEFERRED` disposition. Products already in
the portfolio reuse their product identity through a `REFERENCE_ONLY` binding
to the article that actually includes them; they are never duplicated as
`EXT-*` candidates. The selected product list is the included disposition. The
reader-visible lifecycle governs the effective state; an embedded mismatch is
recorded as `CONFLICT`. `RESTOCK_NOTIFICATION_ONLY` records the narrower case
where the visible store offers only a restock notice and no cart action; it is
kept distinct from an explicit `SOLD_OUT` statement. Generic unnamed alternatives,
audits containing only already-selected products, decision-critical unknowns,
missing reader-visible exclusions, and price/reward/Rakuten weighting are
rejected by the V3 generator.

Article-wide guidance does not establish product-specific due diligence. The
market audit therefore mirrors the current V2 selection audit: safety/recall,
Japan-region warranty/support, and maintenance/repair/consumables remain
`SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED` until every selected product
is bound to locator-backed official evidence. Each incomplete axis has a
recheck date, is excluded from recommendation rationale, and blocks strict
publication. The generator rejects an article-level official link being
promoted to product-level completion.

The tracked Rakuten parser boundary is intentionally disabled. It contains no
guessed live column names or status values. A parser can be enabled only inside
`.secrets/editorial-portfolio-v3/` after a sanitized real export sample is
detected, mapped, owner-attested, and shown to echo one of the twenty
owner-private provider IDs bound to a logical provider slot. The private
directory must be mode `0700`; every input and output file must be mode `0600`.

## Deterministic generation

```sh
.venv/bin/python scripts/build_editorial_portfolio_v3.py
.venv/bin/python scripts/build_editorial_portfolio_v3.py --check
```

## Standard API publication (selected for the current release)

Use `standard-api` for publication without article/placement-level provider
measurement. All 33 products, 37 images and 74 CTA occurrences still require
fresh, exact evidence. Reuse of a provider-returned URL is permitted; the 74
internal CTA identities remain distinct. No provider ID is inferred or added.
API verification is recorded separately from human attestation.

Acquire missing identities using the current source contract while retaining
credentials and provider responses exclusively in the saved checkout:

```sh
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
  .venv/bin/python -B scripts/raos_editorial_portfolio_v2.py \
  discover-identities --owner-checkout /home/minami/rakuten
```

The result distinguishes complete unique matches, ambiguous/partial searches,
no exact matches, request failures, and invalid evidence. An empty API search is
not missing owner input. API query syntax may omit a one-byte token while exact
identity matching retains it; the receipt records both model and actual query.
This diagnostic alone does not verify the affiliate URL, image bytes, official
JAN, sales state or safety evidence, and cannot authorize publication.

The V2 capture command now searches unresolved model identities. It resolves a
complete unique result, then independently fetches the exact item, affiliate URL
and image. Different models, bundles, used products, incomplete result pages and
multiple matches do not become verified. Only unresolved exceptions need input;
the 15-row and 74-row manual worksheets are not prerequisites for this mode.

After API capture and complete V2 local/production materialization:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  standard-api --output standard-api-publication.json
.venv/bin/python scripts/raos_wordpress_publication_request.py --articles all \
  --link-mode standard-api --standard-api-receipt <absolute-private-receipt> \
  --quality-audit-attestation <absolute-private-attestation> \
  --quality-audit-signature <absolute-private-signature>
```

For the explicitly owner-selected Codex technical review policy, replace the two
signed-audit arguments with `--quality-audit-mode codex-owner` and
`--codex-audit-report <absolute-owner-private-codex-report>`. This does not waive
the two clean review rounds, any product/source/runtime evidence, or the owner's
separate wp-admin approval. It is not a signed human-independent audit; see
`changes/wordpress-quality-audit-v1/README.md` for the exact report contract.

The API receipt replays product/safety evidence and both materializations. It is
not a measurement activation or publication approval. The publication command
still requires local audit, the explicitly selected audit policy, separate
wp-admin approval and verified readback. Measurement remains OFF; the measurement plugin
apply receipt is not required in this mode. Local preview uses
`RAOS_WORDPRESS_LINK_MODE=standard-api` and does not install/activate a measurement
plugin. Existing inactive/default-OFF installations are not removed.

Omitting `--link-mode` preserves `measured-admin` compatibility. Mixing receipt
families is rejected, never silently downgraded. The workflow below describes
only the optional measured-admin mode, not a required step for API publication.

## Rakuten attribution contract (measured-admin only)

Rakuten provider attribution is deliberately narrower than the internal CTA
model. The ten articles each have one `product_card` slot and one
`final_summary` slot, for exactly twenty provider slots named
`rps-{article_code}-{card|final}`. The seventy-four CTA bindings remain distinct
internal CTA/Money Link identities in the explicit `RAOS_INTERNAL_CTA_V1`
namespace, using `icta_{article_code}_{product_code}_{card|final}`. These
internal identities are never provider measurement IDs. Rakuten Direct reward
is attributable only to article plus placement; a
product or individual CTA must never be inferred from the provider ID. Product
and CTA dimensions remain available only as first-party/GA4 identities and as
Money Link product-identity evidence.

Actual Rakuten measurement IDs and the complete provider-slot binding belong
only in the mode-`0700` owner-private root and mode-`0600` files. They must not be
copied into Git, chat, tracked artifacts, standalone HTML data attributes, or
safe receipts. Owner-private materialization may consume only an opaque,
finalized Money Link URL; it must never reconstruct that URL or expose the
provider ID separately. Any token shape within an owner-private provider ID is
opaque and carries no product-attribution meaning. A saved pilot is neither
provider verification nor authority to activate, publish, or enable the
measurement gate.

## Private Rakuten workflow

Editorial V2 owns the full ten-article, thirty-three-product and seventy-four-CTA
capture contract. Development preview may render a clearly labelled manufacturer
link together with the visible non-image state `商品画像未確認・購入導線停止`,
but that incomplete fallback is never a successful completion or production
candidate. Article-level or neutral visuals are never reused as product images.
The strict gate requires every product identity registered by the current V2 owner contract,
all 37 product-card image occurrences and all 74 CTA occurrences to be
`verified`; it also requires zero neutral images and zero manufacturer-link
fallbacks. Measurement collection remains disabled by default.

Run the URL-free readiness diagnostic after capture:

```sh
.venv/bin/python scripts/raos_editorial_portfolio_v2.py validate-readiness
.venv/bin/python scripts/raos_editorial_portfolio_v2.py materialize-local \
  --require-complete
.venv/bin/python scripts/raos_editorial_portfolio_v2.py materialize-production
```

The current tracked registry leaves these fifteen identities unset. API discovery
must verify them; unresolved exceptions must not be guessed:

- `PRD-PROTECA-TRI-AIR-01541`
- `PRD-ANKER-SOLIX-C800`
- `PRD-JACKERY-1000-NEW-V3`
- `PRD-DJI-POWER-1000-V2`
- `PRD-THANKO-RAKUA-MINI-TK-MDW22W`
- `PRD-TOSHIBA-DWS-33B-W`
- `PRD-EUFY-AUTOEMPTY-C10-T2292`
- `PRD-ECOVACS-DEEBOT-MINI2`
- `PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171`
- `PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002`
- `PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549`
- `PRD-BERMAS-INTER-CITY-III-60570`
- `PRD-SIROCA-SS-M171`
- `PRD-BLUETTI-AORA30-V2`
- `PRD-BLUETTI-AORA100-V2`

After all product evidence is complete, generate the 74-row Money Link mapping
template without credentials or live calls. The template is deliberately
invalid for activation (`destination_url` is null and the copied flag is false)
until the owner copies every exact Money Link from Rakuten administration:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" \
  money-link-template --output money-links.json
```

After filling all 74 distinct URLs and setting only
`urls_copied_from_rakuten_admin` to true, validate the mapping and generate the
hash-bound administrator/CSV receipt template:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" \
  admin-receipt-template --money-link-mapping money-links.json \
  --output admin-receipt.json
```

The owner must then copy the CSV-echoed measurement ID and representative model
for every row, perform the two identity checks, set the verification booleans
and attestation, and retain `production_publication_authorized: false`. Activation
validates the exact 74-row set, unique HTTPS Money Link URLs, product/model
identity receipt, mapping hash, 24-hour product evidence and 15-minute V2
materialization window before writing URL-free receipts and private overlays:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" activate \
  --money-link-mapping money-links.json --admin-receipt admin-receipt.json \
  --dry-run-output rakuten-activation-dry-run.json
```

No command in this sequence authorizes publication or enables measurement.

Place a sanitized real sample in the private directory, then run:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-detect \
  --sample rakuten-sample.csv --encoding cp932 --delimiter comma \
  --output rakuten-detection.json
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-binding-template \
  --detection rakuten-detection.json --output rakuten-binding.json
```

Detection treats a provider CSV as one or more blank-line-delimited rectangular
sections. Edit only the private binding file: bind the intended report table by
its exact `section_index`, `header_row_index`, and `section_sha256`; map its
exact headers and observed status values; select the amount/date formats; and
fill the complete twenty-slot provider-ID mapping. Set both verification
booleans to `true` only after owner verification and keep the file mode `0600`.
Bind the profile and dry-run the owner-private, potentially unanonymized full
export:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-bind-profile \
  --sample rakuten-sample.csv --detection rakuten-detection.json \
  --binding rakuten-binding.json --output rakuten-profile.json
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-dry-run \
  --report rakuten-report.csv --profile rakuten-profile.json \
  --output rakuten-dry-run.json
```

Commit requires the displayed Rakuten row count and pending/confirmed/cancelled
totals, plus the exact dry-run source hash. The section-bound profile consumes
only the selected table and rejects a changed section position or header. A
changed file, duplicate row, unknown status, formula-like cell, header drift, or
total mismatch fails closed. Only exact owner-private IDs bound to the twenty
provider slots are Direct; unmatched IDs remain Unattributed and the provider
import never creates Estimated attribution. Raw rows and every unanonymized CSV
remain owner-private throughout this workflow.

## Cost and baseline inputs

`cost-template` creates all ten owner-private rows. The owner must fill the
period, approved hourly cost, actual editorial minutes, actual variable cost,
and set `owner_attested` to `true`. Missing or unverified cost keeps contribution
profit `UNAVAILABLE`; an explicit attested zero remains zero.

The optional GSC/GA4 files use the live Google adapter source-record boundary:
`schema_version: 1`, `source`, `site_id`, `date_from`, `date_to`, `retrieved_at`,
`request_sha256`, `row_count`, and `rows`. GA4 additionally includes
`configuration`. GA4 dimensions/metrics serialize as arrays of
`{"name": ..., "value": ...}`. Raw GSC queries remain private and are never
copied into the JSON/HTML baseline report.

Materialize the fixed Google bindings only after placing two different Google
service-account key files and the corresponding administrator readbacks at
`google/{gsc|ga4}/{service-account.json|admin-readback.v1.json}` below the
mode-`0700` private root. Every file and any existing output must be mode
`0600`; symlinks and hard links are refused. The existing owner-local site UUID
is read from the fixed mode-`0600` `google/local-scope.v1.json` receipt, and the
numeric GA4 property ID is read from and cross-checked against the strict GA4
administrator readback. Neither identifier is accepted on the command line.
The GSC resource is fixed in the implementation to the domain property for this
site:

```sh
.venv/bin/python scripts/raos_google_owner_private_v1.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3"
```

The command requires both credentials to declare the same GCP project and
different `client_email` identities. It writes the exact provider
`binding.v1.json` files by atomic replacement, then writes
`google/binding-receipt.v1.json` last as the completion marker; all three are
mode `0600`. Before replacing either binding, it atomically invalidates an
earlier completion marker with a `MATERIALIZING` state. A crash or write failure
therefore leaves a generation that the live loader cannot consume. The loader
accepts only a completed receipt whose canonical binding and administrator
readback hashes, same-project/distinct-service-account co-hashes, exact
read-only semantics, and site UUID all match the files it securely reopened.
The receipt contains no credential, project, email, or GA4 property ID. It
records no separate-admin approval and grants no authority to publish, alter
provider configuration, or enable a measurement gate.

The two administrator inputs are strict V1 readbacks, not arbitrary JSON. GSC
must report the exact domain resource once as `RESTRICTED`, read back through
the service account, and not be an owner. GA4 must bind the readback's numeric
property and canonical property resource, a numeric account, the exact site
origin, JPY, a service-account Viewer that is not an administrator, and exactly
the six required `EVENT` custom dimensions with one successful row each. The
sanitized receipt co-hashes each validated readback with its private binding,
project hash, and service-account email hash, but deliberately does not claim
that the readback document itself cryptographically names the service account.

`refresh-baseline` is the single live, repeatable owner workflow. It uses two
different read-only service accounts from `google/gsc/` and `google/ga4/`,
commits normalized batches and revision/supersession state atomically to
PostgreSQL, writes the GSC/GA4 projections as mode `0600`, and rebuilds the
baseline. It accepts no DSN or password environment variable: the database is
limited to loopback or a local Unix socket and the password must be a relative
mode-`0600` file below mode-`0700` owner-private directories. The strict
mode-`0600` local-scope receipt supplies the site and source-specific worker job
UUIDs, records an initialized scope at the required database revision, and must
refer to rows that already exist in RAOS. These internal identifiers are never
accepted on the command line. The password is read once through pinned
owner-private directory descriptors into a non-serializable, redacted immutable
snapshot; live connections consume that snapshot and never reopen the path.

GA4 must first have the separately approved event-scoped custom dimensions
`article_id`, `snapshot_id`, `cta_id`, `offer_id`, `product_id`, and
`placement`. The Admin API snapshot verifies all six with `EVENT` scope before
the Data API report runs. Their `customEvent:*` fields are normalized to the
private names; any missing or unapproved dimension fails closed instead of
silently weakening article, CTA, product, or placement attribution.

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" refresh-baseline \
  --date-from 2026-08-01 --date-to 2026-08-31 \
  --google-scope-receipt google/local-scope.v1.json \
  --database-name raos --database-user raos_worker \
  --database-password google/database/worker-password.txt \
  --gsc-output gsc.json --ga4-output ga4.json \
  --rakuten-commit rakuten-commit.json --cost-input costs.json \
  --t0-receipt t0-receipt.json \
  --json-output baseline.json --html-output baseline.html
```

The `baseline` command writes private JSON plus `noindex,nofollow` HTML. Program
profit includes reconciled Unattributed reward at program level; article profit
uses Direct reward only and never allocates the Unattributed total.

## Production readback, T0, and follow-ups

T0 is never accepted as a free-form CLI timestamp. The `t0-template` and V4
parsers retain a strict candidate contract for production readbacks that verify all
twenty provider slots and their twenty owner-private measurement IDs, all
seventy-four live Money Links, the same-origin event collector (202 plus
aggregate increment readback), and the GA4 `article_view` event. The twenty-ID
provider readback and seventy-four-link materialization count are separate
invariants; one cannot stand in for the other. The Rakuten readback must also
bind the exact owner-private activation dry-run, provider-slot set and binding
hashes, and its ten-article materialized-set hash. An older or reformatted
activation receipt, a partial twenty-ID set, a partial seventy-four-link set, or
a different published set is rejected. T0 V4 candidates also bind the hashes and exact
states of the separately administered apply receipt, the applied publication
receipt, and the verified public-readback receipt. It requires explicit
separate-admin verification and rejects any self-approval. Every observation
binds its timestamp, request hash, and response hash.

Those V4 files are nevertheless unsigned, self-asserted JSON. Hashes and a
`SEPARATE_ADMIN` string prove consistency, not the authority or provenance of
the response. Until an independently verifiable trusted-evidence contract and
verifier are implemented, `establish-t0` always fails closed with
`RAOS_EDITORIAL_V3_TRUSTED_T0_EVIDENCE_REQUIRED` before reading candidate
files and writes no T0 receipt. The strict publication parsers remain available
for candidate diagnostics, but are insufficient to establish T0.

The three publication inputs must be real mode-`0600` files below the
mode-`0700` owner-private root. In particular, the public-readback wrapper is
created and saved by the separate administrator after anonymous public
readback. It must declare `verification_authority: "SEPARATE_ADMIN"` and
`self_approval_performed: false`; the owner and Codex must not create, repair,
or promote that wrapper themselves. Receipt contents, identifiers, credentials,
and hashes must never be pasted into chat or committed to Git.

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py t0-template \
  --output production-readbacks.json
# Reserved interface: currently exits with TRUSTED_T0_EVIDENCE_REQUIRED and
# does not read these paths or write t0-receipt.json.
.venv/bin/python scripts/raos_editorial_economics_v3.py establish-t0 \
  --observation production-readbacks.json \
  --rakuten-activation-dry-run rakuten-activation-dry-run.json \
  --separate-admin-apply-receipt publication/separate-admin-apply.json \
  --publication-receipt publication/applied-publication.json \
  --public-readback-receipt publication/public-readback.json \
  --output t0-receipt.json
.venv/bin/python scripts/raos_editorial_economics_v3.py baseline \
  --rakuten-commit rakuten-commit.json --cost-input costs.json \
  --gsc-input gsc.json --ga4-input ga4.json --t0-receipt t0-receipt.json \
  --json-output baseline.json --html-output baseline.html
```

The baseline command may still produce a private pre-T0 financial view, but its
state is `INCOMPLETE_TRUSTED_T0_EVIDENCE_REQUIRED`, with T0 and its receipt hash
`UNAVAILABLE`. Supplying an unsigned V4, synthetic, or modified T0 cannot turn
that report into an observed baseline. `evaluate-followups` fails with the same
trusted-evidence-required code, so a hand-edited baseline cannot bypass the
gate.

The prior unsigned follow-up evaluator is intentionally absent; retaining it as
an internal callable would preserve a bypass around the public gate. Day 30/90
and new-article policy evaluation must be restored only together with trusted
T0 verification. The candidate query template remains a disabled input skeleton
for that future work; article/page totals still cannot be reused as candidate
demand:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py candidate-query-template \
  --output candidate-query-demand.json
# Evaluation remains blocked until trusted T0 evidence is supported.
.venv/bin/python scripts/raos_editorial_economics_v3.py evaluate-followups \
  --baseline baseline.json --as-of 2026-11-27 \
  --candidate-query-demand candidate-query-demand.json \
  --output followups.json
```

Any future trusted implementation may emit at most
`ELIGIBLE_FOR_HUMAN_PROPOSAL`; article creation and publication must remain
disabled.
