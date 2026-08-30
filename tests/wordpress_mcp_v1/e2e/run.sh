#!/usr/bin/env bash

# Disposable WordPress 7.1 MCP integration test. It never contacts the live site.
set -euo pipefail
umask 0077

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
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
install -d -m 0755 "$RAOS_WORDPRESS_E2E_DATA_DIR"
install -d -m 0755 "$RAOS_WORDPRESS_E2E_DATA_DIR/html"
install -d -m 0755 "$RAOS_WORDPRESS_E2E_DATA_DIR/raos-code"
install -d -m 0755 "$RAOS_WORDPRESS_E2E_DATA_DIR/raos-code/wp-content"
install -d -m 0700 "$RAOS_WORDPRESS_E2E_DATA_DIR/raos-code/private"
install -d -m 0700 "$RAOS_WORDPRESS_E2E_DATA_DIR/raos-code/staging"
readonly install_log="$e2e_temporary_directory/install.log"
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

approve_proposal() {
  local approval_log="$e2e_temporary_directory/approval.log"
  if ! wordpress_cli eval-file \
    /var/www/raos-code/staging/approve_harness.php "$1" >"$approval_log" 2>&1; then
    tail -c 4096 "$approval_log" >&2 || true
    fail RAOS_WORDPRESS_E2E_APPROVAL_FAILED
  fi
}

