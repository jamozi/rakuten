"""Receipt-bound, effect-free ST-0806 AI draft proposal values.

V2 consumes metadata already committed by ST-0706 and evidence already
evaluated by ST-0605.  It never runs an AI provider, mutates ST-0706 state,
persists an ST-0802 version, approves content, or publishes an article.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.durable_job_queue_v2 import (
    CONTRACT_SHA256 as ST0706_CONTRACT_SHA256,
)
from raos.domain.ai.durable_job_queue_v2 import (
    POLICY_SHA256 as ST0706_POLICY_SHA256,
)
from raos.domain.ai.durable_job_queue_v2 import (
    DurableDecisionCode,
    DurableJobRecord,
    DurableJobStatus,
    DurableOutboxIntent,
    DurableQueueSnapshot,
    RecordedAttemptKind,
    RecordedAttemptOutcome,
    snapshot_state,
)
from raos.domain.ai.job_orchestration import AiJobEventType, ValidationStatus
from raos.domain.editorial.article_lifecycle import (
    ArticleState,
    ArticleVersionState,
    VersionSnapshot,
)
from raos.domain.editorial.content_ast import (
    ContentAst,
    dump_content_ast_json,
    load_content_ast,
)
from raos.domain.evidence.claim_evidence import (
    EVALUATOR_VERSION as ST0605_EVALUATOR_VERSION,
)
from raos.domain.evidence.claim_evidence import POLICY_SHA256 as ST0605_POLICY_SHA256
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceCoverageReport,
    ClaimEvidenceSnapshot,
    CoverageRecordReceipt,
    CoverageStatus,
    evaluate_claim_evidence,
)


AI_ARTICLE_DRAFT_TASK_V2 = "ai.article_draft.v1"
CONTRACT_SHA256 = "4ca2dfb59f60a4c65bb6c0c31595cac1281d6b62b3900bfe5204770f5cc8c6e7"
POLICY_ID = "st-0806.ai-draft-integration.v2"
POLICY_SHA256 = "443b5ea91544ea1e8d5f9c7c2e71ebe331fda6f81397f0b51e25aa70da5c77f2"
FIXTURE_DOCUMENT_ID = "RAOS-ST0806-AI-DRAFT-FIXTURE-002"
FIXTURE_SCHEMA_VERSION = 2
MAXIMUM_FIXTURE_BYTES = 1_048_576
MAXIMUM_DIFF_OPERATIONS = 4_096
MAXIMUM_JSON_POINTER_BYTES = 512
MAXIMUM_COMPLETE_CLAIMS = 10_000

_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_JSON_POINTER = re.compile(r"/(?:[^~/]|~[01])*(?:/(?:[^~/]|~[01])*)*\Z")
_RAW_HTML = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
_REDACTED = "<redacted-ai-draft-integration-v2>"
_BANNED_KEYS = frozenset(
    {
        "affiliate_rate",
        "api_key",
        "client_secret",
        "commission",
        "credential",
        "epc",
        "finance",
        "href",
        "html",
        "password",
        "private_key",
        "profit",
        "raw_html",
        "raw_prompt",
        "review_body",
        "revenue",
        "rpm",
        "secret",
        "token",
        "url",
    }
)
_BANNED_TEXT_FRAGMENTS = (
    "http://",
    "https://",
    "javascript:",
    "data:text/html",
    "authorization: bearer",
    "api_key=",
    "client_secret=",
    "private_key=",
    "password=",
)


class AiDraftV2FailureCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    DISABLED = "DISABLED"
    DURABLE_RECEIPT_INVALID = "DURABLE_RECEIPT_INVALID"
    ARTIFACT_BINDING_MISMATCH = "ARTIFACT_BINDING_MISMATCH"
    CONTENT_AST_INVALID = "CONTENT_AST_INVALID"
    DIFF_INVALID = "DIFF_INVALID"
    COVERAGE_BINDING_MISMATCH = "COVERAGE_BINDING_MISMATCH"
    FIXTURE_INVALID = "FIXTURE_INVALID"
    COLLABORATOR_FAILURE = "COLLABORATOR_FAILURE"
    RESULT_MISMATCH = "RESULT_MISMATCH"


class DraftCoverageDecisionV2(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class DraftProposalDispositionV2(str, Enum):
    HUMAN_EDITABLE_PROPOSAL_ONLY = "HUMAN_EDITABLE_PROPOSAL_ONLY"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class DraftExecutionV2(str, Enum):
    RECORDED_ONLY = "RECORDED_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


class DiffOperationKindV2(str, Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    REPLACE = "REPLACE"


@final
class AiDraftV2Failure(RuntimeError):
    """Immutable failure that retains no rejected fixture or content bytes."""

    __slots__ = ("_code",)
    _code: AiDraftV2FailureCode

    def __init__(self, code: AiDraftV2FailureCode) -> None:
        if type(code) is not AiDraftV2FailureCode:
            raise TypeError("code must be an exact AiDraftV2FailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> AiDraftV2FailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("AiDraftV2Failure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AiDraftV2Failure is immutable")

    def __repr__(self) -> str:
        return f"AiDraftV2Failure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("AI draft V2 failure serialization is unsupported")


def fail_ai_draft_v2(code: AiDraftV2FailureCode) -> NoReturn:
    raise AiDraftV2Failure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("AI draft V2 value serialization is unsupported")


def _require_token(value: object) -> str:
    if type(value) is not str or _SAFE_TOKEN.fullmatch(value) is None:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    return value


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    return value


def _require_uuid(value: object) -> UUID:
    if type(value) is not UUID:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    return value


def _canonical_json_bytes(value: object) -> bytes:
    encoded: bytes | None = None
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        pass
    if encoded is None:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    return encoded


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _reject_prohibited_material(value: object) -> None:
    stack: list[object] = [value]
    visited = 0
    while stack:
        current = stack.pop()
        visited += 1
        if visited > 100_000:
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
        if type(current) is dict:
            for key, child in current.items():
                if type(key) is not str or key.casefold() in _BANNED_KEYS:
                    fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
                stack.append(child)
        elif type(current) is list:
            stack.extend(current)
        elif type(current) is str:
            lowered = current.casefold()
            if _RAW_HTML.search(current) is not None or any(
                fragment in lowered for fragment in _BANNED_TEXT_FRAGMENTS
            ):
                fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)


@final
@dataclass(frozen=True, slots=True, repr=False)
class BoundContentAstV2(_RedactedValue):
    """Immutable canonical AST bytes with a fresh typed projection per access."""

    canonical_bytes: bytes
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.canonical_bytes) is not bytes
            or not self.canonical_bytes
            or len(self.canonical_bytes) > MAXIMUM_FIXTURE_BYTES
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
        copied = bytes(self.canonical_bytes)
        try:
            typed = load_content_ast(copied)
            rendered = dump_content_ast_json(typed).encode("utf-8")
            material = json.loads(copied.decode("utf-8", errors="strict"))
        except Exception:
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
        if copied != rendered:
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
        _reject_prohibited_material(material)
        object.__setattr__(self, "canonical_bytes", copied)
        object.__setattr__(self, "sha256", hashlib.sha256(copied).hexdigest())

    @classmethod
    def from_content_ast(cls, value: ContentAst) -> BoundContentAstV2:
        if type(value) is not ContentAst:
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
        try:
            rendered = dump_content_ast_json(value).encode("utf-8")
        except Exception:
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)
        return cls(rendered)

    def content_ast(self) -> ContentAst:
        """Return a detached typed Content AST projection."""

        try:
            return load_content_ast(self.canonical_bytes)
        except Exception:
            fail_ai_draft_v2(AiDraftV2FailureCode.CONTENT_AST_INVALID)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ContentAstDiffOperationV2(_RedactedValue):
    ordinal: int
    kind: DiffOperationKindV2
    json_pointer: str
    before_value_sha256: str | None
    after_value_sha256: str | None

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or not 1 <= self.ordinal <= MAXIMUM_DIFF_OPERATIONS
            or type(self.kind) is not DiffOperationKindV2
            or type(self.json_pointer) is not str
            or not self.json_pointer
            or len(self.json_pointer.encode("utf-8", errors="strict"))
            > MAXIMUM_JSON_POINTER_BYTES
            or _JSON_POINTER.fullmatch(self.json_pointer) is None
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
        if self.before_value_sha256 is not None:
            _require_sha256(self.before_value_sha256)
        if self.after_value_sha256 is not None:
            _require_sha256(self.after_value_sha256)
        expected_presence = {
            DiffOperationKindV2.ADD: (False, True),
            DiffOperationKindV2.REMOVE: (True, False),
            DiffOperationKindV2.REPLACE: (True, True),
        }[self.kind]
        if (
            self.before_value_sha256 is not None,
            self.after_value_sha256 is not None,
        ) != expected_presence:
            fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)


def _diff_payload(operation: ContentAstDiffOperationV2) -> dict[str, object]:
    return {
        "after_value_sha256": operation.after_value_sha256,
        "before_value_sha256": operation.before_value_sha256,
        "json_pointer": operation.json_pointer,
        "kind": operation.kind.value,
        "ordinal": operation.ordinal,
    }


@final
@dataclass(frozen=True, slots=True, repr=False)
class ContentAstDiffV2(_RedactedValue):
    before_ast_sha256: str
    after_ast_sha256: str
    operations: tuple[ContentAstDiffOperationV2, ...]
    changed: bool
    diff_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.before_ast_sha256)
        _require_sha256(self.after_ast_sha256)
        if (
            type(self.operations) is not tuple
            or len(self.operations) > MAXIMUM_DIFF_OPERATIONS
            or any(
                type(item) is not ContentAstDiffOperationV2 for item in self.operations
            )
            or tuple(item.ordinal for item in self.operations)
            != tuple(range(1, len(self.operations) + 1))
            or len({item.json_pointer for item in self.operations})
            != len(self.operations)
            or type(self.changed) is not bool
            or self.changed != bool(self.operations)
            or self.changed != (self.before_ast_sha256 != self.after_ast_sha256)
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
        object.__setattr__(
            self,
            "diff_sha256",
            _canonical_sha256(
                {
                    "after_ast_sha256": self.after_ast_sha256,
                    "before_ast_sha256": self.before_ast_sha256,
                    "operations": [_diff_payload(item) for item in self.operations],
                    "profile": "ST0806_ORDERED_CONTENT_AST_DIFF_V2",
                }
            ),
        )


def _pointer_component(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _value_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _walk_diff(
    before: object,
    after: object,
    pointer: str,
    output: list[tuple[DiffOperationKindV2, str, str | None, str | None]],
) -> None:
    if len(output) > MAXIMUM_DIFF_OPERATIONS:
        fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
    if type(before) is dict and type(after) is dict:
        before_map = before
        after_map = after
        for key in sorted(set(before_map) | set(after_map)):
            if type(key) is not str:
                fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
            child = f"{pointer}/{_pointer_component(key)}"
            if key not in before_map:
                output.append(
                    (
                        DiffOperationKindV2.ADD,
                        child,
                        None,
                        _value_sha256(after_map[key]),
                    )
                )
            elif key not in after_map:
                output.append(
                    (
                        DiffOperationKindV2.REMOVE,
                        child,
                        _value_sha256(before_map[key]),
                        None,
                    )
                )
            else:
                _walk_diff(before_map[key], after_map[key], child, output)
        return
    if type(before) is list and type(after) is list:
        shared = min(len(before), len(after))
        for index in range(shared):
            _walk_diff(before[index], after[index], f"{pointer}/{index}", output)
        for index in range(shared, len(before)):
            output.append(
                (
                    DiffOperationKindV2.REMOVE,
                    f"{pointer}/{index}",
                    _value_sha256(before[index]),
                    None,
                )
            )
        for index in range(shared, len(after)):
            output.append(
                (
                    DiffOperationKindV2.ADD,
                    f"{pointer}/{index}",
                    None,
                    _value_sha256(after[index]),
                )
            )
        return
    if before != after or type(before) is not type(after):
        output.append(
            (
                DiffOperationKindV2.REPLACE,
                pointer or "/",
                _value_sha256(before),
                _value_sha256(after),
            )
        )


def build_content_ast_diff_v2(
    before: BoundContentAstV2, after: BoundContentAstV2
) -> ContentAstDiffV2:
    if type(before) is not BoundContentAstV2 or type(after) is not BoundContentAstV2:
        fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
    try:
        before_value = json.loads(before.canonical_bytes)
        after_value = json.loads(after.canonical_bytes)
    except Exception:
        fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
    raw: list[tuple[DiffOperationKindV2, str, str | None, str | None]] = []
    _walk_diff(before_value, after_value, "", raw)
    if len(raw) > MAXIMUM_DIFF_OPERATIONS:
        fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
    operations = tuple(
        ContentAstDiffOperationV2(index, kind, pointer, before_sha, after_sha)
        for index, (kind, pointer, before_sha, after_sha) in enumerate(raw, start=1)
    )
    return ContentAstDiffV2(
        before_ast_sha256=before.sha256,
        after_ast_sha256=after.sha256,
        operations=operations,
        changed=bool(operations),
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiDraftV2Activation(_RedactedValue):
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV
    enabled: bool = False
    policy_id: str = POLICY_ID
    contract_sha256: str = CONTRACT_SHA256
    policy_sha256: str = POLICY_SHA256
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.environment) is not RuntimeEnvironment or self.environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_ai_draft_v2(AiDraftV2FailureCode.DEVELOPMENT_ONLY)
        if (
            type(self.enabled) is not bool
            or self.policy_id != POLICY_ID
            or self.contract_sha256 != CONTRACT_SHA256
            or self.policy_sha256 != POLICY_SHA256
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "contract_sha256": self.contract_sha256,
                    "enabled": self.enabled,
                    "environment": self.environment.value,
                    "policy_id": self.policy_id,
                    "policy_sha256": self.policy_sha256,
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiDraftIntegrationRequestV2(_RedactedValue):
    environment: RuntimeEnvironment
    operation_id: str
    queue_snapshot: DurableQueueSnapshot
    recorded_outcome: RecordedAttemptOutcome
    source_version: VersionSnapshot
    article_state: ArticleState
    site_id: UUID
    category_id: UUID
    binding_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.environment) is not RuntimeEnvironment or self.environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_ai_draft_v2(AiDraftV2FailureCode.DEVELOPMENT_ONLY)
        _require_token(self.operation_id)
        if (
            type(self.queue_snapshot) is not DurableQueueSnapshot
            or type(self.recorded_outcome) is not RecordedAttemptOutcome
            or type(self.source_version) is not VersionSnapshot
            or self.article_state is not ArticleState.DRAFT
            or self.source_version.state is not ArticleVersionState.DRAFT
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
        _require_uuid(self.site_id)
        _require_uuid(self.category_id)
        object.__setattr__(
            self,
            "binding_sha256",
            _canonical_sha256(
                {
                    "article_body_sha256": self.source_version.body_sha256.value,
                    "article_id": str(self.source_version.article_id),
                    "article_version_id": str(self.source_version.version_id),
                    "category_id": str(self.category_id),
                    "environment": self.environment.value,
                    "operation_id": self.operation_id,
                    "outcome_sha256": self.recorded_outcome.fingerprint_sha256,
                    "queue_id": self.queue_snapshot.queue_id,
                    "queue_revision": self.queue_snapshot.revision,
                    "queue_state_sha256": self.queue_snapshot.state_sha256,
                    "site_id": str(self.site_id),
                    "source_packet_version_id": str(
                        self.source_version.source_packet_version_id
                    ),
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DurableSucceededBindingV2(_RedactedValue):
    queue_id: str
    state_revision: int
    state_sha256: str
    st0706_contract_sha256: str
    st0706_policy_sha256: str
    operation_id: str
    ai_job_id: UUID
    command_fingerprint_sha256: str
    source_packet_version_id: UUID
    article_version_id: UUID
    input_artifact_id: UUID
    input_artifact_sha256: str
    validation_plan_id: str
    validation_plan_sha256: str
    completion_claim_sha256: str
    outcome_sha256: str
    output_artifact_id: UUID
    output_artifact_sha256: str
    succeeded_intent_id_sha256: str
    succeeded_intent_metadata_sha256: str
    attempt_number: int
    actual_cost_jpy: int
    accumulated_cost_jpy: int
    binding_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_token(self.queue_id)
        if type(self.state_revision) is not int or self.state_revision < 1:
            fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
        for digest in (
            self.state_sha256,
            self.st0706_contract_sha256,
            self.st0706_policy_sha256,
            self.command_fingerprint_sha256,
            self.input_artifact_sha256,
            self.validation_plan_sha256,
            self.completion_claim_sha256,
            self.outcome_sha256,
            self.output_artifact_sha256,
            self.succeeded_intent_id_sha256,
            self.succeeded_intent_metadata_sha256,
        ):
            _require_sha256(digest)
        if (
            self.st0706_contract_sha256 != ST0706_CONTRACT_SHA256
            or self.st0706_policy_sha256 != ST0706_POLICY_SHA256
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
        _require_token(self.operation_id)
        _require_uuid(self.ai_job_id)
        _require_uuid(self.source_packet_version_id)
        _require_uuid(self.article_version_id)
        _require_uuid(self.input_artifact_id)
        _require_token(self.validation_plan_id)
        _require_uuid(self.output_artifact_id)
        if (
            type(self.attempt_number) is not int
            or self.attempt_number < 1
            or type(self.actual_cost_jpy) is not int
            or self.actual_cost_jpy < 0
            or type(self.accumulated_cost_jpy) is not int
            or self.accumulated_cost_jpy < self.actual_cost_jpy
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
        object.__setattr__(
            self,
            "binding_sha256",
            _canonical_sha256(
                {
                    "actual_cost_jpy": self.actual_cost_jpy,
                    "accumulated_cost_jpy": self.accumulated_cost_jpy,
                    "ai_job_id": str(self.ai_job_id),
                    "article_version_id": str(self.article_version_id),
                    "attempt_number": self.attempt_number,
                    "command_fingerprint_sha256": self.command_fingerprint_sha256,
                    "completion_claim_sha256": self.completion_claim_sha256,
                    "input_artifact_id": str(self.input_artifact_id),
                    "input_artifact_sha256": self.input_artifact_sha256,
                    "operation_id": self.operation_id,
                    "outcome_sha256": self.outcome_sha256,
                    "output_artifact_id": str(self.output_artifact_id),
                    "output_artifact_sha256": self.output_artifact_sha256,
                    "queue_id": self.queue_id,
                    "source_packet_version_id": str(self.source_packet_version_id),
                    "state_revision": self.state_revision,
                    "state_sha256": self.state_sha256,
                    "st0706_contract_sha256": self.st0706_contract_sha256,
                    "st0706_policy_sha256": self.st0706_policy_sha256,
                    "succeeded_intent_id_sha256": self.succeeded_intent_id_sha256,
                    "succeeded_intent_metadata_sha256": self.succeeded_intent_metadata_sha256,
                    "validation_plan_id": self.validation_plan_id,
                    "validation_plan_sha256": self.validation_plan_sha256,
                }
            ),
        )


def _exact_succeeded_intent(
    intents: tuple[DurableOutboxIntent, ...], job: DurableJobRecord
) -> DurableOutboxIntent:
    matches = tuple(
        intent
        for intent in intents
        if intent.ai_job_id == job.command.ai_job_id
        and intent.event_type is AiJobEventType.SUCCEEDED
        and intent.status is DurableJobStatus.SUCCEEDED
        and intent.attempt_number == job.attempt_number
    )
    if len(matches) != 1:
        fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
    return matches[0]


def bind_durable_succeeded_completion_v2(
    request: AiDraftIntegrationRequestV2,
) -> DurableSucceededBindingV2:
    """Validate one exact ST-0706 canonical success without mutating its state."""

    if type(request) is not AiDraftIntegrationRequestV2:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    try:
        state = snapshot_state(request.queue_snapshot)
    except Exception:
        fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
    outcome = request.recorded_outcome
    jobs = tuple(
        job for job in state.jobs if job.command.ai_job_id == outcome.ai_job_id
    )
    if len(jobs) != 1:
        fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
    job = jobs[0]
    command = job.command
    if (
        command.operation_id != request.operation_id
        or command.task_code != AI_ARTICLE_DRAFT_TASK_V2
        or command.article_plan_id is not None
        or command.article_version_id != request.source_version.version_id
        or command.source_packet_version_id
        != request.source_version.source_packet_version_id
        or job.status is not DurableJobStatus.SUCCEEDED
        or job.decision_code is not DurableDecisionCode.SUCCEEDED
        or job.lease is not None
        or outcome.kind is not RecordedAttemptKind.SUCCEEDED
        or outcome.validation_status is not ValidationStatus.PASS
        or outcome.validation_failure_class is not None
        or outcome.provider_failure_class is not None
        or outcome.retryable
        or type(outcome.actual_cost_jpy) is not int
        or outcome.actual_cost_jpy < 0
        or type(outcome.output_artifact_id) is not UUID
        or outcome.output_artifact_sha256 is None
        or outcome.ai_job_id != command.ai_job_id
        or outcome.attempt_number != job.attempt_number
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
    receipts = tuple(
        receipt
        for receipt in job.completion_receipts
        if receipt.status is DurableJobStatus.SUCCEEDED
        and receipt.decision_code is DurableDecisionCode.SUCCEEDED
    )
    if len(receipts) != 1:
        fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
    receipt = receipts[0]
    if (
        receipt.outcome_sha256 != outcome.fingerprint_sha256
        or receipt.claimed_attempt_number != outcome.attempt_number
        or receipt.attempt_number != job.attempt_number
        or receipt.accumulated_cost_jpy != job.accumulated_cost_jpy
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.DURABLE_RECEIPT_INVALID)
    intent = _exact_succeeded_intent(state.outbox_intents, job)
    return DurableSucceededBindingV2(
        queue_id=state.queue_id,
        state_revision=state.revision,
        state_sha256=request.queue_snapshot.state_sha256,
        st0706_contract_sha256=ST0706_CONTRACT_SHA256,
        st0706_policy_sha256=ST0706_POLICY_SHA256,
        operation_id=command.operation_id,
        ai_job_id=command.ai_job_id,
        command_fingerprint_sha256=command.fingerprint_sha256,
        source_packet_version_id=command.source_packet_version_id,
        article_version_id=command.article_version_id,
        input_artifact_id=command.input_artifact_id,
        input_artifact_sha256=command.input_artifact_sha256,
        validation_plan_id=command.validation_plan.plan_id,
        validation_plan_sha256=command.validation_plan.plan_sha256,
        completion_claim_sha256=receipt.claim_sha256,
        outcome_sha256=receipt.outcome_sha256,
        output_artifact_id=outcome.output_artifact_id,
        output_artifact_sha256=outcome.output_artifact_sha256,
        succeeded_intent_id_sha256=intent.intent_id_sha256,
        succeeded_intent_metadata_sha256=intent.metadata_sha256,
        attempt_number=outcome.attempt_number,
        actual_cost_jpy=outcome.actual_cost_jpy,
        accumulated_cost_jpy=job.accumulated_cost_jpy,
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedDraftMaterialV2(_RedactedValue):
    after_ast: BoundContentAstV2
    coverage_snapshot: ClaimEvidenceSnapshot | None
    coverage_report: ClaimEvidenceCoverageReport | None
    coverage_receipt: CoverageRecordReceipt | None
    fixture_sha256: str

    def __post_init__(self) -> None:
        if type(self.after_ast) is not BoundContentAstV2:
            fail_ai_draft_v2(AiDraftV2FailureCode.FIXTURE_INVALID)
        _require_sha256(self.fixture_sha256)
        coverage_values = (
            self.coverage_snapshot,
            self.coverage_report,
            self.coverage_receipt,
        )
        if all(value is None for value in coverage_values):
            return
        if (
            type(self.coverage_snapshot) is not ClaimEvidenceSnapshot
            or type(self.coverage_report) is not ClaimEvidenceCoverageReport
            or type(self.coverage_receipt) is not CoverageRecordReceipt
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.FIXTURE_INVALID)


def _claim_references(value: object) -> tuple[str, ...]:
    references: set[str] = set()
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            for key, child in current.items():
                if key in {"claim_ids", "rationale_claim_ids"}:
                    if type(child) is not list or any(
                        type(item) is not str for item in child
                    ):
                        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
                    references.update(child)
                else:
                    stack.append(child)
        elif type(current) is list:
            stack.extend(current)
    return tuple(sorted(references))


@final
@dataclass(frozen=True, slots=True, repr=False)
class CoverageBindingV2(_RedactedValue):
    article_version_id: UUID
    article_body_sha256: str
    source_packet_version_id: UUID
    source_packet_content_sha256: str
    complete_claim_ids: tuple[UUID, ...]
    complete_claim_set_sha256: str
    evaluation_input_sha256: str
    report_sha256: str
    receipt_sequence: int
    evaluator_version: str
    policy_sha256: str
    major_evidenced: int
    major_total: int
    all_verifiable_evidenced: int
    all_verifiable_total: int
    binding_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_uuid(self.article_version_id)
        _require_sha256(self.article_body_sha256)
        _require_uuid(self.source_packet_version_id)
        for digest in (
            self.source_packet_content_sha256,
            self.complete_claim_set_sha256,
            self.evaluation_input_sha256,
            self.report_sha256,
            self.policy_sha256,
        ):
            _require_sha256(digest)
        if (
            type(self.complete_claim_ids) is not tuple
            or not 1 <= len(self.complete_claim_ids) <= MAXIMUM_COMPLETE_CLAIMS
            or any(type(value) is not UUID for value in self.complete_claim_ids)
            or tuple(sorted(self.complete_claim_ids, key=str))
            != self.complete_claim_ids
            or len(set(self.complete_claim_ids)) != len(self.complete_claim_ids)
            or type(self.receipt_sequence) is not int
            or self.receipt_sequence < 1
            or self.evaluator_version != ST0605_EVALUATOR_VERSION
            or self.policy_sha256 != ST0605_POLICY_SHA256
            or type(self.major_evidenced) is not int
            or type(self.major_total) is not int
            or self.major_total < 1
            or self.major_evidenced != self.major_total
            or type(self.all_verifiable_evidenced) is not int
            or type(self.all_verifiable_total) is not int
            or self.all_verifiable_total < 1
            or not 0 <= self.all_verifiable_evidenced <= self.all_verifiable_total
            or self.all_verifiable_evidenced * 100 < self.all_verifiable_total * 95
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
        object.__setattr__(
            self,
            "binding_sha256",
            _canonical_sha256(
                {
                    "all_verifiable": [
                        self.all_verifiable_evidenced,
                        self.all_verifiable_total,
                    ],
                    "article_body_sha256": self.article_body_sha256,
                    "article_version_id": str(self.article_version_id),
                    "complete_claim_ids": [
                        str(value) for value in self.complete_claim_ids
                    ],
                    "complete_claim_set_sha256": self.complete_claim_set_sha256,
                    "evaluation_input_sha256": self.evaluation_input_sha256,
                    "evaluator_version": self.evaluator_version,
                    "major": [self.major_evidenced, self.major_total],
                    "policy_sha256": self.policy_sha256,
                    "receipt_sequence": self.receipt_sequence,
                    "report_sha256": self.report_sha256,
                    "source_packet_content_sha256": self.source_packet_content_sha256,
                    "source_packet_version_id": str(self.source_packet_version_id),
                }
            ),
        )


def bind_coverage_v2(
    *, material: RecordedDraftMaterialV2, after_ast: BoundContentAstV2
) -> tuple[
    DraftCoverageDecisionV2,
    CoverageStatus | None,
    CoverageBindingV2 | None,
    str | None,
    int | None,
]:
    if (
        type(material) is not RecordedDraftMaterialV2
        or type(after_ast) is not BoundContentAstV2
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    if material.coverage_snapshot is None:
        return DraftCoverageDecisionV2.UNAVAILABLE, None, None, None, None
    assert material.coverage_report is not None
    assert material.coverage_receipt is not None
    snapshot = material.coverage_snapshot
    supplied = material.coverage_report
    receipt = material.coverage_receipt
    try:
        recomputed = evaluate_claim_evidence(snapshot)
        supplied.require_valid()
        receipt.require_valid()
    except Exception:
        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
    if (
        recomputed.canonical_bytes() != supplied.canonical_bytes()
        or receipt.report_sha256 != supplied.report_sha256
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
    try:
        ast_value = json.loads(after_ast.canonical_bytes)
        ast_claim_ids = _claim_references(ast_value)
        article = snapshot.article
        expected_claim_ids = tuple(
            sorted(str(value.value) for value in article.complete_claim_ids)
        )
        report_input = supplied.evaluation_input_sha256
        complete_hash = supplied.complete_claim_set_sha256
        major = supplied.major_coverage
        all_claims = supplied.all_verifiable_coverage
        article_version_id = article.article_version_id.value
        source_packet_version_id = article.source_packet_version_id.value
    except Exception:
        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
    if (
        str(ast_value.get("article_version_id")) != str(article_version_id)
        or str(ast_value.get("source_packet_version_ref"))
        != str(source_packet_version_id)
        or article.article_body_sha256.value != after_ast.sha256
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
    if supplied.status is CoverageStatus.UNEVALUABLE:
        return (
            DraftCoverageDecisionV2.UNAVAILABLE,
            supplied.status,
            None,
            supplied.report_sha256.value,
            receipt.sequence,
        )
    if (
        ast_claim_ids != expected_claim_ids
        or supplied.article_version_id != article.article_version_id
        or supplied.article_body_sha256 != article.article_body_sha256
        or supplied.source_packet_version_id != article.source_packet_version_id
        or supplied.source_packet_content_sha256 != article.source_packet_content_sha256
        or complete_hash != article.complete_claim_set_sha256
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
    if supplied.status is CoverageStatus.BLOCK:
        return (
            DraftCoverageDecisionV2.BLOCKED,
            supplied.status,
            None,
            supplied.report_sha256.value,
            receipt.sequence,
        )
    if (
        supplied.status is not CoverageStatus.PASS
        or supplied.findings
        or supplied.major_requirement_satisfied is not True
        or supplied.all_verifiable_requirement_satisfied is not True
        or report_input is None
        or complete_hash is None
        or major is None
        or all_claims is None
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.COVERAGE_BINDING_MISMATCH)
    binding = CoverageBindingV2(
        article_version_id=article_version_id,
        article_body_sha256=article.article_body_sha256.value,
        source_packet_version_id=source_packet_version_id,
        source_packet_content_sha256=article.source_packet_content_sha256.value,
        complete_claim_ids=tuple(
            sorted((value.value for value in article.complete_claim_ids), key=str)
        ),
        complete_claim_set_sha256=complete_hash.value,
        evaluation_input_sha256=report_input.value,
        report_sha256=supplied.report_sha256.value,
        receipt_sequence=receipt.sequence,
        evaluator_version=supplied.evaluator_version,
        policy_sha256=supplied.policy_sha256.value,
        major_evidenced=major.evidenced,
        major_total=major.total,
        all_verifiable_evidenced=all_claims.evidenced,
        all_verifiable_total=all_claims.total,
    )
    return (
        DraftCoverageDecisionV2.AVAILABLE,
        supplied.status,
        binding,
        supplied.report_sha256.value,
        receipt.sequence,
    )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DraftArticleVersionProposalV2(_RedactedValue):
    durable: DurableSucceededBindingV2
    fixture_sha256: str
    site_id: UUID
    category_id: UUID
    article_id: UUID
    article_version_id: UUID
    source_packet_version_id: UUID
    before_ast: BoundContentAstV2
    after_ast: BoundContentAstV2
    diff: ContentAstDiffV2
    coverage: CoverageBindingV2
    article_state: ArticleState
    version_state: ArticleVersionState
    human_editable: bool
    proposal_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.durable) is not DurableSucceededBindingV2:
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        _require_sha256(self.fixture_sha256)
        for value in (
            self.site_id,
            self.category_id,
            self.article_id,
            self.article_version_id,
            self.source_packet_version_id,
        ):
            _require_uuid(value)
        if (
            type(self.before_ast) is not BoundContentAstV2
            or type(self.after_ast) is not BoundContentAstV2
            or type(self.diff) is not ContentAstDiffV2
            or type(self.coverage) is not CoverageBindingV2
            or self.diff.before_ast_sha256 != self.before_ast.sha256
            or self.diff.after_ast_sha256 != self.after_ast.sha256
            or not self.diff.changed
            or self.durable.article_version_id != self.article_version_id
            or self.durable.source_packet_version_id != self.source_packet_version_id
            or self.coverage.article_version_id != self.article_version_id
            or self.coverage.source_packet_version_id != self.source_packet_version_id
            or self.coverage.article_body_sha256 != self.after_ast.sha256
            or self.article_state is not ArticleState.DRAFT
            or self.version_state is not ArticleVersionState.DRAFT
            or self.human_editable is not True
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        object.__setattr__(
            self,
            "proposal_sha256",
            _canonical_sha256(
                {
                    "after_ast_sha256": self.after_ast.sha256,
                    "article_id": str(self.article_id),
                    "article_state": self.article_state.value,
                    "article_version_id": str(self.article_version_id),
                    "before_ast_sha256": self.before_ast.sha256,
                    "category_id": str(self.category_id),
                    "coverage_binding_sha256": self.coverage.binding_sha256,
                    "diff_sha256": self.diff.diff_sha256,
                    "durable_binding_sha256": self.durable.binding_sha256,
                    "fixture_sha256": self.fixture_sha256,
                    "human_editable": self.human_editable,
                    "site_id": str(self.site_id),
                    "source_packet_version_id": str(self.source_packet_version_id),
                    "version_state": self.version_state.value,
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DraftAdoptionIntentV2(_RedactedValue):
    proposal_sha256: str
    expected_before_ast_sha256: str
    proposed_after_ast_sha256: str
    diff_sha256: str
    effect: str = "PROPOSAL_ONLY"
    apply_performed: bool = False
    merge_performed: bool = False
    persistence_performed: bool = False
    recommendation_order_changed: bool = False
    intent_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        for digest in (
            self.proposal_sha256,
            self.expected_before_ast_sha256,
            self.proposed_after_ast_sha256,
            self.diff_sha256,
        ):
            _require_sha256(digest)
        if (
            self.effect != "PROPOSAL_ONLY"
            or self.apply_performed
            or self.merge_performed
            or self.persistence_performed
            or self.recommendation_order_changed
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        object.__setattr__(
            self,
            "intent_sha256",
            _canonical_sha256(
                {
                    "diff_sha256": self.diff_sha256,
                    "effect": self.effect,
                    "expected_before_ast_sha256": self.expected_before_ast_sha256,
                    "proposal_sha256": self.proposal_sha256,
                    "proposed_after_ast_sha256": self.proposed_after_ast_sha256,
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiDraftIntegrationResultV2(_RedactedValue):
    request_binding_sha256: str
    durable_binding: DurableSucceededBindingV2
    fixture_sha256: str
    coverage_decision: DraftCoverageDecisionV2
    coverage_status: CoverageStatus | None
    coverage_report_sha256: str | None
    coverage_receipt_sequence: int | None
    disposition: DraftProposalDispositionV2
    proposal: DraftArticleVersionProposalV2 | None
    adoption_intent: DraftAdoptionIntentV2 | None
    execution: DraftExecutionV2
    approval_permitted: bool
    apply_performed: bool
    merge_performed: bool
    persistence: DraftExecutionV2
    event_emission: DraftExecutionV2
    publication_permitted: bool
    recommendation_order_changed: bool
    formal_validation: DraftExecutionV2
    live_validation: DraftExecutionV2
    release: DraftExecutionV2
    production_eligible: bool

    def __post_init__(self) -> None:
        _require_sha256(self.request_binding_sha256)
        if type(self.durable_binding) is not DurableSucceededBindingV2:
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        _require_sha256(self.fixture_sha256)
        if type(self.coverage_decision) is not DraftCoverageDecisionV2:
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        if (
            self.coverage_status is not None
            and type(self.coverage_status) is not CoverageStatus
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        if self.coverage_report_sha256 is not None:
            _require_sha256(self.coverage_report_sha256)
        if self.coverage_receipt_sequence is not None and (
            type(self.coverage_receipt_sequence) is not int
            or self.coverage_receipt_sequence < 1
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        available = self.coverage_decision is DraftCoverageDecisionV2.AVAILABLE
        expected_disposition = {
            DraftCoverageDecisionV2.AVAILABLE: DraftProposalDispositionV2.HUMAN_EDITABLE_PROPOSAL_ONLY,
            DraftCoverageDecisionV2.BLOCKED: DraftProposalDispositionV2.BLOCKED,
            DraftCoverageDecisionV2.UNAVAILABLE: DraftProposalDispositionV2.UNAVAILABLE,
        }[self.coverage_decision]
        if (
            self.disposition is not expected_disposition
            or available != (type(self.proposal) is DraftArticleVersionProposalV2)
            or available != (type(self.adoption_intent) is DraftAdoptionIntentV2)
            or (available and self.coverage_status is not CoverageStatus.PASS)
            or (
                self.coverage_decision is DraftCoverageDecisionV2.BLOCKED
                and self.coverage_status is not CoverageStatus.BLOCK
            )
            or (
                self.coverage_decision is DraftCoverageDecisionV2.UNAVAILABLE
                and self.coverage_status not in {None, CoverageStatus.UNEVALUABLE}
            )
            or self.execution is not DraftExecutionV2.RECORDED_ONLY
            or self.approval_permitted
            or self.apply_performed
            or self.merge_performed
            or self.persistence is not DraftExecutionV2.NOT_EXECUTED
            or self.event_emission is not DraftExecutionV2.NOT_EXECUTED
            or self.publication_permitted
            or self.recommendation_order_changed
            or self.formal_validation is not DraftExecutionV2.NOT_EXECUTED
            or self.live_validation is not DraftExecutionV2.NOT_EXECUTED
            or self.release is not DraftExecutionV2.NOT_EXECUTED
            or self.production_eligible
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)
        if available:
            assert self.proposal is not None
            assert self.adoption_intent is not None
            if (
                self.proposal.durable != self.durable_binding
                or self.proposal.fixture_sha256 != self.fixture_sha256
                or self.adoption_intent.proposal_sha256 != self.proposal.proposal_sha256
                or self.adoption_intent.expected_before_ast_sha256
                != self.proposal.before_ast.sha256
                or self.adoption_intent.proposed_after_ast_sha256
                != self.proposal.after_ast.sha256
                or self.adoption_intent.diff_sha256 != self.proposal.diff.diff_sha256
            ):
                fail_ai_draft_v2(AiDraftV2FailureCode.RESULT_MISMATCH)


__all__ = [
    "AI_ARTICLE_DRAFT_TASK_V2",
    "CONTRACT_SHA256",
    "FIXTURE_DOCUMENT_ID",
    "FIXTURE_SCHEMA_VERSION",
    "MAXIMUM_COMPLETE_CLAIMS",
    "MAXIMUM_DIFF_OPERATIONS",
    "MAXIMUM_FIXTURE_BYTES",
    "MAXIMUM_JSON_POINTER_BYTES",
    "POLICY_ID",
    "POLICY_SHA256",
    "AiDraftIntegrationRequestV2",
    "AiDraftIntegrationResultV2",
    "AiDraftV2Activation",
    "AiDraftV2Failure",
    "AiDraftV2FailureCode",
    "BoundContentAstV2",
    "ContentAstDiffOperationV2",
    "ContentAstDiffV2",
    "CoverageBindingV2",
    "DiffOperationKindV2",
    "DraftAdoptionIntentV2",
    "DraftArticleVersionProposalV2",
    "DraftCoverageDecisionV2",
    "DraftExecutionV2",
    "DraftProposalDispositionV2",
    "DurableSucceededBindingV2",
    "RecordedDraftMaterialV2",
    "bind_coverage_v2",
    "bind_durable_succeeded_completion_v2",
    "build_content_ast_diff_v2",
    "fail_ai_draft_v2",
]
