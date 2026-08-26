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
readonly expected_version_line='version 30GB 4.29 1355c7a10 linux amd64'
readonly expected_compose_sha256='a6cd0109a2bc63dae10be59bd9aa32ab85e9c3fec3847bc43c413b452cb871f5'
readonly expected_fixture_sha256='50bdb508fb979038ecb5e937318fcd17328672f0278ab840af360903d560a527'
readonly expected_ephemeral_override_sha256='92e141f0c1b96ef47cf79855951d6cadaec509b9796cc03067186ff44dd27239'
readonly expected_ephemeral_override_bytes=382
readonly maximum_ephemeral_override_bytes=512
readonly minimum_ephemeral_port=1024
readonly maximum_ephemeral_port=65535
readonly local_project='raos-st0202-local'

docker_executable=''
docker_candidate=''
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
ephemeral_override_file=''

usage() {
  printf '%s\n' \
    'usage: scripts/object_storage_service.sh --docker EXECUTABLE COMMAND' \
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

normalize_ephemeral_port() {
  local candidate=$1
  if [[ ! $candidate =~ ^[0-9]{1,5}$ ]] || \
    ((10#$candidate < minimum_ephemeral_port || \
      10#$candidate > maximum_ephemeral_port)); then
    return 1
  fi
  printf -v "$2" '%d' "$((10#$candidate))"
}

normalize_observed_port() {
  if [[ $command == test ]]; then
    normalize_ephemeral_port "$1" "$2"
  else
    normalize_bounded_port "$1" "$2"
  fi
}

validate_port() {
  local candidate=$1
  if ! normalize_bounded_port "$candidate" object_storage_port; then
    error 'RAOS_OBJECT_STORAGE_PORT must be a decimal integer from 1024 through 65535'
    return 64
  fi
}

validate_test_directory() {
  local owner
  local permissions

  if [[ -z $test_directory || ! -d $test_directory || -L $test_directory ]]; then
    error 'the disposable test directory must be a regular non-symlink directory'
    return 69
  fi
  owner=$(stat --format='%u' -- "$test_directory")
  if [[ $owner != "$(id -u)" ]]; then
    error 'the disposable test directory must be owned by the current user'
    return 69
  fi
  permissions=$(stat --format='%a' -- "$test_directory")
  if [[ $permissions != 700 ]]; then
    error 'the disposable test directory mode must be exactly 0700'
    return 69
  fi
}

validate_ephemeral_override() {
  local digest
  local owner
  local permissions
  local size

  validate_test_directory || return $?
  case $ephemeral_override_file in
    "$test_directory"/object-storage-disposable-port.override.*.yml) ;;
    *)
      error 'the ephemeral Compose override escaped the disposable test directory'
      return 69
      ;;
  esac
  if [[ ! -f $ephemeral_override_file || -L $ephemeral_override_file ]]; then
    error 'the ephemeral Compose override must be a regular non-symlink file'
    return 69
  fi
  owner=$(stat --format='%u' -- "$ephemeral_override_file")
  if [[ $owner != "$(id -u)" ]]; then
    error 'the ephemeral Compose override must be owned by the current user'
    return 69
  fi
  permissions=$(stat --format='%a' -- "$ephemeral_override_file")
  if [[ $permissions != 600 ]]; then
    error 'the ephemeral Compose override mode must be exactly 0600'
    return 69
  fi
  size=$(stat --format='%s' -- "$ephemeral_override_file")
  if ((size < 1 || size > maximum_ephemeral_override_bytes || \
    size != expected_ephemeral_override_bytes)); then
    error 'the ephemeral Compose override size differs from the exact contract'
    return 69
  fi
  digest=$(sha256sum -- "$ephemeral_override_file")
  digest=${digest%% *}
  if [[ $digest != "$expected_ephemeral_override_sha256" ]]; then
    error 'the ephemeral Compose override digest differs from the exact contract'
    return 69
  fi
}

create_ephemeral_override() {
  if [[ ! -f /usr/bin/mktemp || -L /usr/bin/mktemp || ! -x /usr/bin/mktemp ]]; then
    error 'the fixed mktemp executable is unavailable or unsafe'
    return 69
  fi
  validate_test_directory
  if ! ephemeral_override_file=$(
    /usr/bin/mktemp \
      "$test_directory/object-storage-disposable-port.override.XXXXXXXX.yml"
  ); then
    error 'unable to create the ephemeral Compose override'
    return 69
  fi
  if ! printf '%s\n' \
    'services:' \
    '  object-storage:' \
    '    ports: !override' \
    '      - target: 8333' \
    '        host_ip: 127.0.0.1' \
    '        protocol: tcp' \
    '    networks: !override' \
    '      - object_storage_internal' \
    '      - object_storage_disposable_publish' \
    'networks:' \
    '  object_storage_disposable_publish:' \
    '    driver: bridge' \
    '    internal: false' \
    '    driver_opts:' \
    '      com.docker.network.bridge.enable_ip_masquerade: "false"' \
    >"$ephemeral_override_file"; then
    error 'unable to write the ephemeral Compose override'
    return 69
  fi
  validate_ephemeral_override
}

run_docker() {
  local -a environment=(
    env -i \
    PATH="$PATH" \
    HOME="$docker_config_dir" \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    DOCKER_CONFIG="$docker_config_dir" \
    RAOS_OBJECT_STORAGE_S3_CONFIG_FILE="$config_file"
  )
  if [[ $command != test ]]; then
    environment+=(RAOS_OBJECT_STORAGE_PORT="$object_storage_port")
  fi
  if [[ $command == test && ${1:-} == compose ]]; then
    validate_ephemeral_override || return $?
  fi
  "${environment[@]}" "$docker_executable" --host "$docker_host" "$@"
}

compose_raw() {
  local project=$1
  shift
  local -a compose_files=(--file "$compose_file")
  if [[ $command == test ]]; then
    compose_files+=(--file "$ephemeral_override_file")
  fi
  run_docker compose \
    --project-directory "$repository_root" \
    "${compose_files[@]}" \
    --project-name "$project" \
    "$@"
}

compose() {
  local project=$1
  shift
  assert_compose_model "$project" || return $?
  compose_raw "$project" "$@"
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

  if ! compose_raw "$project" config --format json | \
    /usr/bin/python3 -I -c '
import json
import sys

command = sys.argv[1]
expected_published = sys.argv[2]
try:
    model = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeError):
    raise SystemExit(1)
if not isinstance(model, dict):
    raise SystemExit(1)
services = model.get("services")
if not isinstance(services, dict) or set(services) != {"postgres", "object-storage"}:
    raise SystemExit(1)
service = services.get("object-storage")
if not isinstance(service, dict):
    raise SystemExit(1)
ports = service.get("ports")
if not isinstance(ports, list) or len(ports) != 1:
    raise SystemExit(1)
port = ports[0]
if not isinstance(port, dict):
    raise SystemExit(1)
target = port.get("target")
if isinstance(target, bool) or not isinstance(target, int) or target != 8333:
    raise SystemExit(1)
for key, value in {"host_ip": "127.0.0.1", "protocol": "tcp"}.items():
    observed = port.get(key)
    if not isinstance(observed, str) or observed != value:
        raise SystemExit(1)
if command == "test":
    if "published" in port:
        raise SystemExit(1)
    expected_service_networks = {
        "object_storage_internal",
        "object_storage_disposable_publish",
    }
else:
    observed = port.get("published")
    if not isinstance(observed, str) or observed != expected_published:
        raise SystemExit(1)
    expected_service_networks = {"object_storage_internal"}

service_networks = service.get("networks")
if not isinstance(service_networks, dict) or set(service_networks) != expected_service_networks:
    raise SystemExit(1)
if any(value not in (None, {}) for value in service_networks.values()):
    raise SystemExit(1)

networks = model.get("networks")
expected_networks = {"postgres_internal", "object_storage_internal"}
if command == "test":
    expected_networks.add("object_storage_disposable_publish")
if not isinstance(networks, dict) or set(networks) != expected_networks:
    raise SystemExit(1)

internal_network = networks.get("object_storage_internal")
if not isinstance(internal_network, dict):
    raise SystemExit(1)
if internal_network.get("driver") != "bridge" or internal_network.get("internal") is not True:
    raise SystemExit(1)
if internal_network.get("driver_opts") not in (None, {}):
    raise SystemExit(1)
if any(internal_network.get(key, False) is not False for key in ("external", "attachable", "enable_ipv6")):
    raise SystemExit(1)

if command == "test":
    publish_network = networks.get("object_storage_disposable_publish")
    if not isinstance(publish_network, dict):
        raise SystemExit(1)
    if publish_network.get("driver") != "bridge":
        raise SystemExit(1)
    if publish_network.get("internal", False) is not False:
        raise SystemExit(1)
    if any(publish_network.get(key, False) is not False for key in ("external", "attachable", "enable_ipv6")):
        raise SystemExit(1)
    if publish_network.get("driver_opts") != {
        "com.docker.network.bridge.enable_ip_masquerade": "false"
    }:
        raise SystemExit(1)
' "$command" "$object_storage_port"; then
    error 'the normalized Compose model differs from the exact object-storage port and network contract'
    return 69
  fi
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
  local runtime_init
  local published
  local observed_published_port
  local port_inventory
  local root_process_model
  local server_process_model
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
  runtime_init=$(run_docker inspect --format '{{.HostConfig.Init}}' "$container_id")
  if [[ $runtime_init != true ]]; then
    error 'the object-storage container did not retain the required init process'
    return 1
  fi

  published=$(compose "$project" port object-storage 8333)
  if [[ ! $published =~ ^127\.0\.0\.1:([0-9]+)$ ]] || \
    ! normalize_observed_port "${BASH_REMATCH[1]}" observed_published_port; then
    error 'the S3 endpoint is not published on one bounded loopback port'
    return 1
  fi
  published_port=$observed_published_port
  port_inventory=$(run_docker port "$container_id")
  if [[ $port_inventory != "8333/tcp -> 127.0.0.1:$published_port" ]]; then
    error 'the object-storage container publishes an unexpected host port'
    return 1
  fi

  if ! root_process_model=$(run_docker exec "$container_id" /bin/sh -eu -c '
load_status() {
  status_path=$1
  status_pid=
  status_ppid=
  status_state=
  status_uids=
  status_gids=
  status_cap_eff=
  status_pid_count=0
  status_ppid_count=0
  status_state_count=0
  status_uid_count=0
  status_gid_count=0
  status_cap_eff_count=0
  while IFS= read -r status_line || [ -n "$status_line" ]; do
    case $status_line in
      Pid:*)
        status_pid_count=$((status_pid_count + 1))
        set -- ${status_line#Pid:}
        [ "$#" -eq 1 ] || return 1
        status_pid=$1
        ;;
      PPid:*)
        status_ppid_count=$((status_ppid_count + 1))
        set -- ${status_line#PPid:}
        [ "$#" -eq 1 ] || return 1
        status_ppid=$1
        ;;
      State:*)
        status_state_count=$((status_state_count + 1))
        set -- ${status_line#State:}
        [ "$#" -ge 1 ] || return 1
        status_state=$1
        ;;
      Uid:*)
        status_uid_count=$((status_uid_count + 1))
        set -- ${status_line#Uid:}
        [ "$#" -eq 4 ] || return 1
        status_uids=$1:$2:$3:$4
        ;;
      Gid:*)
        status_gid_count=$((status_gid_count + 1))
        set -- ${status_line#Gid:}
        [ "$#" -eq 4 ] || return 1
        status_gids=$1:$2:$3:$4
        ;;
      CapEff:*)
        status_cap_eff_count=$((status_cap_eff_count + 1))
        set -- ${status_line#CapEff:}
        [ "$#" -eq 1 ] || return 1
        status_cap_eff=$1
        ;;
    esac
  done < "$status_path"
  [ "$status_pid_count" -eq 1 ] &&
    [ "$status_ppid_count" -eq 1 ] &&
    [ "$status_state_count" -eq 1 ] &&
    [ "$status_uid_count" -eq 1 ] &&
    [ "$status_gid_count" -eq 1 ] &&
    [ "$status_cap_eff_count" -eq 1 ]
}

load_server_child() {
  server_pid=
  server_count=0
  children=
  IFS= read -r children < /proc/1/task/1/children || [ -n "$children" ]
  set -- $children
  for candidate in "$@"; do
    case $candidate in
      ""|*[!0-9]*) return 1 ;;
    esac
    [ "$candidate" = "$observer_pid" ] && continue
    server_count=$((server_count + 1))
    server_pid=$candidate
  done
  [ "$server_count" -eq 1 ] && [ "$server_pid" -ne 1 ]
}

load_starttime() {
  process_pid=$1
  stat_line=
  IFS= read -r stat_line < "/proc/$process_pid/stat" || [ -n "$stat_line" ]
  stat_fields=${stat_line##*) }
  [ "$stat_fields" != "$stat_line" ] || return 1
  set -- $stat_fields
  [ "$#" -ge 20 ] || return 1
  shift 19
  process_starttime=$1
  case $process_starttime in
    ""|*[!0-9]*) return 1 ;;
  esac
}

observer_pid=$$
case $observer_pid in
  ""|*[!0-9]*) exit 1 ;;
