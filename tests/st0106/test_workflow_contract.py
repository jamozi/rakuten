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
HISTORICAL_REVIEWED_FINDINGS_RELATIVE_PATH = (
    "changes/st-0106/contracts/reviewed-secret-findings.v1.yaml"
)
HISTORICAL_REVIEWED_FINDINGS_PATH = (
    REPOSITORY_ROOT / HISTORICAL_REVIEWED_FINDINGS_RELATIVE_PATH
)
REVIEWED_FINDINGS_RELATIVE_PATH = (
    "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
)
REVIEWED_FINDINGS_PATH = REPOSITORY_ROOT / REVIEWED_FINDINGS_RELATIVE_PATH
HISTORICAL_REVIEWED_FINDINGS_APPROVAL_PATH = (
    REPOSITORY_ROOT / "changes/st-0106/REVIEWED-SECRET-FINDINGS-APPROVAL-v1.yaml"
)
REVIEWED_FINDINGS_RECONCILIATION_PATH = (
    REPOSITORY_ROOT / "changes/st-0106/REVIEWED-SECRET-FINDINGS-RECONCILIATION-v2.yaml"
)
ORIGIN_REF_INVENTORY_RELATIVE_PATH = (
    "changes/st-0106/contracts/origin-ref-inventory.v2.txt"
)
ORIGIN_REF_INVENTORY_PATH = REPOSITORY_ROOT / ORIGIN_REF_INVENTORY_RELATIVE_PATH
STANDING_AUTHORITY_PATH = REPOSITORY_ROOT / "AGENTS.md"
SCANNER_PATH = REPOSITORY_ROOT / "scripts/scan_secrets.py"
NETWORK_WRAPPER_PATH = REPOSITORY_ROOT / "scripts/run_network_denied.sh"
CI_WRAPPER_PATH = REPOSITORY_ROOT / "scripts/ci_job.sh"
EXPECTED_HISTORICAL_REVIEWED_FINDINGS_BYTES = 46295
EXPECTED_HISTORICAL_REVIEWED_FINDINGS_SHA256 = (
    "1038cf6ef81da0acab528cf8206086646b6e003f5ac0ceed4f2e4b994827bcc7"
)
EXPECTED_HISTORICAL_REVIEWED_FINDINGS_APPROVAL_BYTES = 5524
EXPECTED_HISTORICAL_REVIEWED_FINDINGS_APPROVAL_SHA256 = (
    "b683ae3b3b7312bd4ce04fe2c796f1157542f72c1b1bca79919a71b3a7c1acd9"
)
EXPECTED_REVIEWED_FINDINGS_BYTES = 59769
EXPECTED_REVIEWED_FINDINGS_SHA256 = (
    "667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b"
)
EXPECTED_RECONCILIATION_BYTES = 5962
EXPECTED_RECONCILIATION_SHA256 = (
    "661b480563b2ee3e087ddbc7adf0e3db756130f00ba94cf76bd16f703a3eaa63"
)
EXPECTED_ORIGIN_REF_INVENTORY_BYTES = 6577
EXPECTED_ORIGIN_REF_INVENTORY_SHA256 = (
    "06aeb60e8bebdd0e1496951890a60eb52b74c8241820cccd953777b3ff12889d"
)
EXPECTED_ORIGIN_REF_ENTRIES_SHA256 = (
    "2a04841be9d2af3c0926adcba9bb7eb8940d0f432c9d62e8e65a5c13b217de28"
)
EXPECTED_STANDING_AUTHORITY_BYTES = 43916
EXPECTED_STANDING_AUTHORITY_SHA256 = (
    "a4b8f16d0a6ef073899381ee90597495b4264fc271bf9142f8866561f14ba482"
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


def test_historical_reviewed_findings_v1_authority_remains_byte_exact() -> None:
    ledger_bytes = HISTORICAL_REVIEWED_FINDINGS_PATH.read_bytes()
    assert len(ledger_bytes) == EXPECTED_HISTORICAL_REVIEWED_FINDINGS_BYTES
    assert (
        hashlib.sha256(ledger_bytes).hexdigest()
        == EXPECTED_HISTORICAL_REVIEWED_FINDINGS_SHA256
    )
    ledger = json.loads(ledger_bytes)
    assert set(ledger) == {"version", "status", "rule_id", "entries"}
    assert ledger["version"] == 1
    assert ledger["status"] == "UNAPPROVED_CANDIDATE"
    assert ledger["rule_id"] == "GENERIC_CREDENTIAL"
    assert len(ledger["entries"]) == 89
    assert sum(entry["scope"] == "worktree" for entry in ledger["entries"]) == 31
    assert sum(entry["scope"] == "git_history" for entry in ledger["entries"]) == 58

    approval_bytes = HISTORICAL_REVIEWED_FINDINGS_APPROVAL_PATH.read_bytes()
    assert len(approval_bytes) == EXPECTED_HISTORICAL_REVIEWED_FINDINGS_APPROVAL_BYTES
    assert (
        hashlib.sha256(approval_bytes).hexdigest()
        == EXPECTED_HISTORICAL_REVIEWED_FINDINGS_APPROVAL_SHA256
    )
    document = yaml.safe_load(approval_bytes)
    assert set(document) == {"REVIEWED_SECRET_FINDINGS_APPROVAL_V1"}
    approval = document["REVIEWED_SECRET_FINDINGS_APPROVAL_V1"]
    assert approval["ledger_uri"] == (
        f"repo://{HISTORICAL_REVIEWED_FINDINGS_RELATIVE_PATH}"
    )
    assert approval["ledger_bytes"] == EXPECTED_HISTORICAL_REVIEWED_FINDINGS_BYTES
    assert approval["ledger_sha256"] == EXPECTED_HISTORICAL_REVIEWED_FINDINGS_SHA256
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
    prerequisites = approval["prerequisite_authority"]
    for prefix in ("handoff", "detached_handoff_approval", "proposal"):
        source = repository_path_from_uri(prerequisites[f"{prefix}_uri"])
        content = source.read_bytes()
        assert len(content) == prerequisites[f"{prefix}_bytes"]
        assert hashlib.sha256(content).hexdigest() == prerequisites[f"{prefix}_sha256"]
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


def test_candidate_v2_ledger_has_exact_standing_authority_reconciliation() -> None:
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

    reconciliation_bytes = REVIEWED_FINDINGS_RECONCILIATION_PATH.read_bytes()
    assert len(reconciliation_bytes) == EXPECTED_RECONCILIATION_BYTES
    assert (
        hashlib.sha256(reconciliation_bytes).hexdigest()
        == EXPECTED_RECONCILIATION_SHA256
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
        "standing_authority",
        "immutable_historical_inputs",
        "candidate_ledger",
        "frozen_security_implementation",
        "integration_base",
        "history_universe",
        "sanitized_review",
        "pr_49_v3_non_adoption",
        "boundaries",
        "self_reference_boundary",
    }
    assert reconciliation["story_id"] == "ST-0106"
    assert reconciliation["status"] == (
        "STANDING_DEVELOPMENT_AUTHORITY_RECONCILED_LOCAL_CANDIDATE"
    )
    assert reconciliation["reconciliation_classification"] == (
        "MECHANICAL_EXACT_HEAD_LEDGER_REBINDING"
    )
    assert reconciliation["canonical_status"] == "UNCHANGED"
    assert reconciliation["open_decisions"] == []
    authority_bytes = STANDING_AUTHORITY_PATH.read_bytes()
    assert len(authority_bytes) == EXPECTED_STANDING_AUTHORITY_BYTES
    assert hashlib.sha256(authority_bytes).hexdigest() == (
        EXPECTED_STANDING_AUTHORITY_SHA256
    )
    assert reconciliation["standing_authority"] == {
        "uri": "repo://AGENTS.md",
        "bytes": len(authority_bytes),
        "sha256": hashlib.sha256(authority_bytes).hexdigest(),
        "authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
        "scope": "REVERSIBLE_REPOSITORY_DEVELOPMENT_ONLY",
        "owner_review_claim": "NONE_BEYOND_STANDING_AUTHORIZATION",
        "external_authority": "NONE",
    }
    assert reconciliation["immutable_historical_inputs"] == [
        {
            "uri": f"repo://{HISTORICAL_REVIEWED_FINDINGS_RELATIVE_PATH}",
            "bytes": EXPECTED_HISTORICAL_REVIEWED_FINDINGS_BYTES,
            "sha256": EXPECTED_HISTORICAL_REVIEWED_FINDINGS_SHA256,
            "mutation": "FORBIDDEN",
        },
        {
            "uri": ("repo://changes/st-0106/REVIEWED-SECRET-FINDINGS-APPROVAL-v1.yaml"),
            "bytes": EXPECTED_HISTORICAL_REVIEWED_FINDINGS_APPROVAL_BYTES,
            "sha256": EXPECTED_HISTORICAL_REVIEWED_FINDINGS_APPROVAL_SHA256,
            "mutation": "FORBIDDEN",
        },
    ]
    candidate = reconciliation["candidate_ledger"]
    assert {key: candidate[key] for key in candidate if key != "workflow_binding"} == {
        "uri": f"repo://{REVIEWED_FINDINGS_RELATIVE_PATH}",
        "bytes": EXPECTED_REVIEWED_FINDINGS_BYTES,
        "sha256": EXPECTED_REVIEWED_FINDINGS_SHA256,
        "ledger_version": 1,
        "internal_status": "UNAPPROVED_CANDIDATE",
        "rule_id": "GENERIC_CREDENTIAL",
        "entry_count": 115,
        "scope_counts": {"worktree": 31, "git_history": 84},
        "scanner_semantics": "UNCHANGED_BROAD_GENERIC_DETECTION",
    }
    frozen = reconciliation["frozen_security_implementation"]
    assert len(frozen) == len(EXPECTED_FROZEN_SECURITY_IMPLEMENTATION)
    for row in frozen:
        relative = row["uri"].removeprefix("repo://")
        expected_bytes, expected_sha256 = EXPECTED_FROZEN_SECURITY_IMPLEMENTATION[
            relative
        ]
        content = repository_path_from_uri(row["uri"]).read_bytes()
        assert row == {
            "uri": f"repo://{relative}",
            "bytes": expected_bytes,
            "sha256": expected_sha256,
            "mutation": "FORBIDDEN",
        }
        assert len(content) == expected_bytes
        assert hashlib.sha256(content).hexdigest() == expected_sha256
    assert {
        SCANNER_PATH,
        NETWORK_WRAPPER_PATH,
        CI_WRAPPER_PATH,
    } == {repository_path_from_uri(row["uri"]) for row in frozen}
    assert reconciliation["integration_base"] == {
        "commit": "edf9ef8201718e8c128aa3fe445d4c5a1b4580f4",
        "tree": "705bff193a86ef6e6de03567c3025c7d54e4e774",
    }
    history = reconciliation["history_universe"]
    inventory_bytes = ORIGIN_REF_INVENTORY_PATH.read_bytes()
    assert len(inventory_bytes) == EXPECTED_ORIGIN_REF_INVENTORY_BYTES
    assert (
        hashlib.sha256(inventory_bytes).hexdigest()
        == EXPECTED_ORIGIN_REF_INVENTORY_SHA256
    )
    inventory_lines = inventory_bytes.decode("utf-8").splitlines()
    assert inventory_lines[:10] == [
        "format RAOS_ST0106_ORIGIN_REF_INVENTORY_V2",
        (
            "command git for-each-ref --format='%(refname) %(objectname)' "
            "refs/remotes/origin refs/tags | LC_ALL=C sort"
        ),
        "remote_name origin",
        "fetch_heads +refs/heads/*:refs/remotes/origin/*",
        "fetch_tags +refs/tags/*:refs/tags/*",
        "fetch_depth 0",
        "head_ref_count 44",
        "tag_ref_count 17",
        f"entries_sha256 {EXPECTED_ORIGIN_REF_ENTRIES_SHA256}",
        "entries",
    ]
    inventory_entries = inventory_lines[10:]
    assert inventory_entries == sorted(inventory_entries)
    assert len(inventory_entries) == len(set(inventory_entries)) == 61
    assert all(
        re.fullmatch(r"refs/(?:remotes/origin|tags)/[^ ]+ [0-9a-f]{40}", entry)
        for entry in inventory_entries
    )
    assert (
        sum(entry.startswith("refs/remotes/origin/") for entry in inventory_entries)
        == 44
    )
    assert sum(entry.startswith("refs/tags/") for entry in inventory_entries) == 17
    inventory_entry_bytes = ("\n".join(inventory_entries) + "\n").encode("utf-8")
    assert hashlib.sha256(inventory_entry_bytes).hexdigest() == (
        EXPECTED_ORIGIN_REF_ENTRIES_SHA256
    )
    assert history == {
        "reconstruction": "PHYSICAL_STANDALONE_ORIGIN_REFS_PLUS_TAGS_FETCH_DEPTH_0",
        "physical_git_directory": True,
        "shared_object_store": False,
        "alternates": False,
        "shallow": False,
        "origin_head_ref_count": 44,
        "tag_ref_count": 17,
        "refs_snapshot_sha256": (EXPECTED_ORIGIN_REF_ENTRIES_SHA256),
        "ref_inventory": {
            "uri": f"repo://{ORIGIN_REF_INVENTORY_RELATIVE_PATH}",
            "bytes": EXPECTED_ORIGIN_REF_INVENTORY_BYTES,
            "sha256": EXPECTED_ORIGIN_REF_INVENTORY_SHA256,
            "format": "RAOS_ST0106_ORIGIN_REF_INVENTORY_V2",
            "canonical_command": (
                "git for-each-ref --format='%(refname) %(objectname)' "
                "refs/remotes/origin refs/tags | LC_ALL=C sort"
            ),
            "entries_sha256": EXPECTED_ORIGIN_REF_ENTRIES_SHA256,
            "provenance": "EXACT_TRACKED_VALUE_FREE_INVENTORY",
        },
        "checkout_commit": "edf9ef8201718e8c128aa3fe445d4c5a1b4580f4",
        "checkout_tree": "705bff193a86ef6e6de03567c3025c7d54e4e774",
        "origin_main_commit": "f733200d5b801a417d2f220e24efb9394f616be4",
        "origin_main_tree": "60bbeb3a0d319b4a348f1cdeed824218289149c7",
    }
    assert reconciliation["sanitized_review"] == {
        "metadata_fields": [
            "rule_id",
            "source_kind",
            "path_or_blob",
            "line",
            "source_bytes",
            "source_sha256",
            "line_sha256",
        ],
        "individual_metadata_review": "PASS",
        "matched_values_read_by_reviewer": False,
        "matched_values_persisted": False,
        "total_reviewed": 115,
        "worktree_reviewed": 31,
        "git_history_reviewed": 84,
        "generic_credential_reviewed": 115,
        "specific_rule_findings": {
            "aws_access_key": 0,
            "github_token": 0,
            "openai_key": 0,
            "private_key": 0,
        },
        "genuinely_credential_like_unexplained": "NONE_IDENTIFIED",
        "all_current_line_hashes_previously_reviewed_in_v1": True,
        "v1_history_bindings_retained": 58,
        "new_history_bindings_with_prior_line_hash": 26,
        "current_worktree_bindings_with_prior_line_hash": 31,
    }
    assert reconciliation["pr_49_v3_non_adoption"] == {
        "pull_request": 49,
        "head_branch": "codex/st-0106-base-ci-recovery-v3",
        "head_commit": "43388c5114014a7243f0e37f8241b9402e778522",
        "runtime_adoption": "NOT_ADOPTED",
        "v3_scanner_ast_entropy_rhs_behavior": "NOT_ADOPTED",
        "historical_authority_artifact_count": 9,
        "historical_authority_artifacts_imported": 0,
        "reason": "CONFLICTS_WITH_LATER_BROAD_LEDGER_SECURITY_POLICY",
    }
    assert reconciliation["boundaries"] == {
        "ledger_revision": "REPOSITORY_LOCAL_ONLY",
        "workflow_rebinding": "LOCAL_CANDIDATE_BYTES_ONLY",
        "github_workflow_activation": "NOT_EXECUTED",
        "activation_status": "BLOCKED",
        "active_provenance_closure": "MECHANICAL_ONLY",
        "scanner_semantic_change": "FORBIDDEN",
        "specific_rule_suppression": "FORBIDDEN",
        "canonical_or_status_mutation": "NONE",
        "credential_or_secret_authority": "NONE",
        "external_write_authority": "NONE",
        "hosted_ci": "NOT_EXECUTED",
        "formal_tst_001": "NOT_EXECUTED",
        "formal_tst_002": "NOT_EXECUTED",
        "push_pull_request_or_merge_authority": "NONE_IN_THIS_RECORD",
        "staging_release_or_production_authority": "NONE",
    }
    assert reconciliation["self_reference_boundary"] == {
        "tracked_record_final_commit_binding": (
            "IMPOSSIBLE_BY_SELF_REFERENCE_AND_NOT_CLAIMED"
        ),
        "final_commit_and_tree": "REPORTED_OUTSIDE_TRACKED_RECORD",
        "post_commit_standalone_replay": "NOT_EXECUTED",
        "handoff_status": "BLOCKED_UNTIL_EXACT_POST_COMMIT_STANDALONE_REPLAY",
    }


def test_v2_ledger_continuity_is_derived_and_control_sources_are_not_reviewed() -> None:
    v1 = json.loads(HISTORICAL_REVIEWED_FINDINGS_PATH.read_bytes())
    v2 = json.loads(REVIEWED_FINDINGS_PATH.read_bytes())
    v1_entries = v1["entries"]
    v2_entries = v2["entries"]

    for entries in (v1_entries, v2_entries):
        keys = [reviewed_finding_key(entry) for entry in entries]
        assert len(keys) == len(set(keys))

    def exact_entry(entry: dict[str, Any]) -> str:
        return json.dumps(entry, sort_keys=True, separators=(",", ":"))

    v1_history = {
        exact_entry(entry) for entry in v1_entries if entry["scope"] == "git_history"
    }
    v2_history = {
        exact_entry(entry) for entry in v2_entries if entry["scope"] == "git_history"
    }
    assert len(v1_history) == 58
    assert v1_history < v2_history
    history_delta = [
        entry
        for entry in v2_entries
        if entry["scope"] == "git_history" and exact_entry(entry) not in v1_history
    ]
    assert len(history_delta) == 26
    v1_line_hashes = {entry["exact_line_sha256"] for entry in v1_entries}
    assert all(entry["exact_line_sha256"] in v1_line_hashes for entry in history_delta)

    v1_worktree_line_hashes = {
        entry["exact_line_sha256"]
        for entry in v1_entries
        if entry["scope"] == "worktree"
    }
    v2_worktree = [entry for entry in v2_entries if entry["scope"] == "worktree"]
    assert len(v2_worktree) == 31
    assert all(
        entry["exact_line_sha256"] in v1_worktree_line_hashes for entry in v2_worktree
    )

    reviewed_worktree_paths = {
        entry["exact_source_identifier"] for entry in v2_worktree
    }
    control_sources = {
        "AGENTS.md",
        ".github/workflows/ci.yml",
        "scripts/scan_secrets.py",
        "scripts/run_network_denied.sh",
        "scripts/ci_job.sh",
        "tests/st0106/test_workflow_contract.py",
        "changes/st-0106/README.md",
        "docs/execplans/ST-0106.md",
        "docs/worklogs/ST-0106.md",
        HISTORICAL_REVIEWED_FINDINGS_RELATIVE_PATH,
        REVIEWED_FINDINGS_RELATIVE_PATH,
        "changes/st-0106/REVIEWED-SECRET-FINDINGS-APPROVAL-v1.yaml",
        "changes/st-0106/REVIEWED-SECRET-FINDINGS-RECONCILIATION-v2.yaml",
        ORIGIN_REF_INVENTORY_RELATIVE_PATH,
    }
    assert reviewed_worktree_paths.isdisjoint(control_sources)


def test_secret_job_runs_the_exact_approved_local_history_command() -> None:
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
    reconciliation = yaml.safe_load(REVIEWED_FINDINGS_RECONCILIATION_PATH.read_bytes())[
        "REVIEWED_SECRET_FINDINGS_RECONCILIATION_V2"
    ]
    assert reconciliation["candidate_ledger"]["workflow_binding"] == {
        "workflow_uri": "repo://.github/workflows/ci.yml",
        "job_id": "secrets",
        "step_name": "Reproduce secret scan",
        "exact_argument": f"--reviewed-findings {REVIEWED_FINDINGS_RELATIVE_PATH}",
        "exact_command": expected_command,
        "semantic_delta": "REBIND_EXACT_LEDGER_PATH_ONLY",
        "unrelated_job_semantics": "UNCHANGED",
        "repository_workflow_binding": "PRESENT_IN_LOCAL_CANDIDATE_BYTES",
        "github_workflow_activation": "NOT_EXECUTED",
        "activation_gate": "BLOCKED_UNTIL_EXACT_POST_COMMIT_STANDALONE_REPLAY",
    }


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
