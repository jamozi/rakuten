#!/bin/bash -p

PATH=/usr/bin:/bin
export PATH

set -euo pipefail
umask 077

unset BASH_ENV ENV CDPATH GLOBIGNORE

readonly docker_host='unix:///var/run/docker.sock'
readonly minimum_compose_version='2.24.4'
readonly expected_image='postgres:18.4-bookworm@sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296'
readonly expected_image_config_digest='sha256:0a314d409a9633cff4f89dc18482262625c0ee78cb1aa2ff8e47bc6da0251e1b'
readonly expected_platform='linux/amd64'
readonly expected_compose_sha256='2fac28cdd185b3070e0cc5616953948a92e05b50ebebae70bfc3323765b287b7'
readonly expected_server_version_num='180004'
readonly local_project='raos-st0201-local'

docker_executable=''
repository_root=''
compose_file=''
docker_config_dir=''
password_file=''
postgres_port=''
cleanup_project=''
cleanup_volume=false
test_directory=''

usage() {
  printf '%s\n' \
    'usage: scripts/postgres_service.sh --docker ABSOLUTE_PATH COMMAND' \
    '' \
    'Commands: config, up, check, down, test'
}

error() {
  printf 'error: %s\n' "$1" >&2
}

canonicalize_existing() {
  local label=$1
  local input=$2
  local output
  if ! IFS= read -r -d '' output < <(
    realpath --canonicalize-existing --zero -- "$input"
  ); then
    error "unable to resolve $label: $input"
    return 69
  fi
  printf -v "$3" '%s' "$output"
}

reject_transport_characters() {
  local label=$1
  local value=$2
  case $value in
    *$'\r'* | *$'\n'*)
      error "$label contains forbidden control characters"
      return 69
      ;;
  esac
}

validate_regular_source_file() {
  local label=$1
  local path=$2
  if [[ ! -f $path || -L $path ]]; then
    error "$label must be a regular non-symlink file: $path"
    return 69
  fi
}

