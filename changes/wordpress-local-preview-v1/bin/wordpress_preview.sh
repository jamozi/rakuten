#!/usr/bin/env bash

set -euo pipefail

readonly script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly slice_directory="$(cd "$script_directory/.." && pwd -P)"
readonly repository_root="$(cd "$slice_directory/../.." && pwd -P)"
readonly compose_file="$slice_directory/compose.yaml"
readonly repository_identity="$(printf '%s' "$repository_root" | sha256sum | cut -c1-12)"
readonly project_name="raos-wordpress-preview-$repository_identity"
readonly derived_preview_port="$((20000 + 16#${repository_identity:0:4} % 20000))"
readonly preview_port="${RAOS_WORDPRESS_PREVIEW_PORT:-$derived_preview_port}"
[[ "$preview_port" =~ ^[0-9]{4,5}$ \
  && "$preview_port" -ge 1024 && "$preview_port" -le 65535 ]] \
  || { printf '%s\n' RAOS_WORDPRESS_PREVIEW_PORT_INVALID >&2; exit 69; }
readonly preview_origin="http://127.0.0.1:$preview_port"
readonly preview_article_path=/local-preview-carry-on-suitcase-under-100-seats/
readonly docker_bin="${RAOS_WORDPRESS_PREVIEW_DOCKER_BIN:-docker}"
readonly curl_bin="${RAOS_WORDPRESS_PREVIEW_CURL_BIN:-curl}"
readonly default_private_root="$repository_root/.secrets/wordpress-local-preview"
readonly private_root="${RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT:-$default_private_root}"
readonly credentials_file="$private_root/credentials.env"
readonly requested_fixture_root="${RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT:-}"
readonly link_mode="${RAOS_WORDPRESS_LINK_MODE:-measured-admin}"
[[ "$link_mode" == standard-api || "$link_mode" == measured-admin ]] \
  || { printf '%s\n' RAOS_WORDPRESS_PREVIEW_LINK_MODE_INVALID >&2; exit 69; }
if [[ -n "$requested_fixture_root" ]]; then
  readonly materialized_fixture_root="$requested_fixture_root"
  readonly fixture_override_enabled=true
else
  readonly materialized_fixture_root="$private_root/materialized-fixtures-v2"
  readonly fixture_override_enabled=false
fi
readonly product_media_root="$private_root/product-media"
readonly plugin_cache_root="$private_root/plugins"
readonly yoast_root="$plugin_cache_root/wordpress-seo"
readonly download_cache_root="$private_root/downloads"
readonly yoast_archive="$download_cache_root/wordpress-seo.28.3.zip"
readonly yoast_checksums="$download_cache_root/wordpress-seo.28.3.checksums.json"
readonly yoast_archive_url='https://downloads.wordpress.org/plugin/wordpress-seo.28.3.zip'
readonly yoast_checksums_url='https://downloads.wordpress.org/plugin-checksums/wordpress-seo/28.3.json'
readonly yoast_archive_bytes=5151735
readonly yoast_archive_sha256=381edc1603147bd76af81341f21c9155ff3e9f6ce29ed20886d889fb9d6744fb
readonly yoast_checksums_bytes=343370
readonly yoast_checksums_sha256=1773aaadf88827311b488877c069aefcb6422e8dc6d5a7f50c1bd492d34bf85f
readonly yoast_lock="$repository_root/changes/st-1704/self-hosted-editorial-pilot-v1/theme/yoast-seo-28.3.lock.json"
readonly yoast_materializer="$slice_directory/bin/materialize_yoast.py"
readonly python_bin="${RAOS_WORDPRESS_PREVIEW_PYTHON_BIN:-$repository_root/.venv/bin/python}"
readonly materializer_script="$repository_root/scripts/raos_editorial_portfolio_v2.py"
readonly test_materializer_bin="${RAOS_WORDPRESS_PREVIEW_TEST_MATERIALIZER_BIN:-}"
readonly test_yoast_materializer_bin="${RAOS_WORDPRESS_PREVIEW_TEST_YOAST_MATERIALIZER_BIN:-}"

fail() {
  printf '%s\n' "${1:-RAOS_WORDPRESS_PREVIEW_REFUSED}" >&2
  exit "${2:-69}"
}

