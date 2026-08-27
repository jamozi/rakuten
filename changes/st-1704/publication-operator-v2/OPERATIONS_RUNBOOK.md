# ST-1704 publication operator v2 operations

## Offline build and review

The current deterministic package is `raos-bounded-operator` 2.1.5. This patch
does not change either REST schema. It requires the exact WordPress 7.1
priority-12 `wp_check_for_changed_slugs` and `wp_check_for_changed_dates`
registrations, and suppresses only their target-post redirect-meta operations
during the bounded `post_updated` replay.

Patch 2.1.3 additionally shows only the bounded internal `WP_Error` code on the
administrator reconciliation preview when the dedicated write gate is active.
It never renders error messages, error data, proposal material, or metadata
values; this is read-only operational diagnosis and adds no REST authority.

Patch 2.1.4 keeps cleanup eligibility unchanged but makes candidate diagnosis
precise: the rolled-back preview examines all publication `NEEDS_RECOVERY`
receipts, propagates a bounded validation class, and distinguishes the known
replay-exception result from an otherwise mismatched result code. It never
renders the stored result value or enables either class for cleanup.

Patch 2.1.5 admits the two fixed replay outcomes, `UNCERTAIN` and `EXCEPTION`,
to the same exact-state proof. The actual terminal result must match its audit
event and is bound into the cleanup operation hash. A replay exception alone
never authorizes cleanup: every existing canonical receipt, expired approval,
audit chain, published storage, callback registration, and exact redirect-meta
multiset check must still pass. The proposal remains terminal after cleanup.
This reconciliation proves only removal of the exact redirect metadata and the
later checked public surface. It does not prove hook replay completion or undo
emails, webhooks, remote caches, term-count work, revisions, or any other
external effect that may have occurred before the Throwable. A recurrence on a
later article remains a new terminal incident and must stop publication.

1. Run `make -f changes/st-1704/publication-operator-v2/Makefile check`.
2. Review the exact runtime manifest, deterministic package SHA-256, generated
   four-article binding, controller diff, and terminal local checks.
3. `plugin-package` writes only the deterministic owner-private ZIP. It does not
   install, activate, change gates, make a REST request, or publish.

## External bootstrap

Plugin installation/activation and wp-config changes are human external
operations. Both `RAOS_OPERATOR_WRITES_ENABLED` and
`RAOS_ST1704_PUBLICATION_WRITES_ENABLED` must be explicitly and strictly true
for proposal creation or apply; either false/absent closes the v2 write surface.
Keep the existing exact executor identity and Application Password confinement.

## Fixed terminal redirect-metadata reconciliation

This exceptional Tools workflow is not a REST recovery route and is not a
generic post/meta editor. It is compiled for only the portable-power article at
post 28 and the Anker comparison at post 29. Proposal identifiers are not
compiled into or accepted as target selection: the controller requires exactly
one canonical terminal candidate for each fixed article/post binding and treats
the form proposal ID only as a stale-request assertion.

1. Disable normal publication writes. Set the strict booleans to master `true`,
   publication `false`, and
   `RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED` `true`. Any other
   combination closes the reconciliation action. Keep this window under 15
   minutes and restore all write gates to false immediately afterward.
2. A cookie-authenticated administrator with `manage_options`, `publish_posts`,
   and `edit_post` for the fixed post opens the same Tools page. The plugin holds
   the publication mutex and a SERIALIZABLE transaction while verifying the
   canonical request/rollback receipt, expired approval evidence, complete
   hash-chained audit, exact actors/timestamps, post/category/content/protected
   fields, and every locked `meta_id`/key/value row.
3. Review the displayed cleanup operation SHA-256. Reauthenticate with the
   current WordPress password, supply a 10–300 character reason, and type the
   final 12 operation-hash characters. The administrator must differ from the
   proposal creator.
4. The transaction refuses missing/duplicate/unrelated metadata or any
   pre-state that WordPress core would delete. It CAS-deletes only the exact
   extra Review `_wp_old_slug` and conditional previous `_wp_old_date`, verifies
   the full published state, appends `REDIRECT_META_RECONCILED`, and commits.
   The terminal proposal state/result/count are intentionally unchanged.
