"""Owner generation and drift checks for ST-1902."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import build_st1902_champion_challenger as generator


def _snapshot(paths: tuple[Path, ...]) -> tuple[bytes, ...]:
    return tuple(path.read_bytes() for path in paths)


def test_render_is_deterministic_and_matches_committed_outputs() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for relative, expected in first.items():
        target = generator.REPO_ROOT / relative
        assert target.is_file()
        assert not target.is_symlink()
        assert target.read_bytes() == expected


def test_check_is_read_only_and_cli_is_closed() -> None:
    paths = tuple(generator.REPO_ROOT / path for path in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    assert generator.main(["--check"]) == 0
    assert _snapshot(paths) == before
    for arguments in (["--check=yes"], ["--unknown"], ["--check", "extra"]):
        with pytest.raises(SystemExit) as caught:
            generator.parse_args(arguments)
        assert caught.value.code == 2


def test_generated_report_is_canonical_and_non_authoritative() -> None:
    content = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    parsed = json.loads(content)
    assert content == generator._canonical_output(parsed)
    assert parsed["document"] == {
        "authority": "NONE",
        "default_enabled": False,
        "id": "RAOS-ST1902-CHAMPION-CHALLENGER-SHADOW-REPORT-001",
        "production_eligible": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-1902",
        "version": "1.0.0",
    }
    assert parsed["formal_status"] == {
        "canonical": "DEFERRED_POST_MVP",
        "formal_tst_032": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
    }
    report = parsed["report"]
    assert report["authority"] == "NONE"
    assert report["canary_allocation_percent"] == 0
    assert report["outcome"].startswith("KEEP_CHAMPION_")
    assert report["boundary"]["route_mutation"] == "FORBIDDEN"
    assert report["boundary"]["editorial_mutation"] == "FORBIDDEN"
    assert report["boundary"]["publication"] == "FORBIDDEN"


def test_manifest_inventory_hashes_and_boundary_are_complete() -> None:
    loaded = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    assert loaded["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in loaded["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for row in loaded["source_artifacts"]:
        path = generator.REPO_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)
    report = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    assert loaded["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REPORT_PATH.as_posix()}",
            "bytes": len(report),
            "sha256": generator.sha256_bytes(report),
        }
    ]
    boundary = loaded["boundary"]
    assert boundary["default_enabled"] is False
    assert boundary["canary_allocation_percent"] == 0
    assert boundary["canary_reachable"] is False
    assert boundary["activation_interface_exists"] is False
    assert boundary["provider_called"] is False
    assert boundary["network_used"] is False
    assert boundary["route_mutated"] is False
    assert boundary["editorial_mutated"] is False
    assert boundary["publication_allowed"] is False
    assert boundary["release_authorized"] is False
    assert boundary["production_eligible"] is False
    assert loaded["debt"]["introduced"] == []


def test_check_outputs_rejects_generated_drift(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    outputs = generator.render_outputs()
    for relative, payload in outputs.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    generator.check_outputs(root, outputs)
    target = root / generator.REPORT_PATH
    target.write_bytes(target.read_bytes() + b"drift")
    with pytest.raises(generator.ChampionChallengerBuildError) as caught:
        generator.check_outputs(root, outputs)
    assert caught.value.code == "GENERATED_OUTPUT_DRIFT"


def test_secure_publication_builds_exact_outputs_in_isolated_copy(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    contract = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    required = set(generator.SOURCE_ARTIFACT_PATHS)
    for row in contract["authority"].values():
        if isinstance(row, dict) and "path" in row:
            required.add(Path(row["path"]))
    required.update(Path(path) for path in contract["predecessor"]["artifacts"])
    required.add(Path(contract["route_binding"]["catalog"]["path"]))
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPO_ROOT / relative, target)
    generator.build(root)
    generator.build(root, check=True)
    for relative, expected in generator.render_outputs(root).items():
        assert (root / relative).read_bytes() == expected
