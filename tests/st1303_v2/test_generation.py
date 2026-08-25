from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys

import pytest
import yaml

from scripts import build_st1303_attribution_engine as generator

from .conftest import ROOT


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

    bindings = copy.deepcopy(generator.SOURCE_BINDINGS)
    bindings["canonical_story"]["sha256"] = "0" * 64
    monkeypatch.setattr(generator, "SOURCE_BINDINGS", bindings)
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
