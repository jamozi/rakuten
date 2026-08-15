# ST-0106 hosted network-isolation compatibility

This change restores the existing denied-network boundary on GitHub-hosted
Ubuntu 24.04 without weakening it to a sysctl, AppArmor, or seccomp-only
exception.

The exact owner-approved design is
DESIGN_HANDOFF_V1_ST0106_HOSTED_NETWORK_ISOLATION_COMPATIBILITY_V1.yaml
(13,387 bytes, SHA-256
f53bee06a4ffc16ecbdb16e57ec828712badb6d9da8cfa014f7aa92105671fa2).
The detached approval record preserves the displayed and normalized approval
statement separately.

When the existing unprivileged current-user namespace probe succeeds,
scripts/run_network_denied.sh retains that normal launcher. When it fails, the
wrapper validates fixed root-owned system helpers and passwordless
noninteractive sudo, closes every non-standard descriptor with the kernel
close_range interface independently of mutable caller resource limits, creates
only fresh network/PID/mount namespaces as root, and immediately invokes
setpriv.
setpriv restores the original non-root UID/GID, clears supplementary groups,
drops the complete bounding/inheritable/ambient capability sets, and sets
no_new_privs before the repository assertion or requested command can run.

scripts/assert_network_denied.py now validates a closed launch-mode value. For
the privileged namespace-creation mode, it additionally proves a fresh mount
namespace, an empty supplementary-group list, and zero
inheritable/permitted/effective/bounding/ambient capabilities. The existing
fresh network/PID namespaces, route/interface checks, PID-1 requirement,
socket-denying seccomp filter, local socketpair allowance, descriptor closure,
and descendant cleanup remain mandatory.

The local host supports the unchanged unprivileged path, which is covered by
the focused runtime tests. Its passwordless sudo probe is unavailable, so the
privileged fallback runtime is explicitly
NOT_EXECUTED_PASSWORDLESS_SUDO_UNAVAILABLE; its source ordering, high-FD
closure, and fail-closed privilege assertions are tested locally. A real
GitHub-hosted ubuntu-24.04
pull-request run remains required for hosted fallback evidence.

The hosted Unit test harness uses the workflow's stable
`/usr/bin/python3 -I` system-Python contract rather than assuming that a
version-specific `/usr/bin/python3.10` executable exists on every reviewed
runner image. Two adversarial root-mapped-user-namespace probes remain required
and run in the direct unsandboxed ST-0106 suite. In the already-denied Unit
namespace only, they use the same existing `requires_unsandboxed_parent`
delegation as the other nested-namespace probes; the always-collected outer
assertion must still revalidate the real namespace, non-root identity,
`no_new_privs`, and seccomp boundary before those two cases can be skipped.
This is test-harness compatibility only: the wrapper, assertion, workflow, and
their root-rejection behavior are unchanged.

The ST-0107 manifest is regenerated only as mechanical current-source
provenance. CODEOWNERS, the pull-request template, and the desired-state
ruleset policy must stay byte-identical. This grants no ST-0107 activation,
live-ruleset, status, release, or Production authority.

ST-0202 Storage is a separate Story. No storage runtime, workflow, sysctl,
AppArmor policy, credential, provider, publication, release, or Production
operation is part of this slice. TST-001 and TST-002 remain NOT_EXECUTED until
reviewed hosted evidence is applied through the normal append-only status
process.

## CI cache and reviewed-findings V2 direct candidate

The repository owner separately approved the exact 17,952-byte
`DESIGN_HANDOFF_V1_ST0106_CI_CACHE_AND_REVIEWED_SECRET_FINDINGS_V2.yaml` at
SHA-256
`88a6d97cd70728c860ed7ab1b600d0c8cc69239a48a43d5c1b0c82919ff86e0c`.
Its detached approval authorizes only the repository-local direct candidate on
base commit `8c8b9c4567392886f086d3dd69506619e5a83344`. It does not authorize
staging, commit, push, a pull request, ledger activation, downstream
provenance, hosted evidence, release, or Production.

The Unit job now creates one fresh mode-`0700` uv cache directly below
`RUNNER_TEMP`. Only the network-enabled, source-constrained Unit hydration uses
that cache; Static and Contracts retain their prior no-cache behavior. The
Unit reproduction step transports both the cache and runner-temporary paths as
fixed arguments across the existing denied-network boundary. `ci_job.sh`
canonicalizes them, rejects a missing, relative, unsafe, symlinked,
wrong-owner, wrong-mode, or out-of-root cache, strips ambient cache inputs, and
passes the validated path to Make only as `RAOS_CI_UV_CACHE_DIR`. ST-0102 then
proves a fresh locked offline sync from that exact cache. An explicitly bound
incomplete cache fails; only a direct local ST-0102 run with no explicit cache
retains the documented skip boundary.

The same Unit hydration creates the exact physical-repository
`$GITHUB_WORKSPACE/.npm-cache` only after rejecting a pre-existing path or
symlink, and verifies the new directory is owned by the runner UID/GID with
mode `0700`. The direct pinned npm install hydrates that fixed cache before the
denied-network reproduction invokes the nested ST-0103 Node wrapper and its
fresh offline install. Static and Contracts continue to use separate
runner-temporary npm caches; no reusable Actions cache is introduced.

