"""Canonical, dependency, contract, and completion boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .support import REPOSITORY_ROOT
from raos.domain.analytics.gate2_observation import (
    ARTICLE_METRICS,
    PROGRAM,
    PROGRAM_METRICS,
)
from scripts import build_st1803_gate2_observation as builder


def _story() -> dict[str, Any]:
    backlog = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_text()
    )
    return next(row for row in backlog["stories"] if row["id"] == "ST-1803")


def test_canonical_story_objective_dependencies_and_suites_are_exact() -> None:
    story = _story()
    assert story["objective"] == "検索/行動/鮮度を観測"
    assert story["depends_on"] == ["ST-1802", "ST-1205"]
    assert story["deliverables"] == ["GATE-2 pack"]
    assert story["acceptance_criteria"] == ["defined observation period/data quality"]
    assert story["test_suites"] == ["TST-030", "TST-032"]


def test_contract_declares_semantic_sources_and_dependencies() -> None:
    contract = builder.load_contract()
    flattened: dict[str, object] = dict(contract["source_bindings"])
    dependencies = contract["dependency_bindings"]
    assert isinstance(dependencies, dict)
    flattened.update(dependencies["ST-1802"])
    flattened.update(dependencies["ST-1205"])
    assert flattened == builder.EXPECTED_BINDINGS
    assert all((REPOSITORY_ROOT / path).is_file() for path in flattened)


def test_metric_contract_is_complete_and_fixed_program() -> None:
    contract = builder.load_contract()
    measurement = contract["metric_contract"]
    assert isinstance(measurement, dict)
    assert tuple(measurement["article_metrics"]) == ARTICLE_METRICS
    assert tuple(measurement["program_metrics"]) == PROGRAM_METRICS
    observation = contract["observation_contract"]
    assert isinstance(observation, dict)
    assert observation["program"] == PROGRAM
    assert observation["missing_is_zero"] is False
    assert observation["zero_denominator"] == "UNAVAILABLE"
    assert observation["input_history"] == "APPEND_ONLY_HASH_CHAIN"
    assert observation["input_mutability"] == "IMMUTABLE"


def test_improvement_contract_forbids_finance_and_mutation() -> None:
    contract = builder.load_contract()
    improvement = contract["improvement_contract"]
    assert isinstance(improvement, dict)
    assert improvement["output_only"] is True
    false_fields = {
        "finance_or_reward_used_for_candidate_selection",
        "affiliate_rate_used_for_candidate_selection",
        "epc_used_for_candidate_selection",
        "rpm_used_for_candidate_selection",
        "profit_used_for_candidate_selection",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "automatic_publication",
    }
    assert all(improvement[field] is False for field in false_fields)


def test_execution_boundary_preserves_every_external_gate() -> None:
    boundary = builder.load_contract()["execution_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["actual_30_45_article_observation"] == "NOT_EXECUTED"
    assert boundary["owner_private_ledger_read"] is False
    assert boundary["tracking_activation"] == "DISABLED_OD_012"
    assert boundary["live_rank_provider"] == "NOT_EXECUTED_OD_004"
    assert boundary["gate_approval"] == "NONE"
    assert boundary["publication"] == "NOT_EXECUTED"
    assert boundary["formal_TST-030"] == "NOT_EXECUTED"
    assert boundary["formal_TST-032"] == "NOT_EXECUTED"
    assert boundary["production"] == "NOT_EXECUTED"


def test_completion_record_is_local_only_and_introduces_no_debt() -> None:
    path = REPOSITORY_ROOT / builder.COMPLETION_PATH
    completion = yaml.safe_load(path.read_text())
    assert completion["story_id"] == "ST-1803"
    assert completion["implementation_status_claim"] == "LOCAL_CODE_COMPLETE"
    assert completion["canonical_status_mutated"] is False
    assert completion["acceptance_criteria_satisfied"] is False
    assert completion["decision"]["overall"] == "BLOCKED"
    assert completion["introduced_local_debt"] == []
    assert set(completion["authority"].values()) == {"NONE"}
    assert set(completion["not_executed"].values()) == {"NOT_EXECUTED"}


def test_readme_never_promotes_local_synthetic_evidence() -> None:
    text = (REPOSITORY_ROOT / builder.README_PATH).read_text()
    for phrase in (
        "`BLOCKED`",
        "not an actual pilot observation",
        "none become a silent zero",
        "Unattributed reward is never allocated",
        "cannot change article HTML",
        "actual_observations` is empty",
        "Local checks do not constitute Canonical `VALIDATED` status",
    ):
        assert phrase in text
    assert "Production remain explicitly `NOT_EXECUTED`" in text


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
