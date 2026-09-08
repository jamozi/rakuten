# RAOS Codex MCP Abilities 1.4.0

Ordinary article and child-theme publication uses the optional
[owner-direct-v1 delegation](#owner-direct-v1-plugin-140). It starts OFF and
requires one human administrator setup. The separate approval descriptions below
apply to legacy proposals; direct publication does not repeat that approval.

This plugin is the WordPress-side half of the browser-independent RAOS Codex
workflow. It requires exactly WordPress 7.1.x, PHP 8.1+, and MCP Adapter 0.6.1.
The release is bound to runtime revision
`3959d130244e13994c252522bbbc4ae245d70c517817c7e6e64835c621659a19`;
every loaded critical class must report that exact value before any ability or
mutation is authorized.

It exposes one custom MCP server at
`/wp-json/raos-codex-mcp/v1/editor`. The server lists only site status,
post/page reads, draft creation/update, immutable release proposal creation,
exact publication-batch registration, and operation lookup. It does not expose
MCP Adapter's generic/default server.

When the separately reviewed `raos-editorial-measurement` plugin is active,
the same editor server also exposes its `raos-measurement/aggregate-report`
ability. That tool is read-only and aggregate-only; no raw event or session
read tool is present. If the measurement plugin is absent, MCP Adapter omits
the unavailable ability rather than adding a generic execution surface.

Activation creates three non-administrator roles but no users or Application
Passwords. A human administrator must create one dedicated user per role and
one Application Password with the exact names below:

- `raos_codex_mcp_editor`: `RAOS Codex Editor MCP`
- `raos_codex_deployment_operator`: `RAOS Codex Deployment Bridge`
- `raos_codex_owner_direct_publisher`: `RAOS Codex Owner Direct Publisher`

All roles are single-role identities. Their Application Passwords are denied
on XML-RPC, normal login, every core REST route, and every REST callback except
their exact MCP/deployment callback.

The global write kill switch and draft-writing gate remain host-owned and
default-off because undefined is false:

```php
define('RAOS_OPERATOR_WRITES_ENABLED', true);
define('RAOS_CODEX_DRAFT_WRITES_ENABLED', true);
define('RAOS_CODEX_PRIVATE_DIR', '/owner-private/same-filesystem/raos-codex');
```

`RAOS_CODEX_PRIVATE_DIR` must already exist outside the web/WordPress roots, be
owned by the PHP worker, be writable, have mode `0700`, and share a filesystem
with the theme/plugin target so directory replacement and rollback can be
atomic. A successful separate wp-admin approval creates one mode-`0600`,
proposal-bound authorization lease in that directory. The lease binds the
operation kind, creator, approver, timestamps, and complete before/after hashes;
it is single-use, expires with the proposal, and is removed after success or
failure. Content, theme, and plugin applies therefore require no per-deployment
`wp-config.php` edit.

The read-only site status includes the exact Yoast SEO 28.3 installed/active
state, selected option projection, and canonical settings fingerprint.
Publication-batch claim and content/theme apply reject a missing or drifted
Yoast state; plugin-change bootstrap deliberately remains available so the
required fixed dependency can be installed first.

Publication, theme replacement, and plugin changes need an unexpired proposal
approved by a different cookie-authenticated administrator in **Tools → RAOS
Codex proposals**. The editor first registers an immutable exact-ID publication
batch containing content plus at most one theme; unrelated pending proposals
and plugin changes cannot enter that batch. One batch approval requires current
password reauthentication, a reason, and the visible final eight characters of
the batch manifest hash. The transaction either approves the complete unchanged
registered batch and creates every scoped lease, or approves none. A proposal
and its registered batch stay reviewable for 60 minutes; successful approval
starts a fresh, separate 15-minute single-use apply lease. Approval does not
apply anything; the bounded operator still performs the
apply, backup, readback, and rollback workflow. Content and theme proposals can
only be approved through their exact registered batch; individual approval is
available only for deliberate plugin-change handling.

One bootstrap-only exception records, but never performs, a manual abilities
1.3.2 installation. A different human administrator must first install and
activate the exact proposal package in wp-admin. The attestation form is shown
only when the staged package, host pin, package/file-manifest hashes, installed
tree, plugin version, loaded runtime, and immutable `MANUAL_REQUIRED` proposal
all match. Password reauthentication plus proposal/package/tree hash suffixes
are required. The resulting proposal-bound
`PLUGIN_BOOTSTRAP_ATTESTED_AFTER_MANUAL_INSTALL` receipt is accepted as the
abilities prerequisite for the fixed measurement proposal; it is not a generic
migration approval and has no REST or MCP route.

The plugin has no uninstall handler: users, bindings, proposals, receipts,
packages, and backups are deliberately preserved for owner recovery/audit.
## Owner-direct-v1 (plugin 1.4.0)

This optional policy successor delegates ordinary article and
`kurashinoshirube-child` publication to one dedicated limited account. It is OFF
until a human administrator saves the delegation in **Tools → RAOS Codex
proposals → Owner-direct-v1 publishing**. Create a separate user with role
`raos_codex_owner_direct_publisher`; its only capabilities are `read` and
`raos_codex_owner_direct_publish`. Create its application password with name
`RAOS Codex Owner Direct Publisher`. Existing editor/operator accounts are not
promoted. The credential is restricted to the exact direct routes and its own
batch/operation routes; it cannot call general WordPress REST, plugin changes,
generic abilities, or wp-admin setup.

Setup accepts a bounded existing-target array of
`{article_key, post_id, post_type, slug}`, the dedicated publisher user ID, an
`allow_new_posts` flag, and the enabled checkbox. Existing identities are checked
against WordPress. When new posts are enabled, `ensure-draft` creates only `post`
drafts with safe ASCII keys/slugs; it rejects another article's slug and binds the
actual new ID in a transaction. An identical request after response loss reads
that binding instead of creating another post. Newly created IDs remain available
for later updates without another administrator step. Every setup save changes
the delegation generation and invalidates older direct proposals; disabling the
checkbox revokes the publisher's mutations. The global kill switch remains
required.

The REST namespace is `/raos-codex-owner-direct/v1`:

* `GET /status`: enabled delegation, bounded identities and current theme identity.
* `GET /documents/{id}`: only a configured or direct-created content document.
* `POST /ensure-draft`: `{profile, article_key, slug, idempotency_key}`.
* `POST /content-proposals`: `{profile, article_key, id, precondition, document,
  idempotency_key}`; freezes the existing content proposal and direct binding.
* `POST /theme-proposals`: `{profile, kind:"theme_release", code_package,
  package_base64, idempotency_key}`; only the configured child theme.
* `POST /authorize`: `{profile, proposal_ids, expected_theme_tree_sha256}`;
  returns the existing batch shape with a 15-minute single-use direct lease per
  member. With a theme change the expected hash is the desired theme tree;
  otherwise it is the preparation baseline. Exact retries do not extend leases.
* `POST /batches/{batch_token}/finish`: `{profile, batch_manifest_sha256,
  action:"finalize"|"rollback"}`. Finalize after all member and public readbacks;
  roll back after a confirmed member failure. It returns a durable
  `RAOSOwnerDirectBatchResultV1` with per-member outcomes.

Every `profile` above is exactly `owner-direct-v1`. Existing batch claim, apply,
operation status and recovery routes are reused with the same dedicated
credential and the existing exact headers. Pending legacy proposals cannot be
promoted. Direct proposals carry an immutable `authorization_profile`; direct
leases use `RAOS_CODEX_OWNER_DIRECT_LEASE_V1` and cannot be exchanged with legacy
approval leases. Independent reviews, audit packets and another wp-admin approval
are not part of this profile.

Applied direct theme backups and leases remain until batch finish. Compensation
restores content before theme, and restores a newly created post to its own draft
instead of deleting it. Content compensation requires the exact recorded applied
revision, timestamp and hash under database locks; theme compensation uses the
existing checked rename/backup mechanism. An unknown in-flight member must be
recovered before compensation. Concurrent drift stops compensation and reports
`PARTIAL_CONFLICT`; other people's edits are never overwritten. Finish retries
return the same terminal result. Public article metadata comes only from the
materialized applied document snapshot, and becomes unavailable if current public
content no longer matches that snapshot.
