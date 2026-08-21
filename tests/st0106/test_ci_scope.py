"""Focused tests for the ST-0106 affected-CI classifier."""

from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path

import pytest

from scripts import classify_ci_scope as classifier


SEMANTIC_HIGH_RISK_GLOBS = (
    "changes/st-04*/**",
    "changes/st-1603/**",
    "python/raos/domain/publishing/**",
    "python/raos/application/publishing/**",
    "python/raos/**/security.py",
    "scripts/*security*",
    "tests/st04*/**",
    "tests/st09*/**",
    "tests/st1603/**",
)


@pytest.fixture
def scope_contract() -> dict[str, object]:
    return classifier.load_contract()


def test_docs_only_selects_light_static_and_secrets(
    scope_contract: dict[str, object],
) -> None:
    result = classifier.classify_paths(
        "pull_request", ["docs/worklogs/ST-0804.md", "README.md"], scope_contract
    )
    assert result["mode"] == "affected"
    assert result["risk"] == "docs_only"
    assert result["jobs"] == ["Static", "Secrets"]
    assert result["job_modes"]["Static"] == "light"
    assert result["full_required"] is False


def test_single_story_selects_static_unit_and_secrets(
    scope_contract: dict[str, object],
) -> None:
    result = classifier.classify_paths(
        "pull_request",
        ["python/raos/domain/example.py", "tests/st0804/test_example.py"],
        scope_contract,
    )
    assert result["risk"] == "ordinary"
    assert result["story_suites"] == ["tests/st0804"]
    assert result["jobs"] == ["Static", "Unit", "Secrets"]
    assert result["job_modes"]["Unit"] == "focused"


@pytest.mark.parametrize(
    "paths,expected_risk",
    [
        ([".github/workflows/ci.yml"], "high"),
        (["contracts/schema.json"], "high"),
        (["migrations/next.sql"], "high"),
        (["changes/st-0804/database/next.sql"], "high"),
        (["tests/st0804/test_a.py", "tests/st0805/test_b.py"], "multi_story"),
        (["unclassified.bin"], "unknown"),
    ],
)
def test_risky_or_ambiguous_changes_fail_safe_to_full(
    scope_contract: dict[str, object], paths: list[str], expected_risk: str
) -> None:
    result = classifier.classify_paths("pull_request", paths, scope_contract)
    assert result["risk"] == expected_risk
    assert result["jobs"] == list(classifier.EXPECTED_JOBS)
    assert result["full_required"] is True


@pytest.mark.parametrize("event", ["push", "schedule", "workflow_dispatch"])
def test_non_pr_events_always_run_full(
    scope_contract: dict[str, object], event: str
) -> None:
    result = classifier.classify_paths(event, [], scope_contract)
    assert result["risk"] == "full_event"
    assert result["jobs"] == list(classifier.EXPECTED_JOBS)


def test_secret_path_name_is_not_returned(
    scope_contract: dict[str, object],
) -> None:
    sensitive = ".secrets/do-not-echo-this-name"
    with pytest.raises(classifier.SensitivePathChangedError) as captured:
        classifier.classify_paths("pull_request", [sensitive], scope_contract)
    assert captured.value.count == 1
    assert sensitive not in str(captured.value)


