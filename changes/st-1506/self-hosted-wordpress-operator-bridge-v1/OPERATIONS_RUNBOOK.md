# ST-1506 bounded WordPress operator operations runbook

This runbook is an operational handoff, not authority to install, connect, write,
release, or claim Production readiness. The imported Canonical gates and unresolved
`OD-009`, `OD-011`, `OD-013`, and `OD-015` remain in force.

## 1. Build and review locally

From the exact repository root, run:

```sh
make -f changes/st-1506/self-hosted-wordpress-operator-bridge-v1/Makefile check
make -f changes/st-1506/self-hosted-wordpress-operator-bridge-v1/Makefile plugin-package
```

Record the emitted package path, byte length, and SHA-256. The owner-private ZIP is
created with mode `0600` below `.secrets/st1506-wordpress-operator/plugin/`; it is
not a committed artifact. Compare it with `runtime-manifest.v1.json`. Do not install
a package whose bytes differ.

## 2. Human bootstrap

A human WordPress Administrator performs all bootstrap steps in a bounded
maintenance window:

1. Back up the database, active child theme, plugin inventory, Yoast options, and
   public smoke baseline. Record recovery locations outside the repository.
2. Install the exact reviewed `raos-bounded-operator-1.0.0.zip` and activate it.
   Activation may idempotently create or reconcile only the exact
   `raos_operator_executor` role with `read`, `raos_operator_read`,
   `raos_operator_propose`, and `raos_operator_apply`.
3. Create or select one dedicated non-Administrator user and assign only that exact
   role. Create one dedicated WordPress Application Password. Do not give the
   executor `manage_options`, post, publication, media, plugin, theme-administration,
   user, or role-management capabilities.
   The first valid Application Password authentication for that exact single-role
   user atomically establishes the fixed, non-autoloaded
   `raos_operator_bound_user_id_v1` site binding and the write-once,
   network-global `raos_operator_network_identity_v1` user-meta quarantine marker.
   The bridge never overwrites, reconciles, or deletes either record. Multisite is
   unsupported: activation and bridge execution are refused, while a marked
   credential is rejected on every subsite. Unrelated Application Password users
   are unaffected. An invalid or conflicting binding requires owner database
   recovery outside this bridge; there is no unbind command.
4. Store the exact closed JSON credential document at
   `.secrets/wordpress-operator-local/credentials.v1.json`. The two containing
   directories must be effective-owner mode `0700`; the regular, single-link
   credential file must be effective-owner mode `0600`. The client captures that
   effective UID once when it constructs the credential store. The file contains
   only `schema_version`, the exact
   site origin, executor username, expected role, and Application Password. Never
   pass it in argv or environment and never paste it into a task, log, PR, or test.
5. Keep `RAOS_OPERATOR_WRITES_ENABLED` absent or not strictly `true`. No REST route,
   WordPress option, CLI command, or Codex action can enable it. A human host operator
   may define it as strict boolean `true` only for an approved write window and must
   return it to disabled afterward.

Deactivation or uninstall does not delete the role, users, proposals, or audit
records. Cleanup is a separate reviewed human operation.

## 3. Read-only checks

The closed client exposes these read-only commands:

```sh
scripts/st1506_wordpress_operator_python.sh status
scripts/st1506_wordpress_operator_python.sh verify-yoast-checksums
```

Always enter through that fixed launcher from the exact repository root. Direct
Python execution is refused before credential loading or network access. The
launcher replaces the inherited environment, pins the managed Python executable
and `-B -I -S` flags, accepts only the closed argv shapes, and verifies every
operator runtime source against the exact current-HEAD blob. In verified mode it
does not add the repository to `sys.path`; the closed operator modules are compiled
only from the already captured committed bytes through an in-memory loader.

`status` must report operator version `1.0.0`, only the two supported mutations,
the complete proposal-state counters, and the actual write-constant state.
`verify-yoast-checksums` is fixed to `wordpress-seo` 28.3 and the pinned official
WordPress.org checksum manifest. `UNAVAILABLE` and any mismatch are not success.
Neither command accepts a URL, plugin slug, version, header, credential, or output
path. Every route refuses a non-HTTPS or differently configured WordPress origin,
role-capability drift, or direct per-user capability grants.
The bound Application Password is rejected for XML-RPC, non-REST authentication,
another origin, every Multisite subsite, and every REST handler other than the four
exact method, route, plugin-instance, and callback combinations in this contract.
Each secret-bearing HTTPS request forces and verifies per-instance debug logging
disabled before sending the Authorization header or body.

