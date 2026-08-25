#!/usr/bin/env python3
"""Owner-generate the deterministic maximum-safe local ST-0603 V2 report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn, cast


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.sqlite_fact_conflict_runtime_v2 import (  # noqa: E402
    FactConflictSqliteCommitFaultV2,
)
from raos.domain.evidence.fact_conflict_runtime_v2 import (  # noqa: E402
    FACT_CONFLICT_CONTENT_POLICY_V2,
    FACT_CONFLICT_DETECTOR_VERSION_V2,
    FACT_CONFLICT_EVENT_CHANNEL_V2,
    FACT_CONFLICT_EVENT_TYPE_V2,
    FactComparisonOutcomeV2,
    FactConflictFailureCodeV2,
    FactConflictQueueStatusV2,
    FactConflictReadinessV2,
    FactConflictReasonV2,
    FactConflictReplayStatusV2,
    FactConflictStatusV2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (  # noqa: E402
    FACT_EXTRACTOR_VERSION_V2,
)


CONTRACT: Final = Path("changes/st-0603/contracts/fact-conflict-runtime.v2.json")
FIXTURE: Final = Path("changes/st-0603/fixtures/fact-conflict.synthetic.v2.json")
OUTPUT: Final = Path("changes/st-0603/generated/fact-conflict-runtime.v2.json")
MANIFEST: Final = Path("changes/st-0603/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0603_fact_conflict_runtime.py")
PREDECESSOR_RUNTIME: Final = (
    Path("python/raos/domain/evidence/fact_extraction_runtime_v2.py"),
    Path("python/raos/ports/fact_extraction_runtime_v2.py"),
    Path("python/raos/application/evidence/fact_extraction_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_fact_extraction_runtime_v2.py"),
    Path("changes/st-0602/contracts/fact-extraction-runtime.v2.json"),
    Path("changes/st-0602/generated/fact-extraction-runtime.v2.json"),
    Path("changes/st-0602/manifest.v2.json"),
)
CANONICAL: Final = (
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/evidence/fact_conflict_runtime_v2.py"),
    Path("python/raos/ports/fact_conflict_runtime_v2.py"),
    Path("python/raos/application/evidence/fact_conflict_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_fact_conflict_runtime_v2.py"),
)
OWNED_TEST_SOURCE: Final = (
    Path("tests/st0603/st0603_runtime_v2_fixtures.py"),
    Path("tests/st0603/test_st0603_fact_conflict_domain_v2.py"),
    Path("tests/st0603/test_st0603_fact_conflict_sqlite_v2.py"),
    Path("tests/st0603/test_st0603_fact_conflict_hostile_v2.py"),
    Path("tests/st0603/test_st0603_fact_conflict_generator_v2.py"),
)
DOCUMENTATION: Final = (
    Path("changes/st-0603/README-v2.md"),
    Path("changes/st-0603/PREFLIGHT-v2.md"),
    Path("changes/st-0603/LOCAL-IMPLEMENTATION-COMPLETION-20260825-v2.json"),
)
GENERATION_COMMAND: Final = "python scripts/build_st0603_fact_conflict_runtime.py"
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_EXCLUDED_INPUTS_AND_CAPABILITIES: Final = (
    "affiliate_rate",
    "authority_inference",
    "commission",
    "credential",
    "EPC",
    "profit",
    "provider_call",
    "publication",
    "ranking",
    "recommendation",
    "revenue",
    "reward",
    "RPM",
    "winner_selection",
)
_METAMORPHIC_CASES: Final = (
    "INPUT_PERMUTATION",
    "EXACT_DUPLICATE",
    "DISTINCT_EQUAL_VALUE",
    "VALUE_CONFLICT",
    "DISJOINT_WINDOW",
    "TOUCHING_WINDOW",
    "INCOMPATIBLE_UNIT_OR_LOCALE",
    "NO_TOLERANCE",
    "IDEMPOTENT_REPLAY",
    "RESTART",
    "CONCURRENCY",
    "TAMPER",
    "MALFORMED_SCHEMA",
    "PREEXISTING_DATABASE",
    "COMMIT_AMBIGUITY",
    "COLLABORATOR_SPOOFING",
    "COLLABORATOR_IN_PLACE_MUTATION",
    "ACTION_COUNT_TYPE_SPOOFING",
    "DENIED_NETWORK",
)


class BuildError(RuntimeError):
    """Stable owner-generator refusal with no source material disclosure."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-0603 V2 build failed: {code}") from None


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
    if any(type(key) is not str for key in raw):
        _fail("JSON_OBJECT_REQUIRED")
    return {cast(str, key): item for key, item in raw.items()}


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail("JSON_LIST_REQUIRED")
    return cast(list[object], value)