esac
[ "$observer_pid" -ne 1 ] || exit 1

load_status /proc/1/status || exit 1
[ "$status_pid" = 1 ] && [ "$status_ppid" = 0 ] || exit 1
[ "$status_uids" = 0:0:0:0 ] && [ "$status_gids" = 0:0:0:0 ] || exit 1
case $status_state in ""|Z|X|x) exit 1 ;; esac
init_executable=$(readlink /proc/1/exe 2>/dev/null) || exit 1
[ "$init_executable" = /sbin/docker-init ] || exit 1

load_server_child || exit 1
first_server_pid=$server_pid
load_status "/proc/$first_server_pid/status" || exit 1
[ "$status_pid" = "$first_server_pid" ] && [ "$status_ppid" = 1 ] || exit 1
[ "$status_uids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_gids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_cap_eff" = 0000000000000000 ] || exit 1
case $status_state in ""|Z|X|x) exit 1 ;; esac
load_starttime "$first_server_pid" || exit 1
first_starttime=$process_starttime

load_server_child || exit 1
[ "$server_pid" = "$first_server_pid" ] || exit 1
load_status "/proc/$server_pid/status" || exit 1
[ "$status_pid" = "$server_pid" ] && [ "$status_ppid" = 1 ] || exit 1
[ "$status_uids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_gids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_cap_eff" = 0000000000000000 ] || exit 1
case $status_state in ""|Z|X|x) exit 1 ;; esac
load_starttime "$server_pid" || exit 1
[ "$process_starttime" = "$first_starttime" ] || exit 1

