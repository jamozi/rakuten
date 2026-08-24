"""Owner-generator and fail-closed tests for ST-1002 V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_st1002_public_article_renderer as builder


ROOT = Path(__file__).resolve().parents[2]


def test_expected_artifacts_are_current_and_owner_check_passes() -> None:
    artifacts = builder.expected_artifacts(ROOT)
    assert tuple(path.as_posix() for path, _payload in artifacts) == (
        "packages/web-ui/src/public-article-recorded.v2.ts",
        "changes/st-1002/generated/public-article-renderer-recorded.v2.json",
        "changes/st-1002/runtime-manifest.v2.yaml",
    )
    for relative, expected in artifacts:
        assert (ROOT / relative).read_bytes() == expected
    builder.build(ROOT, check=True)


def test_recorded_view_is_canonical_and_manifest_binds_both_outputs() -> None:
    rendered = (ROOT / builder.RENDERED_FIXTURE_PATH).read_bytes()
    fixture = json.loads(rendered)
    assert fixture["classification"] == (
        "LOCAL_RECORDED_NOINDEX_SSR_ARTICLE_PREVIEW_V2"
    )
    assert fixture["route"]["sourceRouteActivated"] is False
    assert fixture["runtimeBoundary"]["internalIdentifiersRendered"] is False
    manifest = builder._parse_yaml((ROOT / builder.MANIFEST_PATH).read_bytes())
    outputs = manifest["generated_artifacts"]
    assert isinstance(outputs, list)
    generated = (ROOT / builder.GENERATED_SOURCE_PATH).read_bytes()
    assert outputs[0]["sha256"] == hashlib.sha256(generated).hexdigest()
    assert outputs[1]["sha256"] == hashlib.sha256(rendered).hexdigest()


def test_duplicate_keys_and_source_content_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(builder.PublicArticleBuildError, match="^DUPLICATE_YAML_KEY$"):
        builder._parse_yaml(b"safe: 1\nsafe: 2\n")
    with pytest.raises(builder.PublicArticleBuildError, match="^DUPLICATE_JSON_KEY$"):
        builder._parse_json(b'{"safe":1,"safe":2}')

    original = builder._read_regular

    def changed(root: Path, relative: Path) -> bytes:
        payload = original(root, relative)
        if relative != builder.SOURCE_FIXTURE_PATH:
            return payload
        document = json.loads(payload)
        document["output"]["projection"]["article"]["title"] = "changed"
        return (json.dumps(document, sort_keys=True) + "\n").encode()

    monkeypatch.setattr(builder, "_read_regular", changed)
    with pytest.raises(
        builder.PublicArticleBuildError,
        match="^DEPENDENCY_BINDING_DRIFT$",
    ):
        builder._validate_contract(ROOT)


def test_source_reader_rejects_symlink_leaf_and_parent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "regular.yaml"
    regular.write_bytes(b"safe: true\n")
    (root / "leaf.yaml").symlink_to(regular.name)
    with pytest.raises(builder.PublicArticleBuildError, match="^SOURCE_LEAF_INVALID$"):
        builder._read_regular(root, Path("leaf.yaml"))

    real_parent = root / "real-parent"
    real_parent.mkdir()
    (real_parent / "source.yaml").write_bytes(b"safe: true\n")
    (root / "linked-parent").symlink_to(real_parent.name, target_is_directory=True)
    with pytest.raises(
        builder.PublicArticleBuildError, match="^SOURCE_PARENT_INVALID$"
    ):
        builder._read_regular(root, Path("linked-parent/source.yaml"))


def test_unknown_cli_never_writes_generated_outputs() -> None:
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert builder.main(["--unknown"]) == 2
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before
