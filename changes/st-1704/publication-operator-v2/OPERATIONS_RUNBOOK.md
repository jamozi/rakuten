# ST-1704 publication operator v2 operations

## Offline build and review

The current deterministic package is `raos-bounded-operator` 2.1.13. It does
not change either REST schema. It retains the exact WordPress 7.1
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

Patch 2.1.6 keeps cleanup execution unchanged and adds only a bounded refusal
classification for a cookie-authenticated administrator. The page may show one
of the fixed authentication/evidence codes or the fixed execution-refused code;
it never shows messages, data, submitted values, proposal material, metadata,
or database errors. Close all gates before investigating any refusal, then use
the rolled-back Tools preview to distinguish `CLEANED` from
`CLEANUP_REQUIRED` before considering another submission.

Patch 2.1.7 installs and exact-verifies the separate `raos_draft_writer`
(`RAOS Draft Writer`) role during ST-1704 activation. Its complete capability
set is `read` and `edit_posts`; it has no delete, publish, upload,
edit-published, edit-others, operator, or administrator capability. Activation
stops if WordPress cannot create, persist, normalize, or exactly read back the
role. This does not assign the role or create a credential.

Patch 2.1.8 confines the distinct fixed-login `raos-draft-writer` credential's
transport to raw HTTPS `GET` or `POST` on the core `/wp/v2/posts` collection.
XML-RPC, method overrides, other methods, other REST paths, and
identity/capability drift are refused. The transport guard recognizes either
the immutable login or the role marker, including after role removal or
replacement.
The existing base-role authority to create and recover the user's own Drafts
is unchanged. Only the formal verifier's exact post-sanitization `GET` query
shapes arm the transient projection; nonmatching collection `GET`/`POST`
requests fall back to base-role behavior. The bridge may satisfy only
`edit_post` for fixed public posts 19, 28, 29, 41, and 30, plus fixed Review
Draft 26 at the exact payload-hash-bound carry-on Review slug. It persists no
extra capability and never grants publication or administration authority.

Patch 2.1.9 evaluates the projection at its earliest bounded `user_has_cap`
hook priority, before ordinary filters can alter the received capability array.
It retains the exact full-capability comparison and every existing fixed request,
controller, `get_items`/`check_update_permission`, post, and mapped-capability
check.

Patch 2.1.10 is limited to the third concrete terminal incident encountered
during the dishwasher publication. It adds only the generated fixed binding
for that article, post 41, and its public slug to the portable-power and Anker
incident allowlist. It does not pre-authorize the later robot-vacuum article or
establish a reusable incident policy. The canonical receipt remains terminal
and unchanged. Reconciliation still means only exact locked redirect-metadata
cleanup followed by recording one owner-private verification evidence SHA-256;
it does not complete replay or change proposal state, result, counts, REST
schema, normal gates, or normal write authority.

Patch 2.1.11 admits the exact observed no-row state only for that fixed
dishwasher binding. The locked metadata planner must report `CLEAN`, an empty
delete set and empty cleanup digests, equality between current and expected
after rows, and equality between the before and expected after multisets while
the audit remains `CLEANUP_REQUIRED`. The resulting
`VERIFIED_NO_REDIRECT_META_ROWS` V2 operation material binds the disposition,
`CLEAN` state, and empty cleanup rows. Execution performs no `DELETE`, but it
still runs inside the same SERIALIZABLE transaction and requires the same
published-state readback, audit append, and commit. Existing exact-row cleanup
continues to use byte-compatible V1 operation material so the already recorded
portable-power and Anker operation hashes remain valid. This does not change a
receipt, proposal state/result/count, REST schema, gate, or Robot eligibility.

Patch 2.1.12 changes only the private Tools preview projection. The preview
returns the cleanup disposition already recomputed by the locked server plan:
`VERIFIED_NO_REDIRECT_META_ROWS` for the exact dishwasher no-row state and
`ALREADY_RECONCILED` for completed incidents. No submitted field can select
the disposition, and operation material/hashes, receipts, gates, permissions,
REST routes, and execution behavior remain unchanged.

