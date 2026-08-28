#!/usr/bin/env bash

# Disposable WordPress 7.1 MCP integration test. It never contacts the live site.
set -euo pipefail

readonly repository_root=/home/minami/rakuten
readonly e2e_directory="$repository_root/tests/wordpress_mcp_v1/e2e"
readonly compose_file="$e2e_directory/compose.yaml"
readonly adapter_url=https://github.com/WordPress/mcp-adapter/releases/download/v0.6.1/mcp-adapter.zip
readonly adapter_sha256=1c3cd47c32e99b4e7d8690a44a7890256e92a8b96f61776cbe1894e5483cf676
readonly editor_user=raos-e2e-editor
readonly operator_user=raos-e2e-operator
readonly project_name="raoswpe2e$$"

fail() {
  printf '%s\n' "${1:-RAOS_WORDPRESS_E2E_REFUSED}" >&2
  exit 1
}

[[ "$PWD" == "$repository_root" ]] || fail RAOS_WORDPRESS_E2E_WRONG_DIRECTORY
command -v docker >/dev/null 2>&1 || fail RAOS_WORDPRESS_E2E_DOCKER_UNAVAILABLE
command -v curl >/dev/null 2>&1 || fail RAOS_WORDPRESS_E2E_CURL_UNAVAILABLE
docker compose version >/dev/null 2>&1 || fail RAOS_WORDPRESS_E2E_COMPOSE_UNAVAILABLE

e2e_temporary_directory="$(mktemp -d /tmp/raos-wordpress-e2e.XXXXXX)"
case "$e2e_temporary_directory" in
  /tmp/raos-wordpress-e2e.*) ;;
  *) fail RAOS_WORDPRESS_E2E_TEMPORARY_DIRECTORY_INVALID ;;
esac
readonly e2e_temporary_directory
readonly adapter_zip="$e2e_temporary_directory/mcp-adapter.zip"
readonly state_path="$e2e_temporary_directory/state.json"
readonly code_artifact_directory="$e2e_temporary_directory/code-artifacts"
RAOS_WORDPRESS_E2E_DATA_DIR="$e2e_temporary_directory/data"
readonly RAOS_WORDPRESS_E2E_DATA_DIR
install -d -m 0755 "$RAOS_WORDPRESS_E2E_DATA_DIR/html"
install -d -m 0700 "$RAOS_WORDPRESS_E2E_DATA_DIR/private"
install -d -m 0700 "$RAOS_WORDPRESS_E2E_DATA_DIR/staging"
export RAOS_WORDPRESS_E2E_DATA_DIR

mapfile -t generated_passwords < <(
  "$repository_root/.venv/bin/python" - <<'PY'
import secrets

for _ in range(5):
    print(secrets.token_urlsafe(48))
PY
)
[[ "${#generated_passwords[@]}" == 5 ]] || fail RAOS_WORDPRESS_E2E_PASSWORD_GENERATION_FAILED
RAOS_WORDPRESS_E2E_ADMIN_PASSWORD="${generated_passwords[0]}"
RAOS_WORDPRESS_E2E_DATABASE_PASSWORD="${generated_passwords[1]}"
RAOS_WORDPRESS_E2E_DATABASE_ROOT_PASSWORD="${generated_passwords[2]}"
readonly RAOS_WORDPRESS_E2E_ADMIN_PASSWORD
readonly RAOS_WORDPRESS_E2E_DATABASE_PASSWORD
readonly RAOS_WORDPRESS_E2E_DATABASE_ROOT_PASSWORD
readonly editor_login_password="${generated_passwords[3]}"
readonly operator_login_password="${generated_passwords[4]}"
unset generated_passwords
export \
  RAOS_WORDPRESS_E2E_ADMIN_PASSWORD \
  RAOS_WORDPRESS_E2E_DATABASE_PASSWORD \
  RAOS_WORDPRESS_E2E_DATABASE_ROOT_PASSWORD

RAOS_WORDPRESS_E2E_PORT="$(
  "$repository_root/.venv/bin/python" - <<'PY'
import socket

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"
export RAOS_WORDPRESS_E2E_PORT

compose() {
  docker compose \
    --project-directory "$e2e_directory" \
    --project-name "$project_name" \
    --file "$compose_file" \
    "$@"
}

wordpress_cli() {
  compose run --rm --no-deps -T \
    --env RAOS_WORDPRESS_E2E_ADMIN_PASSWORD \
    cli "$@"
}

cleanup() {
  compose exec -T --user root wordpress chown -R \
    "$(id -u):$(id -g)" \
    /var/www/html \
    /var/www/raos-codex-private \
    /var/www/raos-e2e-staging >/dev/null 2>&1 || true
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  if [[ "$e2e_temporary_directory" == /tmp/raos-wordpress-e2e.* ]]; then
    rm -rf -- "$e2e_temporary_directory"
  fi
}
trap cleanup EXIT HUP INT TERM

