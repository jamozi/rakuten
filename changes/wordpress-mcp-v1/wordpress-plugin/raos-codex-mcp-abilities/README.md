# RAOS Codex MCP Abilities 1.3.1

This plugin is the WordPress-side half of the browser-independent RAOS Codex
workflow. It requires exactly WordPress 7.1.x, PHP 8.1+, and MCP Adapter 0.6.1.
The release is bound to runtime revision
`f3e9e302b9a40bf6b312b2457f981272246f4fdd6f3e047d92bec5fda61d8082`;
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

Activation creates two non-administrator roles but no users or Application
Passwords. A human administrator must create one dedicated user per role and
one Application Password with the exact names below:

- `raos_codex_mcp_editor`: `RAOS Codex Editor MCP`
- `raos_codex_deployment_operator`: `RAOS Codex Deployment Bridge`

Both roles are single-role identities. Their Application Passwords are denied
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
1.3.1 installation. A different human administrator must first install and
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
