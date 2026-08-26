# RAOS Bounded Operator 1.0.0

This WordPress plugin exposes a deliberately closed operator surface for the
RAOS owner. It supports only two operations: applying the repository-defined
Yoast 28.3 profile and updating the fixed `kurashinoshirube-child` theme from a
hash- and manifest-bound ZIP.

Activation creates the dedicated `raos_operator_executor` role and the
proposal/audit tables. It never deletes data on deactivation or uninstall.
Assign the dedicated role to a service account and authenticate it using a
WordPress Application Password over HTTPS. Do not assign any additional role.
Role creation and capability reconciliation are read back and must equal the
four-capability fixed role exactly. The plugin also reads the fixed current-site
`user_roles` option directly from the WordPress options table and decodes it
with object instantiation disabled, so an in-memory role update cannot conceal
a failed persistent write. Activation stops before table creation and the
activation audit if either verification fails.
Activation verifies that both operator tables are InnoDB, then appends the
activation audit event inside one explicit transaction. Audit append or commit
uncertainty rolls the audit transaction back and fails activation.

The first valid Application Password authentication observed for a user whose
only role is `raos_operator_executor` atomically creates the non-autoloaded,
write-once site binding `raos_operator_bound_user_id_v1` and the write-once,
network-global user-meta quarantine marker
`raos_operator_network_identity_v1`. A database-scoped named lock serializes
that bootstrap, and neither record is overwritten or deleted by the plugin. A
conflicting, duplicated, unavailable, or malformed record fails closed for the
marked operator without blocking unrelated users' Application Passwords.
Plugin load also promotes an existing valid site binding to the global marker
before accepting subsequent operator authentication.
Once marked, that credential is rejected on XML-RPC, non-REST requests, every
REST method/route outside the four handlers below, and every site other than
the exact fixed origin. This firewall remains in force if the local option is
absent or the account role or capabilities drift.

Multisite is unsupported. Activation is refused on multisite, and a marked or
locally bound operator credential is quarantined through global user meta and
rejected on every multisite subsite. The four own routes separately require a
single-site runtime, the exact role, and the exact capability set.

All proposal and apply mutations are disabled unless trusted host configuration
defines the following constant. There is intentionally no UI or REST toggle:

```php
define('RAOS_OPERATOR_WRITES_ENABLED', true);
```

An administrator must independently approve every exact proposal under
**Tools → RAOS Operator** using a cookie-authenticated session, a proposal nonce,
their current password, a 10–300 character reason, and the final 12 characters
of the proposal ID. Reason length is the exact Unicode scalar count after
WordPress textarea sanitization. Raw input is capped at 1200 bytes before any
Unicode match allocation, invalid UTF-8 is rejected before sanitization, and a
bounded anchored Unicode expression enforces the final 10–300 scalars without
materializing per-character matches. REST and Application Password
authentication cannot approve.

The REST namespace is `raos-operator/v1`:

- `GET /status`
- `POST /yoast-checksum`
- `POST /proposals`
- `POST /proposals/{64-hex-proposal-id}/apply`

Apply requires `If-Match: "{proposal-id}"` and the same unquoted 64-hex value
as `Idempotency-Key`. Theme apply bodies are raw ZIP bytes with
`Content-Type: application/zip`. No generic URL, option, plugin, media, delete,
filesystem, or arbitrary HTML operation exists.

All applies acquire one database- and site-scoped MySQL named lock with a zero
wait. The lock is checked before compare-and-swap, checked again immediately
after the `APPLYING` compare-and-swap commit and before target mutation, held
across the external mutation and terminal audit, and explicitly released.
Uncertain ownership or release fails closed, and a proposal already in
`APPLYING` becomes `NEEDS_RECOVERY`. This also serializes use of WordPress
core's shared theme temporary-backup directory.

Proposal creation and checksum computation use separate fixed-purpose MySQL
named locks with the same database/site scoping. These locks are owned by the
database connection, automatically reclaimed when an interrupted worker's
connection closes, and released only after exact ownership is rechecked. A
release failure never returns a successful create or checksum result. Checksum
cache state is checked again after lock acquisition so a delayed cache-miss
request cannot repeat a completed fresh computation.

Yoast's `wpseo` and `wpseo_social` rows are selected `FOR UPDATE`, compared to
the proposal's exact raw before-state, changed with byte-exact `BINARY`
row-level compare-and-swap, verified while locked, and committed together.
Profile keys use exact replacement so numeric and string non-profile keys keep
their original keys. Transaction rollback never writes a stale array over a
concurrent value. Cache reconciliation and readback happen after commit; any
post-commit drift becomes `NEEDS_RECOVERY`.
The fixed WordPress options table must report the exact `InnoDB` engine through
exact binary schema/table predicates in `information_schema`; exactly one row
must match. An ambiguous, unavailable, or legacy non-transactional engine is
rejected before the transaction begins.

Theme updates capture the complete old tree and use WordPress core temporary
backup APIs. The backup tree must byte-match that capture before any restore.
If the live tree already matches the old capture no restore occurs. After
backup deletion begins, restore is forbidden: a cleanup failure keeps the
verified new theme and becomes `NEEDS_RECOVERY`.

The server does not accept caller-selected theme hashes. The plugin contains a
canonical, hash-anchored capture of the reviewed ST-1704 package and its full
13-file manifest, and normalizes a proposal only when every theme field exactly
matches that server-owned capture. The current capture is the already-installed
`1.1.1` package, so its state is deliberately `NO_REVIEWED_UPGRADE`; theme
proposal creation remains fail-closed until a separately reviewed `1.1.2` or
later package is rebound in a new plugin release. A future bound package is
written to a random 0700 staging directory as one 0600, single-link regular
file. Device/inode, directory identity, size, and SHA-256 are captured after ZIP
validation and rechecked immediately before the upgrader is called. The exact
upgrader instance receives a private random marker and the fixed temporary
backup specification. At WordPress core's last `upgrader_source_selection`
filter, the plugin rechecks the staged ZIP and captures the complete extracted
theme tree against the server-owned manifest before core creates the backup.
At `upgrader_clear_destination`, after core clears the old destination and
immediately before its `move_dir()` or `copy_dir()`, the plugin recaptures the
same extracted root and requires byte-for-byte manifest and filesystem-identity
equality. Either hook rejects a symlink, non-regular node, extra path, changed
file, changed root, wrong destination, wrong upgrader, or wrong marker; a
post-clear refusal uses the already-verified backup restore path.

This boundary assumes the WordPress/PHP operating-system account itself is not
compromised. A malicious process already running as that same filesystem user
can rewrite an installed theme independently of this credential/API bridge and
must be handled as a host compromise.

An exact create retry returns the same 201 receipt and ETag for any of the seven
closed proposal states, including terminal states. Before replay, the plugin
revalidates the stored canonical request bytes, proposal hash, operation,
proposer, timestamps, and exact 900-second lifetime. Replay never inserts,
audits, or changes proposal state; it only lets a client resolve a lost response
and rotate to a new request token when required.
