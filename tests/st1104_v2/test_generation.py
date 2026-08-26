from __future__ import annotations

from pathlib import Path
from typing import cast

from scripts import build_st1104_analytics_finance_dashboard as builder


def test_owner_generator_is_no_write_reproducible() -> None:
    builder.build(check=True)
    expected = builder.expected_artifacts()
    assert tuple(path for path, _content in expected) == (
        builder.OUTPUT_PATH,
        builder.GENERATED_TS_PATH,
        builder.MANIFEST_PATH,
    )
    for path, content in expected:
        assert (builder.REPO_ROOT / path).read_bytes() == content


def test_tracked_contract_dependency_bytes_are_semantic(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    contract = builder._load_contract()
    required = {
        *builder.OWNED_SOURCE_PATHS,
        *builder.LOCKED_TOOLCHAIN_PATHS,
        builder.SECURE_HELPER_PATH,
        *(
            Path(cast(str, builder._mapping(value, name)["path"]))
            for name, value in builder._mapping(
                contract["source_bindings"], "source_bindings"
            ).items()
        ),
        builder.ST1205_FIXTURE_PATH,
        builder.ST1304_FIXTURE_PATH,
        builder.ST1303_FIXTURE_PATH,
    }
    for relative in required:
        source = builder.REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = root / "changes/st-1205/contracts/kpi-read-model.v2.yaml"
    target.write_bytes(target.read_bytes() + b"\n")
    assert builder._load_contract(root)
