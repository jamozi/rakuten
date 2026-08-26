#!/usr/bin/env python3
"""Owner-generate deterministic ST-0604 V2 lifecycle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Final, NoReturn, cast


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT: Final = Path(
    "changes/st-0604/contracts/source-packet-lifecycle-runtime.v2.json"
)
FIXTURE: Final = Path(
    "changes/st-0604/fixtures/source-packet-lifecycle.synthetic.v2.json"
)
OUTPUT: Final = Path(
    "changes/st-0604/generated/source-packet-lifecycle-runtime.v2.json"
)
MANIFEST: Final = Path("changes/st-0604/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0604_source_packet_lifecycle_runtime.py")
GENERATION_COMMAND: Final = (
    "python scripts/build_st0604_source_packet_lifecycle_runtime.py"
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/evidence/source_packet_lifecycle_runtime_v2.py"),
    Path("python/raos/ports/source_packet_lifecycle_runtime_v2.py"),
    Path("python/raos/application/evidence/source_packet_lifecycle_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_source_packet_lifecycle_runtime_v2.py"),
)
TEST_SOURCE: Final = (
    Path("tests/st0604/runtime_v2_fixtures.py"),
    Path("tests/st0604/test_source_packet_lifecycle_runtime_v2.py"),
    Path("tests/st0604/test_source_packet_lifecycle_sqlite_v2.py"),
    Path("tests/st0604/test_source_packet_lifecycle_boundaries_v2.py"),
    Path("tests/st0604/test_source_packet_lifecycle_generator_v2.py"),
)
DOCUMENTATION: Final = (
    Path("changes/st-0604/LOCAL-IMPLEMENTATION-COMPLETION-20260825-v2.json"),
    Path("changes/st-0604/PREFLIGHT-v2.md"),
    Path("changes/st-0604/README-v2.md"),
)
CANONICAL: Final = (
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/02_ui/RAOS_08_workflow_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
)
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_DEPENDENCY_ARTIFACT_PATHS: Final = {
    "ST-0403": frozenset(
        {
            "changes/st-0403/contracts/authorization-registry.v1.json",
            "changes/st-0403/contracts/durable-authorization-runtime.v2.json",
            "changes/st-0403/generated/authorization-registry.v1.json",
            "changes/st-0403/manifest.json",
            "python/raos/adapters/generated_st0403_authorization_registry.py",
            "python/raos/adapters/recorded_authorization.py",
            "python/raos/application/iam/authorization.py",
            "python/raos/domain/iam/authorization.py",
            "python/raos/ports/authorization.py",
        }
    ),
    "ST-0602": frozenset(
        {
            "changes/st-0602/contracts/fact-extraction-runtime.v2.json",
            "changes/st-0602/generated/fact-extraction-runtime.v2.json",
            "changes/st-0602/manifest.v2.json",
            "python/raos/adapters/sqlite_fact_extraction_runtime_v2.py",
            "python/raos/application/evidence/fact_extraction_runtime_v2.py",
            "python/raos/domain/evidence/fact_extraction_runtime_v2.py",
            "python/raos/ports/fact_extraction_runtime_v2.py",
        }
    ),
    "ST-0603": frozenset(
        {
            "changes/st-0603/contracts/fact-conflict-runtime.v2.json",
            "changes/st-0603/generated/fact-conflict-runtime.v2.json",
            "changes/st-0603/manifest.v2.json",
            "python/raos/adapters/sqlite_fact_conflict_runtime_v2.py",
            "python/raos/application/evidence/fact_conflict_runtime_v2.py",
            "python/raos/domain/evidence/fact_conflict_runtime_v2.py",
            "python/raos/ports/fact_conflict_runtime_v2.py",
        }
    ),
}


class BuildError(RuntimeError):
    """Closed owner-generator error without source material."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-0604 V2 build failed: {code}") from None


