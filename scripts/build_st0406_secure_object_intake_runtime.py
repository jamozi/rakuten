#!/usr/bin/env python3
"""Owner-generate the deterministic ST-0406 secure intake V2 projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final, NoReturn, cast

import yaml


ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT: Final = Path("changes/st-0406/contracts/secure-object-intake-runtime.v2.json")
OUTPUT: Final = Path("changes/st-0406/generated/secure-object-intake-runtime.v2.json")
MANIFEST: Final = Path("changes/st-0406/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st0406_secure_object_intake_runtime.py")
BACKLOG: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
INTEGRATION: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
SECURITY: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"
)
TEST_CATALOG: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
OPEN_DECISIONS: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
ST0202_CONTRACT: Final = Path("changes/st-0202/contracts/local-object-storage.v1.yaml")
ST0403_CONTRACT: Final = Path(
    "changes/st-0403/contracts/authorization-registry.v1.json"
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/ops/object_intake_runtime_v2.py"),
    Path("python/raos/ports/object_intake_runtime_v2.py"),
    Path("python/raos/application/ops/object_intake_runtime_v2.py"),
    Path("python/raos/adapters/recorded_object_intake_runtime_v2.py"),
)
TEST_SOURCE: Final = (
    Path("tests/st0406/conftest.py"),
    Path("tests/st0406/test_runtime_v2.py"),
    Path("tests/st0406/test_authorization_first_v2.py"),
    Path("tests/st0406/test_archive_csv_v2.py"),
    Path("tests/st0406/test_storage_security_v2.py"),
    Path("tests/st0406/test_generation_v2.py"),
)
README: Final = Path("changes/st-0406/README.md")
PREFLIGHT: Final = Path("changes/st-0406/PREFLIGHT-20260825-v3.md")
COMPLETION: Final = Path(
    "changes/st-0406/LOCAL-IMPLEMENTATION-COMPLETION-20260825-v3.yaml"
)
MAX_BYTES: Final = 8 * 1024 * 1024
GENERATION_COMMAND: Final = (
    "python scripts/build_st0406_secure_object_intake_runtime.py"
)


class BuildError(RuntimeError):
    """Stable refusal without embedding rejected source content."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-0406 build failed: {code}") from None


def _read(relative: Path) -> bytes:
    candidate = ROOT / relative
    try:
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or ROOT not in candidate.resolve().parents
        ):
            _fail("SOURCE_PATH_INVALID")
        payload = candidate.read_bytes()
    except OSError:
        _fail("SOURCE_UNAVAILABLE")
    if not payload or len(payload) > MAX_BYTES:
        _fail("SOURCE_SIZE_INVALID")
    return payload


def _sha(relative: Path) -> str:
    return hashlib.sha256(_read(relative)).hexdigest()


