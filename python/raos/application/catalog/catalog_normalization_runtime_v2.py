"""One-step recorded catalog-normalization application service for ST-0503 V2."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogCommitRecoveryOutcomeV2,
    CatalogCommitRecoveryV2,
    CatalogNormalizationBatchV2,
    CatalogNormalizationCommandV2,
    CatalogNormalizationResultV2,
    CatalogNormalizationRuntimeFailure,
    CatalogNormalizationRuntimeFailureCode,
    CatalogNormalizedOutboxEventV2,
    CatalogReplayStatusV2,
    CatalogSourceModeV2,
    PersistedCatalogNormalizationV2,
    fail_catalog_normalization_runtime,
    normalize_persisted_item_search_page_v2,
    persisted_catalog_normalization_from_mapping_v2,
    persisted_catalog_normalization_mapping_v2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    IngestionStepOutcomeV2,
    ItemSearchIngestionSessionV2,
    ItemSearchPlanV2,
    ItemSearchProviderObservationV2,
    ItemSearchSortV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchItemV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    ProviderObservationKindV2,
    ProviderTextTrustV2,
    RateLimitObservationV2,
    RawArchiveReceiptV2,
    SecretNameBindingV2,
    SecretTransportV2,
    UntrustedProviderTextV2,
    parse_item_search_page_v2,
)
from raos.ports.catalog_normalization_runtime_v2 import (
    CatalogNormalizationUnitOfWorkStoreV2,
    PersistedItemSearchPageSourceV2,
)


T = TypeVar("T")


def _runtime_failure_code(
    error: CatalogNormalizationRuntimeFailure,
    fallback: CatalogNormalizationRuntimeFailureCode,
) -> CatalogNormalizationRuntimeFailureCode:
    if type(error) is CatalogNormalizationRuntimeFailure:
        try:
            code = error.code
        except Exception:
            return fallback
        if type(code) is CatalogNormalizationRuntimeFailureCode:
            return code
    return fallback


def _collaborator_call(
    call: Callable[[], T],
    *,
    failure_code: CatalogNormalizationRuntimeFailureCode,
) -> T:
    try:
        return call()
    except CatalogNormalizationRuntimeFailure as error:
        sanitized_code = _runtime_failure_code(error, failure_code)
    except Exception:
        sanitized_code = failure_code
    fail_catalog_normalization_runtime(sanitized_code)


def _copy_plan(value: object) -> ItemSearchPlanV2:
    if type(value) is not ItemSearchPlanV2:
        fail_catalog_normalization_runtime()
    plan = value
    return ItemSearchPlanV2(
        keyword=plan.keyword,
        shop_code=plan.shop_code,
        item_code=plan.item_code,
        genre_id=plan.genre_id,
        hits=plan.hits,
        sort=ItemSearchSortV2(plan.sort.value),
        min_price_jpy=plan.min_price_jpy,
        max_price_jpy=plan.max_price_jpy,
        or_flag=plan.or_flag,
        availability=plan.availability,
        postage_included_only=plan.postage_included_only,
        appoint_delivery_date_only=plan.appoint_delivery_date_only,
        attribute_flag=plan.attribute_flag,
        genre_information_flag=plan.genre_information_flag,
        max_pages=plan.max_pages,
        retry_delays_seconds=tuple(plan.retry_delays_seconds),
        circuit_failure_threshold=plan.circuit_failure_threshold,
        circuit_cooldown_seconds=plan.circuit_cooldown_seconds,
    )


def _copy_secret_binding(value: object) -> SecretNameBindingV2:
    if type(value) is not SecretNameBindingV2:
        fail_catalog_normalization_runtime()
    binding = value
    return SecretNameBindingV2(
        provider_name=binding.provider_name,
        secret_name=binding.secret_name,
        transport=SecretTransportV2(binding.transport.value),
        required=binding.required,
    )


def _copy_request(value: object) -> ItemSearchWireRequestV2:
    if type(value) is not ItemSearchWireRequestV2:
        fail_catalog_normalization_runtime()
    request = value
    return ItemSearchWireRequestV2(
        plan_fingerprint=request.plan_fingerprint,
        page=request.page,
        origin=request.origin,
        endpoint_path=request.endpoint_path,
        parameter_pairs=tuple((pair[0], pair[1]) for pair in request.parameter_pairs),
        canonical_query=bytes(request.canonical_query),
        request_fingerprint=request.request_fingerprint,
        secret_name_bindings=tuple(
            _copy_secret_binding(binding) for binding in request.secret_name_bindings
        ),
    )


def _copy_rate(value: object) -> RateLimitObservationV2:
    if type(value) is not RateLimitObservationV2:
        fail_catalog_normalization_runtime()
    rate = value
    return RateLimitObservationV2(
        limit=rate.limit,
        remaining=rate.remaining,
        reset_at=rate.reset_at,
    )


def _copy_provider_text(value: object) -> UntrustedProviderTextV2:
    if type(value) is not UntrustedProviderTextV2:
        fail_catalog_normalization_runtime()
    text = value
    return UntrustedProviderTextV2(
        value=text.value,
        trust=ProviderTextTrustV2.UNTRUSTED_DATA,
    )


def _copy_optional_provider_text(
    value: object,
) -> UntrustedProviderTextV2 | None:
    return None if value is None else _copy_provider_text(value)


def _copy_item(value: object) -> ParsedItemSearchItemV2:
    if type(value) is not ParsedItemSearchItemV2:
        fail_catalog_normalization_runtime()
    item = value
    return ParsedItemSearchItemV2(
        item_code=_copy_provider_text(item.item_code),
        item_name=_copy_provider_text(item.item_name),
        catchcopy=_copy_optional_provider_text(item.catchcopy),
        item_caption=_copy_optional_provider_text(item.item_caption),
        item_price_jpy=item.item_price_jpy,
        item_url=item.item_url,
        affiliate_url=item.affiliate_url,
        shop_code=_copy_provider_text(item.shop_code),
        shop_name=_copy_optional_provider_text(item.shop_name),
        genre_id=item.genre_id,
        availability=item.availability,
        postage_included=item.postage_included,
        image_urls=tuple(item.image_urls),
    )


def _copy_page(value: object) -> ParsedItemSearchPageV2:
    if type(value) is not ParsedItemSearchPageV2:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
        )
    page = value
    return ParsedItemSearchPageV2(
        request_fingerprint=page.request_fingerprint,
        raw_sha256=page.raw_sha256,
        observed_at=page.observed_at,
        page=page.page,
        page_count=page.page_count,
        count=page.count,
        hits=page.hits,
        first=page.first,
        last=page.last,
        items=tuple(_copy_item(item) for item in page.items),
        rate=_copy_rate(page.rate),
    )


def _copy_receipt(value: object) -> RawArchiveReceiptV2:
    if type(value) is not RawArchiveReceiptV2:
        fail_catalog_normalization_runtime()
    receipt = value
    return RawArchiveReceiptV2(
        receipt_id=receipt.receipt_id,
        artifact_sha256=receipt.artifact_sha256,
        byte_size=receipt.byte_size,
        artifact_version=receipt.artifact_version,
        logical_key=receipt.logical_key,
        request_fingerprint=receipt.request_fingerprint,
        page=receipt.page,
        observed_at=receipt.observed_at,
    )


def _copy_session(value: object) -> ItemSearchIngestionSessionV2:
    if type(value) is not ItemSearchIngestionSessionV2:
        fail_catalog_normalization_runtime()
    session = value
    return ItemSearchIngestionSessionV2(
        session_id=session.session_id,
        plan=_copy_plan(session.plan),
        state=type(session.state)(session.state.value),
        next_page=session.next_page,
        completed_pages=session.completed_pages,
        current_attempt=session.current_attempt,
        consecutive_failures=session.consecutive_failures,
        next_allowed_at=session.next_allowed_at,
        seen_request_fingerprints=tuple(session.seen_request_fingerprints),
        seen_response_sha256=tuple(session.seen_response_sha256),
        seen_item_fingerprints=tuple(session.seen_item_fingerprints),
        last_failure_class=(
            None
            if session.last_failure_class is None
            else ProviderFailureClassV2(session.last_failure_class.value)
        ),
        version=session.version,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _copy_source_step(value: object) -> PersistedItemSearchStepV2:
    if type(value) is not PersistedItemSearchStepV2:
        fail_catalog_normalization_runtime()
    step = value
    return PersistedItemSearchStepV2(
        outcome=IngestionStepOutcomeV2(step.outcome.value),
        session=_copy_session(step.session),
        request_fingerprint=step.request_fingerprint,
        receipt=None if step.receipt is None else _copy_receipt(step.receipt),
        failure_class=(
            None
            if step.failure_class is None
            else ProviderFailureClassV2(step.failure_class.value)
        ),
    )


def _copy_command(value: object) -> CatalogNormalizationCommandV2:
    try:
        if type(value) is not CatalogNormalizationCommandV2:
            fail_catalog_normalization_runtime()
        command = value
        return CatalogNormalizationCommandV2(
            operation_id=command.operation_id,
            source_step=_copy_source_step(command.source_step),
            source_request=_copy_request(command.source_request),
            expected_catalog_version=command.expected_catalog_version,
            normalized_at=command.normalized_at,
            normalizer_version=command.normalizer_version,
            source_binding_sha256=command.source_binding_sha256,
            payload_fingerprint=command.payload_fingerprint,
        )
    except CatalogNormalizationRuntimeFailure:
        raise
    except Exception:
        fail_catalog_normalization_runtime()


def _copy_persisted(value: object) -> PersistedCatalogNormalizationV2:
    try:
        if type(value) is not PersistedCatalogNormalizationV2:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
            )
        return persisted_catalog_normalization_from_mapping_v2(
            persisted_catalog_normalization_mapping_v2(value)
        )
    except CatalogNormalizationRuntimeFailure:
        raise
    except Exception:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
        )


def _source_mode(source: PersistedItemSearchPageSourceV2) -> CatalogSourceModeV2:
    candidate = _collaborator_call(
        lambda: source.mode,
        failure_code=CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE,
    )
    if type(candidate) is not CatalogSourceModeV2:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
        )
    return candidate


def _source_action_count(source: PersistedItemSearchPageSourceV2) -> int:
    candidate = _collaborator_call(
        lambda: source.external_action_count,
        failure_code=CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE,
    )
    if type(candidate) is not int or candidate != 0:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
        )
    return candidate


def _validate_persisted_for_command(
    *,
    command: CatalogNormalizationCommandV2,
    persisted: PersistedCatalogNormalizationV2,
) -> None:
    snapshot = persisted.batch.source_snapshot
    receipt = cast(RawArchiveReceiptV2, command.source_step.receipt)
    if (
        persisted.operation_id != command.operation_id
        or persisted.payload_fingerprint != command.payload_fingerprint
        or persisted.catalog_version != command.expected_catalog_version + 1
        or persisted.batch.expected_catalog_version != command.expected_catalog_version
        or snapshot.source_session_id != command.source_step.session.session_id
        or snapshot.source_session_version != command.source_step.session.version
        or snapshot.receipt_id != receipt.receipt_id
        or snapshot.request_fingerprint != receipt.request_fingerprint
        or snapshot.raw_sha256 != receipt.artifact_sha256
        or snapshot.raw_byte_size != receipt.byte_size
        or snapshot.artifact_version != receipt.artifact_version
        or snapshot.page != receipt.page
        or snapshot.observed_at != receipt.observed_at
        or snapshot.normalized_at != command.normalized_at
        or persisted.event.batch_id != persisted.batch.batch_id
        or persisted.event.source_snapshot_id != snapshot.snapshot_id
        or persisted.event != CatalogNormalizedOutboxEventV2.from_batch(persisted.batch)
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT
        )


@final
class CatalogNormalizationRuntimeServiceV2:
    """Read one recorded page and atomically commit one normalization batch."""

    __slots__ = ("_source", "_source_mode", "_store")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: PersistedItemSearchPageSourceV2,
        store: CatalogNormalizationUnitOfWorkStoreV2,
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_catalog_normalization_runtime()
        mode = _source_mode(source)
        _source_action_count(source)
        self._source = source
        self._source_mode = mode
        self._store = store

    @property
    def source_mode(self) -> CatalogSourceModeV2:
        return self._source_mode

    def normalize(
        self, command: CatalogNormalizationCommandV2
    ) -> CatalogNormalizationResultV2:
        exact_command = _copy_command(command)
        existing_value = _collaborator_call(
            lambda: self._store.lookup(exact_command),
            failure_code=CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE,
        )
        if existing_value is not None:
            existing = _copy_persisted(existing_value)
            _validate_persisted_for_command(
                command=exact_command,
                persisted=existing,
            )
            expected_batch, expected_event = self._load_expected(exact_command)
            if existing.batch != expected_batch or existing.event != expected_event:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                )
            return CatalogNormalizationResultV2(
                persisted=existing,
                replay_status=CatalogReplayStatusV2.IDEMPOTENT_REPLAY,
                external_actions=0,
            )
        batch, event = self._load_expected(exact_command)
        try:
            committed_value = _collaborator_call(
                lambda: self._store.commit(
                    command=exact_command,
                    batch=batch,
                    event=event,
                ),
                failure_code=CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            committed = _copy_persisted(committed_value)
        except CatalogNormalizationRuntimeFailure as error:
            if (
                type(error) is not CatalogNormalizationRuntimeFailure
                or error.code
                is not CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            ):
                raise
            return self._recover_unknown_commit(
                command=exact_command,
                expected_batch=batch,
                expected_event=event,
            )
        _validate_persisted_for_command(command=exact_command, persisted=committed)
        if committed.batch != batch or committed.event != event:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )
        return CatalogNormalizationResultV2(
            persisted=committed,
            replay_status=CatalogReplayStatusV2.DIRECT_COMMIT,
            external_actions=0,
        )

    def _load_expected(
        self,
        command: CatalogNormalizationCommandV2,
    ) -> tuple[CatalogNormalizationBatchV2, CatalogNormalizedOutboxEventV2]:
        if (
            _source_mode(self._source) is not self._source_mode
            or self._source_mode is not CatalogSourceModeV2.RECORDED_PERSISTED
        ):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE
            )
        _source_action_count(self._source)
        receipt = cast(RawArchiveReceiptV2, command.source_step.receipt)
        raw_candidate = _collaborator_call(
            lambda: self._source.read_raw(receipt),
            failure_code=CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE,
        )
        if type(raw_candidate) is not bytes:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
            )
        raw_body = bytes(raw_candidate)
        page_candidate = _collaborator_call(
            lambda: self._source.read_page(
                receipt=receipt,
                request=command.source_request,
            ),
            failure_code=CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE,
        )
        try:
            page = _copy_page(page_candidate)
            observation = ItemSearchProviderObservationV2(
                kind=ProviderObservationKindV2.SUCCESS,
                mode=ProviderModeV2.RECORDED_SYNTHETIC,
                request_fingerprint=command.source_request.request_fingerprint,
                observed_at=receipt.observed_at,
                http_status=200,
                request_id="ARCHIVE:ST0503:VERIFY",
                raw_body=raw_body,
                raw_sha256=receipt.artifact_sha256,
                rate=_copy_rate(page.rate),
                retry_after_at=None,
                failure_class=None,
                external_actions=0,
            )
            reparsed = parse_item_search_page_v2(
                request=command.source_request,
                observation=observation,
            )
            if reparsed != page:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY
                )
        except CatalogNormalizationRuntimeFailure:
            raise
        except Exception:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY
            )
        if (
            _source_mode(self._source) is not self._source_mode
            or _source_action_count(self._source) != 0
        ):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
            )
        batch = normalize_persisted_item_search_page_v2(
            command=command,
            page=page,
            raw_body=raw_body,
        )
        event = CatalogNormalizedOutboxEventV2.from_batch(batch)
        return batch, event

    def _recover_unknown_commit(
        self,
        *,
        command: CatalogNormalizationCommandV2,
        expected_batch: CatalogNormalizationBatchV2,
        expected_event: CatalogNormalizedOutboxEventV2,
    ) -> CatalogNormalizationResultV2:
        try:
            candidate = _collaborator_call(
                lambda: self._store.recover_commit(command),
                failure_code=CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            if type(candidate) is not CatalogCommitRecoveryV2:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
                )
            recovery = CatalogCommitRecoveryV2(
                outcome=CatalogCommitRecoveryOutcomeV2(candidate.outcome.value),
                persisted=(
                    None
                    if candidate.persisted is None
                    else _copy_persisted(candidate.persisted)
                ),
            )
        except CatalogNormalizationRuntimeFailure:
            raise
        except Exception:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )
        if recovery.outcome is CatalogCommitRecoveryOutcomeV2.NOT_COMMITTED:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )
        persisted = cast(PersistedCatalogNormalizationV2, recovery.persisted)
        _validate_persisted_for_command(command=command, persisted=persisted)
        if persisted.batch != expected_batch or persisted.event != expected_event:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )
        return CatalogNormalizationResultV2(
            persisted=persisted,
            replay_status=CatalogReplayStatusV2.RECOVERED_COMMIT,
            external_actions=0,
        )

    def recover_commit(
        self, command: CatalogNormalizationCommandV2
    ) -> CatalogCommitRecoveryV2:
        exact_command = _copy_command(command)
        candidate = _collaborator_call(
            lambda: self._store.recover_commit(exact_command),
            failure_code=CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE,
        )
        try:
            if type(candidate) is not CatalogCommitRecoveryV2:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
                )
            persisted = (
                None
                if candidate.persisted is None
                else _copy_persisted(candidate.persisted)
            )
            recovery = CatalogCommitRecoveryV2(
                outcome=CatalogCommitRecoveryOutcomeV2(candidate.outcome.value),
                persisted=persisted,
            )
        except CatalogNormalizationRuntimeFailure:
            raise
        except Exception:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
            )
        if persisted is not None:
            _validate_persisted_for_command(
                command=exact_command,
                persisted=persisted,
            )
            expected_batch, expected_event = self._load_expected(exact_command)
            if persisted.batch != expected_batch or persisted.event != expected_event:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
                )
        return recovery


__all__ = ["CatalogNormalizationRuntimeServiceV2"]
