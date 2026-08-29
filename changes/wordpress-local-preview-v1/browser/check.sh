#!/usr/bin/busybox sh

set -eu
set -o pipefail

readonly repository_root=/home/minami/rakuten
readonly node_bin=/home/minami/.nvm/versions/node/v24.18.1/bin/node
readonly cli_js=$repository_root/node_modules/@playwright/cli/playwright-cli.js
readonly audit_function=$repository_root/changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js
readonly artifact_directory=$repository_root/output/playwright/local-preview
readonly session=raos-wordpress-local-preview-$$

refuse() {
  /usr/bin/busybox printf '%s\n' RAOS_WORDPRESS_LOCAL_PREVIEW_PLAYWRIGHT_REFUSED >&2
  exit 69
}

[ "$PWD" = "$repository_root" ] || refuse
[ -x "$node_bin" ] || refuse
[ "$($node_bin --version)" = v24.18.1 ] || refuse
[ -f "$cli_js" ] && [ ! -L "$cli_js" ] || refuse
[ -f "$audit_function" ] && [ ! -L "$audit_function" ] || refuse

/usr/bin/busybox mkdir -p -- "$artifact_directory"
TMPDIR=/tmp
TEMP=/tmp
TMP=/tmp
PATH=/home/minami/.nvm/versions/node/v24.18.1/bin:/usr/bin:/bin
LANG=C.UTF-8
LC_ALL=C.UTF-8
TZ=UTC
export TMPDIR TEMP TMP PATH LANG LC_ALL TZ

cleanup() {
  "$node_bin" "$cli_js" -s="$session" close >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

"$node_bin" "$cli_js" -s="$session" open \
  http://127.0.0.1:8888 --browser chrome >/dev/null
"$node_bin" "$cli_js" -s="$session" run-code --filename="$audit_function"

/usr/bin/busybox sha256sum "$artifact_directory"/local-preview-*.png

