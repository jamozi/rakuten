"""Deterministic owner-generation tests for ST-1305."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st1305_finance_reconciliation_reference_plan as generator


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


def test_manifest_binds_sources_dependency_and_generated_plan() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["provenance"]["dependency_provenance"] == {
        "st1304": {
            "feature_commit": "6c73e41d630657138d8f51752d8cd1541026a0f1",
            "artifact_binding_commit": "6c73e41d630657138d8f51752d8cd1541026a0f1",
            "binding": "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT",
        }
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


def test_manifest_preserves_unknown_and_null_values() -> None:
    boundary = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )["boundary"]
    assert all(
        boundary[key] is None
        for key in (
            *generator.COUNT_KEYS,
            *generator.TOTAL_KEYS,
            "provider_report_schema",
            "revenue_import_batch_identity",
            "reconciliation_tolerance",
            "rounding_policy",
            "exception_schema",
            "approval_policy",
            "audit_policy",
            "evidence_format",
            "retention_policy",
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
    with pytest.raises(generator.FinanceReconciliationReferenceError):
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
