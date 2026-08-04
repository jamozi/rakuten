#!/bin/bash -p

PATH=/usr/bin:/bin
export PATH

set -euo pipefail

unset BASH_ENV ENV

if (( EUID == 0 )); then
  printf 'error: network-denied checks must start as a non-root user\n' >&2
  exit 69
fi

usage() {
  printf '%s\n' \
    'usage: scripts/run_network_denied.sh --home ABSOLUTE_DIRECTORY -- ABSOLUTE_COMMAND [ARG ...]'
}

canonicalize_existing() {
  local label=$1
  local input=$2
  local output
  if ! IFS= read -r -d '' output < <(
    realpath --canonicalize-existing --zero -- "$input"
  ); then
    printf 'error: unable to resolve %s: %s\n' "$label" "$input" >&2
    return 69
  fi
  printf -v "$3" '%s' "$output"
}

reject_unsafe_path() {
  local label=$1
  local value=$2
  case $value in
    *'$'* | *'`'* | *'"'* | *'\'* | *$'\r'* | *$'\n'*)
      printf 'error: %s contains unsafe transport characters\n' "$label" >&2
      return 69
      ;;
  esac
}

if (( $# < 4 )) || [[ $1 != --home ]] || [[ $2 != /* ]] || [[ $3 != -- ]] || \
  [[ $4 != /* ]]; then
  usage >&2
  exit 64
fi

requested_home=$2
shift 3

canonicalize_existing 'HOME' "$requested_home" canonical_home
if [[ ! -d $canonical_home ]]; then
  printf 'error: HOME is not a directory\n' >&2
  exit 69
fi
reject_unsafe_path 'canonical HOME path' "$canonical_home"

canonicalize_existing 'command' "$1" canonical_command
if [[ ! -f $canonical_command || ! -x $canonical_command ]]; then
  printf 'error: command is not a regular executable\n' >&2
  exit 69
fi
shift

canonicalize_existing 'wrapper' "${BASH_SOURCE[0]}" wrapper_path
canonicalize_existing 'repository root' "${wrapper_path%/*}/.." repository_root
assertion=$repository_root/scripts/assert_network_denied.py
if [[ ! -f $assertion || -L $assertion ]]; then
  printf 'error: network assertion is not a regular repository file\n' >&2
  exit 69
fi
reject_unsafe_path 'physical repository root' "$repository_root"

unshare_executable=/usr/bin/unshare
if [[ ! -f $unshare_executable || -L $unshare_executable || \
  ! -x $unshare_executable ]]; then
  printf 'error: trusted unshare executable is unavailable\n' >&2
  exit 69
fi
unshare_owner=$(stat --format=%u -- "$unshare_executable")
unshare_mode=$(stat --format=%a -- "$unshare_executable")
if [[ $unshare_owner != 0 ]] || (( (8#$unshare_mode & 0022) != 0 )); then
  printf 'error: unshare executable ownership or mode is unsafe\n' >&2
  exit 69
fi

if ! parent_net_namespace=$(readlink -- /proc/self/ns/net); then
  printf 'error: parent network namespace is unreadable\n' >&2
  exit 69
fi
case $parent_net_namespace in
  'net:['[1-9][0-9]*']') ;;
  *)
    printf 'error: parent network namespace is malformed\n' >&2
    exit 69
    ;;
esac

if ! parent_pid_namespace=$(readlink -- /proc/self/ns/pid); then
  printf 'error: parent process namespace is unreadable\n' >&2
  exit 69
fi
case $parent_pid_namespace in
  'pid:['[1-9][0-9]*']') ;;
  *)
    printf 'error: parent process namespace is malformed\n' >&2
    exit 69
    ;;
esac

cd -- "$repository_root"
exec env -i \
  PATH=/usr/bin:/bin \
  HOME="$canonical_home" \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  TZ=UTC \
  PYTHONDONTWRITEBYTECODE=1 \
  RAOS_PARENT_NET_NS="$parent_net_namespace" \
  RAOS_PARENT_PID_NS="$parent_pid_namespace" \
  RAOS_NETWORK_DENIED=1 \
  /usr/bin/python3 -I -c '
import os
import resource
import stat
import sys

for standard_fd in range(3):
    try:
        mode = os.fstat(standard_fd).st_mode
    except OSError:
        continue
    if stat.S_ISSOCK(mode):
        os._exit(69)
soft_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
if soft_limit == resource.RLIM_INFINITY:
    soft_limit = 1 << 20
os.closerange(3, int(soft_limit))
os.execv(sys.argv[1], sys.argv[1:])
' "$unshare_executable" --user --map-current-user --net --pid --fork \
  --kill-child -- \
  /usr/bin/python3 -I "$assertion" --exec -- "$canonical_command" "$@"
