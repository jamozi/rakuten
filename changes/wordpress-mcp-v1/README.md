# Browser-independent WordPress MCP v1

This slice implements the browser-independent Codex workflow for the single
self-hosted site `https://kurashinoshirube.com`.

## Runtime topology

There are exactly two project MCP servers:

1. `wordpressEditor` starts pinned
   `@automattic/mcp-wordpress-remote@0.4.0` through a credential-safe launcher
   and connects to the custom WordPress MCP server.
2. `wordpressDeployment` starts the local
   `@raos/wordpress-mcp-bridge`, built on
   `@modelcontextprotocol/sdk@1.30.0`, over stdio.

The WordPress plugin requires WordPress 7.1.x and exactly MCP Adapter 0.6.1.
It disables MCP Adapter's generic default server and exposes only the seven
tools listed in `contracts/wordpress-mcp.v1.json`. The local bridge exposes only
six typed operations. Neither path includes a generic request, command, PHP,
SQL, filesystem-path, URL, media-write, delete, unpublish, uninstall, or
arbitrary ZIP tool.

The archived `Automattic/wordpress-mcp` repository and the WordPress.com app
are not runtime dependencies. The WordPress.com plugin may remain installed,
but this project does not use it for reads, writes, approval, or deployment.

## Human bootstrap (live external action)

These steps intentionally remain administrator-owned and are not performed by
the build or tests:

1. Install WordPress 7.1.x and MCP Adapter 0.6.1 (tag commit
   `23cb53e0b82f39238eec1c38cb055e28aa30fa7c`).
2. Run `make -C changes/wordpress-mcp-v1 plugin-package`, verify the hash in
   `runtime-manifest.v1.json`, and install/activate the resulting owner-private
   `raos-codex-mcp-abilities-1.1.0.zip` in wp-admin.
3. Create one non-administrator user for each activation-created role, with no
   second role or direct capabilities:
   `raos_codex_mcp_editor` and `raos_codex_deployment_operator`.
4. Create one Application Password per user using the exact names documented
   in the plugin README. Do not reuse the prior bounded-operator or Draft Writer
   user/credential.
5. Store each new value interactively (the password is read with `getpass` and
   is never placed in argv):

   ```text
   .venv/bin/python scripts/store_wordpress_mcp_credential.py --purpose editor_mcp
   .venv/bin/python scripts/store_wordpress_mcp_credential.py --purpose deployment_operator
   ```

   The `username` prompt requires the WordPress login username, not the role,
   display name, or Application Password name. If only that field was entered
   incorrectly, preserve the one-time password and replace the username
   atomically without printing the credential:

   ```text
   .venv/bin/python scripts/store_wordpress_mcp_credential.py --purpose editor_mcp --replace-username
   .venv/bin/python scripts/store_wordpress_mcp_credential.py --purpose deployment_operator --replace-username
   ```

6. Configure an owner-private, same-filesystem directory outside WordPress and
   the web root, mode `0700`, as `RAOS_CODEX_PRIVATE_DIR`. Keep the global
   `RAOS_OPERATOR_WRITES_ENABLED` kill switch owner-controlled. Individual
   content, theme, and plugin applies do not require `wp-config.php` changes.
7. Restart Codex so project MCP configuration is reloaded, then run
   `codex mcp list`. Only `wordpressEditor` and `wordpressDeployment` may be
   enabled.

## Operation flow

- Draft post/page creation and update mutate only `draft` targets and require
  `RAOS_OPERATOR_WRITES_ENABLED` plus `RAOS_CODEX_DRAFT_WRITES_ENABLED`.
- All updates require `revision_id`, `modified_gmt`, and `content_sha256`.
- A content release creates a complete immutable before/after proposal; it does
  not alter or publish the post/page.
- Theme proposal builds only the clean, tracked
  `kurashinoshirube-child` tree from the current Git commit. Additional CSS and
  live/untracked template editing have no tool path.
- Plugin proposal accepts only an exact WordPress.org slug/version or an
  artifact ID registered in `repo-plugin-artifacts.v1.json`. The caller cannot
  provide a URL or path. ZIP traversal, symlink, case collision, size, version,
  compatibility, manifest, and digest checks run locally and again in
  WordPress.
- Plugin packages with activation, database, option-schema, SQL DDL, or generic
  migration signals become `MANUAL_REQUIRED`; wp-admin cannot approve them for
  this automatic path.
- A different cookie-authenticated administrator reviews the complete payload
  in **Tools → RAOS Codex proposals**, reauthenticates, gives a reason, and
  types the after-hash suffix. Approval creates one proposal-bound, single-use
  authorization lease outside the web root. It expires after 15 minutes and
  does not apply the proposal.
- Apply requires the approval plus `If-Match`, the same idempotency key, global
  kill switch, the scoped authorization lease, unchanged before hash, backup,
  replacement, and after-hash readback. The lease is removed after success or
  failure. Communication-loss recovery accepts only the existing operation ID.

## Verification

Offline checks do not install, activate, authenticate to, approve on, or write
to WordPress:

```text
make -C changes/wordpress-mcp-v1 manifest-generate
make -C changes/wordpress-mcp-v1 check
npm run typecheck
npm run wordpress:ui:check
```

The tests cover initialization/tool schemas/annotations, project configuration,
credential absence, fixed versions, route confinement markers, approval and
gate invariants, deterministic packages, and ZIP/migration rejection.

The disposable WordPress and public UI checks require the separately prepared
WordPress 7.1 test host. `npm run wordpress:ui:check` uses the pinned terminal
Playwright CLI (not an interactive browser) at widths 360, 390, 768, and 1440,
saves artifacts only under `output/playwright/`, and rejects overflow, runtime
console/page errors, missing landmarks/alternative text/form labels, duplicate
IDs, and broken ARIA references. Set `RAOS_WORDPRESS_UI_BASELINE_DIR` to an
absolute owner-approved baseline directory to require byte-exact screenshot
comparison in the disposable deterministic environment. Live credentials,
activation, the global kill switch, and publishing stay human-owned external
steps and are not implied by local test success.

The destructive-path integration suite is isolated from the live host and owns
its containers, database, fixed test identities, and volume:

```text
make -C changes/wordpress-mcp-v1 e2e
```

It uses digest-pinned WordPress 7.1.0, WP-CLI 2.12.0, and MariaDB 11.8.3
images. It verifies the downloaded MCP Adapter 0.6.1 release ZIP before use,
then exercises MCP initialization, the exact tool list and annotations,
Application Password confinement, post and page draft create/partial
update/replace, non-mutating proposals, refusal before approval, the real
wp-admin approval handler under a separate administrator, hash-drift refusal,
idempotent apply, tracked child-theme replacement, fixed-hash plugin
activation, failed plugin-activation rollback, recovery, readback, and audit
receipt state. Approval-scoped leases and disposable repo-artifact hashes are
enabled only inside this isolated test environment. The unique Compose project and
same-filesystem temporary bind tree are removed on exit.
Supplying an already downloaded release asset is supported only through an
absolute regular file in
`RAOS_MCP_ADAPTER_ZIP`; its SHA-256 is still checked.
