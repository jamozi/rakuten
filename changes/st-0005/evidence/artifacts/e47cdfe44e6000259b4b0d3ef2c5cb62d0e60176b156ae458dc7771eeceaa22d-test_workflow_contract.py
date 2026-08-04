"""Static contract checks for the ST-0106 base CI workflow."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/ci.yml"
WORKFLOW_TEXT = WORKFLOW_PATH.read_text(encoding="utf-8")
WORKFLOW: dict[str, Any] = yaml.load(WORKFLOW_TEXT, Loader=yaml.BaseLoader)
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
        reproduce_command = (
            "set -euo pipefail\n"
            'node_path="$(command -v node)"\n'
            'node_prefix="$(dirname "$(dirname "$node_path")")"\n'
            'scripts/run_network_denied.sh --home "$HOME" -- \\\n'
            '  "$GITHUB_WORKSPACE/scripts/ci_job.sh" \\\n'
            '  --uv "$(command -v uv)" \\\n'
            '  --node "$node_path" \\\n'
            '  --npm-cli "$node_prefix/lib/node_modules/npm/bin/npm-cli.js" \\\n'
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
        for token in (
            '"$uv_path" --no-config --color never sync --locked',
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


def test_secret_job_runs_the_exact_local_history_command() -> None:
    job = WORKFLOW["jobs"]["secrets"]
    assert len(action_steps(job)) == 1
    assert run_steps(job) == [
        {
            "name": "Reproduce secret scan",
            "run": (
                'scripts/run_network_denied.sh --home "$HOME" -- '
                "/usr/bin/python3 -I scripts/scan_secrets.py "
                "--worktree --git-history"
            ),
        }
    ]


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
        "tests/st0301",
    )
    assert unit_recipe.count("pytest -p no:cacheprovider -q") == len(expected_suites)
    for suite in expected_suites:
        matches = re.findall(rf"(?m)^.*(?<!\S){re.escape(suite)}(?:\s|$)", unit_recipe)
        assert len(matches) == 1
    for story in ("st0002", "st0003", "st0004"):
        assert (
            f"tests/{story} --ignore=tests/{story}/test_postgresql_migration.py"
            in unit_recipe
        )


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
    policy_header = next(
        line
        for line in makefile.splitlines()
        if line.startswith("ci-repository-policy:")
    )
    assert "local-compose-check" in policy_header
    assert "queue-check" in policy_header
    assert "config-check" in policy_header
    assert "migration-check" in policy_header
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
        "\npostgres-generate:", 1
    )[0]

    assert "scripts/build_st0301_migration_framework.py" in generate_block
    assert "scripts/build_st0301_migration_framework.py --check" in check_block
    assert "tests/st0301" in test_block
    assert (
        "migration-check"
        in makefile.split("\nci-repository-policy:", 1)[1].split("\nci-static:", 1)[0]
    )
    assert "migration:" not in workflow


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
