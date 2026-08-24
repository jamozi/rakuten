"""Owner-generator and fail-closed checks for ST-1001 V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_st1001_public_app_shell as builder


ROOT = Path(__file__).resolve().parents[2]


def test_expected_artifacts_are_current_and_owner_check_passes() -> None:
    artifacts = builder.expected_artifacts(ROOT)
    assert tuple(path.as_posix() for path, _payload in artifacts) == (
        "changes/st-1001/generated/public-app-shell-recorded.v2.json",
        "apps/web/src/public-policy-content.generated.ts",
        "changes/st-1001/runtime-manifest.v2.yaml",
    )
    for relative, expected in artifacts:
        assert (ROOT / relative).read_bytes() == expected
    builder.build(ROOT, check=True)


def test_fixture_is_canonical_json_and_manifest_binds_outputs() -> None:
    fixture = (ROOT / builder.FIXTURE_PATH).read_bytes()
    assert fixture.endswith(b"\n")
    assert json.loads(fixture)["classification"] == (
        "LOCAL_ONLY_UNBRANDED_SSR_POLICY_PREVIEW_V2"
    )
    manifest = builder._parse_yaml((ROOT / builder.MANIFEST_PATH).read_bytes())
    outputs = manifest["generated_artifacts"]
    assert isinstance(outputs, list)
    assert outputs[0]["sha256"] == hashlib.sha256(fixture).hexdigest()
    generated_ts = (ROOT / builder.GENERATED_TS_PATH).read_bytes()
    assert outputs[1]["sha256"] == hashlib.sha256(generated_ts).hexdigest()


def test_duplicate_keys_and_untrusted_copy_fail_closed() -> None:
    with pytest.raises(builder.PublicShellBuildError, match="^DUPLICATE_YAML_KEY$"):
        builder._parse_yaml(b"safe: 1\nsafe: 2\n")
    with pytest.raises(builder.PublicShellBuildError, match="^DUPLICATE_JSON_KEY$"):
        builder._parse_json(b'{"safe":1,"safe":2}')

    contract = builder._validate_contract(ROOT)
    pages = contract["pages"]
    assert isinstance(pages, list)
    first = pages[0]
    assert isinstance(first, dict)
    sections = first["sections"]
    assert isinstance(sections, list)
    section = sections[0]
    assert isinstance(section, dict)
    section["body"] = "https://untrusted.invalid/<script>"
    with pytest.raises(builder.PublicShellBuildError, match="^PAGE_CONTRACT_INVALID$"):
        builder._validate_pages(contract)


def test_source_reader_rejects_symlink_leaf_and_parent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "regular.yaml"
    regular.write_bytes(b"safe: true\n")
    (root / "leaf.yaml").symlink_to(regular.name)
    with pytest.raises(builder.PublicShellBuildError, match="^SOURCE_LEAF_INVALID$"):
        builder._read_regular(root, Path("leaf.yaml"))

    real_parent = root / "real-parent"
    real_parent.mkdir()
    (real_parent / "source.yaml").write_bytes(b"safe: true\n")
    (root / "linked-parent").symlink_to(real_parent.name, target_is_directory=True)
    with pytest.raises(builder.PublicShellBuildError, match="^SOURCE_PARENT_INVALID$"):
        builder._read_regular(root, Path("linked-parent/source.yaml"))


def test_canonical_hash_drift_and_unknown_cli_fail_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = builder._read_regular
    drift_path = next(iter(builder.CANONICAL_HASHES))

    def changed(root: Path, relative: Path) -> bytes:
        payload = original(root, relative)
        return payload + b" " if relative == drift_path else payload

    monkeypatch.setattr(builder, "_read_regular", changed)
    with pytest.raises(
        builder.PublicShellBuildError,
        match="^CANONICAL_BINDING_DRIFT$",
    ):
        builder._validate_contract(ROOT)

    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert builder.main(["--unknown"]) == 2
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before
