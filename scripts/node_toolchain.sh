#!/bin/bash -p

PATH=/usr/bin:/bin
export PATH

set -euo pipefail

# Privileged Bash startup ignores BASH_ENV, SHELLOPTS, and inherited functions.
# Remove startup-file variables before any child process is launched too.
unset BASH_ENV ENV

clean_path=$PATH

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

reject_make_unsafe_path() {
  local label=$1
  local value=$2
  case $value in
    *'$'* | *'`'* | *'"'* | *'\'* | *$'\r'* | *$'\n'*)
      printf 'error: %s contains characters unsafe for Make or shell transport\n' \
        "$label" >&2
      return 69
      ;;
  esac
}

usage() {
  printf '%s\n' \
    'usage: scripts/node_toolchain.sh --node ABSOLUTE_PATH --npm-cli ABSOLUTE_PATH COMMAND' \
    '' \
    'Commands: lock, lock-check, sync, sync-offline, versions, format-check,' \
    '          lint, typecheck, pyright, test, check'
}

if (( $# != 5 )) || [[ $1 != --node ]] || [[ $2 != /* ]] || \
  [[ $3 != --npm-cli ]] || [[ $4 != /* ]]; then
  usage >&2
  exit 64
fi
node_executable=$2
npm_cli=$4
command=$5

canonicalize_existing 'Node executable' "$node_executable" canonical_node
canonicalize_existing 'npm CLI' "$npm_cli" canonical_npm_cli
reject_make_unsafe_path 'canonical Node executable path' "$canonical_node"
reject_make_unsafe_path 'canonical npm CLI path' "$canonical_npm_cli"
node_executable=$canonical_node
npm_cli=$canonical_npm_cli

case $command in
  lock) target=node-lock ;;
  lock-check) target=node-lock-check ;;
  sync) target=node-sync ;;
  sync-offline) target=node-sync-offline ;;
  versions) target=node-tool-versions ;;
  format-check) target=node-format-check ;;
  lint) target=node-lint ;;
  typecheck) target=node-typecheck ;;
  pyright) target=node-pyright ;;
  test) target=node-test ;;
  check) target=node-check ;;
  *)
    usage >&2
    exit 64
    ;;
esac

if [[ ! -f $node_executable || ! -x $node_executable ]]; then
  printf 'error: Node executable is not a regular executable: %s\n' \
    "$node_executable" >&2
  exit 69
fi
if [[ ! -f $npm_cli ]]; then
  printf 'error: npm CLI is not a regular file: %s\n' "$npm_cli" >&2
  exit 69
fi

if ! node_version=$(env -i PATH="$clean_path" "$node_executable" --version); then
  printf 'error: unable to execute Node: %s\n' "$node_executable" >&2
  exit 69
fi
if [[ $node_version != v24.18.1 ]]; then
  printf 'error: required Node version ==24.18.1; found: %s\n' "$node_version" >&2
  exit 69
fi
if ! npm_version=$(env -i PATH="$clean_path" "$node_executable" "$npm_cli" --version); then
  printf 'error: unable to execute npm CLI: %s\n' "$npm_cli" >&2
  exit 69
fi
if [[ $npm_version != 11.16.0 ]]; then
  printf 'error: required npm version ==11.16.0; found: %s\n' "$npm_version" >&2
  exit 69
fi

canonicalize_existing 'Node installation prefix' \
  "${node_executable%/*}/.." node_prefix
reject_make_unsafe_path 'canonical Node installation prefix' "$node_prefix"
expected_npm_cli=$node_prefix/lib/node_modules/npm/bin/npm-cli.js
if [[ $npm_cli != "$expected_npm_cli" ]]; then
  printf 'error: npm CLI is not bundled with the selected Node: expected %s; found %s\n' \
    "$expected_npm_cli" "$npm_cli" >&2
  exit 69
fi

canonicalize_existing 'wrapper path' "${BASH_SOURCE[0]}" wrapper_path
canonicalize_existing 'repository root' "${wrapper_path%/*}/.." repository_root
reject_make_unsafe_path 'physical repository root' "$repository_root"

# Start Make with an allowlisted environment. This removes npm_config_ aliases,
# NODE_OPTIONS/NODE_PATH, virtual-environment state, shell startup files, and
# GNU Make preparse controls rather than trying to enumerate every spelling.
cd -- "$repository_root"
exec env -i \
  PATH="$clean_path" \
  HOME="$repository_root" \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  TZ=UTC \
  COREPACK_ENABLE_NETWORK=0 \
  COREPACK_ENABLE_PROJECT_SPEC=0 \
  COREPACK_HOME="$repository_root/.npm-cache/corepack" \
  NEXT_TELEMETRY_DISABLED=1 \
  NPM_CONFIG_USERCONFIG="$repository_root/.npmrc" \
  NPM_CONFIG_GLOBALCONFIG=/dev/null \
  make --no-builtin-rules --no-builtin-variables \
    --file Makefile "$target" \
    "NODE=$node_executable" "NPM_CLI=$npm_cli"