5. Produce and retain the external public verification artifact in the
   owner-private evidence store. The Tools page does not fetch or validate
   arbitrary HTTP content. In the second form, attest the artifact's full
   lowercase 64-hex SHA-256, reauthenticate, give a reason, and confirm the
   final 12 cleanup-operation characters. The plugin appends exactly one
   `RECONCILED_PUBLIC` audit event containing only the uppercase evidence hash.

An identical retry after response loss is idempotent. A different evidence
hash, multiple/conflicting audit events, a stale operation hash, a post lock,
audit drift, or any storage difference stops the workflow. Never create a new
proposal or post to bypass a refusal. Passwords, reasons, nonces, metadata
values, and URLs are not written to the reconciliation audit.

## One-article flow

1. The client loads one exact committed Review Draft from the owner-private v1
   journal and derives the fixed article/slug plus packet, request, snapshot, and
   visible-content hashes. It generates the request token internally.
2. `propose-article-publication --article-id <allowlisted-id>` sends the exact canonical
   request. No title, body, snapshot JSON, category ID, URL, or media input exists.
3. A different `manage_options` human opens the WordPress Tools approval page,
   verifies the target article/post/slug/category impact and full proposal hash,
   then supplies the proposal nonce, current password, 10–300 Unicode-character
   reason, and exact final 12 proposal-ID characters.
4. `apply-article-publication --article-id <same-id> --proposal-id <64hex>` sends body
   `{}`, quoted `If-Match`, and identical unquoted `Idempotency-Key`.
5. Verify the exact final URL and public readback. A mismatch is not success and
   must be handled through the closed recovery state; do not create or mutate
   another post.

`recover-article-publication --article-id <same-id> --proposal-id <64hex>` uses
the exact authenticated GET by the deterministically known proposal ID. It is
the only response-loss recovery read. There is no list/search route, and its
receipt contains no approval reason, password, nonce, or audit data.

AT-003, generic drafts/posts, term creation, media changes, plugin/theme changes,
and publication without the distinct approval are outside this interface.
Title/excerpt/body/snapshot changes are allowed only by the exact revision flow
below. Formal Canonical validation, staging, and Production evidence remain
`NOT_EXECUTED`.

## Fresh-evidence Review Draft revision

This flow is additive. It does not replace or weaken the publication flow.

1. Refresh the fixed source/Rakuten evidence, then run
   `prepare-review-draft-revision --article-id <allowlisted-id>` through the
   editorial pilot launcher. This writes only an owner-private successor
   generation. The legacy COMMITTED journal and every immutable request
   artifact remain unchanged.
2. Run `revision-status`. The legacy `/status` response intentionally remains
   the 2.0 publication-only contract; revision availability is exposed only by
   `/revision-status`.
3. Run `propose-review-draft-revision --article-id <same-id>`. The request binds
   the literal article/post mapping (portable 28, Anker 29, dishwasher 41,
   robot 30), active predecessor, successor packet/request/snapshot/content and
   review slug, generation, operation hash, and a generated request token.
4. A different `manage_options` human uses the same Tools approval page. They
   verify the Draft ID, generation, predecessor/successor hashes and complete
   pre-state hash, then reauthenticate with their current WordPress password.
5. Run
   `apply-review-draft-revision --article-id <same-id> --proposal-id <64hex>`.
   The plugin uses a Draft-only SQL transaction: title, excerpt, content,
   review slug, snapshot meta and modified timestamps change together with the
   APPLIED receipt. Post ID/status/type/author/original dates, taxonomy,
   thumbnail and all non-snapshot meta are exact preserved-state checks.
6. If the response is lost, use only
   `recover-review-draft-revision` with the same article and proposal ID; never
   create a second proposal or post. The client first reads the exact proposal
   receipt and, for a terminal or expired proposal, uses the authenticated
   `/revision-state` observation while holding the plugin's publication mutex.
   Only an exact successor or exact predecessor can close the generation;
   `APPLYING` remains bound to the same idempotent apply retry. Finish with
   `verify-review-draft-revision` using that same proposal ID.

The owner-private generation ledger activates a successor only after an exact
apply/recovery receipt. Verification is read-only. A pending or ambiguous
generation never becomes the active input to publication. Failed generations
remain immutable audit entries, so a later preparation uses the next monotonic
generation number rather than reusing the active generation number.
