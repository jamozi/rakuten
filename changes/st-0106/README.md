# ST-0106 hosted network-isolation compatibility

## Developer Loop Simplification V1

`changes/st-0106/contracts/developer-loop-scope.v1.json` is the versioned
affected-CI and local-check contract. `scripts/classify_ci_scope.py` is a
standard-library-only classifier. Pull requests always run `Secrets`; docs-only
changes run a lightweight `Static`; a single ordinary Story runs `Static`, its
focused `Unit` suite, and `Secrets`; high-risk, unknown, or multi-Story changes
run all six Base CI contexts. Pushes to `main`, scheduled runs, and manual runs
also run all six contexts. Classifier failure makes every required context fail
rather than reporting a successful skip.

The affected path is deliberately finite and fail closed. The versioned
contract names the reviewed ordinary Story IDs and exact tracked paths; a path must
satisfy both proofs to remain ordinary. Every other detected Story, every
Story-local surface that cannot be identified, and every Story-bearing build
script runs full Base CI. This makes a newly added or previously omitted Story
full by default instead of relying on an ever-growing high-risk allowlist.
Imported Canonical and upstream sources remain prohibited edit targets and are
also classified full if they nevertheless appear in a diff.

The fast local entrypoint is:

```bash
make dev-check STORY=ST-0106
make dev-check STORY=ST-0106 BASE_REF=origin/main
make dev-check STORY=ST-0106 STORIES=ST-0106,ST-0107 BASE_REF=main
```

It unions committed, staged, unstaged, and untracked paths. Story detection
uses the same classifier helper for Story-local names, exact ordinary-path
bindings, and generated-output owner bindings. It runs Git whitespace checks,
changed-language checks, every declared and detected isolated Story suite
exactly once, and allowlisted owner generator checks; and emits one
`RAOS_DEV_CHECK_V1` JSON receipt whose `executed_story_suites` lists each suite. A changed
`.secrets/**` path makes the orchestrator fail before child commands and exposes
only the sensitive-path count. The orchestrator does not pass private path names
to its checks, but pytest and generator children remain trusted local processes
with ambient environment access; this command is not a filesystem or network
sandbox. `STORIES` is required when a named integration slice changes more than
one detected Story. This receipt is focused local evidence only, not hosted Base
CI, formal TST-001/TST-002, live, release, or Production evidence.

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

## Current-main V2 reconciliation candidate

The repository owner selected the exact-reviewed-findings V2 strategy over
the mutually exclusive global V3 classifier strategy for reconstruction from
current `main`. That selection does not approve any newly computed ledger
bytes or per-location classification. The approved v1 ledger, its detached
approval, the active workflow reference, and the scanner/network/CI wrappers
therefore remain byte-identical.

`contracts/reviewed-secret-findings.v2.yaml` preserves the exact 115-entry
candidate from PR #50: 31 worktree and 84 Git-history bindings. All 115 are
members of the current sanitized finding set, but the file remains
`UNAPPROVED_CANDIDATE` and is not referenced by the workflow. A fresh physical
non-shallow clone of all 62 actual origin heads and 17 tags found 119 locations:
31 worktree and 88 Git history, all `GENERIC_CREDENTIAL`, with zero specific
AWS, GitHub, OpenAI, or private-key finding.

The unchanged active v1 reference is fail closed rather than current-main
clean: exact denied-network replay exits operationally with
`reviewed-finding-source-size-drift` before emitting findings. Its historical
approval remains immutable, but it is not evidence that the present source and
origin universe pass the Secrets job.

Four new history bindings have line hashes absent from both the owner-approved
v1 ledger and PR #50's V2 candidate. They are recorded only as value-free
`pending_exact_owner_review` metadata in
`REVIEWED-SECRET-FINDINGS-RECONCILIATION-v2.yaml`; they are not ledger entries,
not classified as false positives, and have no no-live-credential rationale.
Denied-network replay with the 115-entry V2 candidate intentionally exits with
those four sanitized generic findings. This is the required fail-closed result,
not a scan pass.

Before V2 can replace v1, the four pending locations require exact owner review,
incident escalation for any plausible credential, regenerated candidate bytes,
separate exact-hash owner approval, a refreshed standalone origin inventory,
Security/Engineering review, and executable hosted CI. Downstream provenance is
unchanged until that activation gate is satisfied. Formal TST-001/TST-002,
status, external writes, staging, release, and Production remain unexecuted.

## Current-main V2 exact activation

The repository owner subsequently approved the exact source candidate commit
`9ea1a52ded96c8d6532fe180997d2e60f7bb2a45`, the unchanged 59,769-byte V2
ledger at SHA-256
`667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b`,
the value-free false-positive classification of the four reconciled Python
`ast.Call` locations with no string literal, and the exact V1-to-V2 Secrets
workflow reference switch.

The historical reconciliation remains byte-identical and continues to record
what was unapproved when that candidate was created. The append-only
`REVIEWED-SECRET-FINDINGS-ACTIVATION-v2.yaml` binds the later approval,
candidate, ledger, four sanitized locations, workflow before/after hashes, and
the refreshed public-origin inventory without storing matched content. The four
locations are not added to the exact ledger and receive no suppression
authority; if their objects become reachable again, the unchanged scanner
fails closed on them as new generic findings.

At activation preflight, a physical standalone clone contained the then-current
five origin heads and seventeen tags, including the newly created Base-CI
restoration branch. Denied-network replay of the exact candidate checkout and
V2 ledger returned clean with only the network-isolation report and no scanner
finding line. The workflow change replaces the V1 path with the V2 path exactly
once; reconstructing that path recovers the complete pre-activation workflow
bytes. Scanner, network wrapper, CI wrapper, ledger, Canonical, status, and
unrelated workflow semantics remain unchanged.

This local activation is not hosted CI or formal TST-001/TST-002 evidence. It
does not mutate ST-0107/downstream provenance and grants no external, staging,
release, publication, or Production authority.
