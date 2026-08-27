# ST-1704 publication operator v2 operations

## Offline build and review

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
