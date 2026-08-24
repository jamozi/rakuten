"""Canonical, dependency, contract and completion boundary tests."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
from typing import Any, cast

import yaml

from conftest import REPOSITORY_ROOT
from raos.domain.analytics.gate3_economics import PROGRAM
from scripts import build_st1804_gate3_economics as builder


def _story() -> dict[str, Any]:
    backlog = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_text()
    )
    return next(row for row in backlog["stories"] if row["id"] == "ST-1804")


def _section(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    return cast(Mapping[str, object], source[key])


def test_canonical_story_is_exact() -> None:
    story = _story()
    assert story["objective"] == "確定成果/費用/利益を評価"
    assert story["depends_on"] == ["ST-1803", "ST-1305"]
    assert story["deliverables"] == ["GATE-3 pack"]
    assert story["acceptance_criteria"] == ["confirmed basis and no false attribution"]
    assert story["test_suites"] == ["TST-030", "TST-032"]


def test_contract_binds_exact_canonical_and_dependency_bytes() -> None:
    contract = builder.load_contract()
    flattened = builder._flatten_bindings(contract)
    assert flattened == builder.EXPECTED_BINDINGS
    for path, expected in flattened.items():
        assert (
            hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()
            == expected
        )


def test_contract_fixes_unavailability_and_no_false_attribution() -> None:
    contract = builder.load_contract()
    inputs = _section(contract, "input_contract")
    assert inputs["program"] == PROGRAM
    assert inputs["missing_is_zero"] is False
    assert inputs["unverified_is_zero"] is False
    assert inputs["mixed_period"] == "UNAVAILABLE"
    assert inputs["mixed_program"] == "UNAVAILABLE"
    assert inputs["immature_cohort"] == "UNAVAILABLE"
    assert inputs["unattributed_article_allocation"] is False
    basis = _section(contract, "basis_contract")
    assert basis["actual_confirmed_profit_claim"] is False
    assert basis["arbitrary_total_article_allocation"] is False


def test_contract_forbids_finance_ranking_and_mutation() -> None:
    boundary = _section(builder.load_contract(), "learning_and_editorial_boundary")
    assert all(
        boundary[key] is False
        for key in (
            "finance_or_reward_used_for_product_ranking",
            "affiliate_rate_used_for_product_ranking",
            "epc_used_for_product_ranking",
            "rpm_used_for_product_ranking",
            "profit_used_for_product_ranking",
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "recommendation_order_mutation",
            "publication_snapshot_mutation",
        )
    )


def test_execution_boundary_preserves_every_external_gate() -> None:
    boundary = _section(builder.load_contract(), "execution_boundary")
    assert boundary["actual_30_45_article_pilot"] == "NOT_EXECUTED"
    assert boundary["actual_gate3_observation"] == "NOT_EXECUTED"
    assert boundary["owner_private_ledger_read"] is False
    assert boundary["gate_approval"] == "NONE"
    assert boundary["scale_authority"] == "NONE"
    assert boundary["publication"] == "NOT_EXECUTED"
    assert boundary["formal_TST-030"] == "NOT_EXECUTED"
    assert boundary["formal_TST-032"] == "NOT_EXECUTED"
    assert boundary["production"] == "NOT_EXECUTED"


def test_generated_pack_records_dependency_period_mismatch() -> None:
    pack = builder.build_pack()
    alignment = _section(pack, "dependency_alignment")
    assert alignment["period_alignment"] == ("MISMATCH_RECORDED_SYNTHETIC_DEPENDENCIES")
    assert alignment["actual_gate_input_eligible"] is False
    confirmed = _section(pack, "confirmed_basis")
    assert confirmed["actual_confirmed_profit_eligible"] is False
    assert pack["overall"] == "BLOCKED"
    assert pack["gate_pass_claim"] is False


def test_completion_record_is_local_only_and_debt_free() -> None:
    completion = yaml.safe_load((REPOSITORY_ROOT / builder.COMPLETION_PATH).read_text())
    assert completion["story_id"] == "ST-1804"
    assert completion["implementation_status_claim"] == "LOCAL_CODE_COMPLETE"
    assert completion["canonical_status_mutated"] is False
    assert completion["acceptance_criteria_satisfied"] is False
    assert completion["decision"]["overall"] == "BLOCKED"
    assert completion["introduced_local_debt"] == []
    assert set(completion["authority"].values()) == {"NONE"}
    assert set(completion["not_executed"].values()) == {"NOT_EXECUTED"}


def test_readme_never_promotes_synthetic_evidence() -> None:
    text = (REPOSITORY_ROOT / builder.README_PATH).read_text()
    for phrase in (
        "not an actual 30–45 article pilot",
        "always `BLOCKED`",
        "`actual_observations` is empty",
        "Provider total is a program total, never article attribution",
        "none become a silent zero",
        "cannot\nrank products",
        "Local checks\ndo not constitute Canonical `VALIDATED`",
    ):
        assert phrase in text


def test_owned_paths_are_outside_immutable_canonical_tree() -> None:
    for path in (
        builder.CONTRACT_PATH,
        builder.FIXTURE_PATH,
        builder.OUTPUT_PATH,
        builder.README_PATH,
        builder.PREFLIGHT_PATH,
        builder.COMPLETION_PATH,
        builder.GENERATOR_PATH,
        builder.DOMAIN_PATH,
        builder.PORT_PATH,
        builder.APPLICATION_PATH,
        builder.ADAPTER_PATH,
    ):
        assert not str(path).startswith(("docs/canonical/", "docs/upstream/", "zip/"))
        assert Path(path).is_absolute() is False
