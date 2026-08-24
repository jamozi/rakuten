#!/usr/bin/env python3
"""Owner-generate the deterministic maximum-safe local ST-0503 projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Final, NoReturn, cast


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.sqlite_catalog_normalization_runtime_v2 import (  # noqa: E402
    CatalogNormalizationSqliteCommitFaultV2,
)
from raos.domain.catalog.catalog_normalization_runtime_v2 import (  # noqa: E402
    CATALOG_EVENT_CHANNEL_V2,
    CATALOG_EVENT_TYPE_V2,
    CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2,
    CATALOG_IDENTITY_OPEN_DECISION_V2,
    CATALOG_NORMALIZER_VERSION_V2,
    CatalogConfidenceStatusV2,
    CatalogIdentityStatusV2,
    CatalogObservationKindV2,
    CatalogReadinessV2,
    CatalogSourceModeV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (  # noqa: E402
    ITEM_SEARCH_API_VERSION,
)


CONTRACT: Final = Path(
    "changes/st-0503/contracts/catalog-normalization-runtime.v2.json"
)
FIXTURE: Final = Path(
    "changes/st-0503/fixtures/catalog-normalization.synthetic.v2.json"
)
OUTPUT: Final = Path("changes/st-0503/generated/catalog-normalization-runtime.v2.json")
MANIFEST: Final = Path("changes/st-0503/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0503_catalog_normalization_runtime.py")
CANONICAL: Final = (
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
)
DEPENDENCY_SOURCE: Final = (
    Path("changes/st-0502/contracts/item-search-runtime.v2.json"),
    Path("changes/st-0502/generated/item-search-runtime.v2.json"),
    Path("python/raos/domain/catalog/rakuten_item_search_runtime_v2.py"),
    Path("python/raos/ports/rakuten_item_search_runtime_v2.py"),
    Path("python/raos/application/catalog/rakuten_item_search_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_rakuten_item_search_runtime_v2.py"),
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/catalog/catalog_normalization_runtime_v2.py"),
    Path("python/raos/ports/catalog_normalization_runtime_v2.py"),
    Path("python/raos/application/catalog/catalog_normalization_runtime_v2.py"),
    Path("python/raos/adapters/recorded_catalog_normalization_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_catalog_normalization_runtime_v2.py"),
)
OWNED_TEST_SOURCE: Final = (
    Path("tests/st0503/runtime_v2_fixtures.py"),
    Path("tests/st0503/test_catalog_normalization_runtime_v2.py"),
    Path("tests/st0503/test_catalog_normalization_runtime_v2_storage.py"),
    Path("tests/st0503/test_catalog_normalization_runtime_v2_hostile.py"),
    Path("tests/st0503/test_catalog_normalization_runtime_v2_generator.py"),
)
DOCUMENTATION: Final = (
    Path("changes/st-0503/README.md"),
    Path("changes/st-0503/PREFLIGHT-v2.md"),
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
GENERATION_COMMAND: Final = (
    "python scripts/build_st0503_catalog_normalization_runtime.py"
)


class BuildError(RuntimeError):
    """Stable owner-generator refusal without rejected source material."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-0503 build failed: {code}") from None


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
    items = cast(list[object], value)
    if any(type(item) is not str for item in items):
        _fail("STRING_LIST_REQUIRED")
    return cast(list[str], items)


