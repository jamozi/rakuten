from __future__ import annotations

from pathlib import Path

from scripts import build_st1607_gate_evidence_pack as builder


def test_contract_is_closed_and_hash_bound(contract: dict[str, object]) -> None:
    assert tuple(contract) == builder.TOP_LEVEL_KEYS
    assert len(contract["sources"]) == len(builder.EXPECTED_SOURCE_HASHES)  # type: ignore[arg-type]
    assert contract["dependency_bindings"] == builder._expected_dependency_bindings()  # noqa: SLF001
    assert contract["decision_gate_binding"] == (builder.EXPECTED_DECISION_GATE_BINDING)
    assert all(
        len(digest) == 64
        for digest in (
            *builder.EXPECTED_SOURCE_HASHES.values(),
            *builder.EXPECTED_DEPENDENCY_HASHES.values(),
            *builder.EXPECTED_DECISION_GATE_HASHES.values(),
        )
    )


def test_snapshot_context_is_explicitly_incomplete(
    contract: dict[str, object],
) -> None:
    snapshot = contract["snapshot_boundary"]
    assert isinstance(snapshot, dict)
    assert snapshot["local_base_commit"] == builder.LOCAL_BASE_COMMIT
    assert snapshot["local_base_commit_type"] == builder.LOCAL_BASE_COMMIT_TYPE
    assert snapshot["local_base_commit_status"] == builder.LOCAL_BASE_COMMIT_STATUS
    assert snapshot["local_base_commit_scope"] == (
        "PREDECESSOR_CHECKOUT_PROVENANCE_ONLY"
    )
    assert snapshot["local_base_commit_qualifying_evidence"] is False
    assert snapshot["source_freeze_identifier_type"] == builder.SOURCE_FREEZE_ID_TYPE
    assert snapshot["source_freeze_status"] == "ABSENT"
    assert snapshot["source_freeze_identifier"] is None
    assert snapshot["source_freeze_qualifying_evidence"] is False
    assert snapshot["reviewed_implementation_tree_commit_type"] == (
        builder.REVIEWED_TREE_COMMIT_TYPE
    )
    assert snapshot["reviewed_implementation_tree_commit_status"] == "ABSENT"
    assert snapshot["reviewed_implementation_tree_commit_qualifying_evidence"] is False
    for key in (
        "reviewed_implementation_tree_commit",
        "target_release_version",
        "staging_execution_identifier",
        "snapshot_observed_at",
        "data_snapshot_identifier",
        "release_identifier",
    ):
        assert snapshot[key] is None
    assert snapshot["approved_exceptions"] == []
    assert snapshot["human_approval_artifacts"] == []


def test_formal_and_authority_boundaries_remain_closed(
    contract: dict[str, object],
) -> None:
    evidence = contract["evidence_boundary"]
    authority = contract["authority_boundary"]
    execution = contract["execution_boundary"]
    assert isinstance(evidence, dict)
    assert isinstance(authority, dict)
    assert isinstance(execution, dict)
    assert evidence["formal_tst_032"] == "NOT_EXECUTED"
    assert evidence["hosted_ci"] == "NOT_EXECUTED"
    assert evidence["staging"] == "NOT_EXECUTED"
    assert evidence["release"] == "NOT_AUTHORIZED"
    assert evidence["production"] == "NOT_AUTHORIZED"
    assert evidence["gate_pass_claim"] is False
    assert evidence["story_acceptance"] is False
    assert all(
        value == "NONE"
        for key, value in authority.items()
        if key != "approval_artifacts"
    )
    assert authority["approval_artifacts"] == []
    assert execution["executable"] is False
    assert execution["input_size_limit_bytes"] == builder.MAX_INPUT_BYTES
    assert execution["input_read_model"] == (
        "ROOT_FD_DESCRIPTOR_RELATIVE_CAPTURED_LEAF"
    )
    assert execution["implementation_input_behavior"] == (
        "HASH_VERIFY_ONLY_NEVER_IMPORT_OR_EXECUTE"
    )
    assert execution["external_action_count"] == 0


def test_bound_artifact_paths_are_repository_relative() -> None:
    for relative in (
        *map(Path, builder.EXPECTED_SOURCE_HASHES),
        *map(Path, builder.EXPECTED_DEPENDENCY_HASHES),
        *map(Path, builder.EXPECTED_DECISION_GATE_HASHES),
    ):
        assert not relative.is_absolute()
        assert ".." not in relative.parts


def test_completion_record_is_local_only_and_preserves_gate_boundaries() -> None:
    completion = builder._load_yaml(  # noqa: SLF001
        builder.REPO_ROOT,
        builder.COMPLETION_PATH,
        "completion",
    )
    assert completion["document"] == {
        "id": "RAOS-ST1607-LOCAL-IMPLEMENTATION-COMPLETION-20260824-V1",
        "schema_version": 1,
        "story_id": "ST-1607",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "recorded_at": "2026-08-24T00:00:00Z",
        "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
        "generated": False,
    }
    authority = completion["authority_boundary"]
    assert isinstance(authority, dict)
    assert all(value is False for value in authority.values())
    identity = completion["snapshot_identity_boundary"]
    assert isinstance(identity, dict)
    assert identity["local_base_commit_qualifying_evidence"] is False
    assert identity["source_freeze_status"] == "ABSENT"
    assert identity["source_freeze_identifier"] is None
    assert identity["reviewed_implementation_tree_commit_status"] == "ABSENT"
    assert identity["reviewed_implementation_tree_commit"] is None
    formal = completion["formal_and_external_boundaries"]
    assert isinstance(formal, dict)
    assert formal["formal_tst_032"] == "NOT_EXECUTED"
    assert formal["human_gate_approvals"] == "NOT_EXECUTED"
    assert formal["staging"] == "NOT_EXECUTED"
    assert formal["production"] == "NOT_EXECUTED"
    assert formal["validated_claim"] == "FORBIDDEN"


def test_all_owned_paths_remain_inside_story_or_isolated_test_scope() -> None:
    assert builder.CONTRACT_PATH.parts[:2] == ("changes", "st-1607")
    assert builder.REPORT_PATH.parts[:3] == ("changes", "st-1607", "generated")
    assert builder.MANIFEST_PATH.parts[:2] == ("changes", "st-1607")
    assert builder.COMPLETION_PATH.parts[:2] == ("changes", "st-1607")
    assert builder.GENERATOR_PATH == Path("scripts/build_st1607_gate_evidence_pack.py")
    assert all(path.parts[0] == "tests" for path in builder.TEST_PATHS)
