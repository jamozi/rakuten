"""Source and projection contract tests for ST-1407."""

from __future__ import annotations

import json

from scripts import build_st1407_external_policy_registry_reference_plan as generator


def test_contract_projects_exact_external_rule_inventory_and_mappings() -> None:
    plan = generator.reference_plan(generator.load_contract())
    projection = plan["catalog_projection"]["external_rule_snapshot"]

    assert tuple(plan) == generator.PLAN_KEYS
    assert projection["document"]["id"] == "RAOS-CONTENT-EXTERNAL-001"
    assert projection["document"]["version"] == "0.1"
    assert projection["observed_at"] == "2026-07-30"
    assert projection["review_policy"] == {
        "frequency": "monthly and event-driven",
        "authoritative_sources_only": True,
        "change_action": (
            "create policy diff, affected publication set, risk classification, "
            "approval and re-evaluation"
        ),
    }
    assert projection["coverage"] == {"projected": 13, "canonical": 13}
    assert [row["id"] for row in projection["rules"]] == list(
        generator.EXTERNAL_RULE_IDS
    )
    assert {
        row["id"]: tuple(row["content_policy_ids"]) for row in projection["rules"]
    } == generator.EXPECTED_EXTERNAL_POLICY_MAP
    assert {row["id"]: row["url"] for row in projection["rules"]} == (
        generator.EXPECTED_EXTERNAL_URLS
    )


def test_contract_projects_exact_independent_official_reference_inventory() -> None:
    projection = generator.reference_plan(generator.load_contract())[
        "catalog_projection"
    ]["official_reference_snapshot"]

    assert projection["document"]["id"] == "RAOS-CONTENT-REF-001"
    assert projection["document"]["status"] == (
        "CURRENT_SNAPSHOT_REVALIDATE_BEFORE_PRODUCTION"
    )
    assert projection["coverage"] == {"projected": 12, "canonical": 12}
    assert [row["id"] for row in projection["sources"]] == list(
        generator.OFFICIAL_REFERENCE_IDS
    )
    assert {row["id"]: row["url"] for row in projection["sources"]} == (
        generator.EXPECTED_OFFICIAL_URLS
    )
    assert projection["inferred_external_rule_links"] == []


def test_external_snapshot_policy_bundle_and_publication_seams_stay_distinct() -> None:
    plan = generator.reference_plan(generator.load_contract())
    seams = plan["candidate_seams"]

    assert seams["source_snapshot"] == {
        "entity": "evidence.source_snapshot",
        "relation_to_external_policy": "UNSPECIFIED",
        "instances": [],
        "content_byte_artifacts": [],
    }
    assert seams["policy_bundle"]["entity"] == "policy.policy_bundle"
    assert seams["policy_bundle"]["identity_relation"] == ("DISTINCT_NOT_IDENTICAL")
    assert seams["policy_bundle"]["bundle_links"] == []
    assert seams["policy_bundle"]["rule_version_links"] == []
    assert seams["publication_snapshot"]["entity"] == (
        "publishing.publication_snapshot"
    )
    assert seams["publication_snapshot"]["relation_status"] == (
        "UNLINKED_CANDIDATE_SEAM"
    )
    assert seams["publication_snapshot"]["version_links"] == []
    assert seams["publication_snapshot"]["affected_articles"] == []
    policy_reference = plan["catalog_projection"]["editorial_policy_reference"]
    assert policy_reference["runtime_policy_bundle_id"] is None
    assert policy_reference["rule_version_links"] == []
    assert policy_reference["mapping_validation"] == (
        "EXACT_REFERENCED_POLICY_IDS_EXIST"
    )


