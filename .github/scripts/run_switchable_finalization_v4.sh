#!/bin/bash

set -euo pipefail

: "${GITHUB_WORKSPACE:?}"
: "${GITHUB_REPOSITORY:?}"
: "${GITHUB_SERVER_URL:?}"
: "${GITHUB_RUN_ID:?}"
: "${GH_TOKEN:?}"
: "${FOUNDATION_BRANCH:?}"
: "${TARGET_BRANCH:?}"
: "${PYTHON_VERSION:?}"

transport="$GITHUB_WORKSPACE/overlay-transport"
subject="$GITHUB_WORKSPACE/subject"
python_path="$(uv --no-config python find "$PYTHON_VERSION")"

"$python_path" "$transport/.github/scripts/materialize_switchable_tree.py" \
  --transport "$transport" \
  --subject "$subject" \
  --temporary "$RUNNER_TEMP/materialize-v4" \
  --foundation-branch "$FOUNDATION_BRANCH"

"$python_path" "$subject/scripts/finalize_strategy_switchboard_sources_v3.py" \
  --apply --root "$subject"
"$python_path" "$subject/scripts/finalize_strategy_switchboard_sources_v3.py" \
  --check --root "$subject"
git -C "$subject" diff --check

cd "$subject"

uv --no-config --color never sync --locked \
  --no-default-groups --group dev --no-install-project --no-install-local \
  --managed-python --no-python-downloads --python "$PYTHON_VERSION" \
  --no-build --no-sources --default-index https://pypi.org/simple \
  --index-strategy first-index --keyring-provider disabled --link-mode copy \
  --resolution highest --prerelease disallow \
  --exclude-newer 2026-08-01T16:50:16Z --no-cache --no-progress

if [[ -f package-lock.json ]]; then
  npm ci --ignore-scripts --no-audit --no-fund
fi

UV_RUN=(
  uv --config-file "$PWD/uv.toml" run --locked --offline --no-cache --no-sync
  --no-env-file --no-python-downloads --python "$PYTHON_VERSION"
)

owned_sources=(
  python/raos/strategy_switchboard
  scripts/build_all_story_strategy_catalog.py
  scripts/finalize_strategy_switchboard_sources.py
  scripts/finalize_strategy_switchboard_sources_v2.py
  scripts/finalize_strategy_switchboard_sources_v3.py
  scripts/select_all_story_strategy.py
  tests/strategy_switchboard
)

"${UV_RUN[@]}" ruff format "${owned_sources[@]}"
"${UV_RUN[@]}" python scripts/finalize_strategy_switchboard_sources_v3.py \
  --check --root "$PWD"
"${UV_RUN[@]}" python scripts/build_all_story_strategy_catalog.py \
  --write --root "$PWD"
git diff --check

