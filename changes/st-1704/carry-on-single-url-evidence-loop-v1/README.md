# Carry-on single-URL evidence loop

This repository-local ST-1704 overlay adds an owner-gated, read-only evidence
command for the carry-on single-URL invariant without granting any WordPress
mutation.

The clean identity is
`https://kurashinoshirube.com/carry-on-suitcase-comparison/`. The temporary Review
identity is never accepted from a caller: the runtime derives it from the sole
terminal `RECOVERY_ATTEMPTED`-bound immutable AT-003 request artifact as
`https://kurashinoshirube.com/<review_draft_slug(bound snapshot)>/`.

This exception is exposed only as `verify-carry-on-single-url`. It binds packet
`570708…5687c`, request `9ead64…b516`, payload `f743a2…c942`, request artifact
`2305a5…ed`, public post ID 19, and retained Review Draft ID 26. The ordinary
`verify-public` command remains `COMMITTED`-only and is not relaxed.

A successful verification requires all of the following in one bounded run:

1. the clean published post and existing article/head/navigation surfaces pass;
2. the exact Review URL returns anonymous HTTP 404 with no `Location` header;
3. the Review slug has an empty anonymous public posts REST projection;
4. an authenticated exact-slug read returns exactly one fully bound Draft at fixed
   post ID 26 for the retained AT-003 Review post; the other four article modes require zero Draft rows
   after their Review post is promoted to the clean published post;
5. after HTML entity decoding and Unicode/whitespace normalization, the anonymous
   404 body contains none of the exact or meaningful partial committed title,
   excerpt, article content, snapshot JSON interior, snapshot payload SHA-256,
   RAOS article markers, high-signal shortened CTA fragments, or affiliate content;
   article fragments use visible text rather than HTML attributes, and only windows
   or tokens wholly contained in the expected clean canonical URL are excluded from
   the snapshot comparison;
6. no raw or strictly percent-decoded `raos-review-*` href occurs anywhere on the
   home page, and malformed, ambiguous, or double-encoded routes fail closed;
7. neither post nor page sitemap contains a raw or encoded `raos-review-*` URL;
8. the clean canonical occurs exactly once in the post sitemap and not in the page
   sitemap; and
9. each of the three Review surfaces has an evidence digest over its fixed path,
   actual HTTP status, actual content type, absent `Location`, relevant REST count
   headers, and response-body SHA-256; those evidence digests bind
   `public_surface_sha256`.

The strict machine-readable policy is
[`contracts/carry-on-single-url-evidence-loop.v1.json`](contracts/carry-on-single-url-evidence-loop.v1.json).
It records design intent and expected evidence shape, not a live observation.

The retained carry-on safe containment state is `one exact Draft + anonymous 404 +
no redirect`. Establishing or changing that state remains a human WordPress
operation. The fixed authenticated read reuses the existing owner gate and credential
header; it adds no credential source or authority. This overlay adds no publish,
update, delete, redirect, arbitrary URL, generic HTTP, or live-evidence path.
The reconciliation reader does not create or lock a journal and verifies that the
sole journal/artifact bytes stay stable while read. Its output is always
`formal_gate_eligible=false`, `journal_state=RECOVERY_ATTEMPTED`, and
`reconciliation_status=PENDING_HUMAN_EXCEPTION`; it is not formal `verify-public`
or Production evidence. The adapter returns the dedicated immutable
`CarryOnSingleUrlReconciliationEvidence` type, which keeps
`public_surface_verified=false` and `strict_public_checks_passed=true`; the internal
strict `PublicVerification` never crosses that public method boundary.
Theme 1.1.1 remains the minimum containment floor while any Review Draft or unbound
pilot slug exists. Formal ST-1704, Canonical suites, staging, release, and Production
status remain unclaimed.
