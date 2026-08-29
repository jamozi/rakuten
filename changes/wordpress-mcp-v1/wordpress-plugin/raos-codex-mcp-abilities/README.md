# RAOS Codex MCP Abilities 1.0.2

This plugin is the WordPress-side half of the browser-independent RAOS Codex
workflow. It requires exactly WordPress 7.1.x, PHP 8.1+, and MCP Adapter 0.6.1.

It exposes one custom MCP server at
`/wp-json/raos-codex-mcp/v1/editor`. The server lists only site status,
post/page reads, draft creation/update, immutable release proposal creation,
and operation lookup. It does not expose MCP Adapter's generic/default server.

Activation creates two non-administrator roles but no users or Application
Passwords. A human administrator must create one dedicated user per role and
one Application Password with the exact names below:

- `raos_codex_mcp_editor`: `RAOS Codex Editor MCP`
- `raos_codex_deployment_operator`: `RAOS Codex Deployment Bridge`

Both roles are single-role identities. Their Application Passwords are denied
on XML-RPC, normal login, every core REST route, and every REST callback except
their exact MCP/deployment callback.

All write constants are default-off because undefined is false:

```php
define('RAOS_OPERATOR_WRITES_ENABLED', true);
define('RAOS_CODEX_DRAFT_WRITES_ENABLED', true);
define('RAOS_CODEX_CONTENT_APPLY_ENABLED', true);
define('RAOS_CODEX_THEME_APPLY_ENABLED', true);
define('RAOS_CODEX_PLUGIN_APPLY_ENABLED', true);
define('RAOS_CODEX_PRIVATE_DIR', '/owner-private/same-filesystem/raos-codex');
```

Set only the gates needed for the current operation. `RAOS_CODEX_PRIVATE_DIR`
must already exist outside the web/WordPress roots, be owned by the PHP worker,
be writable, have mode `0700`, and share a filesystem with the theme/plugin
target so directory replacement and rollback can be atomic.

Publication, theme replacement, and plugin changes need an unexpired proposal
approved by a different cookie-authenticated administrator in **Tools → RAOS
Codex proposals**. Approval requires current-password reauthentication, a
reason, and the final eight characters of the after hash. Approval does not
apply anything.

The plugin has no uninstall handler: users, bindings, proposals, receipts,
packages, and backups are deliberately preserved for owner recovery/audit.
