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
REVIEWED_FINDINGS_V1_RELATIVE_PATH = (
    "changes/st-0106/contracts/reviewed-secret-findings.v1.yaml"
)
REVIEWED_FINDINGS_V1_PATH = REPOSITORY_ROOT / REVIEWED_FINDINGS_V1_RELATIVE_PATH
REVIEWED_FINDINGS_RELATIVE_PATH = (
    "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
)
REVIEWED_FINDINGS_PATH = REPOSITORY_ROOT / REVIEWED_FINDINGS_RELATIVE_PATH
REVIEWED_FINDINGS_APPROVAL_PATH = (
    REPOSITORY_ROOT / "changes/st-0106/REVIEWED-SECRET-FINDINGS-APPROVAL-v1.yaml"
)
REVIEWED_FINDINGS_RECONCILIATION_PATH = (
    REPOSITORY_ROOT / "changes/st-0106/"
    "DESIGN_HANDOFF_V1_ST0106_REVIEWED_SECRET_FINDINGS_CURRENT_MAIN_RECONCILIATION_V2.yaml"
)
EXPECTED_REVIEWED_FINDINGS_V1_BYTES = 46295
EXPECTED_REVIEWED_FINDINGS_V1_SHA256 = (
    "1038cf6ef81da0acab528cf8206086646b6e003f5ac0ceed4f2e4b994827bcc7"
)
EXPECTED_REVIEWED_FINDINGS_BYTES = 59769
EXPECTED_REVIEWED_FINDINGS_SHA256 = (
    "52a5c8057599108c8765b85d95dfac55a96da12eff64cc80d00c90ddd8781c7d"
)
EXPECTED_REVIEWED_FINDINGS_APPROVAL_BYTES = 5524
EXPECTED_REVIEWED_FINDINGS_APPROVAL_SHA256 = (
    "b683ae3b3b7312bd4ce04fe2c796f1157542f72c1b1bca79919a71b3a7c1acd9"
)
EXPECTED_ACTIONS = {
    "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-node": "249970729cb0ef3589644e2896645e5dc5ba9c38",
    "astral-sh/setup-uv": "c771a70e6277c0a99b617c7a806ffedaca235ff9",
}


def action_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "uses" in step]


def run_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "run" in step]


def action_step(job: dict[str, Any], repository: str) -> dict[str, Any]:
    matches = [
        step for step in action_steps(job) if step["uses"].startswith(f"{repository}@")
    ]
    assert len(matches) == 1
    return matches[0]


def test_workflow_uses_only_the_unprivileged_pull_request_event() -> None:
    assert set(WORKFLOW) == {
        "name",
        "on",
        "permissions",
        "concurrency",
        "defaults",
        "jobs",
    }
    assert WORKFLOW["on"] == {"pull_request": ""}
    assert "pull_request_target" not in WORKFLOW_TEXT
    assert "workflow_run" not in WORKFLOW_TEXT
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["concurrency"] == {
        "group": "base-ci-${{ github.event.pull_request.number }}",
        "cancel-in-progress": "true",
    }
    assert WORKFLOW["defaults"] == {"run": {"shell": "bash"}}


def test_jobs_are_bounded_and_have_no_privileged_surface() -> None:
    jobs = WORKFLOW["jobs"]
    assert set(jobs) == {
        "static",
        "unit",
        "contracts",
        "database",
        "storage",
        "secrets",
    }
    for job in jobs.values():
        assert set(job) == {"name", "runs-on", "timeout-minutes", "steps"}
        assert job["runs-on"] == "ubuntu-24.04"
        assert 1 <= int(job["timeout-minutes"]) <= 30
        for step in job["steps"]:
            assert set(step).isdisjoint({"continue-on-error", "env", "if"})
    lowered = WORKFLOW_TEXT.lower()
    assert "${{ secrets." not in lowered
    assert "id-token" not in lowered
    assert "write-all" not in lowered
    assert not re.search(r"(?m)^\s+[a-z-]+:\s+write\s*$", WORKFLOW_TEXT)


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
        expected_depth = "0" if job_id == "secrets" else "1"
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
        assert set(observed_runs) == {
            "Validate dependency metadata without network",
            "Prove npm lock closure without network",
            "Install exact Python without repository code",
            "Hydrate source-constrained locked dependencies",
            f"Reproduce {job_id} job",
        }
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


