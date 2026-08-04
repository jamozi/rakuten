"""Static contract, reference, schema, and manifest tests for ST-0002."""

from __future__ import annotations

from collections.abc import Iterator
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from jsonschema import Draft202012Validator
import yaml

from scripts import build_st0002_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0002"
CONTRACTS_ROOT = BUNDLE_ROOT / "contracts"
MANIFEST_PATH = BUNDLE_ROOT / "manifest.yaml"
STATE_CONTRACT_PATH = BUNDLE_ROOT / "job-state.v1.yaml"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
UPSTREAM_API_ROOT = "RAOS_04_api_contract_package_v0.1/"
UPSTREAM_JOB_MESSAGE = f"{UPSTREAM_API_ROOT}schemas/common/job-message.schema.json"
JOB_MESSAGE_PATH = CONTRACTS_ROOT / "schemas" / "common" / "job-message.schema.json"
CANONICAL_STATES = (
    "REQUESTED",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "RETRY_SCHEDULED",
    "FAILED_TERMINAL",
    "QUARANTINED",
    "CANCELLED",
    "EXPIRED",
)
ALLOWED_TRANSITIONS = frozenset(
    {
        ("REQUESTED", "QUEUED"),
        ("REQUESTED", "CANCELLED"),
        ("REQUESTED", "EXPIRED"),
        ("QUEUED", "RUNNING"),
        ("QUEUED", "CANCELLED"),
        ("QUEUED", "EXPIRED"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED_RETRYABLE"),
        ("RUNNING", "FAILED_TERMINAL"),
        ("RUNNING", "QUARANTINED"),
        ("RUNNING", "CANCELLED"),
        ("RUNNING", "EXPIRED"),
        ("FAILED_RETRYABLE", "RETRY_SCHEDULED"),
        ("FAILED_RETRYABLE", "FAILED_TERMINAL"),
        ("RETRY_SCHEDULED", "QUEUED"),
        ("QUARANTINED", "QUEUED"),
    }
)
LEGACY_MAPPING = {
    "PENDING": "REQUESTED",
    "READY": "QUEUED",
    "FAILED": "FAILED_TERMINAL",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "QUARANTINED": "QUARANTINED",
    "CANCELLED": "CANCELLED",
}
EXPECTED_MODEL_SETS = {
    "completed_at_required": (
        "SUCCEEDED",
        "FAILED_TERMINAL",
        "QUARANTINED",
        "CANCELLED",
        "EXPIRED",
    ),
    "absorbing": (
        "SUCCEEDED",
        "FAILED_TERMINAL",
        "CANCELLED",
        "EXPIRED",
    ),
    "deadline_index_states": (
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
    ),
    "cancellable": ("REQUESTED", "QUEUED", "RUNNING"),
}
STATE_MACHINE_MODEL_KEYS = {
    "completed_at_required": "x-raos-completed-at-required",
    "absorbing": "x-raos-absorbing-states",
    "deadline_index_states": "x-raos-deadline-index-states",
    "cancellable": "x-raos-cancellable-states",
}


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"expected YAML mapping: {path}"
    return document


def load_contract(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def walk_refs(document: Any) -> Iterator[str]:
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "$ref":
                assert isinstance(value, str)
                yield value
            yield from walk_refs(value)
    elif isinstance(document, list):
        for value in document:
            yield from walk_refs(value)


def resolve_json_pointer(document: Any, fragment: str, *, source: Path) -> Any:
    pointer = unquote(fragment)
    if pointer == "":
        return document
    assert pointer.startswith("/"), (
        f"only JSON Pointer fragments are allowed in {source}: #{fragment}"
    )
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            assert token in current, (
                f"missing JSON Pointer token {token!r} in {source}: #{fragment}"
            )
            current = current[token]
        elif isinstance(current, list):
            assert token.isdecimal(), (
                f"non-numeric list token {token!r} in {source}: #{fragment}"
            )
            index = int(token)
            assert index < len(current), (
                f"list token out of range in {source}: #{fragment}"
            )
            current = current[index]
        else:
            raise AssertionError(
                f"JSON Pointer traverses a scalar in {source}: #{fragment}"
            )
    return current


def resolve_ref(source: Path, reference: str) -> tuple[Path, str]:
    parsed = urlsplit(reference)
    assert not parsed.scheme and not parsed.netloc, (
        f"remote reference is forbidden in {source}: {reference}"
    )
    assert not parsed.query, f"query component is forbidden in {source}: {reference}"
    assert "\\" not in parsed.path, (
        f"backslash path is forbidden in {source}: {reference}"
    )

    relative_path = unquote(parsed.path)
    if relative_path:
        assert not PurePosixPath(relative_path).is_absolute(), (
            f"absolute reference is forbidden in {source}: {reference}"
        )
        target = (source.parent / relative_path).resolve()
    else:
        target = source.resolve()

    try:
        target.relative_to(CONTRACTS_ROOT.resolve())
    except ValueError as exc:
        raise AssertionError(
            f"reference escapes the contract tree in {source}: {reference}"
        ) from exc
    assert target.is_file(), f"reference target is missing: {source}: {reference}"
    assert not target.is_symlink(), (
        f"reference target must not be a symlink: {source}: {reference}"
    )
    return target, parsed.fragment


def safe_repository_artifact(raw_path: str) -> Path:
    assert "\\" not in raw_path, f"backslash manifest path: {raw_path}"
    logical_path = PurePosixPath(raw_path)
    assert raw_path == logical_path.as_posix(), (
        f"non-canonical manifest path: {raw_path}"
    )
    assert not logical_path.is_absolute(), f"absolute manifest path: {raw_path}"
    assert ".." not in logical_path.parts, f"escaping manifest path: {raw_path}"

    lexical_path = REPOSITORY_ROOT.joinpath(*logical_path.parts)
    resolved_path = lexical_path.resolve()
    try:
        resolved_path.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise AssertionError(f"manifest path escapes repository: {raw_path}") from exc
    assert lexical_path.is_file(), f"manifest artifact is missing: {raw_path}"
    assert not lexical_path.is_symlink(), (
        f"manifest artifact must not be a symlink: {raw_path}"
    )
    return lexical_path


def assert_hashed_artifact(entry: dict[str, Any]) -> Path:
    path = safe_repository_artifact(entry["path"])
    content = path.read_bytes()

    if "bytes" in entry:
        assert entry["bytes"] == len(content)
    assert entry["sha256"] == sha256(content).hexdigest()
    return path


def job_resource(resource_contracts: dict[str, Any]) -> dict[str, Any]:
    matches = [
        resource
        for resource in resource_contracts["resources"]
        if resource.get("name") == "Job"
    ]
    assert len(matches) == 1
    return matches[0]


def job_state_machine(state_catalog: dict[str, Any]) -> dict[str, Any]:
    matches = [
        machine
        for machine in state_catalog["machines"]
        if machine.get("id") == "SM-JOB"
    ]
    assert len(matches) == 1
    return matches[0]


def test_revision_provenance_and_version_are_consistent() -> None:
    state_contract = load_yaml(STATE_CONTRACT_PATH)
    manifest = load_yaml(MANIFEST_PATH)
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.2.yaml")
    internal = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.2.yaml")
    asyncapi = load_yaml(CONTRACTS_ROOT / "asyncapi.v0.2.yaml")

    assert state_contract["document"]["revision_artifact_version"] == "0.2"
    assert manifest["document"] == {
        "id": revision.REVISION_ID,
        "version": "0.2",
        "story_id": "ST-0002",
        "status": "IMPLEMENTATION_CANDIDATE",
        "generated_by": "scripts/build_st0002_revision.py",
    }
    for contract in (admin, internal, asyncapi):
        info = contract["info"]
        assert info["version"] == "0.2"
        assert info["x-raos-revision-id"] == revision.REVISION_ID
        assert info["x-raos-story-id"] == "ST-0002"
        assert info["x-raos-decision-id"] == "INT-DEC-003"
        assert info["x-raos-base-version"] == "0.1"

    for catalog_name in (
        "job-catalog.v0.2.yaml",
        "resource-contracts.v0.2.yaml",
        "schema-registry.v0.2.yaml",
        "state-transition-catalog.v0.2.yaml",
    ):
        catalog = load_yaml(CONTRACTS_ROOT / "catalogs" / catalog_name)
        document = catalog["document"]
        assert document["version"] == "0.2"
        assert document["provenance"] == {
            "story_id": "ST-0002",
            "decision_id": "INT-DEC-003",
            "revision_id": revision.REVISION_ID,
            "base_version": "0.1",
        }


def test_canonical_state_model_is_equal_across_all_contract_artifacts() -> None:
    state_contract = load_yaml(STATE_CONTRACT_PATH)
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.2.yaml")
    job_catalog = load_yaml(CONTRACTS_ROOT / "catalogs" / "job-catalog.v0.2.yaml")
    state_catalog = load_yaml(
        CONTRACTS_ROOT / "catalogs" / "state-transition-catalog.v0.2.yaml"
    )
    resources = load_yaml(CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.2.yaml")

    source_model = state_contract["state_model"]
    machine = job_state_machine(state_catalog)
    resource_fields = {
        field["name"]: field for field in job_resource(resources)["fields"]
    }
    admin_job = admin["components"]["schemas"]["Job"]
    status_parameter = [
        parameter
        for parameter in admin["paths"]["/api/v1/admin/ops/jobs"]["get"]["parameters"]
        if parameter.get("name") == "status"
    ]

    assert len(status_parameter) == 1
    state_vectors = (
        tuple(source_model["states"]),
        tuple(job_catalog["canonical_states"]),
        tuple(machine["states"]),
        tuple(admin_job["properties"]["status"]["enum"]),
        tuple(resource_fields["status"]["schema"]["enum"]),
        tuple(status_parameter[0]["schema"]["enum"]),
    )
    assert state_vectors == (CANONICAL_STATES,) * len(state_vectors)
    assert machine["initial"] == source_model["initial"] == "REQUESTED"
    assert job_catalog["state_model"]["initial_state"] == "REQUESTED"

    for field, expected in EXPECTED_MODEL_SETS.items():
        assert tuple(source_model[field]) == expected
        assert tuple(job_catalog["state_model"][field]) == expected
        assert tuple(machine[STATE_MACHINE_MODEL_KEYS[field]]) == expected

    catalog_edges = {
        (transition[0], transition[1]) for transition in machine["transitions"]
    }
    assert catalog_edges == ALLOWED_TRANSITIONS
    assert machine["x-raos-legacy-mapping"] == LEGACY_MAPPING


def test_admin_job_fields_and_query_contract_are_canonical() -> None:
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.2.yaml")
    resources = load_yaml(CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.2.yaml")
    properties = admin["components"]["schemas"]["Job"]["properties"]
    resource_fields = {
        field["name"]: field for field in job_resource(resources)["fields"]
    }

    assert properties["job_version"]["type"] == "integer"
    assert properties["job_version"]["minimum"] == 1
    assert properties["job_version"]["readOnly"] is True
    assert resource_fields["job_version"]["schema"]["type"] == "integer"
    assert resource_fields["job_version"]["schema"]["minimum"] == 1
    assert resource_fields["job_version"]["read_only"] is True

    for field_name in ("deadline_at", "cancel_requested_at"):
        api_schema = properties[field_name]
        resource_schema = resource_fields[field_name]["schema"]
        for schema in (api_schema, resource_schema):
            assert schema["readOnly"] is True
            assert schema["anyOf"][0]["type"] == "string"
            assert schema["anyOf"][0]["format"] == "date-time"
            assert schema["anyOf"][1] == {"type": "null"}
        assert resource_fields[field_name]["read_only"] is True

    assert "lock_version" in properties
    assert "job_version" in properties
    assert properties["lock_version"] != properties["job_version"]

    status_parameters = [
        parameter
        for parameter in admin["paths"]["/api/v1/admin/ops/jobs"]["get"]["parameters"]
        if parameter.get("name") == "status"
    ]
    assert len(status_parameters) == 1
    assert tuple(status_parameters[0]["schema"]["enum"]) == CANONICAL_STATES


def test_job_accepted_wire_contract_remains_requested_or_queued() -> None:
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.2.yaml")
    internal = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.2.yaml")
    admin_schema = admin["components"]["schemas"]["JobAccepted"]
    internal_schema = internal["components"]["schemas"]["JobAccepted"]

    assert admin_schema == internal_schema
    assert admin_schema["additionalProperties"] is False
    assert admin_schema["properties"]["status"] == {
        "type": "string",
        "enum": ["REQUESTED", "QUEUED"],
    }
    assert set(admin_schema["required"]) == {
        "job_id",
        "display_id",
        "status",
        "status_url",
        "correlation_id",
    }


def test_job_commands_have_complete_optimistic_concurrency_contracts() -> None:
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.2.yaml")
    commands = (
        ("/api/v1/admin/ops/jobs/{id}/retry", "202"),
        ("/api/v1/admin/ops/jobs/{id}/cancel", "200"),
    )

    for path, success_status in commands:
        operation = admin["paths"][path]["post"]
        parameter_refs = {
            parameter.get("$ref")
            for parameter in operation["parameters"]
            if isinstance(parameter, dict)
        }

        assert "#/components/parameters/IfMatch" in parameter_refs
        assert {"409", "428"} <= operation["responses"].keys()
        assert operation["responses"][success_status]["headers"]["ETag"] == {
            "$ref": "#/components/headers/ETag"
        }
        assert operation["x-raos-state-conflict-status"] == 409
        assert operation["x-raos-success-etag-required"] is True


def test_custom_contract_links_resolve_from_each_generated_artifact() -> None:
    admin_path = CONTRACTS_ROOT / "openapi-admin.v0.2.yaml"
    internal_path = CONTRACTS_ROOT / "openapi-internal.v0.2.yaml"
    asyncapi_path = CONTRACTS_ROOT / "asyncapi.v0.2.yaml"
    resources_path = CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.2.yaml"
    job_catalog_path = CONTRACTS_ROOT / "catalogs" / "job-catalog.v0.2.yaml"
    state_catalog_path = (
        CONTRACTS_ROOT / "catalogs" / "state-transition-catalog.v0.2.yaml"
    )
    admin = load_yaml(admin_path)
    internal = load_yaml(internal_path)
    asyncapi = load_yaml(asyncapi_path)
    resources = load_yaml(resources_path)
    job_catalog = load_yaml(job_catalog_path)

    resource_fields = {
        field["name"]: field for field in job_resource(resources)["fields"]
    }
    state_links = (
        (
            admin_path,
            admin["components"]["schemas"]["Job"]["properties"]["status"][
                "x-raos-state-contract"
            ],
        ),
        (
            admin_path,
            admin["paths"]["/api/v1/admin/ops/jobs/{id}/retry"]["post"][
                "x-raos-state-contract"
            ],
        ),
        (
            admin_path,
            admin["paths"]["/api/v1/admin/ops/jobs/{id}/cancel"]["post"][
                "x-raos-state-contract"
            ],
        ),
        (internal_path, internal["info"]["x-raos-job-state-contract"]),
        (asyncapi_path, asyncapi["x-raos-job-state-contract"]),
        (
            resources_path,
            resource_fields["status"]["schema"]["x-raos-state-contract"],
        ),
    )
    for source, relative_link in state_links:
        assert (
            source.parent / relative_link
        ).resolve() == STATE_CONTRACT_PATH.resolve()

    machine_link, fragment = job_catalog["state_model"]["state_machine_ref"].split(
        "#", 1
    )
    assert (job_catalog_path.parent / machine_link).resolve() == (
        state_catalog_path.resolve()
    )
    assert fragment == "SM-JOB"
    assert job_state_machine(load_yaml(state_catalog_path))["id"] == fragment


def test_common_job_message_is_byte_frozen_at_wire_version_one() -> None:
    with ZipFile(revision.API_PACKAGE) as archive:
        upstream_content = archive.read(UPSTREAM_JOB_MESSAGE)
    generated_content = JOB_MESSAGE_PATH.read_bytes()
    schema = json.loads(generated_content)
    internal = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.2.yaml")
    asyncapi = load_yaml(CONTRACTS_ROOT / "asyncapi.v0.2.yaml")
    registry = load_yaml(CONTRACTS_ROOT / "catalogs" / "schema-registry.v0.2.yaml")
    manifest = load_yaml(MANIFEST_PATH)

    assert generated_content == upstream_content
    assert schema["$schema"] == JSON_SCHEMA_DIALECT
    assert schema["$id"] == (
        "https://schemas.raos.local/common/job-message.schema.json"
    )
    assert schema["required"] == [
        "job_id",
        "job_type",
        "job_version",
        "queue",
        "idempotency_key",
        "requested_at",
        "available_at",
        "priority",
        "resource_ref",
        "budget",
        "correlation_id",
        "requested_by",
        "payload",
    ]
    assert schema["properties"]["job_version"] == {
        "type": "integer",
        "minimum": 1,
    }
    assert schema["properties"]["deadline_at"] == {
        "type": ["string", "null"],
        "format": "date-time",
    }
    assert "deadline_at" not in schema["required"]
    assert "cancel_requested_at" not in schema["properties"]
    assert internal["info"]["x-raos-wire-change"] == "NONE"
    assert asyncapi["info"]["x-raos-wire-change"] == "NONE"
    assert asyncapi["x-raos-job-state-contract"] == "../job-state.v1.yaml"
    assert registry["revision_policy"] == {
        "job_message_wire_change": "NONE",
        "job_message_version": 1,
        "common_schema_frozen": True,
        "revision_id": revision.REVISION_ID,
    }
    assert manifest["compatibility"]["job_message_major"] == 1
    assert manifest["compatibility"]["job_message_wire_change"] == "NONE"


def test_all_contract_references_are_local_safe_and_resolvable() -> None:
    sources = sorted(path for path in CONTRACTS_ROOT.rglob("*") if path.is_file())
    documents = {source.resolve(): load_contract(source) for source in sources}
    resolved_reference_count = 0

    for source in sources:
        document = documents[source.resolve()]
        for reference in walk_refs(document):
            target, fragment = resolve_ref(source, reference)
            target_document = documents[target]
            resolve_json_pointer(target_document, fragment, source=target)
            resolved_reference_count += 1

    assert resolved_reference_count == 2931


def test_schema_registry_covers_and_meta_validates_the_exact_schema_tree() -> None:
    registry = load_yaml(CONTRACTS_ROOT / "catalogs" / "schema-registry.v0.2.yaml")
    entries = {entry["path"]: entry for entry in registry["schemas"]}
    actual_paths = {
        path.relative_to(CONTRACTS_ROOT).as_posix(): path
        for path in (CONTRACTS_ROOT / "schemas").rglob("*.json")
        if path.is_file()
    }

    assert registry["dialect"] == JSON_SCHEMA_DIALECT
    assert len(entries) == len(registry["schemas"]) == 126
    assert set(entries) == set(actual_paths)
    assert len({path.casefold() for path in entries}) == len(entries)

    for relative_path, path in actual_paths.items():
        entry = entries[relative_path]
        content = path.read_bytes()
        schema = json.loads(content)

        assert schema["$schema"] == JSON_SCHEMA_DIALECT
        assert entry["id"] == schema["$id"]
        assert entry["title"] == schema["title"]
        assert entry["sha256"] == sha256(content).hexdigest()
        Draft202012Validator.check_schema(schema)


def test_manifest_paths_file_sets_sizes_and_hashes_are_complete() -> None:
    manifest = load_yaml(MANIFEST_PATH)

    sections = {
        "inputs": manifest["inputs"],
        "source_artifacts": manifest["source_artifacts"],
        "generated_artifacts": manifest["generated_artifacts"],
    }
    for entries in sections.values():
        paths = [entry["path"] for entry in entries]
        assert len(paths) == len(set(paths))
        assert len(paths) == len({path.casefold() for path in paths})
        for entry in entries:
            assert_hashed_artifact(entry)

    expected_inputs = set(revision.EXPECTED_INPUT_HASHES)
    assert {entry["path"] for entry in sections["inputs"]} == expected_inputs
    assert {
        entry["path"]: entry["sha256"] for entry in sections["inputs"]
    } == revision.EXPECTED_INPUT_HASHES

    expected_sources = {
        "scripts/build_st0002_revision.py",
        "changes/st-0002/README.md",
        "changes/st-0002/job-state.v1.yaml",
        *{
            f"changes/st-0002/database/{filename}"
            for filename in revision.MIGRATION_FILES
        },
    }
    assert {entry["path"] for entry in sections["source_artifacts"]} == (
        expected_sources
    )

    actual_generated = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file()
    }
    manifest_generated = {entry["path"] for entry in sections["generated_artifacts"]}
    assert manifest["generated_artifact_count"] == 133
    assert len(manifest_generated) == 133
    assert manifest_generated == actual_generated
    assert all(
        path.startswith("changes/st-0002/contracts/") for path in manifest_generated
    )
