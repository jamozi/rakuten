#!/bin/bash
# ST-0101 transport wrapper for the approved ChatGPT Pro browser workflow.

set -euo pipefail
umask 077
export PATH=/usr/bin:/bin
readonly PATH

readonly REPOSITORY_ROOT=/home/minami/rakuten
readonly PRIVATE_ROOT="${REPOSITORY_ROOT}/.secrets"
readonly WSLG_DISPLAY=:0
readonly EDGE_EXECUTABLE=/opt/microsoft/msedge/msedge
readonly CHROME_EXECUTABLE=/opt/google/chrome/chrome
readonly EDGE_PROFILE_DIR="${PRIVATE_ROOT}/chatgpt-pro-edge-profile"
readonly CHROME_PROFILE_DIR="${PRIVATE_ROOT}/chatgpt-pro-profile"
readonly MCP_OUTPUT_DIR="${PRIVATE_ROOT}/chatgpt-pro-mcp-output"
readonly SECRET_ROOT="${PRIVATE_ROOT}/chatgpt-pro"
readonly NODE_BIN=/home/minami/.nvm/versions/node/v24.18.1/bin/node
readonly PYTHON_BIN=/usr/bin/python3.10
readonly MCP_RUNTIME_ROOT="${PRIVATE_ROOT}/chatgpt-pro-mcp-runtime"
readonly MCP_RUNTIME_SOURCE="${REPOSITORY_ROOT}/scripts/chatgpt_pro_mcp_runtime"
readonly MCP_RUNTIME_VERIFIER="${MCP_RUNTIME_SOURCE}/verify_runtime.py"
readonly MCP_CLI="${MCP_RUNTIME_ROOT}/node_modules/@playwright/mcp/cli.js"

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

check_fixed_executable() {
  local path=$1
  test -f "$path" && test ! -L "$path" && test -x "$path" || \
    fail browser-executable
  test "$(readlink -f -- "$path")" = "$path" || fail browser-executable
  test "$(stat -c %u -- "$path")" = 0 || fail browser-executable-owner
  test "$(stat -c %a -- "$path")" = 755 || fail browser-executable-mode
}

check_owner_executable() {
  local path=$1
  test -f "$path" && test ! -L "$path" && test -x "$path" || \
    fail runtime-tool
  test "$(readlink -f -- "$path")" = "$path" || fail runtime-tool
  test "$(stat -c %u -- "$path")" = "$(id -u)" || fail runtime-tool-owner
  test "$(stat -c %a -- "$path")" = 755 || fail runtime-tool-mode
}

check_system_executable() {
  local path=$1
  test -f "$path" && test ! -L "$path" && test -x "$path" || \
    fail runtime-verifier
  test "$(readlink -f -- "$path")" = "$path" || fail runtime-verifier
  test "$(stat -c %u -- "$path")" = 0 || fail runtime-verifier-owner
  test "$(stat -c %a -- "$path")" = 755 || fail runtime-verifier-mode
}

browser=${RAOS_CHATGPT_BROWSER:-}
case "$browser" in
  edge)
    readonly MCP_BROWSER=msedge
    readonly BROWSER_EXECUTABLE=$EDGE_EXECUTABLE
    readonly PROFILE_DIR=$EDGE_PROFILE_DIR
    ;;
  chrome)
    readonly MCP_BROWSER=chrome
    readonly BROWSER_EXECUTABLE=$CHROME_EXECUTABLE
    readonly PROFILE_DIR=$CHROME_PROFILE_DIR
    ;;
  *) fail invalid-browser ;;
esac

test "${DISPLAY:-}" = "$WSLG_DISPLAY" || fail invalid-display

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
check_fixed_executable "$BROWSER_EXECUTABLE"

test -d "$PROFILE_DIR" || fail missing-dedicated-profile
check_owner_mode "$PROFILE_DIR" 700

if test ! -e "$MCP_OUTPUT_DIR"; then
  mkdir -m 700 -- "$MCP_OUTPUT_DIR"
fi
test -d "$MCP_OUTPUT_DIR" || fail invalid-output-directory
check_owner_mode "$MCP_OUTPUT_DIR" 700

check_owner_executable "$NODE_BIN"
test "$(env -u NODE_OPTIONS -u NODE_PATH "$NODE_BIN" --version)" = v24.18.1 || \
  fail node-version
check_system_executable "$PYTHON_BIN"
test -f "$MCP_RUNTIME_VERIFIER" && test ! -L "$MCP_RUNTIME_VERIFIER" || \
  fail runtime-verifier
check_owner_mode "$MCP_RUNTIME_VERIFIER" 644
"$PYTHON_BIN" -I -B "$MCP_RUNTIME_VERIFIER" || fail mcp-runtime
test -f "$MCP_CLI" && test ! -L "$MCP_CLI" || fail mcp-cli
check_owner_mode "$MCP_CLI" 600

exec env -u DEBUG -u NODE_OPTIONS -u NODE_PATH "$NODE_BIN" "$MCP_CLI" \
  --browser "$MCP_BROWSER" \
  --executable-path "$BROWSER_EXECUTABLE" \
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
