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

AT-003, generic drafts/posts, term creation, body/title/excerpt/snapshot/media
changes, plugin/theme changes, and publication without the distinct approval are
outside this interface. Formal Canonical validation, staging, and Production
evidence remain `NOT_EXECUTED`.
