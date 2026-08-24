"""Owner generation, provenance, and compatibility coverage for ST-1702 V2."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts import build_st1702_category_fixture_runtime as generator


ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_installed_artifacts_equal_owner_generated_bytes() -> None:
    artifacts = generator.expected_artifacts(ROOT)
    assert tuple(path for path, _payload in artifacts) == generator.GENERATED_PATHS
    for relative, payload in artifacts:
        assert (ROOT / relative).read_bytes() == payload


def test_check_mode_is_byte_and_metadata_read_only() -> None:
    paths = tuple(ROOT / relative for relative in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(ROOT, check=True)
    assert _snapshot(paths) == before


def test_fixture_and_python_wrapper_have_exact_hash_binding() -> None:
    fixture = (ROOT / generator.FIXTURE_PATH).read_bytes()
    namespace: dict[str, object] = {}
    exec((ROOT / generator.GENERATED_PYTHON_PATH).read_bytes(), namespace)
    assert namespace["ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON"] == fixture.decode()
    assert (
        namespace["ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256"]
        == hashlib.sha256(fixture).hexdigest()
    )


def test_manifest_has_complete_provenance_and_closed_boundary() -> None:
    manifest = yaml.safe_load((ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["story_id"] == "ST-1702"
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert len(manifest["source_artifacts"]) == len(generator.SOURCE_PATHS)
    assert len({row["uri"] for row in manifest["source_artifacts"]}) == len(
        generator.SOURCE_PATHS
    )
    assert manifest["generation"]["publication"] == (
        "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK"
    )
    boundary = manifest["boundary"]
    assert boundary["data_class"] == "SYNTHETIC_VALIDATOR_FIXTURE_ONLY"
    assert boundary["human_review_required"] is True
    assert boundary["domain_reviewer_approval"] == "NOT_OBTAINED"
    assert boundary["formal_tst_020"] == "NOT_EXECUTED"
    for key in (
        "category_candidate_applied",
        "automatic_merge_enabled",
        "automatic_split_enabled",
        "runtime_enabled",
        "provider_access_enabled",
        "network_enabled",
        "persistence_enabled",
        "publication_authorized",
        "activation_authorized",
        "release_authorized",
        "production_authorized",
    ):
        assert boundary[key] is False


def test_fixture_contains_no_live_product_or_commercial_fields() -> None:
    fixture = json.loads((ROOT / generator.FIXTURE_PATH).read_bytes())
    rendered = json.dumps(fixture, ensure_ascii=False).lower()
    for prohibited in (
        "http://",
        "https://",
        "jan",
        "price",
        "reward",
        "commission",
        "affiliate",
        "inventory",
        "reviewbody",
    ):
        assert prohibited not in rendered


def test_historical_v1_plan_semantics_remain_exact_after_rebind() -> None:
    path = (
        ROOT
        / "changes/st-1702/generated/category-fixtures-rules-reference-plan.v1.json"
    )
    payload = path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == (
        "bf7cf69e296f4e225610fa1fd2b1219dd2b47bcc168d8c45f73165d851708169"
    )
    record = json.loads(payload)
    assert record["fixture_boundary"]["runtime_category_config"] == "NOT_CREATED"
    assert record["fixture_boundary"]["golden_products"] == "NOT_CREATED"
    assert record["document"]["effective_canonical_status"] == "UNCHANGED"


def test_generator_uses_secure_multi_output_publication() -> None:
    source = inspect.getsource(generator)
    assert "secure_generated_publication.publish_generated" in source
    assert "subprocess" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_duplicate_and_nonfinite_contract_json_is_rejected() -> None:
    with pytest.raises(generator.CategoryFixtureRuntimeGenerationError):
        generator._parse_contract(b'{"schemaVersion":2,"schemaVersion":2}')
    with pytest.raises(generator.CategoryFixtureRuntimeGenerationError):
        generator._parse_contract(b'{"schemaVersion":NaN}')


def test_symlinked_contract_is_rejected_without_following(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    target = tmp_path / generator.CONTRACT_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(generator.CategoryFixtureRuntimeGenerationError):
        generator._read_regular(tmp_path, generator.CONTRACT_PATH)


def test_symlinked_contract_ancestor_is_rejected_without_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "changes").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.CategoryFixtureRuntimeGenerationError):
        generator._read_regular(tmp_path, generator.CONTRACT_PATH)
    assert list(outside.iterdir()) == []


def test_expected_artifacts_captures_every_source_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Path] = []
    original = generator._read_regular

    def capture(
        root: Path, relative: Path, *, maximum: int = generator.MAX_SOURCE_BYTES
    ) -> bytes:
        observed.append(relative)
        return original(root, relative, maximum=maximum)

    monkeypatch.setattr(generator, "_read_regular", capture)
    generator.expected_artifacts(ROOT)
    assert tuple(observed) == generator.SOURCE_PATHS
    assert len(set(observed)) == len(observed)


def test_unknown_cli_argument_fails_without_modifying_outputs() -> None:
    paths = tuple(ROOT / relative for relative in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    completed = subprocess.run(
        [sys.executable, str(ROOT / generator.GENERATOR_PATH), "--unknown"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert _snapshot(paths) == before