def _validate_contract(contract: dict[str, object]) -> None:
    source = _mapping(contract.get("source_boundary"))
    normalization = _mapping(contract.get("normalization_boundary"))
    identity = _mapping(contract.get("identity_boundary"))
    recommendation = _mapping(contract.get("recommendation_boundary"))
    durability = _mapping(contract.get("durability_boundary"))
    formal = _mapping(contract.get("formal_evidence"))
    if (
        contract.get("schema_version") != "2.0.0"
        or contract.get("story_id") != "ST-0503"
        or contract.get("local_implementation_status") != "LOCAL_CODE_COMPLETE"
        or contract.get("canonical_status") != "UNCHANGED"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if (
        source.get("accepted_mode") != CatalogSourceModeV2.RECORDED_PERSISTED.value
        or source.get("default_mode") != CatalogSourceModeV2.DISABLED.value
        or source.get("external_actions") != 0
        or any(
            source.get(key) is not False
            for key in (
                "http_or_network_capability",
                "credential_capability",
                "provider_call_capability",
                "worker_activation",
            )
        )
        or any(
            source.get(key) is not True
            for key in (
                "persisted_success_page_required",
                "receipt_request_raw_page_reparse_required",
                "source_snapshot_required",
                "full_provenance_required",
                "collaborator_exceptions_sanitized",
                "collaborator_returns_revalidated",
            )
        )
    ):
        _fail("SOURCE_BOUNDARY_INVALID")
    if (
        normalization.get("normalizer_version") != CATALOG_NORMALIZER_VERSION_V2
        or normalization.get("source_confidence") is not None
        or normalization.get("source_confidence_status")
        != CatalogConfidenceStatusV2.SOURCE_ABSENT.value
        or normalization.get("observation_is_recommendation") is not False
        or normalization.get("ranking_surface") is not False
    ):
        _fail("NORMALIZATION_BOUNDARY_INVALID")
    if (
        identity.get("open_decision") != CATALOG_IDENTITY_OPEN_DECISION_V2
        or identity.get("identity_status") != CatalogIdentityStatusV2.HUMAN_REVIEW.value
        or identity.get("readiness") != CatalogReadinessV2.NOT_READY.value
        or any(
            identity.get(key) is not False
            for key in (
                "automatic_merge",
                "automatic_split",
                "canonical_product_identity",
                "provider_confidence_shortcut",
                "model_or_jan_extraction",
            )
        )
    ):
        _fail("IDENTITY_BOUNDARY_INVALID")
    if _string_list(
        recommendation.get("provider_derived_recommendation_inputs")
    ) != [] or _string_list(recommendation.get("excluded_inputs")) != list(
        CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2
    ):
        _fail("RECOMMENDATION_BOUNDARY_INVALID")
    if (
        durability.get("backend") != "OWNER_PRIVATE_SQLITE"
        or durability.get("strict_directory_mode") != "0700"
        or durability.get("strict_database_mode") != "0600"
        or any(
            durability.get(key) is not True
            for key in (
                "atomic_snapshot_batch_records_outbox_journal_and_cas",
                "exact_schema_sql_bound",
                "exact_autoindex_and_column_inventory_bound",
                "symlink_rejected",
                "hardlink_rejected",
                "path_traversal_rejected",
                "restart_and_commit_ambiguity_recovery",
                "command_idempotency",
                "source_receipt_idempotency",
                "catalog_compare_and_swap",
                "hash_chain",
                "outbox",
                "tamper_and_schema_drift_fail_closed",
            )
        )
    ):
        _fail("DURABILITY_BOUNDARY_INVALID")
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
    expected = _mapping(fixture.get("expected"))
    if (
        fixture.get("schema_version") != "2.0.0"
        or fixture.get("story_id") != "ST-0503"
        or fixture.get("synthetic") is not True
        or fixture.get("operational_default") is not False
        or fixture.get("activation") is not False
        or fixture.get("contains_credential_or_sample_value") is not False
        or fixture.get("external_actions") != 0
        or source.get("story_id") != "ST-0502"
        or source.get("runtime_version") != "V2"
        or source.get("mode") != CatalogSourceModeV2.RECORDED_PERSISTED.value
        or source.get("receipt_and_raw_hash_required") is not True
        or expected.get("candidate_count") != 2
        or expected.get("offer_count") != 2
        or expected.get("observation_count") != 8
        or _string_list(expected.get("observation_kinds_per_offer"))
        != [value.value for value in CatalogObservationKindV2]
        or expected.get("identity_status") != CatalogIdentityStatusV2.HUMAN_REVIEW.value
        or expected.get("readiness") != CatalogReadinessV2.NOT_READY.value
        or expected.get("open_decision") != CATALOG_IDENTITY_OPEN_DECISION_V2
        or expected.get("external_actions") != 0
        or _string_list(fixture.get("commit_faults"))
        != [value.value for value in CatalogNormalizationSqliteCommitFaultV2]
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


def _render() -> tuple[bytes, bytes]:
    contract = _json_object(CONTRACT)
    fixture = _json_object(FIXTURE)
    _validate_contract(contract)
    _validate_fixture(fixture)
    projection: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0503",
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "dependency": {
            "story_id": "ST-0502",
            "api_version": ITEM_SEARCH_API_VERSION,
            "source": "EXACT_PERSISTED_V2_ARCHIVE_ONLY",
        },
        "state_contract": {
            "source_modes": [value.value for value in CatalogSourceModeV2],
            "identity_status": CatalogIdentityStatusV2.HUMAN_REVIEW.value,
            "readiness": CatalogReadinessV2.NOT_READY.value,
            "confidence_status": CatalogConfidenceStatusV2.SOURCE_ABSENT.value,
            "observation_kinds": [value.value for value in CatalogObservationKindV2],
            "commit_faults": [
                value.value for value in CatalogNormalizationSqliteCommitFaultV2
            ],
        },
        "event_contract": {
            "event_type": CATALOG_EVENT_TYPE_V2,
            "channel": CATALOG_EVENT_CHANNEL_V2,
            "delivery_worker": "NOT_IMPLEMENTED_NOT_ACTIVATED",
        },
        "source_boundary": contract["source_boundary"],
        "normalization_boundary": contract["normalization_boundary"],
        "identity_boundary": contract["identity_boundary"],
        "recommendation_boundary": contract["recommendation_boundary"],
        "durability_boundary": contract["durability_boundary"],
        "synthetic_fixture": fixture,
        "formal_evidence": contract["formal_evidence"],
        "external_actions": [],
        "production_authority": "NONE",
    }
    output_bytes = _bytes(projection)
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
        "story_id": "ST-0503",
        "generation_command": GENERATION_COMMAND,
        "source_sha256": {str(path): _sha(path) for path in sources},
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output_bytes).hexdigest()},
        "formal_evidence": "NOT_EXECUTED",
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
    target.write_bytes(content)


def _check(relative: Path, expected: bytes) -> None:
    if _read(relative) != expected:
        _fail("GENERATED_DRIFT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