def test_v1_reviewed_findings_and_detached_approval_remain_exact_audit_bytes() -> None:
    ledger_bytes = REVIEWED_FINDINGS_V1_PATH.read_bytes()
    assert len(ledger_bytes) == EXPECTED_REVIEWED_FINDINGS_V1_BYTES
    assert (
        hashlib.sha256(ledger_bytes).hexdigest() == EXPECTED_REVIEWED_FINDINGS_V1_SHA256
    )
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
    assert approval["ledger_uri"] == f"repo://{REVIEWED_FINDINGS_V1_RELATIVE_PATH}"
    assert approval["ledger_bytes"] == EXPECTED_REVIEWED_FINDINGS_V1_BYTES
    assert approval["ledger_sha256"] == EXPECTED_REVIEWED_FINDINGS_V1_SHA256
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


def test_v2_reviewed_findings_is_the_exact_remote_origin_reconciliation() -> None:
    ledger_bytes = REVIEWED_FINDINGS_PATH.read_bytes()
    assert len(ledger_bytes) == EXPECTED_REVIEWED_FINDINGS_BYTES
    assert hashlib.sha256(ledger_bytes).hexdigest() == EXPECTED_REVIEWED_FINDINGS_SHA256
    ledger = json.loads(ledger_bytes)
    assert set(ledger) == {"version", "status", "rule_id", "entries"}
    assert ledger["version"] == 1
    assert ledger["status"] == "UNAPPROVED_CANDIDATE"
    assert ledger["rule_id"] == "GENERIC_CREDENTIAL"
    assert len(ledger["entries"]) == 115
    assert sum(entry["scope"] == "worktree" for entry in ledger["entries"]) == 31
    assert sum(entry["scope"] == "git_history" for entry in ledger["entries"]) == 84
    assert all(
        entry["classification"] == "REVIEWED_FALSE_POSITIVE"
        for entry in ledger["entries"]
    )
    assert all(
        set(entry).isdisjoint({"value", "matched_value", "secret_value"})
        for entry in ledger["entries"]
    )

    v1 = json.loads(REVIEWED_FINDINGS_V1_PATH.read_bytes())
    v1_line_hashes = {entry["exact_line_sha256"] for entry in v1["entries"]}
    v2_line_hashes = {entry["exact_line_sha256"] for entry in ledger["entries"]}
    assert len(v1_line_hashes) == len(v2_line_hashes) == 32
    assert v2_line_hashes <= v1_line_hashes

    record = yaml.safe_load(REVIEWED_FINDINGS_RECONCILIATION_PATH.read_bytes())[
        "DESIGN_HANDOFF_V1"
    ]
    assert record["approved_story"] == "ST-0106"
    assert record["decision"]["id"] == (
        "ST0106_REVIEWED_SECRET_FINDINGS_CURRENT_MAIN_RECONCILIATION_V2"
    )
    assert record["exact_target"] == {
        "base_commit": "f733200d5b801a417d2f220e24efb9394f616be4",
        "base_tree": "60bbeb3a0d319b4a348f1cdeed824218289149c7",
        "development_branch": "codex/st0106-secrets-ledger-v2-20260820",
        "planned_integration_branch": "codex/base-ci-restoration-final-20260820",
        "final_exact_head": "NOT_PREDECLARED_VERIFY_AFTER_INTEGRATION",
        "root_agents_bytes": 43916,
        "root_agents_sha256": "a4b8f16d0a6ef073899381ee90597495b4264fc271bf9142f8866561f14ba482",
        "authority_basis": "ROOT_AGENTS_STANDING_DEVELOPMENT_AUTHORIZATION",
    }
    reconciliation = record["reconciliation"]
    assert reconciliation["preflight_superset_input"] == {
        "ephemeral_observation_path": (
            "/tmp/raos-st0106-reviewed-findings-expanded-v1-f733200.yaml"
        ),
        "durable_dependency": False,
        "file_type": "regular",
        "owner_uid": 1000,
        "mode": "0600",
        "bytes": 79457,
        "sha256": "390826ccee2072586fb31cb317a048d45f2d74f52908312b1b98b0e6ffec2e0d",
        "parser_schema_version": 1,
        "entry_count": 153,
        "scope_counts": {"worktree": 31, "git_history": 122},
        "history_count_delta_from_v1": 64,
        "history_locations_with_line_hash_not_seen_in_v1": 4,
        "unique_line_hashes_not_seen_in_v1": 3,
        "specific_rule_findings": 0,
        "local_only_history_entries_excluded_from_final": 38,
        "activation_authority": "NONE_INPUT_ONLY",
    }
    final = reconciliation["final_ledger"]
    assert final["path"] == REVIEWED_FINDINGS_RELATIVE_PATH
    assert final["filename_reconciliation_generation"] == 2
    assert final["parser_schema_version"] == 1
    assert final["bytes"] == EXPECTED_REVIEWED_FINDINGS_BYTES
    assert final["sha256"] == EXPECTED_REVIEWED_FINDINGS_SHA256
    assert final["entry_count"] == 115
    assert final["scope_counts"] == {"worktree": 31, "git_history": 84}
    assert final["specific_rule_findings"] == 0
    assert final["unique_line_hashes_not_in_v1"] == 0
    assert (
        reconciliation["sanitized_review_method"]["matched_bytes_printed_or_persisted"]
        is False
    )
    assert record["historical_audit_boundary"] == {
        "v1_ledger": "IMMUTABLE_EXACT_AUDIT_RECORD",
        "v1_detached_approval": "IMMUTABLE_EXACT_AUDIT_RECORD",
        "predecessor_handoffs_approvals_and_proposal": "IMMUTABLE",
        "v1_exact_activation_authority_transfers_to_v2": False,
        "new_detached_owner_approval_created": False,
        "current_reversible_development_authority": "ROOT_AGENTS_STANDING_DEVELOPMENT_AUTHORIZATION",
    }
    assert record["open_decisions"] == []


