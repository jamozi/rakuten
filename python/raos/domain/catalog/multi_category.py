"""Maximum-safe multi-category values for Canonical ST-1904.

The model can describe only two synthetic, inactive category profiles.  It
does not contain a real category selector, product-identity rule, freshness
override, active template, provider endpoint, credential, or mutation command.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Final, Literal, NoReturn, SupportsIndex, cast


MULTI_CATEGORY_CONTRACT_VERSION: Final = "1.0.0"
MULTI_CATEGORY_PARSER_VERSION: Final = "st1904-recorded-multi-category-json.v1"
MULTI_CATEGORY_FIXTURE_PROFILE: Final = "RAOS_ST1904_SYNTHETIC_MULTI_CATEGORY_V1"
MAX_MULTI_CATEGORY_SOURCE_BYTES: Final = 256 * 1024
EXPECTED_SYNTHETIC_CATEGORY_COUNT: Final = 2

_REDACTED: Final = "<redacted-multi-category>"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_CATEGORY_ID = re.compile(r"synthetic_category_[a-z][a-z0-9_]{0,47}\Z", re.ASCII)
_BINDING_NAME = re.compile(r"[a-z][a-z0-9_]{1,63}\Z", re.ASCII)
_TEMPLATE_ID = re.compile(r"TPL-AT-00[1-5]\Z", re.ASCII)

EXPECTED_BINDING_NAMES: Final = (
    "article_template_schema",
    "freshness_policy",
    "identity_reference_plan",
    "st1702_category_fixture",
    "st1805_portfolio_decision",
    "template_product_comparison",
    "template_selection_guide",
)
EXPECTED_TEMPLATE_CANDIDATES: Final = (
    ("synthetic_category_alpha", "TPL-AT-001", "template_selection_guide"),
    ("synthetic_category_beta", "TPL-AT-003", "template_product_comparison"),
)


class MultiCategoryScope(str, Enum):
    """Closed local states; no live or activation member exists."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY = (
        "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY"
    )


DEFAULT_MULTI_CATEGORY_SCOPE: Final = MultiCategoryScope.DISABLED


class IdentityRuleState(str, Enum):
    NOT_DEFINED_UNRESOLVED_OD_006 = "NOT_DEFINED_UNRESOLVED_OD_006"


class IdentityDisposition(str, Enum):
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class FreshnessRuleState(str, Enum):
    PROVISIONAL_SAFE_DEFAULT_UNMODIFIED = "PROVISIONAL_SAFE_DEFAULT_UNMODIFIED"


class TemplateCandidateState(str, Enum):
    SYNTHETIC_CANDIDATE_NOT_APPLIED = "SYNTHETIC_CANDIDATE_NOT_APPLIED"


class MultiCategoryOutcome(str, Enum):
    INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY = (
        "INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY"
    )


class MultiCategoryBoundaryStatus(str, Enum):
    ABSENT = "ABSENT"
    DEFERRED_POST_MVP = "DEFERRED_POST_MVP"
    DISABLED = "DISABLED"
    FORBIDDEN = "FORBIDDEN"
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_USED = "NOT_USED"
    RELEASE_DECISION_REQUIRED = "RELEASE_DECISION_REQUIRED"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"


class MultiCategoryFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    CATEGORY_APPROVAL_PROHIBITED = "CATEGORY_APPROVAL_PROHIBITED"
    RELEASE_DECISION_PROHIBITED = "RELEASE_DECISION_PROHIBITED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    BINDING_SET_MISMATCH = "BINDING_SET_MISMATCH"
    DUPLICATE_CATEGORY = "DUPLICATE_CATEGORY"
    TEMPLATE_BINDING_MISMATCH = "TEMPLATE_BINDING_MISMATCH"


