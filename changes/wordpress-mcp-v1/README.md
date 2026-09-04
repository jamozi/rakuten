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
Abilities 1.3.1 is bound to runtime revision
`f3e9e302b9a40bf6b312b2457f981272246f4fdd6f3e047d92bec5fda61d8082`;
the entrypoint and every critical class must report that exact identity.
It disables MCP Adapter's generic default server and exposes only the nine
tools listed in `contracts/wordpress-mcp.v1.json`. The local bridge exposes only
seven typed operations. Neither path includes a generic request, command, PHP,
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
   `raos-codex-mcp-abilities-1.3.1.zip` in wp-admin.
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

For the ten tracked editorial articles, run the foreground workflow from the
repository root:

```text
make wordpress-production-request ARTICLES=all
```

It runs the mandatory local preview `up`, `sync`, and `check` sequence before
contacting production, reconciles only the exact mapped drafts, creates
idempotent proposals, prints the fixed wp-admin review URL, waits for the
separate administrator approval, applies at most one theme first and then the
selected content, and finally performs production readback. The Make wrapper
accepts only `ARTICLES=all`, which invokes the current CLI interface as
`--articles all`; partial or comma-separated selections fail closed before any
publication proposal. The command neither approves proposals nor changes host
gates. Its resumable
owner-private receipts are stored under
`.secrets/wordpress-mcp/publication-requests/`.

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
  this automatic path. The only automatic exception is the reviewed
  `raos-editorial-measurement` 1.0.0 repo artifact, whose artifact ID, slug,
  version, package SHA-256, and complete file-manifest SHA-256 are fixed in the
  owner-generated registry and independently rechecked by both the local
  operator and installed plugin. Any changed or unknown package returns to
  `MANUAL_REQUIRED`.
- The abilities 1.3.1 upgrade itself remains `MANUAL_REQUIRED`. After a
  different human administrator manually installs and activates the exact
  proposal package in wp-admin, the new plugin may show one narrow attestation
  form. It reauthenticates the administrator and requires visible proposal,
  package, and installed-tree hash suffixes. The server rechecks the staged
  package, host artifact pin, complete manifest, active installed tree,
  version, runtime revision, and immutable proposal before storing
  `PLUGIN_BOOTSTRAP_ATTESTED_AFTER_MANUAL_INSTALL`. This is a proposal-bound
  `APPLIED` receipt only; it cannot install code, issue an apply lease, approve
  another migration, or be called through REST/MCP.
- The editor registers the exact 1–20 content/theme proposal IDs as one
  immutable server-side publication batch; unrelated pending proposals and all
  plugin proposals are excluded. A different cookie-authenticated
  administrator reviews that registered batch in **Tools → RAOS Codex
  proposals**. The review page loads every exact member by manifest ID and
  shows the complete content/theme payload; if any member or hash is missing or
  inconsistent, it withholds the approval form. The administrator
  reauthenticates once, gives a reason, and types the visible final eight
  characters of the canonical manifest hash. Each proposal and its batch stay
  reviewable for 60 minutes. Approval is all-or-nothing: it creates one
  proposal-bound, single-use authorization lease per proposal outside the web
  root. The leases expire after 15 minutes and approval itself
  does not apply anything. An atomic claim made before that deadline consumes
  the authorization and keeps the exact batch recoverable until every claimed
  operation reaches a terminal state; the 15-minute clock does not interrupt a
  batch already being applied.
- The bounded `release-wait-and-apply` operator waits up to 60 minutes for that
  approval, then starts a separate 15-minute apply/recovery budget. It refuses
  plugin proposals and malformed or terminal batches, and binds the server's
  exact batch token, canonical manifest hash, and sorted proposal IDs through
  the final aggregate receipt. Before its first mutation, WordPress verifies
  every member is still at its immutable before/after state and atomically
  claims the whole exact batch in one transaction. It then converges at most
  one theme first, followed by the content proposals (up to 20
  content-only, or up to 19 when a theme is included). Reruns recover or accept
  only already-bound operations. A separate read-only batch-status tool lets a
  changed local request discard an old receipt only after the server confirms
  that every member expired without starting; individual content/theme apply
  tools are not exposed.
- `site-status` reports the installed and loaded Yoast SEO state, the exact
  28.3 version, the selected `wpseo` / `wpseo_social` option projection, and
  its canonical settings fingerprint. Publication-batch claim and every
  content/theme apply fail closed when any value is missing or drifted. The
  `PLUGIN_CHANGE` path remains available so the fixed dependency bootstrap can
  be completed before those release gates become satisfiable.
- Content apply, theme apply, and recovery share one server-side publication
  lock. Each content mutation rechecks the reviewed active-theme tree after its
  write and rolls the content back if that binding changed. Administrators must
  still exclude every external updater or file writer during the complete
  approval/apply/recovery window. Native WordPress core, plugin, and theme
  updaters, the Theme/Plugin File Editor, hosting deployment panels, FTP, SFTP,
  SSH, and direct filesystem writes do not acquire this plugin lock and are
  outside its strict linearization boundary. Before/after compare-and-swap and
  readback remain fail-closed race detectors; they do not make those external
  writers participants in the lock.
- Apply requires the approval plus `If-Match`, the same idempotency key, global
  kill switch, the scoped authorization lease, unchanged before hash, backup,
  replacement, and after-hash readback. The lease is removed after success or
  failure. After every atomic code-tree replacement or rollback, the exact PHP
  files in the validated manifest are invalidated from an active OPcache before
  runtime use. Both status surfaces report the child theme version loaded by
  PHP, and final readback requires it to match the reviewed theme version.
  Communication-loss recovery accepts only the existing operation ID.
- Completion also performs an unauthenticated HTTPS readback of every canonical
  production URL. It requires an exact 200 response without redirects, one
  matching canonical URL, the reviewed title/headings, and no `noindex` marker.

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
