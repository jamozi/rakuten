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
readonly incremental_scope_loader=$script_directory/incremental_scope.py
readonly mixed_report_adapter=$script_directory/mixed_audit_report.py
readonly python_bin="${RAOS_WORDPRESS_PREVIEW_PYTHON_BIN:-$repository_root/.venv/bin/python}"
readonly publication_profile="${RAOS_WORDPRESS_PUBLICATION_PROFILE:-legacy-full}"
readonly link_mode="${RAOS_WORDPRESS_LINK_MODE:-standard-api}"
readonly fixture_root="${RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT:-}"
readonly release_candidate="${RAOS_WORDPRESS_RELEASE_CANDIDATE:-}"
readonly diagnostic_surfaces="${RAOS_WORDPRESS_BROWSER_SURFACES:-}"
readonly started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
readonly axe_source=$repository_root/node_modules/axe-core/axe.min.js
readonly artifact_parent=$repository_root/output/playwright
readonly published_artifact_directory=$artifact_parent/local-preview
readonly session=raos-wordpress-local-preview-$$
readonly preview_origin="${RAOS_WORDPRESS_PREVIEW_ORIGIN:-}"
audit_runtime=''
artifact_directory=''
previous_artifact_directory=''
incremental_scope_file=''
runtime_inventory_file=''
mixed_report_binding=''
mixed_raw_result=''

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
[ "$link_mode" = standard-api ] || [ "$link_mode" = measured-admin ] || refuse
case "$publication_profile" in
  legacy-full) ;;
  verified-incremental)
    [ -z "$diagnostic_surfaces" ] || refuse
    [ "$link_mode" = standard-api ] && [ -n "$fixture_root" ] || refuse
    [ -x "$python_bin" ] && [ -f "$incremental_scope_loader" ] \
      && [ ! -L "$incremental_scope_loader" ] || refuse
    [ -f "$mixed_report_adapter" ] && [ ! -L "$mixed_report_adapter" ] || refuse
    ;;
  *) refuse ;;
esac

cleanup() {
  "$node_bin" "$cli_js" -s="$session" close >/dev/null 2>&1 || true
  [ -z "$audit_runtime" ] || /usr/bin/busybox rm -f -- "$audit_runtime"
  [ -z "$incremental_scope_file" ] || /usr/bin/busybox rm -f -- "$incremental_scope_file"
  [ -z "$runtime_inventory_file" ] || /usr/bin/busybox rm -f -- "$runtime_inventory_file"
  [ -z "$mixed_report_binding" ] || /usr/bin/busybox rm -f -- "$mixed_report_binding"
  if [ -n "$mixed_raw_result" ] && [ -s "$mixed_raw_result" ]; then
    /usr/bin/busybox cp -- "$mixed_raw_result" "$artifact_parent/local-preview.last-attempt.$$.cli.txt"
    /usr/bin/busybox printf 'Browser attempt output: %s/local-preview.last-attempt.%s.cli.txt\n' "$artifact_parent" "$$"
  fi
  [ -z "$mixed_raw_result" ] || /usr/bin/busybox rm -f -- "$mixed_raw_result"
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

set --
if [ -n "$release_candidate" ]; then
  [ "$publication_profile" = verified-incremental ] || refuse
  set -- --candidate "$release_candidate"
  if [ "${RAOS_WORDPRESS_BROWSER_FORCE:-0}" != 1 ] &&
    PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$mixed_report_adapter" verify \
      --fixture-root "$fixture_root" --origin "$preview_origin" "$@" >/dev/null 2>&1
  then
    /usr/bin/busybox printf '%s\n' 'WordPress browser results reused; original timestamps retained.'
    exit 0
  fi
fi

/usr/bin/busybox mkdir -p -- "$artifact_parent"
artifact_directory="$(
  /usr/bin/busybox mktemp -d "$artifact_parent/.local-preview.pending.XXXXXX"
)" || refuse
/usr/bin/busybox chmod 700 -- "$artifact_directory" || refuse
audit_runtime="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-local-audit.XXXXXX)" || refuse
/usr/bin/busybox chmod 600 -- "$audit_runtime" || refuse
mixed_raw_result="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-browser-result.XXXXXX)" || refuse
if [ "$publication_profile" = verified-incremental ]; then
  incremental_scope_file="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-incremental-scope.XXXXXX)" || refuse
  /usr/bin/busybox chmod 600 -- "$incremental_scope_file" || refuse
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$incremental_scope_loader" \
    --fixture-root "$fixture_root" >"$incremental_scope_file" || refuse
  mixed_report_binding="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-browser-binding.XXXXXX)" || refuse
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$mixed_report_adapter" begin \
    --fixture-root "$fixture_root" --origin "$preview_origin" \
    --binding-file "$mixed_report_binding" "$@" || refuse
  runtime_inventory_file="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-reader-inventory.XXXXXX)" || refuse
  /usr/bin/busybox chmod 600 -- "$runtime_inventory_file" || refuse
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" - "$script_directory" "$audit_inventory" \
    "$mixed_report_binding" "$incremental_scope_file" >"$runtime_inventory_file" <<'PYREADERINVENTORY' || refuse
