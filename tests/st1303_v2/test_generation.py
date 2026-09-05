from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest
import yaml

from scripts import build_st1303_attribution_engine as generator

from .support import ROOT


def test_projection_is_deterministic_and_has_closed_boundaries() -> None:
    first = generator.render_output(ROOT)
    second = generator.render_output(ROOT)
    assert first == second
    payload = json.loads(first)
    assert payload["document"]["status"] == "LOCAL_CODE_COMPLETE"
    assert payload["measurement_contract"]["slot_count"] == 5
    assert payload["recorded_result"]["totals"] == {
        "difference_jpy": "0",
        "direct_confirmed_reward_jpy": "120",
        "estimated_confirmed_reward_jpy": "101",
        "provider_confirmed_reward_jpy": "300",
        "unattributed_confirmed_reward_jpy": "79",
    }
    assert set(payload["recorded_result"]["authority"].values()) == {False}
    assert payload["completion_boundary"] == {
        "local_code_complete": True,
        "local_integration_complete": False,
        "canonical_status_changed": False,
        "formal_or_live_evidence_claimed": False,
    }
    assert set(payload["verification_boundary"].values()) <= {
        "CANDIDATE",
        "NOT_EXECUTED",
    }


def test_owner_check_is_no_write_and_mode_is_fixed() -> None:
    output = ROOT / generator.OUTPUT_PATH
    before = output.read_bytes()
    before_stat = output.stat()
    completed = subprocess.run(
        [sys.executable, str(ROOT / generator.GENERATOR_PATH), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "ST-1303 attribution projection checked\n"
    assert output.read_bytes() == before
    assert output.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert stat.S_IMODE(output.stat().st_mode) == 0o644


def test_generated_source_inventory_hashes_match() -> None:
    payload = json.loads((ROOT / generator.OUTPUT_PATH).read_bytes())
    for artifact in payload["provenance"]["source_artifacts"]:
        path = ROOT / artifact["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert artifact["bytes"] == len(content)
        assert artifact["sha256"] == hashlib.sha256(content).hexdigest()


def test_duplicate_yaml_and_binding_drift_fail_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(generator.AttributionBuildError) as duplicate:
        yaml.load("document: 1\ndocument: 2\n", Loader=generator.UniqueSafeLoader)
    assert (
        str(duplicate.value)
        == "ST-1303 build failed: YAML_DUPLICATE_KEY field=contract"
    )

    bindings = generator._current_source_bindings(ROOT)  # noqa: SLF001
    bindings["canonical_story"]["sha256"] = "0" * 64
    expected = copy.deepcopy(generator.SOURCE_BINDINGS)
    expected["canonical_story"]["sha256"] = "0" * 64
    monkeypatch.setattr(generator, "SOURCE_BINDINGS", expected)
    with pytest.raises(generator.AttributionBuildError) as drift:
        generator._validate_bindings(ROOT, bindings)  # noqa: SLF001
    assert str(drift.value) == (
        "ST-1303 build failed: INPUT_HASH_DRIFT field=canonical_story"
    )


def test_single_output_atomic_failure_preserves_previous_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = ROOT / generator.OUTPUT_PATH
    before = output.read_bytes()

    def reject_replace(source: object, destination: object) -> None:
        del source, destination
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(os, "replace", reject_replace)
    with pytest.raises(generator.AttributionBuildError) as captured:
        generator._atomic_write(ROOT, b"not-published\n")  # noqa: SLF001
    assert (
        str(captured.value) == "ST-1303 build failed: ATOMIC_WRITE_FAILED field=output"
    )
    assert output.read_bytes() == before
    assert not list(output.parent.glob(f".{output.name}.*.stage"))


def test_generator_has_one_generated_output_and_no_external_adapter() -> None:
    assert generator.OUTPUT_PATH.as_posix().endswith(".json")
    source = (ROOT / generator.GENERATOR_PATH).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "httpx" not in source
    assert "boto3" not in source
    assert 'provider_call": False' in source


def _copy_owner_root(tmp_path: Path) -> Path:
    paths = {
        *generator.SOURCE_PATHS,
        generator.OUTPUT_PATH,
        generator.ST1704_CONTRACT_PATH,
        *(Path(binding["path"]) for binding in generator.SOURCE_BINDINGS.values()),
    }
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def _change_upstream(root: Path, *, field: str = "packet_sha256") -> None:
    path = root / generator.ST1704_CONTRACT_PATH
    payload = json.loads(path.read_bytes())
    payload["articles"][0][field] = (
        6
        if field == "slot"
        else ("f" * 64 if field == "packet_sha256" else "different-identity")
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _binding_bytes(root: Path) -> dict[Path, bytes]:
    return {
        relative: (root / relative).read_bytes()
        for relative in (
            generator.CONTRACT_PATH,
            generator.FIXTURE_PATH,
            generator.OUTPUT_PATH,
        )
    }


def test_generate_rebinds_only_synthetic_hashes_and_check_never_writes(
    tmp_path: Path,
) -> None:
    root = _copy_owner_root(tmp_path)
    original_contract = yaml.safe_load((root / generator.CONTRACT_PATH).read_bytes())
    original_fixture = json.loads((root / generator.FIXTURE_PATH).read_bytes())
    _change_upstream(root)
    before = _binding_bytes(root)
    with pytest.raises(generator.AttributionBuildError):
        generator.build(root, check=True)
    assert _binding_bytes(root) == before
    generator.build(root)
    generator.build(root, check=True)
    contract, measurement = generator.load_contract(root)
    fixture = json.loads((root / generator.FIXTURE_PATH).read_bytes())
    assert measurement.articles[0].packet_sha256.value == "f" * 64
    assert (
        measurement.source_contract_sha256.value
        == hashlib.sha256(
            (root / generator.ST1704_CONTRACT_PATH).read_bytes()
        ).hexdigest()
    )
    assert fixture["contract_sha256"] == measurement.sha256.value
    assert fixture["expected_input_sha256"] != original_fixture["expected_input_sha256"]
    normalized_contract = copy.deepcopy(contract)
    normalized_contract["source_bindings"]["five_slot_measurement"]["sha256"] = (
        original_contract["source_bindings"]["five_slot_measurement"]["sha256"]
    )
    normalized_contract["measurement_contract"]["source_contract_sha256"] = (
        original_contract["measurement_contract"]["source_contract_sha256"]
    )
    for current, old in zip(
        normalized_contract["measurement_contract"]["articles"],
        original_contract["measurement_contract"]["articles"],
        strict=True,
    ):
        current["packet_sha256"] = old["packet_sha256"]
    assert normalized_contract == original_contract
    fixture["contract_sha256"] = original_fixture["contract_sha256"]
    fixture["expected_input_sha256"] = original_fixture["expected_input_sha256"]
    for current, old in zip(
        fixture["request"]["article_measurements"],
        original_fixture["request"]["article_measurements"],
        strict=True,
    ):
        current["article"]["packet_sha256"] = old["article"]["packet_sha256"]
    assert fixture == original_fixture
    timestamps = {
        path: (root / path).stat().st_mtime_ns
        for path in (generator.CONTRACT_PATH, generator.FIXTURE_PATH)
    }
    generator.build(root)
    assert timestamps == {path: (root / path).stat().st_mtime_ns for path in timestamps}


@pytest.mark.parametrize(
    "field", ["slot", "article_id", "slug", "intent_classification"]
)
def test_upstream_identity_changes_cannot_be_automatically_rebound(
    tmp_path: Path,
    field: str,
) -> None:
    root = _copy_owner_root(tmp_path)
    _change_upstream(root, field=field)
    before = _binding_bytes(root)
    with pytest.raises(
        generator.AttributionBuildError, match="UPSTREAM_ARTICLE_IDENTITY_DRIFT"
    ):
        generator.build(root)
    assert _binding_bytes(root) == before


@pytest.mark.parametrize("field", ["profile", "expected_input_sha256", "observation"])
def test_rebinding_rejects_non_synthetic_or_tampered_fixture(
    tmp_path: Path,
    field: str,
) -> None:
    root = _copy_owner_root(tmp_path)
    _change_upstream(root)
    path = root / generator.FIXTURE_PATH
    fixture = json.loads(path.read_bytes())
    if field == "observation":
        fixture["request"]["article_measurements"][0]["metrics"]["search_impressions"][
            "value"
        ] += 1
    else:
        fixture[field] = "LIVE_PROVIDER" if field == "profile" else "0" * 64
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    before = _binding_bytes(root)
    with pytest.raises(
        generator.AttributionBuildError, match="SYNTHETIC_REBIND_INPUT_INVALID"
    ):
        generator.build(root)
    assert _binding_bytes(root) == before


def test_rebinding_preserves_authority_and_rolls_back_failed_reference_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_owner_root(tmp_path)
    _change_upstream(root)
    before = _binding_bytes(root)
    write = generator._atomic_write  # noqa: SLF001

    def reject_fixture(
        root: Path, payload: bytes, *, relative: Path = generator.OUTPUT_PATH
    ) -> None:
        if relative == generator.FIXTURE_PATH:
            raise generator.AttributionBuildError("synthetic write failure")
        write(root, payload, relative=relative)

    monkeypatch.setattr(generator, "_atomic_write", reject_fixture)
    with pytest.raises(
        generator.AttributionBuildError, match="synthetic write failure"
    ):
        generator.build(root)
    assert _binding_bytes(root) == before
    monkeypatch.setattr(generator, "_atomic_write", write)
    path = root / generator.CONTRACT_PATH
    contract = yaml.safe_load(path.read_bytes())
    contract["authority_boundary"]["publication"] = True
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    before = _binding_bytes(root)
    with pytest.raises(
        generator.AttributionBuildError, match="AUTHORITY_BOUNDARY_DRIFT"
    ):
        generator.build(root)
    assert _binding_bytes(root) == before
