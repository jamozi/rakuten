#!/usr/bin/busybox sh

set -eu
set -o pipefail

readonly script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
readonly repository_root="$(CDPATH= cd -- "$script_directory/../../.." && pwd -P)"
node_bin="${RAOS_WORDPRESS_PREVIEW_NODE_BIN:-${RAOS_NODE:-}}"
[ -n "$node_bin" ] || node_bin="$(command -v node 2>/dev/null || true)"
readonly node_bin
readonly node_directory="$(dirname -- "$node_bin")"
readonly cli_js=$repository_root/node_modules/@playwright/cli/playwright-cli.js
readonly audit_function=$repository_root/changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js
readonly lighthouse_check=$repository_root/changes/wordpress-local-preview-v1/browser/lighthouse_check.sh
readonly audit_inventory=$repository_root/changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json
readonly axe_source=$repository_root/node_modules/axe-core/axe.min.js
readonly artifact_parent=$repository_root/output/playwright
readonly published_artifact_directory=$artifact_parent/local-preview
readonly session=raos-wordpress-local-preview-$$
readonly preview_origin="${RAOS_WORDPRESS_PREVIEW_ORIGIN:-}"
audit_runtime=''
artifact_directory=''
previous_artifact_directory=''

refuse() {
  /usr/bin/busybox printf '%s\n' RAOS_WORDPRESS_LOCAL_PREVIEW_PLAYWRIGHT_REFUSED >&2
  exit 69
}

remove_ephemeral_directory() {
  case "$1" in
    "$artifact_parent"/.local-preview.pending.*|"$artifact_parent"/.local-preview.previous.*)
      /usr/bin/busybox rm -rf -- "$1"
      ;;
    *)
      refuse
      ;;
  esac
}

[ "$PWD" = "$repository_root" ] || refuse
[ -x "$node_bin" ] || refuse
[ "$($node_bin --version)" = v24.18.1 ] || refuse
[ -n "$preview_origin" ] \
  && /usr/bin/busybox echo "$preview_origin" \
    | /usr/bin/busybox grep -Eq '^http://127\.0\.0\.1:[0-9]{4,5}$' \
  || refuse
[ -f "$cli_js" ] && [ ! -L "$cli_js" ] || refuse
[ -f "$audit_function" ] && [ ! -L "$audit_function" ] || refuse
[ -x "$lighthouse_check" ] && [ ! -L "$lighthouse_check" ] || refuse
[ -f "$audit_inventory" ] && [ ! -L "$audit_inventory" ] || refuse
[ -f "$axe_source" ] && [ ! -L "$axe_source" ] || refuse

cleanup() {
  "$node_bin" "$cli_js" -s="$session" close >/dev/null 2>&1 || true
  [ -z "$audit_runtime" ] || /usr/bin/busybox rm -f -- "$audit_runtime"
  if [ -n "$artifact_directory" ] && [ -d "$artifact_directory" ]; then
    remove_ephemeral_directory "$artifact_directory"
  fi
  if [ -n "$previous_artifact_directory" ] && [ -d "$previous_artifact_directory" ]; then
    if [ ! -e "$published_artifact_directory" ]; then
      /usr/bin/busybox mv -- "$previous_artifact_directory" "$published_artifact_directory" \
        || true
    else
      remove_ephemeral_directory "$previous_artifact_directory"
    fi
  fi
}
trap cleanup EXIT HUP INT TERM

/usr/bin/busybox mkdir -p -- "$artifact_parent"
artifact_directory="$(
  /usr/bin/busybox mktemp -d "$artifact_parent/.local-preview.pending.XXXXXX"
)" || refuse
/usr/bin/busybox chmod 700 -- "$artifact_directory" || refuse
audit_runtime="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-local-audit.XXXXXX)" || refuse
/usr/bin/busybox chmod 600 -- "$audit_runtime" || refuse
"$node_bin" -e '
const fs = require("fs");
const [factoryPath, inventoryPath, axePath, outputPath, artifactDirectory, origin] = process.argv.slice(1);
const factory = fs.readFileSync(factoryPath, "utf8");
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
const axeSource = fs.readFileSync(axePath, "utf8");
fs.writeFileSync(
  outputPath,
  `(${factory})(${JSON.stringify({ artifactDirectory, axeSource, inventory, origin })})`,
  { encoding: "utf8", mode: 0o600 },
);
' "$audit_function" "$audit_inventory" "$axe_source" "$audit_runtime" "$artifact_directory" \
  "$preview_origin" \
  2>/dev/null || refuse
