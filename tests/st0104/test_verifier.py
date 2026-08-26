"""TST-002-equivalent corpus, reference, and registry verification tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from .support import MANIFEST_NAME, REPO_ROOT, VERIFIER_PATH, VERSION_ROOT


EXPECTED_REPORT = {
    "artifacts": 306,
    "asyncapi": 1,
    "asyncapi_channel_message_refs": 144,
    "asyncapi_channel_server_refs": 22,
    "asyncapi_message_payload_refs": 105,
    "asyncapi_operation_channel_refs": 37,
    "asyncapi_operation_message_refs": 249,
    "contract_yaml": 47,
    "csv": 2,
    "csv_external_provenance_refs": 1,
    "csv_header_rows": 2,
    "csv_local_refs": 111,
    "csv_records": 1126,
    "csv_rows_including_headers": 1128,
    "declared_hash_bindings": 337,
    "embedded_public_resource_schema_refs": 3,
    "embedded_public_resource_schemas": 7,
    "hash_bound_refs": 66,
    "json": 244,
    "json_schema_refs": 344,
    "json_schemas": 224,
    "job_state_yaml": 1,
    "local_refs": 3844,
    "markdown": 12,
    "openapi": 3,
    "openapi_header_refs": 528,
    "openapi_parameter_refs": 486,
    "openapi_response_refs": 1434,
    "openapi_schema_refs": 492,
    "prompt_frontmatter_refs": 12,
    "registry_entries": 271,
    "role_classified_local_refs": 3844,
    "schema_ids": 224,
    "schema_uri_aliases": 6,
    "semantic_local_refs": 192,
    "semantic_schema_path_refs": 99,
    "semantic_schema_id_refs": 14,
    "status": "PASS",
}


def copy_version(tmp_path: Path) -> Path:
    target = tmp_path / "raos-v0.4"
    shutil.copytree(VERSION_ROOT, target)
    return target


def load_manifest(root: Path) -> dict[str, Any]:
    value = json.loads((root / MANIFEST_NAME).read_bytes())
    assert isinstance(value, dict)
    return value


def load_contract_documents(
    verifier_module: ModuleType, root: Path
) -> tuple[Any, dict[str, object], dict[str, dict[str, object]]]:
    repository = verifier_module.ContractRepository(root)
    documents: dict[str, object] = {}
    schemas: dict[str, dict[str, object]] = {}
    for artifact in repository.artifacts:
        path = artifact.path
        if path.startswith("contracts/") and path.endswith(".json"):
            document = repository.load_json(path)
        elif path.startswith("contracts/") and path.endswith(".yaml"):
            document = verifier_module._strict_yaml(
                repository.read_bytes(path), source=path
            )
        else:
            continue
        documents[path] = document
        if (
            path.endswith(".json")
            and isinstance(document, dict)
            and document.get("$schema") == verifier_module.SCHEMA_DIALECT
        ):
            schemas[path] = document
    documents["job-state.v1.yaml"] = verifier_module._strict_yaml(
        repository.read_bytes("job-state.v1.yaml"), source="job-state.v1.yaml"
    )
    return repository, documents, schemas


def rebind_artifact(root: Path, path: str) -> None:
    manifest = load_manifest(root)
    payload = (root / path).read_bytes()
    entry = next(item for item in manifest["artifacts"] if item["path"] == path)
    entry["bytes"] = len(payload)
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def replace_first_key(value: object, key: str, replacement: str) -> bool:
    if isinstance(value, dict):
        for current_key, child in value.items():
            if current_key == key and isinstance(child, str):
                value[current_key] = replacement
                return True
            if replace_first_key(child, key, replacement):
                return True
    elif isinstance(value, list):
        for child in value:
            if replace_first_key(child, key, replacement):
                return True
    return False


def invalidate_first_inline_schema_type(value: object) -> bool:
    if isinstance(value, dict):
        schema = value.get("schema")
        if isinstance(schema, dict) and isinstance(schema.get("type"), str):
            schema["type"] = 7
            return True
        return any(
            invalidate_first_inline_schema_type(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(invalidate_first_inline_schema_type(child) for child in value)
    return False


def mutate_json_reference(root: Path, reference: str) -> None:
    path = "contracts/schemas/common/publication-snapshot.schema.json"
    target = root / path
    document = json.loads(target.read_bytes())
    assert replace_first_key(document, "$ref", reference)
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_artifact(root, path)


def run_verifier(root: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(VERIFIER_PATH)]
    if root is not None:
        command.extend(["--root", str(root)])
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_live_verifier_cli_reports_complete_exact_counts() -> None:
    process = run_verifier()
    assert process.returncode == 0, process.stderr
    assert process.stderr == ""
    assert json.loads(process.stdout) == EXPECTED_REPORT


def test_library_verifier_matches_cli_report(verifier_module: ModuleType) -> None:
    assert verifier_module.verify(VERSION_ROOT) == EXPECTED_REPORT


def test_pinned_specification_schema_hash_drift_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verifier_module: ModuleType
) -> None:
    filename, expected_sha256, _ = verifier_module.OPENAPI_VALIDATION_RESOURCE
    source = verifier_module.VALIDATION_RESOURCE_ROOT / filename
    target = tmp_path / filename
    shutil.copyfile(source, target)
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(verifier_module, "VALIDATION_RESOURCE_ROOT", tmp_path)
    with pytest.raises(verifier_module.VerificationError, match="hash mismatch"):
        verifier_module._read_pinned_validation_resource(filename, expected_sha256)


def test_pinned_specification_fifo_replacement_cannot_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verifier_module: ModuleType
) -> None:
    filename, expected_sha256, _ = verifier_module.OPENAPI_VALIDATION_RESOURCE
    source = verifier_module.VALIDATION_RESOURCE_ROOT / filename
    target = tmp_path / filename
    shutil.copyfile(source, target)
    monkeypatch.setattr(verifier_module, "VALIDATION_RESOURCE_ROOT", tmp_path)
    real_open = os.open
    replaced = False

    def replace_with_fifo_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if not replaced and Path(path) == target:
            assert flags & os.O_NONBLOCK
            target.unlink()
            os.mkfifo(target)
            replaced = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_with_fifo_before_open)
    with pytest.raises(verifier_module.VerificationError, match="unsafe pinned"):
        verifier_module._read_pinned_validation_resource(filename, expected_sha256)
    assert replaced


@pytest.mark.parametrize(
    ("operation", "diagnostic"),
    [
        ("fstat", "cannot read pinned validation resource"),
        ("read", "cannot read pinned validation resource"),
        ("close", "cannot close pinned validation resource"),
    ],
)
def test_pinned_resource_io_errors_are_normalized(
    operation: str,
    diagnostic: str,
    monkeypatch: pytest.MonkeyPatch,
    verifier_module: ModuleType,
) -> None:
    filename, expected_sha256, _ = verifier_module.OPENAPI_VALIDATION_RESOURCE
    real_close = os.close

    if operation == "fstat":

        def fail_fstat(descriptor: int) -> os.stat_result:
            raise OSError("injected fstat failure")

        monkeypatch.setattr(os, "fstat", fail_fstat)
    elif operation == "read":

        def fail_read(descriptor: int, length: int) -> bytes:
            raise OSError("injected read failure")

        monkeypatch.setattr(os, "read", fail_read)
    else:

        def fail_close(descriptor: int) -> None:
            real_close(descriptor)
            raise OSError("injected close failure")

        monkeypatch.setattr(os, "close", fail_close)

    with pytest.raises(verifier_module.VerificationError, match=diagnostic):
        verifier_module._read_pinned_validation_resource(filename, expected_sha256)


def test_pinned_resource_io_error_is_machine_readable(
    monkeypatch: pytest.MonkeyPatch,
    verifier_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    filename, _, _ = verifier_module.OPENAPI_VALIDATION_RESOURCE
    real_fstat = os.fstat

    def fail_validation_resource(descriptor: int) -> os.stat_result:
        target = os.readlink(f"/proc/self/fd/{descriptor}")
        if Path(target).name == filename:
            raise OSError("injected resource failure")
        return real_fstat(descriptor)

    monkeypatch.setattr(os, "fstat", fail_validation_resource)
    assert verifier_module.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "cannot read pinned validation resource" in failure["error"]


def test_document_graph_budgets_and_shared_aliases(
    monkeypatch: pytest.MonkeyPatch, verifier_module: ModuleType
) -> None:
    shared = {"leaf": 1}
    walked = list(
        verifier_module._walk({"left": shared, "right": shared}, source="shared")
    )
    assert walked.count(("leaf", 1)) == 2

    monkeypatch.setattr(verifier_module, "MAX_DOCUMENT_GRAPH_DEPTH", 2)
    with pytest.raises(verifier_module.VerificationError, match="depth limit"):
        list(verifier_module._walk({"a": {"b": {"c": 1}}}, source="depth"))

    monkeypatch.setattr(verifier_module, "MAX_DOCUMENT_GRAPH_DEPTH", 128)
    monkeypatch.setattr(verifier_module, "MAX_DOCUMENT_GRAPH_VISITS", 2)
    with pytest.raises(verifier_module.VerificationError, match="visit limit"):
        list(verifier_module._walk({"a": {}, "b": {}}, source="visits"))


@pytest.mark.parametrize(
    ("reference", "diagnostic"),
    [
        ("https://attacker.invalid/schema.json", "remote or malformed"),
        ("http://[", "remote or malformed"),
        ("../../../../../../outside.schema.json", "escapes repository"),
        ("#/definitely-missing", "missing JSON Pointer key"),
        ("article-ast.schema.json#/title", "target is not a schema"),
    ],
)
def test_remote_escape_and_broken_pointer_refs_fail_closed(
    tmp_path: Path, reference: str, diagnostic: str
) -> None:
    root = copy_version(tmp_path)
    mutate_json_reference(root, reference)
    process = run_verifier(root)
    assert process.returncode == 1
    failure = json.loads(process.stderr)
    assert failure["status"] == "FAIL"
    assert diagnostic in failure["error"]
    assert process.stdout == ""


def test_physical_schema_ref_without_canonical_uri_binding_fails(
    tmp_path: Path,
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/schemas/common/publication-snapshot.schema.json"
    target = root / path
    document = json.loads(target.read_bytes())
    assert document["properties"]["renderable_content"]["$ref"] == (
        "article-ast.schema.json"
    )
    document["properties"]["renderable_content"]["$ref"] = (
        "../../schemas/common/article-ast.schema.json"
    )
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    failure = json.loads(process.stderr)
    assert "JSON Schema URI reference does not resolve offline" in failure["error"]
    assert process.stdout == ""


def test_yaml_cycle_fails_with_machine_readable_diagnostic(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "job-state.v1.yaml"
    (root / path).write_text("cycle: &cycle\n  - *cycle\n", encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert process.stdout == ""
    failure = json.loads(process.stderr)
    assert "cyclic document graph" in failure["error"]


def test_duplicate_yaml_key_fails_after_manifest_rebind(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "job-state.v1.yaml"
    (root / path).write_text("document: {}\ndocument: {}\n", encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "duplicate YAML mapping key" in process.stderr


def test_non_rectangular_csv_fails_after_manifest_rebind(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/content/RAOS_06_content_test_matrix_v0.1.csv"
    (root / path).write_text("a,b\nc\n", encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "non-rectangular CSV" in process.stderr


def test_openapi_and_asyncapi_identity_drift_fails(tmp_path: Path) -> None:
    root = copy_version(tmp_path / "openapi")
    openapi_path = "contracts/openapi-public.v0.1.yaml"
    openapi = yaml.safe_load((root / openapi_path).read_bytes())
    openapi["openapi"] = "3.0.0"
    (root / openapi_path).write_text(
        yaml.safe_dump(openapi, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, openapi_path)
    assert run_verifier(root).returncode == 1

    root = copy_version(tmp_path / "asyncapi")
    asyncapi_path = "contracts/asyncapi.v0.4.yaml"
    asyncapi = yaml.safe_load((root / asyncapi_path).read_bytes())
    asyncapi["asyncapi"] = "2.6.0"
    (root / asyncapi_path).write_text(
        yaml.safe_dump(asyncapi, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, asyncapi_path)
    assert run_verifier(root).returncode == 1

    root = copy_version(tmp_path / "missing-dialect")
    openapi_path = "contracts/openapi-internal.v0.4.yaml"
    openapi = yaml.safe_load((root / openapi_path).read_bytes())
    del openapi["jsonSchemaDialect"]
    (root / openapi_path).write_text(
        yaml.safe_dump(openapi, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, openapi_path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "unexpected OpenAPI identity" in process.stderr


def test_openapi_and_asyncapi_structure_drift_fails(tmp_path: Path) -> None:
    root = copy_version(tmp_path / "openapi")
    openapi_path = "contracts/openapi-admin.v0.4.yaml"
    openapi = yaml.safe_load((root / openapi_path).read_bytes())
    openapi["info"]["description"] = []
    (root / openapi_path).write_text(
        yaml.safe_dump(openapi, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, openapi_path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "OpenAPI structure validation failed" in process.stderr

    root = copy_version(tmp_path / "asyncapi")
    asyncapi_path = "contracts/asyncapi.v0.4.yaml"
    asyncapi = yaml.safe_load((root / asyncapi_path).read_bytes())
    asyncapi["info"]["description"] = []
    (root / asyncapi_path).write_text(
        yaml.safe_dump(asyncapi, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, asyncapi_path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "AsyncAPI structure validation failed" in process.stderr

    root = copy_version(tmp_path / "openapi-inline-schema")
    openapi_path = "contracts/openapi-admin.v0.4.yaml"
    openapi = yaml.safe_load((root / openapi_path).read_bytes())
    assert invalidate_first_inline_schema_type(openapi)
    (root / openapi_path).write_text(
        yaml.safe_dump(openapi, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, openapi_path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "OpenAPI structure validation failed" in process.stderr


@pytest.mark.parametrize(
    "reference",
    [
        "#/info/title",
        "#/paths/~1api~1v1~1admin~1me/get/x-raos-safe",
    ],
)
def test_openapi_reference_to_wrong_category_fails_closed(
    tmp_path: Path, reference: str
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/openapi-admin.v0.4.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    assert replace_first_key(document, "$ref", reference)
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "OpenAPI parameter reference targets the wrong category" in process.stderr


def test_openapi_parameter_cannot_reference_response(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/openapi-admin.v0.4.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    parameter = document["paths"]["/api/v1/admin/me"]["get"]["parameters"][0]
    assert parameter["$ref"] == "#/components/parameters/RequestID"
    parameter["$ref"] = "#/components/responses/400"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "OpenAPI parameter reference targets the wrong category" in process.stderr


def test_asyncapi_operation_channel_cannot_reference_message(
    tmp_path: Path,
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/asyncapi.v0.4.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    document["operations"]["send_ai_events"]["channel"]["$ref"] = (
        "#/components/messages/jp_raos_ops_job_requested_v1"
    )
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "AsyncAPI operation channel reference targets the wrong category" in (
        process.stderr
    )


def test_asyncapi_operation_message_cannot_cross_channels(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/asyncapi.v0.4.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    message = document["operations"]["send_ai_events"]["messages"][0]
    message["$ref"] = (
        "#/channels/analytics_events/messages/"
        "jp_raos_analytics_daily_metrics_updated_v1"
    )
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "targets a different channel or category" in process.stderr


def test_asyncapi_non_schema_reference_cycle_fails_closed(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/asyncapi.v0.4.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    names = list(document["channels"]["ai_events"]["messages"])[:2]
    first, second = names
    document["components"]["messages"][first] = {
        "$ref": f"#/components/messages/{second}"
    }
    document["components"]["messages"][second] = {
        "$ref": f"#/components/messages/{first}"
    }
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "cyclic AsyncAPI channel message Reference Object chain" in process.stderr


def test_openapi_boolean_schema_reference_is_accepted(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/openapi-public.v0.1.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    schemas = document["components"]["schemas"]
    schemas["BooleanSchema"] = False
    item_schema = schemas["PublicArticleDocument"]["properties"]["blocks"]["items"]
    assert item_schema["$ref"] == "#/components/schemas/PublicArticleBlock"
    item_schema["$ref"] = "#/components/schemas/BooleanSchema"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    adoption_path = "contracts/ai/canonical-adoption.v0.3.yaml"
    adoption_target = root / adoption_path
    adoption = yaml.safe_load(adoption_target.read_bytes())
    adoption["public_isolation"]["sha256"] = hashlib.sha256(
        target.read_bytes()
    ).hexdigest()
    adoption_target.write_text(
        yaml.safe_dump(adoption, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, adoption_path)
    process = run_verifier(root)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == EXPECTED_REPORT


def test_openapi_schema_reference_cannot_target_boolean_annotation(
    tmp_path: Path,
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/openapi-public.v0.1.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    schemas = document["components"]["schemas"]
    schemas["AnnotatedSchema"] = {"type": "string", "readOnly": True}
    item_schema = schemas["PublicArticleDocument"]["properties"]["blocks"]["items"]
    item_schema["$ref"] = "#/components/schemas/AnnotatedSchema/readOnly"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "OpenAPI schema reference targets the wrong category" in process.stderr


def test_asyncapi_payload_cannot_target_boolean_schema_annotation(
    tmp_path: Path,
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/asyncapi.v0.4.yaml"
    target = root / path
    document = yaml.safe_load(target.read_bytes())
    payload = document["components"]["messages"]["jp_raos_ops_job_requested_v1"][
        "payload"
    ]
    assert payload["$ref"].endswith("jp-raos-ops-job-requested-v1.schema.json")
    payload["$ref"] += "#/allOf/1/properties/data/additionalProperties"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "payload reference targets the wrong category" in process.stderr


@pytest.mark.parametrize("reference", ["#/principles", "#/resources/0"])
def test_embedded_public_schema_ref_rejects_wrong_namespace_and_type(
    reference: str, verifier_module: ModuleType
) -> None:
    repository, documents, _ = load_contract_documents(verifier_module, VERSION_ROOT)
    catalog = documents["contracts/catalogs/resource-contracts.v0.4.yaml"]
    assert isinstance(catalog, dict)
    catalog["public_resources"]["PublicProductCard"]["properties"]["offers"]["items"][
        "$ref"
    ] = reference
    with pytest.raises(
        verifier_module.VerificationError, match="targets the wrong category"
    ):
        verifier_module._verify_embedded_public_resource_schemas(documents, repository)


def test_embedded_public_schema_syntax_drift_fails(
    verifier_module: ModuleType,
) -> None:
    repository, documents, _ = load_contract_documents(verifier_module, VERSION_ROOT)
    catalog = documents["contracts/catalogs/resource-contracts.v0.4.yaml"]
    assert isinstance(catalog, dict)
    catalog["public_resources"]["PublicOffer"]["type"] = 7
    with pytest.raises(
        verifier_module.VerificationError,
        match="invalid embedded public resource schema PublicOffer",
    ):
        verifier_module._verify_embedded_public_resource_schemas(documents, repository)


def test_embedded_public_schema_rejects_non_string_object_key(
    verifier_module: ModuleType,
) -> None:
    repository, documents, _ = load_contract_documents(verifier_module, VERSION_ROOT)
    catalog = documents["contracts/catalogs/resource-contracts.v0.4.yaml"]
    assert isinstance(catalog, dict)
    catalog["public_resources"]["PublicOffer"]["properties"][1] = {"type": "string"}
    with pytest.raises(
        verifier_module.VerificationError, match="non-string JSON object key"
    ):
        verifier_module._verify_embedded_public_resource_schemas(documents, repository)


def test_embedded_public_boolean_schema_root_is_accepted(
    verifier_module: ModuleType,
) -> None:
    repository, documents, _ = load_contract_documents(verifier_module, VERSION_ROOT)
    catalog = documents["contracts/catalogs/resource-contracts.v0.4.yaml"]
    assert isinstance(catalog, dict)
    catalog["public_resources"]["PublicOffer"] = False
    assert verifier_module._verify_embedded_public_resource_schemas(
        documents, repository
    ) == (7, 3)


def test_semantic_schema_reference_rejects_local_markdown(
    verifier_module: ModuleType,
) -> None:
    repository, documents, schemas = load_contract_documents(
        verifier_module, VERSION_ROOT
    )
    catalog = documents["contracts/catalogs/job-catalog.v0.4.yaml"]
    assert isinstance(catalog, dict)
    catalog["jobs"][0]["payload_schema"] = "ai/prompts/PROMPT-AI-SEARCH-INTENT_v1.md"
    with pytest.raises(
        verifier_module.VerificationError,
        match="semantic schema reference targets a non-schema",
    ):
        verifier_module._verify_semantic_references(documents, repository, schemas)


@pytest.mark.parametrize("replacement", [7, None])
def test_semantic_schema_reference_cannot_be_relocated_or_retyped(
    replacement: object, verifier_module: ModuleType
) -> None:
    repository, documents, schemas = load_contract_documents(
        verifier_module, VERSION_ROOT
    )
    catalog = documents["contracts/content/RAOS_06_content_block_catalog_v0.1.yaml"]
    assert isinstance(catalog, dict)
    original = catalog["blocks"][0].pop("schema_path")
    if replacement is not None:
        catalog["blocks"][0]["schema_path"] = replacement
    catalog["unrelated_metadata"] = {"schema_path": original}
    with pytest.raises(
        verifier_module.VerificationError,
        match="wrong type or key|unclassified semantic reference context",
    ):
        verifier_module._verify_semantic_references(documents, repository, schemas)


def test_prompt_output_schema_rejects_local_markdown(
    tmp_path: Path, verifier_module: ModuleType
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/ai/prompts/PROMPT-AI-SEARCH-INTENT_v1.md"
    target = root / path
    content = target.read_text(encoding="utf-8")
    target.write_text(
        content.replace(
            "output_schema: schemas/tasks/ai.search_intent_classification.v1.output.schema.json",
            "output_schema: prompts/PROMPT-AI-POLICY-ASSIST_v1.md",
            1,
        ),
        encoding="utf-8",
    )
    assert target.read_text(encoding="utf-8") != content
    rebind_artifact(root, path)
    repository, documents, schemas = load_contract_documents(verifier_module, root)
    with pytest.raises(
        verifier_module.VerificationError,
        match="prompt output_schema targets a non-schema",
    ):
        verifier_module._verify_prompt_frontmatter(repository, documents, schemas)


def test_registry_hash_and_id_bindings_fail_closed(tmp_path: Path) -> None:
    hash_root = copy_version(tmp_path / "hash")
    registry_path = "contracts/catalogs/schema-registry.v0.4.yaml"
    registry = yaml.safe_load((hash_root / registry_path).read_bytes())
    registry["schemas"][0]["sha256"] = "0" * 64
    (hash_root / registry_path).write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(hash_root, registry_path)
    process = run_verifier(hash_root)
    assert process.returncode == 1
    assert "registry hash mismatch" in process.stderr

    id_root = copy_version(tmp_path / "id")
    registry = yaml.safe_load((id_root / registry_path).read_bytes())
    registry["schemas"][0]["id"] = "https://schemas.raos.local/wrong.schema.json"
    (id_root / registry_path).write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(id_root, registry_path)
    process = run_verifier(id_root)
    assert process.returncode == 1
    assert "registry ID mismatch" in process.stderr


def test_semantic_local_reference_rejects_remote_target(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/catalogs/job-catalog.v0.4.yaml"
    document = yaml.safe_load((root / path).read_bytes())
    assert replace_first_key(
        document, "payload_schema", "https://attacker.invalid/payload.json"
    )
    (root / path).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "remote or malformed reference" in process.stderr


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("contracts/content/RAOS_06_article_type_catalog_v0.1.yaml", "template"),
        ("contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml", "prompt_template"),
        (
            "contracts/catalogs/resource-contracts.v0.4.yaml",
            "grader_metric_binding_source",
        ),
        ("contracts/openapi-admin.v0.4.yaml", "x-raos-canonical-source"),
        ("contracts/catalogs/state-transition-catalog.v0.4.yaml", "x-raos-source"),
        (
            "contracts/content/RAOS_06_content_contract_catalog_v0.1.yaml",
            "path",
        ),
        (
            "contracts/content/fixtures/invalid/expected_results.yaml",
            "path",
        ),
    ],
)
def test_all_declared_semantic_path_classes_reject_remote_targets(
    tmp_path: Path, path: str, key: str
) -> None:
    root = copy_version(tmp_path)
    document = yaml.safe_load((root / path).read_bytes())
    assert replace_first_key(document, key, "https://attacker.invalid/target.yaml")
    (root / path).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "remote or malformed reference" in process.stderr


def test_resource_and_event_semantic_schema_ids_fail_closed(tmp_path: Path) -> None:
    root = copy_version(tmp_path / "resource")
    resource_path = "contracts/catalogs/resource-contracts.v0.4.yaml"
    catalog = yaml.safe_load((root / resource_path).read_bytes())
    entry = next(item for item in catalog["resources"] if "schema_id" in item)
    entry["schema_id"] = "https://schemas.raos.local/unknown.schema.json"
    (root / resource_path).write_text(
        yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, resource_path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "schema identifier is not registered locally" in process.stderr

    root = copy_version(tmp_path / "event")
    event_path = (
        "contracts/schemas/events/jp-raos-ai-release-decision-approved-v1.schema.json"
    )
    event = json.loads((root / event_path).read_bytes())
    event["allOf"][1]["properties"]["dataschema"]["const"] = (
        "https://schemas.raos.local/events/"
        "jp-raos-ai-release-decision-revoked-v1.schema.json"
    )
    (root / event_path).write_text(
        json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_artifact(root, event_path)
    registry_path = "contracts/catalogs/schema-registry.v0.4.yaml"
    registry = yaml.safe_load((root / registry_path).read_bytes())
    registry_entry = next(
        item
        for item in registry["schemas"]
        if item["path"] == event_path.removeprefix("contracts/")
    )
    registry_entry["sha256"] = hashlib.sha256(
        (root / event_path).read_bytes()
    ).hexdigest()
    (root / registry_path).write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, registry_path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "event dataschema ID does not bind its document" in process.stderr


def test_renamed_exact_artifact_inventory_fails_with_json_diagnostic(
    tmp_path: Path,
) -> None:
    root = copy_version(tmp_path)
    original = "contracts/asyncapi.v0.4.yaml"
    renamed = "contracts/asyncapi-renamed.v0.4.yaml"
    (root / original).rename(root / renamed)
    manifest = load_manifest(root)
    entry = next(item for item in manifest["artifacts"] if item["path"] == original)
    entry["path"] = renamed
    manifest["artifacts"].sort(key=lambda item: item["path"])
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    process = run_verifier(root)
    assert process.returncode == 1
    assert process.stdout == ""
    failure = json.loads(process.stderr)
    assert failure["status"] == "FAIL"
    assert "artifact path inventory" in failure["error"]


def test_schema_retrieval_alias_manifest_drift_is_json_failure(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    manifest = load_manifest(root)
    manifest["schema_resolution"]["retrieval_uri_aliases"][0]["retrieval_uri"] = (
        "https://schemas.raos.local/unreviewed.schema.json"
    )
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    process = run_verifier(root)
    assert process.returncode == 1
    assert process.stdout == ""
    failure = json.loads(process.stderr)
    assert "manifest.schema_resolution" in failure["error"]


@pytest.mark.parametrize(
    ("path", "container_key", "entries_key", "hash_key", "diagnostic"),
    [
        (
            "contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml",
            None,
            "tasks",
            "output_schema_sha256",
            "AI task output schema hash mismatch",
        ),
        (
            "contracts/ai/RAOS_05_prompt_registry_v0.1.yaml",
            None,
            "templates",
            "sha256",
            "prompt registry hash mismatch",
        ),
        (
            "contracts/ai/canonical-adoption.v0.3.yaml",
            "frozen_artifacts",
            "catalogs_and_templates",
            "sha256",
            "AI frozen artifact mismatch",
        ),
    ],
)
def test_internal_declared_hash_bindings_fail_closed(
    tmp_path: Path,
    path: str,
    container_key: str | None,
    entries_key: str,
    hash_key: str,
    diagnostic: str,
) -> None:
    root = copy_version(tmp_path)
    document = yaml.safe_load((root / path).read_bytes())
    container = document if container_key is None else document[container_key]
    container[entries_key][0][hash_key] = "0" * 64
    (root / path).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert diagnostic in process.stderr


def test_ai_predecessor_job_state_hash_binding_fails_closed(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    path = "contracts/ai/canonical-adoption.v0.3.yaml"
    document = yaml.safe_load((root / path).read_bytes())
    document["predecessor"]["job_state_sha256"] = "0" * 64
    (root / path).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert "AI predecessor job-state hash mismatch" in process.stderr


@pytest.mark.parametrize(
    ("old", "new", "diagnostic"),
    [
        (
            "RAOS_06_article_type_catalog_v0.1.yaml",
            "https://attacker.invalid/catalog.yaml",
            "remote or malformed reference",
        ),
        (
            "\ufeffrequirement_id,design_id,artifact",
            "\ufeffwrong_id,design_id,artifact",
            "unexpected content traceability CSV contract",
        ),
    ],
)
def test_traceability_csv_header_and_local_refs_fail_closed(
    tmp_path: Path, old: str, new: str, diagnostic: str
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/content/RAOS_06_traceability_matrix_v0.1.csv"
    target = root / path
    content = target.read_text(encoding="utf-8")
    assert old in content
    target.write_text(content.replace(old, new, 1), encoding="utf-8")
    rebind_artifact(root, path)
    process = run_verifier(root)
    assert process.returncode == 1
    assert diagnostic in process.stderr


def test_prompt_frontmatter_reference_rejects_remote_target(
    tmp_path: Path, verifier_module: ModuleType
) -> None:
    root = copy_version(tmp_path)
    path = "contracts/ai/prompts/PROMPT-AI-SEARCH-INTENT_v1.md"
    target = root / path
    content = target.read_text(encoding="utf-8")
    target.write_text(
        content.replace(
            "output_schema: schemas/tasks/ai.search_intent_classification.v1.output.schema.json",
            "output_schema: https://attacker.invalid/schema.json",
            1,
        ),
        encoding="utf-8",
    )
    assert target.read_text(encoding="utf-8") != content
    rebind_artifact(root, path)

    repository, documents, schemas = load_contract_documents(verifier_module, root)
    with pytest.raises(
        verifier_module.VerificationError, match="remote or malformed reference"
    ):
        verifier_module._verify_prompt_frontmatter(repository, documents, schemas)
