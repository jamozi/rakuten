from __future__ import annotations

from pathlib import Path

import pytest

from scripts import build_st1102_article_workspace_v2 as builder


def test_rendered_outputs_match_owned_artifacts() -> None:
    outputs = builder.render_outputs(builder.REPO_ROOT)
    assert set(outputs) == set(builder.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (builder.REPO_ROOT / relative).read_bytes() == expected


def test_owner_check_is_read_only_and_passes() -> None:
    before = {
        relative: (builder.REPO_ROOT / relative).read_bytes()
        for relative in builder.GENERATED_PATHS
    }
    builder.build(builder.REPO_ROOT, check=True)
    after = {
        relative: (builder.REPO_ROOT / relative).read_bytes()
        for relative in builder.GENERATED_PATHS
    }
    assert after == before


def test_tracked_contract_bytes_are_semantic_and_duplicate_json_fails_closed(
    tmp_path: Path,
) -> None:
    contract = tmp_path / builder.CONTRACT_PATH
    contract.parent.mkdir(parents=True)
    contract.write_bytes(
        (builder.REPO_ROOT / builder.CONTRACT_PATH).read_bytes() + b"\n"
    )
    assert builder._load_contract(tmp_path)

    with pytest.raises(builder.ArticleWorkspaceBuildError) as json_error:
        builder._load_json_bytes(b'{"safe":1,"safe":2}', "recorded_fixture")
    assert json_error.value.code == "JSON_DUPLICATE_KEY"
    assert json_error.value.field == "recorded_fixture"
