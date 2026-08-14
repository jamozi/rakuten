# ST-0106 hosted recovery revisions

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

The ST-0107 manifest is regenerated only as mechanical current-source
provenance. CODEOWNERS, the pull-request template, and the desired-state
ruleset policy must stay byte-identical. This grants no ST-0107 activation,
live-ruleset, status, release, or Production authority.

ST-0202 Storage is a separate Story. No storage runtime, workflow, sysctl,
AppArmor policy, credential, provider, publication, release, or Production
operation is part of this slice. TST-001 and TST-002 remain NOT_EXECUTED until
reviewed hosted evidence is applied through the normal append-only status
process.

## Hosted Secrets high-confidence classifier

The immutable V1 design record
`DESIGN_HANDOFF_V1_ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V1.yaml` (26,930
bytes, SHA-256
`849705be6fba2a205275bb3c4f393f2bfb99ddd77dc30386dcf958de1344c5cf`) is
retained as audit history. Exact implementation exposed a contradiction
between its declaration-first fixture grammar and three protected kind-first
observations, so V1 implementation authority was superseded by the immutable
V2 record
`DESIGN_HANDOFF_V1_ST0106_HOSTED_SECRETS_HIGH_CONFIDENCE_V2.yaml` (18,951
bytes, SHA-256
`019d8b1394b70a98aa2b7c7d0493eb55a20e043b7ea4cce758655229b058ae9a`). The
full candidate-overlay gate then exposed a bounded matcher contradiction and
floating entropy order dependence. Exact implementation authority is now the
owner-approved 30,873-byte V3 handoff at SHA-256
`2afd9f9684649e48ac3e96f82d205e60091f11b8877b1e43c464723e2a38a7bd`.
All three handoffs, detached approvals, and explanatory companions remain
byte-identical audit records. V1 and V2 produced no implementation commit.

The scanner still applies the existing AWS, GitHub, OpenAI, and private-key
rules first. A generic assignment is suppressed only by an approved complete
placeholder or sentinel, declaration-first not-real fixture, external
reference, bare closed-AST source expression, or bare lower-case symbolic
reference. All remaining values pass the common six-distinct-byte gate and
the exact digit-bearing, digit-free opaque, or lower-case passphrase evidence
families. Prefix and substring words such as `fake`, `sample`, `fixture`, and
`example` grant no exemption.

V3 retains the V2 case-sensitive, full-value kind-first fixture grammar:

```text
(?:client-secret|access-token)-not-real-[0-9]+-x{4,}
```

The hyphens, nonempty ASCII decimal identifier, and at least four lower-case
`x` padding bytes are mandatory. One complete ASCII/Python `str` or `bytes`
literal may be decoded only for this exact decision. No other kind, separator,
identifier, padding, wrapper, residual value, path, line, archive member, Git
blob, or source receives an exemption.

V3 adds one bounded same-physical-line reconstruction decision. It is reached
only after an otherwise-live digit-bearing bare capture is proven ASCII and
syntactically incomplete under Python 3.10. Reconstruction starts at the
original value span and ends at that physical line's raw content boundary. It
accepts only one size-, token-, node-, depth-, and literal-bounded
printable-ASCII eval expression that passes the existing closed AST and raw
suspicious-literal validator. Comments, semicolons, trailing whitespace,
continuations, multiline material, assignments, multiple or residual
expressions, unmatched delimiters, unsupported AST, non-ASCII, and every limit
defect retain the original finding. No callable, operation, attribute, AST
node, literal form, path, blob, or expected-count exemption is added.
Provider bytes overlapping the original captured span retain the existing
provider-only precedence. Provider or private-key bytes found only in the
omitted RHS retain their specific finding and, when the full RHS is refused,
the original generic finding as well.

Floating Shannon entropy is removed. Each existing evidence family uses a
fixed 256-slot byte histogram and the exact integer comparison
`n ** (b*n) >= 2 ** (a*n) * product(c_i ** (b*c_i))`, with the closed reduced
rationals `7/2`, `15/4`, and `33/10`. Equality is included. Byte order, hash
seed, summation order, and `libm` cannot change the result; float, logarithm,
`Decimal`, epsilon, tolerance, and fallback paths are absent. Empty input is
false, while invalid internal constants, impossible histogram state,
overlength direct input, and arithmetic or resource failure reach the existing
sanitized internal-error boundary.

The identical classifier applies to the maintained worktree, bounded nested
archives, and every fetched Git blob. Provider precedence, sanitized
location/rule-only output, archive and traversal failures, CLI and exit codes,
the denied-network wrapper, the workflow, and the hosted Unit selector are
unchanged. Local hostile and regression results are implementation evidence
only; a reviewed GitHub-hosted run and the append-only status process are still
required for formal TST-001/TST-002 evidence. This repair grants no credential,
provider, push, pull-request, merge, publication, release, staging, or
Production authority. The final cut is exactly the six maintained payload and
documentation paths plus the nine immutable V1/V2/V3 authority records.
