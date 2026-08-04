#!/bin/bash
# ST-0101 transport wrapper for the approved ChatGPT Pro browser workflow.

set -euo pipefail
umask 077

readonly REPOSITORY_ROOT=/home/minami/rakuten
readonly PRIVATE_ROOT="${REPOSITORY_ROOT}/.secrets"
readonly PROFILE_DIR="${PRIVATE_ROOT}/chatgpt-pro-profile"
readonly MCP_OUTPUT_DIR="${PRIVATE_ROOT}/chatgpt-pro-mcp-output"
readonly SECRET_ROOT="${PRIVATE_ROOT}/chatgpt-pro"
readonly MCP_PACKAGE=@playwright/mcp@0.0.78
readonly NODE_BIN=/home/minami/.nvm/versions/node/v24.18.1/bin/node
readonly MCP_CACHE_ROOT=/home/minami/.npm/_npx/9833c18b2d85bc59
readonly MCP_LOCK="${MCP_CACHE_ROOT}/package-lock.json"
readonly MCP_CLI="${MCP_CACHE_ROOT}/node_modules/@playwright/mcp/cli.js"
readonly MCP_PACKAGE_JSON="${MCP_CACHE_ROOT}/node_modules/@playwright/mcp/package.json"
readonly MCP_LOCK_SHA256=59dcee8d3689b747c7d5be9fc5159fa51c77e9c94790ea27e2363ca5f28659f0
readonly MCP_CLI_SHA256=70dab09ab9a5bc1943fb78e2655f00af7349f9931073833919f19c5d7d786ad6
readonly MCP_PACKAGE_JSON_SHA256=d1d7d6d08a2c8b10ac95a04fc358f8ca55b8855fabb8d6fa8c7cf26dfd5378b7

fail() {
  printf '%s\n' "chatgpt-pro-mcp: fail-closed launch refusal ($1)" >&2
  exit 64
}

check_owner_mode() {
  local path=$1
  local expected_mode=$2
  test ! -L "$path" || fail symlink
  test "$(stat -c %u -- "$path")" = "$(id -u)" || fail owner
  test "$(stat -c %a -- "$path")" = "$expected_mode" || fail mode
}

secrets_file=${PLAYWRIGHT_MCP_SECRETS_FILE:-}
test -n "$secrets_file" || fail missing-secret-file
test "${secrets_file#/}" != "$secrets_file" || fail non-absolute-secret-file
secret_basename=${secrets_file#"${SECRET_ROOT}/"}
test "$secret_basename" != "$secrets_file" || fail secret-file-scope
case "$secret_basename" in
  */* | "") fail secret-file-scope ;;
esac
[[ "$secret_basename" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.env$ ]] || \
  fail secret-file-name

test -d "$PRIVATE_ROOT" || fail missing-private-root
check_owner_mode "$PRIVATE_ROOT" 700
test -d "$SECRET_ROOT" || fail missing-secret-root
check_owner_mode "$SECRET_ROOT" 700
test -f "$secrets_file" || fail missing-secret-file
check_owner_mode "$secrets_file" 600

test -d "$PROFILE_DIR" || fail missing-dedicated-profile
check_owner_mode "$PROFILE_DIR" 700

if test ! -e "$MCP_OUTPUT_DIR"; then
  mkdir -m 700 -- "$MCP_OUTPUT_DIR"
fi
test -d "$MCP_OUTPUT_DIR" || fail invalid-output-directory
check_owner_mode "$MCP_OUTPUT_DIR" 700

test -x "$NODE_BIN" || fail missing-node
test "$("$NODE_BIN" --version)" = v24.18.1 || fail node-version
test -f "$MCP_LOCK" && test ! -L "$MCP_LOCK" || fail mcp-lock
test -f "$MCP_CLI" && test ! -L "$MCP_CLI" || fail mcp-cli
test -f "$MCP_PACKAGE_JSON" && test ! -L "$MCP_PACKAGE_JSON" || fail mcp-package
printf '%s  %s\n' "$MCP_LOCK_SHA256" "$MCP_LOCK" | \
  sha256sum --check --status || fail mcp-lock-hash
printf '%s  %s\n' "$MCP_CLI_SHA256" "$MCP_CLI" | \
  sha256sum --check --status || fail mcp-cli-hash
printf '%s  %s\n' "$MCP_PACKAGE_JSON_SHA256" "$MCP_PACKAGE_JSON" | \
  sha256sum --check --status || fail mcp-package-hash

exec env -u DEBUG "$NODE_BIN" "$MCP_CLI" \
  --browser chrome \
  --user-data-dir "$PROFILE_DIR" \
  --allowed-origins https://chatgpt.com \
  --block-service-workers \
  --sandbox \
  --snapshot-mode none \
  --image-responses omit \
  --console-level error \
  --codegen none \
  --secrets "$secrets_file" \
  --output-dir "$MCP_OUTPUT_DIR"