printf "%s\n" RAOS_OBJECT_STORAGE_ROOT_PROCESS_MODEL_V1
' 2>/dev/null); then
    error 'the object-storage root process model could not be verified'
    return 1
  fi
  if [[ $root_process_model != RAOS_OBJECT_STORAGE_ROOT_PROCESS_MODEL_V1 ]]; then
    error 'the object-storage root process model differs from the pinned contract'
    return 1
  fi

  if ! server_process_model=$(run_docker exec --user 1000:1000 "$container_id" /bin/sh -eu -c '
load_status() {
  status_path=$1
  status_pid=
  status_ppid=
  status_state=
  status_uids=
  status_gids=
  status_cap_eff=
  status_pid_count=0
  status_ppid_count=0
  status_state_count=0
  status_uid_count=0
  status_gid_count=0
  status_cap_eff_count=0
  while IFS= read -r status_line || [ -n "$status_line" ]; do
    case $status_line in
      Pid:*)
        status_pid_count=$((status_pid_count + 1))
        set -- ${status_line#Pid:}
        [ "$#" -eq 1 ] || return 1
        status_pid=$1
        ;;
      PPid:*)
        status_ppid_count=$((status_ppid_count + 1))
        set -- ${status_line#PPid:}
        [ "$#" -eq 1 ] || return 1
        status_ppid=$1
        ;;
      State:*)
        status_state_count=$((status_state_count + 1))
        set -- ${status_line#State:}
        [ "$#" -ge 1 ] || return 1
        status_state=$1
        ;;
      Uid:*)
        status_uid_count=$((status_uid_count + 1))
        set -- ${status_line#Uid:}
        [ "$#" -eq 4 ] || return 1
        status_uids=$1:$2:$3:$4
        ;;
      Gid:*)
        status_gid_count=$((status_gid_count + 1))
        set -- ${status_line#Gid:}
        [ "$#" -eq 4 ] || return 1
        status_gids=$1:$2:$3:$4
        ;;
      CapEff:*)
        status_cap_eff_count=$((status_cap_eff_count + 1))
        set -- ${status_line#CapEff:}
        [ "$#" -eq 1 ] || return 1
        status_cap_eff=$1
        ;;
    esac
  done < "$status_path"
  [ "$status_pid_count" -eq 1 ] &&
    [ "$status_ppid_count" -eq 1 ] &&
    [ "$status_state_count" -eq 1 ] &&
    [ "$status_uid_count" -eq 1 ] &&
    [ "$status_gid_count" -eq 1 ] &&
    [ "$status_cap_eff_count" -eq 1 ]
}

load_server_child() {
  server_pid=
  server_count=0
  children=
  IFS= read -r children < /proc/1/task/1/children || [ -n "$children" ]
  set -- $children
  for candidate in "$@"; do
    case $candidate in
      ""|*[!0-9]*) return 1 ;;
    esac
    [ "$candidate" = "$observer_pid" ] && continue
    server_count=$((server_count + 1))
    server_pid=$candidate
  done
  [ "$server_count" -eq 1 ] && [ "$server_pid" -ne 1 ]
}

