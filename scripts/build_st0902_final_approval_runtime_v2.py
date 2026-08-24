#!/usr/bin/env python3
"""Generate the deterministic ST-0902 V2 final-approval fixture and provenance."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn, cast
from uuid import UUID

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken, Token


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import secure_generated_publication  # noqa: E402

from raos.adapters.recorded_final_approval import (  # noqa: E402
    load_recorded_final_approval_fixture,
)
from raos.adapters.recorded_policy_engine import (  # noqa: E402
    load_recorded_policy_fixture,
)
from raos.adapters.recorded_review_completion import (  # noqa: E402
    load_recorded_review_completion_fixture,
)
from raos.domain.editorial.policy_engine_v2 import (  # noqa: E402
    PolicyEvaluationRecordReceiptV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.publishing.final_approval import (  # noqa: E402
    PROFILE,
    FinalApprovalFindingSnapshotV2,
    coverage_receipt_sha256,
)
from raos.domain.publishing.review_completion_v2 import (  # noqa: E402
    policy_finding_snapshot_sha256,
    policy_receipt_sha256,
)
from raos.domain.publishing.review_workflow import (  # noqa: E402
    ArticleVersionId,
    UtcTimestamp,
)

CONTRACT_PATH: Final = Path("changes/st-0902/contracts/final-approval-runtime.v2.yaml")
FIXTURE_PATH: Final = Path("changes/st-0902/generated/final-approval-pass.v2.json")
MODULE_PATH: Final = Path("python/raos/generated/final_approval_pass_v2.py")
MANIFEST_PATH: Final = Path("changes/st-0902/runtime-manifest.v2.yaml")
POLICY_FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
REVIEW_FIXTURE_PATH: Final = Path(
    "changes/st-0901/generated/review-completion-pass.v2.json"
)
GENERATOR_PATH: Final = Path("scripts/build_st0902_final_approval_runtime_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024

SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/publishing/final_approval.py"),
    Path("python/raos/ports/final_approval.py"),
    Path("python/raos/application/publishing/final_approval.py"),
    Path("python/raos/adapters/recorded_final_approval.py"),
    Path("changes/st-0902/README-v2.md"),
    Path("changes/st-0902/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0902.md"),
    Path("docs/worklogs/ST-0902.md"),
    Path("tests/st0902_v2/__init__.py"),
    Path("tests/st0902_v2/conftest.py"),
    Path("tests/st0902_v2/test_domain.py"),
    Path("tests/st0902_v2/test_application_adapter.py"),
    Path("tests/st0902_v2/test_generation.py"),
    Path("tests/st0902_v2/test_static_boundary.py"),
)

DEPENDENCY_PATHS: Final = (
    Path("AGENTS.md"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md"),
    Path(
        "docs/upstream/key_documents/RAOS_06_content_editorial_evidence_design_v0.1.md"
    ),
    Path("python/raos/domain/evidence/claim_evidence.py"),
    Path("changes/st-0605/contracts/claim-evidence-runtime.v1.yaml"),
    Path("changes/st-0605/runtime-manifest.v1.yaml"),
    Path("python/raos/domain/editorial/policy_engine_v2.py"),
    Path("python/raos/adapters/recorded_policy_engine.py"),
    POLICY_FIXTURE_PATH,
    Path("changes/st-0805/contracts/policy-runtime.v2.yaml"),
    Path("changes/st-0805/runtime-manifest.v2.yaml"),
    Path("python/raos/domain/publishing/review_completion_v2.py"),
    Path("python/raos/adapters/recorded_review_completion.py"),
    REVIEW_FIXTURE_PATH,
    Path("changes/st-0901/contracts/review-completion-runtime.v2.yaml"),
    Path("changes/st-0901/runtime-manifest.v2.yaml"),
    Path("changes/st-0902/README.md"),
    Path("changes/st-0902/contracts/final-approval-reference-plan.v1.yaml"),
    Path("changes/st-0902/generated/final-approval-reference-plan.v1.json"),
    Path("changes/st-0902/manifest.yaml"),
    Path("scripts/build_st0902_final_approval_reference_plan.py"),
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
_FIXTURE_KEYS: Final = ("fixture_id", "approval", "actor")
_APPROVAL_KEYS: Final = (
    "approval_id",
    "audit_event_id",
    "approved_at",
    "reason",
    "idempotency_key",
    "article_author_id",
    "last_editor_id",
    "site_id",
    "finding_snapshot_captured_at",
    "open_blocking_finding_ids",
)
_ACTOR_KEYS: Final = (
    "principal_id",
    "site_id",
    "subject_kind",
    "subject_status",
    "role",
    "mfa_state",
    "step_up_state",
    "reauthenticated_at",
)
_BINDING_KEYS: Final = (
    "st0805_policy_fixture_uri",
    "st0805_policy_fixture_sha256",
    "st0805_policy_report_sha256",
    "st0805_policy_receipt_sequence",
    "st0805_policy_receipt_sha256",
    "st0605_coverage_report_sha256",
    "st0605_coverage_receipt_sha256",
    "st0901_review_fixture_uri",
    "st0901_review_fixture_sha256",
    "st0901_review_result_sha256",
    "st0901_review_record_sha256",
    "st0901_review_decision_sha256",
    "policy_finding_snapshot_sha256",
    "finding_clearance_sha256",
    "article_version_id",
    "article_version_no",
    "article_body_sha256",
    "canonical_ast_sha256",
)
_EXPECTED_RUNTIME: Final = {
    "executable": True,
    "provider_mode": "RECORDED_SYNTHETIC_ONLY",
    "repository_write": False,
    "process_local_recording_only": True,
    "local_human_final_approval_record_supported": True,
    "real_final_approval_authorized": False,
    "publication_snapshot_authorized": False,
    "publication_authorized": False,
    "release_authorized": False,
    "production_authorized": False,
}
_EXPECTED_APPROVAL_GATE: Final[dict[str, object]] = {
    "exact_article_version_and_hashes_required": True,
    "exact_st0605_coverage_report_receipt_required": True,
    "coverage_status_required": "PASS",
    "major_claim_coverage_required": True,
    "all_verifiable_claim_coverage_required": True,
    "exact_st0805_policy_report_receipt_required": True,
    "policy_status_required": "LOCAL_EVALUATED",
    "policy_findings_required": [],
    "legacy_policy_findings_required": [],
    "waiver_evaluations_required": [],
    "local_eligibility_required": True,
    "quality_threshold_required": True,
    "quality_floors_required": True,
    "policy_rules_required": True,
    "zero_tolerance_clear_required": True,
    "quality_gates_required": True,
    "predecessors_available_required": True,
    "exact_st0901_completed_approve_required": True,
    "complete_finding_snapshot_required": True,
    "open_blocking_findings_required": [],
    "blocking_waiver_supported": False,
    "active_human_required": True,
    "managing_editor_required": True,
    "site_scope_required": True,
    "mfa_required": True,
    "recorded_step_up_required": True,
    "recorded_step_up_max_age_seconds": 300,
    "author_approver_separation_required": True,
    "editor_approver_separation_required": True,
    "reviewer_approver_separation_required": True,
}
_EXPECTED_COMPLETION_BOUNDARY: Final = {
    "immutable_gate_bundle": True,
    "immutable_local_final_approval_record": True,
    "immutable_local_audit_artifact": True,
    "local_idempotency_receipt": True,
    "durable_transaction": False,
    "public_api": False,
    "database": False,
    "event_bus": False,
    "outbox": False,
    "publication_snapshot_effect": False,
}
_EXPECTED_EXECUTION_BOUNDARY: Final = {
    "network": "FORBIDDEN",
    "credential": "FORBIDDEN",
    "provider": "FORBIDDEN",
    "external_identity_lookup": "FORBIDDEN",
    "public_api_write": "FORBIDDEN",
    "database_write": "FORBIDDEN",
    "event_emit": "FORBIDDEN",
    "publication_snapshot_mutation": "FORBIDDEN",
    "publication": "FORBIDDEN",
    "staging": "FORBIDDEN",
    "release": "FORBIDDEN",
    "production": "FORBIDDEN",
}
_EXPECTED_VERIFICATION_BOUNDARY: Final = {
    "TST-012": "NOT_EXECUTED",
    "TST-021": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


class FinalApprovalGenerationError(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise FinalApprovalGenerationError(code) from None


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
        metadata = path.lstat()
    except OSError:
        _fail("SOURCE_MISSING")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
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


def _sha(value: object) -> str:
    observed = _string(value)
    if len(observed) != 64 or any(item not in "0123456789abcdef" for item in observed):
        _fail("CONTRACT_VALUE_INVALID")
    return observed


def _instant(value: object) -> UtcTimestamp:
    text = _string(value)
    if not text.endswith("Z"):
        _fail("CONTRACT_VALUE_INVALID")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
        if parsed.tzinfo is not timezone.utc or parsed.fold:
            _fail("CONTRACT_VALUE_INVALID")
        return UtcTimestamp(parsed)
    except FinalApprovalGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_VALUE_INVALID")


def load_contract(root: Path) -> dict[str, object]:
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
    except FinalApprovalGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    contract = _mapping(document, _ROOT_KEYS)
    if (
        _integer(contract["schema_version"], minimum=2, maximum=2) != 2
        or _string(contract["story_id"], "ST-0902") != "ST-0902"
        or _string(contract["local_status"], "LOCAL_IMPLEMENTATION_COMPLETE")
        != "LOCAL_IMPLEMENTATION_COMPLETE"
        or _string(
            contract["classification"],
            "LOCAL_EXECUTABLE_RECORDED_HUMAN_FINAL_APPROVAL_V2",
        )
        != "LOCAL_EXECUTABLE_RECORDED_HUMAN_FINAL_APPROVAL_V2"
        or _string(contract["profile"], PROFILE) != PROFILE
    ):
        _fail("CONTRACT_VALUE_INVALID")
    runtime = _mapping(contract["runtime"])
    if runtime != _EXPECTED_RUNTIME:
        _fail("AUTHORITY_ESCALATION")
    _mapping(contract["bindings"], _BINDING_KEYS)
    fixture = _mapping(contract["fixture"], _FIXTURE_KEYS)
    approval = _mapping(fixture["approval"], _APPROVAL_KEYS)
    _mapping(fixture["actor"], _ACTOR_KEYS)
    approval_gate = _mapping(contract["approval_gate"])
    if approval_gate != _EXPECTED_APPROVAL_GATE:
        _fail("APPROVAL_GATE_INVALID")
    if approval["open_blocking_finding_ids"] != []:
        _fail("APPROVAL_GATE_INVALID")
    completion = _mapping(contract["completion_boundary"])
    if completion != _EXPECTED_COMPLETION_BOUNDARY:
        _fail("AUTHORITY_ESCALATION")
    execution = _mapping(contract["execution_boundary"])
    if execution != _EXPECTED_EXECUTION_BOUNDARY:
        _fail("EXECUTION_BOUNDARY_INVALID")
    verification = _mapping(contract["verification_boundary"])
    if verification != _EXPECTED_VERIFICATION_BOUNDARY:
        _fail("VERIFICATION_BOUNDARY_INVALID")
    return contract


def _fixture_bytes(root: Path, contract: dict[str, object]) -> bytes:
    bindings = _mapping(contract["bindings"], _BINDING_KEYS)
    fixture = _mapping(contract["fixture"], _FIXTURE_KEYS)
    approval = _mapping(fixture["approval"], _APPROVAL_KEYS)
    actor = _mapping(fixture["actor"], _ACTOR_KEYS)
    _string(
        bindings["st0805_policy_fixture_uri"],
        f"repo://{POLICY_FIXTURE_PATH.as_posix()}",
    )
    _string(
        bindings["st0901_review_fixture_uri"],
        f"repo://{REVIEW_FIXTURE_PATH.as_posix()}",
    )
    policy_fixture = _read_regular(_safe_path(root, POLICY_FIXTURE_PATH))
    review_fixture = _read_regular(_safe_path(root, REVIEW_FIXTURE_PATH))
    if hashlib.sha256(policy_fixture).hexdigest() != _sha(
        bindings["st0805_policy_fixture_sha256"]
    ) or hashlib.sha256(review_fixture).hexdigest() != _sha(
        bindings["st0901_review_fixture_sha256"]
    ):
        _fail("DEPENDENCY_FIXTURE_DRIFT")
    try:
        envelope = load_recorded_policy_fixture(policy_fixture)
        policy_report = evaluate_editorial_policy_v2(envelope)
        policy_report.require_valid()
        policy_receipt = PolicyEvaluationRecordReceiptV2(
            sequence=_integer(
                bindings["st0805_policy_receipt_sequence"],
                minimum=1,
                maximum=(1 << 53) - 1,
            ),
            report_sha256=policy_report.report_sha256,
        )
        policy_receipt.require_valid()
        review_step = load_recorded_review_completion_fixture(
            review_fixture,
            policy_fixture=policy_fixture,
        )
        review_step.require_valid()
    except Exception:
        _fail("DEPENDENCY_FIXTURE_INVALID")
    if (
        policy_report.article_version_id is None
        or policy_report.article_version_no is None
        or policy_report.article_body_sha256 is None
        or policy_report.canonical_ast_sha256 is None
    ):
        _fail("DEPENDENCY_BINDING_DRIFT")
    finding_snapshot = FinalApprovalFindingSnapshotV2(
        article_version_id=ArticleVersionId(policy_report.article_version_id.value),
        policy_report_sha256=policy_report.report_sha256,
        policy_finding_snapshot_sha256=policy_finding_snapshot_sha256(policy_report),
        captured_at=_instant(approval["finding_snapshot_captured_at"]),
        open_blocking_finding_ids=tuple(
            UUID(_string(item))
            for item in cast(list[object], approval["open_blocking_finding_ids"])
        ),
    )
    expected = {
        "st0805_policy_report_sha256": policy_report.report_sha256.value,
        "st0805_policy_receipt_sha256": policy_receipt_sha256(policy_receipt).value,
        "st0605_coverage_report_sha256": envelope.coverage_report.report_sha256.value,
        "st0605_coverage_receipt_sha256": coverage_receipt_sha256(
            envelope.coverage_receipt
        ).value,
        "st0901_review_result_sha256": review_step.result.result_sha256.value,
        "st0901_review_record_sha256": review_step.result.record.record_sha256.value,
        "st0901_review_decision_sha256": (
            review_step.result.record.decision.decision_sha256.value
        ),
        "policy_finding_snapshot_sha256": policy_finding_snapshot_sha256(
            policy_report
        ).value,
        "finding_clearance_sha256": finding_snapshot.snapshot_sha256.value,
        "article_version_id": str(policy_report.article_version_id.value),
        "article_version_no": policy_report.article_version_no,
        "article_body_sha256": policy_report.article_body_sha256.value,
        "canonical_ast_sha256": policy_report.canonical_ast_sha256.value,
    }
    for key, value in expected.items():
        if bindings.get(key) != value:
            _fail("DEPENDENCY_BINDING_DRIFT")
    document = {
        "schema_version": 2,
        "profile": PROFILE,
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "fixture_id": _string(fixture["fixture_id"]),
        "approval": {key: approval[key] for key in _APPROVAL_KEYS},
        "actor": {key: actor[key] for key in _ACTOR_KEYS},
        "bindings": {
            "policy_fixture_sha256": _sha(bindings["st0805_policy_fixture_sha256"]),
            "policy_report_sha256": expected["st0805_policy_report_sha256"],
            "policy_receipt_sequence": policy_receipt.sequence,
            "policy_receipt_sha256": expected["st0805_policy_receipt_sha256"],
            "coverage_report_sha256": expected["st0605_coverage_report_sha256"],
            "coverage_receipt_sha256": expected["st0605_coverage_receipt_sha256"],
            "review_fixture_sha256": _sha(bindings["st0901_review_fixture_sha256"]),
            "review_result_sha256": expected["st0901_review_result_sha256"],
            "review_record_sha256": expected["st0901_review_record_sha256"],
            "review_decision_sha256": expected["st0901_review_decision_sha256"],
            "policy_finding_snapshot_sha256": expected[
                "policy_finding_snapshot_sha256"
            ],
            "finding_clearance_sha256": expected["finding_clearance_sha256"],
            "article_version_id": expected["article_version_id"],
            "article_version_no": expected["article_version_no"],
            "article_body_sha256": expected["article_body_sha256"],
            "canonical_ast_sha256": expected["canonical_ast_sha256"],
        },
        "authority": {
            "recorded_synthetic_only": True,
            "real_final_approval_authorized": False,
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
        '"""Owner-generated ST-0902 V2 recorded fixture bytes."""\n\n'
        "from typing import Final\n\n"
        f"FINAL_APPROVAL_PASS_V2_JSON: Final = {fixture!r}\n"
        "FINAL_APPROVAL_PASS_V2_SHA256: Final = (\n"
        f'    "{digest}"\n'
        ")\n\n"
        "__all__ = (\n"
        '    "FINAL_APPROVAL_PASS_V2_JSON",\n'
        '    "FINAL_APPROVAL_PASS_V2_SHA256",\n'
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
    sources = [
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
        "story_id": "ST-0902",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_RECORDED_FINAL_APPROVAL_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python scripts/build_st0902_final_approval_runtime_v2.py"
            ),
            "check_command": (
                ".venv/bin/python "
                "scripts/build_st0902_final_approval_runtime_v2.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "secure_publication_helper_sha256": hashlib.sha256(
                _read_regular(_safe_path(root, SECURE_HELPER_PATH))
            ).hexdigest(),
        },
        "authority": {
            "real_final_approval_authorized": False,
            "publication_snapshot_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "formal_tst_012_status": "NOT_EXECUTED",
            "formal_tst_021_status": "NOT_EXECUTED",
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
            namespace="st0902-v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    root = Path(os.path.abspath(root))
    contract = load_contract(root)
    fixture = _fixture_bytes(root, contract)
    try:
        step = load_recorded_final_approval_fixture(
            fixture,
            policy_fixture=_read_regular(_safe_path(root, POLICY_FIXTURE_PATH)),
            review_fixture=_read_regular(_safe_path(root, REVIEW_FIXTURE_PATH)),
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
        print("ST-0902 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0902 V2 runtime checked"
        if arguments.check
        else "ST-0902 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
