#!/usr/bin/busybox sh

# Terminal-only Playwright UI acceptance for home, ten articles, and three pages.
set -eu
set -o pipefail

readonly script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
readonly repository_root="$(CDPATH= cd -- "$script_directory/.." && pwd -P)"
readonly node_bin=/home/minami/.nvm/versions/node/v24.18.1/bin/node
readonly cli_js=$repository_root/node_modules/@playwright/cli/playwright-cli.js
readonly audit_function=$repository_root/scripts/wordpress_public_ui_audit.function.js
readonly audit_inventory=$repository_root/changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json
readonly artifact_directory=$repository_root/output/playwright
readonly session=raos-wordpress-ui-$$
audit_runtime=''

refuse() {
  /usr/bin/busybox printf '%s\n' WORDPRESS_PUBLIC_UI_PLAYWRIGHT_REFUSED >&2
  exit 69
}

[ "$PWD" = "$repository_root" ] || refuse
[ -x "$node_bin" ] || refuse
[ "$($node_bin --version)" = v24.18.1 ] || refuse
[ -f "$cli_js" ] && [ ! -L "$cli_js" ] || refuse
[ -f "$audit_function" ] && [ ! -L "$audit_function" ] || refuse
[ -f "$audit_inventory" ] && [ ! -L "$audit_inventory" ] || refuse

cleanup() {
  "$node_bin" "$cli_js" -s="$session" close >/dev/null 2>&1 || true
  [ -z "$audit_runtime" ] || /usr/bin/busybox rm -f -- "$audit_runtime"
}
trap cleanup EXIT HUP INT TERM

/usr/bin/busybox mkdir -p -- "$artifact_directory"
audit_runtime="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-public-audit.XXXXXX)" || refuse
/usr/bin/busybox chmod 600 -- "$audit_runtime" || refuse
"$node_bin" -e '
const fs = require("fs");
const [factoryPath, inventoryPath, outputPath, artifactDirectory] = process.argv.slice(1);
const factory = fs.readFileSync(factoryPath, "utf8");
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
fs.writeFileSync(
  outputPath,
  `(${factory})(${JSON.stringify({ artifactDirectory, inventory })})`,
  { encoding: "utf8", mode: 0o600 },
);
' "$audit_function" "$audit_inventory" "$audit_runtime" "$artifact_directory" \
  2>/dev/null || refuse
TMPDIR=/tmp
TEMP=/tmp
TMP=/tmp
PATH=/home/minami/.nvm/versions/node/v24.18.1/bin:/usr/bin:/bin
LANG=C.UTF-8
LC_ALL=C.UTF-8
TZ=UTC
export TMPDIR TEMP TMP PATH LANG LC_ALL TZ

"$node_bin" "$cli_js" -s="$session" open \
  https://kurashinoshirube.com --browser chrome >/dev/null
"$node_bin" "$cli_js" -s="$session" run-code --filename="$audit_runtime"

artifact_names="$("$node_bin" -e '
const fs = require("fs");
const inventory = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
for (const surface of inventory.surfaces) {
  for (const width of inventory.viewports) {
    process.stdout.write(`wordpress-${surface.surface_id}-${width}.png\n`);
  }
}
' "$audit_inventory")" || refuse
expected_count="$("$node_bin" -e '
const fs = require("fs");
const inventory = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
process.stdout.write(String(inventory.surfaces.length * inventory.viewports.length));
' "$audit_inventory")" || refuse

if [ -n "${RAOS_WORDPRESS_UI_BASELINE_DIR-}" ]; then
  case "$RAOS_WORDPRESS_UI_BASELINE_DIR" in
    /*) ;;
    *) refuse ;;
  esac
  [ -d "$RAOS_WORDPRESS_UI_BASELINE_DIR" ] || refuse
  for artifact_name in $artifact_names; do
    /usr/bin/busybox cmp -s \
      "$RAOS_WORDPRESS_UI_BASELINE_DIR/$artifact_name" \
      "$artifact_directory/$artifact_name" || {
        /usr/bin/busybox printf '%s\n' \
          "WORDPRESS_PUBLIC_UI_SCREENSHOT_DIFF_$artifact_name" >&2
        exit 1
      }
  done
fi

screenshots=''
for artifact_name in $artifact_names; do
  screenshot="$artifact_directory/$artifact_name"
  [ -f "$screenshot" ] && [ ! -L "$screenshot" ] || refuse
  screenshots="$screenshots $screenshot"
done
set -- $screenshots
[ "$#" -eq "$expected_count" ] || refuse
/usr/bin/busybox sha256sum "$@"