import json
from pathlib import Path
import sys

sys.path.insert(0, sys.argv[1])
from mixed_audit_report import bind_reader_inventory, canonical, read_regular, reject, sha

inventory_raw = read_regular(Path(sys.argv[2]))
inputs = json.loads(read_regular(Path(sys.argv[3])))["inputs"]
scope = json.loads(read_regular(Path(sys.argv[4])))
if sha(inventory_raw) != inputs["audit_inventory_sha256"] or scope != inputs["scope"]:
    reject()
sys.stdout.buffer.write(canonical(bind_reader_inventory(json.loads(inventory_raw), inputs)))
PYREADERINVENTORY
fi
"$node_bin" -e '
const fs = require("fs");
const [factoryPath, inventoryPath, axePath, outputPath, artifactDirectory, origin,
  publicationProfile, linkMode, scopePath, bindingPath] = process.argv.slice(1);
const factory = fs.readFileSync(factoryPath, "utf8");
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
const axeSource = fs.readFileSync(axePath, "utf8");
const incrementalScope = scopePath ? JSON.parse(fs.readFileSync(scopePath, "utf8")) : null;
const binding = bindingPath ? JSON.parse(fs.readFileSync(bindingPath, "utf8")) : null;
const selectedSurfaceIds = binding?.inputs?.browser_plan?.surface_ids ||
  (process.env.RAOS_WORDPRESS_BROWSER_SURFACES ? process.env.RAOS_WORDPRESS_BROWSER_SURFACES.split(",") : null);
const workers = Number(process.env.RAOS_WORDPRESS_BROWSER_WORKERS ||
  Math.min(4, require("os").availableParallelism()));
fs.writeFileSync(
  outputPath,
  `(${factory})(${JSON.stringify({ artifactDirectory, axeSource, inventory, origin,
    publicationProfile, linkMode, incrementalScope, selectedSurfaceIds, workers })})`,
  { encoding: "utf8", mode: 0o600 },
);
' "$audit_function" "${runtime_inventory_file:-$audit_inventory}" "$axe_source" "$audit_runtime" "$artifact_directory" \
  "$preview_origin" "$publication_profile" "$link_mode" "$incremental_scope_file" "$mixed_report_binding" \
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
"$node_bin" "$cli_js" -s="$session" run-code --filename="$audit_runtime" >"$mixed_raw_result"
# Keep the full runner output as an artifact, not hundreds of KB of copied code
# in a task transcript. CLI errors can have exit status zero, so inspect results.
"$python_bin" - "$mixed_raw_result" <<'PYRESULT'
import json, re, sys
from pathlib import Path
raw = Path(sys.argv[1]).read_text()
if "### Error" in raw:
    codes = re.findall(r"RAOS_[A-Z0-9_]+", raw.split("### Error", 1)[1].split("### Ran", 1)[0])
    print("Browser failed: " + (codes[0] if codes else "inspect original browser output"), file=sys.stderr)
    raise SystemExit(69)
