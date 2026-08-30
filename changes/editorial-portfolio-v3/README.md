# Editorial V3 portfolio and owner-private economics

`editorial-portfolio.v3.json` is an additive, generated successor to Editorial
V2. It covers the current ten articles and thirty-two products without changing
the historical V2 contract. `generated/navigation.v3.json` is the single
machine-readable home/related-article source.

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

## Rakuten attribution contract

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
