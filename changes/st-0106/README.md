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

The ST-0107 manifest is regenerated only as mechanical current-source
provenance. CODEOWNERS, the pull-request template, and the desired-state
ruleset policy must stay byte-identical. This grants no ST-0107 activation,
live-ruleset, status, release, or Production authority.

ST-0202 Storage is a separate Story. No storage runtime, workflow, sysctl,
AppArmor policy, credential, provider, publication, release, or Production
operation is part of this slice. TST-001 and TST-002 remain NOT_EXECUTED until
reviewed hosted evidence is applied through the normal append-only status
process.
