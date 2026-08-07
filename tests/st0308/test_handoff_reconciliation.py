"""Independent physical reconstruction and deterministic report checks."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile

import yaml

import pytest

from conftest import (
    EXPECTED_ARCHIVE_BYTES,
    EXPECTED_ARCHIVE_DIRECTORY_COUNT,
    EXPECTED_ARCHIVE_MEMBER_COUNT,
    EXPECTED_ARCHIVE_MEMBER_BYTES,
    EXPECTED_ARCHIVE_REGULAR_MEMBER_COUNT,
    EXPECTED_ARCHIVE_TUPLE,
    EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
    EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_BYTES,
    EXPECTED_HANDOFF_BYTES,
    EXPECTED_INVENTORY_SHA256,
    EXPECTED_LOCK_VERSION_RELATIONS,
    EXPECTED_PHYSICAL_TABLE_RELATIONS,
    EXPECTED_REPOSITORY_TEXT_BYTES,
    EXPECTED_SQL_FRAGMENT_BYTES,
    EXPECTED_STATE_CAS_RELATIONS,
    EXPECTED_VALIDATOR_CONTRACT_SHA256,
    PINNED_SQL_FRAGMENT_PATHS,
    PINNED_SOURCE_REFERENCE_TUPLES,
    EXPECTED_TABLE_COUNT,
    EXPECTED_VIEW_COUNT,
    _live_physical_relation_sets,
    clone_candidate,
    load_validator_module,
    report,
    run_validator,
)


LEGACY_NINE_STATE_CAS_RELATIONS = frozenset(
    {
        "catalog.ingestion_request",
        "catalog.provider_endpoint",
        "editorial.article_disclosure_context",
        "editorial.media_asset",
        "editorial.review_comment",
        "evidence.first_hand_experience_record",
        "iam.principal_role_assignment",
        "policy.finding",
        "policy.waiver",
    }
)


def test_contract_digest_matches_independent_literal_and_validator_pin() -> None:
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
    )
    digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    validator = load_validator_module()
    assert digest == EXPECTED_VALIDATOR_CONTRACT_SHA256
    assert validator.EXPECTED_CONTRACT_SHA256 == EXPECTED_VALIDATOR_CONTRACT_SHA256


def test_independent_literal_inventory_matches_hash_pinned_live_catalogs() -> None:
    live_relations, live_lock_relations = _live_physical_relation_sets()
    assert live_relations == set(EXPECTED_PHYSICAL_TABLE_RELATIONS)
    assert live_lock_relations == set(EXPECTED_LOCK_VERSION_RELATIONS)
    assert len(EXPECTED_PHYSICAL_TABLE_RELATIONS) == EXPECTED_TABLE_COUNT
    assert len(EXPECTED_LOCK_VERSION_RELATIONS) == 27
    assert len(EXPECTED_STATE_CAS_RELATIONS) == 24
    assert EXPECTED_STATE_CAS_RELATIONS <= live_relations
    assert EXPECTED_STATE_CAS_RELATIONS.isdisjoint(live_lock_relations)
    normalized = (
        "ST0308_PHYSICAL_INVENTORY_V1\n"
        "postgresql_server_version_num=180004\n"
        + "".join(
            f"TABLE\t{relation}\n"
            for relation in sorted(EXPECTED_PHYSICAL_TABLE_RELATIONS)
        )
        + "VIEW\tcatalog.v_safe_offer_current\n"
    ).encode("utf-8")
    assert hashlib.sha256(normalized).hexdigest() == EXPECTED_INVENTORY_SHA256


def test_physical_inputs_reconstruct_103_tables_one_view_and_27_lock_relations(
    candidate_path: Path,
) -> None:
    process = run_validator(candidate_path)
    result = report(process)
    derived = result["derived_physical_inventory"]
    assert derived["tables"] == EXPECTED_TABLE_COUNT
    assert derived["views"] == EXPECTED_VIEW_COUNT
    assert derived["inventory_sha256"] == EXPECTED_INVENTORY_SHA256
    assert set(derived["lock_version_relations"]) == set(
        EXPECTED_LOCK_VERSION_RELATIONS
    )


def test_exact_24_state_cas_set_passes_and_legacy_nine_fails(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    candidate_path: Path,
) -> None:
    exact_process = run_validator(candidate_path)
    exact_result = report(exact_process)
    assert exact_process.returncode == 0
    assert exact_result["checks"]["state_cas_without_lock_version_reconciliation"] == {
        "status": "PASS"
    }

    legacy = clone_candidate(pass_candidate)
    legacy_models = legacy["DESIGN_HANDOFF_V1"]["decision"]["port_contracts"][  # type: ignore[index]
        "concurrency_models"
    ]
    legacy_models["STATE_CAS_WITHOUT_LOCK_VERSION"]["relations"] = sorted(  # type: ignore[index]
        LEGACY_NINE_STATE_CAS_RELATIONS
    )
    legacy_path = tmp_path / "legacy-nine-state-cas.yaml"
    legacy_path.write_text(
        yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    legacy_process = run_validator(legacy_path)
    legacy_result = report(legacy_process)
    assert len(LEGACY_NINE_STATE_CAS_RELATIONS) == 9
    assert LEGACY_NINE_STATE_CAS_RELATIONS < EXPECTED_STATE_CAS_RELATIONS
    assert legacy_process.returncode == 1
    assert legacy_result["checks"]["state_cas_without_lock_version_reconciliation"] == {
        "status": "FAIL",
        "reason_codes": ["state_cas_relation_set_mismatch"],
    }
    assert "state_cas_relation_set_mismatch" in legacy_result["errors"]


def test_verified_v2_bundle_binds_the_approved_member(candidate_path: Path) -> None:
    result = report(run_validator(candidate_path))
    assert result["verified_v2_bundle"] == {
        "archive_path": EXPECTED_ARCHIVE_TUPLE[0],
        "archive_sha256": EXPECTED_ARCHIVE_TUPLE[1],
        "approved_input_member": EXPECTED_ARCHIVE_TUPLE[2],
        "approved_input_sha256": EXPECTED_ARCHIVE_TUPLE[3],
        "regular_member_count": EXPECTED_ARCHIVE_REGULAR_MEMBER_COUNT,
        "regular_member_uncompressed_bytes": EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_BYTES,
    }
    contract = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2]
            / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
        ).read_text(encoding="utf-8")
    )
    assert (
        contract["v2_bundle"]["expected_member_count"] == EXPECTED_ARCHIVE_MEMBER_COUNT
    )
    assert (
        contract["v2_bundle"]["expected_regular_file_count"]
        == EXPECTED_ARCHIVE_REGULAR_MEMBER_COUNT
    )
    assert (
        contract["v2_bundle"]["expected_directory_count"]
        == EXPECTED_ARCHIVE_DIRECTORY_COUNT
    )


def test_generic_read_limits_are_exact_and_routed_by_input_kind(
    tmp_path: Path,
) -> None:
    validator = load_validator_module()
    contract = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2]
            / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
        ).read_text(encoding="utf-8")
    )
    for limit in (
        EXPECTED_SQL_FRAGMENT_BYTES,
        EXPECTED_REPOSITORY_TEXT_BYTES,
        EXPECTED_ARCHIVE_BYTES,
    ):
        path = tmp_path / f"read-{limit}.bin"
        path.write_bytes(b"x" * limit)
        assert len(validator._secure_read_absolute(path, limit=limit)) == limit
        path.write_bytes(b"x" * (limit + 1))
        with pytest.raises(validator.TrustedFailure) as error:
            validator._secure_read_absolute(path, limit=limit)
        assert error.value.code == "file_oversized"

    for path, _digest in PINNED_SOURCE_REFERENCE_TUPLES:
        if path in PINNED_SQL_FRAGMENT_PATHS:
            expected = EXPECTED_SQL_FRAGMENT_BYTES
        elif path == EXPECTED_ARCHIVE_TUPLE[0]:
            expected = EXPECTED_ARCHIVE_BYTES
        else:
            expected = EXPECTED_REPOSITORY_TEXT_BYTES
        assert validator._limit_for_path(contract, path) == expected
    assert contract["limits"]["archive_member_bytes"] == EXPECTED_ARCHIVE_MEMBER_BYTES
    assert (
        contract["limits"]["archive_uncompressed_regular_bytes"]
        == EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT
    )
    assert EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_BYTES < (
        EXPECTED_ARCHIVE_REGULAR_MEMBER_COUNT * EXPECTED_ARCHIVE_MEMBER_BYTES
    )


def test_archive_member_read_limit_is_independent_from_cumulative_budget() -> None:
    validator = load_validator_module()
    exact_stream = io.BytesIO(b"x" * EXPECTED_ARCHIVE_MEMBER_BYTES)
    exact = validator._read_archive_member_limited(
        exact_stream,
        EXPECTED_ARCHIVE_MEMBER_BYTES,
        limit=EXPECTED_ARCHIVE_MEMBER_BYTES,
    )
    assert len(exact) == EXPECTED_ARCHIVE_MEMBER_BYTES

    oversized_stream = io.BytesIO(b"x" * (EXPECTED_ARCHIVE_MEMBER_BYTES + 1))
    with pytest.raises(validator.TrustedFailure) as member_error:
        validator._read_archive_member_limited(
            oversized_stream,
            EXPECTED_ARCHIVE_MEMBER_BYTES + 1,
            limit=EXPECTED_ARCHIVE_MEMBER_BYTES,
        )
    assert member_error.value.code == "bundle_member_oversized"

    overread_stream = io.BytesIO(b"x" * (EXPECTED_ARCHIVE_MEMBER_BYTES + 1))
    with pytest.raises(validator.TrustedFailure) as read_error:
        validator._read_archive_member_limited(
            overread_stream,
            EXPECTED_ARCHIVE_MEMBER_BYTES,
            limit=EXPECTED_ARCHIVE_MEMBER_BYTES,
        )
    assert read_error.value.code == "bundle_member_read_limit"

    class Unreadable:
        def read(self, _limit: int) -> bytes:
            raise OSError("probe")

    with pytest.raises(validator.TrustedFailure) as unreadable_error:
        validator._read_archive_member_limited(
            Unreadable(),
            0,
            limit=EXPECTED_ARCHIVE_MEMBER_BYTES,
        )
    assert unreadable_error.value.code == "bundle_member_unreadable"

    symlink = tarfile.TarInfo("link")
    symlink.type = tarfile.SYMTYPE
    with pytest.raises(validator.TrustedFailure) as special_error:
        validator._validate_archive_member_kind(symlink)
    assert special_error.value.code == "bundle_special_member"

    with pytest.raises(validator.TrustedFailure) as cumulative_error:
        validator._advance_archive_regular_bytes(
            0,
            EXPECTED_ARCHIVE_MEMBER_BYTES,
            limit=EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
        )
    assert cumulative_error.value.code == "bundle_uncompressed_regular_bytes_limit"


def test_archive_cumulative_regular_limit_accepts_exact_and_rejects_first_over() -> (
    None
):
    validator = load_validator_module()
    exact = validator._advance_archive_regular_bytes(
        0,
        EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
        limit=EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
    )
    assert exact == EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT
    with pytest.raises(validator.TrustedFailure) as error:
        validator._advance_archive_regular_bytes(
            0,
            EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT + 1,
            limit=EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
        )
    assert error.value.code == "bundle_uncompressed_regular_bytes_limit"


def test_structured_archive_reference_can_bind_the_archive_source(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    refs[:] = [  # type: ignore[index]
        row
        for row in refs
        if row.get("path") != "changes/st-0308/pro-correction-input.v2.tar.gz"
    ]
    path = tmp_path / "structured-archive-only.yaml"
    path.write_text(
        yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    result = report(run_validator(path))
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_report_is_byte_identical_for_identical_candidate_bytes(
    candidate_path: Path,
) -> None:
    first = run_validator(candidate_path)
    second = run_validator(candidate_path)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr == ""


def test_compact_json_and_empty_stderr_are_deterministic_for_all_outcomes(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    candidate_path: Path,
) -> None:
    ordinary = clone_candidate(pass_candidate)
    ordinary["DESIGN_HANDOFF_V1"]["open_decisions"] = ["unresolved"]  # type: ignore[index]
    ordinary_path = tmp_path / "ordinary-failure.yaml"
    ordinary_path.write_text(
        yaml.safe_dump(ordinary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    oversized_path = tmp_path / "oversized-failure.yaml"
    oversized_path.write_bytes(b"x" * (EXPECTED_HANDOFF_BYTES + 1))

    for path, expected_returncode in (
        (candidate_path, 0),
        (ordinary_path, 1),
        (oversized_path, 1),
    ):
        first = run_validator(path)
        second = run_validator(path)
        assert first.returncode == second.returncode == expected_returncode
        assert first.stdout == second.stdout
        assert first.stderr == second.stderr == ""
        assert first.stdout.endswith("\n")
        assert "\n" not in first.stdout.rstrip("\n")
        parsed = json.loads(first.stdout)
        assert first.stdout == (
            json.dumps(
                parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        )


def test_physical_inventory_is_not_taken_from_candidate_self_report(
    candidate_path: Path,
) -> None:
    payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    payload["DESIGN_HANDOFF_V1"]["approved_scope"]["physical_cut"]["tables"] = 1
    candidate_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    process = run_validator(candidate_path, expected_sha256=digest)
    result = report(process)
    assert process.returncode == 1
    assert result["derived_physical_inventory"]["tables"] == EXPECTED_TABLE_COUNT
    assert result["checks"]["physical_inventory_reconciliation"]["status"] == "FAIL"


def test_weak_semantic_stubs_remain_manual_required(
    candidate_path: Path,
) -> None:
    payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    decision = payload["DESIGN_HANDOFF_V1"]["decision"]
    decision["transaction_boundary"] = {"module_uows": "stub"}
    decision["mapping_strategy"] = {"representation": "alternate"}
    decision["cross_module_and_outbox_boundary"] = {
        "shared_infrastructure": "separate valid adapters",
        "idempotency": "opaque claim handle",
        "aggregate_versions": "manual event-source review",
    }
    decision["connection_and_identity_boundary"] = {"boundary": "stub"}
    decision["port_contracts"]["state_cas_predicates"] = {
        "policy.finding": "manual predicate review",
        "policy.waiver": "manual predicate review",
    }
    candidate_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    process = run_validator(candidate_path, expected_sha256=digest)
    result = report(process)
    assert process.returncode == 0
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"
    for name in (
        "inward_uow_surfaces_all_modules_and_joined_forms",
        "shared_audit_outbox_idempotency_ownership",
        "idempotency_completion_cas_expressibility",
        "aggregate_version_source_or_event_exclusion",
        "exact_state_cas_predicates",
        "domain_value_mapper_targets",
        "connection_and_identity_boundary_semantics",
    ):
        assert result["checks"][name]["status"] == "MANUAL_REQUIRED"


def test_negative_words_are_not_lexically_interpreted(
    candidate_path: Path,
) -> None:
    payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    models = payload["DESIGN_HANDOFF_V1"]["decision"]["port_contracts"][
        "concurrency_models"
    ]
    models["LOCK_VERSION_CAS"]["rule"] = (
        "expected_version is forbidden in this descriptive sentence."
    )
    models["STATE_CAS_WITHOUT_LOCK_VERSION"]["rule"] = (
        "expected_version is not used by this non-versioned classification."
    )
    payload["DESIGN_HANDOFF_V1"]["decision"]["cross_module_and_outbox_boundary"][
        "aggregate_version_rule"
    ] = "not a synthetic counter or timestamp"
    candidate_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    process = run_validator(candidate_path, expected_sha256=digest)
    result = report(process)
    assert process.returncode == 0
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_report_never_claims_implementation_authority(
    candidate_path: Path,
) -> None:
    process = run_validator(candidate_path)
    result = report(process)
    assert result["implementation_authority"] == "NOT_GRANTED"
    assert result["exact_byte_owner_approval_required"] is True
    assert result["manual_canonical_reconciliation_required"] is True
    assert result["automated_pass_authorizes_implementation"] is False
    assert "formal" not in json.dumps(result, sort_keys=True).casefold()
