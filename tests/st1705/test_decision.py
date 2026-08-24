from __future__ import annotations

from scripts import build_st1705_pilot_signoff as builder


def test_decision_is_always_blocked_not_signed_off_and_not_eligible(
    contract: dict[str, object],
) -> None:
    record = builder.decision_record(contract)
    decision = record["decision"]
    assert isinstance(decision, dict)
    assert decision["overall"] == "BLOCKED"
    assert decision["gate_0"] == "BLOCKED"
    assert decision["technical_pilot"] == "BLOCKED"
    assert decision["security_sign_off"] == "NOT_SIGNED_OFF"
    assert decision["recovery_sign_off"] == "NOT_SIGNED_OFF"
    assert decision["pilot_eligibility"] == "NOT_ELIGIBLE"
    assert decision["downstream_st_1801_eligibility"] == "NOT_ELIGIBLE"
    assert decision["qualifying_evidence_references"] == []


def test_five_local_articles_are_not_real_pilot_or_revenue_evidence(
    contract: dict[str, object],
) -> None:
    record = builder.decision_record(contract)
    boundary = record["article_artifact_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["exact_article_ids"] == list(builder.ARTICLE_IDS)
    assert boundary["local_artifacts_exist"] is True
    assert boundary["local_artifacts_are_pilot_observations"] is False
    assert boundary["local_artifacts_are_publication_evidence"] is False
    assert boundary["local_artifacts_are_revenue_evidence"] is False
    assert boundary["local_artifacts_are_gate_evidence"] is False
    inputs = record["decision_inputs"]
    assert isinstance(inputs, dict)
    local = inputs["st_1704_local_artifacts"]
    assert local["tracked_article_packet_count"] == 5
    assert local["immutable_publication_snapshot_count"] == 0
    assert local["public_verification_count"] == 0
    assert local["real_pilot_observation_status"] == "UNAVAILABLE"
    assert local["revenue_observation_status"] == "UNAVAILABLE"
    assert local["owner_private_measurement_ledger_read"] is False


def test_required_formal_suites_remain_not_executed(
    contract: dict[str, object],
) -> None:
    record = builder.decision_record(contract)
    rows = record["runtime_evidence"]
    assert isinstance(rows, list)
    assert [row["suite_id"] for row in rows] == ["TST-026", "TST-029", "TST-032"]
    assert all(row["execution_status"] == "NOT_EXECUTED" for row in rows)
    assert all(row["artifact_uri"] is None for row in rows)
    assert all(row["artifact_sha256"] is None for row in rows)
    assert all(row["eligible"] is False for row in rows)


def test_all_fourteen_active_decisions_remain_blocking(
    contract: dict[str, object],
) -> None:
    record = builder.decision_record(contract)
    inputs = record["decision_inputs"]
    assert isinstance(inputs, dict)
    gate = inputs["st_1607_gate_pack"]
    assert gate["active_blocking_open_decisions"] == 14
    assert gate["gate_0_status"] == "BLOCKED"
    assert "ACTIVE_BLOCKING_OPEN_DECISIONS_14" in record["blockers"]


def test_source_freeze_reviewed_tree_and_human_approvals_are_unavailable(
    contract: dict[str, object],
) -> None:
    record = builder.decision_record(contract)
    evidence = record["evidence_boundary"]
    assert isinstance(evidence, dict)
    assert evidence["source_freeze_status"] == "UNAVAILABLE"
    assert evidence["source_freeze_identifier"] is None
    assert evidence["reviewed_implementation_tree_status"] == "UNAVAILABLE"
    assert evidence["reviewed_implementation_tree_commit"] is None
    assert evidence["local_base_commit_qualifying_evidence"] is False
    decision = record["decision"]
    assert decision["approval_artifacts"] == []


def test_authority_and_external_action_surfaces_are_absent(
    contract: dict[str, object],
) -> None:
    record = builder.decision_record(contract)
    authority = record["authority_boundary"]
    execution = record["execution_boundary"]
    assert isinstance(authority, dict)
    assert isinstance(execution, dict)
    assert all(value == "NONE" for value in authority.values())
    assert execution["external_action_count"] == 0
    assert execution["network_access"] == "FORBIDDEN"
    assert execution["credential_access"] == "FORBIDDEN"
    assert execution["status_registry_mutation"] == "FORBIDDEN"
    assert execution["publication_actions"] == "FORBIDDEN"
    assert execution["staging_actions"] == "FORBIDDEN"
    assert execution["release_actions"] == "FORBIDDEN"
    assert execution["production_actions"] == "FORBIDDEN"
