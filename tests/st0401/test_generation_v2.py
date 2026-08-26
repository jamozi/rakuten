"""Owner generation and closed-boundary coverage for ST-0401 V2."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest

from .support import REPOSITORY_ROOT
from scripts import build_st0401_local_auth_runtime as generator


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_installed_artifacts_equal_owner_generated_bytes() -> None:
    artifacts = generator.expected_artifacts(REPOSITORY_ROOT)
    assert tuple(path for path, _payload in artifacts) == generator.GENERATED_PATHS
    for relative, payload in artifacts:
        assert (REPOSITORY_ROOT / relative).read_bytes() == payload


def test_check_mode_is_byte_and_metadata_read_only() -> None:
    paths = tuple(REPOSITORY_ROOT / relative for relative in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before


def test_runtime_and_manifest_keep_od010_and_all_external_authority_closed() -> None:
    runtime = json.loads((REPOSITORY_ROOT / generator.RUNTIME_PATH).read_bytes())
    manifest = json.loads((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    contract = runtime["contract"]

    assert runtime["story_id"] == "ST-0401"
    assert (
        runtime["contract_sha256"]
        == hashlib.sha256(
            (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_bytes()
        ).hexdigest()
    )
    assert contract["open_decision"] == {
        "id": "OD-010",
        "provider_selection": "UNSELECTED",
        "safe_default": "LOCAL_FAKE_DEVELOPMENT_ONLY_EXTERNAL_PUBLICATION_FORBIDDEN",
        "status": "HUMAN_DECISION_REQUIRED",
    }
    assert all(value is False for value in contract["authority"].values())
    assert contract["runtime"]["transport"]["route_registration"] is False
    assert contract["runtime"]["persistence"]["external_io_inside_transaction"] is False
    assert manifest["generation"]["publication"] == (
        "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK"
    )
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert len(manifest["source_artifacts"]) == len(generator.SOURCE_PATHS)
    assert len({row["path"] for row in manifest["source_artifacts"]}) == len(
        generator.SOURCE_PATHS
    )


def test_generated_documents_select_no_provider_credential_or_browser_delivery() -> (
    None
):
    rendered = " ".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        for path in generator.GENERATED_PATHS
    )
    for forbidden in (
        "client_secret",
        "access_token",
        "refresh_token",
        "id_token",
        "set_cookie",
        "cognito",
    ):
        assert forbidden not in rendered.lower()
    assert '"provider_selection": "UNSELECTED"' in rendered
    assert '"browser_storage": "UNSELECTED_NOT_DELIVERED"' in rendered


def test_generator_is_offline_and_uses_secure_multi_output_publication() -> None:
    source = inspect.getsource(generator)
    assert "secure_generated_publication.publish_generated" in source
    for forbidden in ("subprocess", "socket", "requests", "urllib"):
        assert forbidden not in source


def test_duplicate_nonfinite_and_wrong_contract_shapes_are_rejected() -> None:
    with pytest.raises(generator.LocalAuthRuntimeGenerationError):
        generator._parse_contract(b'{"story_id":"ST-0401","story_id":"ST-0401"}')
    with pytest.raises(generator.LocalAuthRuntimeGenerationError):
        generator._parse_contract(b'{"schema_version":NaN}')
    with pytest.raises(generator.LocalAuthRuntimeGenerationError):
        generator._validate_contract({"story_id": "ST-0401"})


def test_tracked_contract_is_semantic_and_canonical_remains_hash_bound() -> None:
    inputs = generator._capture_sources(REPOSITORY_ROOT)
    inputs[generator.CONTRACT_PATH] += b" "
    generator._validate_pins(inputs)

    inputs = generator._capture_sources(REPOSITORY_ROOT)
    canonical_path = next(iter(generator.CANONICAL_BINDINGS))
    inputs[canonical_path] += b" "
    with pytest.raises(
        generator.LocalAuthRuntimeGenerationError, match="CANONICAL_BINDING_DRIFT"
    ):
        generator._validate_pins(inputs)


def test_symlinked_source_is_rejected_without_following(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    target = tmp_path / generator.CONTRACT_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)

    with pytest.raises(generator.LocalAuthRuntimeGenerationError):
        generator._read_regular(tmp_path, generator.CONTRACT_PATH)


def test_unknown_cli_argument_fails_without_modifying_outputs() -> None:
    paths = tuple(REPOSITORY_ROOT / relative for relative in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / generator.GENERATOR_PATH), "--unknown"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert _snapshot(paths) == before