def test_empty_affected_articles_means_query_not_executed_not_zero() -> None:
    evaluation = generator.reference_plan(generator.load_contract())[
        "evaluation_boundary"
    ]
    assert evaluation["impact_query"] == "NOT_EVALUATED"
    assert evaluation["affected_articles"] == []
    assert evaluation["affected_articles_empty_interpretation"] == (
        "QUERY_NOT_EXECUTED_NOT_ZERO_AFFECTED"
    )
    for name in (
        "snapshot_instances",
        "official_content_bytes",
        "change_diffs",
        "join_records",
        "version_links",
        "due_evaluations",
        "alert_records",
        "audit_events",
    ):
        assert evaluation[name] == []
    assert evaluation["overdue"] == "NOT_EVALUATED"


def test_alert_and_runbook_are_inert_and_severity_mapping_is_unresolved() -> None:
    projection = generator.reference_plan(generator.load_contract())[
        "catalog_projection"
    ]
    alert = projection["alert_reference"]
    runbook = projection["runbook_reference"]

    assert alert["id"] == "ALT-019"
    assert alert["severity"] == "SEV4"
    assert alert["ops_severity_mapping"] == "NOT_DEFINED"
    assert alert["authority"] == "INERT_CATALOG_TEXT_ONLY"
    assert alert["state"] == "NOT_EVALUATED"
    assert alert["records"] == []
    assert runbook["id"] == "RB-018"
    assert runbook["authority"] == "INERT_CATALOG_TEXT_ONLY"
    assert runbook["execution"] == "NOT_EXECUTED"


def test_unresolved_gates_retain_restrictive_human_gated_defaults() -> None:
    plan = generator.reference_plan(generator.load_contract())
    assert plan["unresolved_gates"] == generator.EXPECTED_UNRESOLVED_GATES
    assert [row["id"] for row in plan["unresolved_gates"]] == [
        "OPEN-018",
        "OD-008",
        "OD-011",
    ]
    assert all(row["human_gated"] is True for row in plan["unresolved_gates"])


def test_pro_unavailable_record_has_no_proposal_or_content_authority() -> None:
    pro = generator.reference_plan(generator.load_contract())["pro_assistance"]
    assert pro == generator.EXPECTED_PRO_ASSISTANCE
    assert pro["status"] == "PRO_UNAVAILABLE"
    assert pro["authority"] == "NONE"
    assert pro["proposal_captured"] is False
    assert pro["content_used"] is False


def test_execution_surface_and_action_counts_are_empty() -> None:
    boundary = generator.reference_plan(generator.load_contract())["execution_boundary"]
    for name in (
        "network",
        "filesystem_runtime",
        "database",
        "api",
        "job",
        "event",
        "provider",
        "clock",
        "alert",
        "audit",
        "activation",
        "hold",
        "kill",
        "re_review",
        "publication",
    ):
        assert boundary[name] == "NOT_EXECUTED"
    assert boundary["runtime_reader"] == "NOT_IMPLEMENTED"
    assert boundary["external_actions"] == []
    assert all(
        type(value) is int and value == 0
        for value in boundary["action_counts"].values()
    )


def test_traceability_divergence_and_formal_boundaries_are_explicit() -> None:
    verification = generator.reference_plan(generator.load_contract())[
        "verification_boundary"
    ]
    assert verification["story_test_suites"] == ["TST-005", "TST-020"]
    assert verification["master_trace_test_suites"] == [
        "TST-005",
        "TST-019",
        "TST-020",
    ]
    assert verification["acceptance_trace_test_suites"] == [
        "TST-008",
        "TST-020",
    ]
    assert verification["traceability_status"] == ("DIVERGENT_RECORDED_NOT_RESOLVED")
    for name in (
        "formal_tst_005",
        "formal_tst_019",
        "formal_tst_020",
        "live",
        "staging",
        "release",
        "production",
    ):
        assert verification[name] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["production_eligible"] is False
    assert verification["approval"] is None


def test_installed_json_has_exact_top_sections_and_boundary() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"]["executable"] is False
    assert plan["document"]["story_acceptance"] is False
    assert plan["document"]["production_eligible"] is False
    assert plan["verification_boundary"]["effective_canonical_status"] == ("UNCHANGED")