## 4. Create an immutable proposal

Proposal creation writes only to the bounded operator journal, but it is still a
server-side write. The human host operator must enable
`RAOS_OPERATOR_WRITES_ENABLED` for this approved maintenance window before either
proposal command. The constant does not approve the proposal or authorize its
target mutation.

The client generates a fresh, non-secret lower-case 64-hex request token from the OS
CSPRNG for each intent. The token prevents a terminal proposal from being
repurposed; it conveys no approval and is never caller input. Before transport, the
client exclusively creates and fsyncs an intent containing the operation, request
token, proposal ID, and an explicit `canonical_request_sha256` equal to that
proposal ID. The client publishes the fully written intent by an atomic hard link
and fsyncs its directory before transport. The intent lives in one owner-private
per-operation file below
`.secrets/wordpress-operator-local/proposal-intents/`. A per-operation lock makes
the write-ahead decision exclusive. A retry for the same operation must reuse that
exact unresolved intent. Never delete or edit an intent merely because a request
timed out or returned an invalid response.

For the fixed Yoast profile:

```sh
scripts/st1506_wordpress_operator_python.sh propose-yoast-profile
```

For a child-theme update:

```sh
scripts/st1506_wordpress_operator_python.sh propose-theme-update
```

The client accepts only the exact site and contract/profile versions. The Yoast
proposal contains every fixed `wpseo` and `wpseo_social` profile value; callers
cannot supply option names or values. Theme proposals require slug
`kurashinoshirube-child`, exact installed `from_version` 1.1.1, a strictly greater
semantic `to_version`, a bounded regular ZIP, its SHA-256, size, and sorted file
manifest. The caller cannot select a token or package path: the client rebuilds only
the hash-pinned ST-1704 child-theme source through
`scripts/build_st1704_self_hosted_theme.py`. Before both propose and apply, it also
rebuilds the expected ST-1704 runtime-manifest bytes through
`scripts/build_st1704_self_hosted_editorial_manifest.py` and requires byte equality
with both the tracked `runtime-manifest.v1.json` and its current-HEAD blob; it never
regenerates that tracked file. The committed-byte check uses only fixed read-only
`/usr/bin/git` plumbing with no shell, ambient Git configuration, prompt, network
fetch, or unbounded output.
Every generated theme archive entry must also have the exact size and SHA-256 from
the stage-captured ST-1704 manifest. The client revalidates the manifest and source
set after the in-memory package build, so a pathname replacement cannot become an
approved package.
The fixed `http.client` transport does not consume `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, or `NO_PROXY`, so their presence is inert. Non-empty
`SSL_CERT_DIR`, `SSL_CERT_FILE`, or `SSLKEYLOGFILE` is refused before transport so
ambient TLS configuration cannot change the fixed connection semantics.
Every archive entry must be an unencrypted `ZIP_STORED` regular file with an ASCII,
safe, case-fold-unique path. The current 1.1.1 source against installed 1.1.1 is an
intentional safe no-op and fails before transport. A real update requires a separate
reviewed theme release at 1.1.2 or greater and a regenerated ST-1704 manifest.

The server validates and canonicalizes the closed request. `proposal_id` is exactly
the SHA-256 of those canonical bytes, including origin, contract/profile versions,
request token, operation, TTL, and operation payload. It is the sole ETag. Save the
sanitized proposal receipt; do not modify the proposal.
The receipt is accepted only when its operation and proposal ID match, its state is
one of the seven closed proposal states, its strict UTC timestamps differ by exactly
900 seconds, and its ETag is the quoted proposal ID. A first receipt must be an
unexpired `PROPOSED` result. A validated replay may report `APPROVED` and direct the
matching apply command, or report `APPLYING` and require status verification before
any retry. The WordPress approval surface is shown only for a live `PROPOSED`
receipt. A validated expired or terminal replay still resolves the response-loss
ambiguity, so the client clears the journal and returns non-success
`NEW_PROPOSAL_REQUIRED` instead of retaining a permanent block.

## 5. Independent human approval

The REST executor cannot approve. A different human Administrator opens the
plugin's Tools page in a normal cookie-authenticated `wp-admin` session and reviews
the operation, exact target, before-state hash, impact, expiry, and full proposal ID.
The Administrator must:

1. use the proposal-specific WordPress nonce;
2. re-enter the current WordPress password;
3. enter a 10–300 character reason;
4. type the exact final 12 hexadecimal characters of `proposal_id`; and
5. submit before the proposal expires.

The handler rejects the proposing executor's user ID, Application Password
authentication, missing or stale nonce, bad reauthentication, wrong suffix,
expired proposal, and any non-`PROPOSED` state. It atomically binds the identifier,
approver, approval/expiry timestamps, reason, and audit hash. There is no REST
approval endpoint. The password is checked in memory and never persisted; reasons,
cookies, nonces, and passwords never appear in REST responses or Codex logs.

## 6. Apply the exact approved proposal

Only after the independent approval and human activation of the host write constant:

```sh
scripts/st1506_wordpress_operator_python.sh \
  apply-yoast-profile --proposal-id <approved-64-lowercase-hex>

