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

validate_privileged_helper() {
  local label=$1
  local path=$2
  local require_setuid=$3
  local owner
  local mode
  if [[ ! -f $path || -L $path || ! -x $path ]]; then
    printf 'error: trusted %s executable is unavailable\n' "$label" >&2
    return 69
  fi
  owner=$(stat --format=%u -- "$path")
  mode=$(stat --format=%a -- "$path")
  if [[ $owner != 0 ]] || (( (8#$mode & 0022) != 0 )); then
    printf 'error: %s executable ownership or mode is unsafe\n' "$label" >&2
    return 69
  fi
  if [[ $require_setuid == true ]] && (( (8#$mode & 04000) == 0 )); then
    printf 'error: %s executable is not set-user-ID root\n' "$label" >&2
    return 69
  fi
}

readonly close_descriptors_program='
import ctypes
import os
import stat
import sys

for standard_fd in range(3):
    try:
        mode = os.fstat(standard_fd).st_mode
    except OSError:
        continue
    if stat.S_ISSOCK(mode):
        os._exit(69)
try:
    close_range = ctypes.CDLL(None, use_errno=True).close_range
except AttributeError:
    os._exit(69)
close_range.argtypes = (ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
close_range.restype = ctypes.c_int
if close_range(3, (1 << 32) - 1, 0) != 0:
    os._exit(69)
os.execv(sys.argv[1], sys.argv[1:])
'

caller_uid=$EUID
caller_gid=$(id -g)
if [[ ! $caller_uid =~ ^[1-9][0-9]*$ || ! $caller_gid =~ ^[1-9][0-9]*$ ]]; then
  printf 'error: caller identity is not a supported non-root numeric identity\n' >&2
  exit 69
fi

launch_mode=UNPRIVILEGED_USER_NAMESPACE
if ! env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  "$unshare_executable" --user --map-current-user -- /bin/true \
  >/dev/null 2>&1; then
  readonly sudo_executable=/usr/bin/sudo
  readonly setpriv_executable=/usr/bin/setpriv
  validate_privileged_helper sudo "$sudo_executable" true
  validate_privileged_helper unshare "$unshare_executable" false
  validate_privileged_helper setpriv "$setpriv_executable" false
  if ! env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    /usr/bin/python3 -I -c "$close_descriptors_program" \
    "$sudo_executable" -n -- /bin/true >/dev/null 2>&1; then
    printf '%s\n' \
      'error: user namespaces are unavailable and a trusted passwordless sudo fallback is not authorized' >&2
    exit 69
  fi
  launch_mode=PRIVILEGED_NAMESPACE_THEN_DROP
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

if ! parent_mount_namespace=$(readlink -- /proc/self/ns/mnt); then
  printf 'error: parent mount namespace is unreadable\n' >&2
  exit 69
fi
case $parent_mount_namespace in
  'mnt:['[1-9][0-9]*']') ;;
  *)
    printf 'error: parent mount namespace is malformed\n' >&2
    exit 69
    ;;
esac

cd -- "$repository_root"
common_environment=(
  PATH=/usr/bin:/bin \
  HOME="$canonical_home" \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  TZ=UTC \
  PYTHONDONTWRITEBYTECODE=1 \
  RAOS_PARENT_NET_NS="$parent_net_namespace" \
  RAOS_PARENT_PID_NS="$parent_pid_namespace" \
  RAOS_PARENT_MNT_NS="$parent_mount_namespace" \
  RAOS_NETWORK_LAUNCH_MODE="$launch_mode" \
  RAOS_NETWORK_DENIED=1 \
)
if [[ $launch_mode == UNPRIVILEGED_USER_NAMESPACE ]]; then
  launcher=(
    "$unshare_executable" --user --map-current-user --net --pid --fork
    --kill-child --
    /usr/bin/python3 -I "$assertion" --exec -- "$canonical_command" "$@"
  )
else
  launcher=(
    "$sudo_executable" -n --
    /usr/bin/env -i "${common_environment[@]}"
    "$unshare_executable" --net --pid --mount --fork --kill-child --mount-proc
    "$setpriv_executable"
    --reuid="$caller_uid" --regid="$caller_gid" --clear-groups
    --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs --
    /usr/bin/python3 -I "$assertion" --exec -- "$canonical_command" "$@"
  )
fi

exec env -i "${common_environment[@]}" \
  /usr/bin/python3 -I -c "$close_descriptors_program" "${launcher[@]}"