validate_secret_file() {
  local input=$1
  local candidate
  local canonical
  local lexical
  local owner
  local permissions
  local size

  reject_transport_characters 'password file path' "$input"
  if [[ $input = /* ]]; then
    candidate=$input
  else
    case $input in
      '' | . | .. | ./*/../* | ../* | */../* | */..)
        error 'relative password file path is unsafe'
        return 69
        ;;
    esac
    candidate=$repository_root/$input
  fi
  canonicalize_existing 'password file' "$candidate" canonical
  if ! IFS= read -r -d '' lexical < <(
    realpath --canonicalize-missing --no-symlinks --zero -- "$candidate"
  ); then
    error "unable to normalize password file path: $candidate"
    return 69
  fi
  if [[ $canonical != "$lexical" ]]; then
    error 'password file and every ancestor must be non-symlinked'
    return 69
  fi
  validate_regular_source_file 'password file' "$canonical"
  owner=$(stat --format='%u' -- "$canonical")
  if [[ $owner != "$(id -u)" ]]; then
    error 'password file must be owned by the current user'
    return 69
  fi
  permissions=$(stat --format='%a' -- "$canonical")
  if [[ $permissions != 600 ]]; then
    error 'password file mode must be exactly 0600'
    return 69
  fi
  size=$(stat --format='%s' -- "$canonical")
  if (( size < 1 || size > 1024 )); then
    error 'password file must contain between 1 and 1024 bytes'
    return 69
  fi
  password_file=$canonical
}

validate_port() {
  local candidate=$1
  if [[ ! $candidate =~ ^[0-9]+$ ]] || (( 10#$candidate < 1024 || 10#$candidate > 65535 )); then
    error 'RAOS_POSTGRES_PORT must be a decimal integer from 1024 through 65535'
    return 64
  fi
  postgres_port=$((10#$candidate))
}

run_docker() {
  env -i \
    PATH="$PATH" \
    HOME="$docker_config_dir" \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    DOCKER_CONFIG="$docker_config_dir" \
    RAOS_POSTGRES_PASSWORD_FILE="$password_file" \
    RAOS_POSTGRES_PORT="$postgres_port" \
    "$docker_executable" --host "$docker_host" "$@"
}

compose() {
  local project=$1
  shift
  run_docker compose \
    --project-directory "$repository_root" \
    --file "$compose_file" \
    --project-name "$project" \
    "$@"
}

assert_compose_model() {
  local project=$1
  local services

  services=$(compose "$project" config --services)
  if [[ $services != postgres ]]; then
    error 'the generated Compose model must contain exactly the PostgreSQL service'
    return 1
  fi
  compose "$project" config --quiet
}

version_at_least() {
  local observed=${1#v}
  observed=${observed%%-*}
  observed=${observed%%+*}
  local required=$2
  local observed_major observed_minor observed_patch
  local required_major required_minor required_patch
  IFS=. read -r observed_major observed_minor observed_patch <<<"$observed"
  IFS=. read -r required_major required_minor required_patch <<<"$required"
  if [[ ! ${observed_major:-} =~ ^[0-9]+$ || \
        ! ${observed_minor:-} =~ ^[0-9]+$ || \
        ! ${observed_patch:-} =~ ^[0-9]+$ ]]; then
    return 1
  fi
  (( observed_major > required_major )) && return 0
  (( observed_major < required_major )) && return 1
  (( observed_minor > required_minor )) && return 0
  (( observed_minor < required_minor )) && return 1
  (( observed_patch >= required_patch ))
}

validate_docker_client() {
  local client_version
  local compose_version
  if ! client_version=$(env -i PATH="$PATH" HOME="$docker_config_dir" \
      DOCKER_CONFIG="$docker_config_dir" "$docker_executable" --version); then
    error 'unable to execute the selected Docker client'
    return 69
  fi
  if [[ $client_version != Docker\ version\ * ]]; then
    error 'selected executable did not identify itself as a Docker client'
    return 69
  fi
  if ! compose_version=$(run_docker compose version --short); then
    error 'the selected Docker client has no usable Compose plugin'
    return 69
  fi
  if ! version_at_least "$compose_version" "$minimum_compose_version"; then
    error "Docker Compose >=$minimum_compose_version is required; found: $compose_version"
    return 69
  fi
}

assert_service() {
  local project=$1
  local services
  local container_id
  local health
  local runtime_image
  local image_config_digest
  local image_platform
  local version

  services=$(compose "$project" ps --status running --services)
  if [[ $services != postgres ]]; then
    error 'the PostgreSQL service is not the sole requested running service'
    return 1
  fi
  container_id=$(compose "$project" ps --quiet postgres)
  if [[ ! $container_id =~ ^[0-9a-f]{12,64}$ ]]; then
    error 'Compose did not return one valid PostgreSQL container ID'
    return 1
  fi
  health=$(run_docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id")
  if [[ $health != healthy ]]; then
    error 'the PostgreSQL container is not healthy'
    return 1
  fi
  runtime_image=$(run_docker inspect --format '{{.Config.Image}}' "$container_id")
  if [[ $runtime_image != "$expected_image" ]]; then
    error 'the running PostgreSQL container image reference differs from the pinned contract'
    return 1
  fi
  image_config_digest=$(run_docker inspect --format '{{.Image}}' "$container_id")
  if [[ $image_config_digest != "$expected_image_config_digest" ]]; then
    error 'the running PostgreSQL image config digest differs from the pinned linux/amd64 contract'
    return 1
  fi
  image_platform=$(run_docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image_config_digest")
  if [[ $image_platform != "$expected_platform" ]]; then
    error 'the running PostgreSQL image platform differs from linux/amd64'
    return 1
  fi
  version=$(compose "$project" exec -T postgres \
    psql --username raos --dbname raos --tuples-only --no-align \
    --command 'SHOW server_version_num;')
  version=${version//[[:space:]]/}
  if [[ $version != "$expected_server_version_num" ]]; then
    error "PostgreSQL server_version_num differs from the exact 18.4 contract: $version"
    return 1
  fi
}

finish_disposable_project() {
  local project=$cleanup_project

  if ! compose "$project" down --volumes --remove-orphans >&2; then
    error 'unable to remove the disposable PostgreSQL project and volume'
    return 1
  fi
  cleanup_project=''
  cleanup_volume=false
}

cleanup() {
  local exit_status=$?
  set +e
  if [[ -n $cleanup_project && -n $docker_executable && -n $docker_config_dir ]]; then
    if [[ $cleanup_volume == true ]]; then
      compose "$cleanup_project" down --volumes --remove-orphans >/dev/null 2>&1
    else
      compose "$cleanup_project" down --remove-orphans >/dev/null 2>&1
    fi
  fi
  if [[ -n $test_directory && -d $test_directory ]]; then
    find "$test_directory" -depth -mindepth 1 -delete >/dev/null 2>&1
    rmdir -- "$test_directory" >/dev/null 2>&1
  fi
  if [[ -n $docker_config_dir && -d $docker_config_dir ]]; then
    find "$docker_config_dir" -depth -mindepth 1 -delete >/dev/null 2>&1
    rmdir -- "$docker_config_dir" >/dev/null 2>&1
  fi
  trap - EXIT HUP INT TERM
  exit "$exit_status"
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if (( $# != 3 )) || [[ $1 != --docker ]] || [[ $2 != /* ]]; then
  usage >&2
  exit 64
fi

canonicalize_existing 'Docker executable' "$2" docker_executable
reject_transport_characters 'Docker executable path' "$docker_executable"
if [[ ! -f $docker_executable || ! -x $docker_executable ]]; then
  error "Docker executable must be a regular executable: $docker_executable"
  exit 69
fi

command=$3
case $command in
  config | up | check | down | test) ;;
  *)
    usage >&2
    exit 64
    ;;
esac

canonicalize_existing 'wrapper path' "${BASH_SOURCE[0]}" wrapper_path
canonicalize_existing 'repository root' "${wrapper_path%/*}/.." repository_root
reject_transport_characters 'repository root' "$repository_root"
compose_file=$repository_root/docker-compose.yml
manifest_file=$repository_root/changes/st-0201/manifest.yaml
validate_regular_source_file 'generated Compose file' "$compose_file"
validate_regular_source_file 'generated manifest' "$manifest_file"
compose_sha256=$(sha256sum -- "$compose_file")
compose_sha256=${compose_sha256%% *}
if [[ $compose_sha256 != "$expected_compose_sha256" ]]; then
  error 'generated Compose file digest differs from the wrapper contract'
  exit 69
fi

docker_config_dir=$(mktemp -d "${TMPDIR:-/tmp}/raos-st0201-docker-config.XXXXXXXX")
validate_docker_client

if [[ $command == test ]]; then
  test_directory=$(mktemp -d "${TMPDIR:-/tmp}/raos-st0201-test.XXXXXXXX")
  password_file=$test_directory/postgres_password
  {
    printf 'raos-st0201-'
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
    printf '\n'
  } >"$password_file"
  chmod 0600 "$password_file"
  # A set-but-empty value makes ${RAOS_POSTGRES_PORT-5432} omit HOST_PORT,
  # which is Compose's documented ephemeral-publish form.
  postgres_port=''
  cleanup_project="raos-st0201-test-$(id -u)-$$-$RANDOM"
  cleanup_volume=true
  assert_compose_model "$cleanup_project"
  compose "$cleanup_project" up --detach --wait --pull always postgres
  assert_service "$cleanup_project"
  finish_disposable_project
  printf '%s\n' \
    '{"formal_tst_008":"NOT_EXECUTED","mode":"test","runtime":"LOCAL_PASS","server_version_num":"180004","status":"PASS","story_id":"ST-0201"}'
  exit 0
fi

validate_secret_file "${RAOS_POSTGRES_PASSWORD_FILE:-.secrets/postgres_password}"
validate_port "${RAOS_POSTGRES_PORT:-5432}"
assert_compose_model "$local_project"

case $command in
  config)
    printf '%s\n' \
      '{"formal_tst_008":"NOT_EXECUTED","mode":"config","status":"PASS","story_id":"ST-0201"}'
    ;;
  up)
    compose "$local_project" up --detach --wait --pull always postgres
    assert_service "$local_project"
    printf '%s\n' \
      '{"formal_tst_008":"NOT_EXECUTED","mode":"up","server_version_num":"180004","status":"PASS","story_id":"ST-0201"}'
    ;;
  check)
    assert_service "$local_project"
    printf '%s\n' \
      '{"formal_tst_008":"NOT_EXECUTED","mode":"check","server_version_num":"180004","status":"PASS","story_id":"ST-0201"}'
    ;;
  down)
    compose "$local_project" down --remove-orphans
    printf '%s\n' \
      '{"formal_tst_008":"NOT_EXECUTED","mode":"down","preserved_volume":true,"status":"PASS","story_id":"ST-0201"}'
    ;;
esac