`scripts/scan_secrets.py` also accepts an optional `--reviewed-findings PATH`.
The file uses a JSON-compatible strict YAML subset so duplicate mapping keys
and YAML aliases, anchors, tags, or merges are not part of the grammar. Its
top-level version, unapproved-candidate status, sole
`GENERIC_CREDENTIAL` rule, and entries are closed. Every entry binds scope,
exact source identifier, physical line, source byte count, source SHA-256,
line SHA-256, closed classification, and a fixed value-free rationale.
Worktree sources must be exact present regular files and an unused entry is an
operational error. History sources use exact Git blob object IDs; an absent
object is inert, while a present object must match every binding. Subtraction
happens only after the scan and only for the exact generic finding set member;
AWS, GitHub, OpenAI, and private-key findings are never suppressible.

The reconciled base inventory contains 31 sanitized worktree locations and 58
sanitized Git-history locations, all under `GENERIC_CREDENTIAL`, with zero
specific-rule findings. The candidate at
`contracts/reviewed-secret-findings.v1.yaml` contains only locations, sizes,
and hashes—never matched bytes. Its immutable internal status remains
`UNAPPROVED_CANDIDATE`, and its frozen bytes remain 46,295 with SHA-256
`1038cf6ef81da0acab528cf8206086646b6e003f5ac0ceed4f2e4b994827bcc7`.

The repository owner subsequently approved that exact ledger and the exact
local CI reference activation within the V2 handoff stop conditions. The
detached record is
`REVIEWED-SECRET-FINDINGS-APPROVAL-v1.yaml`, 5,524 bytes at SHA-256
`b683ae3b3b7312bd4ce04fe2c796f1157542f72c1b1bca79919a71b3a7c1acd9`.
It binds all 89 sanitized reviews, the exact visible and normalized approval
statements, the V2 handoff and its detached approval, and the unchanged ledger
bytes. The Secrets job therefore appends exactly
`--reviewed-findings changes/st-0106/contracts/reviewed-secret-findings.v1.yaml`
to the existing denied-network scan. The scanner, ledger, denied-network
wrapper, and every unrelated job retain their frozen direct-candidate bytes
and semantics.

This approval is only for the exact repository-local workflow reference. It
does not authorize ledger mutation, commit, push, a pull request, merge,
ST-0107 or other downstream provenance mutation, status or canonical changes,
hosted CI, formal TST-001/TST-002 evidence, staging, external writes, release,
or Production. Those remain separately gated.

The approval-named files above are retained as exact audit and allowlist
records for the reviewed ledger contract; they are not an ongoing permission
checkpoint. The repository owner's later standing development authorization
separately covers reversible local implementation, verification,
documentation, and an atomic ST-0106 commit. It does not cover push, pull
request, merge, hosted/formal evidence, status transition, staging, external
writes, release, or Production.

For uv 0.12.1, the explicit cache is accepted only after a fresh project can
rebuild the exact lock with `uv sync --locked --offline`. A deliberate project
drift can then be rejected either as a stale lock or at uv's exact
network-disabled, package-not-in-cache resolver boundary. The latter does not
make an incomplete cache acceptable: cache completeness is proven first, and
arbitrary diagnostics still fail the test.

## Exact-head reviewed-findings reconciliation

The historical v1 ledger and detached owner approval remain byte-identical.
They describe the earlier 31-worktree/58-history universe and are not rewritten
as current authority. The local candidate workflow bytes now reference
`contracts/reviewed-secret-findings.v2.yaml`. The filename is revisioned, but
its strict scanner grammar intentionally remains internal `version: 1`; no
scanner, generic-assignment, placeholder, AST, entropy, RHS, specific-rule, or
subtraction behavior changes.

The v2 ledger is 59,769 bytes at SHA-256
`667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b`.
It binds 115 sanitized metadata records: 31 maintained worktree locations and
84 Git-history blobs. Every finding is `GENERIC_CREDENTIAL`; AWS, GitHub,
OpenAI, and private-key findings are zero. All 31 current worktree line hashes
and all 26 newly reachable history bindings reuse line hashes already reviewed
under v1; the 58 earlier history bindings remain present. Review used only
rule, source kind, path or blob, line, size, source hash, and line hash. No
matched value was displayed or persisted.

`REVIEWED-SECRET-FINDINGS-RECONCILIATION-v2.yaml` separately binds the exact
v1 artifacts, v2 ledger, immutable integration base, current root standing
development authority, exact physical origin-heads-plus-tags snapshot, and
the workflow command. It claims no new repository-owner approval and grants
no external authority. PR 49's V3 scanner/AST/entropy/RHS behavior is recorded
as `NOT_ADOPTED` because it conflicts with the later broad generic-detection
and exact-ledger policy; its nine historical authority artifacts are not
imported.

The value-free `contracts/origin-ref-inventory.v2.txt` freezes the canonical
sorted `git for-each-ref` rows for all 44 origin heads and 17 tags. Its entry
rows hash to
`2a04841be9d2af3c0926adcba9bb7eb8940d0f432c9d62e8e65a5c13b217de28`;
the reconciliation record binds the complete artifact bytes separately.

The workflow delta in the local candidate bytes is only the v1-to-v2 ledger
path rebinding. The generator provenance closure is regenerated mechanically in dependency order,
without changing runtime contracts. ST-0308 is excluded because its ST-0306
handoff-validation dependency is a separate semantic gate. A tracked record
cannot bind the commit containing itself; the final commit/tree is reported
outside tracked artifacts. The exact post-commit standalone replay is
`NOT_EXECUTED`, so handoff and GitHub workflow activation remain `BLOCKED`.
Hosted CI, formal TST-001/TST-002, status, staging, external writes, release,
and Production remain unexecuted and unauthorized by this record.