def test_current_reconciliation_records_the_complete_live_integration_fixed_point() -> (
    None
):
    record = yaml.safe_load(REVIEWED_FINDINGS_RECONCILIATION_PATH.read_bytes())[
        "DESIGN_HANDOFF_V1"
    ]
    mechanical = record["mechanical_provenance"]
    direct_bindings = {
        "st_0202_contract_sha256": (
            "changes/st-0202/contracts/local-object-storage.v1.yaml"
        ),
        "st_0202_generator_sha256": "scripts/build_local_compose.py",
        "st_0202_runtime_wrapper_sha256": "scripts/object_storage_service.sh",
        "st_0202_wrapper_test_sha256": "tests/st0202/test_wrapper.py",
        "st_0306_contract_sha256": (
            "changes/st-0306/contracts/database-roles-grants.v1.yaml"
        ),
        "st_0306_generator_sha256": "scripts/build_st0306_database_roles.py",
        "st_0306_generated_revision_sha256": (
            "migrations/versions/202608030006_database_roles.py"
        ),
        "st_0306_generated_catalog_sha256": (
            "changes/st-0306/generated/database-roles-grants.v1.json"
        ),
        "st_0306_generated_validation_sha256": (
            "changes/st-0306/generated/database-roles-validation.v1.sql"
        ),
        "st_0306_generated_manifest_sha256": "changes/st-0306/manifest.yaml",
        "st_0307_contract_sha256": (
            "changes/st-0307/contracts/migration-upgrade-fixtures.v1.yaml"
        ),
        "st_0307_generator_sha256": "scripts/build_st0307_migration_fixtures.py",
        "st_0307_job_fixture_sha256": (
            "tests/fixtures/migrations/st0307/v0.1-job-alignment.v1.sql"
        ),
        "st_0307_ai_fixture_sha256": (
            "tests/fixtures/migrations/st0307/v0.2-ai-alignment.v1.sql"
        ),
        "st_0307_content_fixture_sha256": (
            "tests/fixtures/migrations/st0307/v0.3-content-alignment.v1.sql"
        ),
        "st_0307_predecessor_fixture_sha256": (
            "tests/fixtures/migrations/st0307/202608030005-predecessor.v1.sql"
        ),
        "st_0307_generated_catalog_sha256": (
            "changes/st-0307/generated/migration-upgrade-fixture-catalog.v1.json"
        ),
        "st_0307_generated_manifest_sha256": "changes/st-0307/manifest.yaml",
    }
    for field, relative in direct_bindings.items():
        assert (
            mechanical[field]
            == hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
        )

    chain = mechanical[
        "integrated_st0202_and_st0307_contracts_to_st0903_st0904_st0905_chain"
    ]
    downstream_bindings = {
        "st_0903_contract_sha256": (
            "changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml"
        ),
        "st_0903_generator_sha256": (
            "scripts/build_st0903_publication_snapshot_reference_plan.py"
        ),
        "st_0903_generated_plan_sha256": (
            "changes/st-0903/generated/publication-snapshot-reference-plan.v1.json"
        ),
        "st_0903_generated_manifest_sha256": "changes/st-0903/manifest.yaml",
        "st_0904_contract_sha256": (
            "changes/st-0904/contracts/public-projection-reference-plan.v1.yaml"
        ),
        "st_0904_generator_sha256": (
            "scripts/build_st0904_public_projection_reference_plan.py"
        ),
        "st_0904_generated_plan_sha256": (
            "changes/st-0904/generated/public-projection-reference-plan.v1.json"
        ),
        "st_0904_generated_manifest_sha256": "changes/st-0904/manifest.yaml",
        "st_0905_contract_sha256": (
            "changes/st-0905/contracts/publication-commands-reference-plan.v1.yaml"
        ),
        "st_0905_generator_sha256": (
            "scripts/build_st0905_publication_commands_reference_plan.py"
        ),
        "st_0905_generated_plan_sha256": (
            "changes/st-0905/generated/publication-commands-reference-plan.v1.json"
        ),
        "st_0905_generated_manifest_sha256": "changes/st-0905/manifest.yaml",
    }
    for field, relative in downstream_bindings.items():
        assert (
            chain[field]
            == hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
        )

    assert mechanical["combined_integration_additional_semantic_delta"] == {
        "story_id": "ST-0202",
        "decision": "EXACT_HOSTED_RUNTIME_VERSION_FIRST_LINE_CORRECTION",
        "expected_line": "version 30GB 4.29 1355c7a10 linux amd64",
        "full_image_revision_changed": False,
        "compose_changed": False,
        "od_014_changed": False,
    }
    assert mechanical["st0106_semantic_contract_delta"] == "NONE"


