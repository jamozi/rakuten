"""Fail-closed ENV-DEV/CI evaluation seam for Canonical ST-1904."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.multi_category import (
    MultiCategoryEvaluationCommand,
    MultiCategoryEvaluationReport,
    MultiCategoryFailure,
    MultiCategoryFailureCode,
    MultiCategoryOutcome,
    MultiCategoryScope,
    RecordedMultiCategoryBundle,
    fail_multi_category,
    finalize_report,
    validate_bundle,
)
from raos.ports.multi_category import RecordedMultiCategorySource


_BLOCKERS = (
    "FORMAL_TST_032_NOT_EXECUTED",
    "OD_001_CATEGORY_SELECTION_UNRESOLVED",
    "OD_006_IDENTITY_RULES_UNRESOLVED",
    "OD_007_FRESHNESS_SLA_UNRESOLVED",
    "PRODUCT_OWNER_PORTFOLIO_DECISION_ABSENT",
    "RECORDED_SYNTHETIC_ONLY",
    "RELEASE_DECISION_ABSENT",
    "ST1805_NO_DECISION",
)


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> MultiCategoryEvaluationCommand:
    if type(candidate) is not MultiCategoryEvaluationCommand:
        fail_multi_category()
    try:
        return MultiCategoryEvaluationCommand(
            recording_id=candidate.recording_id,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            expected_binding_set_sha256=candidate.expected_binding_set_sha256,
            scope=candidate.scope,
            category_approval_sha256=candidate.category_approval_sha256,
            release_decision_sha256=candidate.release_decision_sha256,
            parser_version=candidate.parser_version,
        )
    except MultiCategoryFailure:
        raise
    except Exception:
        fail_multi_category()


def evaluate_recorded_multi_category(
    bundle: RecordedMultiCategoryBundle,
) -> MultiCategoryEvaluationReport:
    """Summarize compatibility without selecting or activating a category."""

    normalized = validate_bundle(bundle)
    category_ids = tuple(category.category_id for category in normalized.categories)
    template_candidates = tuple(
        (category.category_id, category.template_id)
        for category in normalized.categories
    )
    provisional = MultiCategoryEvaluationReport(
        recording_id=normalized.recording_id,
        source_sha256=normalized.source_sha256,
        command_sha256=normalized.command_sha256,
        binding_set_sha256=normalized.binding_set_sha256,
        bundle_sha256=normalized.bundle_sha256,
        category_ids=category_ids,
        template_candidates=template_candidates,
        human_review_category_count=sum(
            1 for category in normalized.categories if category.human_review_required
        ),
        freshness_safe_default_count=sum(
            1
            for category in normalized.categories
            if category.category_override is None
            and category.provider_override is None
            and category.stale_never_fresh
        ),
        outcome=(MultiCategoryOutcome.INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY),
        blockers=_BLOCKERS,
        report_sha256="0" * 64,
        scope=MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY,
    )
    return finalize_report(provisional)


@final
class MultiCategoryEvaluationService:
    """Call one recorded source only when the explicit local scope is enabled."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: RecordedMultiCategorySource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), RecordedMultiCategorySource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_multi_category()
        self._source = source

    def evaluate(
        self, command: MultiCategoryEvaluationCommand
    ) -> MultiCategoryEvaluationReport:
        normalized = _validated_command(command)
        if (
            normalized.scope
            is not MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
        ):
            fail_multi_category(MultiCategoryFailureCode.FEATURE_DISABLED)
        observed: object = None
        try:
            observed = self._source.read(normalized)
        except MultiCategoryFailure:
            raise
        except Exception:
            fail_multi_category(MultiCategoryFailureCode.SOURCE_UNAVAILABLE)
        if type(observed) is not RecordedMultiCategoryBundle:
            fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)
        result = validate_bundle(observed)
        if (
            result.recording_id != normalized.recording_id
            or result.source_sha256 != normalized.source_sha256
            or result.command_sha256 != normalized.command_sha256
            or result.binding_set_sha256 != normalized.expected_binding_set_sha256
        ):
            fail_multi_category(MultiCategoryFailureCode.SOURCE_RESULT_INVALID)
        return evaluate_recorded_multi_category(result)


__all__ = (
    "MultiCategoryEvaluationService",
    "evaluate_recorded_multi_category",
)
