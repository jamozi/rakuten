"""Historical reference-plan compatibility and V2 boundary assertions."""

from __future__ import annotations

import json

import yaml

from scripts import (
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)


def test_historical_v1_reference_plan_interface_remains_byte_compatible() -> None:
    contract = generator.load_contract()
    plan = generator.reference_plan(contract)
    assert tuple(plan) == generator.CONTRACT_KEYS
    assert plan == contract
    assert plan["document"]["executable"] is False
    assert plan["document"]["interface_only"] is True
    assert plan["document"]["runtime_eligible"] is False
    assert plan["open_decision"]["safe_default"] == "RECORDED_FIXTURE_ONLY"
    installed = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert installed == plan


def test_v2_contract_is_local_complete_but_operationally_disabled() -> None:
    contract = yaml.safe_load(
        (generator.REPO_ROOT / generator.RUNTIME_CONTRACT_PATH).read_bytes()
    )
    document = contract["document"]
    assert document["status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert document["provider_mode"] == "RECORDED_SYNTHETIC_ONLY"
    assert document["default_enabled"] is False
    for name in (
        "live_provider_allowed",
        "credentials_allowed",
        "network_allowed",
        "route_mutation_allowed",
        "activation_allowed",
        "approval_allowed",
        "publication_allowed",
        "release_authorized",
        "production_eligible",
    ):
        assert document[name] is False
    policy = contract["runtime_policy"]
    assert policy["unavailable_is_pass"] is False
    assert policy["unknown_is_zero"] is False
    assert policy["insufficient_is_pass"] is False
    assert policy["zero_tolerance_waiver_allowed"] is False
    assert policy["od_015"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert policy["formal_tst_018"] == "NOT_EXECUTED"


def test_exact_st0703_binding_and_st0707_report_are_declared() -> None:
    contract = yaml.safe_load(
        (generator.REPO_ROOT / generator.RUNTIME_CONTRACT_PATH).read_bytes()
    )
    st0703 = contract["st0703_recorded_binding"]
    assert st0703["recorded_task_id"] == "AIT-004"
    assert st0703["target_task_code"] == "ai.article_draft.v1"
    assert st0703["route_version"] == "route.synthetic.recorded.v1"
    assert st0703["prompt_version"] == "PRM-004-v1"
    assert st0703["model_id"] == "raos-synthetic-model-v1"
    assert st0703["provenance"] == "ST0703_RECORDED_SYNTHETIC_TEST_FIXTURE"
    assert all(
        st0703[name] is False
        for name in (
            "canonical_route_selected",
            "canonical_model_selected",
            "canonical_prompt_selected",
            "live_binding",
        )
    )
    st0707 = contract["st0707_report_binding"]
    assert st0707["bundle_sha256"] == (
        "c955d57442be07a4da7a1459bd759b9f03c346be18f7fe8885310da77249a5ea"
    )
    assert st0707["report_sha256"] == (
        "e16248e167bf267645ebdbf25ca7e7e9b2e220925bd8461566cc07a9ba3b381d"
    )
    assert st0707["source_task_code"] == "ai.opportunity_assessment.v1"
    assert st0707["dataset_provenance"] == "SYNTHETIC_PLUMBING_ONLY"
    assert st0707["human_label_status"] == "UNAVAILABLE"
    assert st0707["release_eligible"] is False


def test_critical_target_suite_has_all_exact_gates() -> None:
    request = json.loads((generator.REPO_ROOT / generator.REQUEST_PATH).read_bytes())[
        "evidence"
    ]
    assert request["target_task_code"] == "ai.article_draft.v1"
    assert request["target_suite_code"] == "suite.ai.article_draft.v1.release.v1"
    assert request["risk_level"] == "CRITICAL"
    assert request["minimum_adjudicated_cases"] == 200
    assert request["required_splits"] == [
        "DEV",
        "CALIBRATION",
        "HOLDOUT",
        "ADVERSARIAL",
        "REGRESSION",
    ]
    assert len(request["thresholds"]) == 9
    assert len(request["zero_tolerance_classes"]) == 8
    assert request["metric_observations"] == []
    assert request["zero_tolerance_observations"] == []


def test_installed_v2_artifacts_make_no_formal_or_live_claim() -> None:
    report = json.loads((generator.REPO_ROOT / generator.REPORT_PATH).read_bytes())
    assert report["formal_status"] == {
        "formal_tst_018": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
    }
    assert report["report"]["outcome"] == "REFUSED_INCOMPLETE_EVIDENCE"
    assert report["report"]["decision_kind"] == "PROPOSAL"
    assert report["report"]["authority"] == "NONE"
