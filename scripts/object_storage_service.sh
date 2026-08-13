#!/bin/bash -p

PATH=/usr/bin:/bin
export PATH

set -euo pipefail
umask 077

unset BASH_ENV ENV CDPATH GLOBIGNORE

readonly docker_host='unix:///var/run/docker.sock'
readonly minimum_compose_version='2.24.4'
readonly expected_image='docker.io/chrislusf/seaweedfs:4.29@sha256:d47c7ee99fcb951351d7194915f4e3a5ea604a8e8871183d713907dec4fb9bf5'
readonly expected_image_config_digest='sha256:10b004ca7cc8ee13615dbe670e1be047270ab30a742a5944e82330017d64d8fd'
readonly expected_platform='linux/amd64'
readonly expected_revision='1355c7a102194d6c461baf090eff50367b575afb'
readonly expected_version_line='version 8000GB 4.29 1355c7a linux amd64'
readonly expected_compose_sha256='a6cd0109a2bc63dae10be59bd9aa32ab85e9c3fec3847bc43c413b452cb871f5'
readonly expected_fixture_sha256='50bdb508fb979038ecb5e937318fcd17328672f0278ab840af360903d560a527'
readonly local_project='raos-st0202-local'
readonly disposable_port_min=49152
readonly disposable_port_max=65535
readonly disposable_port_range='49152-65535'

docker_executable=''
repository_root=''
compose_file=''
fixture_client=''
docker_config_dir=''
config_file=''
object_storage_port=''
published_port=''
cleanup_project=''
cleanup_volume=false
test_directory=''