foundation_sha="$(cat .foundation-commit.sha)"
failure=0
while IFS= read -r path; do
  [[ -f $path ]] || continue
  case "$path" in
    */__init__.py|*.keep|*.gitkeep) continue ;;
  esac
  case "$path" in
    python/*|scripts/*|tests/*|packages/*|apps/*|infra/*|changes/*)
      if [[ ! -s $path ]]; then
        printf 'empty implementation artifact: %s\n' "$path" >&2
        failure=1
      fi
      ;;
  esac
done < <(git diff --name-only "$foundation_sha")
if ((failure != 0)); then
  exit 1
fi

git add -A
git diff --cached --binary >"$RUNNER_TEMP/v4-before.patch"
git diff --cached --name-only >"$RUNNER_TEMP/v4-changed-paths.txt"
test -s "$RUNNER_TEMP/v4-before.patch"
test -s "$RUNNER_TEMP/v4-changed-paths.txt"

"${UV_RUN[@]}" python scripts/finalize_strategy_switchboard_sources_v3.py \
  --check --root "$PWD"
"${UV_RUN[@]}" python scripts/build_all_story_strategy_catalog.py \
  --check --root "$PWD"
"${UV_RUN[@]}" python -m compileall -q \
  python/raos/strategy_switchboard \
  scripts/build_all_story_strategy_catalog.py \
  scripts/finalize_strategy_switchboard_sources.py \
  scripts/finalize_strategy_switchboard_sources_v2.py \
  scripts/finalize_strategy_switchboard_sources_v3.py \
  scripts/select_all_story_strategy.py
"${UV_RUN[@]}" ruff check --no-cache "${owned_sources[@]}"
"${UV_RUN[@]}" ruff format --check "${owned_sources[@]}"
"${UV_RUN[@]}" mypy --strict \
  python/raos/strategy_switchboard \
  scripts/build_all_story_strategy_catalog.py \
  scripts/finalize_strategy_switchboard_sources.py \
  scripts/finalize_strategy_switchboard_sources_v2.py \
  scripts/finalize_strategy_switchboard_sources_v3.py \
  scripts/select_all_story_strategy.py
"${UV_RUN[@]}" pytest -p no:cacheprovider --import-mode=importlib -q \
  tests/strategy_switchboard

"${UV_RUN[@]}" python - <<'PY'
from __future__ import annotations

import ast
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

root = Path.cwd()
story_text = (
    root / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
).read_text(encoding="utf-8")
decision_text = (
    root / "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
).read_text(encoding="utf-8")
stories = set(re.findall(r"\bST-[0-9]{4}\b", story_text))
decisions = set(re.findall(r"\bOD-[0-9]{3}\b", decision_text))
if decisions != {f"OD-{number:03d}" for number in range(1, 16)}:
    raise SystemExit("canonical Open Decision inventory mismatch")

catalog_path = root / "changes/all-stories/generated/switchable-strategy-catalog.v1.json"
document = json.loads(catalog_path.read_bytes())
candidates = document["catalog"]["candidates"]
grouped: dict[str, list[dict[str, object]]] = {}
for candidate in candidates:
    grouped.setdefault(candidate["boundary_id"], []).append(candidate)
if set(grouped) != stories | decisions:
    raise SystemExit("catalog does not cover the exact canonical boundaries")

for boundary_id, items in grouped.items():
    if len(items) != 3:
        raise SystemExit(f"{boundary_id}: expected exactly three candidates")
    by_tier = {item["tier"]: item for item in items}
    if set(by_tier) != {"safe", "standard", "advanced"}:
        raise SystemExit(f"{boundary_id}: invalid candidate tier set")
    safe = by_tier["safe"]
    standard = by_tier["standard"]
    advanced = by_tier["advanced"]
    if safe["execution_kind"] != "deterministic_plan" or safe["side_effects"]:
        raise SystemExit(f"{boundary_id}: safe candidate is not inert")
    if safe["requirements"]["allowed_environments"] != ["local"]:
        raise SystemExit(f"{boundary_id}: safe candidate is not local-only")
    if "production" in standard["requirements"]["allowed_environments"]:
        raise SystemExit(f"{boundary_id}: standard candidate permits production")
    if advanced["execution_kind"] != "injected_adapter":
        raise SystemExit(f"{boundary_id}: advanced candidate is not injected")
    if "production-use" not in advanced["requirements"]["approvals"]:
        raise SystemExit(f"{boundary_id}: advanced candidate lacks production approval")
    if not advanced["requirements"]["evidence"]:
        raise SystemExit(f"{boundary_id}: advanced candidate lacks evidence")
    if not advanced["requirements"]["capabilities"]:
        raise SystemExit(f"{boundary_id}: advanced candidate lacks capability")

asset_root = root / "changes/all-stories-switchable-strategies"
for schema_path in (
    asset_root / "schemas/strategy-profile.v1.schema.json",
    asset_root / "schemas/gate-context.v1.schema.json",
):
    Draft202012Validator.check_schema(json.loads(schema_path.read_bytes()))
profile_schema = json.loads(
    (asset_root / "schemas/strategy-profile.v1.schema.json").read_bytes()
)
profile_validator = Draft202012Validator(profile_schema)
for profile_path in sorted((asset_root / "profiles").glob("*.json")):
    profile_validator.validate(json.loads(profile_path.read_bytes()))

forbidden_import_roots = {"boto3", "openai", "requests", "sqlalchemy"}
for path in sorted((root / "python/raos/strategy_switchboard").glob("*.py")):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = {alias.name.partition(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported = {node.module.partition(".")[0]}
        else:
            continue
        if imported & forbidden_import_roots:
            raise SystemExit(f"provider or framework import in {path}")

print(
    json.dumps(
        {
            "candidate_count": len(candidates),
            "decision_count": len(decisions),
            "profile_count": len(list((asset_root / "profiles").glob("*.json"))),
            "status": "PASS",
            "story_count": len(stories),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY

mapfile -t changed_python < <(
  git diff --name-only "$foundation_sha" | \
    grep -E '^(python|scripts|tests)/.*\.py$' | sort -u
)
test ${#changed_python[@]} -gt 0
"${UV_RUN[@]}" ruff check --no-cache "${changed_python[@]}"
mapfile -t changed_tests < <(
  printf '%s\n' "${changed_python[@]}" | grep '^tests/' | sort -u
)
test ${#changed_tests[@]} -gt 0
"${UV_RUN[@]}" pytest -p no:cacheprovider --import-mode=importlib -q \
  "${changed_tests[@]}"

mapfile -t generators < <(
  git diff --name-only "$foundation_sha" | \
    grep '^scripts/build_.*\.py$' | sort -u || true
)
for generator in "${generators[@]}"; do
  help="$(${UV_RUN[@]} python "$generator" --help 2>&1 || true)"
  if grep -q -- '--check' <<<"$help"; then
    "${UV_RUN[@]}" python "$generator" --check
  fi
done

if [[ -d tests/st0703 ]]; then
  "${UV_RUN[@]}" python scripts/build_st0703_recorded_adapter.py --check
  "${UV_RUN[@]}" python scripts/build_st0703_recorded_adapter.py --check-installed
  "${UV_RUN[@]}" pytest -p no:cacheprovider -q tests/st0703
fi

if [[ -f package.json && -d node_modules ]]; then
  npm run lint --if-present
  npm run typecheck --if-present
  npm run test --if-present
fi

git add -A
git diff --cached --binary >"$RUNNER_TEMP/v4-after.patch"
cmp "$RUNNER_TEMP/v4-before.patch" "$RUNNER_TEMP/v4-after.patch"
git diff --check

patch_sha="$(sha256sum "$RUNNER_TEMP/v4-after.patch" | cut -d' ' -f1)"
"$python_path" - "$patch_sha" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

root = Path.cwd()
catalog = json.loads(
    (root / "changes/all-stories/generated/switchable-strategy-catalog.v1.json").read_bytes()
)
evidence = {
    "catalog_sha256": catalog["catalog_sha256"],
    "candidate_count": catalog["coverage"]["candidate_count"],
    "cli_available": True,
    "external_values_invented": False,
    "formal_tst_claimed": False,
    "foundation_commit": (root / ".foundation-commit.sha").read_text().strip(),
    "human_approval_invented": False,
    "open_decision_count": catalog["coverage"]["open_decision_boundary_count"],
    "open_decisions_resolved": False,
    "overlay_mode": (root / ".combined-overlay.mode").read_text().strip(),
    "overlay_sha256": (root / ".combined-overlay.sha256").read_text().strip(),
    "production_activated": False,
    "profile_count": 3,
    "status": "VALIDATED_IMPLEMENTATION_CANDIDATE",
    "story_count": catalog["coverage"]["story_boundary_count"],
    "strategy_source_commit": (root / ".strategy-source-commit.sha").read_text().strip(),
    "validated_patch_sha256": sys.argv[1],
}
output = root / "changes/all-stories/generated/switchable-strategy-evidence.v1.json"
output.write_text(
    json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    + "\n",
    encoding="utf-8",
)
PY

git config user.name github-actions[bot]
git config user.email 41898282+github-actions[bot]@users.noreply.github.com
git checkout -B "$TARGET_BRANCH"
git add -A
git commit -m 'feat: implement switchable strategies for all RAOS Stories'
target_ref="refs/heads/$TARGET_BRANCH"
remote_sha="$(git ls-remote --heads origin "$target_ref" | awk '{print $1}')"
if [[ -n $remote_sha ]]; then
  git push --force-with-lease="$target_ref:$remote_sha" origin "HEAD:$target_ref"
else
  git push origin "HEAD:$target_ref"
fi
head_sha="$(git rev-parse HEAD)"
gh api "repos/${GITHUB_REPOSITORY}/statuses/${head_sha}" \
  --method POST \
  -f state=success \
  -f context=all-stories/switchable-validation-v4 \
  -f description='All Story alternatives, profiles, CLI, and gates validated' \
  -f target_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"

cat >"$RUNNER_TEMP/v4-pr-body.md" <<'EOF'
## Summary

Implements safe, standard, and advanced switchable alternatives for every canonical RAOS Story and domain-specific alternatives for OD-001 through OD-015.

The implementation includes typed profiles, exact per-boundary overrides, strict JSON Profile and GateContext schemas, an explicit file-driven CLI, approval/evidence/capability gates, deterministic selection records, and injected provider-neutral adapters. Production cannot downgrade to local or Staging candidates.

No Open Decision, credential, production value, human approval, formal TST result, infrastructure apply, publication, release, or Production activation is invented or claimed.

## Validation

The V4 finalizer reconstructs the complete all-Story tree and validates Python 3.14.6 source normalization, deterministic generation, JSON schemas and profiles, canonical coverage, strict mypy, Ruff, every changed Python test, changed generators, TypeScript workspaces, ST-0703, and byte-identical pre/post validation content before publishing this branch.
EOF
existing="$(gh pr list --head "$TARGET_BRANCH" --base main --state open --json number --jq '.[0].number // empty')"
if [[ -n $existing ]]; then
  gh pr edit "$existing" \
    --title 'Implement switchable strategies for all RAOS Stories' \
    --body-file "$RUNNER_TEMP/v4-pr-body.md"
else
  gh pr create --draft --base main --head "$TARGET_BRANCH" \
    --title 'Implement switchable strategies for all RAOS Stories' \
    --body-file "$RUNNER_TEMP/v4-pr-body.md"
fi
gh pr view "$TARGET_BRANCH" --json number,url,headRefOid,isDraft \
  >"$RUNNER_TEMP/v4-final-pr.json"
