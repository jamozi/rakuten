"""Owner-generator checks for the ST-1004 V2 local runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_st1004_disclosure_affiliate_runtime as builder


ROOT = Path(__file__).resolve().parents[2]


def test_expected_artifacts_are_current_and_owner_check_is_read_only() -> None:
    artifacts = builder.expected_artifacts(ROOT)
    assert tuple(path.as_posix() for path, _payload in artifacts) == (
        "changes/st-1004/generated/disclosure-affiliate-recorded.v2.json",
        "changes/st-1004/runtime-manifest.v2.yaml",
    )
    for relative, expected in artifacts:
        assert (ROOT / relative).read_bytes() == expected
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    builder.build(ROOT, check=True)
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before


def test_recorded_output_keeps_actual_url_absent_and_only_synthetic_url_exact() -> None:
    recorded = json.loads((ROOT / builder.GENERATED_PATH).read_bytes())
    cta = recorded["articleView"]["affiliateCta"]
    assert cta["state"] == "UNAVAILABLE_SOURCE"
    assert cta["anchor"] is None
    assert cta["source"]["affiliateUrl"] is None
    synthetic = recorded["syntheticCtaFixture"]
    assert synthetic["href"] == "https://example.invalid/rakuten-marketplace/item"
    assert synthetic["rel"] == "sponsored nofollow"
    assert synthetic["routeRendered"] is False
    assert json.dumps(recorded).count("https://") == 1


def test_duplicate_documents_and_bound_dependency_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(builder.St1004BuildError, match="^DUPLICATE_YAML_KEY$"):
        builder._parse_yaml(b"safe: 1\nsafe: 2\n")
    with pytest.raises(builder.St1004BuildError, match="^DUPLICATE_JSON_KEY$"):
        builder._parse_json(b'{"safe":1,"safe":2}')

    original = builder._read_regular

    def changed(root: Path, relative: Path, *, maximum: int = 4_000_000) -> bytes:
        payload = original(root, relative, maximum=maximum)
        if relative != Path("python/raos/domain/catalog/catalog_normalization.py"):
            return payload
        return payload.replace(b"affiliate_url=None", b"affiliate_url='invented'", 1)

    monkeypatch.setattr(builder, "_read_regular", changed)
    with pytest.raises(builder.St1004BuildError, match="^ST0503_SOURCE_DRIFT$"):
        builder.expected_artifacts(ROOT)


def test_reader_rejects_symlink_leaf_and_parent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "regular.yaml"
    regular.write_bytes(b"safe: true\n")
    (root / "leaf.yaml").symlink_to(regular.name)
    with pytest.raises(builder.St1004BuildError, match="^SOURCE_LEAF_INVALID$"):
        builder._read_regular(root, Path("leaf.yaml"))

    real_parent = root / "real-parent"
    real_parent.mkdir()
    (real_parent / "source.yaml").write_bytes(b"safe: true\n")
    (root / "linked-parent").symlink_to(real_parent.name, target_is_directory=True)
    with pytest.raises(builder.St1004BuildError, match="^SOURCE_PARENT_INVALID$"):
        builder._read_regular(root, Path("linked-parent/source.yaml"))


def test_unknown_cli_does_not_write_generated_artifacts() -> None:
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert builder.main(["--unknown"]) == 2
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before
