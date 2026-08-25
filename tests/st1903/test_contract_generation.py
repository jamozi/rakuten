from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts import build_st1903_partial_auto_publication as builder


def test_contract_binds_canonical_story_and_dependency() -> None:
    contract = builder.load_contract()
    assert contract["document"]["canonical_implementation_status"] == (
        "DEFERRED_POST_MVP"
    )
    assert contract["predecessor"]["current_semantics"] == {
        "overall": "BLOCKED",
        "outcome": "NO_DECISION",
        "authorized": False,
        "acceptance_criteria_satisfied": False,
        "human_decision_required": True,
        "local_integration_complete": False,
    }


def test_outputs_are_deterministic_and_current(
    report_path: Path,
    manifest_path: Path,
) -> None:
    first = builder.build_outputs()
    second = builder.build_outputs()
    assert first == second
    assert report_path.read_bytes() == first[builder.REPORT_PATH]
    assert manifest_path.read_bytes() == first[builder.MANIFEST_PATH]


def test_report_and_manifest_are_non_attesting() -> None:
    outputs = builder.build_outputs()
    report = json.loads(outputs[builder.REPORT_PATH])
    manifest = yaml.safe_load(outputs[builder.MANIFEST_PATH])
    builder.validate_report(report)
    assert report["outcome"] == "REFUSED_DEPENDENCY_BLOCKED"
    assert report["positive_publication_outcome_exists"] is False
    assert all(value is False for value in report["authority"].values())
    assert manifest["boundary"]["activation"] == "DISABLED"
    assert manifest["boundary"]["publication_authority"] == "NONE"
    assert manifest["boundary"]["public_write_authority"] == "NONE"


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("outcome",), "PUBLISHED"),
        (("positive_publication_outcome_exists",), True),
        (("future_human_release_decision_required",), False),
        (("authority", "publication"), True),
        (("authority", "release"), True),
        (("actions",), [{"kind": "PUBLISH"}]),
        (("effects",), [{"kind": "PUBLIC_WRITE"}]),
        (("dependency", "overall"), "PASS"),
    ),
)
def test_report_promotion_is_rejected(
    path: tuple[str, ...], replacement: object
) -> None:
    report: dict[str, object] = json.loads(builder.build_report())
    mutated = deepcopy(report)
    target = mutated
    for key in path[:-1]:
        child = target[key]
        assert type(child) is dict
        target = child
    target[path[-1]] = replacement
    with pytest.raises(builder.PartialAutoPublicationBuildError):
        builder.validate_report(mutated)


def test_check_mode_is_no_write(report_path: Path, manifest_path: Path) -> None:
    before = (report_path.read_bytes(), manifest_path.read_bytes())
    assert builder.main(["--check"]) == 0
    after = (report_path.read_bytes(), manifest_path.read_bytes())
    assert after == before


def test_cli_requires_isolated_no_bytecode_mode() -> None:
    result = subprocess.run(
        [
            "/home/minami/rakuten/.venv/bin/python",
            str(builder.REPO_ROOT / builder.GENERATOR_PATH),
            "--check",
        ],
        cwd=builder.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "ISOLATED_MODE_REQUIRED" in result.stderr


@pytest.mark.parametrize("arguments", (["--chec"], ["--check", "--check"], ["x"]))
def test_cli_rejects_unreviewed_arguments(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        builder._parse_args(arguments)
    assert caught.value.code == 2
