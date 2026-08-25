"""Owner-generator checks for the ST-0504 V2 runtime artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from scripts import build_st0504_product_identity_runtime as generator


def _json(relative: Path) -> dict[str, object]:
    value = cast(
        object,
        json.loads((generator.REPO_ROOT / relative).read_text(encoding="utf-8")),
    )
    assert type(value) is dict
    raw = cast(dict[object, object], value)
    assert all(type(key) is str for key in raw)
    return {cast(str, key): item for key, item in raw.items()}


def _string_mapping(value: object) -> dict[str, str]:
    assert type(value) is dict
    raw = cast(dict[object, object], value)
    assert all(type(key) is str and type(item) is str for key, item in raw.items())
    return {cast(str, key): cast(str, item) for key, item in raw.items()}


def test_render_is_deterministic_and_installed_outputs_are_exact() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    assert all(
        (generator.REPO_ROOT / path).read_bytes() == value
        for path, value in first.items()
    )


def test_check_mode_is_no_write_and_accepts_exact_outputs() -> None:
    before = {
        path: (generator.REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    assert generator.main(["--check"]) == 0
    after = {
        path: (generator.REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    assert after == before


def test_generated_projection_preserves_human_review_and_blocked_authorization() -> (
    None
):
    projection = _json(generator.OUTPUT)
    identity = projection["identity_boundary"]
    authorization = projection["authorization_boundary"]
    execution = projection["execution_boundary"]
    durability = projection["durability_boundary"]
    assert type(identity) is dict
    assert type(authorization) is dict
    assert type(execution) is dict
    assert type(durability) is dict
    assert identity["open_decision"] == "OD-006"
    assert identity["open_decision_resolved"] is False
    assert identity["automatic_merge"] is False
    assert identity["automatic_split"] is False
    assert identity["ranking_surface"] is False
    assert authorization["service"] == "DurableAuthorizationService.recover_admin"
    assert authorization["current_canonical_binding"] == "BLOCKED"
    assert authorization["new_authorization_issuance"] is False
    assert execution["external_actions"] == 0
    assert execution["production_authority"] == "NONE"
    assert durability["exclusive_created_initialization"] is True
    assert durability["live_device_inode_pinned"] is True
    assert durability["process_local_monotonic_prefix_pin"] is True
    assert durability["cross_process_restart_rollback_detection"] is False
    assert durability["external_rollback_anchor"] is False


def test_manifest_binds_every_owned_source_and_generated_output() -> None:
    manifest = _json(generator.MANIFEST)
    source_hashes = _string_mapping(manifest["source_sha256"])
    generated_hashes = _string_mapping(manifest["generated_sha256"])
    assert set(source_hashes) == {str(path) for path in generator.SOURCE_PATHS}
    for relative, digest in source_hashes.items():
        assert (
            hashlib.sha256((generator.REPO_ROOT / relative).read_bytes()).hexdigest()
            == digest
        )
    assert set(generated_hashes) == {str(generator.OUTPUT), str(generator.EVIDENCE)}
    for relative, digest in generated_hashes.items():
        assert (
            hashlib.sha256((generator.REPO_ROOT / relative).read_bytes()).hexdigest()
            == digest
        )
    assert manifest["formal_evidence"] == "NOT_EXECUTED"
    assert manifest["production"] == "NOT_EXECUTED"


def test_generator_failure_is_sanitized_and_rejected_value_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "secret-generator-canary"
    monkeypatch.setattr(generator, "CONTRACT", Path(f"changes/st-0504/{canary}"))
    with pytest.raises(generator.ProductIdentityBuildError) as caught:
        generator.render_outputs()
    assert str(caught.value) == "ST-0504 V2 build failed: SOURCE_PATH_INVALID"
    assert canary not in str(caught.value)