match = re.search(r"(?m)^### Result\n", raw)
if match is None:
    raise SystemExit(69)
results, _ = json.JSONDecoder().raw_decode(raw[match.end():].lstrip())
if not isinstance(results, list) or not results:
    raise SystemExit(69)
print(f"Browser assertions passed: {len(results)} surface/viewport results")
PYRESULT

"$node_bin" -e '
const fs = require("fs");
const [inventoryPath, artifactDirectory, bindingPath] = process.argv.slice(1);
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
const binding = bindingPath ? JSON.parse(fs.readFileSync(bindingPath, "utf8")) : null;
const selected = binding?.inputs?.browser_plan?.surface_ids ||
  (process.env.RAOS_WORDPRESS_BROWSER_SURFACES ? process.env.RAOS_WORDPRESS_BROWSER_SURFACES.split(",") :
    [...inventory.surfaces, ...inventory.local_surfaces].map((row) => row.surface_id));
const expected = selected.flatMap((id) => [
  ...inventory.viewports.map((width) => `local-preview-${id}-${width}.png`),
  `local-preview-${id}-zoom200.png`,
]).sort();
const entries = fs.readdirSync(artifactDirectory, { withFileTypes: true });
const actual = entries.map((entry) => entry.name).sort();
if (!expected.length || new Set(expected).size !== expected.length ||
    actual.length !== expected.length || actual.some((name, i) => name !== expected[i]) ||
    entries.some((entry) => !entry.isFile() || entry.isSymbolicLink())) process.exit(69);
' "${runtime_inventory_file:-$audit_inventory}" "$artifact_directory" "$mixed_report_binding" || refuse
RAOS_WORDPRESS_PREVIEW_NODE_BIN="$node_bin" \
RAOS_WORDPRESS_PREVIEW_ORIGIN="$preview_origin" \
RAOS_WORDPRESS_BROWSER_BINDING="$mixed_report_binding" \
  "$lighthouse_check"
if [ "$publication_profile" = verified-incremental ]; then
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$incremental_scope_loader" \
    --fixture-root "$fixture_root" | /usr/bin/busybox cmp -s "$incremental_scope_file" - \
    || refuse
fi

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

if [ "$publication_profile" = verified-incremental ]; then
  PYTHONDONTWRITEBYTECODE=1 "$python_bin" "$mixed_report_adapter" finish \
    --fixture-root "$fixture_root" --origin "$preview_origin" \
    --binding-file "$mixed_report_binding" --raw-result "$mixed_raw_result" \
    --artifact-directory "$published_artifact_directory" "$@" || refuse
fi

if [ "$publication_profile" = legacy-full ]; then
  /usr/bin/busybox cp -- "$mixed_raw_result" "$artifact_parent/local-preview.audit.cli.txt"
fi
"$python_bin" - "$published_artifact_directory" "$preview_origin" "$started_at" <<'PYSUMMARY'
from datetime import UTC, datetime
import hashlib, json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
shots = [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.glob("*.png"))]
end = datetime.now(UTC)
summary = {"schema": "RAOS_WORDPRESS_LOCAL_RUN_SUMMARY_V2", "publication_authority": False,
    "origin": sys.argv[2], "started_at": sys.argv[3], "completed_at": end.isoformat(),
    "duration_seconds": round((end - datetime.fromisoformat(sys.argv[3])).total_seconds(), 2),
    "screenshots": shots, "workers": int(os.environ.get("RAOS_WORDPRESS_BROWSER_WORKERS", min(4, os.cpu_count() or 1)))}
path = root.parent / "local-preview.run-summary.v2.json"
path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(f"Browser and Lighthouse passed: {len(shots)} screenshots; {summary['duration_seconds']}s; {path}")
PYSUMMARY
