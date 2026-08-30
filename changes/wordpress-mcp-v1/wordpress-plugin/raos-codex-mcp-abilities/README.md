# RAOS Codex MCP Abilities 1.2.2

This plugin is the WordPress-side half of the browser-independent RAOS Codex
workflow. It requires exactly WordPress 7.1.x, PHP 8.1+, and MCP Adapter 0.6.1.

It exposes one custom MCP server at
`/wp-json/raos-codex-mcp/v1/editor`. The server lists only site status,
post/page reads, draft creation/update, immutable release proposal creation,
exact publication-batch registration, and operation lookup. It does not expose
MCP Adapter's generic/default server.

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
it is single-use, lasts 15 minutes from approval, and is removed after success
or failure. Content, theme, and plugin applies therefore require no
per-deployment `wp-config.php` edit.

Publication, theme replacement, and plugin changes need an unexpired proposal
approved by a different cookie-authenticated administrator in **Tools → RAOS
Codex proposals**. The editor first registers an immutable exact-ID publication
batch containing content plus at most one theme; unrelated pending proposals
and plugin changes cannot enter that batch. One batch approval requires current
password reauthentication, a reason, and the visible final eight characters of
the batch manifest hash. The transaction either approves the complete unchanged
registered batch and creates every scoped lease, or approves none.
Pending proposals and registered batches expire after 60 minutes. Approval
replaces that pre-approval deadline with a fresh 15-minute apply lease, so an
approval near the end of the review window still receives the complete apply
and recovery budget. Approval does not apply anything; the bounded operator
still performs the apply, backup, readback, and rollback workflow. Content and
theme proposals can only be approved through their exact registered batch;
individual approval is available only for deliberate plugin-change handling.

The plugin has no uninstall handler: users, bindings, proposals, receipts,
packages, and backups are deliberately preserved for owner recovery/audit.
