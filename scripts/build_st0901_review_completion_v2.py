#!/usr/bin/env python3
"""Generate the deterministic ST-0901 V2 review fixture and provenance."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken, Token


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import secure_generated_publication  # noqa: E402

from raos.adapters.recorded_policy_engine import (  # noqa: E402
    load_recorded_policy_fixture,
)
from raos.adapters.recorded_review_completion import (  # noqa: E402
    load_recorded_review_completion_fixture,
)
from raos.domain.editorial.policy_engine_v2 import (  # noqa: E402
    evaluate_editorial_policy_v2,
)
from raos.domain.publishing.review_completion_v2 import (  # noqa: E402
    PROFILE,
    policy_finding_snapshot_sha256,
)


CONTRACT_PATH: Final = Path(
    "changes/st-0901/contracts/review-completion-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path("changes/st-0901/generated/review-completion-pass.v2.json")
MODULE_PATH: Final = Path("python/raos/generated/review_completion_pass_v2.py")
MANIFEST_PATH: Final = Path("changes/st-0901/runtime-manifest.v2.yaml")
POLICY_FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
GENERATOR_PATH: Final = Path("scripts/build_st0901_review_completion_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024

SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/publishing/review_completion_v2.py"),
    Path("python/raos/ports/review_completion.py"),
    Path("python/raos/application/publishing/review_completion.py"),
    Path("python/raos/adapters/recorded_review_completion.py"),
    Path("changes/st-0901/README-v2.md"),
    Path("changes/st-0901/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0901.md"),
    Path("docs/worklogs/ST-0901.md"),
    Path("tests/st0901_v2/__init__.py"),
    Path("tests/st0901_v2/conftest.py"),
    Path("tests/st0901_v2/test_domain.py"),
    Path("tests/st0901_v2/test_application_adapter.py"),
    Path("tests/st0901_v2/test_generation.py"),
    Path("tests/st0901_v2/test_static_boundary.py"),
)

DEPENDENCY_PATHS: Final = (
    Path("AGENTS.md"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("changes/st-0004/contracts/content/RAOS_06_review_checklist_v0.1.yaml"),
    Path("docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("python/raos/domain/publishing/review_workflow.py"),
    Path("python/raos/domain/publishing/review_assignment_operations.py"),
    Path("python/raos/domain/publishing/review_decision_operations.py"),
    Path("python/raos/domain/editorial/policy_engine_v2.py"),
    Path("python/raos/application/editorial/policy_engine.py"),
    Path("python/raos/adapters/recorded_policy_engine.py"),
    POLICY_FIXTURE_PATH,
    Path("changes/st-0805/runtime-manifest.v2.yaml"),
    SECURE_HELPER_PATH,
)

_ROOT_KEYS: Final = (
    "schema_version",
    "story_id",
    "local_status",
    "classification",
    "profile",
    "runtime",
    "bindings",
    "fixture",
    "approval_gate",
    "completion_boundary",
    "execution_boundary",
    "verification_boundary",
)


class ReviewCompletionGenerationError(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise ReviewCompletionGenerationError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                key_node, deep=deep
            ),
        )
        if type(key) is not str or key in result:
            _fail("CONTRACT_MAPPING_INVALID")
        result[key] = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                value_node, deep=deep
            ),
        )
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _safe_path(root: Path, relative: Path) -> Path:
    if (
        not root.is_absolute()
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("PATH_INVALID")
    candidate = root.joinpath(relative)
    try:
        candidate.relative_to(root)
    except ValueError:
        _fail("PATH_INVALID")
    return candidate


def _read_regular(path: Path) -> bytes:
    try:
        value = path.lstat()
    except OSError:
        _fail("SOURCE_MISSING")
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        _fail("SOURCE_INVALID")
    try:
        payload = path.read_bytes()
    except OSError:
        _fail("SOURCE_INVALID")
    if not payload:
        _fail("SOURCE_INVALID")
    return payload


def _mapping(value: object, keys: tuple[str, ...] | None = None) -> dict[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_MAPPING_INVALID")
    observed = cast(dict[str, object], value)
    if keys is not None and tuple(observed) != keys:
        _fail("CONTRACT_MAPPING_INVALID")
    return observed


def _string(value: object, expected: str | None = None) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("CONTRACT_VALUE_INVALID")
    if expected is not None and value != expected:
        _fail("CONTRACT_VALUE_INVALID")
    return value


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("CONTRACT_VALUE_INVALID")
    return value


def _false(value: object) -> bool:
    if value is not False:
        _fail("AUTHORITY_ESCALATION")
    return False


def _load_contract(root: Path) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, CONTRACT_PATH))
    if len(payload) > 256 * 1024:
        _fail("CONTRACT_TOO_LARGE")
    try:
        tokens = cast(
            Iterable[Token],
            yaml.scan(  # pyright: ignore[reportUnknownMemberType]
                payload.decode("utf-8", errors="strict")
            ),
        )
        for token in tokens:
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("CONTRACT_YAML_FEATURE_FORBIDDEN")
        document = yaml.load(payload, Loader=_UniqueLoader)
    except ReviewCompletionGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    root_mapping = _mapping(document, _ROOT_KEYS)
    if (
        _integer(root_mapping["schema_version"], minimum=2, maximum=2) != 2
        or _string(root_mapping["story_id"], "ST-0901") != "ST-0901"
        or _string(root_mapping["local_status"], "LOCAL_IMPLEMENTATION_COMPLETE")
        != "LOCAL_IMPLEMENTATION_COMPLETE"
        or _string(root_mapping["profile"], PROFILE) != PROFILE
    ):
        _fail("CONTRACT_VALUE_INVALID")
    runtime = _mapping(root_mapping["runtime"])
    for key in (
        "final_approval_authorized",
        "publication_snapshot_authorized",
        "publication_authorized",
        "release_authorized",
        "production_authorized",
    ):
        _false(runtime.get(key))
    execution = _mapping(root_mapping["execution_boundary"])
    if any(value != "FORBIDDEN" for value in execution.values()):
        _fail("EXECUTION_BOUNDARY_INVALID")
    verification = _mapping(root_mapping["verification_boundary"])
    if any(value != "NOT_EXECUTED" for value in verification.values()):
        _fail("VERIFICATION_BOUNDARY_INVALID")
    return root_mapping


def _fixture_bytes(root: Path, contract: dict[str, object]) -> bytes:
    bindings = _mapping(contract["bindings"])
    fixture = _mapping(contract["fixture"])
    assignment = _mapping(fixture["assignment"])
    decision = _mapping(fixture["decision"])
    policy_fixture = _read_regular(_safe_path(root, POLICY_FIXTURE_PATH))
    expected_fixture_sha = _string(bindings["st0805_policy_fixture_sha256"])
    if hashlib.sha256(policy_fixture).hexdigest() != expected_fixture_sha:
        _fail("POLICY_FIXTURE_DRIFT")
    try:
        report = evaluate_editorial_policy_v2(
            load_recorded_policy_fixture(policy_fixture)
        )
        report.require_valid()
        finding_sha = policy_finding_snapshot_sha256(report).value
    except Exception:
        _fail("POLICY_FIXTURE_INVALID")
    if report.article_version_id is None:
        _fail("POLICY_BINDING_DRIFT")
    if (
        report.report_sha256.value != _string(bindings["st0805_policy_report_sha256"])
        or finding_sha != _string(bindings["st0805_finding_snapshot_sha256"])
        or str(report.article_version_id.value)
        != _string(assignment["article_version_id"])
    ):
        _fail("POLICY_BINDING_DRIFT")
    document = {
        "schema_version": 2,
        "profile": PROFILE,
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "fixture_id": _string(fixture["fixture_id"]),
        "assignment": {
            "assignment_id": _string(assignment["assignment_id"]),
            "article_version_id": _string(assignment["article_version_id"]),
            "assigned_by": _string(assignment["assigned_by"]),
            "assigned_to": _string(assignment["assigned_to"]),
            "review_type": _string(assignment["review_type"]),
            "priority": _integer(assignment["priority"], minimum=0, maximum=100),
            "created_at": _string(assignment["created_at"]),
            "started_at": _string(assignment["started_at"]),
        },
        "decision": {
            "decision_id": _string(decision["decision_id"]),
            "audit_event_id": _string(decision["audit_event_id"]),
            "decided_at": _string(decision["decided_at"]),
            "decision": _string(decision["decision"], "APPROVE"),
            "summary": _string(decision["summary"]),
            "checklist_version": _string(bindings["review_checklist_version"]),
            "checklist_sha256": _string(bindings["review_checklist_sha256"]),
            "checklist_status": _string(decision["checklist_status"], "ALL_PASS"),
            "idempotency_key": _string(decision["idempotency_key"]),
        },
        "policy": {
            "fixture_sha256": expected_fixture_sha,
            "report_sha256": report.report_sha256.value,
            "receipt_sequence": _integer(
                bindings["st0805_receipt_sequence"],
                minimum=1,
                maximum=(1 << 53) - 1,
            ),
            "finding_snapshot_sha256": finding_sha,
        },
        "authority": {
            "recorded_synthetic_only": True,
            "final_approval_authorized": False,
            "publication_snapshot_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
        },
    }
    return (
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _module_bytes(fixture: bytes) -> bytes:
    digest = hashlib.sha256(fixture).hexdigest()
    return (
        '"""Owner-generated ST-0901 V2 recorded fixture bytes."""\n\n'
        "from typing import Final\n\n"
        f"REVIEW_COMPLETION_PASS_V2_JSON: Final = {fixture!r}\n"
        "REVIEW_COMPLETION_PASS_V2_SHA256: Final = (\n"
        f'    "{digest}"\n'
        ")\n\n"
        "__all__ = (\n"
        '    "REVIEW_COMPLETION_PASS_V2_JSON",\n'
        '    "REVIEW_COMPLETION_PASS_V2_SHA256",\n'
        ")\n"
    ).encode("utf-8")


def _media_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".md": "text/markdown",
        ".py": "text/x-python",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
    }.get(path.suffix, "application/octet-stream")


def _artifact(root: Path, path: Path, role: str) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, path))
    return {
        "uri": f"repo://{path.as_posix()}",
        "artifact_role": role,
        "media_type": _media_type(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _manifest_bytes(root: Path, fixture: bytes, module: bytes) -> bytes:
    source_artifacts = [
        *(_artifact(root, path, "OWNER_SOURCE") for path in SOURCE_PATHS),
        *(
            _artifact(root, path, "CANONICAL_OR_DEPENDENCY_INPUT")
            for path in DEPENDENCY_PATHS
        ),
    ]
    generated = [
        {
            "uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "artifact_role": "GENERATED_RECORDED_FIXTURE",
            "media_type": "application/json",
            "bytes": len(fixture),
            "sha256": hashlib.sha256(fixture).hexdigest(),
        },
        {
            "uri": f"repo://{MODULE_PATH.as_posix()}",
            "artifact_role": "GENERATED_RUNTIME_MODULE",
            "media_type": "text/x-python",
            "bytes": len(module),
            "sha256": hashlib.sha256(module).hexdigest(),
        },
    ]
    document = {
        "schema_version": 2,
        "story_id": "ST-0901",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_RECORDED_REVIEW_COMPLETION_MANIFEST_V2",
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": ".venv/bin/python scripts/build_st0901_review_completion_v2.py",
            "check_command": (
                ".venv/bin/python scripts/build_st0901_review_completion_v2.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "secure_publication_helper_sha256": hashlib.sha256(
                _read_regular(_safe_path(root, SECURE_HELPER_PATH))
            ).hexdigest(),
        },
        "authority": {
            "final_approval_authorized": False,
            "publication_snapshot_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "formal_tst_011_status": "NOT_EXECUTED",
            "formal_tst_012_status": "NOT_EXECUTED",
            "formal_tst_020_status": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st0901-v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    root = Path(os.path.abspath(root))
    contract = _load_contract(root)
    fixture = _fixture_bytes(root, contract)
    try:
        step = load_recorded_review_completion_fixture(
            fixture,
            policy_fixture=_read_regular(_safe_path(root, POLICY_FIXTURE_PATH)),
        )
        step.require_valid()
    except Exception:
        _fail("GENERATED_FIXTURE_VALIDATION_FAILED")
    module = _module_bytes(fixture)
    manifest = _manifest_bytes(root, fixture, module)
    expected = (
        (FIXTURE_PATH, fixture),
        (MODULE_PATH, module),
        (MANIFEST_PATH, manifest),
    )
    if check:
        for path, payload in expected:
            if _read_regular(_safe_path(root, path)) != payload:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    _replace_generated(
        tuple((_safe_path(root, path), payload) for path, payload in expected)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    try:
        arguments, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        build(check=arguments.check)
    except Exception:
        print("ST-0901 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0901 V2 runtime checked"
        if arguments.check
        else "ST-0901 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
