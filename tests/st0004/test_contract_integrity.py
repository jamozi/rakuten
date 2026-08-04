"""Hash, inventory, reference and provenance integrity for ST-0004."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from zipfile import ZipFile

from jsonschema import Draft202012Validator
import yaml

from scripts import build_st0004_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0004"
CONTRACTS_ROOT = BUNDLE_ROOT / "contracts"
PREDECESSOR_ROOT = REPOSITORY_ROOT / "changes" / "st-0003"
MANIFEST_PATH = BUNDLE_ROOT / "manifest.yaml"
EXPECTED_INPUTS = {
    "docs/upstream/RAOS_06_content_design_package_v0.1.zip":
        "4cc7e0802b2dfd7d01762aa73190caa746b6f2490c2411804c564f7ce02803ec",
    "docs/upstream/patches/RAOS_06_001_data_alignment_patch_v0.1.sql":
        "69ac7925c206862bea5244d6831a65eaa0b3b5bc6cf9defde8a3e6a3a654ed3e",
    "docs/upstream/patches/RAOS_06_002_api_alignment_patch_v0.1.yaml":
        "4390ea3a638eb70217ea023dbe0d76d3167a436d0fd1cfc9ea40ba2659bfa573",
    "docs/upstream/patches/RAOS_06_003_ai_alignment_patch_v0.1.yaml":
        "89fe29c6182dc38b40d96379a65715fada43b74e93b5715eb3320b6a50285c1e",
}
EXPECTED_SOURCE_PATHS = {
    "scripts/build_st0004_revision.py",
    "changes/st-0004/README.md",
    *(f"changes/st-0004/database/{name}" for name in revision.MIGRATION_PHASES),
    f"changes/st-0004/database/{revision.GUARDED_DOWNGRADE}",
    f"changes/st-0004/database/{revision.FORWARD_RECOVERY}",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def load_document(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def assert_safe_repo_file(relative: str) -> Path:
    logical = PurePosixPath(relative)
    assert relative and not logical.is_absolute() and "\\" not in relative
    assert all(part not in {"", ".", ".."} for part in logical.parts)
    path = REPOSITORY_ROOT.joinpath(*logical.parts)
    assert path.is_file() and not path.is_symlink(), relative
    assert path.resolve().is_relative_to(REPOSITORY_ROOT.resolve()), relative
    return path


def verify_artifact_entries(entries: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    folded: set[str] = set()
    for entry in entries:
        path = entry["path"]
        assert isinstance(path, str) and path.casefold() not in folded
        folded.add(path.casefold())
        actual = assert_safe_repo_file(path)
        assert entry["bytes"] == actual.stat().st_size
        assert entry["sha256"] == digest(actual)
        paths.add(path)
    return paths


def iter_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            yield ref
        for child in value.values():
            yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)


def resolve_pointer(document: Any, fragment: str) -> Any:
    if not fragment:
        return document
    assert fragment.startswith("/"), fragment
    value = document
    for raw in fragment.removeprefix("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def equal_object_count(value: Any, target: dict[str, Any]) -> int:
    count = int(isinstance(value, dict) and value == target)
    if isinstance(value, dict):
        count += sum(equal_object_count(child, target) for child in value.values())
    elif isinstance(value, list):
        count += sum(equal_object_count(child, target) for child in value)
    return count


def bundle_security_copy_count(root: Path, target: dict[str, Any]) -> int:
    paths = [root / "manifest.yaml"]
    paths.extend(
        path
        for path in (root / "contracts").rglob("*")
        if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}
    )
    return sum(equal_object_count(load_document(path), target) for path in paths)


def test_manifest_identity_inputs_archive_and_formal_counts_are_exact() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    assert manifest["document"] == {
        "id": "RAOS-CONTENT-REVISION-001",
        "version": "0.4",
        "story_id": "ST-0004",
        "status": "IMPLEMENTATION_CANDIDATE",
        "generated_by": "scripts/build_st0004_revision.py",
    }
    assert manifest["provenance"]["requirement_ids"] == ["FR-007", "FR-010"]
    assert manifest["provenance"]["decision_ids"] == ["INT-DEC-005"]
    assert manifest["provenance"]["supporting_decision_ids"] == ["INT-DEC-006"]
    assert {item["path"]: item["sha256"] for item in manifest["inputs"]} == EXPECTED_INPUTS
    for path, expected in EXPECTED_INPUTS.items():
        assert digest(assert_safe_repo_file(path)) == expected

    archive = manifest["archive_validation"]
    assert archive["regular_member_count"] == 111
    assert archive["declared_checksum_count"] == 110
    assert all(
        archive[key] is True
        for key in (
            "declared_equals_regular_members_excluding_inventory",
            "all_member_hashes_verified",
            "standalone_proposals_equal_both_archive_copies",
            "path_casefold_traversal_symlink_checks",
        )
    )
    with ZipFile(revision.CONTENT_PACKAGE) as package:
        files = revision.checked_archive_files(package)
        checksum = revision.CONTENT_CHECKSUM_MEMBER.removeprefix(revision.CONTENT_ROOT)
        declared = revision.parse_checksum_inventory(package.read(files[checksum]))
        assert len(files) == 111 and len(declared) == 110
        assert set(declared) == set(files) - {checksum}
        for relative, expected in declared.items():
            assert sha256(package.read(files[relative])).hexdigest() == expected


def test_manifest_source_and_generated_inventories_are_complete_and_hashed() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    assert verify_artifact_entries(manifest["source_artifacts"]) == EXPECTED_SOURCE_PATHS
    generated = manifest["generated_artifacts"]
    assert manifest["generated_artifact_count"] == len(generated)
    listed = verify_artifact_entries(generated)
    actual = {"changes/st-0004/job-state.v1.yaml"}
    actual.update(
        f"changes/st-0004/{path.relative_to(BUNDLE_ROOT).as_posix()}"
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file()
    )
    assert listed == actual


def test_predecessor_manifest_inputs_sources_and_generated_are_all_live_and_hashed() -> None:
    predecessor_path = PREDECESSOR_ROOT / "manifest.yaml"
    assert digest(predecessor_path) == revision.PREDECESSOR_MANIFEST_HASH
    manifest = load_yaml(predecessor_path)
    assert len(manifest["inputs"]) == 5
    for entry in manifest["inputs"]:
        assert digest(assert_safe_repo_file(entry["path"])) == entry["sha256"]
    verify_artifact_entries(manifest["source_artifacts"])
    generated = verify_artifact_entries(manifest["generated_artifacts"])
    actual = {"changes/st-0003/job-state.v1.yaml"}
    actual.update(
        f"changes/st-0003/{path.relative_to(PREDECESSOR_ROOT).as_posix()}"
        for path in PREDECESSOR_ROOT.joinpath("contracts").rglob("*")
        if path.is_file()
    )
    assert generated == actual
    assert manifest["generated_artifact_count"] == len(generated)


def test_every_local_or_registry_ref_resolves_without_escaping_contracts() -> None:
    documents = {
        path.resolve(): load_document(path)
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}
    }
    ids = {
        document["$id"].split("#", 1)[0]: (path, document)
        for path, document in documents.items()
        if isinstance(document.get("$id"), str)
    }
    for source, document in documents.items():
        for ref in iter_refs(document):
            base, _, fragment = ref.partition("#")
            if base.startswith(("http://", "https://")):
                assert base in ids, f"unregistered remote ref {ref} in {source}"
                _, target = ids[base]
            elif base:
                target_path = (source.parent / base).resolve()
                assert target_path.is_relative_to(CONTRACTS_ROOT.resolve()), ref
                assert target_path in documents, f"missing local ref {ref} in {source}"
                target = documents[target_path]
            else:
                target = document
            resolve_pointer(target, fragment)


def test_schema_registry_is_complete_unique_and_hash_bound() -> None:
    registry = load_yaml(CONTRACTS_ROOT / "catalogs" / "schema-registry.v0.4.yaml")
    entries = registry["schemas"]
    assert registry["schema_count"] == len(entries)
    assert len({entry["path"].casefold() for entry in entries}) == len(entries)
    assert len({entry["id"] for entry in entries}) == len(entries)
    actual = {
        path.relative_to(CONTRACTS_ROOT).as_posix(): path
        for root in (
            CONTRACTS_ROOT / "schemas",
            CONTRACTS_ROOT / "content" / "schemas",
            CONTRACTS_ROOT / "ai" / "schemas",
        )
        for path in root.rglob("*.json")
    }
    assert {entry["path"] for entry in entries} == set(actual)
    for entry in entries:
        path = actual[entry["path"]]
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert entry["id"] == schema["$id"]
        assert entry["sha256"] == digest(path)


def test_public_job_state_and_legacy_article_ast_are_frozen() -> None:
    assert digest(CONTRACTS_ROOT / "openapi-public.v0.1.yaml") == revision.PUBLIC_OPENAPI_HASH
    assert digest(BUNDLE_ROOT / "job-state.v1.yaml") == revision.JOB_STATE_HASH
    legacy = "schemas/common/article-ast.schema.json"
    assert (CONTRACTS_ROOT / legacy).read_bytes() == (
        PREDECESSOR_ROOT / "contracts" / legacy
    ).read_bytes()
    assert (CONTRACTS_ROOT / legacy).read_bytes() != (
        CONTRACTS_ROOT / "content" / "schemas" / "content-ast.schema.json"
    ).read_bytes()


def test_ai_execution_security_has_sixteen_named_unchanged_contract_copies() -> None:
    expected = load_yaml(PREDECESSOR_ROOT / "manifest.yaml")["database_execution_security"]
    candidate = load_yaml(MANIFEST_PATH)
    assert candidate["database_execution_security"] == expected
    evaluation_run = load_document(
        CONTRACTS_ROOT
        / "schemas"
        / "ai-governance"
        / "evaluation-run.v1.schema.json"
    )
    catalog = load_yaml(CONTRACTS_ROOT / "catalogs" / "resource-contracts.v0.4.yaml")
    resources = {
        resource["name"]: resource
        for resource in catalog["resources"]
        if isinstance(resource, dict) and isinstance(resource.get("name"), str)
    }
    internal = load_yaml(CONTRACTS_ROOT / "openapi-internal.v0.4.yaml")
    admin = load_yaml(CONTRACTS_ROOT / "openapi-admin.v0.4.yaml")
    operations = {
        operation["operationId"]: operation
        for path_item in admin["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and isinstance(operation.get("operationId"), str)
    }
    asyncapi = load_yaml(CONTRACTS_ROOT / "asyncapi.v0.4.yaml")
    event_ref = asyncapi["components"]["messages"][
        "jp_raos_ai_evaluation_completed_v2"
    ]["payload"]["$ref"]
    event = load_document((CONTRACTS_ROOT / event_ref).resolve())

    copies = (
        evaluation_run["x-raos-completion-execution-security-invariants"],
        evaluation_run["x-raos-completion-evidence-invariants"]["execution_security"],
        resources["EvaluationRun"]["x-raos-completion-execution-security-invariants"],
        resources["EvaluationRun"]["x-raos-completion-evidence-invariants"][
            "execution_security"
        ],
        resources["EvaluationResult"]["x-raos-completion-evidence-invariants"][
            "execution_security"
        ],
        catalog["evaluation_completion_execution_security_invariants"],
        catalog["evaluation_run_completion_evidence_invariants"]["execution_security"],
        internal["x-raos-ai-governance"]["database_execution_security"],
        candidate["database_execution_security"],
        operations["AI-108"]["x-raos-completion-execution-security-invariants"],
        operations["AI-109"]["x-raos-completion-execution-security-invariants"],
        admin["x-raos-ai-governance"][
            "evaluation_completion_execution_security_invariants"
        ],
        admin["components"]["schemas"]["EvaluationResult"][
            "x-raos-completion-evidence-invariants"
        ]["execution_security"],
        operations["AI-108"]["x-raos-completion-evidence-invariants"][
            "execution_security"
        ],
        admin["x-raos-ai-governance"][
            "evaluation_run_completion_evidence_invariants"
        ]["execution_security"],
        event["allOf"][1]["properties"]["data"][
            "x-raos-completion-evidence-invariants"
        ]["execution_security"],
    )
    assert len(copies) == 16
    assert all(copy == expected for copy in copies)
    assert expected["worker_direct_execute"]["policy"] == "REVOKED"
    assert expected["public_execute"]["policy"] == "REVOKED"
    assert len(expected["evaluation_run_trigger_guards"]) == 3
    assert "completion_trigger_wrapper" not in json.dumps(expected, sort_keys=True)
