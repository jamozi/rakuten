from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
from typing import Any, cast

import pytest
import yaml

from scripts import build_st1305_finance_reconciliation as generator

from .support import ROOT


def test_projection_is_deterministic_and_has_closed_boundaries() -> None:
    first = generator.render_output(ROOT)
    second = generator.render_output(ROOT)
    assert first == second
    payload = json.loads(first)
    assert payload["document"]["status"] == "LOCAL_CODE_COMPLETE"
    assert payload["document"]["authority"] == "RECORDED_SYNTHETIC_ONLY"
    assert len(payload["measurement_boundary"]["article_slots"]) == 5
    assert all(
        tuple(row)
        == (
            "article_id",
            "intent_classification",
            "packet_sha256",
            "slot",
            "slug",
        )
        for row in payload["measurement_boundary"]["article_slots"]
    )
    assert payload["recorded_report"]["availability"] == "PARTIAL"
    assert payload["recorded_report"]["learning_report"]["output_kind"] == (
        "REVIEW_CANDIDATES_ONLY"
    )
    assert set(payload["recorded_report"]["authority"].values()) == {False}
    assert payload["completion_boundary"] == {
        "canonical_status_changed": False,
        "formal_or_live_evidence_claimed": False,
        "local_code_complete": True,
        "local_integration_complete": False,
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
        env={**os.environ, "PYTHONPATH": f"{ROOT / 'python'}:{ROOT}"},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "ST-1305 finance reconciliation projection checked\n"
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


def test_duplicate_yaml_and_binding_drift_fail_sanitized() -> None:
    with pytest.raises(generator.FinanceReconciliationBuildError) as duplicate:
        yaml.load("document: 1\ndocument: 2\n", Loader=generator.UniqueSafeLoader)
    assert str(duplicate.value) == (
        "ST-1305 build failed: YAML_DUPLICATE_KEY field=contract"
    )

    contract = cast(dict[str, Any], copy.deepcopy(generator.load_contract(ROOT)))
    contract["source_bindings"]["canonical_story"]["sha256"] = "0" * 64
    with pytest.raises(generator.FinanceReconciliationBuildError) as drift:
        generator._validate_bindings(  # noqa: SLF001
            ROOT, contract["source_bindings"]
        )
    assert str(drift.value) == (
        "ST-1305 build failed: INPUT_HASH_DRIFT field=canonical_story"
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
    with pytest.raises(generator.FinanceReconciliationBuildError) as captured:
        generator._atomic_write(ROOT, b"not-published\n")  # noqa: SLF001
    assert str(captured.value) == (
        "ST-1305 build failed: ATOMIC_WRITE_FAILED field=output"
    )
    assert output.read_bytes() == before
    assert not list(output.parent.glob(f".{output.name}.*.stage"))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "production_eligible", True),
        ("document", "formal_validation_claimed", True),
        ("report_contract", "arbitrary_total_allocation", True),
        ("report_contract", "missing_as_zero", True),
        ("metric_contract", "unattributed_reward_article_allocation", True),
        (
            "metric_contract",
            "missing_unverified_zero_denominator_immature_mismatch",
            "ZERO",
        ),
        ("learning_contract", "reward_or_profit_priority", True),
        ("learning_contract", "article_html_mutation", True),
        ("learning_contract", "cta_mutation", True),
        ("learning_contract", "product_selection_mutation", True),
        ("learning_contract", "recommendation_order_mutation", True),
        ("learning_contract", "publication_snapshot_mutation", True),
        ("authority_boundary", "provider_call", True),
        ("authority_boundary", "publication", True),
        ("authority_boundary", "recommendation_order_mutation", True),
        ("authority_boundary", "production", True),
    ],
)
def test_false_authority_allocation_or_zero_coercion_is_rejected(
    section: str, field: str, value: object
) -> None:
    contract = cast(dict[str, Any], copy.deepcopy(generator.load_contract(ROOT)))
    contract[section][field] = value
    with pytest.raises(generator.FinanceReconciliationBuildError):
        generator.validate_contract(contract)


def test_open_decisions_remain_unresolved_and_synthetic_only() -> None:
    contract = cast(dict[str, Any], copy.deepcopy(generator.load_contract(ROOT)))
    contract["open_decision_boundary"]["report_sample"]["resolved"] = True
    with pytest.raises(generator.FinanceReconciliationBuildError):
        generator.validate_contract(contract)

    contract = cast(dict[str, Any], copy.deepcopy(generator.load_contract(ROOT)))
    contract["recorded_fixture"]["provider_execution"] = "EXECUTED"
    with pytest.raises(generator.FinanceReconciliationBuildError):
        generator.validate_contract(contract)


def test_source_identity_and_recorded_fixture_hash_are_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = cast(dict[str, Any], copy.deepcopy(generator.load_contract(ROOT)))
    contract["source_bindings"]["canonical_story"]["path"] = (
        "docs/canonical/07_backlog/other.yaml"
    )
    with pytest.raises(generator.FinanceReconciliationBuildError):
        generator.validate_contract(contract)

    contract = cast(dict[str, Any], copy.deepcopy(generator.load_contract(ROOT)))
    contract["recorded_fixture"]["sha256"] = "0" * 64
    monkeypatch.setattr(generator, "load_contract", lambda root=ROOT: contract)
    with pytest.raises(generator.FinanceReconciliationBuildError) as captured:
        generator.render_output(ROOT)
    assert str(captured.value) == (
        "ST-1305 build failed: RECORDED_FIXTURE_BINDING_DRIFT field=recorded_fixture"
    )


def test_generator_has_one_output_and_no_external_adapter() -> None:
    assert generator.OUTPUT_PATH.as_posix().endswith(".json")
    source = (ROOT / generator.GENERATOR_PATH).read_text(encoding="utf-8")
    for forbidden in ("requests", "httpx", "boto3", "wordpress"):
        assert forbidden not in source