def _strings(value: object) -> list[str]:
    values = _list(value)
    if any(type(item) is not str for item in values):
        _fail("JSON_STRING_LIST_REQUIRED")
    return cast(list[str], values)


def _exact_keys(value: dict[str, object], expected: frozenset[str]) -> None:
    if frozenset(value) != expected:
        _fail("JSON_KEYS_INVALID")


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


def _exact_zero(value: object) -> bool:
    return type(value) is int and value == 0


def _exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


def _validate_predecessor(value: object) -> dict[str, object]:
    predecessor = _mapping(value)
    _exact_keys(
        predecessor,
        frozenset(
            {
                "story_id",
                "git_commit",
                "runtime_artifact_sha256",
                "exact_input_type",
                "extractor_version",
                "mapping_round_trip_revalidated",
                "batch_fact_event_chain_and_action_counts_revalidated",
            }
        ),
    )
    artifacts = _mapping(predecessor["runtime_artifact_sha256"])
    if (
        predecessor["story_id"] != "ST-0602"
        or type(predecessor["git_commit"]) is not str
        or _COMMIT.fullmatch(predecessor["git_commit"]) is None
        or predecessor["exact_input_type"] != "PersistedFactExtractionV2"
        or predecessor["extractor_version"] != FACT_EXTRACTOR_VERSION_V2
        or predecessor["mapping_round_trip_revalidated"] is not True
        or predecessor["batch_fact_event_chain_and_action_counts_revalidated"]
        is not True
        or frozenset(artifacts) != frozenset(map(str, PREDECESSOR_RUNTIME))
    ):
        _fail("PREDECESSOR_BINDING_INVALID")
    for relative in PREDECESSOR_RUNTIME:
        digest = artifacts[str(relative)]
        if (
            type(digest) is not str
            or _SHA256.fullmatch(digest) is None
            or digest != _sha(relative)
        ):
            _fail("PREDECESSOR_HASH_DRIFT")
    return predecessor