TMPDIR=/tmp
TEMP=/tmp
TMP=/tmp
PATH=$node_directory:/usr/bin:/bin
LANG=C.UTF-8
LC_ALL=C.UTF-8
TZ=UTC
export TMPDIR TEMP TMP PATH LANG LC_ALL TZ

"$node_bin" "$cli_js" -s="$session" open \
  "$preview_origin" --browser chrome >/dev/null
"$node_bin" "$cli_js" -s="$session" run-code --filename="$audit_runtime"

artifact_names="$("$node_bin" -e '
const fs = require("fs");
const inventory = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
for (const surface of [...inventory.surfaces, ...inventory.local_surfaces]) {
  for (const width of inventory.viewports) {
    process.stdout.write(`local-preview-${surface.surface_id}-${width}.png\n`);
  }
  process.stdout.write(`local-preview-${surface.surface_id}-zoom200.png\n`);
}
' "$audit_inventory")" || refuse
expected_count="$("$node_bin" -e '
const fs = require("fs");
const inventory = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
process.stdout.write(String(
  (inventory.surfaces.length + inventory.local_surfaces.length) *
    (inventory.viewports.length + 1),
));
' "$audit_inventory")" || refuse
[ "$expected_count" -eq 130 ] || refuse
"$node_bin" -e '
const fs = require("fs");
const [inventoryPath, artifactDirectory] = process.argv.slice(1);
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
const expected = [];
for (const surface of [...inventory.surfaces, ...inventory.local_surfaces]) {
  for (const width of inventory.viewports) {
    expected.push(`local-preview-${surface.surface_id}-${width}.png`);
  }
  expected.push(`local-preview-${surface.surface_id}-zoom200.png`);
}
expected.sort();
const entries = fs.readdirSync(artifactDirectory, { withFileTypes: true });
const actual = entries.map((entry) => entry.name).sort();
if (
  expected.length !== 130 || actual.length !== expected.length ||
  actual.some((name, index) => name !== expected[index]) ||
  entries.some((entry) => !entry.isFile() || entry.isSymbolicLink())
) process.exit(69);
' "$audit_inventory" "$artifact_directory" || refuse
RAOS_WORDPRESS_PREVIEW_NODE_BIN="$node_bin" \
RAOS_WORDPRESS_PREVIEW_ORIGIN="$preview_origin" \
  "$lighthouse_check"

previous_artifact_directory=$artifact_parent/.local-preview.previous.$$
[ ! -e "$previous_artifact_directory" ] || refuse
if [ -e "$published_artifact_directory" ]; then
  [ -d "$published_artifact_directory" ] && [ ! -L "$published_artifact_directory" ] || refuse
  /usr/bin/busybox mv -- \
    "$published_artifact_directory" "$previous_artifact_directory" || refuse
fi
if ! /usr/bin/busybox mv -- "$artifact_directory" "$published_artifact_directory"; then
  if [ -d "$previous_artifact_directory" ] && [ ! -e "$published_artifact_directory" ]; then
    /usr/bin/busybox mv -- \
      "$previous_artifact_directory" "$published_artifact_directory" || true
  fi
  refuse
fi
artifact_directory=''
if [ -d "$previous_artifact_directory" ]; then
  remove_ephemeral_directory "$previous_artifact_directory"
fi
previous_artifact_directory=''

screenshots=''
for artifact_name in $artifact_names; do
  screenshot="$published_artifact_directory/$artifact_name"
  [ -f "$screenshot" ] && [ ! -L "$screenshot" ] || refuse
  screenshots="$screenshots $screenshot"
done
set -- $screenshots
[ "$#" -eq "$expected_count" ] || refuse
/usr/bin/busybox sha256sum "$@"
