#!/usr/bin/busybox sh

# Terminal-only Playwright UI acceptance for the public WordPress home page.
set -eu
set -o pipefail

readonly repository_root=/home/minami/rakuten
readonly node_bin=/home/minami/.nvm/versions/node/v24.18.1/bin/node
readonly cli_js=$repository_root/node_modules/@playwright/cli/playwright-cli.js
readonly audit_function=$repository_root/scripts/wordpress_public_ui_audit.function.js
readonly artifact_directory=$repository_root/output/playwright
readonly session=raos-wordpress-ui-$$

refuse() {
  /usr/bin/busybox printf '%s\n' WORDPRESS_PUBLIC_UI_PLAYWRIGHT_REFUSED >&2
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
  https://kurashinoshirube.com --browser chrome >/dev/null
"$node_bin" "$cli_js" -s="$session" run-code --filename="$audit_function"

if [ -n "${RAOS_WORDPRESS_UI_BASELINE_DIR-}" ]; then
  case "$RAOS_WORDPRESS_UI_BASELINE_DIR" in
    /*) ;;
    *) refuse ;;
  esac
  [ -d "$RAOS_WORDPRESS_UI_BASELINE_DIR" ] || refuse
  for width in 360 390 768 1440; do
    /usr/bin/busybox cmp -s \
      "$RAOS_WORDPRESS_UI_BASELINE_DIR/wordpress-home-$width.png" \
      "$artifact_directory/wordpress-home-$width.png" || {
        /usr/bin/busybox printf '%s\n' "WORDPRESS_PUBLIC_UI_SCREENSHOT_DIFF_$width" >&2
        exit 1
      }
  done
fi

/usr/bin/busybox sha256sum "$artifact_directory"/wordpress-home-*.png
