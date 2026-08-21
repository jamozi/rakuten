"""Static contract checks for the ST-0106 base CI workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/ci.yml"
WORKFLOW_TEXT = WORKFLOW_PATH.read_text(encoding="utf-8")
WORKFLOW: dict[str, Any] = yaml.load(WORKFLOW_TEXT, Loader=yaml.BaseLoader)
REVIEWED_FINDINGS_RELATIVE_PATH = (
    "changes/st-0106/contracts/reviewed-secret-findings.v1.yaml"
)
REVIEWED_FINDINGS_PATH = REPOSITORY_ROOT / REVIEWED_FINDINGS_RELATIVE_PATH
REVIEWED_FINDINGS_APPROVAL_PATH = (
    REPOSITORY_ROOT / "changes/st-0106/REVIEWED-SECRET-FINDINGS-APPROVAL-v1.yaml"
)
EXPECTED_REVIEWED_FINDINGS_BYTES = 46295
EXPECTED_REVIEWED_FINDINGS_SHA256 = (
    "1038cf6ef81da0acab528cf8206086646b6e003f5ac0ceed4f2e4b994827bcc7"
)
EXPECTED_REVIEWED_FINDINGS_APPROVAL_BYTES = 5524
EXPECTED_REVIEWED_FINDINGS_APPROVAL_SHA256 = (
    "b683ae3b3b7312bd4ce04fe2c796f1157542f72c1b1bca79919a71b3a7c1acd9"
)
V2_REVIEWED_FINDINGS_RELATIVE_PATH = (
    "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
)
V2_REVIEWED_FINDINGS_PATH = REPOSITORY_ROOT / V2_REVIEWED_FINDINGS_RELATIVE_PATH
V2_RECONCILIATION_RELATIVE_PATH = (
    "changes/st-0106/REVIEWED-SECRET-FINDINGS-RECONCILIATION-v2.yaml"
)
V2_RECONCILIATION_PATH = REPOSITORY_ROOT / V2_RECONCILIATION_RELATIVE_PATH
V2_ACTIVATION_RELATIVE_PATH = (
    "changes/st-0106/REVIEWED-SECRET-FINDINGS-ACTIVATION-v2.yaml"
)
V2_ACTIVATION_PATH = REPOSITORY_ROOT / V2_ACTIVATION_RELATIVE_PATH
V2_INVENTORY_RELATIVE_PATH = "changes/st-0106/contracts/origin-ref-inventory.v2.txt"
V2_INVENTORY_PATH = REPOSITORY_ROOT / V2_INVENTORY_RELATIVE_PATH
ACTIVATION_INVENTORY_RELATIVE_PATH = (
    "changes/st-0106/contracts/origin-ref-inventory.activation-v2.txt"
)
ACTIVATION_INVENTORY_PATH = REPOSITORY_ROOT / ACTIVATION_INVENTORY_RELATIVE_PATH
EXPECTED_V2_REVIEWED_FINDINGS_BYTES = 59769
EXPECTED_V2_REVIEWED_FINDINGS_SHA256 = (
    "667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b"
)
EXPECTED_V2_RECONCILIATION_BYTES = 9109
EXPECTED_V2_RECONCILIATION_SHA256 = (
    "9cbe56b54eee9218e007d2c5f1b88d2a82bf58e8510ee7ab1c212610db39c3e7"
)
EXPECTED_V2_ACTIVATION_BYTES = 8878
EXPECTED_V2_ACTIVATION_SHA256 = (
    "b5293cbfeec9b75f861155770ea1b7e8d429bbe5ec61910afbea86429a9bc2bb"
)
EXPECTED_V2_INVENTORY_BYTES = 8436
EXPECTED_V2_INVENTORY_SHA256 = (
    "fa244e651d3bf6aba5c494372b4963bb5420ac68ac998d1cb47a2bd0eed11c0c"
)
EXPECTED_V2_INVENTORY_ENTRIES_SHA256 = (
    "92d352e79d8b13d611c0689d2062a747390a38856208160e429f49f8af28b802"
)
EXPECTED_ACTIVATION_INVENTORY_BYTES = 2729
EXPECTED_ACTIVATION_INVENTORY_SHA256 = (
    "45d79e7741d9f9c540ecd9d87533e6b9d849115a48ddba991326efb2ef48d369"
)
EXPECTED_ACTIVATION_INVENTORY_ENTRIES_SHA256 = (
    "be8ace03c736ca395b1cfbf5d7adc35fea8c654094cf315556f516eb508bb790"
)
EXPECTED_PRE_ACTIVATION_WORKFLOW_BYTES = 20122
EXPECTED_PRE_ACTIVATION_WORKFLOW_SHA256 = (
    "06872527682949b0fdfbb3a1e116fae205cd758f58fb5c233ab075075df0c647"
)
EXPECTED_POST_ACTIVATION_WORKFLOW_BYTES = 20122
EXPECTED_POST_ACTIVATION_WORKFLOW_SHA256 = (
    "790af484fea8aaa38f040de7bd51dbb729bd643d255847a23310aaa37462510f"
)
EXPECTED_FROZEN_SECURITY_IMPLEMENTATION = {
    "scripts/scan_secrets.py": (
        43062,
        "3af1b7c468cd5eb55016f3a9199204dcac11ab8b1cbffee831876408d7b57970",
    ),
    "scripts/run_network_denied.sh": (
        6688,
        "171e9be2a368473dc855cf5bf996df14762766791f06569fd70e7ab90ebe0efd",
    ),
    "scripts/ci_job.sh": (
        7456,
        "6f93f7ceeacf1ed69158adc6d0e9176ec658cd1a71d6db05fb90d84a1570a067",
    ),
}
EXPECTED_ACTIONS = {
    "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-node": "249970729cb0ef3589644e2896645e5dc5ba9c38",
    "astral-sh/setup-uv": "c771a70e6277c0a99b617c7a806ffedaca235ff9",
}


def action_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "uses" in step]


def run_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "run" in step]


def named_run_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in run_steps(job) if step["name"] == name]
    assert len(matches) == 1
    return matches[0]


def action_step(job: dict[str, Any], repository: str) -> dict[str, Any]:
    matches = [
        step for step in action_steps(job) if step["uses"].startswith(f"{repository}@")
    ]
    assert len(matches) == 1
    return matches[0]


def repository_path_from_uri(uri: str) -> Path:
    assert uri.startswith("repo://")
    relative = Path(uri.removeprefix("repo://"))
    assert not relative.is_absolute()
    assert relative.parts
    assert all(part not in {"", ".", ".."} for part in relative.parts)
    return REPOSITORY_ROOT / relative


def reviewed_finding_key(entry: dict[str, Any]) -> tuple[str, str, int]:
    return (
        entry["scope"],
        entry["exact_source_identifier"],
        entry["exact_line_number"],
    )


def test_workflow_uses_unprivileged_pr_and_full_integration_events() -> None:
    assert set(WORKFLOW) == {
        "name",
        "on",
        "permissions",
        "concurrency",
        "defaults",
        "jobs",
    }
    assert WORKFLOW["on"] == {
        "pull_request": "",
        "push": {"branches": ["main"]},
        "schedule": [{"cron": "17 18 * * *"}],
        "workflow_dispatch": "",
    }
    assert "pull_request_target" not in WORKFLOW_TEXT
    assert "workflow_run" not in WORKFLOW_TEXT
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["concurrency"] == {
        "group": (
            "base-ci-${{ github.event_name == 'pull_request' && "
            "format('pr-{0}', github.event.pull_request.number) || "
            "github.event_name == 'push' && format('push-{0}', github.ref) || "
            "format('{0}-{1}', github.event_name, github.run_id) }}"
        ),
        "cancel-in-progress": "true",
    }


def test_concurrency_groups_separate_pr_push_schedule_and_manual_runs() -> None:
    group = WORKFLOW["concurrency"]["group"]
    assert "format('pr-{0}', github.event.pull_request.number)" in group
    assert "format('push-{0}', github.ref)" in group
    assert "format('{0}-{1}', github.event_name, github.run_id)" in group
    assert "github.event.pull_request.number || github.ref" not in group
    assert WORKFLOW["defaults"] == {"run": {"shell": "bash"}}


def test_jobs_are_bounded_and_have_no_privileged_surface() -> None:
    jobs = WORKFLOW["jobs"]
    assert set(jobs) == {
        "classify",
        "static",
        "unit",
        "contracts",
        "database",
        "storage",
        "secrets",
    }
    assert set(jobs["classify"]) == {
        "name",
        "runs-on",
        "timeout-minutes",
        "outputs",
        "steps",
    }
    for job_id, job in jobs.items():
        if job_id != "classify":
            assert set(job) == {
                "name",
                "needs",
                "if",
                "runs-on",
                "timeout-minutes",
                "steps",
            }
            assert job["needs"] == "classify"
            assert job["if"] == "${{ always() }}"
            assert (
                named_run_step(job, "Require successful CI classification")["run"]
                == "test '${{ needs.classify.result }}' = success"
            )
        assert job["runs-on"] == "ubuntu-24.04"
        assert 1 <= int(job["timeout-minutes"]) <= 30
        for step in job["steps"]:
            assert set(step).isdisjoint({"continue-on-error", "env"})
    lowered = WORKFLOW_TEXT.lower()
    assert "${{ secrets." not in lowered
    assert "id-token" not in lowered
    assert "write-all" not in lowered
    assert not re.search(r"(?m)^\s+[a-z-]+:\s+write\s*$", WORKFLOW_TEXT)


def test_classifier_controls_every_required_context_fail_closed() -> None:
    jobs = WORKFLOW["jobs"]
    classifier = jobs["classify"]
    assert classifier["outputs"] == {
        "static": "${{ steps.scope.outputs.static }}",
        "static_mode": "${{ steps.scope.outputs.static_mode }}",
        "unit": "${{ steps.scope.outputs.unit }}",
        "unit_mode": "${{ steps.scope.outputs.unit_mode }}",
        "story_suite": "${{ steps.scope.outputs.story_suite }}",
        "contracts": "${{ steps.scope.outputs.contracts }}",
        "database": "${{ steps.scope.outputs.database }}",
        "storage": "${{ steps.scope.outputs.storage }}",
        "secrets": "${{ steps.scope.outputs.secrets }}",
        "full_required": "${{ steps.scope.outputs.full_required }}",
        "classification_json": "${{ steps.scope.outputs.classification_json }}",
    }
    classify_step = named_run_step(classifier, "Classify affected jobs")
    assert classify_step["id"] == "scope"
    for token in (
        "/usr/bin/python3 -I scripts/classify_ci_scope.py",
        "--event pull_request",
        "github.event.pull_request.base.sha",
        "github.event.pull_request.head.sha",
        '--event "$GITHUB_EVENT_NAME"',
        '--github-output "$GITHUB_OUTPUT"',
    ):
        assert token in classify_step["run"]

    expected_names = {
        "static": "Static",
        "unit": "Unit",
        "contracts": "Contracts",
        "database": "Database",
        "storage": "Storage",
        "secrets": "Secrets",
    }
    for job_id, display_name in expected_names.items():
        job = jobs[job_id]
        assert job["name"] == display_name
        assert job["needs"] == "classify"
        assert job["if"] == "${{ always() }}"
        assert (
            named_run_step(job, "Require successful CI classification")["run"]
            == "test '${{ needs.classify.result }}' = success"
        )
        not_applicable = named_run_step(job, "Record not applicable")
        assert "needs.classify.result == 'success'" in not_applicable["if"]
        assert f"needs.classify.outputs.{job_id} == 'false'" in not_applicable["if"]


def test_every_external_action_is_full_sha_pinned() -> None:
    observed: dict[str, set[str]] = {}
    for job in WORKFLOW["jobs"].values():
        for step in action_steps(job):
            repository, separator, revision = step["uses"].partition("@")
            assert separator == "@"
            assert re.fullmatch(r"[0-9a-f]{40}", revision)
            observed.setdefault(repository, set()).add(revision)
    assert observed == {
        repository: {revision} for repository, revision in EXPECTED_ACTIONS.items()
    }


def test_checkout_never_persists_credentials_and_history_is_minimal() -> None:
    for job_id, job in WORKFLOW["jobs"].items():
        checkout = action_step(job, "actions/checkout")
        expected_depth = "0" if job_id in {"classify", "static", "secrets"} else "1"
        assert checkout["with"] == {
            "fetch-depth": expected_depth,
            "persist-credentials": "false",
            "show-progress": "false",
        }


def test_setup_and_hydration_are_exact_source_constrained_and_cache_isolated() -> None:
    for job_id in ("static", "unit", "contracts"):
        job = WORKFLOW["jobs"][job_id]
        setup_uv = action_step(job, "astral-sh/setup-uv")
        setup_node = action_step(job, "actions/setup-node")
        assert setup_uv["with"] == {
            "version": "0.12.1",
            "enable-cache": "false",
        }
        assert setup_node["with"] == {
            "node-version": "24.18.1",
            "package-manager-cache": "false",
            "check-latest": "false",
        }
        cache_arguments = (
            '  --uv-cache "$RUNNER_TEMP/raos-unit-uv-cache" \\\n'
            '  --runner-temp "$RUNNER_TEMP" \\\n'
            if job_id == "unit"
            else ""
        )
        reproduce_command = (
            "set -euo pipefail\n"
            'node_path="$(command -v node)"\n'
            'node_prefix="$(dirname "$(dirname "$node_path")")"\n'
            'scripts/run_network_denied.sh --home "$HOME" -- \\\n'
            '  "$GITHUB_WORKSPACE/scripts/ci_job.sh" \\\n'
            '  --uv "$(command -v uv)" \\\n'
            '  --node "$node_path" \\\n'
            '  --npm-cli "$node_prefix/lib/node_modules/npm/bin/npm-cli.js" \\\n'
            f"{cache_arguments}"
            f"  {job_id}\n"
        )
        observed_runs = {step["name"]: step["run"] for step in run_steps(job)}
        required_heavy_steps = {
            "Validate dependency metadata without network",
            "Prove npm lock closure without network",
            "Install exact Python without repository code",
            "Hydrate source-constrained locked dependencies",
            f"Reproduce {job_id} job",
        }
        assert required_heavy_steps <= set(observed_runs)
        assert "Require successful CI classification" in observed_runs
        assert "Record not applicable" in observed_runs
        if job_id == "static":
            assert "Run lightweight static check" in observed_runs
            expected_condition = "${{ needs.classify.outputs.static_mode == 'full' }}"
        else:
            expected_condition = (
                "${{ needs.classify.outputs." + job_id + " == 'true' }}"
            )
        for step in job["steps"]:
            if step["name"] in required_heavy_steps or step["name"].startswith(
                "Install exact"
            ):
                if step["name"] == "Reproduce unit job":
                    assert step["if"] == (
                        "${{ needs.classify.outputs.unit_mode == 'full' }}"
                    )
                else:
                    assert step["if"] == expected_condition
        assert observed_runs["Validate dependency metadata without network"] == (
            'scripts/run_network_denied.sh --home "$HOME" -- '
            "/usr/bin/python3 -I scripts/validate_ci_hydration.py"
        )

        python_install = observed_runs["Install exact Python without repository code"]
        assert "env -i PATH=/usr/bin:/bin" in python_install
        assert '"$uv_path" --no-config --color never python install' in python_install
        for token in (
            "--managed-python",
            "--no-bin",
            "--no-registry",
            "--no-cache",
            "--no-progress 3.14.6",
        ):
            assert token in python_install

        npm_preflight = observed_runs["Prove npm lock closure without network"]
        for token in (
            'preflight_root="$(mktemp -d "$RUNNER_TEMP/raos-npm-preflight.XXXXXX")"',
            'cp -- package.json package-lock.json "$preflight_workspace/"',
            "apps/web/package.json",
            "packages/web-contracts/package.json",
            "packages/web-ui/package.json",
            'scripts/run_network_denied.sh --home "$preflight_home" --',
            '/usr/bin/env -i --chdir="$preflight_workspace"',
            '"$node_path" "$npm_cli"',
            '--cache "$preflight_cache" --registry https://registry.npmjs.org/',
            "--replace-registry-host=always",
            "--ignore-scripts=true",
            "--package-lock=true --save=false",
            "--install-links=true --legacy-peer-deps=false --strict-peer-deps=true",
            "--prefer-dedupe=true --omit-lockfile-registry-resolved=false",
            "--provenance=false --loglevel=error ci --dry-run --offline",
            'test ! -e "$preflight_workspace/node_modules"',
            'sha256sum "$preflight_workspace/package-lock.json"',
        ):
            assert token in npm_preflight
        assert npm_preflight.count("scripts/run_network_denied.sh") == 1
        assert npm_preflight.count("env -i") == 1
        assert npm_preflight.count("sha256sum") == 2
        for forbidden in (
            "ci_job.sh",
            "Makefile",
            "make ",
            "npm run",
            "uv run",
            "python_toolchain",
            "node_toolchain",
        ):
            assert forbidden not in npm_preflight

        hydration = observed_runs["Hydrate source-constrained locked dependencies"]
        assert hydration.count("env -i PATH=/usr/bin:/bin") == 2
        uv_sync_prefix = (
            '"$uv_path" --no-config --color never --cache-dir "$uv_cache_dir" '
            "\\\n  sync --locked"
            if job_id == "unit"
            else '"$uv_path" --no-config --color never sync --locked'
        )
        for token in (
            uv_sync_prefix,
            "--no-default-groups --group dev",
            "--no-install-project --no-install-local",
            "--managed-python --no-python-downloads --python 3.14.6",
            "--no-build --no-sources --default-index https://pypi.org/simple",
            "--index-strategy first-index --keyring-provider disabled",
            "--exclude-newer 2026-08-01T16:50:16Z",
            '"$node_path" "$npm_cli"',
            "--registry https://registry.npmjs.org/",
            "--replace-registry-host=always",
            "--ignore-scripts=true",
            "--strict-peer-deps=true",
            "--provenance=false ci",
        ):
            assert token in hydration
        for forbidden in (
            "scripts/",
            "Makefile",
            "make ",
            "npm run",
            "uv run",
            "python_toolchain",
            "node_toolchain",
        ):
            assert forbidden not in python_install
            assert forbidden not in hydration
        if job_id == "unit":
            for token in (
                "umask 077",
                'uv_cache_dir="$RUNNER_TEMP/raos-unit-uv-cache"',
                'test ! -e "$uv_cache_dir"',
                'test ! -L "$uv_cache_dir"',
                'mkdir --mode=0700 -- "$uv_cache_dir"',
                'npm_cache_dir="$GITHUB_WORKSPACE/.npm-cache"',
                'test ! -e "$npm_cache_dir"',
                'test ! -L "$npm_cache_dir"',
                'mkdir --mode=0700 -- "$npm_cache_dir"',
                "stat --format='%u:%g:%a' -- \"$npm_cache_dir\"",
                '"$(id -u):$(id -g):700"',
                '--cache "$npm_cache_dir"',
            ):
                assert token in hydration
            assert hydration.count('npm_cache_dir="$GITHUB_WORKSPACE/.npm-cache"') == 1
            assert "$RUNNER_TEMP/raos-npm-cache" not in hydration
            npm_cache_guard_order = (
                'npm_cache_dir="$GITHUB_WORKSPACE/.npm-cache"',
                'test ! -e "$npm_cache_dir"',
                'test ! -L "$npm_cache_dir"',
                'mkdir --mode=0700 -- "$npm_cache_dir"',
                "stat --format='%u:%g:%a' -- \"$npm_cache_dir\"",
                '--cache "$npm_cache_dir"',
            )
            assert [
                hydration.index(token) for token in npm_cache_guard_order
            ] == sorted(hydration.index(token) for token in npm_cache_guard_order)
            assert "--no-cache --no-progress" not in hydration
        else:
            assert "raos-unit-uv-cache" not in hydration
            assert "--cache-dir" not in hydration
            assert "--no-cache --no-progress" in hydration
            assert (
                hydration.count(
                    'npm_cache_dir="$(mktemp -d "$RUNNER_TEMP/raos-npm-cache.XXXXXX")"'
                )
                == 1
            )
            assert "$GITHUB_WORKSPACE/.npm-cache" not in hydration
            for token in (
                'test ! -e "$npm_cache_dir"',
                'test ! -L "$npm_cache_dir"',
                'mkdir --mode=0700 -- "$npm_cache_dir"',
                "stat --format='%u:%g:%a'",
            ):
                assert token not in hydration
        assert observed_runs[f"Reproduce {job_id} job"] == reproduce_command
        if job_id == "unit":
            focused = named_run_step(job, "Reproduce focused Story unit job")
            assert focused["if"] == (
                "${{ needs.classify.outputs.unit_mode == 'focused' }}"
            )
            for token in (
                "needs.classify.outputs.story_suite",
                "^tests/st[0-9]{4}$",
                "-p no:cacheprovider -q -m 'not raos_owner_private'",
                "node_modules/vitest/vitest.mjs",
                "scripts/run_network_denied.sh",
            ):
                assert token in focused["run"]

        step_names = [step["name"] for step in job["steps"]]
        assert step_names.index("Validate dependency metadata without network") < (
            step_names.index("Install exact uv")
        )
        assert step_names.index("Install exact Node") < step_names.index(
            "Prove npm lock closure without network"
        )
        assert step_names.index("Prove npm lock closure without network") < (
            step_names.index("Hydrate source-constrained locked dependencies")
        )
        assert step_names.index("Hydrate source-constrained locked dependencies") < (
            step_names.index(f"Reproduce {job_id} job")
        )


def test_unit_hydrates_the_exact_npm_cache_consumed_by_st0103() -> None:
    unit = WORKFLOW["jobs"]["unit"]
    observed_runs = {step["name"]: step["run"] for step in run_steps(unit)}
    hydration = observed_runs["Hydrate source-constrained locked dependencies"]
    reproduction = observed_runs["Reproduce unit job"]
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert 'npm_cache_dir="$GITHUB_WORKSPACE/.npm-cache"' in hydration
    assert '--cache "$npm_cache_dir"' in hydration
    assert 'scripts/run_network_denied.sh --home "$HOME" --' in reproduction
    for token in (
        "override NPM_CACHE := $(RAOS_REPOSITORY_ROOT)/.npm-cache",
        'NPM_CONFIG_CACHE="$(NPM_CACHE)"',
        '--cache "$(NPM_CACHE)"',
        "node-sync-offline: node-storage-check",
        "tests/st0103",
    ):
        assert token in makefile


def test_reviewed_findings_ledger_has_exact_detached_activation_approval() -> None:
    ledger_bytes = REVIEWED_FINDINGS_PATH.read_bytes()
    assert len(ledger_bytes) == EXPECTED_REVIEWED_FINDINGS_BYTES
    assert hashlib.sha256(ledger_bytes).hexdigest() == EXPECTED_REVIEWED_FINDINGS_SHA256
    ledger = json.loads(ledger_bytes)
    assert set(ledger) == {"version", "status", "rule_id", "entries"}
    assert ledger["version"] == 1
    assert ledger["status"] == "UNAPPROVED_CANDIDATE"
    assert ledger["rule_id"] == "GENERIC_CREDENTIAL"
    assert len(ledger["entries"]) == 89
    assert sum(entry["scope"] == "worktree" for entry in ledger["entries"]) == 31
    assert sum(entry["scope"] == "git_history" for entry in ledger["entries"]) == 58

    approval_bytes = REVIEWED_FINDINGS_APPROVAL_PATH.read_bytes()
    assert len(approval_bytes) == EXPECTED_REVIEWED_FINDINGS_APPROVAL_BYTES
    assert (
        hashlib.sha256(approval_bytes).hexdigest()
        == EXPECTED_REVIEWED_FINDINGS_APPROVAL_SHA256
    )
    document = yaml.safe_load(approval_bytes)
    assert set(document) == {"REVIEWED_SECRET_FINDINGS_APPROVAL_V1"}
    approval = document["REVIEWED_SECRET_FINDINGS_APPROVAL_V1"]
    assert approval["ledger_uri"] == f"repo://{REVIEWED_FINDINGS_RELATIVE_PATH}"
    assert approval["ledger_bytes"] == EXPECTED_REVIEWED_FINDINGS_BYTES
    assert approval["ledger_sha256"] == EXPECTED_REVIEWED_FINDINGS_SHA256
    assert approval["ledger_version"] == 1
    assert approval["ledger_internal_status"] == "UNAPPROVED_CANDIDATE"
    assert approval["reviewed_entry_count"] == 89
    assert approval["reviewed_scope_counts"] == {"worktree": 31, "git_history": 58}
    assert approval["reviewed_rule_id"] == "GENERIC_CREDENTIAL"
    assert approval["status"] == "OWNER_APPROVED_FOR_EXACT_CI_REFERENCE_ACTIVATION"
    assert approval["approved_by"] == "repository_owner:jamozi"
    assert approval["observed_at"] == "2026-08-14T19:16:10Z"
    assert approval["message_authored_at"] == "NOT_SUPPLIED"
    visible = approval["visible_user_rendering"].encode("utf-8")
    normalized = approval["normalized_semantic_statement"].encode("utf-8")
    assert len(visible) == approval["visible_user_rendering_utf8_bytes"] == 351
    assert (
        hashlib.sha256(visible).hexdigest()
        == approval["visible_user_rendering_sha256"]
        == "61fafd8cbf9b4b0b2b2571c5aa5e14e1e5d7206f05f48854670c0a6b6a97f478"
    )
    assert (
        len(normalized) == approval["normalized_semantic_statement_utf8_bytes"] == 340
    )
    assert (
        hashlib.sha256(normalized).hexdigest()
        == approval["normalized_semantic_statement_sha256"]
        == "99a3e6259cd40b2e9ceefd8620c208905bd2dc3f4a9ebf3a344ce02dc6fd2222"
    )
    assert approval["normalization"] == {
        "display_markdown_quote_markers_removed": True,
        "display_line_wrapping_joined": True,
        "other_text_change": False,
        "semantic_delta": "NONE",
    }
    assert approval["prerequisite_authority"] == {
        "handoff_uri": "repo://changes/st-0106/DESIGN_HANDOFF_V1_ST0106_CI_CACHE_AND_REVIEWED_SECRET_FINDINGS_V2.yaml",
        "handoff_bytes": 17952,
        "handoff_sha256": "88a6d97cd70728c860ed7ab1b600d0c8cc69239a48a43d5c1b0c82919ff86e0c",
        "detached_handoff_approval_uri": "repo://changes/st-0106/DESIGN-HANDOFF-APPROVAL-CI-CACHE-AND-REVIEWED-SECRET-FINDINGS-v2.yaml",
        "detached_handoff_approval_bytes": 4179,
        "detached_handoff_approval_sha256": "8cd1fb6ff25e3d33a4b96d790512162e8b18ff2f1a9ac3cf29e352d759be4d49",
        "proposal_uri": "repo://changes/st-0106/CI-CACHE-AND-REVIEWED-SECRET-FINDINGS-V2-PROPOSAL.md",
        "proposal_bytes": 4366,
        "proposal_sha256": "3b5d2e17062b458934ac99766f78f05aa43c02150042e10061ba0a2081526966",
        "decision_id": "ST0106-CI-CACHE-AND-REVIEWED-SECRET-FINDINGS-V2",
        "handoff_open_decisions": [],
    }
    review = approval["sanitized_per_location_review"]
    assert review["every_ledger_entry_individually_reviewed"] is True
    assert review["total_reviewed"] == 89
    assert review["worktree_reviewed"] == 31
    assert review["git_history_reviewed"] == 58
    assert review["generic_credential_reviewed"] == 89
    assert review["specific_rule_findings_reviewed"] == {
        "aws_access_key": 0,
        "github_token": 0,
        "openai_key": 0,
        "private_key": 0,
    }
    assert review["plausible_real_credential_incident_candidate"] == "NONE_IDENTIFIED"
    for key in (
        "matched_secret_values_observed_during_review",
        "matched_secret_values_persisted",
        "ledger_contains_matched_secret_values",
        "review_output_contains_matched_secret_values",
    ):
        assert review[key] is False
    assert approval["open_decisions"] == []
    boundaries = approval["boundaries"]
    assert boundaries["exact_local_workflow_reference_activation"] == "AUTHORIZED"
    for key in (
        "ledger_content_mutation",
        "scanner_or_wrapper_mutation",
        "st_0102_mutation",
        "network_isolation_mutation",
        "authority_handoff_proposal_or_approval_mutation",
        "st_0107_or_downstream_provenance_mutation",
        "status_or_canonical_mutation",
        "formal_evidence_or_formal_authority",
        "staging_or_commit",
        "push_or_pull_request",
        "merge",
        "external_write",
        "release",
        "production",
    ):
        assert boundaries[key] == "NOT_AUTHORIZED"
    assert boundaries["hosted_ci"] == "NOT_EXECUTED"
    assert boundaries["formal_tst_001"] == "NOT_EXECUTED"
    assert boundaries["formal_tst_002"] == "NOT_EXECUTED"


def test_current_main_v2_candidate_keeps_four_unreviewed_bindings_fail_closed() -> None:
    ledger_bytes = V2_REVIEWED_FINDINGS_PATH.read_bytes()
    assert len(ledger_bytes) == EXPECTED_V2_REVIEWED_FINDINGS_BYTES
    assert (
        hashlib.sha256(ledger_bytes).hexdigest() == EXPECTED_V2_REVIEWED_FINDINGS_SHA256
    )
    ledger = json.loads(ledger_bytes)
    assert set(ledger) == {"version", "status", "rule_id", "entries"}
    assert ledger["version"] == 1
    assert ledger["status"] == "UNAPPROVED_CANDIDATE"
    assert ledger["rule_id"] == "GENERIC_CREDENTIAL"
    entries = ledger["entries"]
    assert len(entries) == 115
    assert sum(entry["scope"] == "worktree" for entry in entries) == 31
    assert sum(entry["scope"] == "git_history" for entry in entries) == 84
    entry_keys = [reviewed_finding_key(entry) for entry in entries]
    assert len(entry_keys) == len(set(entry_keys)) == 115

    reconciliation_bytes = V2_RECONCILIATION_PATH.read_bytes()
    assert len(reconciliation_bytes) == EXPECTED_V2_RECONCILIATION_BYTES
    assert (
        hashlib.sha256(reconciliation_bytes).hexdigest()
        == EXPECTED_V2_RECONCILIATION_SHA256
    )
    document = yaml.safe_load(reconciliation_bytes)
    assert set(document) == {"REVIEWED_SECRET_FINDINGS_RECONCILIATION_V2"}
    reconciliation = document["REVIEWED_SECRET_FINDINGS_RECONCILIATION_V2"]
    assert set(reconciliation) == {
        "story_id",
        "status",
        "reconciliation_classification",
        "canonical_status",
        "open_decisions",
        "semantic_selection",
        "candidate_base",
        "immutable_historical_inputs",
        "candidate_ledger",
        "complete_current_scan",
        "active_v1_replay",
        "pending_exact_owner_review",
        "candidate_replay",
        "history_universe",
        "frozen_security_implementation",
        "pr_49_v3_non_adoption",
        "boundaries",
        "self_reference_boundary",
    }
    assert reconciliation["story_id"] == "ST-0106"
    assert reconciliation["status"] == "UNAPPROVED_CURRENT_MAIN_CANDIDATE"
    assert reconciliation["reconciliation_classification"] == (
        "FAIL_CLOSED_EXACT_LEDGER_REVIEW_BOUNDARY"
    )
    assert reconciliation["canonical_status"] == "UNCHANGED"
    assert reconciliation["open_decisions"] == []

    selection = reconciliation["semantic_selection"]
    assert selection["decision_id"] == (
        "ST0106-CI-CACHE-AND-REVIEWED-SECRET-FINDINGS-V2"
    )
    assert selection["selected_strategy"] == ("EXACT_REVIEWED_GENERIC_FINDINGS_LEDGER")
    assert selection["rejected_strategy"] == ("GLOBAL_V3_GENERIC_CLASSIFIER_CHANGE")
    assert selection["current_main_reconstruction"] == "AUTHORIZED"
    assert selection["current_main_confirmation"] == {
        "provenance": ("REPOSITORY_OWNER_CONFIRMATION_REPORTED_BY_INTEGRATION_OWNER"),
        "observed_date": "2026-08-20",
        "scope": "SEMANTIC_APPROACH_SELECTION_ONLY",
        "exact_candidate_ledger_approval": "NONE",
        "workflow_rebinding_approval": "NONE",
    }
    for key in ("approved_handoff", "detached_handoff_approval"):
        binding = selection[key]
        content = repository_path_from_uri(binding["uri"]).read_bytes()
        assert len(content) == binding["bytes"]
        assert hashlib.sha256(content).hexdigest() == binding["sha256"]
    assert selection["approved_handoff"]["open_decisions"] == []

    assert reconciliation["candidate_base"] == {
        "branch": "codex/st-0106-reviewed-ledger-v2-current-main",
        "commit": "f733200d5b801a417d2f220e24efb9394f616be4",
        "tree": "60bbeb3a0d319b4a348f1cdeed824218289149c7",
        "base_ref": "origin/main",
    }
    candidate = reconciliation["candidate_ledger"]
    assert candidate == {
        "uri": f"repo://{V2_REVIEWED_FINDINGS_RELATIVE_PATH}",
        "source": "BYTE_IDENTICAL_PR_50_CANDIDATE",
        "source_commit": "bfac4720d9936a6806cc4fdf9f4c284b73e078d8",
        "bytes": EXPECTED_V2_REVIEWED_FINDINGS_BYTES,
        "sha256": EXPECTED_V2_REVIEWED_FINDINGS_SHA256,
        "ledger_version": 1,
        "internal_status": "UNAPPROVED_CANDIDATE",
        "rule_id": "GENERIC_CREDENTIAL",
        "entry_count": 115,
        "scope_counts": {"worktree": 31, "git_history": 84},
        "exact_members_present_in_current_scan": 115,
        "owner_approval": "NOT_EXECUTED",
        "workflow_binding": "ABSENT",
        "activation": "BLOCKED",
        "scanner_semantics": "UNCHANGED_BROAD_GENERIC_DETECTION",
    }

    current_scan = reconciliation["complete_current_scan"]
    assert current_scan["total_findings"] == 119
    assert current_scan["scope_counts"] == {"worktree": 31, "git_history": 88}
    assert current_scan["rule_counts"] == {
        "GENERIC_CREDENTIAL": 119,
        "AWS_ACCESS_KEY_ID": 0,
        "GITHUB_TOKEN": 0,
        "OPENAI_API_KEY": 0,
        "PRIVATE_KEY": 0,
    }
    assert current_scan["matched_values_printed"] is False
    assert current_scan["matched_values_persisted"] is False
    assert current_scan["stderr_bytes"] == 0

    assert reconciliation["active_v1_replay"] == {
        "network_boundary": "DENIED",
        "result": "EXPECTED_FAIL_CLOSED_STALE_WORKTREE_BINDING",
        "exit_code": 2,
        "error_code": "reviewed-finding-source-size-drift",
        "finding_count": 0,
        "stderr_bytes": 73,
        "stderr_sha256": (
            "d7019d56871988a4bc3ed0ebe9c2b54fdc14795ba63753d1805ba0c523e60b00"
        ),
        "current_main_clean_scan_claim": "NONE",
        "historical_owner_approval_mutation": "NONE",
    }

    pending = reconciliation["pending_exact_owner_review"]
    assert pending["state"] == "BLOCKING_NON_LEDGER_METADATA"
    assert pending["binding_count"] == 4
    assert pending["scope_counts"] == {"worktree": 0, "git_history": 4}
    assert pending["bindings_with_line_hash_absent_from_v1_and_pr50_v2"] == 4
    assert pending["owner_per_location_review"] == "NOT_EXECUTED"
    assert pending["false_positive_classification"] == "NOT_ASSIGNED"
    assert pending["no_live_credential_rationale"] == "NOT_ASSIGNED"
    assert pending["scanner_suppression_eligibility"] == "NONE"
    pending_bindings = pending["bindings"]
    assert len(pending_bindings) == 4
    assert all(
        set(binding)
        == {
            "scope",
            "exact_source_identifier",
            "exact_line_number",
            "exact_source_bytes",
            "exact_source_sha256",
            "exact_line_sha256",
            "path_hints",
            "candidate_state",
        }
        for binding in pending_bindings
    )
    assert all(
        binding["scope"] == "git_history"
        and binding["candidate_state"] == "PENDING_EXACT_OWNER_REVIEW"
        for binding in pending_bindings
    )
    pending_keys = {reviewed_finding_key(binding) for binding in pending_bindings}
    assert pending_keys.isdisjoint(entry_keys)
    ledger_line_hashes = {entry["exact_line_sha256"] for entry in entries}
    v1_entries = json.loads(REVIEWED_FINDINGS_PATH.read_bytes())["entries"]
    v1_line_hashes = {entry["exact_line_sha256"] for entry in v1_entries}
    assert all(
        binding["exact_line_sha256"] not in ledger_line_hashes
        and binding["exact_line_sha256"] not in v1_line_hashes
        for binding in pending_bindings
    )
    assert pending["forbidden_interpretations"] == [
        "reviewed ledger entry",
        "reviewed false positive",
        "no-live-credential conclusion",
        "suppression authority",
    ]

    replay = reconciliation["candidate_replay"]
    assert replay == {
        "ledger_entries_validated": 115,
        "result": "EXPECTED_FAIL_CLOSED_PENDING_REVIEW",
        "exit_code": 1,
        "residual_finding_count": 4,
        "residual_scope_counts": {"worktree": 0, "git_history": 4},
        "residual_rule_counts": {"GENERIC_CREDENTIAL": 4},
        "residual_sanitized_output_bytes": 400,
        "residual_sanitized_output_sha256": (
            "b71ffaf6e1d2cb7164e42a789153d58a10d80f21e2cbff390d45310385ab2fbb"
        ),
        "stderr_bytes": 0,
        "scan_pass_claim": "NONE",
        "activation_claim": "NONE",
    }

    v1_history = {
        json.dumps(entry, sort_keys=True, separators=(",", ":"))
        for entry in v1_entries
        if entry["scope"] == "git_history"
    }
    v2_history = {
        json.dumps(entry, sort_keys=True, separators=(",", ":"))
        for entry in entries
        if entry["scope"] == "git_history"
    }
    assert len(v1_history) == 58
    assert v1_history < v2_history
    assert len(v2_history - v1_history) == 26
    assert all(
        json.loads(entry)["exact_line_sha256"] in v1_line_hashes
        for entry in v2_history - v1_history
    )

    assert reconciliation["boundaries"]["approved_v1_workflow_binding"] == ("PRESERVED")
    assert reconciliation["boundaries"]["v2_workflow_rebinding"] == "BLOCKED"
    assert reconciliation["pr_49_v3_non_adoption"]["runtime_adoption"] == (
        "NOT_ADOPTED"
    )
    assert (
        reconciliation["pr_49_v3_non_adoption"]["ast_entropy_rhs_classifier_semantics"]
        == "NOT_ADOPTED"
    )


def test_current_origin_inventory_and_frozen_security_bytes_are_exact() -> None:
    inventory_bytes = V2_INVENTORY_PATH.read_bytes()
    assert len(inventory_bytes) == EXPECTED_V2_INVENTORY_BYTES
    assert hashlib.sha256(inventory_bytes).hexdigest() == EXPECTED_V2_INVENTORY_SHA256
    lines = inventory_bytes.decode("utf-8").splitlines()
    assert lines[:11] == [
        "format RAOS_ST0106_ORIGIN_REF_INVENTORY_V2",
        (
            "command git for-each-ref --format='%(refname) %(objectname)' "
            "refs/remotes/origin refs/tags | awk "
            "'$1 != \"refs/remotes/origin/HEAD\"' | LC_ALL=C sort"
        ),
        "remote_name origin",
        "fetch_heads +refs/heads/*:refs/remotes/origin/*",
        "fetch_tags +refs/tags/*:refs/tags/*",
        "fetch_depth 0",
        "symbolic_origin_head EXCLUDED",
        "head_ref_count 62",
        "tag_ref_count 17",
        f"entries_sha256 {EXPECTED_V2_INVENTORY_ENTRIES_SHA256}",
        "entries",
    ]
    entries = lines[11:]
    assert entries == sorted(entries)
    assert len(entries) == len(set(entries)) == 79
    assert all(
        re.fullmatch(r"refs/(?:remotes/origin|tags)/[^ ]+ [0-9a-f]{40}", entry)
        for entry in entries
    )
    assert sum(entry.startswith("refs/remotes/origin/") for entry in entries) == 62
    assert sum(entry.startswith("refs/tags/") for entry in entries) == 17
    assert not any(entry.startswith("refs/remotes/origin/HEAD ") for entry in entries)
    assert not any(entry.startswith("refs/remotes/origin/pr/") for entry in entries)
    entry_bytes = ("\n".join(entries) + "\n").encode("utf-8")
    assert hashlib.sha256(entry_bytes).hexdigest() == (
        EXPECTED_V2_INVENTORY_ENTRIES_SHA256
    )

    reconciliation = yaml.safe_load(V2_RECONCILIATION_PATH.read_bytes())[
        "REVIEWED_SECRET_FINDINGS_RECONCILIATION_V2"
    ]
    history = reconciliation["history_universe"]
    assert history["actual_origin_head_count"] == 62
    assert history["tag_ref_count"] == 17
    assert history["symbolic_origin_head"] == "EXCLUDED"
    assert history["local_origin_pr_refs"] == "EXCLUDED"
    assert history["entries_sha256"] == EXPECTED_V2_INVENTORY_ENTRIES_SHA256
    assert history["ref_inventory"] == {
        "uri": f"repo://{V2_INVENTORY_RELATIVE_PATH}",
        "bytes": EXPECTED_V2_INVENTORY_BYTES,
        "sha256": EXPECTED_V2_INVENTORY_SHA256,
        "format": "RAOS_ST0106_ORIGIN_REF_INVENTORY_V2",
        "entry_count": 79,
    }

    frozen = reconciliation["frozen_security_implementation"]
    assert len(frozen) == len(EXPECTED_FROZEN_SECURITY_IMPLEMENTATION)
    for binding in frozen:
        relative = binding["uri"].removeprefix("repo://")
        expected_bytes, expected_sha256 = EXPECTED_FROZEN_SECURITY_IMPLEMENTATION[
            relative
        ]
        content = repository_path_from_uri(binding["uri"]).read_bytes()
        assert binding == {
            "uri": f"repo://{relative}",
            "bytes": expected_bytes,
            "sha256": expected_sha256,
            "mutation": "FORBIDDEN",
        }
        assert len(content) == expected_bytes
        assert hashlib.sha256(content).hexdigest() == expected_sha256


def test_current_main_v2_activation_is_exact_hash_bound_and_append_only() -> None:
    activation_bytes = V2_ACTIVATION_PATH.read_bytes()
    assert len(activation_bytes) == EXPECTED_V2_ACTIVATION_BYTES
    assert hashlib.sha256(activation_bytes).hexdigest() == EXPECTED_V2_ACTIVATION_SHA256
    document = yaml.safe_load(activation_bytes)
    assert set(document) == {"REVIEWED_SECRET_FINDINGS_ACTIVATION_V2"}
    activation = document["REVIEWED_SECRET_FINDINGS_ACTIVATION_V2"]
    assert set(activation) == {
        "story_id",
        "slice_id",
        "status",
        "canonical_status",
        "open_decisions",
        "exact_authority",
        "source_candidate",
        "exact_ledger",
        "approved_sanitized_nonledger_locations",
        "authorized_activation",
        "current_ref_replay",
        "frozen_security_implementation",
        "boundaries",
        "self_reference_boundary",
    }
    assert activation["story_id"] == "ST-0106"
    assert activation["slice_id"] == (
        "ST0106_CURRENT_MAIN_REVIEWED_SECRET_FINDINGS_V2_ACTIVATION"
    )
    assert activation["status"] == (
        "OWNER_APPROVED_FOR_EXACT_V2_CI_REFERENCE_ACTIVATION"
    )
    assert activation["canonical_status"] == "UNCHANGED"
    assert activation["open_decisions"] == []

    authority = activation["exact_authority"]
    statement = authority["normalized_semantic_statement"].encode("utf-8")
    assert authority["approved_by"] == "repository_owner:jamozi"
    assert authority["observed_at"] == "2026-08-20T13:03:40Z"
    assert authority["message_authored_at"] == "NOT_SUPPLIED"
    assert authority["provenance"] == ("CONNECTED_CONVERSATION_VISIBLE_USER_MESSAGE")
    assert len(statement) == authority["normalized_semantic_statement_utf8_bytes"]
    assert len(statement) == 299
    assert (
        hashlib.sha256(statement).hexdigest()
        == (authority["normalized_semantic_statement_sha256"])
    )
    assert authority["normalized_semantic_statement_sha256"] == (
        "4be3d3b4c3bf3fe203eaed68514b2fa4d2b1e6ca93b562d7cf6de63830590a63"
    )
    assert authority["normalization"] == {
        "display_markdown_quote_markers_removed": True,
        "display_line_wrapping_joined": True,
        "other_text_change": False,
        "semantic_delta": "NONE",
    }

    source = activation["source_candidate"]
    assert source == {
        "branch": "codex/st-0106-reviewed-ledger-v2-current-main",
        "commit": "9ea1a52ded96c8d6532fe180997d2e60f7bb2a45",
        "tree": "6e15340bc9c7c28ef815182c9e2a6d7794f4a4e1",
        "parent_commit": "f733200d5b801a417d2f220e24efb9394f616be4",
        "reconciliation_uri": f"repo://{V2_RECONCILIATION_RELATIVE_PATH}",
        "reconciliation_bytes": EXPECTED_V2_RECONCILIATION_BYTES,
        "reconciliation_sha256": EXPECTED_V2_RECONCILIATION_SHA256,
        "reconciliation_history_mutation": "NONE",
    }
    reconciliation_bytes = repository_path_from_uri(
        source["reconciliation_uri"]
    ).read_bytes()
    assert len(reconciliation_bytes) == source["reconciliation_bytes"]
    assert (
        hashlib.sha256(reconciliation_bytes).hexdigest()
        == (source["reconciliation_sha256"])
    )

    ledger = activation["exact_ledger"]
    assert ledger == {
        "uri": f"repo://{V2_REVIEWED_FINDINGS_RELATIVE_PATH}",
        "bytes": EXPECTED_V2_REVIEWED_FINDINGS_BYTES,
        "sha256": EXPECTED_V2_REVIEWED_FINDINGS_SHA256,
        "ledger_version": 1,
        "internal_status": "UNAPPROVED_CANDIDATE",
        "rule_id": "GENERIC_CREDENTIAL",
        "entry_count": 115,
        "scope_counts": {"worktree": 31, "git_history": 84},
        "content_mutation": "NONE",
        "specific_rule_suppression": "FORBIDDEN",
    }
    ledger_bytes = repository_path_from_uri(ledger["uri"]).read_bytes()
    assert len(ledger_bytes) == ledger["bytes"]
    assert hashlib.sha256(ledger_bytes).hexdigest() == ledger["sha256"]
    ledger_entries = json.loads(ledger_bytes)["entries"]

    historical = yaml.safe_load(V2_RECONCILIATION_PATH.read_bytes())[
        "REVIEWED_SECRET_FINDINGS_RECONCILIATION_V2"
    ]["pending_exact_owner_review"]
    approved = activation["approved_sanitized_nonledger_locations"]
    assert approved["source"] == (
        f"repo://{V2_RECONCILIATION_RELATIVE_PATH}#pending_exact_owner_review.bindings"
    )
    assert approved["binding_count"] == 4
    assert approved["scope_counts"] == {"worktree": 0, "git_history": 4}
    assert approved["owner_classification"] == (
        "REVIEWED_FALSE_POSITIVE_NON_SECRET_PYTHON_CALL_EXPRESSION"
    )
    assert approved["no_live_credential_conclusion"] == "CONFIRMED"
    assert approved["review_method"] == (
        "HASH_BOUND_LOCATION_AND_DETERMINISTIC_AST_SHAPE_ONLY"
    )
    assert approved["matched_values_extracted"] is False
    assert approved["matched_values_printed"] is False
    assert approved["matched_values_persisted"] is False
    assert approved["ledger_membership"] == "ABSENT"
    assert approved["scanner_suppression_eligibility"] == "NONE"
    assert approved["reintroduction_behavior"] == ("FAIL_CLOSED_AS_NEW_GENERIC_FINDING")
    approved_bindings = approved["bindings"]
    assert len(approved_bindings) == len(historical["bindings"]) == 4
    historical_metadata_keys = {
        "scope",
        "exact_source_identifier",
        "exact_line_number",
        "exact_source_bytes",
        "exact_source_sha256",
        "exact_line_sha256",
        "path_hints",
    }
    for historical_binding, approved_binding in zip(
        historical["bindings"], approved_bindings, strict=True
    ):
        assert {key: approved_binding[key] for key in historical_metadata_keys} == {
            key: historical_binding[key] for key in historical_metadata_keys
        }
        assert approved_binding["selected_ast_shape"] == "ast.Call"
        assert approved_binding["selected_string_literal_count"] == 0
        assert approved_binding["classification"] == (
            "REVIEWED_FALSE_POSITIVE_NON_SECRET_PYTHON_CALL_EXPRESSION"
        )
        assert approved_binding["no_live_credential"] is True
        assert approved_binding["ledger_membership"] == "ABSENT"
        assert approved_binding["scanner_suppression_eligibility"] == "NONE"
    ledger_keys = {reviewed_finding_key(entry) for entry in ledger_entries}
    approved_keys = {reviewed_finding_key(binding) for binding in approved_bindings}
    assert approved_keys.isdisjoint(ledger_keys)

    boundaries = activation["boundaries"]
    assert boundaries["exact_local_workflow_reference_activation"] == "IMPLEMENTED"
    assert boundaries["exact_v2_ledger_content"] == "UNCHANGED"
    assert boundaries["four_reviewed_nonledger_location_suppression"] == "NONE"
    assert boundaries["specific_rule_suppression"] == "FORBIDDEN"
    for key in (
        "scanner_or_wrapper_mutation",
        "reconciliation_history_mutation",
        "v1_ledger_or_approval_mutation",
        "canonical_or_status_mutation",
        "st_0107_or_downstream_provenance_mutation",
    ):
        assert boundaries[key] == "NONE"
    for key in (
        "hosted_ci",
        "formal_tst_001",
        "formal_tst_002",
        "push_pull_request_or_merge",
        "external_write",
        "staging_release_or_production",
    ):
        assert boundaries[key] == "NOT_EXECUTED"
    assert activation["self_reference_boundary"] == {
        "tracked_record_final_activation_commit_binding": (
            "IMPOSSIBLE_BY_SELF_REFERENCE_AND_NOT_CLAIMED"
        ),
        "activation_commit_and_post_commit_replay": ("REPORTED_OUTSIDE_TRACKED_RECORD"),
    }


def test_activation_origin_inventory_and_replay_boundary_are_exact() -> None:
    inventory_bytes = ACTIVATION_INVENTORY_PATH.read_bytes()
    assert len(inventory_bytes) == EXPECTED_ACTIVATION_INVENTORY_BYTES
    assert hashlib.sha256(inventory_bytes).hexdigest() == (
        EXPECTED_ACTIVATION_INVENTORY_SHA256
    )
    lines = inventory_bytes.decode("utf-8").splitlines()
    assert lines[:13] == [
        "format RAOS_ST0106_ORIGIN_REF_INVENTORY_ACTIVATION_V2",
        (
            "command git for-each-ref --format='%(refname) %(objectname)' "
            "refs/remotes/origin refs/tags | awk "
            "'$1 != \"refs/remotes/origin/HEAD\"' | LC_ALL=C sort"
        ),
        "source_remote https://github.com/jamozi/rakuten.git",
        "observed_at 2026-08-20T13:14:44Z",
        "remote_name origin",
        "fetch_heads +refs/heads/*:refs/remotes/origin/*",
        "fetch_tags +refs/tags/*:refs/tags/*",
        "fetch_depth 0",
        "symbolic_origin_head EXCLUDED",
        "head_ref_count 5",
        "tag_ref_count 17",
        (f"entries_sha256 {EXPECTED_ACTIVATION_INVENTORY_ENTRIES_SHA256}"),
        "entries",
    ]
    entries = lines[13:]
    assert entries == sorted(entries)
    assert len(entries) == len(set(entries)) == 22
    assert all(
        re.fullmatch(r"refs/(?:remotes/origin|tags)/[^ ]+ [0-9a-f]{40}", entry)
        for entry in entries
    )
    assert sum(entry.startswith("refs/remotes/origin/") for entry in entries) == 5
    assert sum(entry.startswith("refs/tags/") for entry in entries) == 17
    assert not any(entry.startswith("refs/remotes/origin/HEAD ") for entry in entries)
    assert not any(entry.startswith("refs/remotes/origin/pr/") for entry in entries)
    entry_bytes = ("\n".join(entries) + "\n").encode("utf-8")
    assert hashlib.sha256(entry_bytes).hexdigest() == (
        EXPECTED_ACTIVATION_INVENTORY_ENTRIES_SHA256
    )

    activation = yaml.safe_load(V2_ACTIVATION_PATH.read_bytes())[
        "REVIEWED_SECRET_FINDINGS_ACTIVATION_V2"
    ]
    replay = activation["current_ref_replay"]
    assert replay == {
        "observed_at": "2026-08-20T13:14:44Z",
        "reconstruction": (
            "PHYSICAL_STANDALONE_CURRENT_ORIGIN_HEADS_AND_TAGS_FETCH_DEPTH_0"
        ),
        "inventory_uri": f"repo://{ACTIVATION_INVENTORY_RELATIVE_PATH}",
        "inventory_bytes": EXPECTED_ACTIVATION_INVENTORY_BYTES,
        "inventory_sha256": EXPECTED_ACTIVATION_INVENTORY_SHA256,
        "inventory_format": "RAOS_ST0106_ORIGIN_REF_INVENTORY_ACTIVATION_V2",
        "inventory_entry_count": 22,
        "inventory_entries_sha256": (EXPECTED_ACTIVATION_INVENTORY_ENTRIES_SHA256),
        "actual_origin_head_count": 5,
        "tag_ref_count": 17,
        "checkout_commit": "9ea1a52ded96c8d6532fe180997d2e60f7bb2a45",
        "physical_git_directory": True,
        "shared_object_store": False,
        "alternates": False,
        "shallow": False,
        "network_boundary": "DENIED",
        "exact_v2_ledger_result": "CLEAN",
        "exit_code": 0,
        "network_report_lines": 1,
        "scanner_finding_lines": 0,
        "stderr_bytes": 0,
        "residual_finding_count": 0,
        "specific_rule_findings": 0,
        "matched_values_printed": False,
        "matched_values_persisted": False,
        "post_activation_commit_replay": (
            "REQUIRED_AND_REPORTED_OUTSIDE_TRACKED_RECORD"
        ),
    }
    frozen = activation["frozen_security_implementation"]
    assert len(frozen) == len(EXPECTED_FROZEN_SECURITY_IMPLEMENTATION)
    for binding in frozen:
        relative = binding["uri"].removeprefix("repo://")
        expected_bytes, expected_sha256 = EXPECTED_FROZEN_SECURITY_IMPLEMENTATION[
            relative
        ]
        content = repository_path_from_uri(binding["uri"]).read_bytes()
        assert binding == {
            "uri": f"repo://{relative}",
            "bytes": expected_bytes,
            "sha256": expected_sha256,
            "mutation": "FORBIDDEN",
        }
        assert len(content) == expected_bytes
        assert hashlib.sha256(content).hexdigest() == expected_sha256


def test_secret_job_runs_the_exact_approved_local_history_command() -> None:
    job = WORKFLOW["jobs"]["secrets"]
    expected_command = (
        'scripts/run_network_denied.sh --home "$HOME" -- '
        "/usr/bin/python3 -I scripts/scan_secrets.py "
        "--worktree --git-history --reviewed-findings "
        f"{V2_REVIEWED_FINDINGS_RELATIVE_PATH}"
    )
    assert WORKFLOW_TEXT.count("--reviewed-findings") == 1
    assert WORKFLOW_TEXT.count(REVIEWED_FINDINGS_RELATIVE_PATH) == 0
    assert WORKFLOW_TEXT.count(V2_REVIEWED_FINDINGS_RELATIVE_PATH) == 1
    assert len(action_steps(job)) == 1
    secret_step = named_run_step(job, "Reproduce secret scan")
    assert secret_step == {
        "name": "Reproduce secret scan",
        "if": "${{ needs.classify.outputs.secrets == 'true' }}",
        "run": expected_command,
    }
    activation = yaml.safe_load(V2_ACTIVATION_PATH.read_bytes())[
        "REVIEWED_SECRET_FINDINGS_ACTIVATION_V2"
    ]
    assert activation["authorized_activation"] == {
        "workflow_uri": "repo://.github/workflows/ci.yml",
        "job_id": "secrets",
        "step_name": "Reproduce secret scan",
        "exact_argument": (f"--reviewed-findings {V2_REVIEWED_FINDINGS_RELATIVE_PATH}"),
        "exact_command": expected_command,
        "semantic_delta": "REPLACE_EXACT_LEDGER_PATH_V1_WITH_V2_ONCE",
        "pre_activation_workflow_bytes": EXPECTED_PRE_ACTIVATION_WORKFLOW_BYTES,
        "pre_activation_workflow_sha256": EXPECTED_PRE_ACTIVATION_WORKFLOW_SHA256,
        "post_activation_workflow_bytes": EXPECTED_POST_ACTIVATION_WORKFLOW_BYTES,
        "post_activation_workflow_sha256": EXPECTED_POST_ACTIVATION_WORKFLOW_SHA256,
        "v1_workflow_reference_count": 0,
        "v2_workflow_reference_count": 1,
        "unrelated_workflow_bytes": "PRE_ACTIVATION_BYTES_RECONSTRUCTED_EXACTLY",
        "scanner_semantics": "UNCHANGED",
        "network_wrapper_semantics": "UNCHANGED",
        "ci_wrapper_semantics": "UNCHANGED",
    }


def test_database_job_runs_only_the_exact_st0201_runtime_wrapper() -> None:
    job = WORKFLOW["jobs"]["database"]
    assert job["name"] == "Database"
    assert len(action_steps(job)) == 1
    runtime_step = named_run_step(job, "Verify exact PostgreSQL service")
    assert runtime_step == {
        "name": "Verify exact PostgreSQL service",
        "if": "${{ needs.classify.outputs.database == 'true' }}",
        "run": ('scripts/postgres_service.sh --docker "$(command -v docker)" test'),
    }
    assert "scripts/run_network_denied.sh" not in runtime_step["run"]


def test_storage_job_runs_only_the_exact_st0202_runtime_wrapper() -> None:
    job = WORKFLOW["jobs"]["storage"]
    assert job["name"] == "Storage"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == "20"
    assert len(action_steps(job)) == 1
    runtime_step = named_run_step(job, "Verify exact object-storage service")
    assert runtime_step == {
        "name": "Verify exact object-storage service",
        "if": "${{ needs.classify.outputs.storage == 'true' }}",
        "run": (
            'scripts/object_storage_service.sh --docker "$(command -v docker)" test'
        ),
    }
    command = runtime_step["run"]
    for forbidden in (
        "scripts/run_network_denied.sh",
        "setup-uv",
        "setup-node",
        "sync",
        "secret",
        "deploy",
    ):
        assert forbidden not in command.lower()


def test_official_source_snapshot_matches_workflow_pins() -> None:
    snapshot_path = (
        REPOSITORY_ROOT / "docs/architecture/ST-0106-github-actions-snapshot.yaml"
    )
    snapshot = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
    observed = {item["repository"]: item["commit_sha"] for item in snapshot["actions"]}
    assert observed == EXPECTED_ACTIONS
    assert snapshot["document"]["checked_at"].startswith("2026-08-02")


def test_make_and_docs_expose_every_local_job_boundary() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    execplan = (REPOSITORY_ROOT / "docs/execplans/ST-0106.md").read_text(
        encoding="utf-8"
    )
    worklog = (REPOSITORY_ROOT / "docs/worklogs/ST-0106.md").read_text(encoding="utf-8")
    for target in (
        "ci-static",
        "ci-unit",
        "ci-contracts",
        "ci-database",
        "ci-storage",
    ):
        assert re.search(rf"(?m)^{target}:", makefile)
    normalized = " ".join(f"{readme}\n{execplan}\n{worklog}".split())
    for token in (
        "scripts/ci_job.sh",
        "scripts/scan_secrets.py",
        "TST-001",
        "TST-002",
        "IMPLEMENTED_NOT_VALIDATED",
        "NOT_STARTED",
        "NOT_EXECUTED",
    ):
        assert token in normalized


def test_unit_job_keeps_overlapping_story_modules_in_separate_processes() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    unit_recipe = makefile.split("\nci-unit:", 1)[1].split("\nci-contracts:", 1)[0]
    expected_suites = (
        "tests/test_import_raos_design.py",
        "tests/st0002",
        "tests/st0003",
        "tests/st0004",
        "tests/st0005",
        "tests/st0006",
        "tests/st0101",
        "tests/st0102",
        "tests/st0103",
        "tests/st0106",
        "tests/st0107",
        "tests/st0201",
        "tests/st0202",
        "tests/st0203",
        "tests/st0204",
        "tests/st0205",
        "tests/st0301",
        "tests/st0302",
        "tests/st0303",
        "tests/st0304",
        "tests/st0305",
        "tests/st0306",
        "tests/st0307",
        "tests/st0701",
        "tests/st0703",
        "tests/st0801",
    )
    assert unit_recipe.count("pytest -p no:cacheprovider -q") == len(expected_suites)
    assert [unit_recipe.index(suite) for suite in expected_suites] == sorted(
        unit_recipe.index(suite) for suite in expected_suites
    )
    for suite in expected_suites:
        matches = re.findall(rf"(?m)^.*(?<!\S){re.escape(suite)}(?:\s|$)", unit_recipe)
        assert len(matches) == 1
    for story in ("st0002", "st0003", "st0004"):
        assert (
            f"tests/{story} --ignore=tests/{story}/test_postgresql_migration.py"
            in unit_recipe
        )
    assert "tests/st0307 --ignore=tests/st0307/test_postgresql.py" in unit_recipe


def test_contract_database_and_storage_make_recipes_keep_distinct_boundaries() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    contracts_block = makefile.split("\nci-contracts:", 1)[1].split(
        "\nci-database:", 1
    )[0]
    database_block = (
        makefile.split("\nci-database:", 1)[1].split("\nci-storage:", 1)[0].splitlines()
    )
    storage_block = makefile.split("\nci-storage:", 1)[1].splitlines()
    database_recipe = []
    for line in database_block[1:]:
        if not line.startswith("\t"):
            break
        database_recipe.append(line)

    assert "contract-codegen-hydrate" in contracts_block.splitlines()[0]
    assert "contract-codegen-gate" in contracts_block
    assert database_block[0].strip() == "postgres-test"
    assert database_recipe == []
    assert storage_block[0].strip() == "object-storage-test"


def test_shared_compose_generator_is_the_single_repository_policy_check() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    makefile_lines = makefile.splitlines()
    header_index = next(
        index
        for index, line in enumerate(makefile_lines)
        if line.startswith("ci-repository-policy:")
    )
    header_lines = [makefile_lines[header_index]]
    while header_lines[-1].endswith("\\"):
        header_lines.append(makefile_lines[header_index + len(header_lines)])
    policy_header = " ".join(line.removesuffix("\\").strip() for line in header_lines)
    assert "local-compose-check" in policy_header
    assert "queue-check" in policy_header
    assert "config-check" in policy_header
    assert "synthetic-data-check" in policy_header
    assert "migration-check" in policy_header
    assert "ai-registry-check" in policy_header
    assert "content-ast-check" in policy_header
    policy_recipe = makefile.split("\nci-repository-policy:", 1)[1].split(
        "\nci-static:", 1
    )[0]
    assert "build_st0201_postgres_service.py" not in policy_recipe
    assert makefile.count("scripts/build_local_compose.py --check") == 1

    generate_block = makefile.split("\nlocal-compose-generate:", 1)[1].split(
        "\nlocal-compose-check:", 1
    )[0]
    check_block = makefile.split("\nlocal-compose-check:", 1)[1].split(
        "\npostgres-generate:", 1
    )[0]
    assert "scripts/build_local_compose.py" in generate_block
    assert "scripts/build_local_compose.py --check" in check_block
    assert "build_st0201_postgres_service.py" not in generate_block + check_block
    assert "postgres-generate: local-compose-generate" in makefile
    assert "postgres-check: local-compose-check" in makefile


def test_queue_fake_uses_the_offline_unit_boundary_without_a_broker_job() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    generate_block = makefile.split("\nqueue-generate:", 1)[1].split(
        "\nqueue-check:", 1
    )[0]
    check_block = makefile.split("\nqueue-check:", 1)[1].split("\nqueue-test:", 1)[0]
    test_block = makefile.split("\nqueue-test:", 1)[1].split("\nconfig-generate:", 1)[0]

    assert "scripts/build_st0203_queue_fake.py" in generate_block
    assert "scripts/build_st0203_queue_fake.py --check" in check_block
    assert "tests/st0203" in test_block
    assert "queue:" not in workflow
    assert "LocalStack" not in workflow


def test_runtime_config_uses_repository_policy_and_offline_unit_boundaries() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    generate_block = makefile.split("\nconfig-generate:", 1)[1].split(
        "\nconfig-check:", 1
    )[0]
    check_block = makefile.split("\nconfig-check:", 1)[1].split("\nconfig-test:", 1)[0]
    test_block = makefile.split("\nconfig-test:", 1)[1].split(
        "\npostgres-generate:", 1
    )[0]

    assert "scripts/build_st0204_config_loader.py" in generate_block
    assert "scripts/build_st0204_config_loader.py --check" in check_block
    assert "tests/st0204" in test_block
    assert "secret-manager:" not in workflow
    assert "dotenv" not in workflow.lower()


def test_synthetic_data_uses_repository_policy_and_offline_unit_boundaries() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    generate_block = makefile.split("\nsynthetic-data-generate:", 1)[1].split(
        "\nsynthetic-data-check:", 1
    )[0]
    check_block = makefile.split("\nsynthetic-data-check:", 1)[1].split(
        "\nsynthetic-data-test:", 1
    )[0]
    test_block = makefile.split("\nsynthetic-data-test:", 1)[1].split(
        "\nmigration-generate:", 1
    )[0]

    assert "scripts/build_st0205_synthetic_data.py" in generate_block
    assert "scripts/build_st0205_synthetic_data.py --check" in check_block
    assert "tests/st0205" in test_block
    assert "synthetic-data-generate: | python-sync" in makefile
    assert "synthetic-data-check:\n" in makefile
    assert "synthetic-data-check: | python-sync" not in makefile
    assert "synthetic-data-test:\n" in makefile
    assert "synthetic-data-test: | python-sync" not in makefile
    assert "$(UV_READONLY_RUN)" in check_block
    assert "$(UV_READONLY_RUN)" in test_block
    assert "provider" not in workflow.lower().split("jobs:", 1)[0]


def test_migration_framework_uses_repository_policy_and_unit_boundaries() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    generate_block = makefile.split("\nmigration-generate:", 1)[1].split(
        "\nmigration-check:", 1
    )[0]
    check_block = makefile.split("\nmigration-check:", 1)[1].split(
        "\nmigration-test:", 1
    )[0]
    test_block = makefile.split("\nmigration-test:", 1)[1].split(
        "\nmigration-fixture-generate:", 1
    )[0]
    fixture_generate_block = makefile.split("\nmigration-fixture-generate:", 1)[
        1
    ].split("\nmigration-fixture-check:", 1)[0]
    fixture_check_block = makefile.split("\nmigration-fixture-check:", 1)[1].split(
        "\nmigration-fixture-test:", 1
    )[0]
    fixture_test_block = makefile.split("\nmigration-fixture-test:", 1)[1].split(
        "\npostgres-generate:", 1
    )[0]

    assert "scripts/build_st0306_database_roles.py" in generate_block
    assert "scripts/build_st0306_database_roles.py --check" in check_block
    assert "scripts/build_st0301_migration_framework.py" not in generate_block
    assert "scripts/build_st0301_migration_framework.py" not in check_block
    assert "scripts/build_st0302_foundation.py" not in generate_block
    assert "scripts/build_st0302_foundation.py" not in check_block
    assert "scripts/build_st0303_iam_ops.py" not in generate_block
    assert "scripts/build_st0303_iam_ops.py" not in check_block
    assert "scripts/build_st0304_domain_schemas.py" not in generate_block
    assert "scripts/build_st0304_domain_schemas.py" not in check_block
    expected_migration_suites = (
        "tests/st0301",
        "tests/st0302",
        "tests/st0303",
        "tests/st0304",
        "tests/st0305",
        "tests/st0306",
    )
    assert test_block.count("pytest") == len(expected_migration_suites)
    assert [test_block.index(suite) for suite in expected_migration_suites] == sorted(
        test_block.index(suite) for suite in expected_migration_suites
    )
    for suite in expected_migration_suites:
        assert len(re.findall(rf"(?m)^.*-q {re.escape(suite)}$", test_block)) == 1
    assert "scripts/build_st0307_migration_fixtures.py" in fixture_generate_block
    assert "scripts/build_st0307_migration_fixtures.py --check" in fixture_check_block
    assert "-q tests/st0307" in fixture_test_block
    assert (
        "migration-check"
        in makefile.split("\nci-repository-policy:", 1)[1].split("\nci-static:", 1)[0]
    )
    assert "migration:" not in workflow


def test_migration_documentation_names_current_head_and_runtime_evidence_gate() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())

    assert "current migration head to `202608030006`" in normalized_readme
    assert "`scripts/build_st0306_database_roles.py`" in readme
    assert (
        "Exact PostgreSQL 18.4 runtime evidence requires both `RAOS_PG_BIN` and "
        "`RAOS_PG_LIB`" in normalized_readme
    )
    assert "all six isolated migration Story suites" in normalized_readme
    assert "zero skipped tests" in normalized_readme


def test_content_ast_uses_repository_policy_and_offline_unit_boundaries() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    generate_block = makefile.split("\ncontent-ast-generate:", 1)[1].split(
        "\ncontent-ast-check:", 1
    )[0]
    check_block = makefile.split("\ncontent-ast-check:", 1)[1].split(
        "\ncontent-ast-test:", 1
    )[0]
    test_block = makefile.split("\ncontent-ast-test:", 1)[1].split(
        "\nlocal-compose-generate:", 1
    )[0]

    assert "scripts/build_st0801_content_ast.py" in generate_block
    assert "--check" not in generate_block
    assert "scripts/build_st0801_content_ast.py --check" in check_block
    assert "tests/st0801" in test_block
    assert (
        "content-ast-check"
        in makefile.split("\nci-repository-policy:", 1)[1].split("\nci-static:", 1)[0]
    )
    assert "content-ast:" not in workflow


def test_ai_registry_uses_repository_policy_and_offline_unit_boundaries() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    format_block = makefile.split("\npython-format-check:", 1)[1].split(
        "\npython-typecheck:", 1
    )[0]
    generate_block = makefile.split("\nai-registry-generate:", 1)[1].split(
        "\nai-registry-check:", 1
    )[0]
    check_block = makefile.split("\nai-registry-check:", 1)[1].split(
        "\nai-registry-test:", 1
    )[0]
    test_block = makefile.split("\nai-registry-test:", 1)[1].split(
        "\nopenai-recorded-generate:", 1
    )[0]

    assert "scripts/build_st0701_ai_registry.py" in generate_block
    assert "--check" not in generate_block
    assert generate_block.startswith(" | python-sync\n")
    assert "scripts/build_st0701_ai_registry.py --check" in check_block
    assert "tests/st0701" in test_block
    assert "python-sync" not in check_block
    assert "python-sync" not in test_block
    assert "PYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN)" in check_block
    assert "PYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN)" in test_block
    assert format_block.count("scripts/build_st0701_ai_registry.py") == 1
    assert format_block.count("tests/st0701") == 1
    assert (
        "ai-registry-check"
        in makefile.split("\nci-repository-policy:", 1)[1].split("\nci-static:", 1)[0]
    )
    assert "ai-registry:" not in workflow


def test_object_storage_make_targets_use_only_the_bounded_runtime_wrapper() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    expected_commands = {
        "object-storage-config": "config",
        "object-storage-up": "up",
        "object-storage-health": "check",
        "object-storage-down": "down",
        "object-storage-test": "test",
    }
    for target, command in expected_commands.items():
        expected = (
            f'{target}:\n\tscripts/object_storage_service.sh --docker "$(DOCKER)" '
            f"{command}"
        )
        assert expected in makefile
    assert "ci-storage: object-storage-test" in makefile
