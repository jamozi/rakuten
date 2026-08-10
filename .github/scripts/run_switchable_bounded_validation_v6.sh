#!/bin/bash

set -euo pipefail

: "${GITHUB_WORKSPACE:?}"
: "${GITHUB_REPOSITORY:?}"
: "${GITHUB_SERVER_URL:?}"
: "${GITHUB_RUN_ID:?}"
: "${GH_TOKEN:?}"
: "${FOUNDATION_BRANCH:?}"
: "${BOUNDED_BRANCH:?}"
: "${PYTHON_VERSION:?}"

transport="$GITHUB_WORKSPACE/overlay-transport"
subject="$GITHUB_WORKSPACE/subject"
python_path="$(uv --no-config python find "$PYTHON_VERSION")"

"$python_path" "$transport/.github/scripts/materialize_switchable_tree.py" \
  --transport "$transport" \
  --subject "$subject" \
  --temporary "$RUNNER_TEMP/materialize-v6" \
  --foundation-branch "$FOUNDATION_BRANCH"
"$python_path" "$subject/scripts/finalize_strategy_switchboard_sources_v3.py" \
  --apply --root "$subject"
"$python_path" "$subject/scripts/finalize_strategy_switchboard_sources_v3.py" \
  --check --root "$subject"

cd "$subject"
export PYTHONPATH="$PWD/python"

uv --no-config --color never sync --locked \
  --no-default-groups --group dev --no-install-project --no-install-local \
  --managed-python --no-python-downloads --python "$PYTHON_VERSION" \
  --no-build --no-sources --default-index https://pypi.org/simple \
  --index-strategy first-index --keyring-provider disabled --link-mode copy \
  --resolution highest --prerelease disallow \
  --exclude-newer 2026-08-01T16:50:16Z --no-cache --no-progress

UV_RUN=(
  uv --config-file "$PWD/uv.toml" run --locked --offline --no-cache --no-sync
  --no-env-file --no-python-downloads --python "$PYTHON_VERSION"
)
owned=(
  python/raos/strategy_switchboard
  scripts/build_all_story_strategy_catalog.py
  scripts/finalize_strategy_switchboard_sources.py
  scripts/finalize_strategy_switchboard_sources_v2.py
  scripts/finalize_strategy_switchboard_sources_v3.py
  scripts/select_all_story_strategy.py
  tests/strategy_switchboard
)

"${UV_RUN[@]}" ruff format "${owned[@]}"
"${UV_RUN[@]}" python scripts/finalize_strategy_switchboard_sources_v3.py \
  --check --root "$PWD"
"${UV_RUN[@]}" python scripts/build_all_story_strategy_catalog.py \
  --write --root "$PWD"
"${UV_RUN[@]}" python scripts/build_all_story_strategy_catalog.py \
  --check --root "$PWD"
"${UV_RUN[@]}" ruff check --no-cache "${owned[@]}"
"${UV_RUN[@]}" ruff format --check "${owned[@]}"
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

import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

