#!/bin/bash -p

PATH=/usr/bin:/bin
export PATH

set -euo pipefail

unset BASH_ENV ENV RAOS_CI_UV_CACHE_DIR RUNNER_TEMP UV_CACHE_DIR

clean_path=$PATH
original_home=${HOME:-}

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
    'usage: scripts/ci_job.sh --uv ABSOLUTE_PATH --node ABSOLUTE_PATH --npm-cli ABSOLUTE_PATH [--uv-cache ABSOLUTE_DIRECTORY --runner-temp ABSOLUTE_DIRECTORY] JOB' \
    '' \
    'Jobs: static, unit, contracts (the explicit cache pair is valid only for unit)'
}

if (( $# != 7 && $# != 11 )) || [[ $1 != --uv ]] || [[ $2 != /* ]] || \
  [[ $3 != --node ]] || [[ $4 != /* ]] || [[ $5 != --npm-cli ]] || \
  [[ $6 != /* ]]; then
  usage >&2
  exit 64
fi

uv_executable=$2
node_executable=$4
npm_cli=$6
uv_cache_directory=
runner_temp_directory=
if (( $# == 11 )); then
  if [[ $7 != --uv-cache ]] || [[ $8 != /* ]] || \
    [[ $9 != --runner-temp ]] || [[ ${10} != /* ]]; then
    usage >&2
    exit 64
  fi
  uv_cache_directory=$8
  runner_temp_directory=${10}
  job=${11}
else
  job=$7
fi

case $job in
  static) target=ci-static ;;
  unit) target=ci-unit ;;
  contracts) target=ci-contracts ;;
  *)
    usage >&2
    exit 64
    ;;
esac
if [[ $job == unit && -z $uv_cache_directory ]]; then
  printf 'error: the unit job requires an explicit uv cache and runner temporary directory\n' >&2
  exit 64
fi
if [[ -n $uv_cache_directory && $job != unit ]]; then
  printf 'error: an explicit uv cache is valid only for the unit job\n' >&2
  exit 64
fi

canonicalize_existing 'uv executable' "$uv_executable" canonical_uv
canonicalize_existing 'Node executable' "$node_executable" canonical_node
canonicalize_existing 'npm CLI' "$npm_cli" canonical_npm_cli
if [[ -n $uv_cache_directory ]]; then
  canonicalize_existing 'uv cache directory' \
    "$uv_cache_directory" canonical_uv_cache_directory
  canonicalize_existing 'runner temporary directory' \
    "$runner_temp_directory" canonical_runner_temp_directory
  if [[ $canonical_uv_cache_directory != "$uv_cache_directory" || \
    $canonical_runner_temp_directory != "$runner_temp_directory" ]]; then
    printf 'error: uv cache and runner temporary paths must be exact canonical paths\n' >&2
    exit 69
  fi
fi
if [[ $original_home != /* ]]; then
  printf 'error: HOME must be an absolute existing directory\n' >&2
  exit 69
fi
canonicalize_existing 'user home' "$original_home" canonical_user_home

reject_make_unsafe_path 'canonical uv executable path' "$canonical_uv"
reject_make_unsafe_path 'canonical Node executable path' "$canonical_node"
reject_make_unsafe_path 'canonical npm CLI path' "$canonical_npm_cli"
reject_make_unsafe_path 'canonical user home path' "$canonical_user_home"
if [[ -n $uv_cache_directory ]]; then
  reject_make_unsafe_path 'canonical uv cache path' \
    "$canonical_uv_cache_directory"
  reject_make_unsafe_path 'canonical runner temporary path' \
    "$canonical_runner_temp_directory"
fi

uv_executable=$canonical_uv
node_executable=$canonical_node
npm_cli=$canonical_npm_cli

make_cache_argument=()
if [[ -n $uv_cache_directory ]]; then
  if [[ ! -d $canonical_uv_cache_directory || \
    -L $canonical_uv_cache_directory ]]; then
    printf 'error: uv cache must be a regular directory\n' >&2
    exit 69
  fi
  case $canonical_uv_cache_directory in
    "$canonical_runner_temp_directory"/*) ;;
    *)
      printf 'error: uv cache must be below the runner temporary directory\n' >&2
      exit 69
      ;;
  esac
  cache_owner=$(stat --format=%u -- "$canonical_uv_cache_directory")
  cache_mode=$(stat --format=%a -- "$canonical_uv_cache_directory")
  if [[ $cache_owner != "$EUID" || $cache_mode != 700 ]]; then
    printf 'error: uv cache ownership or mode is unsafe\n' >&2
    exit 69
  fi
  make_cache_argument=(
    "RAOS_CI_UV_CACHE_DIR=$canonical_uv_cache_directory"
  )
fi

for executable in "$uv_executable" "$node_executable"; do
  if [[ ! -f $executable || ! -x $executable ]]; then
    printf 'error: required executable is not a regular executable: %s\n' \
      "$executable" >&2
    exit 69
  fi
done
if [[ ! -f $npm_cli ]]; then
  printf 'error: npm CLI is not a regular file: %s\n' "$npm_cli" >&2
  exit 69
fi

if ! uv_version=$(env -i PATH="$clean_path" "$uv_executable" --version); then
  printf 'error: unable to execute uv: %s\n' "$uv_executable" >&2
  exit 69
fi
case $uv_version in
  'uv 0.12.1'|'uv 0.12.1 '*) ;;
  *)
    printf 'error: required uv version ==0.12.1; found: %s\n' \
      "$uv_version" >&2
    exit 69
    ;;
esac

if ! node_version=$(env -i PATH="$clean_path" "$node_executable" --version); then
  printf 'error: unable to execute Node: %s\n' "$node_executable" >&2
  exit 69
fi
if [[ $node_version != v24.18.1 ]]; then
  printf 'error: required Node version ==24.18.1; found: %s\n' \
    "$node_version" >&2
  exit 69
fi

if ! npm_version=$(
  env -i PATH="$clean_path" "$node_executable" "$npm_cli" --version
); then
  printf 'error: unable to execute npm CLI: %s\n' "$npm_cli" >&2
  exit 69
fi
if [[ $npm_version != 11.16.0 ]]; then
  printf 'error: required npm version ==11.16.0; found: %s\n' \
    "$npm_version" >&2
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
network_wrapper=$repository_root/scripts/run_network_denied.sh
network_assertion=$repository_root/scripts/assert_network_denied.py
for network_file in "$network_wrapper" "$network_assertion"; do
  if [[ ! -f $network_file || -L $network_file ]]; then
    printf 'error: required network-isolation file is unsafe: %s\n' \
      "$network_file" >&2
    exit 69
  fi
done
if [[ ! -x $network_wrapper ]]; then
  printf 'error: network-isolation wrapper is not executable\n' >&2
  exit 69
fi

cd -- "$repository_root"
printf '%s\n' 'CI_PHASE network=denied purpose=repository-checks'
if [[ ${RAOS_NETWORK_DENIED:-} == 1 ]]; then
  /usr/bin/python3 -I "$network_assertion"
  exec /usr/bin/make --no-builtin-rules --no-builtin-variables \
    --file Makefile "$target" \
    RAOS_CI_OFFLINE=1 \
    "UV=$uv_executable" "NODE=$node_executable" "NPM_CLI=$npm_cli" \
    "${make_cache_argument[@]}"
fi
exec "$network_wrapper" --home "$canonical_user_home" -- \
  /usr/bin/make --no-builtin-rules --no-builtin-variables \
    --file Makefile "$target" \
    RAOS_CI_OFFLINE=1 \
    "UV=$uv_executable" "NODE=$node_executable" "NPM_CLI=$npm_cli" \
    "${make_cache_argument[@]}"