def _path(relative: Path) -> Path:
    candidate = REPO_ROOT / relative
    try:
        resolved = candidate.resolve(strict=True)
        if (
            candidate.is_symlink()
            or not candidate.is_file()
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


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in items:
        if key in output:
            _fail("JSON_DUPLICATE_KEY")
        output[key] = value
    return output


def _json(relative: Path) -> dict[str, object]:
    try:
        value = json.loads(
            _read(relative).decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: _fail("JSON_NONFINITE"),
        )
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    if type(value) is not dict:
        _fail("JSON_OBJECT_REQUIRED")
    return cast(dict[str, object], value)


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("OBJECT_REQUIRED")
    mapping = cast(dict[object, object], value)
    if any(type(key) is not str for key in mapping):
        _fail("OBJECT_REQUIRED")
    return cast(dict[str, object], mapping)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail("LIST_REQUIRED")
    return cast(list[object], value)


def _exact_keys(value: dict[str, object], keys: frozenset[str]) -> None:
    if frozenset(value) != keys:
        _fail("KEY_SET_INVALID")


def _validate_dependency_bindings(value: object) -> dict[str, object]:
    bindings = _mapping(value)
    if frozenset(bindings) != frozenset({"ST-0403", "ST-0602", "ST-0603"}):
        _fail("DEPENDENCY_SET_INVALID")
    expected_types = {
        "ST-0403": None,
        "ST-0602": "PersistedFactExtractionV2",
        "ST-0603": "PersistedFactConflictDetectionV2",
    }
    for story, raw in bindings.items():
        binding = _mapping(raw)
        _exact_keys(
            binding,
            frozenset(
                {"git_commit", "exact_type", "artifacts"}
                if story != "ST-0403"
                else {
                    "git_commit",
                    "operation_id",
                    "action",
                    "resource_kind",
                    "resource_state",
                    "artifacts",
                }
            ),
        )
        commit = binding.get("git_commit")
        artifacts = _mapping(binding.get("artifacts"))
        if (
            type(commit) is not str
            or _COMMIT.fullmatch(commit) is None
            or not artifacts
            or frozenset(artifacts) != _DEPENDENCY_ARTIFACT_PATHS[story]
        ):
            _fail("DEPENDENCY_BINDING_INVALID")
        expected_type = expected_types[story]
        if expected_type is not None and binding.get("exact_type") != expected_type:
            _fail("DEPENDENCY_TYPE_INVALID")
        if story == "ST-0403" and (
            binding.get("operation_id") != "PUBADM-004"
            or binding.get("action") != "review_article"
            or binding.get("resource_kind") != "REVIEW_ASSIGNMENT"
            or binding.get("resource_state") != "IN_PROGRESS"
        ):
            _fail("AUTHORIZATION_BINDING_INVALID")
        for path_text, digest in artifacts.items():
            if (
                type(path_text) is not str
                or type(digest) is not str
                or _SHA256.fullmatch(digest) is None
            ):
                _fail("DEPENDENCY_BINDING_INVALID")
    return bindings


def _validate_contract(contract: dict[str, object]) -> dict[str, object]:
    integration_commit = contract.get("integration_commit")
    _exact_keys(
        contract,
        frozenset(
            {
                "schema_version",
                "story_id",
                "classification",
                "local_implementation_status",
                "canonical_status",
                "integration_commit",
                "dependency_bindings",
                "lifecycle_boundary",
                "approval_binding",
                "generation_gate",
                "durability_boundary",
                "authority_boundary",
                "formal_evidence",
            }
        ),
    )
    if (
        contract["schema_version"] != "2.0.0"
        or contract["story_id"] != "ST-0604"
        or contract["classification"]
        != "MAXIMUM_SAFE_RECORDED_LOCAL_DURABLE_SOURCE_PACKET_LIFECYCLE"
        or contract["local_implementation_status"] != "LOCAL_CODE_COMPLETE"
        or contract["canonical_status"] != "UNCHANGED"
        or type(integration_commit) is not str
        or not integration_commit
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    _validate_dependency_bindings(contract["dependency_bindings"])
    lifecycle = _mapping(contract["lifecycle_boundary"])
    _exact_keys(
        lifecycle,
        frozenset(
            {
                "commands",
                "statuses",
                "content_immutable_per_version",
                "edit_creates_new_version",
                "prior_current_version_superseded",
                "approved_locked_history_preserved",
                "cas_required",
                "idempotency_key",
            }
        ),
    )
    if (
        lifecycle.get("commands")
        != [
            "CREATE_PACKET",
            "CREATE_VERSION",
            "SUBMIT_REVIEW",
            "RECORD_REVIEW",
            "LOCK_VERSION",
            "READ_GENERATION_INPUT",
        ]
        or lifecycle.get("statuses")
        != ["BUILDING", "IN_REVIEW", "APPROVED", "REJECTED", "SUPERSEDED"]
        or lifecycle.get("idempotency_key") != "command_id+request_sha256"
        or any(
            lifecycle.get(key) is not True
            for key in (
                "content_immutable_per_version",
                "edit_creates_new_version",
                "prior_current_version_superseded",
                "approved_locked_history_preserved",
                "cas_required",
            )
        )
    ):
        _fail("LIFECYCLE_BOUNDARY_INVALID")
    approval = _mapping(contract["approval_binding"])
    _exact_keys(
        approval,
        frozenset(
            {
                "human_recorded_authorization_required",
                "active_session_recovery_required",
                "exact_packet_version_content_sha256",
                "exact_ST0602_fact_membership_sha256",
                "exact_ST0603_no_open_conflict_scan_sha256",
                "exact_ST0403_authorization_audit_digest",
                "reviewer_session_fingerprint_bound",
                "deny_default",
                "synthetic_or_recorded_local_only",
            }
        ),
    )
    if any(value is not True for value in approval.values()):
        _fail("APPROVAL_BOUNDARY_INVALID")
    gate = _mapping(contract["generation_gate"])
    _exact_keys(
        gate,
        frozenset(
            {
                "required_current",
                "required_status",
                "required_lock",
                "required_open_conflict_count",
                "required_conflict_queue_count",
                "unapproved_cannot_generate",
                "noncurrent_cannot_generate",
                "unlocked_cannot_generate",
                "rejected_cannot_generate",
                "dedicated_output_type",
            }
        ),
    )
    if (
        gate.get("required_status") != "APPROVED"
        or gate.get("required_open_conflict_count") != 0
        or gate.get("required_conflict_queue_count") != 0
        or gate.get("dedicated_output_type") != "ApprovedLockedGenerationInputV2"
        or any(
            gate.get(key) is not True
            for key in (
                "required_current",
                "required_lock",
                "unapproved_cannot_generate",
                "noncurrent_cannot_generate",
                "unlocked_cannot_generate",
                "rejected_cannot_generate",
            )
        )
    ):
        _fail("GENERATION_GATE_INVALID")
    authority = _mapping(contract["authority_boundary"])
    _exact_keys(
        authority,
        frozenset(
            {
                "ai",
                "network",
                "provider",
                "publication",
                "ranking",
                "recommendation",
                "revenue",
                "credential_read",
                "staging",
                "release",
                "production",
                "external_action_count",
                "provider_action_count",
                "publication_action_count",
                "ai_action_count",
                "production_authority",
            }
        ),
    )
    if (
        authority.get("production_authority") != "NONE"
        or any(
            value is not False
            for key, value in authority.items()
            if key
            in {
                "ai",
                "network",
                "provider",
                "publication",
                "ranking",
                "recommendation",
                "revenue",
                "credential_read",
                "staging",
                "release",
                "production",
            }
        )
        or any(
            type(authority.get(key)) is not int or authority.get(key) != 0
            for key in (
                "external_action_count",
                "provider_action_count",
                "publication_action_count",
                "ai_action_count",
            )
        )
    ):
        _fail("AUTHORITY_BOUNDARY_INVALID")
    durability = _mapping(contract["durability_boundary"])
    _exact_keys(
        durability,
        frozenset(
            {
                "backend",
                "environments",
                "directory_mode",
                "database_mode",
                "exclusive_create_only",
                "existing_ancestor_symlink_rejected",
                "owner_uid_required",
                "database_single_link_required",
                "file_inode_pinned_per_process",
                "directory_fsync_after_create",
                "strict_tables",
                "exact_sqlite_master_inventory",
                "exact_pragmas_and_user_version",
                "foreign_keys",
                "foreign_key_check_required",
                "append_only_lifecycle_review_lock_command_and_audit_journals",
                "canonical_decode_and_hash_revalidation",
                "exact_commit_recovery_without_blind_retry",
                "process_local_identity_count_head_prefix_anchor",
                "cross_restart_external_rollback_anchor",
            }
        ),
    )
    if (
        durability.get("backend") != "OWNER_PRIVATE_SQLITE"
        or durability.get("environments") != ["ENV-DEV", "ENV-CI"]
        or durability.get("directory_mode") != "0700"
        or durability.get("database_mode") != "0600"
        or durability.get("cross_restart_external_rollback_anchor") is not False
        or any(
            durability.get(key) is not True
            for key in (
                "exclusive_create_only",
                "existing_ancestor_symlink_rejected",
                "owner_uid_required",
                "database_single_link_required",
                "file_inode_pinned_per_process",
                "directory_fsync_after_create",
                "strict_tables",
                "exact_sqlite_master_inventory",
                "exact_pragmas_and_user_version",
                "foreign_keys",
                "foreign_key_check_required",
                "append_only_lifecycle_review_lock_command_and_audit_journals",
                "canonical_decode_and_hash_revalidation",
                "exact_commit_recovery_without_blind_retry",
                "process_local_identity_count_head_prefix_anchor",
            )
        )
    ):
        _fail("DURABILITY_BOUNDARY_INVALID")
    formal = _mapping(contract["formal_evidence"])
    _exact_keys(
        formal,
        frozenset(
            {"TST-012", "TST-020", "hosted_ci", "staging", "release", "production"}
        ),
    )
    if (
        formal.get("TST-012") != "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
        or formal.get("TST-020") != "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
        or any(
            formal.get(key) != "NOT_EXECUTED"
            for key in ("hosted_ci", "staging", "release", "production")
        )
    ):
        _fail("FORMAL_EVIDENCE_INVALID")
    return contract


def _validate_fixture(fixture: dict[str, object]) -> dict[str, object]:
    _exact_keys(
        fixture,
        frozenset(
            {
                "schema_version",
                "story_id",
                "recorded_synthetic",
                "operational_default",
                "activation",
                "contains_credentials",
                "contains_provider_text",
                "contains_raw_source_body",
                "contains_url",
                "input_summary",
                "expected_transition_sequence",
                "expected_generation_boundary",
                "expected_action_counts",
                "metamorphic_cases",
            }
        ),
    )
    if (
        fixture["schema_version"] != "2.0.0"
        or fixture["story_id"] != "ST-0604"
        or fixture["recorded_synthetic"] is not True
        or any(
            fixture[key] is not False
            for key in (
                "operational_default",
                "activation",
                "contains_credentials",
                "contains_provider_text",
                "contains_raw_source_body",
                "contains_url",
            )
        )
    ):
        _fail("FIXTURE_IDENTITY_INVALID")
    summary = _mapping(fixture["input_summary"])
    _exact_keys(
        summary,
        frozenset(
            {
                "fact_batch_count",
                "fact_count",
                "open_conflict_count",
                "conflict_queue_count",
                "authorization_mode",
                "packet_purpose",
            }
        ),
    )
    if (
        summary.get("fact_batch_count") != 1
        or summary.get("fact_count") != 3
        or summary.get("open_conflict_count") != 0
        or summary.get("conflict_queue_count") != 0
        or summary.get("authorization_mode") != "RECORDED_LOCAL_PUBADM_004"
        or summary.get("packet_purpose") != "ARTICLE_DRAFT"
    ):
        _fail("FIXTURE_INPUT_INVALID")
    if fixture["expected_transition_sequence"] != [
        "CREATE_PACKET",
        "CREATE_VERSION",
        "SUBMIT_REVIEW",
        "RECORD_REVIEW:APPROVE",
        "LOCK_VERSION",
        "READ_GENERATION_INPUT",
        "CREATE_VERSION:SUPERSEDE_PRIOR",
    ]:
        _fail("FIXTURE_TRANSITION_INVALID")
    generation = _mapping(fixture["expected_generation_boundary"])
    _exact_keys(
        generation,
        frozenset(
            {
                "before_approval",
                "approved_unlocked",
                "approved_locked_current",
                "superseded_approved_locked",
                "new_building_current",
                "rejected",
                "unresolved_conflict",
            }
        ),
    )
    if generation != {
        "before_approval": "DENIED",
        "approved_unlocked": "DENIED",
        "approved_locked_current": "ALLOWED_TYPED_INPUT",
        "superseded_approved_locked": "DENIED",
        "new_building_current": "DENIED",
        "rejected": "DENIED",
        "unresolved_conflict": "DENIED",
    }:
        _fail("FIXTURE_GENERATION_INVALID")
    actions = _mapping(fixture["expected_action_counts"])
    if frozenset(actions) != frozenset(
        {"external", "provider", "publication", "ai"}
    ) or any(type(value) is not int or value != 0 for value in actions.values()):
        _fail("FIXTURE_ACTION_INVALID")
    if _list(fixture["metamorphic_cases"]) != [
        "CANONICAL_ROUND_TRIP",
        "UNKNOWN_FIELD",
        "FACT_MEMBERSHIP_MISMATCH",
        "CONFLICT_SCAN_MISMATCH",
        "UNRESOLVED_CONFLICT",
        "AUTHORIZATION_OPERATION_MISMATCH",
        "AUTHORIZATION_TARGET_MISMATCH",
        "AUTHORIZATION_RESULT_MISMATCH",
        "EXPIRED_SESSION",
        "COMMAND_REPLAY",
        "COMMAND_CONFLICT",
        "CAS_CONCURRENCY",
        "COMMIT_UNKNOWN_BEFORE",
        "COMMIT_UNKNOWN_AFTER",
        "RESTART",
        "PROCESS_LOCAL_ROLLBACK",
        "OBSERVED_PEER_PREFIX_ROLLBACK",
        "JOURNAL_TAMPER",
        "DENIED_NETWORK",
        "BACKDATED_LIFECYCLE",
        "SAME_COLUMN_SCHEMA_WEAKENING",
        "UNSAFE_SYMLINK_PATH",
        "DATABASE_HARDLINK",
        "OVERDEEP_CANONICAL_JSON",
    ]:
        _fail("FIXTURE_COVERAGE_INVALID")
    return fixture


def _render(
    contract: dict[str, object], fixture: dict[str, object]
) -> dict[str, object]:
    return {
        **contract,
        "external_actions": [],
        "production_authority": "NONE",
        "recorded_synthetic_fixture_report": fixture,
        "runtime_contract": {
            "approved_generation_input_type": "ApprovedLockedGenerationInputV2",
            "database_name": "source-packet-runtime-v2.sqlite3",
            "failure_codes": [
                "INVALID_ARGUMENT",
                "DEPENDENCY_MISMATCH",
                "UNRESOLVED_CONFLICT",
                "AUTHORIZATION_REQUIRED",
                "STATE_CONFLICT",
                "VERSION_CONFLICT",
                "IMMUTABLE_VERSION",
                "NOT_GENERATION_READY",
                "COMMAND_UNKNOWN",
                "COMMAND_CONFLICT",
                "STORAGE_FAILED",
                "STORAGE_COMMIT_UNKNOWN",
                "TAMPER_DETECTED",
            ],
            "replay_statuses": ["COMMITTED", "REPLAYED"],
        },
    }


def _bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    ).encode("ascii")


def _sources() -> tuple[Path, ...]:
    contract = _validate_contract(_json(CONTRACT))
    dependencies = _validate_dependency_bindings(contract["dependency_bindings"])
    dependency_paths: list[Path] = []
    for raw in dependencies.values():
        artifacts = _mapping(_mapping(raw).get("artifacts"))
        dependency_paths.extend(Path(path) for path in artifacts)
    return tuple(
        dict.fromkeys(
            (
                CONTRACT,
                FIXTURE,
                GENERATOR,
                *RUNTIME_SOURCE,
                *TEST_SOURCE,
                *DOCUMENTATION,
                *CANONICAL,
                *dependency_paths,
            )
        )
    )


def _manifest(contract: dict[str, object], output_bytes: bytes) -> dict[str, object]:
    integration_commit = contract["integration_commit"]
    if type(integration_commit) is not str:
        _fail("CONTRACT_IDENTITY_INVALID")
    return {
        "schema_version": "2.0.0",
        "story_id": "ST-0604",
        "generation_command": GENERATION_COMMAND,
        "integration_commit": integration_commit,
        "source_sha256": {
            str(path): _sha(path) for path in sorted(_sources(), key=str)
        },
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output_bytes).hexdigest()},
        "external_actions": [],
        "formal_TST_012": "NOT_EXECUTED",
        "formal_TST_020": "NOT_EXECUTED",
        "hosted_ci": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "production_authority": "NONE",
    }


def _atomic_write(relative: Path, value: bytes) -> None:
    target = REPO_ROOT / relative
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    if stat.S_IMODE(target.stat().st_mode) != 0o644:
        _fail("OUTPUT_MODE_INVALID")


def build(*, check: bool) -> None:
    contract = _validate_contract(_json(CONTRACT))
    fixture = _validate_fixture(_json(FIXTURE))
    output_bytes = _bytes(_render(contract, fixture))
    manifest_bytes = _bytes(_manifest(contract, output_bytes))
    if check:
        try:
            if _read(OUTPUT) != output_bytes or _read(MANIFEST) != manifest_bytes:
                _fail("GENERATED_DRIFT")
        except BuildError:
            raise
        return
    _atomic_write(OUTPUT, output_bytes)
    _atomic_write(MANIFEST, manifest_bytes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        build(check=arguments.check)
    except BuildError as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
