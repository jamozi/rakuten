# ST-1506 self-hosted WordPress bounded operator bridge

This additive ST-1506 integration slice packages a least-privilege WordPress
operator and a closed client. It lets Codex inspect operator status and Yoast
checksums and prepare two maintenance operations: applying the exact RAOS Yoast
28.3 profile and updating the exact `kurashinoshirube-child` theme package.

It does not give Codex Administrator authority. Each mutation is an immutable
proposal whose identifier is the SHA-256 of its canonical validated request. A
different human Administrator must approve that identifier in `wp-admin` with a
cookie session, nonce, current-password reauthentication, reason, and typed hash
suffix. Application then requires the same identifier in `If-Match` and the
external `RAOS_OPERATOR_WRITES_ENABLED === true` host constant.

There is no REST approval route and no toggle for the host constant. The executor
role contains only `read`, `raos_operator_read`, `raos_operator_propose`, and
`raos_operator_apply`. Post content/status, publication, taxonomy, media, plugins,
users, arbitrary options, and generic HTTP/PHP/SQL are deliberately absent.
Human plugin activation may idempotently install only the exact executor role and
four-capability set. No REST or CLI role mutation exists, and deactivation or
uninstall does not delete the role, users, fixed bound-user identity, proposals, or
audit records. The fixed identity consists of a site option plus a write-once,
network-global user-meta quarantine marker. Multisite is unsupported, and the
marked Application Password cannot use another subsite, XML-RPC, non-REST, another
origin, or any REST callback outside the four exact routes. Unrelated Application
Password users are unaffected.

Proposal creation uses an owner-private per-operation write-ahead intent so a lost
response cannot silently mint a second proposal. The intent explicitly binds its
canonical-request hash to `proposal_id` and is fsynced before atomic hard-link
publication. A fresh intent rejects replay-shaped or malformed receipts without
clearing the journal. An exact expired or terminal replay clears only that matching
intent and requires a fresh request token on the next invocation. Apply success
codes are operation-specific. Credential
and journal ownership is captured from the effective UID. Proxy environment
variables are inert; ambient TLS overrides fail closed and HTTP debug logging is
forced off before transport. The committed golden vector binds the Python and PHP
canonical JSON implementations. The operational launcher imports the closed runtime
only from already captured current-HEAD bytes, without reopening repository module
paths. Both applies share a global database advisory
mutex with a post-`APPLYING` pre-mutation ownership check. Yoast writes use
byte-exact row CAS and an exact single-row InnoDB proof; theme restore requires a
verified complete backup and never follows backup cleanup. Theme proposals additionally
require a byte-current ST-1704 runtime manifest, per-entry size and SHA-256 equality
with that stage-captured manifest, ASCII case-fold-unique paths, and deterministic
unencrypted `ZIP_STORED` entries; the existing 1.1.1-to-1.1.1 package is
intentionally rejected until a separately reviewed 1.1.2-or-newer release.

Run local checks from the repository root:

```sh
make -f changes/st-1506/self-hosted-wordpress-operator-bridge-v1/Makefile check
```

Live client commands use only `scripts/st1506_wordpress_operator_python.sh` from
the exact owner repository root. The launcher uses a clean isolated CPython 3.14.6
process and verifies current-HEAD runtime bytes before any credential or network
access; direct Python execution is refused.

Build the deterministic owner-private plugin package with `plugin-package`. Read
`OPERATIONS_RUNBOOK.md` before any live bootstrap. Local output is not formal
`TST-032`, staging, release, or Production evidence.