def _validate_contract(contract: dict[str, object]) -> dict[str, object]:
    _exact_keys(
        contract,
        frozenset(
            {
                "schema_version",
                "story_id",
                "classification",
                "local_implementation_status",
                "canonical_status",
                "predecessor_binding",
                "comparison_boundary",
                "conflict_boundary",
                "event_boundary",
                "durability_boundary",
                "excluded_inputs_and_capabilities",
                "authority_boundary",
                "formal_evidence",
            }
        ),
    )
    if (
        contract["schema_version"] != "2.0.0"
        or contract["story_id"] != "ST-0603"
        or contract["classification"]
        != "MAXIMUM_SAFE_RECORDED_LOCAL_DURABLE_FACT_CONFLICT_RUNTIME"
        or contract["local_implementation_status"] != "LOCAL_CODE_COMPLETE"
        or contract["canonical_status"] != "UNCHANGED"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    predecessor = _validate_predecessor(contract["predecessor_binding"])
    comparison = _mapping(contract["comparison_boundary"])
    _exact_keys(
        comparison,
        frozenset(
            {
                "subject_key",
                "subject_match",
                "validity_window",
                "overlap_required",
                "touching_windows_overlap",
                "typed_value_comparison",
                "unit_and_locale_compatibility",
                "tolerance",
                "conversion_capability",
                "exact_duplicates_create_conflict",
                "disjoint_windows_create_conflict",
                "different_compatible_typed_values_create_conflict",
                "incompatible_unit_or_locale_route",
                "authority_priority",
                "winner_selection",
                "silent_resolution",
            }
        ),
    )
    if (
        _strings(comparison.get("subject_key"))
        != ["subject_type", "subject_id", "predicate"]
        or comparison.get("subject_match") != "EXACT"
        or comparison.get("validity_window") != "HALF_OPEN"
        or comparison.get("overlap_required") is not True
        or comparison.get("touching_windows_overlap") is not False
        or comparison.get("typed_value_comparison") != "EXACT"
        or comparison.get("unit_and_locale_compatibility") != "EXACT"
        or comparison.get("tolerance") is not None
        or comparison.get("conversion_capability") is not False
        or comparison.get("exact_duplicates_create_conflict") is not False
        or comparison.get("disjoint_windows_create_conflict") is not False
        or comparison.get("different_compatible_typed_values_create_conflict")
        is not True
        or comparison.get("incompatible_unit_or_locale_route")
        != "UNRESOLVED_HUMAN_REVIEW_NO_CONVERSION"
        or comparison.get("authority_priority") is not False
        or comparison.get("winner_selection") is not False
        or comparison.get("silent_resolution") is not False
    ):
        _fail("COMPARISON_BOUNDARY_INVALID")
    conflict = _mapping(contract["conflict_boundary"])
    _exact_keys(
        conflict,
        frozenset(
            {
                "status",
                "queue_status",
                "readiness",
                "content_policy",
                "silent_resolution_forbidden",
                "winner_fact_id",
                "tolerance",
                "resolution",
                "authority_priority_used",
                "deterministic_scan_conflict_queue_and_event_ids",
                "scan_bound_conflict_identity",
                "arbitrary_html_or_url",
                "unknown_or_claim_creation",
            }
        ),
    )
    if (
        conflict.get("status") != FactConflictStatusV2.UNRESOLVED.value
        or conflict.get("queue_status") != FactConflictQueueStatusV2.HUMAN_REVIEW.value
        or conflict.get("readiness") != FactConflictReadinessV2.NOT_READY.value
        or conflict.get("content_policy") != FACT_CONFLICT_CONTENT_POLICY_V2
        or conflict.get("silent_resolution_forbidden") is not True
        or conflict.get("winner_fact_id") is not None
        or conflict.get("tolerance") is not None
        or conflict.get("resolution") is not None
        or conflict.get("authority_priority_used") is not False
        or conflict.get("deterministic_scan_conflict_queue_and_event_ids") is not True
        or conflict.get("scan_bound_conflict_identity") is not True
        or conflict.get("arbitrary_html_or_url") is not False
        or conflict.get("unknown_or_claim_creation") is not False
    ):
        _fail("CONFLICT_BOUNDARY_INVALID")
    event = _mapping(contract["event_boundary"])
    _exact_keys(
        event,
        frozenset(
            {
                "event_type",
                "channel",
                "delivery_status",
                "atomic_with_scan_conflicts_queue_and_journal",
                "delivery_worker",
            }
        ),
    )
    if (
        event.get("event_type") != FACT_CONFLICT_EVENT_TYPE_V2
        or event.get("channel") != FACT_CONFLICT_EVENT_CHANNEL_V2
        or event.get("delivery_status") != "RECORDED_LOCAL_NOT_DELIVERED"
        or event.get("atomic_with_scan_conflicts_queue_and_journal") is not True
        or event.get("delivery_worker") is not False
    ):
        _fail("EVENT_BOUNDARY_INVALID")
    durability = _mapping(contract["durability_boundary"])
    _exact_keys(
        durability,
        frozenset(
            {
                "backend",
                "environments",
                "strict_directory_mode",
                "strict_database_mode",
                "exclusive_create_only_initialization",
                "preexisting_empty_partial_or_foreign_rejected",
                "exact_schema_trigger_and_autoindex_inventory",
                "strict_tables",
                "foreign_keys",
                "append_only_triggers",
                "dirfd_and_no_follow",
                "symlink_rejected",
                "hardlink_rejected",
                "device_and_inode_pinned",
                "canonical_json_uuid_rfc3339_and_typed_value_revalidation",
                "payload_hash_and_chain_recomputation",
                "atomic_conflict_queue_outbox_journal_and_cas",
                "idempotency_key",
                "restart_recovery",
                "commit_ambiguity_recovery",
                "process_lifetime_count_head_and_prefix_monotonicity",
                "cross_restart_rollback_anchor",
                "delete_update_export_retention_capability",
            }
        ),
    )
    true_durability = (
        "exclusive_create_only_initialization",
        "preexisting_empty_partial_or_foreign_rejected",
        "exact_schema_trigger_and_autoindex_inventory",
        "strict_tables",
        "foreign_keys",
        "append_only_triggers",
        "dirfd_and_no_follow",
        "symlink_rejected",
        "hardlink_rejected",
        "device_and_inode_pinned",
        "canonical_json_uuid_rfc3339_and_typed_value_revalidation",
        "payload_hash_and_chain_recomputation",
        "atomic_conflict_queue_outbox_journal_and_cas",
        "restart_recovery",
        "commit_ambiguity_recovery",
        "process_lifetime_count_head_and_prefix_monotonicity",
    )
    if (
        durability.get("backend") != "OWNER_PRIVATE_SQLITE"
        or _strings(durability.get("environments")) != ["ENV-DEV", "ENV-CI"]
        or durability.get("strict_directory_mode") != "0700"
        or durability.get("strict_database_mode") != "0600"
        or any(durability.get(key) is not True for key in true_durability)
        or durability.get("idempotency_key") != "input_set_sha256+detector_version"
        or durability.get("cross_restart_rollback_anchor") is not False
        or durability.get("delete_update_export_retention_capability") is not False
    ):
        _fail("DURABILITY_BOUNDARY_INVALID")
    excluded = _strings(contract["excluded_inputs_and_capabilities"])
    if excluded != list(_EXCLUDED_INPUTS_AND_CAPABILITIES):
        _fail("EXCLUDED_CAPABILITY_INVALID")
    authority = _mapping(contract["authority_boundary"])
    _exact_keys(
        authority,
        frozenset(
            {
                "human_review_decision",
                "publication",
                "recommendation",
                "ranking",
                "revenue",
                "live_provider",
                "credential_read",
                "network",
                "ai",
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
    if any(
        authority.get(key) is not False
        for key in (
            "human_review_decision",
            "publication",
            "recommendation",
            "ranking",
            "revenue",
            "live_provider",
            "credential_read",
            "network",
            "ai",
            "staging",
            "release",
            "production",
        )
    ) or any(
        not _exact_zero(authority.get(key))
        for key in (
            "external_action_count",
            "provider_action_count",
            "publication_action_count",
            "ai_action_count",
        )
    ):
        _fail("AUTHORITY_BOUNDARY_INVALID")
    if authority.get("production_authority") != "NONE":
        _fail("AUTHORITY_BOUNDARY_INVALID")
    formal = _mapping(contract["formal_evidence"])
    _exact_keys(
        formal,
        frozenset(
            {
                "TST-007",
                "TST-020",
                "live_provider",
                "hosted_ci",
                "staging",
                "release",
                "production",
            }
        ),
    )
    if any(
        formal.get(key) != "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
        for key in ("TST-007", "TST-020")
    ) or any(
        formal.get(key) != "NOT_EXECUTED"
        for key in (
            "live_provider",
            "hosted_ci",
            "staging",
            "release",
            "production",
        )
    ):
        _fail("FORMAL_BOUNDARY_INVALID")
    return predecessor


def _validate_fixture(fixture: dict[str, object]) -> None:
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
                "contains_raw_or_affiliate_url",
                "inputs",
                "expected_report",
                "negative_cases",
                "commit_faults",
                "metamorphic_cases",
            }
        ),
    )
    inputs = _mapping(fixture.get("inputs"))
    expected = _mapping(fixture.get("expected_report"))
    negative = _mapping(fixture.get("negative_cases"))
    _exact_keys(
        inputs,
        frozenset(
            {
                "story_id",
                "persisted_batch_count",
                "offer_count_per_batch",
                "facts_per_offer",
                "same_subject_ids",
                "same_predicates",
                "overlapping_validity",
                "different_price_value",
                "equal_boolean_values",
            }
        ),
    )
    _exact_keys(
        expected,
        frozenset(
            {
                "comparison_count",
                "equal_value_count",
                "disjoint_window_count",
                "incompatible_unit_or_locale_count",
                "conflict_count",
                "queue_count",
                "conflict_reason",
                "status",
                "queue_status",
                "readiness",
                "content_policy",
                "silent_resolution_forbidden",
                "winner_fact_id",
                "tolerance",
                "resolution",
                "publication_authority",
                "external_action_count",
                "provider_action_count",
                "publication_action_count",
                "ai_action_count",
            }
        ),
    )
    _exact_keys(
        negative,
        frozenset(
            {
                "exact_duplicate",
                "distinct_equal_value",
                "disjoint_window",
                "touching_half_open_window",
                "incompatible_unit_or_locale",
                "value_kind_mismatch",
                "dependency_hash_or_chain_mismatch",
            }
        ),
    )
    if (
        fixture.get("schema_version") != "2.0.0"
        or fixture.get("story_id") != "ST-0603"
        or fixture.get("recorded_synthetic") is not True
        or fixture.get("operational_default") is not False
        or fixture.get("activation") is not False
        or fixture.get("contains_credentials") is not False
        or fixture.get("contains_provider_text") is not False
        or fixture.get("contains_raw_or_affiliate_url") is not False
        or inputs.get("story_id") != "ST-0602"
        or not _exact_int(inputs.get("persisted_batch_count"), 2)
        or not _exact_int(inputs.get("offer_count_per_batch"), 1)
        or not _exact_int(inputs.get("facts_per_offer"), 3)
        or any(
            inputs.get(key) is not True
            for key in (
                "same_subject_ids",
                "same_predicates",
                "overlapping_validity",
                "different_price_value",
                "equal_boolean_values",
            )
        )
        or not _exact_int(expected.get("comparison_count"), 3)
        or not _exact_int(expected.get("equal_value_count"), 2)
        or not _exact_int(expected.get("disjoint_window_count"), 0)
        or not _exact_int(expected.get("incompatible_unit_or_locale_count"), 0)
        or not _exact_int(expected.get("conflict_count"), 1)
        or not _exact_int(expected.get("queue_count"), 1)
        or expected.get("conflict_reason") != FactConflictReasonV2.VALUE_MISMATCH.value
        or expected.get("status") != FactConflictStatusV2.UNRESOLVED.value
        or expected.get("queue_status") != FactConflictQueueStatusV2.HUMAN_REVIEW.value
        or expected.get("readiness") != FactConflictReadinessV2.NOT_READY.value
        or expected.get("content_policy") != FACT_CONFLICT_CONTENT_POLICY_V2
        or expected.get("silent_resolution_forbidden") is not True
        or expected.get("winner_fact_id") is not None
        or expected.get("tolerance") is not None
        or expected.get("resolution") is not None
        or expected.get("publication_authority") != "NONE"
        or any(
            not _exact_zero(expected.get(key))
            for key in (
                "external_action_count",
                "provider_action_count",
                "publication_action_count",
                "ai_action_count",
            )
        )
        or negative.get("exact_duplicate") != "NO_CONFLICT"
        or negative.get("distinct_equal_value") != "NO_CONFLICT"
        or negative.get("disjoint_window") != "NO_CONFLICT"
        or negative.get("touching_half_open_window") != "NO_CONFLICT"
        or negative.get("incompatible_unit_or_locale")
        != "UNRESOLVED_HUMAN_REVIEW_NO_CONVERSION"
        or negative.get("value_kind_mismatch") != "FAIL_CLOSED"
        or negative.get("dependency_hash_or_chain_mismatch") != "FAIL_CLOSED"
        or _strings(fixture.get("commit_faults"))
        != [value.value for value in FactConflictSqliteCommitFaultV2]
        or _strings(fixture.get("metamorphic_cases")) != list(_METAMORPHIC_CASES)
    ):
        _fail("FIXTURE_BOUNDARY_INVALID")


def _bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _render() -> tuple[bytes, bytes]:
    contract = _json_object(CONTRACT)
    fixture = _json_object(FIXTURE)
    predecessor = _validate_contract(contract)
    _validate_fixture(fixture)
    report: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0603",
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "predecessor_binding": predecessor,
        "detector_contract": {
            "detector_version": FACT_CONFLICT_DETECTOR_VERSION_V2,
            "comparison_outcomes": [value.value for value in FactComparisonOutcomeV2],
            "conflict_reasons": [value.value for value in FactConflictReasonV2],
            "failure_codes": [value.value for value in FactConflictFailureCodeV2],
            "replay_statuses": [value.value for value in FactConflictReplayStatusV2],
        },
        "comparison_boundary": contract["comparison_boundary"],
        "conflict_boundary": contract["conflict_boundary"],
        "event_boundary": contract["event_boundary"],
        "durability_boundary": contract["durability_boundary"],
        "excluded_inputs_and_capabilities": contract[
            "excluded_inputs_and_capabilities"
        ],
        "recorded_synthetic_fixture_report": fixture,
        "authority_boundary": contract["authority_boundary"],
        "formal_evidence": contract["formal_evidence"],
        "external_actions": [],
        "production_authority": "NONE",
    }
    output_bytes = _bytes(report)
    sources = (
        *CANONICAL,
        *PREDECESSOR_RUNTIME,
        *RUNTIME_SOURCE,
        *OWNED_TEST_SOURCE,
        *DOCUMENTATION,
        CONTRACT,
        FIXTURE,
        GENERATOR,
    )
    manifest: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0603",
        "generation_command": GENERATION_COMMAND,
        "predecessor_commit": predecessor["git_commit"],
        "source_sha256": {str(path): _sha(path) for path in sources},
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output_bytes).hexdigest()},
        "formal_TST_007": "NOT_EXECUTED",
        "formal_TST_020": "NOT_EXECUTED",
        "live_provider": "NOT_EXECUTED",
        "hosted_ci": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "external_actions": [],
        "production_authority": "NONE",
    }
    return output_bytes, _bytes(manifest)


def _write(relative: Path, content: bytes) -> None:
    target = REPO_ROOT / relative
    if relative.is_absolute() or ".." in relative.parts:
        _fail("OUTPUT_PATH_INVALID")
    current = REPO_ROOT
    try:
        root = REPO_ROOT.resolve(strict=True)
        for component in relative.parent.parts:
            current /= component
            metadata = current.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                _fail("OUTPUT_PATH_INVALID")
        if current.resolve(strict=True) != root / relative.parent:
            _fail("OUTPUT_PATH_INVALID")
        if target.exists() or target.is_symlink():
            metadata = target.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                _fail("OUTPUT_PATH_INVALID")
    except OSError:
        _fail("OUTPUT_PATH_INVALID")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        target.chmod(0o644)
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o644
        ):
            _fail("OUTPUT_WRITE_FAILED")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    output, manifest = _render()
    if args.check:
        _check(OUTPUT, output)
        _check(MANIFEST, manifest)
    else:
        _write(OUTPUT, output)
        _write(MANIFEST, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