class MultiCategoryFailure(ValueError):
    """Closed failure that never retains rejected category material."""

    __slots__ = ("code",)

    def __init__(self, code: MultiCategoryFailureCode) -> None:
        if type(code) is not MultiCategoryFailureCode:
            raise TypeError("invalid multi-category failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"MultiCategoryFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("multi-category failures cannot be serialized")


def fail_multi_category(
    code: MultiCategoryFailureCode = MultiCategoryFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise MultiCategoryFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("multi-category values cannot be serialized")


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail_multi_category()


def multi_category_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_multi_category()
    return value


def sha256_bytes(value: object) -> str:
    if type(value) is not bytes:
        fail_multi_category()
    return hashlib.sha256(value).hexdigest()


def _recording_id(value: object) -> str:
    if type(value) is not str or _RECORDING_ID.fullmatch(value) is None:
        fail_multi_category()
    return value


def _category_id(value: object) -> str:
    if type(value) is not str or _CATEGORY_ID.fullmatch(value) is None:
        fail_multi_category(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID)
    return value


def _display_name(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 120
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        fail_multi_category(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_multi_category(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID)
    return value


def _binding_name(value: object) -> str:
    if type(value) is not str or _BINDING_NAME.fullmatch(value) is None:
        fail_multi_category(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID)
    return value


def _template_id(value: object) -> str:
    if type(value) is not str or _TEMPLATE_ID.fullmatch(value) is None:
        fail_multi_category(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID)
    return value


def _bounded_source_bytes(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_MULTI_CATEGORY_SOURCE_BYTES:
        fail_multi_category()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class MultiCategorySourceBinding(_RedactedValue):
    name: str
    sha256: str

    def __post_init__(self) -> None:
        _binding_name(self.name)
        multi_category_sha256(self.sha256)


def binding_set_sha256(bindings: object) -> str:
    if type(bindings) is not tuple:
        fail_multi_category()
    candidate = cast(tuple[object, ...], bindings)
    if any(type(binding) is not MultiCategorySourceBinding for binding in candidate):
        fail_multi_category()
    typed = cast(tuple[MultiCategorySourceBinding, ...], candidate)
    return sha256_bytes(
        canonical_json_bytes(
            [{"name": binding.name, "sha256": binding.sha256} for binding in typed]
        )
    )


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticCategoryProfile(_RedactedValue):
    category_id: str
    display_name: str
    synthetic: Literal[True]
    real_category_selected: Literal[False]
    identity_rule_state: IdentityRuleState
    identity_disposition: IdentityDisposition
    automatic_merge_enabled: Literal[False]
    automatic_split_enabled: Literal[False]
    freshness_rule_state: FreshnessRuleState
    freshness_policy_id: Literal["RAOS-CONTENT-FRESH-001"]
    freshness_policy_version: Literal["1.0.0"]
    category_override: None
    provider_override: None
    stale_never_fresh: Literal[True]
    recommendation_auto_reorder: Literal["FORBIDDEN"]
    template_id: str
    template_sha256: str
    template_state: TemplateCandidateState
    template_active: Literal[False]
    human_review_required: Literal[True]

    def __post_init__(self) -> None:
        _category_id(self.category_id)
        _display_name(self.display_name)
        _template_id(self.template_id)
        multi_category_sha256(self.template_sha256)
        if (
            self.synthetic is not True
            or self.real_category_selected is not False
            or self.identity_rule_state
            is not IdentityRuleState.NOT_DEFINED_UNRESOLVED_OD_006
            or self.identity_disposition
            is not IdentityDisposition.HUMAN_REVIEW_REQUIRED
            or self.automatic_merge_enabled is not False
            or self.automatic_split_enabled is not False
            or self.freshness_rule_state
            is not FreshnessRuleState.PROVISIONAL_SAFE_DEFAULT_UNMODIFIED
            or self.freshness_policy_id != "RAOS-CONTENT-FRESH-001"
            or self.freshness_policy_version != "1.0.0"
            or self.category_override is not None
            or self.provider_override is not None
            or self.stale_never_fresh is not True
            or self.recommendation_auto_reorder != "FORBIDDEN"
            or self.template_state
            is not TemplateCandidateState.SYNTHETIC_CANDIDATE_NOT_APPLIED
            or self.template_active is not False
            or self.human_review_required is not True
        ):
            fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class MultiCategoryEvaluationCommand(_RedactedValue):
    recording_id: str
    source_sha256: str
    source_bytes: int
    expected_binding_set_sha256: str
    scope: MultiCategoryScope = DEFAULT_MULTI_CATEGORY_SCOPE
    category_approval_sha256: str | None = None
    release_decision_sha256: str | None = None
    parser_version: str = MULTI_CATEGORY_PARSER_VERSION

    def __post_init__(self) -> None:
        _recording_id(self.recording_id)
        multi_category_sha256(self.source_sha256)
        _bounded_source_bytes(self.source_bytes)
        multi_category_sha256(self.expected_binding_set_sha256)
        if (
            type(self.scope) is not MultiCategoryScope
            or self.parser_version != MULTI_CATEGORY_PARSER_VERSION
        ):
            fail_multi_category()
        if self.category_approval_sha256 is not None:
            fail_multi_category(MultiCategoryFailureCode.CATEGORY_APPROVAL_PROHIBITED)
        if self.release_decision_sha256 is not None:
            fail_multi_category(MultiCategoryFailureCode.RELEASE_DECISION_PROHIBITED)

    @property
    def command_sha256(self) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "category_approval_sha256": None,
                    "expected_binding_set_sha256": self.expected_binding_set_sha256,
                    "parser_version": self.parser_version,
                    "recording_id": self.recording_id,
                    "release_decision_sha256": None,
                    "scope": self.scope.value,
                    "source_bytes": self.source_bytes,
                    "source_sha256": self.source_sha256,
                }
            )
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedMultiCategoryBundle(_RedactedValue):
    recording_id: str
    source_sha256: str
    command_sha256: str
    fixture_profile: str
    parser_version: str
    bindings: tuple[MultiCategorySourceBinding, ...]
    categories: tuple[SyntheticCategoryProfile, ...]
    runtime_enabled: Literal[False]
    persistence_enabled: Literal[False]
    provider_access_enabled: Literal[False]
    network_enabled: Literal[False]
    identity_decisions_applied: Literal[False]
    freshness_overrides_applied: Literal[False]
    templates_activated: Literal[False]
    editorial_mutation_enabled: Literal[False]
    recommendation_mutation_enabled: Literal[False]
    publication_authorized: Literal[False]
    release_authorized: Literal[False]
    production_authorized: Literal[False]

    def require_valid(self) -> None:
        _recording_id(self.recording_id)
        multi_category_sha256(self.source_sha256)
        multi_category_sha256(self.command_sha256)
        if (
            self.fixture_profile != MULTI_CATEGORY_FIXTURE_PROFILE
            or self.parser_version != MULTI_CATEGORY_PARSER_VERSION
            or type(self.bindings) is not tuple
            or type(self.categories) is not tuple
            or any(
                type(binding) is not MultiCategorySourceBinding
                for binding in self.bindings
            )
            or any(
                type(category) is not SyntheticCategoryProfile
                for category in self.categories
            )
            or tuple(binding.name for binding in self.bindings)
            != EXPECTED_BINDING_NAMES
            or len({binding.name for binding in self.bindings}) != len(self.bindings)
            or len(self.categories) != EXPECTED_SYNTHETIC_CATEGORY_COUNT
            or len({category.category_id for category in self.categories})
            != len(self.categories)
            or any(
                value is not False
                for value in (
                    self.runtime_enabled,
                    self.persistence_enabled,
                    self.provider_access_enabled,
                    self.network_enabled,
                    self.identity_decisions_applied,
                    self.freshness_overrides_applied,
                    self.templates_activated,
                    self.editorial_mutation_enabled,
                    self.recommendation_mutation_enabled,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_authorized,
                )
            )
        ):
            fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)
        binding_map = {binding.name: binding.sha256 for binding in self.bindings}
        observed_candidates = tuple(
            (
                category.category_id,
                category.template_id,
                (
                    "template_selection_guide"
                    if category.template_id == "TPL-AT-001"
                    else "template_product_comparison"
                ),
            )
            for category in self.categories
        )
        if observed_candidates != EXPECTED_TEMPLATE_CANDIDATES:
            fail_multi_category(MultiCategoryFailureCode.TEMPLATE_BINDING_MISMATCH)
        for category, (_category_id_value, _template_id_value, binding_name) in zip(
            self.categories, EXPECTED_TEMPLATE_CANDIDATES, strict=True
        ):
            if category.template_sha256 != binding_map[binding_name]:
                fail_multi_category(MultiCategoryFailureCode.TEMPLATE_BINDING_MISMATCH)

    @property
    def binding_set_sha256(self) -> str:
        self.require_valid()
        return binding_set_sha256(self.bindings)

    @property
    def bundle_sha256(self) -> str:
        self.require_valid()
        return sha256_bytes(canonical_json_bytes(bundle_projection(self)))


def category_projection(category: SyntheticCategoryProfile) -> dict[str, object]:
    if type(category) is not SyntheticCategoryProfile:
        fail_multi_category()
    category.__post_init__()
    return {
        "category_id": category.category_id,
        "display_name": category.display_name,
        "freshness": {
            "category_override": None,
            "policy_id": category.freshness_policy_id,
            "policy_version": category.freshness_policy_version,
            "provider_override": None,
            "recommendation_auto_reorder": category.recommendation_auto_reorder,
            "stale_never_fresh": category.stale_never_fresh,
            "state": category.freshness_rule_state.value,
        },
        "human_review_required": category.human_review_required,
        "identity": {
            "automatic_merge_enabled": category.automatic_merge_enabled,
            "automatic_split_enabled": category.automatic_split_enabled,
            "disposition": category.identity_disposition.value,
            "rule_state": category.identity_rule_state.value,
        },
        "real_category_selected": category.real_category_selected,
        "synthetic": category.synthetic,
        "template": {
            "active": category.template_active,
            "sha256": category.template_sha256,
            "state": category.template_state.value,
            "template_id": category.template_id,
        },
    }


def bundle_projection(bundle: RecordedMultiCategoryBundle) -> dict[str, object]:
    if type(bundle) is not RecordedMultiCategoryBundle:
        fail_multi_category()
    return {
        "authority": {
            "editorial_mutation_enabled": bundle.editorial_mutation_enabled,
            "freshness_overrides_applied": bundle.freshness_overrides_applied,
            "identity_decisions_applied": bundle.identity_decisions_applied,
            "network_enabled": bundle.network_enabled,
            "persistence_enabled": bundle.persistence_enabled,
            "provider_access_enabled": bundle.provider_access_enabled,
            "publication_authorized": bundle.publication_authorized,
            "recommendation_mutation_enabled": (bundle.recommendation_mutation_enabled),
            "release_authorized": bundle.release_authorized,
            "runtime_enabled": bundle.runtime_enabled,
            "templates_activated": bundle.templates_activated,
            "production_authorized": bundle.production_authorized,
        },
        "bindings": [
            {"name": binding.name, "sha256": binding.sha256}
            for binding in bundle.bindings
        ],
        "categories": [category_projection(category) for category in bundle.categories],
        "command_sha256": bundle.command_sha256,
        "fixture_profile": bundle.fixture_profile,
        "parser_version": bundle.parser_version,
        "recording_id": bundle.recording_id,
        "source_sha256": bundle.source_sha256,
    }


@dataclass(frozen=True, slots=True, repr=False)
class MultiCategoryEvaluationReport(_RedactedValue):
    recording_id: str
    source_sha256: str
    command_sha256: str
    binding_set_sha256: str
    bundle_sha256: str
    category_ids: tuple[str, ...]
    template_candidates: tuple[tuple[str, str], ...]
    human_review_category_count: int
    freshness_safe_default_count: int
    outcome: MultiCategoryOutcome
    blockers: tuple[str, ...]
    report_sha256: str
    scope: MultiCategoryScope
    default_scope: MultiCategoryScope = DEFAULT_MULTI_CATEGORY_SCOPE
    authority: Literal["NONE"] = "NONE"
    category_selection: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
    )
    identity_rules: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
    )
    freshness_sla: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
    )
    category_activation: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.DISABLED
    )
    template_activation: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.DISABLED
    )
    release_decision: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.RELEASE_DECISION_REQUIRED
    )
    provider: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.NOT_USED
    network: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.FORBIDDEN
    credentials: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.NOT_USED
    persistence: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.NOT_EXECUTED
    editorial_mutation: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.FORBIDDEN
    )
    recommendation_mutation: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.FORBIDDEN
    )
    publication: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.FORBIDDEN
    formal_tst_032: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.NOT_EXECUTED
    )
    canonical_status: MultiCategoryBoundaryStatus = (
        MultiCategoryBoundaryStatus.DEFERRED_POST_MVP
    )
    staging: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.NOT_EXECUTED
    production: MultiCategoryBoundaryStatus = MultiCategoryBoundaryStatus.NOT_EXECUTED

    def require_valid(self) -> None:
        _recording_id(self.recording_id)
        for digest in (
            self.source_sha256,
            self.command_sha256,
            self.binding_set_sha256,
            self.bundle_sha256,
            self.report_sha256,
        ):
            multi_category_sha256(digest)
        if (
            self.category_ids
            != tuple(category_id for category_id, _template in self.template_candidates)
            or len(self.category_ids) != EXPECTED_SYNTHETIC_CATEGORY_COUNT
            or len(set(self.category_ids)) != len(self.category_ids)
            or tuple(self.category_ids)
            != tuple(candidate[0] for candidate in EXPECTED_TEMPLATE_CANDIDATES)
            or tuple(template for _category, template in self.template_candidates)
            != tuple(candidate[1] for candidate in EXPECTED_TEMPLATE_CANDIDATES)
            or self.human_review_category_count != EXPECTED_SYNTHETIC_CATEGORY_COUNT
            or self.freshness_safe_default_count != EXPECTED_SYNTHETIC_CATEGORY_COUNT
            or self.outcome
            is not MultiCategoryOutcome.INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY
            or self.blockers != tuple(sorted(set(self.blockers)))
            or self.scope
            is not MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
            or self.default_scope is not MultiCategoryScope.DISABLED
            or self.authority != "NONE"
            or self.category_selection
            is not MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
            or self.identity_rules
            is not MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
            or self.freshness_sla
            is not MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
            or self.category_activation is not MultiCategoryBoundaryStatus.DISABLED
            or self.template_activation is not MultiCategoryBoundaryStatus.DISABLED
            or self.release_decision
            is not MultiCategoryBoundaryStatus.RELEASE_DECISION_REQUIRED
            or self.provider is not MultiCategoryBoundaryStatus.NOT_USED
            or self.network is not MultiCategoryBoundaryStatus.FORBIDDEN
            or self.credentials is not MultiCategoryBoundaryStatus.NOT_USED
            or self.persistence is not MultiCategoryBoundaryStatus.NOT_EXECUTED
            or self.editorial_mutation is not MultiCategoryBoundaryStatus.FORBIDDEN
            or self.recommendation_mutation is not MultiCategoryBoundaryStatus.FORBIDDEN
            or self.publication is not MultiCategoryBoundaryStatus.FORBIDDEN
            or self.formal_tst_032 is not MultiCategoryBoundaryStatus.NOT_EXECUTED
            or self.canonical_status
            is not MultiCategoryBoundaryStatus.DEFERRED_POST_MVP
            or self.staging is not MultiCategoryBoundaryStatus.NOT_EXECUTED
            or self.production is not MultiCategoryBoundaryStatus.NOT_EXECUTED
            or self.report_sha256
            != sha256_bytes(canonical_json_bytes(_report_projection_unchecked(self)))
        ):
            fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)


