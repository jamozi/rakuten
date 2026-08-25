from __future__ import annotations

from pathlib import Path

from scripts import build_st1705_pilot_signoff as builder


def test_contract_is_closed_and_exactly_hash_bound(
    contract: dict[str, object],
) -> None:
    assert tuple(contract) == builder.TOP_LEVEL_KEYS
    assert contract["source_bindings"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in builder.EXPECTED_SOURCE_HASHES.items()
    ]
    assert contract["dependency_bindings"] == builder._expected_dependency_bindings()  # noqa: SLF001
    assert all(
        len(digest) == 64
        for digest in (
            *builder.EXPECTED_SOURCE_HASHES.values(),
            *builder.EXPECTED_DEPENDENCY_HASHES.values(),
            builder.FORMAL_SCHEMA_SHA256,
        )
    )


def test_future_formal_evidence_port_is_closed_and_default_deny(
    contract: dict[str, object],
) -> None:
    port = contract["formal_evidence_port"]
    assert isinstance(port, dict)
    assert port == {
        "schema_uri": f"repo://{builder.FORMAL_SCHEMA_PATH.as_posix()}",
        "schema_sha256": builder.FORMAL_SCHEMA_SHA256,
        "schema_behavior": "CLOSED_ADDITIONAL_PROPERTIES_FALSE",
        "activation": "DISABLED",
        "current_input_uri": None,
        "current_input_sha256": None,
        "current_input_status": "ABSENT",
        "dynamic_input_path": "FORBIDDEN",
        "authenticity_policy": "INDEPENDENT_FORMAL_OWNER_PIPELINE_REQUIRED",
        "default_decision": "BLOCKED",
        "evidence_cannot_self_authorize": True,
    }
    schema = builder._load_json(  # noqa: SLF001
        builder.REPO_ROOT, builder.FORMAL_SCHEMA_PATH, "schema"
    )
    assert schema["additionalProperties"] is False
    assert len(schema["required"]) == 9  # type: ignore[arg-type]


def test_exact_dependency_roles_do_not_promote_local_artifacts(
    contract: dict[str, object],
) -> None:
    dependencies = contract["dependency_bindings"]
    assert isinstance(dependencies, dict)
    assert dependencies["st_1607"]["role"] == "BLOCKED_GATE_PACK_INPUT"
    assert dependencies["st_1704_self_hosted"]["role"] == "LOCAL_ARTICLE_ARTIFACT_INPUT"
    assert (
        dependencies["st_1704_measurement"]["role"]
        == "LOCAL_MEASUREMENT_INTERFACE_INPUT"
    )


def test_all_owned_paths_are_inside_the_delegated_scope() -> None:
    assert builder.CONTRACT_PATH.parts[:2] == ("changes", "st-1705")
    assert builder.FORMAL_SCHEMA_PATH.parts[:2] == ("changes", "st-1705")
    assert builder.DECISION_PATH.parts[:3] == ("changes", "st-1705", "generated")
    assert builder.MANIFEST_PATH.parts[:2] == ("changes", "st-1705")
    assert builder.GENERATOR_PATH == Path("scripts/build_st1705_pilot_signoff.py")
    assert all(path.parts[:2] == ("tests", "st1705") for path in builder.TEST_PATHS)


def test_completion_record_is_local_only_and_non_attesting() -> None:
    completion = builder._load_yaml(  # noqa: SLF001
        builder.REPO_ROOT, builder.COMPLETION_PATH, "completion"
    )
    document = completion["document"]
    assert document["story_id"] == "ST-1705"
    assert document["status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert document["authority"] == "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY"
    boundary = completion["formal_and_external_boundaries"]
    assert all(
        boundary[key] == "NOT_EXECUTED"
        for key in (
            "formal_tst_026",
            "formal_tst_029",
            "formal_tst_032",
            "source_freeze",
            "reviewed_implementation_tree",
            "human_sign_off",
            "live_pilot",
            "publication",
            "staging",
            "release",
            "deployment",
            "production",
        )
    )
