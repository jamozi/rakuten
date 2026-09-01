#!/usr/bin/busybox sh

set -eu
set -o pipefail

readonly script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
readonly repository_root="$(CDPATH= cd -- "$script_directory/../../.." && pwd -P)"
readonly node_bin="${RAOS_WORDPRESS_PREVIEW_NODE_BIN:-}"
readonly node_platform="$($node_bin -p 'process.platform' 2>/dev/null || true)"
readonly node_temporary_directory="$($node_bin -p 'require("os").tmpdir()' 2>/dev/null || true)"
readonly preview_origin="${RAOS_WORDPRESS_PREVIEW_ORIGIN:-}"
readonly lighthouse_cli="$repository_root/node_modules/lighthouse/cli/index.js"
readonly chrome_candidate="${RAOS_WORDPRESS_PREVIEW_CHROME_BIN:-/usr/bin/google-chrome}"
readonly chrome_bin="$(/usr/bin/readlink -f -- "$chrome_candidate" 2>/dev/null || true)"
readonly artifact_directory="$repository_root/output/lighthouse/local-preview"
readonly theme_contract="$repository_root/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/theme-contract.v1.json"
readonly navigation_contract="$repository_root/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/editorial-navigation.v3.json"
readonly audit_inventory="$repository_root/changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
readonly audit_script="$repository_root/changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js"
readonly lighthouse_version=12.8.2
binding_file=''

refuse() {
  /usr/bin/busybox printf '%s\n' RAOS_WORDPRESS_LOCAL_PREVIEW_LIGHTHOUSE_REFUSED >&2
  exit 69
}

cleanup() {
  [ -z "$binding_file" ] || /usr/bin/busybox rm -f -- "$binding_file"
}
trap cleanup EXIT HUP INT TERM

