#!/usr/bin/env python3
"""Owner-generate the deterministic recorded-local ST-0504 V2 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Final, NoReturn, cast


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.sqlite_product_identity_runtime_v2 import (  # noqa: E402
    ProductIdentitySqliteCommitFaultV2,
)
from raos.domain.catalog.product_identity_runtime_v2 import (  # noqa: E402
    PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2,
    PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2,
    PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2,
    PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2,
    PRODUCT_IDENTITY_EVENT_CHANNEL_V2,
    PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2,
    PRODUCT_IDENTITY_OPEN_DECISION_V2,
    PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2,
    PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
    ProductIdentityDecisionTypeV2,
    ProductIdentityReadinessV2,
    ProductIdentityReviewStatusV2,
)


CONTRACT: Final = Path("changes/st-0504/contracts/product-identity-runtime.v2.json")
FIXTURE: Final = Path(
    "changes/st-0504/fixtures/product-identity-recorded.synthetic.v2.json"
)
OUTPUT: Final = Path("changes/st-0504/generated/product-identity-runtime.v2.json")
EVIDENCE: Final = Path("changes/st-0504/evidence/local-evidence-proposal.v2.json")
MANIFEST: Final = Path("changes/st-0504/runtime-manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0504_product_identity_runtime.py")
CANONICAL: Final = (
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"),
    Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
)
DEPENDENCY_SOURCE: Final = (
    Path("changes/st-0503/contracts/catalog-normalization-runtime.v2.json"),
    Path("changes/st-0503/generated/catalog-normalization-runtime.v2.json"),
    Path("changes/st-0503/manifest.v2.json"),
    Path("python/raos/domain/catalog/catalog_normalization_runtime_v2.py"),
    Path("python/raos/ports/catalog_normalization_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_catalog_normalization_runtime_v2.py"),
    Path("python/raos/application/iam/authorization.py"),
    Path("python/raos/domain/iam/authorization.py"),
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/catalog/product_identity_runtime_v2.py"),
    Path("python/raos/ports/product_identity_runtime_v2.py"),
    Path("python/raos/application/catalog/product_identity_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_product_identity_runtime_v2.py"),
)
TEST_SOURCE: Final = (
    Path("tests/st0504/runtime_v2_support.py"),
    Path("tests/st0504/test_product_identity_runtime_v2.py"),
    Path("tests/st0504/test_product_identity_runtime_v2_storage.py"),
    Path("tests/st0504/test_product_identity_runtime_v2_generator.py"),
)
DOCUMENTATION: Final = (Path("changes/st-0504/README-v2.md"),)
SOURCE_PATHS: Final = (
    *CANONICAL,
    *DEPENDENCY_SOURCE,
    *RUNTIME_SOURCE,
    *TEST_SOURCE,
    *DOCUMENTATION,
    CONTRACT,
    FIXTURE,
    GENERATOR,
)
GENERATED_PATHS: Final = (OUTPUT, EVIDENCE, MANIFEST)
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
GENERATION_COMMAND: Final = "python scripts/build_st0504_product_identity_runtime.py"


class ProductIdentityBuildError(RuntimeError):
    """Sanitized deterministic owner-generator failure."""

    __slots__ = ()


def _fail(code: str) -> NoReturn:
    raise ProductIdentityBuildError(f"ST-0504 V2 build failed: {code}") from None


def _path(relative: Path) -> Path:
    candidate = REPO_ROOT / relative
    try:
        resolved = candidate.resolve(strict=True)
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or REPO_ROOT not in resolved.parents
        ):
            _fail("SOURCE_PATH_INVALID")
    except OSError:
        _fail("SOURCE_PATH_INVALID")
    return candidate


def _read(relative: Path) -> bytes:
    try:
        value = _path(relative).read_bytes()
    except OSError:
        _fail("SOURCE_UNAVAILABLE")
    if not value or len(value) > MAX_SOURCE_BYTES:
        _fail("SOURCE_SIZE_INVALID")
    return value


def _sha(relative: Path) -> str:
    return hashlib.sha256(_read(relative)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail("JSON_DUPLICATE_OR_KEY_INVALID")
        result[key] = value
    return result


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("JSON_OBJECT_REQUIRED")
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        _fail("JSON_OBJECT_REQUIRED")
    return {cast(str, key): item for key, item in raw.items()}


def _json_object(relative: Path) -> dict[str, object]:
    try:
        value = cast(
            object,
            json.loads(
                _read(relative).decode("utf-8", errors="strict"),
                object_pairs_hook=_pairs,
                parse_constant=lambda _value: _fail("JSON_NONFINITE"),
            ),
        )
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    return _mapping(value)


def _string_list(value: object) -> list[str]:
    if type(value) is not list:
        _fail("STRING_LIST_REQUIRED")
    values = cast(list[object], value)
    if any(type(item) is not str for item in values):
        _fail("STRING_LIST_REQUIRED")
    return cast(list[str], values)


def _all_exact(mapping: dict[str, object], expected: dict[str, object]) -> bool:
    return all(mapping.get(key) == value for key, value in expected.items())


def _validate_contract(contract: dict[str, object]) -> None:
    source = _mapping(contract.get("source_boundary"))
    identity = _mapping(contract.get("identity_boundary"))
    decision = _mapping(contract.get("human_decision_boundary"))
    authorization = _mapping(contract.get("authorization_boundary"))
    durability = _mapping(contract.get("durability_boundary"))
    recommendation = _mapping(contract.get("recommendation_boundary"))
    execution = _mapping(contract.get("execution_boundary"))
    formal = _mapping(contract.get("formal_evidence"))
    if not _all_exact(
        contract,
        {
            "schema_version": "2.0.0",
            "story_id": "ST-0504",
            "classification": "RECORDED_LOCAL_HUMAN_REVIEW_PRODUCT_IDENTITY_RUNTIME",
            "local_implementation_status": "LOCAL_CODE_COMPLETE",
            "canonical_status": "UNCHANGED",
        },
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if not _all_exact(
        source,
        {
            "dependency_story": "ST-0503",
            "accepted_type": "PersistedCatalogNormalizationV2",
            "exact_type_required": True,
            "source_snapshot_hash_required": True,
            "source_batch_hash_required": True,
            "source_candidate_record_hash_required": True,
            "source_receipt_and_raw_hash_required": True,
            "source_chain_and_persisted_record_hash_required": True,
            "provider_or_network_capability": False,
            "external_actions": 0,
        },
    ):
        _fail("SOURCE_BOUNDARY_INVALID")
    if (
        not _all_exact(
            identity,
            {
                "open_decision": PRODUCT_IDENTITY_OPEN_DECISION_V2,
                "open_decision_resolved": False,
                "review_status": ProductIdentityReviewStatusV2.HUMAN_REVIEW.value,
                "readiness": ProductIdentityReadinessV2.NOT_READY.value,
                "all_candidate_pairs_queued": True,
                "automatic_merge": False,
                "automatic_split": False,
                "identity_inference": False,
                "grouping_inference": False,
                "canonical_product_creation": False,
                "grouping_application": False,
                "ranking_surface": False,
            },
        )
        or _string_list(identity.get("category_rules")) != []
        or _string_list(identity.get("thresholds")) != []
        or _string_list(identity.get("scores")) != []
    ):
        _fail("IDENTITY_BOUNDARY_INVALID")
    if _string_list(decision.get("decision_types")) != [
        value.value for value in ProductIdentityDecisionTypeV2
    ] or not _all_exact(
        decision,
        {
            "reason_required": True,
            "actor_session_fingerprint_required": True,
            "authorization_provenance_required": True,
            "append_only_history": True,
            "past_decision_mutation": False,
            "supersede_by_new_decision": True,
            "decision_is_grouping_execution": False,
            "decision_changes_readiness": False,
            "decision_changes_ranking": False,
        },
    ):
        _fail("DECISION_BOUNDARY_INVALID")
    if not _all_exact(
        authorization,
        {
            "service": "DurableAuthorizationService.recover_admin",
            "active_session_recheck_required": True,
            "exact_result_and_request_digest_revalidation": True,
            "exact_audit_digest_recomputation": True,
            "collaborator_material_pre_post_recomputation": True,
            "store_action_count_exact_zero": True,
            "operation_id": PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2,
            "action": PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2,
            "resource_kind": PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2,
            "resource_state": None,
            "site_binding_required": True,
            "resource_id_inference": False,
            "current_canonical_binding": "BLOCKED",
            "current_block_reason": "STEP_UP_RESOURCE_UNMAPPED",
            "new_authorization_issuance": False,
            "recorded_durable_allow_recovery_only": True,
            "ambiguous_mapping_outcome": "QUEUE_ONLY_NO_DECISION_WRITE",
        },
    ):
        _fail("AUTHORIZATION_BOUNDARY_INVALID")
    if (
        durability.get("backend") != "OWNER_PRIVATE_SQLITE"
        or durability.get("directory_mode") != "0700"
        or durability.get("database_mode") != "0600"
        or durability.get("rollback_detection_scope") != "SAME_STORE_PROCESS_ONLY"
        or durability.get("cross_process_restart_rollback_detection") is not False
        or durability.get("external_rollback_anchor") is not False
        or any(
            durability.get(key) is not True
            for key in (
                "exact_schema_binding",
                "strict_tables",
                "exclusive_created_initialization",
                "preexisting_uninitialized_database_rejected",
                "live_device_inode_pinned",
                "exact_foreign_keys",
                "append_only_schema_triggers",
                "canonical_stored_json_required",
                "canonical_uuid_and_rfc3339_required",
                "atomic_queue_pairs_state_outbox_journal",
                "atomic_decision_state_outbox_journal",
                "compare_and_swap",
                "idempotency_journal",
                "per_queue_hash_chain",
                "append_only_decisions",
                "ambiguous_commit_recovery",
                "sqlite_commit_exception_exact_recovery",
                "restart_recovery",
                "process_local_monotonic_prefix_pin",
                "same_process_rollback_detection",
                "concurrency_fail_closed",
                "tamper_fail_closed",
                "schema_drift_fail_closed",
                "symlink_rejected",
                "hardlink_rejected",
                "unsafe_path_rejected",
            )
        )
    ):
        _fail("DURABILITY_BOUNDARY_INVALID")
    excluded = _string_list(recommendation.get("excluded_inputs"))
    if (
        recommendation.get("ranking_surface") is not False
        or recommendation.get("recommendation_mutation") is not False
        or excluded != list(PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2)
    ):
        _fail("RECOMMENDATION_BOUNDARY_INVALID")
    if (
        execution.get("default_enabled") is not False
        or execution.get("external_actions") != 0
        or execution.get("production_authority") != "NONE"
        or any(
            execution.get(key) is not False
            for key in (
                "http",
                "network",
                "credential",
                "provider",
                "worker",
                "publication",
                "live_write",
            )
        )
    ):
        _fail("EXECUTION_BOUNDARY_INVALID")
    if any(
        formal.get(key) != "NOT_EXECUTED"
        for key in (
            "TST-008_postgresql",
            "live",
            "staging",
            "release",
            "production",
        )
    ):
        _fail("FORMAL_BOUNDARY_INVALID")


def _validate_fixture(fixture: dict[str, object]) -> None:
    source = _mapping(fixture.get("source"))
    expected = _mapping(fixture.get("expected"))
    if (
        not _all_exact(
            fixture,
            {
                "schema_version": "2.0.0",
                "story_id": "ST-0504",
                "synthetic": True,
                "operational_default": False,
                "activation": False,
                "contains_credential_or_production_data": False,
            },
        )
        or not _all_exact(
            source,
            {
                "story_id": "ST-0503",
                "runtime_version": "V2",
                "candidate_count": 2,
                "expected_pair_count": 1,
                "exact_persisted_hash_binding": True,
            },
        )
        or _string_list(expected.get("decision_types"))
        != [value.value for value in ProductIdentityDecisionTypeV2]
        or not _all_exact(
            expected,
            {
                "review_status": ProductIdentityReviewStatusV2.HUMAN_REVIEW.value,
                "readiness": ProductIdentityReadinessV2.NOT_READY.value,
                "first_history_version": 2,
                "supersession_is_append_only": True,
                "grouping_applied": False,
                "ranking_impact": False,
                "external_actions": 0,
            },
        )
        or _string_list(fixture.get("commit_faults"))
        != [value.value for value in ProductIdentitySqliteCommitFaultV2]
    ):
        _fail("FIXTURE_BOUNDARY_INVALID")


def _bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def render_outputs() -> dict[Path, bytes]:
    contract = _json_object(CONTRACT)
    fixture = _json_object(FIXTURE)
    _validate_contract(contract)
    _validate_fixture(fixture)
    projection: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0504",
        "runtime_version": PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "dependency": {
            "story_id": "ST-0503",
            "accepted_type": "PersistedCatalogNormalizationV2",
            "binding": "SNAPSHOT_BATCH_CANDIDATE_RECEIPT_RAW_CHAIN_AND_RECORD_HASHES",
        },
        "state_contract": {
            "review_status": ProductIdentityReviewStatusV2.HUMAN_REVIEW.value,
            "readiness": ProductIdentityReadinessV2.NOT_READY.value,
            "decision_types": [value.value for value in ProductIdentityDecisionTypeV2],
            "commit_faults": [
                value.value for value in ProductIdentitySqliteCommitFaultV2
            ],
        },
        "event_contract": {
            "queue_event_type": PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2,
            "decision_event_type": PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2,
            "channel": PRODUCT_IDENTITY_EVENT_CHANNEL_V2,
            "delivery_worker": "NOT_IMPLEMENTED_NOT_ACTIVATED",
        },
        "source_boundary": contract["source_boundary"],
        "identity_boundary": contract["identity_boundary"],
        "human_decision_boundary": contract["human_decision_boundary"],
        "authorization_boundary": contract["authorization_boundary"],
        "durability_boundary": contract["durability_boundary"],
        "recommendation_boundary": contract["recommendation_boundary"],
        "execution_boundary": contract["execution_boundary"],
        "synthetic_fixture": fixture,
        "formal_evidence": contract["formal_evidence"],
        "external_actions": [],
        "production_authority": "NONE",
    }
    output = _bytes(projection)
    evidence: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0504",
        "classification": "LOCAL_EVIDENCE_PROPOSAL",
        "status_transition_authority": "NONE",
        "source_and_test_artifacts_hash_bound": True,
        "local_check_commands": [
            "pytest -q tests/st0504",
            "pytest -q tests/st0503 tests/st0504",
            "ruff check <owned ST-0504 Python>",
            "mypy --strict <owned ST-0504 Python>",
            "pyright <owned ST-0504 Python>",
            "unshare -Urn pytest -q tests/st0504/test_product_identity_runtime_v2.py tests/st0504/test_product_identity_runtime_v2_storage.py",
        ],
        "formal_evidence": contract["formal_evidence"],
        "live_actions": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "external_actions": [],
        "production_authority": "NONE",
    }
    evidence_bytes = _bytes(evidence)
    sources = {str(path): _sha(path) for path in SOURCE_PATHS}
    manifest: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0504",
        "runtime_version": PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
        "generation_command": GENERATION_COMMAND,
        "source_sha256": sources,
        "generated_sha256": {
            str(OUTPUT): hashlib.sha256(output).hexdigest(),
            str(EVIDENCE): hashlib.sha256(evidence_bytes).hexdigest(),
        },
        "formal_evidence": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "external_actions": [],
        "production_authority": "NONE",
    }
    return {OUTPUT: output, EVIDENCE: evidence_bytes, MANIFEST: _bytes(manifest)}


def _write(relative: Path, content: bytes) -> None:
    target = REPO_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (target.is_symlink() or not target.is_file()):
        _fail("OUTPUT_PATH_INVALID")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except OSError:
            pass
        _fail("OUTPUT_WRITE_FAILED")


def _check(relative: Path, expected: bytes) -> None:
    if _read(relative) != expected:
        _fail("GENERATED_DRIFT")


def build(*, check: bool) -> None:
    outputs = render_outputs()
    for path, content in outputs.items():
        if check:
            _check(path, content)
        else:
            _write(path, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    build(check=arguments.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
