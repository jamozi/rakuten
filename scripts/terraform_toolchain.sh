#!/bin/bash -p

set -euo pipefail

unset BASH_ENV ENV

usage() {
  printf '%s\n' \
    'usage: scripts/terraform_toolchain.sh --terraform ABSOLUTE_PATH COMMAND' \
    '' \
    'Commands: version, fmt-check'
}

if (( $# != 3 )) || [[ $1 != --terraform ]] || [[ $2 != /* ]]; then
  usage >&2
  exit 64
fi
terraform_executable=$2
command_name=$3

if [[ -L $terraform_executable || ! -f $terraform_executable || ! -x $terraform_executable ]]; then
  printf '%s\n' 'error: terraform executable must be a non-symlink regular executable' >&2
  exit 69
fi

if ! terraform_version_output=$(env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  "$terraform_executable" version -json); then
  printf '%s\n' 'error: unable to execute terraform version probe' >&2
  exit 69
fi

if ! env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  python3 -I -S -c '
import json, sys
payload = json.load(sys.stdin)
if type(payload) is not dict or payload.get("terraform_version") != "1.15.8":
    raise SystemExit(1)
' <<<"$terraform_version_output"; then
  printf '%s\n' 'error: required Terraform version ==1.15.8' >&2
  exit 69
fi

script_directory=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repository_root=$(CDPATH= cd -- "$script_directory/.." && pwd -P)
native_root="$repository_root/infra/terraform/foundation/native"

# Repository evidence commands run with a closed environment. In particular,
# do not inherit Terraform CLI configuration, workspaces, plugin/cache paths,
# cloud credentials, metadata-service controls, or proxy routing.
run_terraform() {
  env -i \
    PATH=/usr/bin:/bin \
    HOME="$repository_root" \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    TF_IN_AUTOMATION=1 \
    CHECKPOINT_DISABLE=1 \
    "$terraform_executable" "$@"
}

case $command_name in
  version)
    printf '%s\n' 'Terraform v1.15.8'
    ;;
  fmt-check)
    run_terraform -chdir="$native_root" fmt -check -diff
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac
