"""Deterministic owner-generation tests for ST-1304."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st1304_cost_unit_economics_reference_plan as generator


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    assert first == generator.render_outputs()
    assert all(
        (generator.REPO_ROOT / path).read_bytes() == content
        for path, content in first.items()
    )


def test_check_mode_accepts_exact_outputs() -> None:
    assert generator.main(["--check"]) == 0


def _snapshot(path: Path) -> tuple[bytes, int, int]:
    metadata = path.stat()
    return path.read_bytes(), metadata.st_mtime_ns, stat.S_IMODE(metadata.st_mode)


def test_check_mode_is_no_write() -> None:
    paths = [generator.REPO_ROOT / path for path in generator.GENERATED_PATHS]
    before = {path: _snapshot(path) for path in paths}
    generator.build(check=True)
    assert {path: _snapshot(path) for path in paths} == before


def test_isolated_publication_is_atomic_0644_and_adjacent(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        assert path.is_file() and not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        assert not tuple(path.parent.glob(f".{path.name}.*.tmp"))
    generator.build(isolated_repository, check=True)


def test_manifest_binds_sources_dependencies_and_generated_plan() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["provenance"]["dependency_provenance"] == {
        "st0706": {
            "feature_commit": "fe867f85c68ea661b055f4edd32ef6fbc600fa68",
            "artifact_binding_commit": "f9428c375f19e478c7233dc78652ec518663dafa",
            "binding": "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT",
        },
        "st1205": {
            "feature_commit": "fe18734820cb6f78622950549d32f1ab5394214e",
            "artifact_binding_commit": "a3ea6d1a1e8621d9ff198c9dea31b0c6f7a768d5",
            "binding": "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT",
        },
        "st1303": {
            "feature_commit": "0436364b8737d05b9aea3a08da8bf15c04292b12",
            "artifact_binding_commit": "acdcc3719670c110bf6ec94af1762d87ac7fcb74",
            "binding": "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT",
        },
    }
    assert manifest["provenance"]["bound_inputs"] == generator._artifact_uri_rows(
        generator._contract_artifacts(generator.load_contract())
    )
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": generator._sha256(reference),
        }
    ]


def test_manifest_preserves_unknown_labor_and_null_values() -> None:
    boundary = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )["boundary"]
    assert all(
        boundary[key] is None
        for key in (
            *generator.COUNT_KEYS,
            *generator.TOTAL_KEYS,
            "hourly_cost_jpy",
            "allocation_rule",
            "calculation_version",
            "period_month",
            "source_watermarks",
            "rounding_policy",
            "persistence_policy",
        )
    )
    assert boundary["labor_cost_state"] == "UNKNOWN"
    assert boundary["unknown_labor_is_zero"] is False
    assert boundary["empty_means_zero"] is False
    assert boundary["vacuous_pass_allowed"] is False
    assert all(
        type(value) is int and value == 0
        for value in boundary["action_counts"].values()
    )


@pytest.mark.parametrize("relative", generator.GENERATED_PATHS)
def test_generated_or_manifest_drift_is_rejected(
    isolated_repository: Path, relative: Path
) -> None:
    generator.build(isolated_repository)
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"drift")
    with pytest.raises(generator.CostUnitEconomicsReferenceError):
        generator.build(isolated_repository, check=True)


def test_reference_plan_bytes_are_canonical_utf8_json() -> None:
    content = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n") and b"\r" not in content
    assert content == generator._json_bytes(json.loads(content))


@pytest.mark.parametrize(
    "arguments", [["--check=yes"], ["--unknown"], ["--check", "extra"]]
)
def test_cli_rejects_every_argument_except_exact_check(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        generator.parse_args(arguments)
    assert caught.value.code == 2