load_starttime() {
  process_pid=$1
  stat_line=
  IFS= read -r stat_line < "/proc/$process_pid/stat" || [ -n "$stat_line" ]
  stat_fields=${stat_line##*) }
  [ "$stat_fields" != "$stat_line" ] || return 1
  set -- $stat_fields
  [ "$#" -ge 20 ] || return 1
  shift 19
  process_starttime=$1
  case $process_starttime in
    ""|*[!0-9]*) return 1 ;;
  esac
}

observer_pid=$$
case $observer_pid in
  ""|*[!0-9]*) exit 1 ;;
esac
[ "$observer_pid" -ne 1 ] || exit 1

load_server_child || exit 1
first_server_pid=$server_pid
load_status "/proc/$first_server_pid/status" || exit 1
[ "$status_pid" = "$first_server_pid" ] && [ "$status_ppid" = 1 ] || exit 1
[ "$status_uids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_gids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_cap_eff" = 0000000000000000 ] || exit 1
case $status_state in ""|Z|X|x) exit 1 ;; esac
server_executable=$(readlink "/proc/$first_server_pid/exe" 2>/dev/null) || exit 1
[ "$server_executable" = /usr/bin/weed ] || exit 1
load_starttime "$first_server_pid" || exit 1
first_starttime=$process_starttime