Patch 2.1.13 admits only the fourth observed terminal incident: the exact
Robot article, post 30, and generated public slug. Robot is no-row-only. Its
locked metadata plan must be `CLEAN`, both row collections must be empty, and
the current/expected rows and before/after multiset hashes must be equal.
Planning and execution both refuse a Robot exact-row cleanup before `DELETE`.
The no-row literal map contains only Dishwasher and Robot; Portable-power and
Anker clean states stay ineligible. Robot operation material binds its exact
article, post, and public-slug hash using the existing V2 shape. Therefore the
Dishwasher V2 operation bytes/hash and the Portable-power/Anker V1 operation
bytes/hashes remain unchanged. The same transaction, readback, audit,
distinct-human, terminal-receipt, gate, count, and REST invariants apply.

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
For owner-private authenticated draft/public verification, a human WordPress
administrator may create the distinct non-administrator login
`raos-draft-writer`, assign only `RAOS Draft Writer`, and create a dedicated
Application Password. User
creation, role assignment, Application Password creation/copying, and insertion
into the owner-private credential store remain human external operations. Never
reuse the bound `raos_operator_executor` identity or its Application Password
for owner verification.

Do not create or install the Draft-writer Application Password until plugin
2.1.13 or later is active and its exact package/version checks pass. The
temporary projection is read-only; the role's pre-existing own-Draft
create/recover behavior is unchanged and remains bounded by its exact base
capabilities.

For a fresh deployment that has never activated 2.1.7 or later, keep every
Draft-writer user and Application Password absent. Install the package, then
explicitly activate it. Package replacement alone does not run activation
hooks. Verify the active plugin version and exact persisted `RAOS Draft Writer`
role (`read`, `edit_posts`, and no other capability) before assigning the role
to the exact `raos-draft-writer` login and creating the Application Password.
If activation stops
after normalizing the role, do not create a credential; restore or reactivate a
known-good package and repeat exact role verification first.

For the current 2.1.12 upgrade state, the role has already been activated and
exactly persisted, dedicated user ID 3 is assigned, and its dedicated
Application Password may already exist. Version 2.1.13 does not change that
DB/role schema. Replace 2.1.12 in place without deactivation/reactivation, then
verify active version 2.1.13, the exact persisted role, dedicated user ID 3's exact
`raos-draft-writer` login and identity,
and both operator status surfaces before creating the Application Password.
Avoiding deactivation also avoids an unnecessary interval without the new
transport confinement.

Before rollback, downgrade, deactivation, role removal/replacement, or any
direct database identity change after a Draft-writer credential exists, revoke
that Application Password first, then remove/disable the dedicated user's
Draft-writer assignment while 2.1.13 confinement is still active. WordPress UI
does not rename `user_login`; do not edit this immutable binding directly.
Deactivation does not remove the persisted role or Application Password, so
reversing that order would leave the base `read`/`edit_posts` authority without
the transport confinement.

## Fixed terminal redirect-metadata reconciliation

This exceptional Tools workflow is not a REST recovery route and is not a
generic post/meta editor. It is compiled only for the four observed incidents:
the portable-power article at post 28, the Anker comparison at post 29, and the
dishwasher article at post 41, plus the robot-vacuum article at post 30, each
with its exact generated public slug. Proposal identifiers are not compiled into or
accepted as target selection: the controller requires exactly one canonical
terminal candidate for each fixed article/post/slug binding and treats the form
proposal ID only as a stale-request assertion. The approval TTL must already be
expired before any preview or cleanup can succeed.

1. Disable normal publication writes. Set the strict booleans to master `true`,
   publication `false`, and
   `RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED` `true`. Any other
   combination closes the reconciliation action. Keep this window under 15
   minutes and restore all write gates to false immediately afterward.
2. A cookie-authenticated administrator with `manage_options`, `publish_posts`,
   and `edit_post` for the fixed post opens the dedicated Tools page at
   `/wp-admin/tools.php?page=raos-st1704-publication-operator-v2` (not the
   legacy `page=raos-bounded-operator` screen). The plugin holds
   the publication mutex and a SERIALIZABLE transaction while verifying the
   canonical request/rollback receipt, expired approval evidence, complete
   hash-chained audit, exact actors/timestamps, post/category/content/protected
   fields, and every locked `meta_id`/key/value row.
3. Review the displayed cleanup operation SHA-256. Reauthenticate with the
   current WordPress password, supply a 10–300 character reason, and type the
   final 12 operation-hash characters. The administrator must differ from the
   proposal creator.
4. The transaction refuses missing/duplicate/unrelated metadata or any
   pre-state that WordPress core would delete. When exact redirect extras are
   present, it CAS-deletes only the extra Review `_wp_old_slug` and conditional
   previous `_wp_old_date`. For only the exact Dishwasher or Robot incident, a
   verified `CLEAN` multiset with zero cleanup rows performs no deletion. Robot
   is never eligible for the exact-row deletion path. Both eligible paths
   verify the full published state, append `REDIRECT_META_RECONCILED`, and
   commit.
   The terminal proposal state/result/count and receipt are intentionally
   unchanged; reconciliation never converts the receipt into success.
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