if [[ -n "${RAOS_MCP_ADAPTER_ZIP:-}" ]]; then
  [[ "$RAOS_MCP_ADAPTER_ZIP" == /* ]] || fail RAOS_WORDPRESS_E2E_ADAPTER_PATH_INVALID
  [[ -f "$RAOS_MCP_ADAPTER_ZIP" && ! -L "$RAOS_MCP_ADAPTER_ZIP" ]] \
    || fail RAOS_WORDPRESS_E2E_ADAPTER_PATH_INVALID
  install -m 0600 -- "$RAOS_MCP_ADAPTER_ZIP" "$adapter_zip"
else
  curl \
    --proto '=https' \
    --tlsv1.2 \
    --fail \
    --location \
    --silent \
    --show-error \
    --output "$adapter_zip" \
    "$adapter_url"
  chmod 0600 "$adapter_zip"
fi

actual_adapter_sha256="$(sha256sum "$adapter_zip" | awk '{print $1}')"
[[ "$actual_adapter_sha256" == "$adapter_sha256" ]] \
  || fail RAOS_WORDPRESS_E2E_ADAPTER_DIGEST_MISMATCH

"$repository_root/.venv/bin/python" \
  "$repository_root/scripts/build_wordpress_mcp_v1.py" --package
readonly raos_plugin_zip="$repository_root/.secrets/wordpress-mcp/plugin/raos-codex-mcp-abilities-1.0.2.zip"
"$repository_root/.venv/bin/python" \
  "$repository_root/scripts/build_wordpress_mcp_v1.py" --package-check

RAOS_WORDPRESS_E2E_ARTIFACTS="$code_artifact_directory/artifacts.json"
"$repository_root/.venv/bin/python" \
  "$e2e_directory/prepare_packages.py" "$code_artifact_directory" >/dev/null
mapfile -t code_package_hashes < <(
  "$repository_root/.venv/bin/python" -c \
    'import json,sys; value=json.load(open(sys.argv[1], encoding="ascii")); print(value["plugin_success"]["code_package"]["package_sha256"]); print(value["plugin_rollback"]["code_package"]["package_sha256"])' \
    "$RAOS_WORDPRESS_E2E_ARTIFACTS"
)
[[ "${#code_package_hashes[@]}" == 2 ]] || fail RAOS_WORDPRESS_E2E_ARTIFACT_INVALID
RAOS_WORDPRESS_E2E_SAFE_PLUGIN_SHA256="${code_package_hashes[0]}"
RAOS_WORDPRESS_E2E_BROKEN_PLUGIN_SHA256="${code_package_hashes[1]}"
readonly RAOS_WORDPRESS_E2E_ARTIFACTS
readonly RAOS_WORDPRESS_E2E_SAFE_PLUGIN_SHA256
readonly RAOS_WORDPRESS_E2E_BROKEN_PLUGIN_SHA256
unset code_package_hashes
export \
  RAOS_WORDPRESS_E2E_ARTIFACTS \
  RAOS_WORDPRESS_E2E_BROKEN_PLUGIN_SHA256 \
  RAOS_WORDPRESS_E2E_SAFE_PLUGIN_SHA256

compose up --detach database wordpress

wordpress_ready=false
for _attempt in $(seq 1 90); do
  if curl \
    --silent \
    --show-error \
    --fail \
    --header 'Host: kurashinoshirube.com' \
    "http://127.0.0.1:$RAOS_WORDPRESS_E2E_PORT/wp-login.php" \
    --output /dev/null 2>/dev/null; then
    wordpress_ready=true
    break
  fi
  sleep 2
done
[[ "$wordpress_ready" == true ]] || fail RAOS_WORDPRESS_E2E_BOOT_TIMEOUT

compose exec -T --user root wordpress sh -eu -c \
  'chown www-data:www-data /var/www/raos-codex-private /var/www/raos-e2e-staging; chmod 0700 /var/www/raos-codex-private /var/www/raos-e2e-staging'
compose cp "$adapter_zip" wordpress:/var/www/raos-e2e-staging/mcp-adapter.zip
compose cp "$raos_plugin_zip" wordpress:/var/www/raos-e2e-staging/raos-codex-mcp-abilities.zip
compose cp "$e2e_directory/approve_harness.php" wordpress:/var/www/raos-e2e-staging/approve_harness.php
compose cp "$e2e_directory/mutate_harness.php" wordpress:/var/www/raos-e2e-staging/mutate_harness.php
compose cp "$code_artifact_directory/kurashinoshirube-child-baseline.zip" wordpress:/var/www/raos-e2e-staging/kurashinoshirube-child-baseline.zip
compose exec -T --user root wordpress chown -R www-data:www-data /var/www/raos-e2e-staging

printf '%s\n' "$RAOS_WORDPRESS_E2E_ADMIN_PASSWORD" | wordpress_cli core install \
  --url=https://kurashinoshirube.com \
  --title='RAOS WordPress MCP E2E' \
  --admin_user=raos-e2e-approver \
  --admin_email=approver@example.invalid \
  --skip-email \
  --prompt=admin_password

wordpress_cli plugin install /var/www/raos-e2e-staging/mcp-adapter.zip --activate
wordpress_cli plugin install /var/www/raos-e2e-staging/raos-codex-mcp-abilities.zip --activate
wordpress_cli theme is-installed twentytwentyfive \
  || fail RAOS_WORDPRESS_E2E_PARENT_THEME_MISSING
wordpress_cli theme install \
  /var/www/raos-e2e-staging/kurashinoshirube-child-baseline.zip --activate
[[ "$(wordpress_cli core version)" == 7.1.0 ]] \
  || fail RAOS_WORDPRESS_E2E_WORDPRESS_VERSION_INVALID
[[ "$(wordpress_cli eval 'echo WP_MCP_VERSION;')" == 0.6.1 ]] \
  || fail RAOS_WORDPRESS_E2E_ADAPTER_VERSION_INVALID

printf '%s\n' "$editor_login_password" | wordpress_cli user create \
  "$editor_user" editor@example.invalid \
  --role=raos_codex_mcp_editor \
  --prompt=user_pass \
  --porcelain >/dev/null
printf '%s\n' "$operator_login_password" | wordpress_cli user create \
  "$operator_user" operator@example.invalid \
  --role=raos_codex_deployment_operator \
  --prompt=user_pass \
  --porcelain >/dev/null

RAOS_WORDPRESS_E2E_EDITOR_PASSWORD="$(
  wordpress_cli user application-password create \
    "$editor_user" 'RAOS Codex Editor MCP' --porcelain
)"
RAOS_WORDPRESS_E2E_OPERATOR_PASSWORD="$(
  wordpress_cli user application-password create \
    "$operator_user" 'RAOS Codex Deployment Bridge' --porcelain
)"
RAOS_WORDPRESS_E2E_EDITOR_USER="$editor_user"
RAOS_WORDPRESS_E2E_OPERATOR_USER="$operator_user"
export \
  RAOS_WORDPRESS_E2E_EDITOR_PASSWORD \
  RAOS_WORDPRESS_E2E_EDITOR_USER \
  RAOS_WORDPRESS_E2E_OPERATOR_PASSWORD \
  RAOS_WORDPRESS_E2E_OPERATOR_USER

"$repository_root/.venv/bin/python" "$e2e_directory/client.py" propose "$state_path"

mapfile -t release_proposals < <(
  "$repository_root/.venv/bin/python" -c \
    'import json,sys; print("\n".join(item["proposal_id"] for item in json.load(open(sys.argv[1], encoding="utf-8"))["proposals"]))' \
    "$state_path"
)
drift_proposal="$("$repository_root/.venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["drift"]["proposal_id"])' \
  "$state_path")"
drift_post_id="$("$repository_root/.venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["drift"]["post_id"])' \
  "$state_path")"
mapfile -t code_proposals < <(
  "$repository_root/.venv/bin/python" -c \
    'import json,sys; print("\n".join(item["proposal_id"] for item in json.load(open(sys.argv[1], encoding="utf-8"))["code_proposals"]))' \
    "$state_path"
)

for proposal_id in "${release_proposals[@]}"; do
  [[ "$proposal_id" =~ ^[0-9a-f]{64}$ ]] || fail RAOS_WORDPRESS_E2E_PROPOSAL_INVALID
  wordpress_cli eval-file /var/www/raos-e2e-staging/approve_harness.php "$proposal_id" >/dev/null
done
[[ "$drift_proposal" =~ ^[0-9a-f]{64}$ && "$drift_post_id" =~ ^[0-9]+$ ]] \
  || fail RAOS_WORDPRESS_E2E_DRIFT_TARGET_INVALID
wordpress_cli eval-file /var/www/raos-e2e-staging/mutate_harness.php "$drift_post_id"
wordpress_cli eval-file /var/www/raos-e2e-staging/approve_harness.php "$drift_proposal" >/dev/null
for proposal_id in "${code_proposals[@]}"; do
  [[ "$proposal_id" =~ ^[0-9a-f]{64}$ ]] || fail RAOS_WORDPRESS_E2E_CODE_PROPOSAL_INVALID
  wordpress_cli eval-file /var/www/raos-e2e-staging/approve_harness.php "$proposal_id" >/dev/null
done

"$repository_root/.venv/bin/python" "$e2e_directory/client.py" apply "$state_path"
wordpress_cli plugin is-active raos-e2e-safe-plugin/raos-e2e-safe-plugin.php \
  || fail RAOS_WORDPRESS_E2E_PLUGIN_ACTIVATION_FAILED
if wordpress_cli plugin is-installed raos-e2e-broken-plugin; then
  fail RAOS_WORDPRESS_E2E_PLUGIN_ROLLBACK_FAILED
fi
printf '%s\n' RAOS_WORDPRESS_E2E_OK
