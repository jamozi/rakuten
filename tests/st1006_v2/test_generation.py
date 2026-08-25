"""Owner-generator and fail-closed checks for ST-1006 V2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_st1006_public_performance_runtime as builder


ROOT = Path(__file__).resolve().parents[2]


def test_expected_artifacts_are_current_and_check_is_read_only() -> None:
    artifacts = builder.expected_artifacts(ROOT)
    assert tuple(path.as_posix() for path, _payload in artifacts) == (
        "changes/st-1006/generated/public-performance-recorded.v2.json",
        "changes/st-1006/runtime-manifest.v2.yaml",
    )
    for relative, expected in artifacts:
        assert (ROOT / relative).read_bytes() == expected
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    builder.build(ROOT, check=True)
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before


def test_recorded_output_is_synthetic_value_free_and_authority_closed() -> None:
    value = json.loads((ROOT / builder.GENERATED_PATH).read_bytes())
    assert value["performanceBudgets"]["recordedSyntheticAssessment"]["state"] == (
        "RECORDED_SYNTHETIC_PASS"
    )
    assert value["performanceBudgets"]["fieldAssessment"] == "NOT_EXECUTED"
    assert value["performanceBudgets"]["browserLabAssessment"] == "NOT_EXECUTED"
    image = value["imagePolicy"]["recordedSyntheticPresentation"]
    assert image["src"] is None
    assert image["srcSet"] is None
    assert image["renderable"] is False
    assert image["width"] == 640
    assert image["height"] == 360
    assert image["loading"] == "lazy"
    assert value["rumHook"]["enabled"] is False
    assert value["rumHook"]["bufferCapacity"] == 0
    assert value["rumHook"]["capturedEvents"] == []
    assert all(item in {False, "NOT_EXECUTED"} for item in value["authority"].values())
    serialized = json.dumps(value)
    assert "https://" not in serialized
    assert "article_body" not in serialized


def test_duplicate_documents_and_dependency_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(builder.St1006BuildError, match="^DUPLICATE_YAML_KEY$"):
        builder._parse_yaml(b"safe: 1\nsafe: 2\n")
    with pytest.raises(builder.St1006BuildError, match="^DUPLICATE_JSON_KEY$"):
        builder._parse_json(b'{"safe":1,"safe":2}')

    original = builder._read_regular

    def changed(root: Path, relative: Path, *, maximum: int = 4_000_000) -> bytes:
        payload = original(root, relative, maximum=maximum)
        if relative != builder.DEPENDENCY_SOURCE_PATHS[0]:
            return payload
        return payload.replace(
            b"affiliate_cta_rendered: false", b"affiliate_cta_rendered: true", 1
        )

    monkeypatch.setattr(builder, "_read_regular", changed)
    with pytest.raises(builder.St1006BuildError, match="^DEPENDENCY_CONTRACT_DRIFT$"):
        builder.expected_artifacts(ROOT)


def test_reader_rejects_symlink_leaf_and_parent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "regular.yaml"
    regular.write_bytes(b"safe: true\n")
    (root / "leaf.yaml").symlink_to(regular.name)
    with pytest.raises(builder.St1006BuildError, match="^SOURCE_LEAF_INVALID$"):
        builder._read_regular(root, Path("leaf.yaml"))

    real_parent = root / "real-parent"
    real_parent.mkdir()
    (real_parent / "source.yaml").write_bytes(b"safe: true\n")
    (root / "linked-parent").symlink_to(real_parent.name, target_is_directory=True)
    with pytest.raises(builder.St1006BuildError, match="^SOURCE_PARENT_INVALID$"):
        builder._read_regular(root, Path("linked-parent/source.yaml"))


def test_unknown_cli_does_not_write_generated_artifacts() -> None:
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert builder.main(["--unknown"]) == 2
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before