def _report_projection_unchecked(
    report: MultiCategoryEvaluationReport,
) -> dict[str, object]:
    return {
        "authority": report.authority,
        "binding_set_sha256": report.binding_set_sha256,
        "blockers": list(report.blockers),
        "boundary": {
            "canonical_status": report.canonical_status.value,
            "category_activation": report.category_activation.value,
            "category_selection": report.category_selection.value,
            "credentials": report.credentials.value,
            "editorial_mutation": report.editorial_mutation.value,
            "formal_tst_032": report.formal_tst_032.value,
            "freshness_sla": report.freshness_sla.value,
            "identity_rules": report.identity_rules.value,
            "network": report.network.value,
            "persistence": report.persistence.value,
            "production": report.production.value,
            "provider": report.provider.value,
            "publication": report.publication.value,
            "recommendation_mutation": report.recommendation_mutation.value,
            "release_decision": report.release_decision.value,
            "staging": report.staging.value,
            "template_activation": report.template_activation.value,
        },
        "bundle_sha256": report.bundle_sha256,
        "category_ids": list(report.category_ids),
        "command_sha256": report.command_sha256,
        "freshness_safe_default_count": report.freshness_safe_default_count,
        "human_review_category_count": report.human_review_category_count,
        "outcome": report.outcome.value,
        "recording_id": report.recording_id,
        "scope": report.scope.value,
        "source_sha256": report.source_sha256,
        "template_candidates": [
            {"category_id": category_id, "template_id": template_id}
            for category_id, template_id in report.template_candidates
        ],
    }