[ "$PWD" = "$repository_root" ] || refuse
[ -x "$node_bin" ] || refuse
[ "$($node_bin --version)" = v24.18.1 ] || refuse
[ "$node_platform" = linux ] || refuse
case "$node_temporary_directory" in
  /*) ;;
  *) refuse ;;
esac
case "$node_temporary_directory/" in
  "$repository_root"/*) refuse ;;
esac
[ -d "$node_temporary_directory" ] && [ ! -L "$node_temporary_directory" ] \
  || refuse
[ -n "$preview_origin" ] \
  && /usr/bin/busybox echo "$preview_origin" \
    | /usr/bin/busybox grep -Eq '^http://127\.0\.0\.1:[0-9]{4,5}$' \
  || refuse
[ -f "$lighthouse_cli" ] && [ ! -L "$lighthouse_cli" ] || refuse
[ -n "$chrome_bin" ] && [ -f "$chrome_bin" ] && [ -x "$chrome_bin" ] \
  && [ ! -L "$chrome_bin" ] || refuse
for input_path in "$theme_contract" "$navigation_contract" "$audit_inventory" "$audit_script"; do
  [ -f "$input_path" ] && [ ! -L "$input_path" ] || refuse
done
[ ! -L "$repository_root/output" ] \
  && [ ! -L "$repository_root/output/lighthouse" ] \
  && [ ! -L "$artifact_directory" ] \
  || refuse
/usr/bin/busybox mkdir -p -- "$artifact_directory"
[ -d "$artifact_directory" ] && [ ! -L "$artifact_directory" ] || refuse

# A new run can never inherit a prior success. Refuse links and invalidate every
# known report plus the summary before capturing any new evidence.
for stale_name in \
  summary.json summary.json.tmp \
  home-1.json home-2.json home-3.json \
  article-a04-1.json article-a04-2.json article-a04-3.json
do
  stale_path="$artifact_directory/$stale_name"
  [ ! -L "$stale_path" ] || refuse
  /usr/bin/busybox rm -f -- "$stale_path" || refuse
done

binding_file="$(/usr/bin/busybox mktemp /tmp/raos-wordpress-lighthouse-binding.XXXXXX)" \
  || refuse
/usr/bin/busybox chmod 600 -- "$binding_file" || refuse
"$node_bin" -e '
const crypto = require("crypto");
const fs = require("fs");
const [bindingPath, themePath, navigationPath, inventoryPath, auditPath] =
  process.argv.slice(1);
const MAX_INPUT_BYTES = 4 * 1024 * 1024;
const readBoundFile = (file) => {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 1 || stat.size > MAX_INPUT_BYTES) {
    throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_INPUT_INVALID");
  }
  return fs.readFileSync(file);
};
const sha256 = (payload) => crypto.createHash("sha256").update(payload).digest("hex");
const themeBytes = readBoundFile(themePath);
const navigationBytes = readBoundFile(navigationPath);
const inventoryBytes = readBoundFile(inventoryPath);
const auditBytes = readBoundFile(auditPath);
const theme = JSON.parse(themeBytes.toString("utf8"));
const runtimeRevision = theme.runtime_evidence?.revision;
const sourceFingerprint = theme.runtime_evidence?.source_fingerprint;
if (
  !/^[0-9a-f]{64}$/.test(runtimeRevision || "") ||
  !/^[0-9a-f]{64}$/.test(sourceFingerprint || "") ||
  runtimeRevision !== sourceFingerprint
) {
  throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_THEME_EVIDENCE_INVALID");
}
const binding = {
  schema: "RAOS_WORDPRESS_LIGHTHOUSE_INPUT_BINDING_V1",
  started_at: new Date().toISOString(),
  inputs: {
    audit_inventory_sha256: sha256(inventoryBytes),
    audit_script_sha256: sha256(auditBytes),
    navigation_sha256: sha256(navigationBytes),
    theme_contract_sha256: sha256(themeBytes),
    theme_runtime_revision: runtimeRevision,
    theme_source_fingerprint: sourceFingerprint,
  },
};
fs.writeFileSync(bindingPath, `${JSON.stringify(binding, null, 2)}\n`, {
  encoding: "utf8",
  mode: 0o600,
});
' "$binding_file" "$theme_contract" "$navigation_contract" "$audit_inventory" \
  "$audit_script" 2>/dev/null || refuse

run_target() {
  target_name=$1
  target_url=$2
  run=1
  while [ "$run" -le 3 ]; do
    output_path="$artifact_directory/$target_name-$run.json"
    CHROME_PATH="$chrome_bin" "$node_bin" "$lighthouse_cli" "$target_url" \
      --only-categories=performance \
      --form-factor=mobile \
      --throttling-method=simulate \
      --output=json \
      --output-path="$output_path" \
      --chrome-flags='--headless=new --no-sandbox --disable-dev-shm-usage' \
      --quiet
    [ -f "$output_path" ] && [ ! -L "$output_path" ] || refuse
    run=$((run + 1))
  done
}

run_target home "$preview_origin/"
run_target article-a04 "$preview_origin/local-preview-countertop-dishwasher-for-small-households/"

"$node_bin" -e '
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const [directory, origin, expectedVersion, bindingPath, themePath, navigationPath,
  inventoryPath, auditPath] = process.argv.slice(1);
const MAX_EVIDENCE_AGE_MS = 2 * 60 * 60 * 1000;
const MAX_REPORT_BYTES = 50 * 1024 * 1024;
const REPETITIONS = 3;
const sha256 = (payload) => crypto.createHash("sha256").update(payload).digest("hex");
const readRegular = (file, maximum) => {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 1 || stat.size > maximum) {
    throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_FILE_INVALID");
  }
  return fs.readFileSync(file);
};
const binding = JSON.parse(readRegular(bindingPath, 65536).toString("utf8"));
if (
  binding.schema !== "RAOS_WORDPRESS_LIGHTHOUSE_INPUT_BINDING_V1" ||
  !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(binding.started_at || "")
) {
  throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_BINDING_INVALID");
}
const currentInputs = {
  audit_inventory_sha256: sha256(readRegular(inventoryPath, 4 * 1024 * 1024)),
  audit_script_sha256: sha256(readRegular(auditPath, 4 * 1024 * 1024)),
  navigation_sha256: sha256(readRegular(navigationPath, 4 * 1024 * 1024)),
  theme_contract_sha256: sha256(readRegular(themePath, 4 * 1024 * 1024)),
};
for (const [name, value] of Object.entries(currentInputs)) {
  if (!/^[0-9a-f]{64}$/.test(value) || binding.inputs?.[name] !== value) {
    throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_INPUT_CHANGED");
  }
}
for (const name of ["theme_runtime_revision", "theme_source_fingerprint"]) {
  if (!/^[0-9a-f]{64}$/.test(binding.inputs?.[name] || "")) {
    throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_THEME_EVIDENCE_INVALID");
  }
}
if (binding.inputs.theme_runtime_revision !== binding.inputs.theme_source_fingerprint) {
  throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_THEME_EVIDENCE_MISMATCH");
}
const currentTheme = JSON.parse(readRegular(themePath, 4 * 1024 * 1024).toString("utf8"));
if (
  currentTheme.runtime_evidence?.revision !== binding.inputs.theme_runtime_revision ||
  currentTheme.runtime_evidence?.source_fingerprint !== binding.inputs.theme_source_fingerprint
) {
  throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_THEME_EVIDENCE_CHANGED");
}
const capturedAt = new Date().toISOString();
const startedMs = Date.parse(binding.started_at);
const capturedMs = Date.parse(capturedAt);
if (
  !Number.isFinite(startedMs) || !Number.isFinite(capturedMs) ||
  capturedMs < startedMs || capturedMs - startedMs > MAX_EVIDENCE_AGE_MS
) {
  throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_EVIDENCE_STALE");
}
const targets = [
  { name: "home", url: `${origin}/` },
  {
    name: "article-a04",
    url: `${origin}/local-preview-countertop-dishwasher-for-small-households/`,
  },
];
const metricIds = {
  lcp_ms: "largest-contentful-paint",
  cls: "cumulative-layout-shift",
  tbt_ms: "total-blocking-time",
};
const limits = { lcp_ms: 2500, cls: 0.1, tbt_ms: 200 };
const median = (values) => {
  if (values.length !== REPETITIONS) {
    throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_SAMPLE_COUNT_INVALID");
  }
  return [...values].sort((left, right) => left - right)[Math.floor(values.length / 2)];
};
const results = [];
for (const target of targets) {
  const samples = [];
  const reports = [];
  for (let run = 1; run <= REPETITIONS; run += 1) {
    const file = path.join(directory, `${target.name}-${run}.json`);
    const reportBytes = readRegular(file, MAX_REPORT_BYTES);
    const report = JSON.parse(reportBytes.toString("utf8"));
    const fetchMs = Date.parse(report.fetchTime);
    if (
      report.lighthouseVersion !== expectedVersion ||
      report.requestedUrl !== target.url ||
      report.finalDisplayedUrl !== target.url ||
      report.runtimeError ||
      typeof report.categories?.performance?.score !== "number" ||
      !Number.isFinite(fetchMs) || fetchMs < startedMs - 1000 || fetchMs > capturedMs
    ) {
      throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_REPORT_INVALID");
    }
    const metrics = {};
    for (const [name, auditId] of Object.entries(metricIds)) {
      const value = report.audits?.[auditId]?.numericValue;
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
        throw new Error("RAOS_WORDPRESS_LIGHTHOUSE_METRIC_INVALID");
      }
      metrics[name] = value;
    }
    samples.push(metrics);
    reports.push({
      fetch_time: report.fetchTime,
      report_sha256: sha256(reportBytes),
      run,
    });
  }
  const medians = Object.fromEntries(
    Object.keys(metricIds).map((name) => [
      name,
      median(samples.map((sample) => sample[name])),
    ]),
  );
  const passed = Object.entries(limits).every(
    ([name, maximum]) => medians[name] <= maximum,
  );
  results.push({
    target: target.name,
    url: target.url,
    sample_count: samples.length,
    samples,
    medians,
    reports,
    passed,
  });
}
const summary = {
  schema: "RAOS_WORDPRESS_LIGHTHOUSE_MEDIAN_V2",
  captured_at: capturedAt,
  started_at: binding.started_at,
  evidence_max_age_ms: MAX_EVIDENCE_AGE_MS,
  lighthouse_version: expectedVersion,
  inputs: binding.inputs,
  repetitions: REPETITIONS,
  sample_count: results.reduce((count, result) => count + result.sample_count, 0),
  limits,
  results,
  passed: results.every((result) => result.passed),
};
const summaryPath = path.join(directory, "summary.json");
const temporarySummaryPath = path.join(directory, "summary.json.tmp");
fs.writeFileSync(temporarySummaryPath, `${JSON.stringify(summary, null, 2)}\n`, {
  encoding: "utf8",
  flag: "wx",
  mode: 0o600,
});
fs.renameSync(temporarySummaryPath, summaryPath);
if (!summary.passed) process.exit(1);
' "$artifact_directory" "$preview_origin" "$lighthouse_version" "$binding_file" \
  "$theme_contract" "$navigation_contract" "$audit_inventory" "$audit_script" \
  2>/dev/null || refuse

/usr/bin/busybox printf '%s\n' RAOS_WORDPRESS_LOCAL_PREVIEW_LIGHTHOUSE_PASSED