usage() {
  printf '%s\n' \
    'usage: scripts/object_storage_service.sh --docker ABSOLUTE_PATH COMMAND' \
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

validate_config_file() {
  local input=$1
  local candidate
  local canonical
  local lexical
  local owner
  local permissions
  local size

  reject_transport_characters 'static identity file path' "$input"
  if [[ $input = /* ]]; then
    candidate=$input
  else
    case $input in
      '' | . | .. | ./*/../* | ../* | */../* | */..)
        error 'relative static identity file path is unsafe'
        return 69
        ;;
    esac
    candidate=$repository_root/$input
  fi
  canonicalize_existing 'static identity file' "$candidate" canonical
  if ! IFS= read -r -d '' lexical < <(
    realpath --canonicalize-missing --no-symlinks --zero -- "$candidate"
  ); then
    error "unable to normalize static identity file path: $candidate"
    return 69
  fi
  if [[ $canonical != "$lexical" ]]; then
    error 'static identity file and every ancestor must be non-symlinked'
    return 69
  fi
  validate_regular_source_file 'static identity file' "$canonical"
  owner=$(stat --format='%u' -- "$canonical")
  if [[ $owner != "$(id -u)" ]]; then
    error 'static identity file must be owned by the current user'
    return 69
  fi
  permissions=$(stat --format='%a' -- "$canonical")
  if [[ $permissions != 600 ]]; then
    error 'static identity file mode must be exactly 0600'
    return 69
  fi
  size=$(stat --format='%s' -- "$canonical")
  if (( size < 1 || size > 16384 )); then
    error 'static identity file must contain between 1 and 16384 bytes'
    return 69
  fi
  config_file=$canonical
  if ! run_fixture validate-config >/dev/null; then
    error 'static identity file failed the maintained schema validation'
    return 69
  fi
}

normalize_bounded_port() {
  local candidate=$1
  if [[ ! $candidate =~ ^[0-9]{1,5}$ ]] || \
    ((10#$candidate < 1024 || 10#$candidate > 65535)); then
    return 1
  fi
  printf -v "$2" '%d' "$((10#$candidate))"
}

validate_port() {
  local candidate=$1
  if ! normalize_bounded_port "$candidate" object_storage_port; then
    error 'RAOS_OBJECT_STORAGE_PORT must be a decimal integer from 1024 through 65535'
    return 64
  fi
}

run_docker() {
  env -i \
    PATH="$PATH" \
    HOME="$docker_config_dir" \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    DOCKER_CONFIG="$docker_config_dir" \
    RAOS_OBJECT_STORAGE_S3_CONFIG_FILE="$config_file" \
    RAOS_OBJECT_STORAGE_PORT="$object_storage_port" \
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

run_fixture() {
  local command=$1
  shift || true
  if [[ $command == create-config ]]; then
    env -i PATH="$PATH" HOME="${test_directory:-$docker_config_dir}" \
      LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
      /usr/bin/python3 -I "$fixture_client" create-config "$@"
    return
  fi
  if [[ $command == validate-config ]]; then
    env -i PATH="$PATH" HOME="${test_directory:-$docker_config_dir}" \
      LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
      /usr/bin/python3 -I "$fixture_client" validate-config \
      --config-file "$config_file"
    return
  fi
  env -i PATH="$PATH" HOME="${test_directory:-$docker_config_dir}" \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    /usr/bin/python3 -I "$fixture_client" "$command" \
    --endpoint "http://127.0.0.1:$published_port" \
    --config-file "$config_file" "$@"
}

assert_compose_model() {
  local project=$1
  local services
  local service
  local object_storage_count=0

  services=$(compose "$project" config --services)
  while IFS= read -r service; do
    case $service in
      object-storage) object_storage_count=$((object_storage_count + 1)) ;;
      postgres) ;;
      '') ;;
      *)
        error "the generated Compose model contains an unreviewed service: $service"
        return 1
        ;;
    esac
  done <<<"$services"
  if ((object_storage_count != 1)); then
    error 'the generated Compose model must contain exactly one object-storage service'
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
  ((observed_major > required_major)) && return 0
  ((observed_major < required_major)) && return 1
  ((observed_minor > required_minor)) && return 0
  ((observed_minor < required_minor)) && return 1
  ((observed_patch >= required_patch))
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
  local image_revision
  local image_version
  local image_license
  local image_source
  local published
  local observed_published_port
  local port_inventory
  local process_uid
  local version_output
  local version_line

  services=$(compose "$project" ps --status running --services)
  if [[ $services != object-storage ]]; then
    error 'the object-storage service is not the sole requested running service'
    return 1
  fi
  container_id=$(compose "$project" ps --quiet object-storage)
  if [[ ! $container_id =~ ^[0-9a-f]{12,64}$ ]]; then
    error 'Compose did not return one valid object-storage container ID'
    return 1
  fi
  health=$(run_docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id")
  if [[ $health != healthy ]]; then
    error 'the object-storage container is not healthy'
    return 1
  fi
  runtime_image=$(run_docker inspect --format '{{.Config.Image}}' "$container_id")
  if [[ $runtime_image != "$expected_image" ]]; then
    error 'the running object-storage image reference differs from the pinned contract'
    return 1
  fi
  image_config_digest=$(run_docker inspect --format '{{.Image}}' "$container_id")
  if [[ $image_config_digest != "$expected_image_config_digest" ]]; then
    error 'the running object-storage image config digest differs from the pinned contract'
    return 1
  fi
  image_platform=$(run_docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image_config_digest")
  if [[ $image_platform != "$expected_platform" ]]; then
    error 'the running object-storage image platform differs from linux/amd64'
    return 1
  fi
  image_revision=$(run_docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_config_digest")
  image_version=$(run_docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$image_config_digest")
  image_license=$(run_docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.licenses"}}' "$image_config_digest")
  image_source=$(run_docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$image_config_digest")
  if [[ $image_revision != "$expected_revision" || $image_version != 4.29 || \
    $image_license != Apache-2.0 || \
    $image_source != https://github.com/seaweedfs/seaweedfs ]]; then
    error 'the running object-storage image labels differ from the verified source snapshot'
    return 1
  fi

  published=$(compose "$project" port object-storage 8333)
  if [[ ! $published =~ ^127\.0\.0\.1:([0-9]+)$ ]] || \
    ! normalize_bounded_port "${BASH_REMATCH[1]}" observed_published_port; then
    error 'the S3 endpoint is not published on one bounded loopback port'
    return 1
  fi
  if [[ $command == test ]] && \
    ((observed_published_port < disposable_port_min || \
      observed_published_port > disposable_port_max)); then
    error 'the disposable S3 endpoint escaped the reviewed random host-port range'
    return 1
  fi
  published_port=$observed_published_port
  port_inventory=$(run_docker port "$container_id")
  if [[ $port_inventory != "8333/tcp -> 127.0.0.1:$published_port" ]]; then
    error 'the object-storage container publishes an unexpected host port'
    return 1
  fi

  process_uid=$(compose "$project" exec -T object-storage /bin/sh -c \
    "sed -n 's/^Uid:[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p' /proc/1/status")
  if [[ $process_uid != 1000 ]]; then
    error 'the object-storage server process did not drop to UID 1000'
    return 1
  fi
  version_output=$(compose "$project" exec -T object-storage /usr/bin/weed version 2>/dev/null)
  version_line=${version_output%%$'\n'*}
  if [[ $version_line != "$expected_version_line" ]]; then
    error "SeaweedFS runtime version differs from the exact 4.29 contract: $version_line"
    return 1
  fi
}

finish_disposable_project() {
  local project=$cleanup_project
  if ! compose "$project" down --volumes --remove-orphans >&2; then
    error 'unable to remove the disposable object-storage project and volume'
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
fixture_client=$repository_root/scripts/object_storage_fixture.py
validate_regular_source_file 'generated Compose file' "$compose_file"
validate_regular_source_file 'object-storage fixture client' "$fixture_client"
compose_sha256=$(sha256sum -- "$compose_file")
compose_sha256=${compose_sha256%% *}
if [[ $compose_sha256 != "$expected_compose_sha256" ]]; then
  error 'generated Compose file digest differs from the wrapper contract'
  exit 69
fi
fixture_sha256=$(sha256sum -- "$fixture_client")
fixture_sha256=${fixture_sha256%% *}
if [[ $fixture_sha256 != "$expected_fixture_sha256" ]]; then
  error 'object-storage fixture client digest differs from the wrapper contract'
  exit 69
fi
if [[ ! -x /usr/bin/python3 || ! -f /usr/bin/python3 ]]; then
  error 'the fixed standard-library Python interpreter is unavailable'
  exit 69
fi

docker_config_dir=$(mktemp -d "${TMPDIR:-/tmp}/raos-st0202-docker-config.XXXXXXXX")
if [[ $command == test ]]; then
  object_storage_port=$disposable_port_range
fi
validate_docker_client

if [[ $command == test ]]; then
  test_directory=$(mktemp -d "${TMPDIR:-/tmp}/raos-st0202-test.XXXXXXXX")
  config_file=$test_directory/object-storage-s3-config.json
  run_fixture create-config --output "$config_file" >/dev/null
  validate_config_file "$config_file"
  cleanup_project="raos-st0202-test-$(id -u)-$$-$RANDOM"
  cleanup_volume=true
  assert_compose_model "$cleanup_project"
  compose "$cleanup_project" up --detach --wait --pull always object-storage
  assert_service "$cleanup_project"
  run_fixture acceptance >/dev/null
  finish_disposable_project
  printf '%s\n' \
    '{"formal_tst_014":"NOT_EXECUTED","mode":"test","runtime":"LOCAL_CANDIDATE_PASS","status":"PASS","story_id":"ST-0202"}'
  exit 0
fi

validate_config_file "${RAOS_OBJECT_STORAGE_S3_CONFIG_FILE:-.secrets/object-storage-s3-config.json}"
validate_port "${RAOS_OBJECT_STORAGE_PORT:-8333}"
assert_compose_model "$local_project"

case $command in
  config)
    printf '%s\n' \
      '{"formal_tst_014":"NOT_EXECUTED","mode":"config","status":"PASS","story_id":"ST-0202"}'
    ;;
  up)
    compose "$local_project" up --detach --wait --pull always object-storage
    assert_service "$local_project"
    run_fixture bootstrap >/dev/null
    printf '%s\n' \
      '{"formal_tst_014":"NOT_EXECUTED","mode":"up","runtime":"LOCAL_CANDIDATE_PASS","status":"PASS","story_id":"ST-0202"}'
    ;;
  check)
    assert_service "$local_project"
    run_fixture acceptance >/dev/null
    printf '%s\n' \
      '{"formal_tst_014":"NOT_EXECUTED","mode":"check","runtime":"LOCAL_CANDIDATE_PASS","status":"PASS","story_id":"ST-0202"}'
    ;;
  down)
    compose "$local_project" down --remove-orphans
    printf '%s\n' \
      '{"formal_tst_014":"NOT_EXECUTED","mode":"down","preserved_volume":true,"status":"PASS","story_id":"ST-0202"}'
    ;;
esac