cleanup() {
  compose exec -T --user root wordpress chown -R \
    "$(id -u):$(id -g)" \
    /var/www/html \
    /var/www/raos-code >/dev/null 2>&1 || true
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
readonly raos_plugin_zip="$repository_root/.secrets/wordpress-mcp/plugin/raos-codex-mcp-abilities-1.3.1.zip"
"$repository_root/.venv/bin/python" \
  "$repository_root/scripts/build_wordpress_mcp_v1.py" --package-check
"$repository_root/.venv/bin/python" \
  "$repository_root/scripts/build_editorial_measurement_v1.py" --package
readonly measurement_plugin_zip="$repository_root/.secrets/wordpress-mcp/repo-plugin-artifacts/raos-editorial-measurement-v1.zip"

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

compose up --detach database wordpress gateway

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
  'cp -a /usr/src/wordpress/wp-content/. /var/www/raos-code/wp-content/; chown -R www-data:www-data /var/www/raos-code; chmod 0700 /var/www/raos-code/private /var/www/raos-code/staging'
compose cp "$adapter_zip" wordpress:/var/www/raos-code/staging/mcp-adapter.zip
compose cp "$raos_plugin_zip" wordpress:/var/www/raos-code/staging/raos-codex-mcp-abilities.zip
compose cp "$measurement_plugin_zip" wordpress:/var/www/raos-code/staging/raos-editorial-measurement.zip
compose cp "$e2e_directory/approve_harness.php" wordpress:/var/www/raos-code/staging/approve_harness.php
compose cp "$e2e_directory/batch_approve_harness.php" wordpress:/var/www/raos-code/staging/batch_approve_harness.php
compose cp "$e2e_directory/idempotency_harness.php" wordpress:/var/www/raos-code/staging/idempotency_harness.php
compose cp "$e2e_directory/mutate_harness.php" wordpress:/var/www/raos-code/staging/mutate_harness.php
compose cp "$e2e_directory/rollback_harness.php" wordpress:/var/www/raos-code/staging/rollback_harness.php
compose cp "$e2e_directory/store_upgrade_harness.php" wordpress:/var/www/raos-code/staging/store_upgrade_harness.php
compose cp "$code_artifact_directory/kurashinoshirube-child-baseline.zip" wordpress:/var/www/raos-code/staging/kurashinoshirube-child-baseline.zip
compose exec -T --user root wordpress chown -R www-data:www-data /var/www/raos-code/staging

if ! printf '%s\n' "$RAOS_WORDPRESS_E2E_ADMIN_PASSWORD" | wordpress_cli core install \
  --url=https://kurashinoshirube.com \
  --title='RAOS WordPress MCP E2E' \
  --admin_user=raos-e2e-approver \
  --admin_email=approver@example.invalid \
  --skip-email \
  --prompt=admin_password >"$install_log" 2>&1; then
  sed -E 's/[[:alnum:]_-]{32,}/[REDACTED]/g' "$install_log" | tail -n 8 >&2
  fail RAOS_WORDPRESS_E2E_INSTALL_FAILED
fi

wordpress_cli config set WP_CONTENT_DIR /var/www/raos-code/wp-content \
  --type=constant >/dev/null
wordpress_cli config set WP_CONTENT_URL https://kurashinoshirube.com/wp-content \
  --type=constant >/dev/null

wordpress_cli plugin install /var/www/raos-code/staging/mcp-adapter.zip --activate
wordpress_cli plugin install /var/www/raos-code/staging/raos-codex-mcp-abilities.zip --activate
wordpress_cli plugin install /var/www/raos-code/staging/raos-editorial-measurement.zip --activate
wordpress_cli rewrite structure '/%postname%/' --hard >/dev/null 2>&1 \
  || fail RAOS_WORDPRESS_E2E_REWRITE_FAILED
wordpress_cli theme is-installed twentytwentyfive \
  || fail RAOS_WORDPRESS_E2E_PARENT_THEME_MISSING
wordpress_cli theme install \
  /var/www/raos-code/staging/kurashinoshirube-child-baseline.zip --activate
[[ "$(wordpress_cli core version)" == 7.1 ]] \
  || fail RAOS_WORDPRESS_E2E_WORDPRESS_VERSION_INVALID
[[ "$(wordpress_cli eval 'echo WP_MCP_VERSION;')" == 0.6.1 ]] \
  || fail RAOS_WORDPRESS_E2E_ADAPTER_VERSION_INVALID
actual_plugin_directory="$(wordpress_cli eval 'echo WP_PLUGIN_DIR;')"
if [[ "$actual_plugin_directory" != /var/www/raos-code/wp-content/plugins ]]; then
  printf 'RAOS_WORDPRESS_E2E_PLUGIN_DIRECTORY=%s\n' "$actual_plugin_directory" >&2
  fail RAOS_WORDPRESS_E2E_PLUGIN_DIRECTORY_INVALID
fi
wordpress_cli plugin is-active mcp-adapter \
  || fail RAOS_WORDPRESS_E2E_ADAPTER_INACTIVE
wordpress_cli plugin is-active raos-codex-mcp-abilities \
  || fail RAOS_WORDPRESS_E2E_PLUGIN_INACTIVE
wordpress_cli plugin is-active raos-editorial-measurement \
  || fail RAOS_WORDPRESS_E2E_MEASUREMENT_PLUGIN_INACTIVE
wordpress_cli eval-file /var/www/raos-code/staging/store_upgrade_harness.php degrade \
  || fail RAOS_WORDPRESS_E2E_STORE_DEGRADE_FAILED
wordpress_cli eval-file /var/www/raos-code/staging/store_upgrade_harness.php check \
  || fail RAOS_WORDPRESS_E2E_STORE_UPGRADE_FAILED
wordpress_cli eval-file /var/www/raos-code/staging/store_upgrade_harness.php degrade-v3 \
  || fail RAOS_WORDPRESS_E2E_STORE_V3_DEGRADE_FAILED
wordpress_cli eval-file /var/www/raos-code/staging/store_upgrade_harness.php check \
  || fail RAOS_WORDPRESS_E2E_STORE_V3_UPGRADE_FAILED
wordpress_cli eval-file /var/www/raos-code/staging/rollback_harness.php \
  || fail RAOS_WORDPRESS_E2E_ROLLBACK_FAILED
[[ "$(wordpress_cli eval 'rest_get_server(); echo isset(rest_get_server()->get_routes()["/raos-codex-mcp/v1/editor"]) ? "yes" : "no";')" == yes ]] \
  || fail RAOS_WORDPRESS_E2E_EDITOR_ROUTE_MISSING

if ! printf '%s\n' "$editor_login_password" | wordpress_cli user create \
  "$editor_user" editor@example.invalid \
  --role=raos_codex_mcp_editor \
  --prompt=user_pass \
  --porcelain >/dev/null 2>&1; then
  fail RAOS_WORDPRESS_E2E_EDITOR_CREATE_FAILED
fi
if ! printf '%s\n' "$operator_login_password" | wordpress_cli user create \
  "$operator_user" operator@example.invalid \
  --role=raos_codex_deployment_operator \
  --prompt=user_pass \
  --porcelain >/dev/null 2>&1; then
  fail RAOS_WORDPRESS_E2E_OPERATOR_CREATE_FAILED
fi

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
wordpress_cli eval-file /var/www/raos-code/staging/idempotency_harness.php \
  || fail RAOS_WORDPRESS_E2E_IDEMPOTENCY_FAILED

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
mapfile -t plugin_proposals < <(
  "$repository_root/.venv/bin/python" -c \
    'import json,sys; print("\n".join(item["proposal_id"] for item in json.load(open(sys.argv[1], encoding="utf-8"))["code_proposals"] if item["name"] != "theme"))' \
    "$state_path"
)

for proposal_id in "${release_proposals[@]}"; do
  [[ "$proposal_id" =~ ^[0-9a-f]{64}$ ]] || fail RAOS_WORDPRESS_E2E_PROPOSAL_INVALID
done
[[ "$drift_proposal" =~ ^[0-9a-f]{64}$ && "$drift_post_id" =~ ^[0-9]+$ ]] \
  || fail RAOS_WORDPRESS_E2E_DRIFT_TARGET_INVALID
for proposal_id in "${code_proposals[@]}"; do
  [[ "$proposal_id" =~ ^[0-9a-f]{64}$ ]] || fail RAOS_WORDPRESS_E2E_CODE_PROPOSAL_INVALID
done

wordpress_cli eval-file \
  /var/www/raos-code/staging/batch_approve_harness.php expect-rollback \
  || fail RAOS_WORDPRESS_E2E_BATCH_APPROVAL_ROLLBACK_FAILED
if ! wordpress_cli eval-file \
  /var/www/raos-code/staging/batch_approve_harness.php approve \
  >"$e2e_temporary_directory/batch-approval.log" 2>&1; then
  tail -c 4096 "$e2e_temporary_directory/batch-approval.log" >&2 || true
  fail RAOS_WORDPRESS_E2E_BATCH_APPROVAL_FAILED
fi
wordpress_cli eval-file \
  /var/www/raos-code/staging/batch_approve_harness.php claim-ambiguous-reset \
  || fail RAOS_WORDPRESS_E2E_BATCH_CLAIM_FAILED
wordpress_cli eval-file \
  /var/www/raos-code/staging/batch_approve_harness.php plugin-ambiguous-reset \
  || fail RAOS_WORDPRESS_E2E_PLUGIN_APPROVAL_CRASH_CONSISTENCY_FAILED

for proposal_id in "${plugin_proposals[@]}"; do
  approval_lease="/var/www/raos-code/private/approval-lease-$proposal_id.json"
  if compose exec -T wordpress test -e "$approval_lease"; then
    fail RAOS_WORDPRESS_E2E_PUBLICATION_BATCH_APPROVED_PLUGIN
  fi
  approve_proposal "$proposal_id"
done
wordpress_cli eval-file /var/www/raos-code/staging/mutate_harness.php "$drift_post_id"

for proposal_id in "${release_proposals[@]}" "${code_proposals[@]}"; do
  approval_lease="/var/www/raos-code/private/approval-lease-$proposal_id.json"
  if ! compose exec -T wordpress sh -eu -c \
    'path="$1"; [ -f "$path" ] && [ ! -L "$path" ] && [ "$(stat -c "%a" "$path")" = 600 ]' \
    sh "$approval_lease"; then
    fail RAOS_WORDPRESS_E2E_APPROVAL_LEASE_MISSING
  fi
done

"$repository_root/.venv/bin/python" "$e2e_directory/client.py" apply "$state_path"
if compose exec -T wordpress sh -eu -c \
  'find /var/www/raos-code/private -maxdepth 1 -type f -name "approval-lease-*.json" -print -quit | grep -q .'; then
  fail RAOS_WORDPRESS_E2E_APPROVAL_LEASE_NOT_CONSUMED
fi
wordpress_cli plugin is-active raos-e2e-safe-plugin/raos-e2e-safe-plugin.php \
  || fail RAOS_WORDPRESS_E2E_PLUGIN_ACTIVATION_FAILED
if wordpress_cli plugin is-installed raos-e2e-broken-plugin; then
  fail RAOS_WORDPRESS_E2E_PLUGIN_ROLLBACK_FAILED
fi
printf '%s\n' RAOS_WORDPRESS_E2E_OK