if [[ "$private_root" != "$default_private_root" ]]; then
  [[ "$private_root" =~ ^/tmp/raos-wordpress-preview-test\.[A-Za-z0-9]{1,64}$ ]] \
    || fail RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT_INVALID
fi
[[ -f "$compose_file" && ! -L "$compose_file" ]] \
  || fail RAOS_WORDPRESS_PREVIEW_COMPOSE_INVALID
[[ "$(git -C "$repository_root" rev-parse --show-toplevel 2>/dev/null)" == "$repository_root" ]] \
  || fail RAOS_WORDPRESS_PREVIEW_REPOSITORY_INVALID

random_hex() {
  local value
  value="$(od -An -N 32 -tx1 /dev/urandom | tr -d ' \n')"
  [[ "$value" =~ ^[0-9a-f]{64}$ ]] || fail RAOS_WORDPRESS_PREVIEW_RANDOM_INVALID
  printf '%s' "$value"
}

ensure_credentials() {
  if [[ ! -e "$private_root" ]]; then
    mkdir -m 0700 -p -- "$private_root"
  fi
  [[ -d "$private_root" && ! -L "$private_root" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT_INVALID
  chmod 0700 -- "$private_root"

  if [[ ! -e "$credentials_file" ]]; then
    local database_password database_root_password admin_password temporary
    database_password="$(random_hex)"
    database_root_password="$(random_hex)"
    admin_password="$(random_hex)"
    temporary="$private_root/.credentials.env.$$"
    umask 0077
    {
      printf 'RAOS_WORDPRESS_PREVIEW_DATABASE_PASSWORD=%s\n' "$database_password"
      printf 'RAOS_WORDPRESS_PREVIEW_DATABASE_ROOT_PASSWORD=%s\n' "$database_root_password"
      printf 'RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD=%s\n' "$admin_password"
    } >"$temporary"
    chmod 0600 -- "$temporary"
    mv -n -- "$temporary" "$credentials_file" \
      || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_CREATE_FAILED
  fi
  [[ -f "$credentials_file" && ! -L "$credentials_file" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID
  [[ "$(stat -c '%a' "$credentials_file")" == 600 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_MODE_INVALID
  [[ "$(stat -c '%h' "$credentials_file")" == 1 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_LINK_INVALID
}

load_credentials() {
  ensure_credentials
  local name value seen_database=false seen_root=false seen_admin=false
  while IFS='=' read -r name value; do
    [[ "$value" =~ ^[0-9a-f]{64}$ ]] \
      || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID
    case "$name" in
      RAOS_WORDPRESS_PREVIEW_DATABASE_PASSWORD)
        [[ "$seen_database" == false ]] || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID
        RAOS_WORDPRESS_PREVIEW_DATABASE_PASSWORD="$value"
        seen_database=true
        ;;
      RAOS_WORDPRESS_PREVIEW_DATABASE_ROOT_PASSWORD)
        [[ "$seen_root" == false ]] || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID
        RAOS_WORDPRESS_PREVIEW_DATABASE_ROOT_PASSWORD="$value"
        seen_root=true
        ;;
      RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD)
        [[ "$seen_admin" == false ]] || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID
        RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD="$value"
        seen_admin=true
        ;;
      *) fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID ;;
    esac
  done <"$credentials_file"
  [[ "$seen_database" == true && "$seen_root" == true && "$seen_admin" == true ]] \
    || fail RAOS_WORDPRESS_PREVIEW_CREDENTIAL_INVALID
  readonly RAOS_WORDPRESS_PREVIEW_DATABASE_PASSWORD
  readonly RAOS_WORDPRESS_PREVIEW_DATABASE_ROOT_PASSWORD
  readonly RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD
}

require_docker() {
  command -v "$docker_bin" >/dev/null 2>&1 \
    || fail RAOS_WORDPRESS_PREVIEW_DOCKER_UNAVAILABLE
  "$docker_bin" compose version >/dev/null 2>&1 \
    || fail RAOS_WORDPRESS_PREVIEW_COMPOSE_UNAVAILABLE
}

compose() {
  RAOS_REPOSITORY_ROOT="$repository_root" \
  RAOS_WORDPRESS_PREVIEW_ORIGIN="$preview_origin" \
  RAOS_WORDPRESS_PREVIEW_PORT="$preview_port" \
  RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_ROOT="$materialized_fixture_root/articles" \
  RAOS_WORDPRESS_PREVIEW_POST_FIXTURE="$materialized_fixture_root/posts.json" \
  RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_ROOT="$product_media_root" \
  RAOS_WORDPRESS_PREVIEW_YOAST_ROOT="$yoast_root" \
  "$docker_bin" compose \
    --project-directory "$slice_directory" \
    --project-name "$project_name" \
    --env-file "$credentials_file" \
    --file "$compose_file" \
    "$@"
}

validate_locked_download() {
  local path="$1" expected_bytes="$2" expected_sha256="$3"
  [[ -f "$path" && ! -L "$path" && "$(stat -c '%h' "$path")" == 1 ]] \
    || return 1
  [[ "$(wc -c <"$path" | tr -d '[:space:]')" == "$expected_bytes" ]] \
    || return 1
  [[ "$(sha256sum "$path" | cut -d ' ' -f 1)" == "$expected_sha256" ]]
}

download_locked_file() {
  local url="$1" path="$2" expected_bytes="$3" expected_sha256="$4" temporary
  if [[ -e "$path" ]]; then
    validate_locked_download "$path" "$expected_bytes" "$expected_sha256" \
      || fail RAOS_WORDPRESS_PREVIEW_YOAST_DOWNLOAD_INVALID
    return 0
  fi
  command -v "$curl_bin" >/dev/null 2>&1 \
    || fail RAOS_WORDPRESS_PREVIEW_CURL_UNAVAILABLE
  mkdir -m 0700 -p -- "$download_cache_root"
  [[ -d "$download_cache_root" && ! -L "$download_cache_root" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_DOWNLOAD_INVALID
  chmod 0700 -- "$download_cache_root"
  temporary="$(mktemp "$download_cache_root/.download.XXXXXX")" \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_DOWNLOAD_INVALID
  chmod 0600 -- "$temporary"
  if ! "$curl_bin" --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 --output "$temporary" "$url"; then
    unlink -- "$temporary" 2>/dev/null || true
    fail RAOS_WORDPRESS_PREVIEW_YOAST_DOWNLOAD_FAILED
  fi
  if ! validate_locked_download "$temporary" "$expected_bytes" "$expected_sha256"; then
    unlink -- "$temporary" 2>/dev/null || true
    fail RAOS_WORDPRESS_PREVIEW_YOAST_DOWNLOAD_INVALID
  fi
  if ! mv -n -- "$temporary" "$path"; then
    unlink -- "$temporary" 2>/dev/null || true
    validate_locked_download "$path" "$expected_bytes" "$expected_sha256" \
      || fail RAOS_WORDPRESS_PREVIEW_YOAST_DOWNLOAD_INVALID
  fi
}

ensure_yoast_runtime() {
  if [[ -n "$test_yoast_materializer_bin" ]]; then
    [[ "$private_root" != "$default_private_root" \
      && -f "$test_yoast_materializer_bin" \
      && -x "$test_yoast_materializer_bin" \
      && ! -L "$test_yoast_materializer_bin" ]] \
      || fail RAOS_WORDPRESS_PREVIEW_YOAST_MATERIALIZER_UNAVAILABLE
    "$test_yoast_materializer_bin" "$private_root" \
      || fail RAOS_WORDPRESS_PREVIEW_YOAST_MATERIALIZATION_FAILED
    [[ -d "$yoast_root" && ! -L "$yoast_root" \
      && -f "$yoast_root/wp-seo.php" && ! -L "$yoast_root/wp-seo.php" ]] \
      || fail RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID
    return 0
  fi
  [[ -x "$python_bin" && -f "$yoast_materializer" && ! -L "$yoast_materializer" \
    && -f "$yoast_lock" && ! -L "$yoast_lock" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_MATERIALIZER_UNAVAILABLE
  download_locked_file \
    "$yoast_archive_url" "$yoast_archive" \
    "$yoast_archive_bytes" "$yoast_archive_sha256"
  download_locked_file \
    "$yoast_checksums_url" "$yoast_checksums" \
    "$yoast_checksums_bytes" "$yoast_checksums_sha256"
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$yoast_materializer" \
    --archive "$yoast_archive" \
    --checksums "$yoast_checksums" \
    --lock "$yoast_lock" \
    --output-parent "$plugin_cache_root" >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_MATERIALIZATION_FAILED
  [[ -d "$yoast_root" && ! -L "$yoast_root" \
    && -f "$yoast_root/wp-seo.php" && ! -L "$yoast_root/wp-seo.php" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID
}

refuse_foreign_port_owner() {
  local owners container_id project extra
  owners="$(
    "$docker_bin" ps \
      --filter "publish=$preview_port" \
      --format '{{.ID}} {{.Label "com.docker.compose.project"}}'
  )" || fail RAOS_WORDPRESS_PREVIEW_PORT_INSPECTION_FAILED
  while read -r container_id project extra; do
    [[ -z "$container_id" ]] && continue
    [[ -z "$extra" && "$project" == "$project_name" ]] \
      || fail RAOS_WORDPRESS_PREVIEW_FOREIGN_PORT_OWNER
  done <<<"$owners"
}

validate_materialized_runtime() {
  [[ -d "$materialized_fixture_root" && ! -L "$materialized_fixture_root" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_MATERIALIZED_FIXTURE_INVALID
  [[ -d "$materialized_fixture_root/articles" && ! -L "$materialized_fixture_root/articles" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_MATERIALIZED_FIXTURE_INVALID
  [[ -f "$materialized_fixture_root/posts.json" && ! -L "$materialized_fixture_root/posts.json" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_MATERIALIZED_FIXTURE_INVALID
  [[ -d "$product_media_root" && ! -L "$product_media_root" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_INVALID
  [[ -d "$yoast_root" && ! -L "$yoast_root" \
    && -f "$yoast_root/wp-seo.php" && ! -L "$yoast_root/wp-seo.php" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_RUNTIME_INVALID

  local article_count
  article_count="$(find "$materialized_fixture_root/articles" \
    -mindepth 1 -maxdepth 1 -type f -name '*.html' -printf '.' | wc -c | tr -d '[:space:]')"
  [[ "$article_count" == 10 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_MATERIALIZED_FIXTURE_INVALID
}

validate_owner_private_fixture_override() {
  [[ "$fixture_override_enabled" == true \
    && "$materialized_fixture_root" == /* \
    && "$materialized_fixture_root" != *$'\n'* \
    && "$materialized_fixture_root" != *$'\r'* ]] \
    || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID

  local resolved current_uid path entry_count html_count
  resolved="$(realpath -e -- "$materialized_fixture_root" 2>/dev/null)" \
    || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID
  [[ "$resolved" == "$materialized_fixture_root" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID
  current_uid="$(id -u)"
  for path in "$materialized_fixture_root" "$materialized_fixture_root/articles"; do
    [[ -d "$path" && ! -L "$path" \
      && "$(stat -c '%u' "$path")" == "$current_uid" \
      && "$(stat -c '%a' "$path")" == 700 ]] \
      || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID
  done
  path="$materialized_fixture_root/posts.json"
  [[ -f "$path" && ! -L "$path" \
    && "$(stat -c '%u' "$path")" == "$current_uid" \
    && "$(stat -c '%a' "$path")" == 600 \
    && "$(stat -c '%h' "$path")" == 1 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID

  entry_count="$(find "$materialized_fixture_root/articles" \
    -mindepth 1 -maxdepth 1 -printf '.' | wc -c | tr -d '[:space:]')"
  html_count=0
  while IFS= read -r -d '' path; do
    [[ "${path##*/}" =~ ^[a-z0-9]+(-[a-z0-9]+)*\.html$ \
      && -f "$path" && ! -L "$path" \
      && "$(stat -c '%u' "$path")" == "$current_uid" \
      && "$(stat -c '%a' "$path")" == 600 \
      && "$(stat -c '%h' "$path")" == 1 ]] \
      || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID
    html_count=$((html_count + 1))
  done < <(
    find "$materialized_fixture_root/articles" \
      -mindepth 1 -maxdepth 1 -print0
  )
  [[ "$entry_count" == 10 && "$html_count" == 10 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID
}

materialize_runtime() {
  ensure_yoast_runtime
  if [[ "$fixture_override_enabled" == true ]]; then
    validate_owner_private_fixture_override
    validate_materialized_runtime
    return 0
  fi
  if [[ -n "$test_materializer_bin" ]]; then
    [[ "$private_root" != "$default_private_root" \
      && -x "$test_materializer_bin" && -f "$test_materializer_bin" \
      && ! -L "$test_materializer_bin" ]] \
      || fail RAOS_WORDPRESS_PREVIEW_TEST_MATERIALIZER_INVALID
    "$test_materializer_bin" "$private_root"
    validate_materialized_runtime
    return 0
  fi
  [[ -x "$python_bin" && -f "$materializer_script" && ! -L "$materializer_script" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_MATERIALIZER_UNAVAILABLE
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$materializer_script" \
    materialize-local --output-root "$private_root"
  validate_materialized_runtime
}

wordpress_cli() {
  compose run --rm --no-deps -T cli "$@"
}

wordpress_cli_tty() {
  compose run --rm --no-deps cli "$@"
}

wait_until_ready() {
  command -v "$curl_bin" >/dev/null 2>&1 \
    || fail RAOS_WORDPRESS_PREVIEW_CURL_UNAVAILABLE
  local attempt
  for attempt in $(seq 1 90); do
    if "$curl_bin" \
      --fail \
      --silent \
      --show-error \
      --output /dev/null \
      "$preview_origin/wp-login.php" 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  fail RAOS_WORDPRESS_PREVIEW_BOOT_TIMEOUT
}

install_wordpress_if_needed() {
  if wordpress_cli core is-installed >/dev/null 2>&1; then
    return 0
  fi
  printf '%s\n' "$RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD" | wordpress_cli core install \
    --url="$preview_origin" \
    --title='暮らしのしるべ — ローカルプレビュー' \
    --admin_user=raos-local-admin \
    --admin_email=local-preview@example.invalid \
    --skip-email \
    --prompt=admin_password >/dev/null
}

activate_theme() {
  wordpress_cli theme is-installed twentytwentyfive >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_PARENT_THEME_MISSING
  wordpress_cli theme is-installed kurashinoshirube-child >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_CHILD_THEME_MISSING
  wordpress_cli theme activate kurashinoshirube-child >/dev/null
}

activate_measurement_plugin() {
  if [[ "$link_mode" == standard-api ]]; then
    if wordpress_cli plugin is-active raos-editorial-measurement >/dev/null; then
      wordpress_cli plugin deactivate raos-editorial-measurement >/dev/null
    fi
    return 0
  fi
  wordpress_cli plugin is-installed raos-editorial-measurement >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_MEASUREMENT_PLUGIN_MISSING
  wordpress_cli plugin activate raos-editorial-measurement >/dev/null
}

activate_yoast_plugin() {
  wordpress_cli plugin is-installed wordpress-seo >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_PLUGIN_MISSING
  [[ "$(wordpress_cli plugin get wordpress-seo --field=version)" == 28.3 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_VERSION_INVALID
  wordpress_cli plugin activate wordpress-seo >/dev/null
}

seed() {
  local mode="$1"
  compose run --rm --no-deps -T \
    --env "RAOS_PREVIEW_SEED_MODE=$mode" \
    cli eval-file /var/www/raos-local-preview/seed.php
  wordpress_cli rewrite flush >/dev/null
}

do_up() {
  require_docker
  refuse_foreign_port_owner
  load_credentials
  materialize_runtime
  compose up --detach database wordpress gateway
  wait_until_ready
  install_wordpress_if_needed
  activate_theme
  activate_measurement_plugin
  activate_yoast_plugin
  seed initialize
  printf 'WordPress preview: %s/\n' "$preview_origin"
  printf 'Article preview: %s%s\n' "$preview_origin" "$preview_article_path"
  printf '%s\n' 'Admin user: raos-local-admin (set a password with make wordpress-preview-password)'
}

do_status() {
  require_docker
  if [[ ! -f "$credentials_file" ]]; then
    printf '%s\n' RAOS_WORDPRESS_PREVIEW_NOT_INITIALIZED
    return 0
  fi
  load_credentials
  validate_materialized_runtime
  compose ps
  wordpress_cli core is-installed >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_WORDPRESS_NOT_INSTALLED
  [[ "$(wordpress_cli option get home)" == "$preview_origin" ]] \
    || fail RAOS_WORDPRESS_PREVIEW_ORIGIN_INVALID
  [[ "$(wordpress_cli theme list --name=kurashinoshirube-child --field=status)" == active ]] \
    || fail RAOS_WORDPRESS_PREVIEW_THEME_INACTIVE
  if [[ "$link_mode" == measured-admin ]]; then
    [[ "$(wordpress_cli plugin list --name=raos-editorial-measurement --field=status)" == active ]] \
      || fail RAOS_WORDPRESS_PREVIEW_MEASUREMENT_PLUGIN_INACTIVE
  elif wordpress_cli plugin is-active raos-editorial-measurement >/dev/null; then
    fail RAOS_WORDPRESS_PREVIEW_MEASUREMENT_PLUGIN_ACTIVE
  fi
  [[ "$(wordpress_cli plugin list --name=wordpress-seo --field=status)" == active ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_PLUGIN_INACTIVE
  [[ "$(wordpress_cli plugin get wordpress-seo --field=version)" == 28.3 ]] \
    || fail RAOS_WORDPRESS_PREVIEW_YOAST_VERSION_INVALID
  wordpress_cli eval \
    'exit(function_exists("kurashinoshirube_yoast_configuration_is_exact") && kurashinoshirube_yoast_configuration_is_exact() ? 0 : 1);' \
    >/dev/null || fail RAOS_WORDPRESS_PREVIEW_YOAST_CONFIGURATION_INVALID
  printf '%s\n' RAOS_WORDPRESS_PREVIEW_READY
}

do_sync() {
  require_docker
  load_credentials
  materialize_runtime
  wordpress_cli core is-installed >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_WORDPRESS_NOT_INSTALLED
  activate_theme
  activate_measurement_plugin
  activate_yoast_plugin
  seed sync
}

do_password() {
  require_docker
  load_credentials
  [[ -t 0 && -t 1 ]] || fail RAOS_WORDPRESS_PREVIEW_PASSWORD_REQUIRES_TTY
  wordpress_cli core is-installed >/dev/null \
    || fail RAOS_WORDPRESS_PREVIEW_WORDPRESS_NOT_INSTALLED
  wordpress_cli_tty user update raos-local-admin --prompt=user_pass >/dev/null
  printf '%s\n' RAOS_WORDPRESS_PREVIEW_PASSWORD_UPDATED
}

do_check() {
  [[ -f "$credentials_file" ]] || fail RAOS_WORDPRESS_PREVIEW_NOT_INITIALIZED
  do_status >/dev/null
  RAOS_WORDPRESS_PREVIEW_ORIGIN="$preview_origin" \
    "$slice_directory/browser/check.sh"
}

do_down() {
  require_docker
  if [[ ! -f "$credentials_file" ]]; then
    printf '%s\n' RAOS_WORDPRESS_PREVIEW_ALREADY_DOWN
    return 0
  fi
  load_credentials
  compose down --remove-orphans
  printf '%s\n' RAOS_WORDPRESS_PREVIEW_STOPPED_DATA_PRESERVED
}

do_reset() {
  [[ "${CONFIRM:-}" == YES ]] || fail RAOS_WORDPRESS_PREVIEW_RESET_CONFIRMATION_REQUIRED
  require_docker
  ensure_credentials
  compose down --volumes --remove-orphans
  do_up
}

case "${1:-}" in
  up) do_up ;;
  status) do_status ;;
  sync) do_sync ;;
  password) do_password ;;
  check) do_check ;;
  down) do_down ;;
  reset) do_reset ;;
  *)
    printf '%s\n' 'usage: wordpress_preview.sh {up|status|sync|password|check|down|reset}' >&2
    exit 64
    ;;
esac