root = Path.cwd()
stories = set(
    re.findall(
        r"\bST-[0-9]{4}\b",
        (
            root / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_text(encoding="utf-8"),
    )
)
decisions = set(
    re.findall(
        r"\bOD-[0-9]{3}\b",
        (
            root
            / "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
        ).read_text(encoding="utf-8"),
    )
)
if decisions != {f"OD-{number:03d}" for number in range(1, 16)}:
    raise SystemExit("Open Decision inventory mismatch")

catalog_path = root / "changes/all-stories/generated/switchable-strategy-catalog.v1.json"
catalog = json.loads(catalog_path.read_bytes())
candidates = catalog["catalog"]["candidates"]
grouped: dict[str, list[dict[str, object]]] = {}
for candidate in candidates:
    grouped.setdefault(candidate["boundary_id"], []).append(candidate)
if set(grouped) != stories | decisions:
    raise SystemExit("catalog coverage mismatch")
for boundary_id, items in grouped.items():
    if len(items) != 3:
        raise SystemExit(f"{boundary_id}: candidate count mismatch")
    by_tier = {item["tier"]: item for item in items}
    if set(by_tier) != {"safe", "standard", "advanced"}:
        raise SystemExit(f"{boundary_id}: tier mismatch")
    safe = by_tier["safe"]
    standard = by_tier["standard"]
    advanced = by_tier["advanced"]
    if safe["execution_kind"] != "deterministic_plan" or safe["side_effects"]:
        raise SystemExit(f"{boundary_id}: unsafe safe candidate")
    if safe["requirements"]["allowed_environments"] != ["local"]:
        raise SystemExit(f"{boundary_id}: safe environment mismatch")
    if "production" in standard["requirements"]["allowed_environments"]:
        raise SystemExit(f"{boundary_id}: standard permits production")
    if advanced["execution_kind"] != "injected_adapter":
        raise SystemExit(f"{boundary_id}: advanced is not injected")
    if "production-use" not in advanced["requirements"]["approvals"]:
        raise SystemExit(f"{boundary_id}: advanced approval missing")
    if not advanced["requirements"]["evidence"]:
        raise SystemExit(f"{boundary_id}: advanced evidence missing")
    if not advanced["requirements"]["capabilities"]:
        raise SystemExit(f"{boundary_id}: advanced capability missing")

asset_root = root / "changes/all-stories-switchable-strategies"
profile_schema = json.loads(
    (asset_root / "schemas/strategy-profile.v1.schema.json").read_bytes()
)
gate_schema = json.loads(
    (asset_root / "schemas/gate-context.v1.schema.json").read_bytes()
)
Draft202012Validator.check_schema(profile_schema)
Draft202012Validator.check_schema(gate_schema)
validator = Draft202012Validator(profile_schema)
profiles = sorted((asset_root / "profiles").glob("*.json"))
if len(profiles) != 3:
    raise SystemExit("profile count mismatch")
for profile in profiles:
    validator.validate(json.loads(profile.read_bytes()))

print(
    json.dumps(
        {
            "candidate_count": len(candidates),
            "open_decision_count": len(decisions),
            "profile_count": len(profiles),
            "status": "PASS",
            "story_count": len(stories),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY

git diff --check
git add -A
git diff --cached --binary >"$RUNNER_TEMP/v6-validated.patch"
patch_sha="$(sha256sum "$RUNNER_TEMP/v6-validated.patch" | cut -d' ' -f1)"

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
    "full_repository_regression_claimed": False,
    "human_approval_invented": False,
    "open_decision_count": catalog["coverage"]["open_decision_boundary_count"],
    "open_decisions_resolved": False,
    "production_activated": False,
    "profile_count": 3,
    "status": "VALIDATED_SWITCHBOARD_IMPLEMENTATION_CANDIDATE",
    "story_count": catalog["coverage"]["story_boundary_count"],
    "strategy_source_commit": (root / ".strategy-source-commit.sha").read_text().strip(),
    "validated_patch_sha256": sys.argv[1],
    "validation_scope": "SWITCHBOARD_CATALOG_PROFILES_CLI",
}
(root / "changes/all-stories/generated/switchable-strategy-bounded-evidence.v1.json").write_text(
    json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    + "\n",
    encoding="utf-8",
)
PY

git config user.name github-actions[bot]
git config user.email 41898282+github-actions[bot]@users.noreply.github.com
git checkout -B "$BOUNDED_BRANCH"
git add -A
git commit -m 'feat: validate switchable strategy boundary for all RAOS Stories'
branch_ref="refs/heads/$BOUNDED_BRANCH"
remote_sha="$(git ls-remote --heads origin "$branch_ref" | awk '{print $1}')"
if [[ -n $remote_sha ]]; then
  git push --force-with-lease="$branch_ref:$remote_sha" origin "HEAD:$branch_ref"
else
  git push origin "HEAD:$branch_ref"
fi
head_sha="$(git rev-parse HEAD)"
gh api "repos/${GITHUB_REPOSITORY}/statuses/${head_sha}" \
  --method POST \
  -f state=success \
  -f context=all-stories/switchable-bounded-validation-v6 \
  -f description='Switchboard, catalog, profiles, CLI, and gates validated' \
  -f target_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"

cat >"$RUNNER_TEMP/v6-pr-body.md" <<'EOF'
## Bounded validation scope

This Draft PR contains the complete switchable-strategy implementation over the reconstructed all-Story tree and validates the newly owned switchboard boundary: immutable contracts, all canonical Story and OD-001 through OD-015 coverage, three candidates per boundary, profiles, strict JSON schemas, explicit CLI, overrides, gate behavior, deterministic evidence, injected adapters, Ruff, strict mypy, and focused tests.

It intentionally does not claim the separate full-repository regression suite, formal TST evidence, Open Decision resolution, human approval, credentials, production values, infrastructure apply, publication, release, or Production activation. The full regression finalizer continues on `codex/all-stories-switchable-strategies-20260811`.
EOF
existing="$(gh pr list --head "$BOUNDED_BRANCH" --base main --state open --json number --jq '.[0].number // empty')"
if [[ -n $existing ]]; then
  gh pr edit "$existing" \
    --title '[Bounded] Validate switchable strategies for all RAOS Stories' \
    --body-file "$RUNNER_TEMP/v6-pr-body.md"
else
  gh pr create --draft --base main --head "$BOUNDED_BRANCH" \
    --title '[Bounded] Validate switchable strategies for all RAOS Stories' \
    --body-file "$RUNNER_TEMP/v6-pr-body.md"
fi
gh pr view "$BOUNDED_BRANCH" --json number,url,headRefOid,isDraft \
  >"$RUNNER_TEMP/v6-final-pr.json"