def test_secret_job_runs_the_exact_current_reconciliation_command() -> None:
    job = WORKFLOW["jobs"]["secrets"]
    expected_command = (
        'scripts/run_network_denied.sh --home "$HOME" -- '
        "/usr/bin/python3 -I scripts/scan_secrets.py "
        "--worktree --git-history --reviewed-findings "
        f"{REVIEWED_FINDINGS_RELATIVE_PATH}"
    )
    assert WORKFLOW_TEXT.count("--reviewed-findings") == 1
    assert WORKFLOW_TEXT.count(REVIEWED_FINDINGS_RELATIVE_PATH) == 1
    assert len(action_steps(job)) == 1
    assert run_steps(job) == [
        {
            "name": "Reproduce secret scan",
            "run": expected_command,
        }
    ]
    historical_approval = yaml.safe_load(REVIEWED_FINDINGS_APPROVAL_PATH.read_bytes())[
        "REVIEWED_SECRET_FINDINGS_APPROVAL_V1"
    ]
    assert historical_approval["authorized_activation"] == {
        "workflow_uri": "repo://.github/workflows/ci.yml",
        "job_id": "secrets",
        "step_name": "Reproduce secret scan",
        "exact_argument": (f"--reviewed-findings {REVIEWED_FINDINGS_V1_RELATIVE_PATH}"),
        "exact_command": (
            'scripts/run_network_denied.sh --home "$HOME" -- '
            "/usr/bin/python3 -I scripts/scan_secrets.py "
            "--worktree --git-history --reviewed-findings "
            f"{REVIEWED_FINDINGS_V1_RELATIVE_PATH}"
        ),
        "semantic_delta": "APPEND_EXACT_LEDGER_ARGUMENT_ONLY",
        "unrelated_job_semantics": "MUST_REMAIN_UNCHANGED",
        "ledger_bytes": "MUST_REMAIN_UNCHANGED",
        "scanner_bytes": "MUST_REMAIN_UNCHANGED",
    }
    assert REVIEWED_FINDINGS_V1_RELATIVE_PATH not in WORKFLOW_TEXT
    record = yaml.safe_load(REVIEWED_FINDINGS_RECONCILIATION_PATH.read_bytes())[
        "DESIGN_HANDOFF_V1"
    ]
    assert record["workflow_binding"]["new_exact_argument"] == (
        f"--reviewed-findings {REVIEWED_FINDINGS_RELATIVE_PATH}"
    )
    assert record["workflow_binding"]["scanner_bytes_and_rules"] == "UNCHANGED"


def test_database_job_runs_only_the_exact_st0201_runtime_wrapper() -> None:
    job = WORKFLOW["jobs"]["database"]
    assert job["name"] == "Database"
    assert len(action_steps(job)) == 1
    assert run_steps(job) == [
        {
            "name": "Verify exact PostgreSQL service",
            "run": ('scripts/postgres_service.sh --docker "$(command -v docker)" test'),
        }
    ]
    assert "scripts/run_network_denied.sh" not in run_steps(job)[0]["run"]


def test_storage_job_runs_only_the_exact_st0202_runtime_wrapper() -> None:
    job = WORKFLOW["jobs"]["storage"]
    assert job["name"] == "Storage"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == "20"
    assert len(action_steps(job)) == 1
    assert run_steps(job) == [
        {
            "name": "Verify exact object-storage service",
            "run": (
                'scripts/object_storage_service.sh --docker "$(command -v docker)" test'
            ),
        }
    ]
    command = run_steps(job)[0]["run"]
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
