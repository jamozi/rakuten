"""Reproducibility and closed-contract tests for ST-1604 V2 runtime artifacts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import stat

import pytest

from scripts import build_st1604_local_performance_load as generator


def test_render_is_deterministic_and_matches_installed_artifacts() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_check_mode_is_no_write_and_outputs_are_regular_0644() -> None:
    paths = [generator.REPO_ROOT / path for path in generator.GENERATED_PATHS]
    before = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    generator.build(check=True)
    after = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    assert after == before
    assert all(row[2] == 0o644 for row in after.values())


def test_generated_report_is_local_only_and_has_all_four_surfaces() -> None:
    report = json.loads((generator.REPO_ROOT / generator.REPORT_PATH).read_bytes())
    assert report["report_status"] == "LOCAL_CAPACITY_DOCUMENTED"
    assert [row["surface"] for row in report["evaluations"]] == [
        "PUBLIC",
        "ADMIN",
        "API",
        "WORKER",
    ]
    assert report["formal_tst_027"] == "NOT_EXECUTED"
    assert report["production_capacity_claim"] is None
    assert report["production_eligible"] is False
    assert set(report["action_counts"].values()) == {0}


def test_manifest_binds_sources_predecessors_authority_and_report() -> None:
    manifest = json.loads((generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert generator.DOMAIN_INIT_PATH in generator.SOURCE_PATHS
    assert generator.APPLICATION_INIT_PATH in generator.SOURCE_PATHS
    assert [row["uri"] for row in manifest["predecessor_inputs"]] == [
        f"repo://{path.as_posix()}" for path in generator.PREDECESSOR_PATHS
    ]
    assert len(manifest["authority_inputs"]) == 5
    assert manifest["safety_boundary"]["recorded_capture_enabled"] is False
    assert manifest["safety_boundary"]["rollback_detection_scope"] == (
        "LIVE_JOURNAL_INSTANCE_ONLY_NO_EXTERNAL_DURABLE_ANCHOR"
    )
    report = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "bytes": len(report),
            "sha256": generator._sha256(report),
            "uri": f"repo://{generator.REPORT_PATH.as_posix()}",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b'{"document":{},"document":{}}',
        b'{"document":1.5}',
        b'{"document":NaN}',
        b"\xff",
    ],
)
def test_duplicate_float_constant_and_non_utf8_json_fail_closed(payload: bytes) -> None:
    with pytest.raises(generator.LocalPerformanceLoadBuildError):
        generator._json_document(payload)


def test_contract_unknown_field_and_fixture_digest_drift_fail_closed() -> None:
    contract = deepcopy(generator.load_contract())
    contract["unknown"] = None
    with pytest.raises(generator.LocalPerformanceLoadBuildError):
        generator._request_from_contract(contract)
    contract = deepcopy(generator.load_contract())
    contract["observations"][0]["duration_samples_ms"][0] += 1
    with pytest.raises(generator.LocalPerformanceLoadBuildError) as caught:
        generator._request_from_contract(contract)
    assert str(caught.value) == "ST1604_LOCAL_BUILD_FIXTURE_DIGEST_INVALID"


@pytest.mark.parametrize(
    "value",
    [
        "{16040000-0000-4000-8000-000000000001}",
        "SECRET-UUID-MATERIAL",
    ],
)
def test_contract_uuid_must_be_exact_canonical_text(value: str) -> None:
    contract = deepcopy(generator.load_contract())
    contract["request"]["run_id"] = value
    with pytest.raises(generator.LocalPerformanceLoadBuildError) as caught:
        generator._request_from_contract(contract)
    assert str(caught.value) == "ST1604_LOCAL_BUILD_UUID_INVALID"
    assert value not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_manifest_and_report_are_canonical_ascii_json() -> None:
    for relative in generator.GENERATED_PATHS:
        content = (generator.REPO_ROOT / relative).read_bytes()
        assert content.endswith(b"\n")
        assert b"\r" not in content
        content.decode("ascii")
        parsed = json.loads(content)
        assert content == generator._canonical_json_bytes(parsed)


def test_builder_has_no_external_target_or_runtime_selection() -> None:
    contract = generator.load_contract()
    serialized = json.dumps(contract, sort_keys=True).lower()
    for forbidden in (
        "https://",
        "authorization",
        "bearer",
        "credential_material",
        "selected_provider",
        "production_ready",
    ):
        assert forbidden not in serialized


def test_v2_output_symlink_is_rejected_without_touching_target(
    tmp_path: Path,
) -> None:
    output_parent = tmp_path / "generated"
    output_parent.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    linked = output_parent / "report.json"
    linked.symlink_to(outside)
    with pytest.raises(generator.LocalPerformanceLoadBuildError):
        generator._output_path(tmp_path, Path("generated/report.json"), create=True)
    assert outside.read_bytes() == b"outside"
