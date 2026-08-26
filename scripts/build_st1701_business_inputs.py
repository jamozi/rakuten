#!/usr/bin/env python3
"""Build semantic ST-1701 decision models without approval-hash authority."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml"
)
DECISION_PACKAGE_PATH: Final = Path(
    "changes/st-1701/contracts/mvp-business-decision-package.v1.yaml"
)
REFERENCE_PATH: Final = Path(
    "changes/st-1701/generated/unresolved-mvp-business-inputs.v1.json"
)
DECISION_READ_MODEL_PATH: Final = Path(
    "changes/st-1701/generated/mvp-business-decision-package.v1.json"
)
CANONICAL_REVISION_REQUEST_PATH: Final = Path(
    "changes/st-1701/generated/canonical-revision-request.v1.md"
)
GOLD_VALIDATION_PATH: Final = Path(
    "changes/st-1701/generated/gold-evidence-validation.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1701/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1701_business_inputs.py")
SOURCE_PATHS: Final = (CONTRACT_PATH, DECISION_PACKAGE_PATH, GENERATOR_PATH)
GENERATED_CONTENT_PATHS: Final = (
    REFERENCE_PATH,
    DECISION_READ_MODEL_PATH,
    CANONICAL_REVISION_REQUEST_PATH,
    GOLD_VALIDATION_PATH,
)
GENERATED_PATHS: Final = (*GENERATED_CONTENT_PATHS, MANIFEST_PATH)
MAX_SOURCE_BYTES: Final = 2 * 1024 * 1024


class BusinessInputBuildError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise BusinessInputBuildError(code)


def _read_regular(root: Path, relative: Path, *, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    path = root / relative
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 1 <= metadata.st_size <= maximum
        ):
            _fail("INPUT_INVALID")
        content = path.read_bytes()
    except BusinessInputBuildError:
        raise
    except OSError:
        _fail("INPUT_INVALID")
    if len(content) != metadata.st_size:
        _fail("INPUT_INVALID")
    return content


def _load_yaml(root: Path, relative: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(_read_regular(root, relative))
    except BusinessInputBuildError:
        raise
    except (UnicodeError, yaml.YAMLError):
        _fail("CONTRACT_INVALID")
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("CONTRACT_INVALID")
    return cast(dict[str, Any], value)


def _repo_path(uri: object) -> Path:
    if type(uri) is not str or not uri.startswith("repo://"):
        _fail("CANONICAL_INPUT_INVALID")
    relative = Path(uri.removeprefix("repo://"))
    if relative.is_absolute() or ".." in relative.parts:
        _fail("CANONICAL_INPUT_INVALID")
    return relative


def _verify_canonical_sources(root: Path, contract: dict[str, Any]) -> None:
    sources = contract.get("sources")
    if type(sources) is not list or len(sources) != 6:
        _fail("CANONICAL_INPUT_INVALID")
    for raw in sources:
        if type(raw) is not dict:
            _fail("CANONICAL_INPUT_INVALID")
        relative = _repo_path(raw.get("uri"))
        digest = raw.get("sha256")
        if (
            not relative.as_posix().startswith("docs/canonical/")
            or type(digest) is not str
            or hashlib.sha256(_read_regular(root, relative)).hexdigest() != digest
        ):
            _fail("CANONICAL_INPUT_DRIFT")


def validate_contract(contract: dict[str, Any], root: Path = REPO_ROOT) -> None:
    required = {
        "document",
        "sources",
        "predecessor_binding",
        "scope",
        "decisions",
        "business_inputs",
        "safe_defaults",
        "activation",
        "gates",
        "action_boundary",
        "evidence_boundary",
        "downstream_boundary",
    }
    if set(contract) != required:
        _fail("CONTRACT_INVALID")
    document = contract["document"]
    predecessor = contract["predecessor_binding"]
    actions = contract["action_boundary"]
    if not all(type(value) is dict for value in (document, predecessor, actions)):
        _fail("CONTRACT_INVALID")
    if (
        document.get("story_id") != "ST-1701"
        or document.get("executable") is not False
        or predecessor.get("owner_id") != "build_st0006_decision_gates"
        or predecessor.get("owner_version") != "2"
        or predecessor.get("binding") != "SEMANTIC_OWNER_GRAPH"
        or any(
            actions.get(key) != "FORBIDDEN"
            for key in (
                "external_actions",
                "external_publication",
                "staging",
                "release",
                "production",
            )
        )
        or any(value != 0 for value in actions.get("action_counts", {}).values())
    ):
        _fail("SAFETY_BOUNDARY_DRIFT")
    _verify_canonical_sources(root, contract)


def validate_decision_package(package: dict[str, Any]) -> None:
    required = {
        "document",
        "development_context",
        "status_boundary",
        "record_status_model",
        "canonical_truth_boundary",
        "scoped_decisions",
        "informational_cross_story_owner_inputs",
        "implementation_boundary",
        "evidence_boundary",
        "action_boundary",
    }
    if set(package) != required:
        _fail("DECISION_PACKAGE_INVALID")
    document = package["document"]
    context = package["development_context"]
    status = package["status_boundary"]
    evidence = package["evidence_boundary"]
    actions = package["action_boundary"]
    if not all(type(value) is dict for value in (document, context, status, evidence, actions)):
        _fail("DECISION_PACKAGE_INVALID")
    if (
        document.get("version") != "2.0.0"
        or document.get("status") != "LOCAL_DECISION_MODEL"
        or context.get("mode") != "CONTINUOUS_REVERSIBLE_REPOSITORY_WORK"
        or status.get("gate_state") != "BLOCKED"
        or evidence.get("production") != "NOT_EXECUTED"
        or actions.get("external_actions") != "NOT_AUTHORIZED"
        or actions.get("publication") != "NOT_AUTHORIZED"
        or actions.get("production") != "NOT_AUTHORIZED"
    ):
        _fail("SAFETY_BOUNDARY_DRIFT")
    serialized = yaml.safe_dump(package, allow_unicode=True, sort_keys=False).lower()
    if any(
        marker in serialized
        for marker in (
            "handoff_sha256",
            "approval_sha256",
            "approved_source_contract_sha256",
            "base_commit",
            "implementation_authority:",
        )
    ):
        _fail("GOVERNANCE_BINDING_FORBIDDEN")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = _load_yaml(root, CONTRACT_PATH)
    validate_contract(contract, root)
    return contract


def load_decision_package(root: Path = REPO_ROOT) -> dict[str, Any]:
    package = _load_yaml(root, DECISION_PACKAGE_PATH)
    validate_decision_package(package)
    return package


def reference_document(contract: dict[str, Any]) -> dict[str, object]:
    return copy.deepcopy(contract)


def decision_read_model(
    package: dict[str, Any],
    _contract: dict[str, Any] | None = None,
    _root: Path = REPO_ROOT,
) -> dict[str, object]:
    return copy.deepcopy(package)


def gold_evidence_validation_document(
    _root: Path = REPO_ROOT,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "story_id": "ST-1701",
        "status": "EXTERNAL_EVIDENCE_NOT_EXECUTED",
        "generator_owner_id": "build_st1701_business_inputs",
        "generator_version": 2,
        "eligible_for_canonical_revision": False,
        "unexecuted": ["OD-006_DOMAIN_EVIDENCE", "TST-032", "PRODUCTION"],
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _revision_request_bytes() -> bytes:
    return (
        "# ST-1701 canonical revision request\n\n"
        "Status: NOT_READY\n\n"
        "The local decision model is implemented. OD-006 external domain evidence "
        "and TST-032 remain unexecuted; no canonical status transition is requested.\n"
    ).encode("utf-8")


def render(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    package = load_decision_package(root)
    outputs = {
        REFERENCE_PATH: _json_bytes(reference_document(contract)),
        DECISION_READ_MODEL_PATH: _json_bytes(decision_read_model(package, contract)),
        CANONICAL_REVISION_REQUEST_PATH: _revision_request_bytes(),
        GOLD_VALIDATION_PATH: _json_bytes(gold_evidence_validation_document(root)),
    }
    manifest = {
        "schema_version": 2,
        "generator_owner_id": "build_st1701_business_inputs",
        "generator_version": 2,
        "story_ids": ["ST-1701"],
        "semantic_inputs": [
            {
                "uri": f"repo://{CONTRACT_PATH.as_posix()}",
                "semantic_id": "st1701-unresolved-business-inputs",
                "semantic_version": "1.0.0",
            },
            {
                "uri": f"repo://{DECISION_PACKAGE_PATH.as_posix()}",
                "semantic_id": "st1701-business-decision-model",
                "semantic_version": "2.0.0",
            },
        ],
        "canonical_inputs": [copy.deepcopy(row) for row in contract["sources"]],
        "outputs": [
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for path, content in outputs.items()
        ],
    }
    outputs[MANIFEST_PATH] = yaml.safe_dump(
        manifest, allow_unicode=True, sort_keys=False
    ).encode("utf-8")
    return outputs


def _write_atomic(root: Path, relative: Path, content: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.next")
    try:
        with temporary.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    expected = render(root)
    if check:
        for relative, content in expected.items():
            try:
                current = (root / relative).read_bytes()
            except OSError:
                _fail("GENERATED_DRIFT")
            if current != content:
                _fail("GENERATED_DRIFT")
        return
    for relative, content in expected.items():
        _write_atomic(root, relative, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        build(check=arguments.check)
    except BusinessInputBuildError as error:
        print(f"ERROR code={error.code}", file=sys.stderr)
        return 1
    print("ST-1701 business inputs checked" if arguments.check else "ST-1701 business inputs generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
