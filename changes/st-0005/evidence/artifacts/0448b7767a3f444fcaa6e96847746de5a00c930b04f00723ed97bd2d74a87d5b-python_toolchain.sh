#!/bin/bash -p

set -euo pipefail

# Privileged Bash startup ignores BASH_ENV, SHELLOPTS, and inherited functions.
# Remove the startup-file variables before any child process is launched too.
unset BASH_ENV ENV

usage() {
  printf '%s\n' \
    'usage: scripts/python_toolchain.sh --uv ABSOLUTE_PATH COMMAND' \
    '' \
    'Commands: install, lock, lock-check, lock-check-offline, sync,' \
    '          sync-offline, versions, lint, format-check, typecheck,' \
    '          test, check'
}

if (( $# != 3 )) || [[ $1 != --uv ]] || [[ $2 != /* ]]; then
  usage >&2
  exit 64
fi
uv_executable=$2
shift 2

case $1 in
  install) target=python-install ;;
  lock) target=python-lock ;;
  lock-check) target=python-lock-check ;;
  lock-check-offline) target=python-lock-check-offline ;;
  sync) target=python-sync ;;
  sync-offline) target=python-sync-offline ;;
  versions) target=python-tool-versions ;;
  lint) target=python-lint ;;
  format-check) target=python-format-check ;;
  typecheck) target=python-typecheck ;;
  test) target=python-test ;;
  check) target=python-check ;;
  *)
    usage >&2
    exit 64
    ;;
esac

if [[ ! -f $uv_executable || ! -x $uv_executable ]]; then
  printf 'error: uv executable is not a regular executable: %s\n' \
    "$uv_executable" >&2
  exit 69
fi

if ! uv_version=$("$uv_executable" --version); then
  printf 'error: unable to execute uv: %s\n' "$uv_executable" >&2
  exit 69
fi
case $uv_version in
  'uv 0.12.1'|'uv 0.12.1 '*) ;;
  *)
    printf 'error: required uv version ==0.12.1; found: %s\n' "$uv_version" >&2
    exit 69
    ;;
esac

script_directory=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repository_root=$(CDPATH= cd -- "$script_directory/.." && pwd -P)

# GNU Make processes these inputs before the repository Makefile. They are not
# valid evidence inputs, so the trusted wrapper removes them before Make starts.
unset MAKEFLAGS GNUMAKEFLAGS MAKEFILES MFLAGS MAKEOVERRIDES

cd -- "$repository_root"
exec make --no-builtin-rules --no-builtin-variables \
  --file "$repository_root/Makefile" "$target" "UV=$uv_executable"
