"""One-shot, caller-byte recorded adapter for ST-0806 V2."""

from __future__ import annotations

import hashlib
import json
from threading import RLock
from typing import NoReturn, SupportsIndex, cast, final

from raos.adapters.recorded_claim_evidence import (
    load_recorded_claim_evidence_fixture,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ai_draft_integration_v2 import (
    CONTRACT_SHA256,
    FIXTURE_DOCUMENT_ID,
    FIXTURE_SCHEMA_VERSION,
    MAXIMUM_FIXTURE_BYTES,
    POLICY_SHA256,
    AiDraftV2FailureCode,
    BoundContentAstV2,
    RecordedDraftMaterialV2,
    fail_ai_draft_v2,
)
from raos.domain.evidence.claim_evidence import (
    CoverageRecordReceipt,
    evaluate_claim_evidence,
)
from raos.domain.shared.persistence import Sha256Digest


_ROOT_KEYS = (
    "after_content_ast_sha256",
    "after_content_ast_utf8",
    "claim_evidence_snapshot_sha256",
    "claim_evidence_snapshot_utf8",
    "contract_sha256",
    "coverage_receipt",
    "coverage_report_sha256",
    "coverage_report_utf8",
    "document_id",
    "policy_sha256",
    "schema_version",
)


def _fail() -> NoReturn:
    fail_ai_draft_v2(AiDraftV2FailureCode.FIXTURE_INVALID)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _string(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail()
    return value


def _sha256(value: object) -> str:
    text = _string(value)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail()
    return text


def _document_string(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or len(value.encode("utf-8", errors="strict")) > MAXIMUM_FIXTURE_BYTES
    ):
        _fail()
    return value


def _canonical_fixture_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8", errors="strict")
            + b"\n"
        )
    except Exception:
        _fail()


def load_recorded_ai_draft_fixture_v2(payload: bytes) -> RecordedDraftMaterialV2:
    """Decode and recompute one canonical, content-addressed fixture."""

    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAXIMUM_FIXTURE_BYTES
    ):
        _fail()
    copied = bytes(payload)
    try:
        loaded: object = json.loads(copied, object_pairs_hook=_pairs)
    except Exception:
        _fail()
    if type(loaded) is not dict:
        _fail()
    document = cast(dict[str, object], loaded)
    if tuple(document) != _ROOT_KEYS:
        _fail()
    if copied != _canonical_fixture_bytes(document):
        _fail()
    if (
        document["document_id"] != FIXTURE_DOCUMENT_ID
        or document["schema_version"] != FIXTURE_SCHEMA_VERSION
        or type(document["schema_version"]) is not int
        or document["contract_sha256"] != CONTRACT_SHA256
        or document["policy_sha256"] != POLICY_SHA256
    ):
        _fail()

    try:
        after_bytes = _document_string(document["after_content_ast_utf8"]).encode(
            "utf-8", errors="strict"
        )
        snapshot_bytes = _document_string(
            document["claim_evidence_snapshot_utf8"]
        ).encode("utf-8", errors="strict")
        report_bytes = _document_string(document["coverage_report_utf8"]).encode(
            "utf-8", errors="strict"
        )
    except Exception:
        _fail()
    if (
        hashlib.sha256(after_bytes).hexdigest()
        != _sha256(document["after_content_ast_sha256"])
        or hashlib.sha256(snapshot_bytes).hexdigest()
        != _sha256(document["claim_evidence_snapshot_sha256"])
        or hashlib.sha256(report_bytes).hexdigest()
        != _sha256(document["coverage_report_sha256"])
    ):
        _fail()
    try:
        after_ast = BoundContentAstV2(after_bytes)
        snapshot = load_recorded_claim_evidence_fixture(snapshot_bytes)
        report = evaluate_claim_evidence(snapshot)
        report.require_valid()
    except Exception:
        _fail()
    if report.canonical_bytes() != report_bytes:
        _fail()
    receipt_value = document["coverage_receipt"]
    if type(receipt_value) is not dict:
        _fail()
    receipt_row = cast(dict[str, object], receipt_value)
    if tuple(receipt_row) != (
        "publication_authorized",
        "report_sha256",
        "sequence",
    ):
        _fail()
    publication_authorized = receipt_row["publication_authorized"]
    sequence = receipt_row["sequence"]
    if publication_authorized is not False or type(sequence) is not int:
        _fail()
    try:
        receipt = CoverageRecordReceipt(
            sequence=sequence,
            report_sha256=Sha256Digest(_sha256(receipt_row["report_sha256"])),
            publication_authorized=False,
        )
        receipt.require_valid()
    except Exception:
        _fail()
    if receipt.report_sha256 != report.report_sha256:
        _fail()
    return RecordedDraftMaterialV2(
        after_ast=after_ast,
        coverage_snapshot=snapshot,
        coverage_report=report,
        coverage_receipt=receipt,
        fixture_sha256=hashlib.sha256(copied).hexdigest(),
    )


@final
class RecordedAiDraftIntegrationStepV2:
    """Immutable request binding plus copied fixture bytes."""

    __slots__ = ("_fixture_bytes", "_request_binding_sha256")

    def __init__(self, *, request_binding_sha256: str, fixture_bytes: bytes) -> None:
        if type(fixture_bytes) is not bytes:
            _fail()
        _sha256(request_binding_sha256)
        copied = bytes(fixture_bytes)
        load_recorded_ai_draft_fixture_v2(copied)
        self._request_binding_sha256 = request_binding_sha256
        self._fixture_bytes = copied

    @property
    def request_binding_sha256(self) -> str:
        return self._request_binding_sha256

    def material(self) -> RecordedDraftMaterialV2:
        return load_recorded_ai_draft_fixture_v2(bytes(self._fixture_bytes))

    def __repr__(self) -> str:
        return "RecordedAiDraftIntegrationStepV2(<redacted-st0806-v2>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded ST-0806 V2 step serialization is unsupported")


@final
class RecordedAiDraftIntegrationAdapterV2:
    """Consume exactly one request-bound fixture with no fallback or I/O."""

    __slots__ = ("_called", "_environment", "_lock", "_step")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        script_capacity: int,
        scripts: tuple[RecordedAiDraftIntegrationStepV2, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(script_capacity) is not int
            or script_capacity != 1
            or type(scripts) is not tuple
            or len(scripts) != 1
            or type(scripts[0]) is not RecordedAiDraftIntegrationStepV2
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.DEVELOPMENT_ONLY)
        self._environment = environment
        self._step = scripts[0]
        self._called = False
        self._lock = RLock()

    @property
    def call_count(self) -> int:
        with self._lock:
            return int(self._called)

    def integrate(self, *, request_binding_sha256: str) -> RecordedDraftMaterialV2:
        with self._lock:
            if (
                self._called
                or _sha256(request_binding_sha256) != self._step.request_binding_sha256
            ):
                fail_ai_draft_v2(AiDraftV2FailureCode.COLLABORATOR_FAILURE)
            self._called = True
            return self._step.material()

    def __repr__(self) -> str:
        return "RecordedAiDraftIntegrationAdapterV2(<redacted-st0806-v2>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded ST-0806 V2 adapter serialization is unsupported")


__all__ = [
    "RecordedAiDraftIntegrationAdapterV2",
    "RecordedAiDraftIntegrationStepV2",
    "load_recorded_ai_draft_fixture_v2",
]