scripts/st1506_wordpress_operator_python.sh \
  apply-theme-update --proposal-id <approved-64-lowercase-hex>
```

The adapter sends `If-Match: "<proposal_id>"` and the same unquoted value as its
`Idempotency-Key`. Yoast apply sends only `{}`; theme apply sends the exact bound ZIP bytes as
`application/zip`. The server refuses a missing/different approval, changed
before-state, expiry, wrong operation, wrong archive, capability drift, or disabled
constant. Timeout or an invalid response after a write attempt is
`WORDPRESS_OPERATOR_OUTCOME_AMBIGUOUS`; do not blindly retry. First run `status` and
have a human inspect the proposal/audit record.
The first response for a fresh proposal must have `replayed:false`, and an applied
receipt must return `YOAST_PROFILE_APPLIED` for the Yoast operation or
`THEME_UPDATE_APPLIED` for the theme operation. A malformed, replay-contradictory,
or cross-operation receipt remains ambiguous and cannot clear the local intent.

All applies share one fail-fast database advisory mutex derived from the database
name, table prefix, and exact site origin. It is acquired with a zero-second wait
before locked proposal revalidation and remains held through target mutation,
readback or recovery, and terminal audit persistence. Connection ownership is
verified before before-state capture, immediately after the `APPLYING` CAS commit
and before target mutation, and again before terminal persistence. Release runs in
`finally`; an unavailable, lost, or uncertain mutex never reports success.

After an exact validated `APPLIED` receipt, the client clears an unresolved create
intent only if its operation and proposal ID match that receipt. This covers a lost
create response followed by approval and apply via the ID shown in `wp-admin`. An
absent or different intent is retained without error. Ambiguous or unsuccessful
apply never clears any intent.

Yoast application revalidates the profile stored in the exact approved request
against both the fixed contract and runtime prerequisites, then merges those stored
allowlisted values only into the existing `wpseo` and `wpseo_social` arrays. Values
newly derived at apply time are not a write source. It preserves every non-profile
key/value and each row's autoload value. Both raw rows are locked with
`SELECT ... FOR UPDATE`, changed with byte-exact `BINARY` before-value CAS using
`array_replace` so numeric keys retain their identity, and verified before commit.
Before capture and apply, a read-only `information_schema.TABLES` query must prove
exactly one byte-exact schema/table row for the current-prefix options table reports
`InnoDB`; missing, duplicate, unknown, or different engine state refuses before any
option write.
Failure rolls back that same database transaction and verifies the captured raw
rows; it never issues stale `update_option` restoration writes. Commit uncertainty,
rollback uncertainty, or post-commit drift requires recovery and never reports
success. Whole-option replacement is forbidden.

Theme application accepts only the bound child-theme ZIP and direct WordPress
filesystem mode. A pre-existing recovery backup or any symlink fails closed. The
backup must reproduce the complete captured before manifest before any restore.
Once backup deletion begins, no restore is attempted; cleanup failure keeps and
verifies the new theme, reports `NEEDS_RECOVERY`, and never reports success.
Immediately verify theme version, Site Health, anonymous home and article pages,
responsive assets, and the exact package/source hashes.

## 7. Close and recover

After a successful readback, the human host operator disables
`RAOS_OPERATOR_WRITES_ENABLED` and confirms `status` reports writes disabled.

On any defect:

1. disable the host write constant;
2. stop further proposal/apply attempts;
3. retain the immutable proposal and audit records;
4. inspect the closed failure code and current state, then use the captured raw
   Yoast rows or verified child-theme backup only through a separate human recovery
   path; never apply a stale snapshot over concurrent state; and
5. repeat read-only checksum, Site Health, and anonymous public smoke checks.

Do not delete database rows, users, roles, proposals, audit records, posts, media,
themes, or plugins as part of automated recovery. Publication and post mutation are
not commands in this slice and require a separate `ST-0905`/`ST-1704` design and PR.