def report_projection(report: MultiCategoryEvaluationReport) -> dict[str, object]:
    if type(report) is not MultiCategoryEvaluationReport:
        fail_multi_category()
    report.require_valid()
    return _report_projection_unchecked(report) | {
        "report_sha256": report.report_sha256
    }


def finalize_report(
    report: MultiCategoryEvaluationReport,
) -> MultiCategoryEvaluationReport:
    if type(report) is not MultiCategoryEvaluationReport:
        fail_multi_category()
    finalized = replace(
        report,
        report_sha256=sha256_bytes(
            canonical_json_bytes(_report_projection_unchecked(report))
        ),
    )
    finalized.require_valid()
    return finalized


def validate_bundle(candidate: object) -> RecordedMultiCategoryBundle:
    if type(candidate) is not RecordedMultiCategoryBundle:
        fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)
    try:
        for binding in candidate.bindings:
            binding.__post_init__()
        for category in candidate.categories:
            category.__post_init__()
        candidate.require_valid()
    except MultiCategoryFailure:
        raise
    except Exception:
        fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)
    return candidate


__all__ = (
    "DEFAULT_MULTI_CATEGORY_SCOPE",
    "EXPECTED_BINDING_NAMES",
    "EXPECTED_SYNTHETIC_CATEGORY_COUNT",
    "EXPECTED_TEMPLATE_CANDIDATES",
    "FreshnessRuleState",
    "IdentityDisposition",
    "IdentityRuleState",
    "MAX_MULTI_CATEGORY_SOURCE_BYTES",
    "MULTI_CATEGORY_CONTRACT_VERSION",
    "MULTI_CATEGORY_FIXTURE_PROFILE",
    "MULTI_CATEGORY_PARSER_VERSION",
    "MultiCategoryBoundaryStatus",
    "MultiCategoryEvaluationCommand",
    "MultiCategoryEvaluationReport",
    "MultiCategoryFailure",
    "MultiCategoryFailureCode",
    "MultiCategoryOutcome",
    "MultiCategoryScope",
    "MultiCategorySourceBinding",
    "RecordedMultiCategoryBundle",
    "SyntheticCategoryProfile",
    "TemplateCandidateState",
    "binding_set_sha256",
    "bundle_projection",
    "canonical_json_bytes",
    "category_projection",
    "fail_multi_category",
    "finalize_report",
    "multi_category_sha256",
    "report_projection",
    "sha256_bytes",
    "validate_bundle",
)
