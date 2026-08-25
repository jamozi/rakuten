#!/usr/bin/env python3
"""Owner-generate the deterministic maximum-safe local ST-0502 projection."""

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

from raos.adapters.sqlite_rakuten_item_search_runtime_v2 import (  # noqa: E402
    SqliteCommitFaultV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (  # noqa: E402
    FORBIDDEN_RECOMMENDATION_INPUTS_V2,
    ITEM_SEARCH_API_VERSION,
    ITEM_SEARCH_ENDPOINT_PATH,
    ITEM_SEARCH_FORMAT_VERSION,
    ITEM_SEARCH_ORIGIN,
    ITEM_SEARCH_SECRET_NAME_BINDINGS_V2,
    OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256,
    OFFICIAL_ITEM_SEARCH_DOCUMENTATION_URL,
    SAFE_ITEM_SEARCH_ELEMENTS_V2,
    SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2,
    IngestionSessionStateV2,
    IngestionStepOutcomeV2,
    ProviderFailureClassV2,
    ProviderModeV2,
)


SOURCE_FACTS: Final = Path(
    "changes/st-0502/contracts/rakuten-item-search-official-source-facts.v2.json"
)
CONTRACT: Final = Path("changes/st-0502/contracts/item-search-runtime.v2.json")
FIXTURE: Final = Path("changes/st-0502/fixtures/item-search-pages.synthetic.v2.json")
OUTPUT: Final = Path("changes/st-0502/generated/item-search-runtime.v2.json")
MANIFEST: Final = Path("changes/st-0502/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0502_item_search_runtime.py")
CANONICAL: Final = (
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/catalog/rakuten_item_search_runtime_v2.py"),
    Path("python/raos/ports/rakuten_item_search_runtime_v2.py"),
    Path("python/raos/application/catalog/rakuten_item_search_runtime_v2.py"),
    Path("python/raos/adapters/recorded_rakuten_item_search_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_rakuten_item_search_runtime_v2.py"),
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
GENERATION_COMMAND: Final = "python scripts/build_st0502_item_search_runtime.py"


class BuildError(RuntimeError):
    """Stable owner-generator refusal without rejected source material."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-0502 build failed: {code}") from None


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


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("JSON_OBJECT_REQUIRED")
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        _fail("JSON_OBJECT_REQUIRED")
    return {cast(str, key): item for key, item in raw.items()}


def _string_list(value: object) -> list[str]:
    if type(value) is not list:
        _fail("STRING_LIST_REQUIRED")
    items = cast(list[object], value)
    if any(type(item) is not str for item in items):
        _fail("STRING_LIST_REQUIRED")
    return cast(list[str], items)


def _validate_source_facts(source: dict[str, object]) -> None:
    normalized = _mapping(source.get("normalized_facts"))
    if (
        source.get("schema_version") != "2.0.0"
        or source.get("source_kind") != "OFFICIAL_PRIMARY_DOCUMENTATION"
        or source.get("url") != OFFICIAL_ITEM_SEARCH_DOCUMENTATION_URL
        or source.get("raw_response_sha256")
        != OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256
        or source.get("fetched_at") != "2026-08-24T16:43:55Z"
        or any(
            source.get(key) is not False
            for key in (
                "raw_response_committed",
                "raw_html_committed",
                "api_test_material_committed",
                "credential_or_sample_value_committed",
            )
        )
    ):
        _fail("OFFICIAL_SOURCE_BINDING_INVALID")
    if (
        normalized.get("api_version") != ITEM_SEARCH_API_VERSION
        or normalized.get("origin") != ITEM_SEARCH_ORIGIN
        or normalized.get("endpoint_path") != ITEM_SEARCH_ENDPOINT_PATH
        or normalized.get("format_version_2_supported") is not True
        or normalized.get("access_key_required") is not True
        or normalized.get("access_key_transport")
        != "HTTP_HEADER_SECRET_NAME_ONLY_FUTURE_BINDING"
        or normalized.get("hits_minimum") != 1
        or normalized.get("hits_maximum") != 30
        or normalized.get("page_minimum") != 1
        or normalized.get("page_maximum") != 100
        or _string_list(normalized.get("implemented_safe_input_subset"))
        != list(SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2)
        or _string_list(normalized.get("implemented_safe_output_subset"))
        != [item.value for item in SAFE_ITEM_SEARCH_ELEMENTS_V2]
    ):
        _fail("NORMALIZED_FACTS_INVALID")


def _validate_contract(contract: dict[str, object]) -> None:
    provider = _mapping(contract.get("provider_boundary"))
    wire = _mapping(contract.get("wire_boundary"))
    durability = _mapping(contract.get("durability_boundary"))
    recommendation = _mapping(contract.get("recommendation_boundary"))
    formal = _mapping(contract.get("formal_evidence"))
    if (
        contract.get("schema_version") != "2.0.0"
        or contract.get("story_id") != "ST-0502"
        or contract.get("local_implementation_status") != "LOCAL_CODE_COMPLETE"
        or contract.get("canonical_status") != "UNCHANGED"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if (
        _string_list(provider.get("modes"))
        != [ProviderModeV2.RECORDED_SYNTHETIC.value, ProviderModeV2.DISABLED.value]
        or provider.get("live_http_mode_representable") is not False
        or provider.get("ambient_environment_read") is not False
        or provider.get("credential_value_read") is not False
        or provider.get("external_actions") != 0
        or provider.get("collaborator_arguments_boundary_copied") is not True
        or provider.get(
            "collaborator_arguments_revalidated_after_normal_or_exception_return"
        )
        is not True
        or provider.get(
            "provider_and_store_action_count_checked_before_and_after_calls"
        )
        is not True
        or provider.get("loop") is not False
        or provider.get("sleep") is not False
        or provider.get("worker_activation") is not False
    ):
        _fail("PROVIDER_BOUNDARY_INVALID")
    if (
        wire.get("access_key_transport") != "HEADER_SECRET_NAME_ONLY"
        or any(
            wire.get(key) is not False
            for key in (
                "application_id_value_rendered",
                "access_key_value_rendered",
                "affiliate_id_value_rendered",
                "url_contains_secret_value",
                "log_contains_secret_value",
                "archive_contains_secret_value",
            )
        )
        or durability.get("backend") != "OWNER_PRIVATE_SQLITE_BLOB"
        or durability.get("sqlite_schema_version") != 2
        or durability.get("exclusive_dirfd_create_winner_only") is not True
        or durability.get("preexisting_empty_partial_or_foreign_database_rejected")
        is not True
        or durability.get("append_only_update_delete_triggers") is not True
        or durability.get("hash_bound_command_result_rate_and_mutation_chain")
        is not True
        or durability.get("foreign_key_and_integrity_checks_recomputed") is not True
        or durability.get("device_inode_pinned") is not True
        or durability.get("process_local_mutation_count_head_and_prefix_pinned")
        is not True
        or durability.get("same_inode_process_local_rollback_rejected") is not True
        or durability.get("cross_restart_rollback_external_anchor") is not False
        or durability.get("exact_committed_recovery_recomputed") is not True
        or durability.get("canonical_json_uuid_and_utc_persistence") is not True
        or durability.get("persisted_external_action_count") != 0
        or durability.get("object_cloud_storage") != "NOT_EXECUTED"
        or _string_list(recommendation.get("provider_derived_recommendation_inputs"))
        != []
        or _string_list(recommendation.get("excluded_inputs"))
        != list(FORBIDDEN_RECOMMENDATION_INPUTS_V2)
    ):
        _fail("RUNTIME_BOUNDARY_INVALID")
    if any(
        formal.get(key) != "NOT_EXECUTED"
        for key in (
            "TST-014",
            "TST-015",
            "real_rakuten_credential",
            "live_rakuten_call",
            "object_cloud_storage",
            "hosted_ci",
            "staging",
            "release",
            "production",
        )
    ):
        _fail("FORMAL_BOUNDARY_INVALID")


def _validate_fixture(fixture: dict[str, object]) -> None:
    pages = fixture.get("success_pages")
    if type(pages) is not list:
        _fail("FIXTURE_PAGES_INVALID")
    page_mappings = [_mapping(value) for value in cast(list[object], pages)]
    if (
        fixture.get("schema_version") != "2.0.0"
        or fixture.get("synthetic") is not True
        or fixture.get("operational_default") is not False
        or fixture.get("activation") is not False
        or fixture.get("external_actions") != 0
        or fixture.get("contains_credential_or_sample_value") is not False
        or [value.get("page") for value in page_mappings] != [1, 2]
        or [value.get("expected_state") for value in page_mappings]
        != [
            IngestionSessionStateV2.READY.value,
            IngestionSessionStateV2.COMPLETED.value,
        ]
        or [value.get("expected_outcome") for value in page_mappings]
        != [
            IngestionStepOutcomeV2.PAGE_ARCHIVED.value,
            IngestionStepOutcomeV2.COMPLETED.value,
        ]
        or fixture.get("commit_faults")
        != [value.value for value in SqliteCommitFaultV2]
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
    source_facts = _json_object(SOURCE_FACTS)
    contract = _json_object(CONTRACT)
    fixture = _json_object(FIXTURE)
    _validate_source_facts(source_facts)
    _validate_contract(contract)
    _validate_fixture(fixture)
    external_actions: list[str] = []
    projection: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0502",
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "official_source": {
            "url": source_facts["url"],
            "fetched_at": source_facts["fetched_at"],
            "raw_response_sha256": source_facts["raw_response_sha256"],
            "raw_response_committed": False,
        },
        "api": {
            "version": ITEM_SEARCH_API_VERSION,
            "format_version": ITEM_SEARCH_FORMAT_VERSION,
            "origin": ITEM_SEARCH_ORIGIN,
            "endpoint_path": ITEM_SEARCH_ENDPOINT_PATH,
            "safe_query_parameters": list(SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2),
            "safe_elements": [value.value for value in SAFE_ITEM_SEARCH_ELEMENTS_V2],
            "secret_name_bindings": [
                {
                    "provider_name": value.provider_name,
                    "secret_name": value.secret_name,
                    "transport": value.transport.value,
                    "required": value.required,
                }
                for value in ITEM_SEARCH_SECRET_NAME_BINDINGS_V2
            ],
        },
        "state_contract": {
            "provider_modes": [value.value for value in ProviderModeV2],
            "provider_failure_classes": [
                value.value for value in ProviderFailureClassV2
            ],
            "ingestion_states": [value.value for value in IngestionSessionStateV2],
            "step_outcomes": [value.value for value in IngestionStepOutcomeV2],
            "commit_faults": [value.value for value in SqliteCommitFaultV2],
        },
        "provider_boundary": contract["provider_boundary"],
        "wire_boundary": contract["wire_boundary"],
        "parser_boundary": contract["parser_boundary"],
        "ingestion_boundary": contract["ingestion_boundary"],
        "durability_boundary": contract["durability_boundary"],
        "recommendation_boundary": contract["recommendation_boundary"],
        "synthetic_fixture": fixture,
        "formal_evidence": contract["formal_evidence"],
        "external_actions": external_actions,
    }
    output_bytes = _bytes(projection)
    sources = (
        *CANONICAL,
        *RUNTIME_SOURCE,
        SOURCE_FACTS,
        CONTRACT,
        FIXTURE,
        GENERATOR,
    )
    manifest = {
        "schema_version": "2.0.0",
        "story_id": "ST-0502",
        "generation_command": GENERATION_COMMAND,
        "source_sha256": {str(path): _sha(path) for path in sources},
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output_bytes).hexdigest()},
        "official_source_raw_response_sha256": (
            OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256
        ),
        "raw_official_response_committed": False,
        "credential_or_sample_value_committed": False,
        "formal_evidence": "NOT_EXECUTED",
        "live_provider": "NOT_EXECUTED",
        "object_cloud_storage": "NOT_EXECUTED",
        "hosted_ci": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
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
