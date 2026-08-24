"""Fail-closed ENV-DEV/CI evaluator for the disabled ST-1903 seam."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.partial_auto_publication import (
    PartialAutoPublicationCommand,
    PartialAutoPublicationFailure,
    PartialAutoPublicationFailureCode,
    PartialAutoPublicationReport,
    PartialAutoPublicationScope,
    RecordedPartialAutoPublicationBundle,
    evaluate_partial_auto_publication,
    fail_partial_auto_publication,
)
from raos.ports.publishing.partial_auto_publication import (
    PartialAutoPublicationEvidenceSource,
)


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> PartialAutoPublicationCommand:
    if type(candidate) is not PartialAutoPublicationCommand:
        fail_partial_auto_publication()
    try:
        return PartialAutoPublicationCommand(
            recording_id=candidate.recording_id,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            scope=candidate.scope,
            parser_version=candidate.parser_version,
            release_decision_sha256=candidate.release_decision_sha256,
        )
    except PartialAutoPublicationFailure:
        raise
    except Exception:
        fail_partial_auto_publication()


def _validated_bundle(
    candidate: object,
    command: PartialAutoPublicationCommand,
) -> RecordedPartialAutoPublicationBundle:
    if type(candidate) is not RecordedPartialAutoPublicationBundle:
        fail_partial_auto_publication(
            PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
        )
    try:
        rebuilt = RecordedPartialAutoPublicationBundle(
            recording_id=candidate.recording_id,
            command_sha256=candidate.command_sha256,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            fixture_profile=candidate.fixture_profile,
            parser_version=candidate.parser_version,
            candidate=candidate.candidate,
            dependency=candidate.dependency,
            gates=candidate.gates,
        )
    except PartialAutoPublicationFailure:
        raise
    except Exception:
        fail_partial_auto_publication(
            PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
        )
    if (
        rebuilt.recording_id != command.recording_id
        or rebuilt.command_sha256 != command.canonical_sha256
        or rebuilt.source_sha256 != command.source_sha256
        or rebuilt.source_bytes != command.source_bytes
        or rebuilt.parser_version != command.parser_version
    ):
        fail_partial_auto_publication(
            PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
        )
    return rebuilt


@final
class PartialAutoPublicationEvaluationService:
    """Evaluate metadata without approval, release, or write authority."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: PartialAutoPublicationEvidenceSource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), PartialAutoPublicationEvidenceSource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_partial_auto_publication()
        self._source = source

    def evaluate(
        self,
        command: PartialAutoPublicationCommand,
    ) -> PartialAutoPublicationReport:
        normalized = _validated_command(command)
        if (
            normalized.scope
            is not PartialAutoPublicationScope.RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY
        ):
            fail_partial_auto_publication(
                PartialAutoPublicationFailureCode.FEATURE_DISABLED
            )
        observed: object = None
        try:
            observed = self._source.read(normalized)
        except PartialAutoPublicationFailure:
            raise
        except Exception:
            fail_partial_auto_publication(
                PartialAutoPublicationFailureCode.SOURCE_UNAVAILABLE
            )
        bundle = _validated_bundle(observed, normalized)
        return evaluate_partial_auto_publication(bundle)


__all__ = ("PartialAutoPublicationEvaluationService",)