def _mapping(value: object, code: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(code)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail(code)
    return {cast(str, key): item for key, item in raw.items()}


def _list(value: object, code: str) -> list[object]:
    if type(value) is not list:
        _fail(code)
    return cast(list[object], value)


def _json(relative: Path) -> dict[str, object]:
    try:
        value: object = json.loads(_read(relative))
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    return _mapping(value, "JSON_OBJECT_REQUIRED")


def _yaml(relative: Path) -> object:
    try:
        return cast(object, yaml.safe_load(_read(relative)))
    except UnicodeDecodeError, yaml.YAMLError:
        _fail("YAML_INVALID")


def _one(rows: object, *, identifier: str, code: str) -> dict[str, object]:
    matches = [
        _mapping(row, code)
        for row in _list(rows, code)
        if _mapping(row, code).get("id") == identifier
    ]
    if len(matches) != 1:
        _fail(code)
    return matches[0]


def _validate_contract(contract: dict[str, object]) -> None:
    if (
        contract.get("schema_version") != "2.0.0"
        or contract.get("story_id") != "ST-0406"
        or contract.get("local_implementation_status") != "LOCAL_CODE_COMPLETE"
        or contract.get("canonical_status") != "UNCHANGED"
        or contract.get("dependencies") != ["ST-0202", "ST-0403"]
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    authorization = _mapping(
        contract.get("authorization"), "AUTHORIZATION_CONTRACT_INVALID"
    )
    if (
        authorization.get("service") != "DurableAuthorizationService.recover_admin"
        or authorization.get("recover_before_source_or_quarantine_io") is not True
        or authorization.get("active_session_recheck") is not True
        or authorization.get("recovered_result_exact_equality") is not True
        or authorization.get(
            "request_digest_recomputed_from_recovered_session_fingerprint"
        )
        is not True
        or authorization.get("operation_id") != "ED-011"
        or authorization.get("action") != "edit_article_draft"
        or authorization.get("resource_kind") != "ARTICLE_VERSION"
        or authorization.get("resource_state") != "DRAFT"
        or authorization.get("binding_status") != "ACTIVE_RECORDED"
        or authorization.get("site_and_resource_exact_descriptor_binding") is not True
        or authorization.get("value_constructor_service_provenance") is not False
        or authorization.get("allowed_intake_kinds")
        != ["MEDIA_ASSET", "SOURCE_DOCUMENT"]
        or authorization.get("denied_intake_kinds") != ["REVENUE_REPORT"]
    ):
        _fail("AUTHORIZATION_CONTRACT_INVALID")
    storage = _mapping(contract.get("storage"), "STORAGE_CONTRACT_INVALID")
    if (
        storage.get("mode") != "RECORDED_LOCAL"
        or storage.get("owner_private_root_mode") != "0700"
        or storage.get("database_mode") != "0600"
        or storage.get("database_creation") != "CREATED_ONLY_O_EXCL_NO_EMPTY_ADOPTION"
        or storage.get("application_id") != 1_380_400_602
        or storage.get("strict_tables") is not True
        or storage.get("foreign_keys_exact_and_enforced") is not True
        or storage.get("schema_index_trigger_inventory_exact") is not True
        or storage.get("root_and_database_inode_anchored") is not True
        or storage.get("process_monotonic_prefix_anchor") is not True
        or storage.get("snapshot_rollback_detected_in_process") is not True
        or storage.get("database_replacement_detected") is not True
        or storage.get("journal") != "APPEND_ONLY_SHA256_HASH_CHAIN"
        or storage.get("journals") != ["LIFECYCLE", "COMMAND", "AUDIT"]
        or storage.get("journal_encoding") != "CANONICAL_ASCII_JSON"
        or storage.get("full_chain_semantic_verification") is not True
        or storage.get("public_byte_read_surface") is not False
    ):
        _fail("STORAGE_CONTRACT_INVALID")
    inspection = _mapping(contract.get("inspection"), "INSPECTION_CONTRACT_INVALID")
    if (
        inspection.get("archive_extraction") is not False
        or inspection.get("csv_encoding") != "STRICT_UTF_8_NO_BOM"
        or inspection.get("magic_mime_extension_exact") is not True
    ):
        _fail("INSPECTION_CONTRACT_INVALID")
    open_boundary = _mapping(
        contract.get("open_decision_boundary"), "OPEN_DECISION_BOUNDARY_INVALID"
    )
    if (
        open_boundary.get("decision_id") != "OD-014"
        or open_boundary.get("state") != "UNRESOLVED"
        or open_boundary.get("retention_default") is not None
        or open_boundary.get("automatic_deletion") is not False
        or open_boundary.get("read_export_promote_delete_lifecycle_surfaces")
        is not False
    ):
        _fail("OPEN_DECISION_BOUNDARY_INVALID")
    authority = _mapping(contract.get("authority"), "AUTHORITY_INVALID")
    if authority.get("external_action_count") != 0 or any(
        authority.get(key) is not False
        for key in (
            "socket",
            "subprocess",
            "provider",
            "credential",
            "publication",
            "staging",
            "release",
            "production",
        )
    ):
        _fail("AUTHORITY_INVALID")
    formal = _mapping(contract.get("formal_evidence"), "FORMAL_BOUNDARY_INVALID")
    if set(formal.values()) != {"NOT_EXECUTED"}:
        _fail("FORMAL_BOUNDARY_INVALID")


def _validate_sources() -> dict[str, object]:
    backlog = _mapping(_yaml(BACKLOG), "BACKLOG_INVALID")
    story = _one(backlog.get("stories"), identifier="ST-0406", code="STORY_INVALID")
    if (
        story.get("depends_on") != ["ST-0202", "ST-0403"]
        or story.get("design_refs") != ["RAOS-SEC-001"]
        or story.get("test_suites") != ["TST-014", "TST-026", "TST-031"]
        or story.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
    ):
        _fail("STORY_INVALID")

    st0403 = _json(ST0403_CONTRACT)
    trust = _mapping(st0403.get("value_trust_boundary"), "ST0403_TRUST_INVALID")
    if (
        trust.get("constructor_scope")
        != "INTERNAL_VALUE_NORMALIZATION_NOT_SERVICE_PROVENANCE"
        or trust.get("unforgeable_capability") is not False
    ):
        _fail("ST0403_TRUST_INVALID")
    bindings = [
        _mapping(row, "ST0403_BINDING_INVALID")
        for row in _list(st0403.get("bindings"), "ST0403_BINDING_INVALID")
        if _mapping(row, "ST0403_BINDING_INVALID").get("operation_id") == "ED-011"
    ]
    if len(bindings) != 1 or bindings[0] != {
        "operation_id": "ED-011",
        "action": "edit_article_draft",
        "permission_scope": "editorial:version:write",
        "resource_kind": "ARTICLE_VERSION",
        "allowed_states": ["DRAFT"],
        "status": "ACTIVE_RECORDED",
    }:
        _fail("ST0403_BINDING_INVALID")

    decisions = _mapping(_yaml(OPEN_DECISIONS), "OPEN_DECISIONS_INVALID")
    od014 = _one(
        decisions.get("items"),
        identifier="OD-014",
        code="OD014_INVALID",
    )
    if od014.get("status") not in {
        "BLOCKED_PENDING_INPUT",
        "HUMAN_DECISION_REQUIRED",
    }:
        _fail("OD014_INVALID")

    test_catalog = _mapping(_yaml(TEST_CATALOG), "TEST_CATALOG_INVALID")
    suites = _list(test_catalog.get("suites"), "TEST_CATALOG_INVALID")
    for suite_id in ("TST-014", "TST-026", "TST-031"):
        _one(suites, identifier=suite_id, code="TEST_SUITE_INVALID")
    st0202 = _mapping(_yaml(ST0202_CONTRACT), "ST0202_CONTRACT_INVALID")
    st0202_document = _mapping(st0202.get("document"), "ST0202_CONTRACT_INVALID")
    if st0202_document.get("story_id") != "ST-0202":
        _fail("ST0202_CONTRACT_INVALID")
    return story


def _bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _render() -> tuple[bytes, bytes]:
    contract = _json(CONTRACT)
    _validate_contract(contract)
    story = _validate_sources()
    projection: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-0406",
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "story": {
            "depends_on": story["depends_on"],
            "design_refs": story["design_refs"],
            "test_suites": story["test_suites"],
        },
        "runtime_contract": contract,
        "external_actions": [],
    }
    output = _bytes(projection)
    sources = (
        BACKLOG,
        INTEGRATION,
        SECURITY,
        TEST_CATALOG,
        OPEN_DECISIONS,
        ST0202_CONTRACT,
        ST0403_CONTRACT,
        CONTRACT,
        README,
        PREFLIGHT,
        COMPLETION,
        GENERATOR,
        *RUNTIME_SOURCE,
        *TEST_SOURCE,
    )
    manifest = {
        "schema_version": "2.0.0",
        "story_id": "ST-0406",
        "generation_command": GENERATION_COMMAND,
        "source_sha256": {str(path): _sha(path) for path in sources},
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output).hexdigest()},
        "formal_evidence": "NOT_EXECUTED",
        "live_provider": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "external_action_count": 0,
    }
    return output, _bytes(manifest)


def _write(relative: Path, content: bytes) -> None:
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _check(relative: Path, expected: bytes) -> None:
    if _read(relative) != expected:
        _fail("GENERATED_DRIFT")


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    output, manifest = _render()
    if arguments.check:
        _check(OUTPUT, output)
        _check(MANIFEST, manifest)
    else:
        _write(OUTPUT, output)
        _write(MANIFEST, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
