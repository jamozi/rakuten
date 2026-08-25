#!/usr/bin/env python3
"""Owner-generate the deterministic maximum-safe local ST-0602 V2 report."""

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

from raos.adapters.sqlite_fact_extraction_runtime_v2 import (  # noqa: E402
    FactExtractionSqliteCommitFaultV2,
)
from raos.domain.catalog.catalog_normalization_runtime_v2 import (  # noqa: E402
    CATALOG_IDENTITY_OPEN_DECISION_V2,
    CatalogIdentityStatusV2,
    CatalogObservationKindV2,
    CatalogReadinessV2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (  # noqa: E402
    FACT_EXTRACTION_CONFIDENCE_V2,
    FACT_EXTRACTION_EVENT_CHANNEL_V2,
    FACT_EXTRACTION_EVENT_TYPE_V2,
    FACT_EXTRACTION_JOB_QUEUE_V2,
    FACT_EXTRACTION_JOB_TYPE_V2,
    FACT_EXTRACTOR_VERSION_V2,
    FactConfidenceBasisV2,
    FactKindV2,
    FactPublicationReadinessV2,
    FactSubjectTypeV2,
    FactTruthAttestationV2,
    FactValueKindV2,
)


CONTRACT: Final = Path("changes/st-0602/contracts/fact-extraction-runtime.v2.json")
FIXTURE: Final = Path("changes/st-0602/fixtures/fact-extraction.synthetic.v2.json")
OUTPUT: Final = Path("changes/st-0602/generated/fact-extraction-runtime.v2.json")
MANIFEST: Final = Path("changes/st-0602/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0602_fact_extraction_runtime.py")
CANONICAL: Final = (
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
    Path(
        "contracts/raos-v0.4/contracts/schemas/jobs/"
        "evidence-extract-facts-v1.schema.json"
    ),
    Path(
        "contracts/raos-v0.4/contracts/schemas/events/"
        "jp-raos-evidence-facts-extracted-v1.schema.json"
    ),
    Path("contracts/raos-v0.4/contracts/schemas/common/job-message.schema.json"),
    Path("contracts/raos-v0.4/contracts/schemas/common/event-envelope.schema.json"),
    Path("contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"),
)
DEPENDENCY_SOURCE: Final = (
    Path("python/raos/domain/ops/artifact_registry_runtime_v2.py"),
    Path("python/raos/ports/artifact_registry_runtime_v2.py"),
    Path("python/raos/application/ops/artifact_registry_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_artifact_registry_runtime_v2.py"),
    Path("python/raos/domain/catalog/catalog_normalization_runtime_v2.py"),
    Path("python/raos/ports/catalog_normalization_runtime_v2.py"),
    Path("python/raos/application/catalog/catalog_normalization_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_catalog_normalization_runtime_v2.py"),
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/evidence/fact_extraction_runtime_v2.py"),
    Path("python/raos/ports/fact_extraction_runtime_v2.py"),
    Path("python/raos/application/evidence/fact_extraction_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_fact_extraction_runtime_v2.py"),
)
OWNED_TEST_SOURCE: Final = (
    Path("tests/st0602/runtime_v2_fixtures.py"),
    Path("tests/st0602/test_fact_extraction_runtime_v2.py"),
    Path("tests/st0602/test_fact_extraction_runtime_v2_boundaries.py"),
    Path("tests/st0602/test_fact_extraction_runtime_v2_hostile.py"),
    Path("tests/st0602/test_fact_extraction_runtime_v2_storage.py"),
    Path("tests/st0602/test_fact_extraction_runtime_v2_generator.py"),
)
DOCUMENTATION: Final = (
    Path("changes/st-0602/README.md"),
    Path("changes/st-0602/PREFLIGHT-v2.md"),
    Path("changes/st-0602/LOCAL-IMPLEMENTATION-COMPLETION-20260825-v2.json"),
)
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024
GENERATION_COMMAND: Final = "python scripts/build_st0602_fact_extraction_runtime.py"


class BuildError(RuntimeError):
    """Stable owner-generator refusal with no source material disclosure."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-0602 V2 build failed: {code}") from None


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


def _validate_contract(contract: dict[str, object]) -> None:
    source = _mapping(contract.get("source_boundary"))
    fact = _mapping(contract.get("fact_boundary"))
    confidence = _mapping(contract.get("confidence_boundary"))
    job = _mapping(contract.get("job_boundary"))
    event = _mapping(contract.get("event_boundary"))
    durability = _mapping(contract.get("durability_boundary"))
    authority = _mapping(contract.get("authority_boundary"))
    formal = _mapping(contract.get("formal_evidence"))
    if (
        contract.get("schema_version") != "2.0.0"
        or contract.get("story_id") != "ST-0602"
        or contract.get("local_implementation_status") != "LOCAL_CODE_COMPLETE"
        or contract.get("canonical_status") != "UNCHANGED"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if (
        any(
            source.get(key) is not True
            for key in (
                "artifact_readback_exact_type_required",
                "artifact_record_receipt_request_page_version_logical_key_time_and_raw_hash_revalidated",
                "normalization_exact_type_required",
                "snapshot_batch_event_version_chain_and_time_revalidated",
                "recorded_local_only",
            )
        )
        or any(
            source.get(key) is not False
            for key in (
                "provider_or_network_capability",
                "browser_or_tool_capability",
                "ai_or_model_capability",
                "manual_review_decision_capability",
            )
        )
        or not _exact_zero(source.get("external_actions"))
    ):
        _fail("SOURCE_BOUNDARY_INVALID")
    expected_observations = [
        CatalogObservationKindV2.PRICE_JPY.value,
        CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG.value,
        CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG.value,
    ]
    if (
        fact.get("subject_type") != FactSubjectTypeV2.OFFER.value
        or fact.get("fact_kind") != FactKindV2.ASSERTED.value
        or _strings(fact.get("accepted_observations")) != expected_observations
        or fact.get("affiliate_url_fact") is not False
        or fact.get("product_fact") is not False
        or fact.get("canonical_product_id") is not False
        or fact.get("identity_open_decision") != CATALOG_IDENTITY_OPEN_DECISION_V2
        or fact.get("identity_status") != CatalogIdentityStatusV2.HUMAN_REVIEW.value
        or fact.get("readiness") != CatalogReadinessV2.NOT_READY.value
        or fact.get("one_typed_value") is not True
        or fact.get("numeric_price_unit") != "JPY"
        or fact.get("numeric_price_locale") != "ja-JP"
        or fact.get("boolean_unit") is not None
        or fact.get("boolean_locale") is not None
    ):
        _fail("FACT_BOUNDARY_INVALID")
    if (
        confidence.get("value") != format(FACT_EXTRACTION_CONFIDENCE_V2, ".4f")
        or confidence.get("basis")
        != FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION.value
        or confidence.get("meaning") != "EXTRACTION_FIDELITY_ONLY"
        or confidence.get("copies_provider_truth_confidence") is not False
        or confidence.get("truth_attestation")
        != FactTruthAttestationV2.NOT_ATTESTED.value
        or confidence.get("publication_readiness")
        != FactPublicationReadinessV2.NOT_READY.value
        or confidence.get("manual_review_required") is not True
    ):
        _fail("CONFIDENCE_BOUNDARY_INVALID")
    excluded = _strings(contract.get("excluded_inputs"))
    if len(excluded) != len(set(excluded)) or not {
        "affiliate_url",
        "canonical_product_id",
        "commission",
        "EPC",
        "profit",
        "ranking",
        "recommendation",
        "review_aggregate",
        "review_body",
        "reward",
        "RPM",
    }.issubset(excluded):
        _fail("EXCLUDED_INPUTS_INVALID")
    if (
        job.get("job_type") != FACT_EXTRACTION_JOB_TYPE_V2
        or job.get("queue") != FACT_EXTRACTION_JOB_QUEUE_V2
        or job.get("idempotency_key") != "source_snapshot_id+extractor_version"
        or job.get("subject_hints") != []
        or job.get("enqueue_capability") is not False
    ):
        _fail("JOB_BOUNDARY_INVALID")
    if (
        event.get("event_type") != FACT_EXTRACTION_EVENT_TYPE_V2
        or event.get("channel") != FACT_EXTRACTION_EVENT_CHANNEL_V2
        or event.get("delivery_status") != "RECORDED_LOCAL_NOT_DELIVERED"
        or event.get("atomic_with_fact_batch_and_validation_records") is not True
        or event.get("delivery_worker") is not False
    ):
        _fail("EVENT_BOUNDARY_INVALID")
    if (
        durability.get("backend") != "OWNER_PRIVATE_SQLITE"
        or durability.get("strict_directory_mode") != "0700"
        or durability.get("strict_database_mode") != "0600"
        or any(
            durability.get(key) is not True
            for key in (
                "exclusive_create_distinguishes_new_from_preexisting_empty_or_partial",
                "exact_schema_and_inventory",
                "strict_tables",
                "foreign_keys",
                "symlink_rejected",
                "hardlink_rejected",
                "live_inode_pinned",
                "atomic_batch_validation_outbox_journal_and_cas",
                "payload_hash_conflict_detection",
                "restart_recovery",
                "commit_ambiguity_recovery",
                "hash_chain",
                "process_lifetime_monotonic_head_and_count",
            )
        )
        or durability.get("cross_restart_rollback_anchor") is not False
        or durability.get("delete_update_export_retention_capability") is not False
    ):
        _fail("DURABILITY_BOUNDARY_INVALID")
    if any(
        authority.get(key) is not False
        for key in (
            "publication",
            "recommendation",
            "ranking",
            "revenue",
            "live_provider",
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
    if any(
        formal.get(key) != "NOT_EXECUTED"
        for key in (
            "TST-008_postgresql",
            "live_provider",
            "hosted_ci",
            "staging",
            "release",
            "production",
        )
    ) or any(
        formal.get(key) != "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
        for key in ("TST-005", "TST-007")
    ):
        _fail("FORMAL_BOUNDARY_INVALID")


def _validate_fixture(fixture: dict[str, object]) -> None:
    source = _mapping(fixture.get("source"))
    expected = _mapping(fixture.get("expected_report"))
    if (
        fixture.get("schema_version") != "2.0.0"
        or fixture.get("story_id") != "ST-0602"
        or fixture.get("recorded_synthetic") is not True
        or fixture.get("operational_default") is not False
        or fixture.get("activation") is not False
        or fixture.get("contains_credentials") is not False
        or fixture.get("contains_provider_text") is not False
        or fixture.get("contains_raw_or_affiliate_url") is not False
        or source.get("artifact_story") != "ST-0601"
        or source.get("normalization_story") != "ST-0503"
        or source.get("offer_count") != 2
        or source.get("structural_observations_per_offer") != 3
        or source.get("ignored_observations_per_offer") != 1
        or source.get("source_confidence") is not None
        or source.get("source_confidence_status") != "SOURCE_ABSENT"
        or expected.get("fact_count") != 6
        or expected.get("validation_count") != 6
        or expected.get("event_count") != 1
        or _strings(expected.get("fact_predicates"))
        != [
            CatalogObservationKindV2.PRICE_JPY.value,
            CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG.value,
            CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG.value,
        ]
        or expected.get("subject_type") != FactSubjectTypeV2.OFFER.value
        or expected.get("fact_kind") != FactKindV2.ASSERTED.value
        or expected.get("confidence") != format(FACT_EXTRACTION_CONFIDENCE_V2, ".4f")
        or expected.get("confidence_basis")
        != FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION.value
        or expected.get("truth_attestation")
        != FactTruthAttestationV2.NOT_ATTESTED.value
        or expected.get("identity_status") != CatalogIdentityStatusV2.HUMAN_REVIEW.value
        or expected.get("readiness") != CatalogReadinessV2.NOT_READY.value
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
        or _strings(fixture.get("commit_faults"))
        != [value.value for value in FactExtractionSqliteCommitFaultV2]
        or len(_strings(fixture.get("metamorphic_cases"))) != 16
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
    _validate_contract(contract)
    _validate_fixture(fixture)
    report: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0602",
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "dependency_contract": contract["dependencies"],
        "extractor_contract": {
            "extractor_version": FACT_EXTRACTOR_VERSION_V2,
            "subject_types": [value.value for value in FactSubjectTypeV2],
            "fact_kinds": [value.value for value in FactKindV2],
            "value_kinds": [value.value for value in FactValueKindV2],
            "accepted_observations": _mapping(contract["fact_boundary"])[
                "accepted_observations"
            ],
            "confidence": format(FACT_EXTRACTION_CONFIDENCE_V2, ".4f"),
            "confidence_basis": FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION.value,
            "truth_attestation": FactTruthAttestationV2.NOT_ATTESTED.value,
            "publication_readiness": FactPublicationReadinessV2.NOT_READY.value,
        },
        "event_contract": {
            "event_type": FACT_EXTRACTION_EVENT_TYPE_V2,
            "channel": FACT_EXTRACTION_EVENT_CHANNEL_V2,
            "delivery_status": "RECORDED_LOCAL_NOT_DELIVERED",
            "delivery_worker": "NOT_IMPLEMENTED_NOT_ACTIVATED",
        },
        "job_contract": contract["job_boundary"],
        "source_boundary": contract["source_boundary"],
        "fact_boundary": contract["fact_boundary"],
        "confidence_boundary": contract["confidence_boundary"],
        "excluded_inputs": contract["excluded_inputs"],
        "durability_boundary": contract["durability_boundary"],
        "recorded_synthetic_fixture_report": fixture,
        "formal_evidence": contract["formal_evidence"],
        "authority_boundary": contract["authority_boundary"],
        "external_actions": [],
        "production_authority": "NONE",
    }
    output_bytes = _bytes(report)
    sources = (
        *CANONICAL,
        *DEPENDENCY_SOURCE,
        *RUNTIME_SOURCE,
        *OWNED_TEST_SOURCE,
        *DOCUMENTATION,
        CONTRACT,
        FIXTURE,
        GENERATOR,
    )
    manifest: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0602",
        "generation_command": GENERATION_COMMAND,
        "source_sha256": {str(path): _sha(path) for path in sources},
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output_bytes).hexdigest()},
        "formal_TST_005": "NOT_EXECUTED",
        "formal_TST_007": "NOT_EXECUTED",
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
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
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