load_server_child || exit 1
[ "$server_pid" = "$first_server_pid" ] || exit 1
load_status "/proc/$server_pid/status" || exit 1
[ "$status_pid" = "$server_pid" ] && [ "$status_ppid" = 1 ] || exit 1
[ "$status_uids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_gids" = 1000:1000:1000:1000 ] || exit 1
[ "$status_cap_eff" = 0000000000000000 ] || exit 1
case $status_state in ""|Z|X|x) exit 1 ;; esac
server_executable=$(readlink "/proc/$server_pid/exe" 2>/dev/null) || exit 1
[ "$server_executable" = /usr/bin/weed ] || exit 1
load_starttime "$server_pid" || exit 1
[ "$process_starttime" = "$first_starttime" ] || exit 1

printf "%s\n" RAOS_OBJECT_STORAGE_SERVER_PROCESS_MODEL_V1
' 2>/dev/null); then
    error 'the object-storage same-UID server process model could not be verified'
    return 1
  fi
  if [[ $server_process_model != RAOS_OBJECT_STORAGE_SERVER_PROCESS_MODEL_V1 ]]; then
    error 'the object-storage same-UID server process model differs from the pinned contract'
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

if (( $# != 3 )) || [[ $1 != --docker ]]; then
  usage >&2
  exit 64
fi

reject_transport_characters 'Docker executable' "$2"
if [[ $2 == */* ]]; then
  docker_candidate=$2
elif ! docker_candidate=$(type -P -- "$2"); then
  error "Docker executable is unavailable on the safe PATH: $2"
  exit 69
fi
canonicalize_existing 'Docker executable' "$docker_candidate" docker_executable
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
  if [[ ! -f /usr/bin/mktemp || -L /usr/bin/mktemp || ! -x /usr/bin/mktemp ]]; then
    error 'the fixed mktemp executable is unavailable or unsafe'
    exit 69
  fi
  test_directory=$(
    /usr/bin/mktemp -d "${TMPDIR:-/tmp}/raos-st0202-test.XXXXXXXX"
  )
  validate_test_directory
  create_ephemeral_override
  config_file=$test_directory/object-storage-s3-config.json
  run_fixture create-config --output "$config_file" >/dev/null
  validate_config_file "$config_file"
  validate_ephemeral_override
fi
validate_docker_client

if [[ $command == test ]]; then
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