def test_secret_path_cli_fails_with_only_closed_reason_and_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sensitive = ".secrets/do-not-echo-this-name"
    assert (
        classifier.main(
            ["--event", "pull_request", "--path", sensitive, "--path", ".secrets/x"]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert sensitive not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "reason": "forbidden_secret_path_changed",
        "schema": "RAOS_CI_SCOPE_V1",
        "sensitive_path_count": 2,
        "status": "ERROR",
    }


@pytest.mark.parametrize(
    "path",
    [
        "scripts/build_st0104_contract_repository.py",
        "tests/st0104/test_verifier.py",
        "scripts/build_st0301_migration_framework.py",
        "tests/st0301/test_generation.py",
        "scripts/build_st0005_status.py",
        "tests/st0005/test_overlay_contract.py",
        "python/raos/application/iam/authentication.py",
        "python/raos/domain/iam/authorization.py",
        "python/raos/adapters/development_workload_credentials.py",
        "python/raos/adapters/wordpresscom_oauth.py",
        "python/raos/domain/publishing/review_workflow.py",
        "python/raos/application/publishing/review_decision.py",
        "tests/st0904/test_contract.py",
        "python/raos/domain/http/security.py",
        "python/raos/application/http/security.py",
        "tests/st0401/test_authentication.py",
        "scripts/build_st1603_security_verification_pack.py",
        "tests/st1603/test_contract.py",
    ],
)
def test_mandatory_taxonomy_examples_are_high_risk(
    scope_contract: dict[str, object], path: str
) -> None:
    result = classifier.classify_paths("pull_request", [path], scope_contract)
    assert result["risk"] == "high"
    assert result["full_required"] is True
    assert result["jobs"] == list(classifier.EXPECTED_JOBS)


def test_every_versioned_taxonomy_representative_is_high_risk(
    scope_contract: dict[str, object],
) -> None:
    categories = scope_contract["mandatory_high_risk_categories"]
    assert isinstance(categories, dict)
    for category_name, raw_category in categories.items():
        assert isinstance(category_name, str)
        assert isinstance(raw_category, dict)
        representatives = raw_category["representative_paths"]
        assert isinstance(representatives, list)
        for path in representatives:
            assert isinstance(path, str)
            assert category_name in classifier.high_risk_categories(
                path, scope_contract
            )
            result = classifier.classify_paths("pull_request", [path], scope_contract)
            assert result["risk"] == "high"
            assert result["full_required"] is True


def test_every_tracked_publication_or_security_surface_is_high_risk(
    scope_contract: dict[str, object],
) -> None:
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=classifier.REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    semantic_paths = sorted(
        path
        for path in tracked
        if path
        and any(
            fnmatch.fnmatchcase(path, pattern) for pattern in SEMANTIC_HIGH_RISK_GLOBS
        )
    )

    assert semantic_paths
    assert [
        path
        for path in semantic_paths
        if not classifier.high_risk_categories(path, scope_contract)
    ] == []


def test_github_output_contains_every_required_job_without_path_material(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "github-output"
    result = classifier.main(
        [
            "--event",
            "pull_request",
            "--path",
            "tests/st0804/test_example.py",
            "--github-output",
            str(output),
        ]
    )
    assert result == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["jobs"] == ["Static", "Unit", "Secrets"]
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["static"] == "true"
    assert values["unit"] == "true"
    assert values["contracts"] == "false"
    assert values["database"] == "false"
    assert values["storage"] == "false"
    assert values["secrets"] == "true"
    assert values["static_mode"] == "full"
    assert values["unit_mode"] == "focused"
    assert values["story_suite"] == "tests/st0804"


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_git_rename_classifies_both_endpoints(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "st0106@example.invalid")
    _git(tmp_path, "config", "user.name", "ST-0106")
    source = tmp_path / "tests/st0804/test_old.py"
    source.parent.mkdir(parents=True)
    source.write_text("old = True\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(tmp_path, "mv", "tests/st0804/test_old.py", "tests/st0804/test_new.py")
    _git(tmp_path, "commit", "-qam", "rename")

    assert classifier.git_changed_paths(tmp_path, base, "HEAD") == [
        "tests/st0804/test_new.py",
        "tests/st0804/test_old.py",
    ]


def test_contract_duplicate_key_is_rejected(tmp_path: Path) -> None:
    contract = tmp_path / classifier.CONTRACT_PATH
    contract.parent.mkdir(parents=True)
    contract.write_text('{"document": {}, "document": {}}', encoding="utf-8")
    with pytest.raises(classifier.ClassificationError, match="duplicate JSON key"):
        classifier.load_contract(tmp_path)


def test_generator_check_and_output_story_sets_must_match(tmp_path: Path) -> None:
    contract = classifier.load_contract()
    contract["generator_owned_outputs"] = {}
    path = tmp_path / classifier.CONTRACT_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(
        classifier.ClassificationError,
        match="generator check and output stories differ",
    ):
        classifier.load_contract(tmp_path)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("story_path_patterns", ["changes/{digits}/"], "story path patterns differ"),
        ("node_suffixes", [".js"], "Node suffix inventory differs"),
        ("mandatory_high_risk_categories", {}, "category inventory differs"),
    ],
)
def test_behavioral_contract_fields_are_bound_fail_closed(
    tmp_path: Path, field: str, value: object, error: str
) -> None:
    contract = classifier.load_contract()
    contract[field] = value
    path = tmp_path / classifier.CONTRACT_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(classifier.ClassificationError, match=error):
        classifier.load_contract(tmp_path)
