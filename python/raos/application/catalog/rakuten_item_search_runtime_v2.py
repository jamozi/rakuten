"""One-call, one-page local ingestion orchestration for ST-0502."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, TypeVar, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    CommitRecoveryOutcomeV2,
    IngestionSessionStateV2,
    IngestionStepOutcomeV2,
    ItemSearchCommitRecoveryV2,
    ItemSearchIngestionSessionV2,
    ItemSearchPlanV2,
    ItemSearchProviderObservationV2,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchStepCommandV2,
    ItemSearchStepResultV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchItemV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    ProviderObservationKindV2,
    RateLimitObservationV2,
    RawArchiveReceiptV2,
    SecretNameBindingV2,
    SecretTransportV2,
    UntrustedProviderTextV2,
    fail_item_search_runtime,
    failure_transition_v2,
    parse_item_search_page_v2,
    success_transition_v2,
)
from raos.ports.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionUnitOfWorkStoreV2,
    ItemSearchPageProviderV2,
)


_T = TypeVar("_T")
_NO_VALUE = object()


def _supports(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


def _collaborator_call(
    invoke: Callable[[], _T],
    *,
    failure_code: ItemSearchRuntimeFailureCode,
) -> _T:
    """Call a hostile collaborator without retaining or echoing its exception."""

    try:
        return invoke()
    except ItemSearchRuntimeFailure as error:
        if type(error) is ItemSearchRuntimeFailure:
            raise
    except Exception:
        pass
    fail_item_search_runtime(failure_code)


def _validated_collaborator_value(
    value: object,
    validator: Callable[[object], _T],
    *,
    failure_code: ItemSearchRuntimeFailureCode = (
        ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
    ),
) -> _T:
    """Reconstruct exact domain values so forged exact-class objects fail closed."""

    try:
        validated = validator(value)
        if validated == value:
            return validated
    except Exception:
        pass
    fail_item_search_runtime(failure_code)


def _checked_collaborator_call(
    invoke: Callable[[], _T],
    *,
    verify_after: Callable[[], None],
    failure_code: ItemSearchRuntimeFailureCode,
) -> _T:
    """Always run the closed postcondition, including exception returns."""

    value: object = _NO_VALUE
    captured_code: ItemSearchRuntimeFailureCode | None = None
    try:
        value = invoke()
    except ItemSearchRuntimeFailure as error:
        captured_code = (
            error.code
            if type(error) is ItemSearchRuntimeFailure
            and type(error.code) is ItemSearchRuntimeFailureCode
            else failure_code
        )
    except Exception:
        captured_code = failure_code
    try:
        verify_after()
    except ItemSearchRuntimeFailure as error:
        fail_item_search_runtime(
            error.code
            if type(error) is ItemSearchRuntimeFailure
            and type(error.code) is ItemSearchRuntimeFailureCode
            else failure_code
        )
    except Exception:
        fail_item_search_runtime(failure_code)
    if captured_code is not None:
        fail_item_search_runtime(captured_code)
    if value is _NO_VALUE:
        fail_item_search_runtime(failure_code)
    return cast(_T, value)


def _copy_plan(value: object) -> ItemSearchPlanV2:
    if type(value) is not ItemSearchPlanV2:
        fail_item_search_runtime()
    plan = value
    return ItemSearchPlanV2(
        keyword=plan.keyword,
        shop_code=plan.shop_code,
        item_code=plan.item_code,
        genre_id=plan.genre_id,
        hits=plan.hits,
        sort=type(plan.sort)(plan.sort.value),
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
        fail_item_search_runtime()
    binding = value
    return SecretNameBindingV2(
        provider_name=binding.provider_name,
        secret_name=binding.secret_name,
        transport=SecretTransportV2(binding.transport.value),
        required=binding.required,
    )


def _copy_request(value: object) -> ItemSearchWireRequestV2:
    if type(value) is not ItemSearchWireRequestV2:
        fail_item_search_runtime()
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


def _copy_command(value: object) -> ItemSearchStepCommandV2:
    if type(value) is not ItemSearchStepCommandV2:
        fail_item_search_runtime()
    command = value
    return ItemSearchStepCommandV2(
        operation_id=command.operation_id,
        session_id=command.session_id,
        expected_version=command.expected_version,
        observed_at=command.observed_at,
    )


def _copy_rate(value: object) -> RateLimitObservationV2:
    if type(value) is not RateLimitObservationV2:
        fail_item_search_runtime()
    rate = value
    return RateLimitObservationV2(
        limit=rate.limit,
        remaining=rate.remaining,
        reset_at=rate.reset_at,
    )


def _copy_provider_text(value: object) -> UntrustedProviderTextV2:
    if type(value) is not UntrustedProviderTextV2:
        fail_item_search_runtime()
    text = value
    return UntrustedProviderTextV2(value=text.value, trust=text.trust)


def _copy_item(value: object) -> ParsedItemSearchItemV2:
    if type(value) is not ParsedItemSearchItemV2:
        fail_item_search_runtime()
    item = value
    return ParsedItemSearchItemV2(
        item_code=_copy_provider_text(item.item_code),
        item_name=_copy_provider_text(item.item_name),
        catchcopy=(
            None if item.catchcopy is None else _copy_provider_text(item.catchcopy)
        ),
        item_caption=(
            None
            if item.item_caption is None
            else _copy_provider_text(item.item_caption)
        ),
        item_price_jpy=item.item_price_jpy,
        item_url=item.item_url,
        affiliate_url=item.affiliate_url,
        shop_code=_copy_provider_text(item.shop_code),
        shop_name=(
            None if item.shop_name is None else _copy_provider_text(item.shop_name)
        ),
        genre_id=item.genre_id,
        availability=item.availability,
        postage_included=item.postage_included,
        image_urls=item.image_urls,
    )


def _copy_page(value: object) -> ParsedItemSearchPageV2:
    if type(value) is not ParsedItemSearchPageV2:
        fail_item_search_runtime()
    page = value
    if type(page.items) is not tuple:
        fail_item_search_runtime()
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


def _copy_observation(value: object) -> ItemSearchProviderObservationV2:
    if type(value) is not ItemSearchProviderObservationV2:
        fail_item_search_runtime()
    observation = value
    return ItemSearchProviderObservationV2(
        kind=ProviderObservationKindV2(observation.kind.value),
        mode=ProviderModeV2(observation.mode.value),
        request_fingerprint=observation.request_fingerprint,
        observed_at=observation.observed_at,
        http_status=observation.http_status,
        request_id=observation.request_id,
        raw_body=(
            None if observation.raw_body is None else bytes(observation.raw_body)
        ),
        raw_sha256=observation.raw_sha256,
        rate=_copy_rate(observation.rate),
        retry_after_at=observation.retry_after_at,
        failure_class=observation.failure_class,
        external_actions=observation.external_actions,
    )


def _copy_receipt(value: object) -> RawArchiveReceiptV2:
    if type(value) is not RawArchiveReceiptV2:
        fail_item_search_runtime()
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
        fail_item_search_runtime()
    session = value
    return ItemSearchIngestionSessionV2(
        session_id=session.session_id,
        plan=_copy_plan(session.plan),
        state=session.state,
        next_page=session.next_page,
        completed_pages=session.completed_pages,
        current_attempt=session.current_attempt,
        consecutive_failures=session.consecutive_failures,
        next_allowed_at=session.next_allowed_at,
        seen_request_fingerprints=session.seen_request_fingerprints,
        seen_response_sha256=session.seen_response_sha256,
        seen_item_fingerprints=session.seen_item_fingerprints,
        last_failure_class=session.last_failure_class,
        version=session.version,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _copy_persisted(value: object) -> PersistedItemSearchStepV2:
    if type(value) is not PersistedItemSearchStepV2:
        fail_item_search_runtime()
    persisted = value
    return PersistedItemSearchStepV2(
        outcome=persisted.outcome,
        session=_copy_session(persisted.session),
        request_fingerprint=persisted.request_fingerprint,
        receipt=(
            None if persisted.receipt is None else _copy_receipt(persisted.receipt)
        ),
        failure_class=persisted.failure_class,
    )


def _copy_recovery(value: object) -> ItemSearchCommitRecoveryV2:
    if type(value) is not ItemSearchCommitRecoveryV2:
        fail_item_search_runtime()
    recovery = value
    return ItemSearchCommitRecoveryV2(
        outcome=CommitRecoveryOutcomeV2(recovery.outcome.value),
        persisted=(
            None if recovery.persisted is None else _copy_persisted(recovery.persisted)
        ),
    )


def _validated_persisted(
    value: object,
    *,
    failure_code: ItemSearchRuntimeFailureCode = (
        ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
    ),
) -> PersistedItemSearchStepV2:
    persisted = _validated_collaborator_value(
        value,
        _copy_persisted,
        failure_code=failure_code,
    )
    session = persisted.session
    state_outcomes: dict[IngestionSessionStateV2, set[IngestionStepOutcomeV2]] = {
        IngestionSessionStateV2.READY: {IngestionStepOutcomeV2.PAGE_ARCHIVED},
        IngestionSessionStateV2.RETRY_WAIT: {
            IngestionStepOutcomeV2.WAIT_RETRY,
            IngestionStepOutcomeV2.PROVIDER_DISABLED,
        },
        IngestionSessionStateV2.RATE_LIMITED: {IngestionStepOutcomeV2.WAIT_RATE_LIMIT},
        IngestionSessionStateV2.CIRCUIT_OPEN: {
            IngestionStepOutcomeV2.WAIT_CIRCUIT,
            IngestionStepOutcomeV2.PROVIDER_DISABLED,
        },
        IngestionSessionStateV2.COMPLETED: {IngestionStepOutcomeV2.COMPLETED},
        IngestionSessionStateV2.COMPLETED_BOUNDED: {
            IngestionStepOutcomeV2.COMPLETED_BOUNDED
        },
        IngestionSessionStateV2.FAILED: {IngestionStepOutcomeV2.FAILED},
        IngestionSessionStateV2.QUARANTINED: {IngestionStepOutcomeV2.QUARANTINED},
    }
    state_failures: dict[
        IngestionSessionStateV2, set[ProviderFailureClassV2 | None]
    ] = {
        IngestionSessionStateV2.READY: {None},
        IngestionSessionStateV2.RETRY_WAIT: {
            ProviderFailureClassV2.TRANSIENT,
            ProviderFailureClassV2.UNAVAILABLE,
        },
        IngestionSessionStateV2.RATE_LIMITED: {
            None,
            ProviderFailureClassV2.RATE_LIMITED,
        },
        IngestionSessionStateV2.CIRCUIT_OPEN: {
            ProviderFailureClassV2.TRANSIENT,
            ProviderFailureClassV2.UNAVAILABLE,
        },
        IngestionSessionStateV2.COMPLETED: {None},
        IngestionSessionStateV2.COMPLETED_BOUNDED: {None},
        IngestionSessionStateV2.FAILED: {
            ProviderFailureClassV2.AUTH,
            ProviderFailureClassV2.PERMANENT,
        },
        IngestionSessionStateV2.QUARANTINED: {
            ProviderFailureClassV2.CONTRACT,
            ProviderFailureClassV2.INTEGRITY,
            ProviderFailureClassV2.RATE_LIMITED,
        },
    }
    failure_class = persisted.failure_class
    receipt_required = failure_class is None or (
        session.state is IngestionSessionStateV2.QUARANTINED
        and failure_class
        in {ProviderFailureClassV2.CONTRACT, ProviderFailureClassV2.INTEGRITY}
    )
    if (
        persisted.outcome not in state_outcomes[session.state]
        or failure_class not in state_failures[session.state]
        or failure_class is not session.last_failure_class
        or persisted.request_fingerprint is None
        or (persisted.receipt is not None) is not receipt_required
        or (
            persisted.outcome is IngestionStepOutcomeV2.PROVIDER_DISABLED
            and failure_class is not ProviderFailureClassV2.UNAVAILABLE
        )
        or (
            persisted.outcome
            in {
                IngestionStepOutcomeV2.WAIT_RETRY,
                IngestionStepOutcomeV2.WAIT_CIRCUIT,
            }
            and failure_class is not ProviderFailureClassV2.TRANSIENT
        )
    ):
        fail_item_search_runtime(failure_code)
    if persisted.receipt is not None:
        receipt = persisted.receipt
        if (
            receipt.page > session.plan.max_pages
            or receipt.request_fingerprint != persisted.request_fingerprint
        ):
            fail_item_search_runtime(failure_code)
        if failure_class is None:
            if (
                session.completed_pages != receipt.page
                or session.next_page != min(receipt.page + 1, 100)
                or not session.seen_request_fingerprints
                or not session.seen_response_sha256
                or session.seen_request_fingerprints[-1] != receipt.request_fingerprint
                or session.seen_response_sha256[-1] != receipt.artifact_sha256
            ):
                fail_item_search_runtime(failure_code)
        elif (
            receipt.page != session.next_page
            or ItemSearchWireRequestV2.from_plan(
                session.plan,
                page=session.next_page,
            ).request_fingerprint
            != persisted.request_fingerprint
        ):
            fail_item_search_runtime(failure_code)
    elif (
        session.next_page != session.completed_pages + 1
        or session.next_page > session.plan.max_pages
        or ItemSearchWireRequestV2.from_plan(
            session.plan,
            page=session.next_page,
        ).request_fingerprint
        != persisted.request_fingerprint
    ):
        fail_item_search_runtime(failure_code)
    return persisted


def _provider_mode(provider: ItemSearchPageProviderV2) -> ProviderModeV2:
    candidate = _collaborator_call(
        lambda: provider.mode,
        failure_code=ItemSearchRuntimeFailureCode.PROVIDER_UNAVAILABLE,
    )
    if type(candidate) is not ProviderModeV2 or candidate not in {
        ProviderModeV2.RECORDED_SYNTHETIC,
        ProviderModeV2.DISABLED,
    }:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
    return candidate


def _provider_action_count(provider: ItemSearchPageProviderV2) -> int:
    candidate = _collaborator_call(
        lambda: provider.external_action_count,
        failure_code=ItemSearchRuntimeFailureCode.PROVIDER_UNAVAILABLE,
    )
    if type(candidate) is not int or candidate != 0:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
    return candidate


def _store_action_count(
    store: ItemSearchIngestionUnitOfWorkStoreV2,
    *,
    failure_code: ItemSearchRuntimeFailureCode = (
        ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE
    ),
) -> None:
    candidate = _collaborator_call(
        lambda: store.external_action_count,
        failure_code=failure_code,
    )
    if type(candidate) is not int or candidate != 0:
        fail_item_search_runtime(failure_code)
    return None


def _terminal_outcome(state: IngestionSessionStateV2) -> IngestionStepOutcomeV2:
    mapping = {
        IngestionSessionStateV2.COMPLETED: IngestionStepOutcomeV2.COMPLETED,
        IngestionSessionStateV2.COMPLETED_BOUNDED: (
            IngestionStepOutcomeV2.COMPLETED_BOUNDED
        ),
        IngestionSessionStateV2.FAILED: IngestionStepOutcomeV2.FAILED,
        IngestionSessionStateV2.QUARANTINED: IngestionStepOutcomeV2.QUARANTINED,
    }
    outcome = mapping.get(state)
    if outcome is None:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
    return outcome


def _waiting_outcome(state: IngestionSessionStateV2) -> IngestionStepOutcomeV2:
    mapping = {
        IngestionSessionStateV2.RETRY_WAIT: IngestionStepOutcomeV2.WAIT_RETRY,
        IngestionSessionStateV2.RATE_LIMITED: (IngestionStepOutcomeV2.WAIT_RATE_LIMIT),
        IngestionSessionStateV2.CIRCUIT_OPEN: IngestionStepOutcomeV2.WAIT_CIRCUIT,
    }
    outcome = mapping.get(state)
    if outcome is None:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
    return outcome


@final
class RakutenItemSearchRuntimeServiceV2:
    """Perform no more than one recorded fetch and one local UoW commit."""

    __slots__ = ("_provider", "_provider_mode", "_store")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        provider: ItemSearchPageProviderV2,
        store: ItemSearchIngestionUnitOfWorkStoreV2,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _supports(provider, ItemSearchPageProviderV2)
            or not _supports(store, ItemSearchIngestionUnitOfWorkStoreV2)
        ):
            fail_item_search_runtime()
        mode = _provider_mode(provider)
        _provider_action_count(provider)
        _store_action_count(store)
        self._provider = provider
        self._provider_mode = mode
        self._store = store

    @property
    def provider_mode(self) -> ProviderModeV2:
        return self._provider_mode

    def create_session(
        self,
        *,
        session_id: object,
        plan: ItemSearchPlanV2,
        created_at: datetime,
    ) -> ItemSearchIngestionSessionV2:
        session = ItemSearchIngestionSessionV2.initial(
            session_id=cast(UUID, session_id),
            plan=plan,
            created_at=created_at,
        )
        store_session = _copy_session(session)
        _store_action_count(self._store)
        created = _checked_collaborator_call(
            lambda: self._store.create_session(store_session),
            verify_after=lambda: self._verify_store_session_argument(
                store_session,
                session,
                failure_code=ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE,
            ),
            failure_code=ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE,
        )
        if created is not None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        loaded = self._load_session(session.session_id)
        if loaded != session:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        return loaded

    def _load_session(self, session_id: UUID) -> ItemSearchIngestionSessionV2:
        _store_action_count(self._store)
        candidate = _checked_collaborator_call(
            lambda: self._store.load_session(session_id),
            verify_after=lambda: _store_action_count(self._store),
            failure_code=ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE,
        )
        session = _validated_collaborator_value(candidate, _copy_session)
        if session.session_id != session_id:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        return session

    def _lookup_step(
        self,
        command: ItemSearchStepCommandV2,
    ) -> PersistedItemSearchStepV2 | None:
        exact_command = _copy_command(command)
        store_command = _copy_command(exact_command)
        _store_action_count(self._store)
        candidate = _checked_collaborator_call(
            lambda: self._store.lookup_step(store_command),
            verify_after=lambda: self._verify_store_command_argument(
                store_command,
                exact_command,
                failure_code=ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE,
            ),
            failure_code=ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE,
        )
        if candidate is None:
            return None
        persisted = _validated_persisted(candidate)
        if (
            persisted.session.session_id != exact_command.session_id
            or persisted.session.version != exact_command.expected_version + 1
            or persisted.session.updated_at != exact_command.observed_at
            or persisted.request_fingerprint is None
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        return persisted

    def step_once(self, command: ItemSearchStepCommandV2) -> ItemSearchStepResultV2:
        exact_command = _copy_command(command)
        existing = self._lookup_step(exact_command)
        if existing is not None:
            return self._rehydrate(existing)
        session = self._load_session(exact_command.session_id)
        if session.version != exact_command.expected_version:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT)
        if session.terminal:
            persisted = PersistedItemSearchStepV2(
                outcome=_terminal_outcome(session.state),
                session=session,
                request_fingerprint=None,
                receipt=None,
                failure_class=session.last_failure_class,
            )
            return ItemSearchStepResultV2(
                persisted=persisted,
                page=None,
                provider_mode=self._provider_mode,
                external_actions=0,
            )
        if (
            session.next_allowed_at is not None
            and exact_command.observed_at < session.next_allowed_at
        ):
            persisted = PersistedItemSearchStepV2(
                outcome=_waiting_outcome(session.state),
                session=session,
                request_fingerprint=None,
                receipt=None,
                failure_class=session.last_failure_class,
            )
            return ItemSearchStepResultV2(
                persisted=persisted,
                page=None,
                provider_mode=self._provider_mode,
                external_actions=0,
            )
        request = ItemSearchWireRequestV2.from_plan(
            session.plan,
            page=session.next_page,
        )
        observation = self._fetch(request, observed_at=exact_command.observed_at)
        if observation.kind is ProviderObservationKindV2.SUCCESS:
            return self._success(
                command=exact_command,
                before=session,
                request=request,
                observation=observation,
            )
        failure_class = observation.failure_class
        if failure_class is None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        after, outcome = failure_transition_v2(
            session=session,
            failure_class=failure_class,
            observed_at=exact_command.observed_at,
            retry_after_at=observation.retry_after_at,
        )
        return self._commit_failure(
            command=exact_command,
            before=session,
            after=after,
            request=request,
            failure_class=failure_class,
            observation=observation,
            expected_outcome=outcome,
        )

    def recover_commit(
        self,
        command: ItemSearchStepCommandV2,
    ) -> ItemSearchCommitRecoveryV2:
        exact_command = _copy_command(command)
        store_command = _copy_command(exact_command)
        _store_action_count(self._store)
        candidate = _checked_collaborator_call(
            lambda: self._store.recover_commit(store_command),
            verify_after=lambda: self._verify_store_command_argument(
                store_command,
                exact_command,
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            ),
            failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
        )
        recovery = _validated_collaborator_value(
            candidate,
            _copy_recovery,
            failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
        )
        persisted = recovery.persisted
        if persisted is not None and (
            persisted.session.session_id != exact_command.session_id
            or persisted.session.version != exact_command.expected_version + 1
            or persisted.session.updated_at != exact_command.observed_at
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)
        return recovery

    def _verify_store_command_argument(
        self,
        actual: object,
        expected: ItemSearchStepCommandV2,
        *,
        failure_code: ItemSearchRuntimeFailureCode,
    ) -> None:
        _store_action_count(self._store, failure_code=failure_code)
        if _copy_command(actual) != expected:
            fail_item_search_runtime(failure_code)

    def _verify_store_session_argument(
        self,
        actual: object,
        expected: ItemSearchIngestionSessionV2,
        *,
        failure_code: ItemSearchRuntimeFailureCode,
    ) -> None:
        _store_action_count(self._store, failure_code=failure_code)
        if _copy_session(actual) != expected:
            fail_item_search_runtime(failure_code)

    def _fetch(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        if _provider_mode(self._provider) is not self._provider_mode:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        _provider_action_count(self._provider)
        exact_request = _copy_request(request)
        provider_request = _copy_request(exact_request)
        candidate: object = _checked_collaborator_call(
            lambda: self._provider.fetch_once(
                provider_request,
                observed_at=observed_at,
            ),
            verify_after=lambda: self._verify_provider_fetch_boundary(
                provider_request,
                exact_request,
            ),
            failure_code=ItemSearchRuntimeFailureCode.PROVIDER_UNAVAILABLE,
        )
        observation = _validated_collaborator_value(candidate, _copy_observation)
        after_mode = _provider_mode(self._provider)
        _provider_action_count(self._provider)
        if (
            observation.request_fingerprint != exact_request.request_fingerprint
            or observation.observed_at != observed_at
            or observation.mode is not self._provider_mode
            or after_mode is not self._provider_mode
            or observation.external_actions != 0
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        return observation

    def _verify_provider_fetch_boundary(
        self,
        actual_request: object,
        expected_request: ItemSearchWireRequestV2,
    ) -> None:
        if (
            _copy_request(actual_request) != expected_request
            or _provider_mode(self._provider) is not self._provider_mode
            or _provider_action_count(self._provider) != 0
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)

    def _success(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        observation: ItemSearchProviderObservationV2,
    ) -> ItemSearchStepResultV2:
        try:
            page = parse_item_search_page_v2(
                request=request,
                observation=observation,
            )
            after, outcome = success_transition_v2(
                session=before,
                page=page,
                observed_at=command.observed_at,
            )
        except ItemSearchRuntimeFailure:
            after, outcome = failure_transition_v2(
                session=before,
                failure_class=ProviderFailureClassV2.CONTRACT,
                observed_at=command.observed_at,
                retry_after_at=None,
            )
            return self._commit_failure(
                command=command,
                before=before,
                after=after,
                request=request,
                failure_class=ProviderFailureClassV2.CONTRACT,
                observation=observation,
                expected_outcome=outcome,
            )
        try:
            store_command = _copy_command(command)
            store_before = _copy_session(before)
            store_after = _copy_session(after)
            store_request = _copy_request(request)
            store_observation = _copy_observation(observation)
            store_page = _copy_page(page)
            _store_action_count(
                self._store,
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            candidate = _checked_collaborator_call(
                lambda: self._store.commit_success(
                    command=store_command,
                    before=store_before,
                    after=store_after,
                    request=store_request,
                    observation=store_observation,
                    page=store_page,
                ),
                verify_after=lambda: self._verify_success_commit_boundary(
                    command=store_command,
                    expected_command=command,
                    before=store_before,
                    expected_before=before,
                    after=store_after,
                    expected_after=after,
                    request=store_request,
                    expected_request=request,
                    observation=store_observation,
                    expected_observation=observation,
                    page=store_page,
                    expected_page=page,
                ),
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            persisted = _validated_persisted(
                candidate,
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            self._validate_committed_step(
                persisted=persisted,
                after=after,
                request=request,
                expected_outcome=outcome,
                expected_failure_class=None,
                receipt_required=True,
            )
        except ItemSearchRuntimeFailure as error:
            return self._commit_error(
                error=error,
                command=command,
                before=before,
                request=request,
            )
        return ItemSearchStepResultV2(
            persisted=persisted,
            page=page,
            provider_mode=self._provider_mode,
            external_actions=0,
        )

    def _commit_failure(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        failure_class: ProviderFailureClassV2,
        observation: ItemSearchProviderObservationV2 | None,
        expected_outcome: IngestionStepOutcomeV2,
    ) -> ItemSearchStepResultV2:
        try:
            store_command = _copy_command(command)
            store_before = _copy_session(before)
            store_after = _copy_session(after)
            store_request = _copy_request(request)
            store_observation = (
                None if observation is None else _copy_observation(observation)
            )
            _store_action_count(
                self._store,
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            candidate = _checked_collaborator_call(
                lambda: self._store.commit_failure(
                    command=store_command,
                    before=store_before,
                    after=store_after,
                    request=store_request,
                    failure_class=failure_class,
                    observation=store_observation,
                ),
                verify_after=lambda: self._verify_failure_commit_boundary(
                    command=store_command,
                    expected_command=command,
                    before=store_before,
                    expected_before=before,
                    after=store_after,
                    expected_after=after,
                    request=store_request,
                    expected_request=request,
                    observation=store_observation,
                    expected_observation=observation,
                ),
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            persisted = _validated_persisted(
                candidate,
                failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
            )
            self._validate_committed_step(
                persisted=persisted,
                after=after,
                request=request,
                expected_outcome=expected_outcome,
                expected_failure_class=failure_class,
                receipt_required=(
                    observation is not None and observation.raw_body is not None
                ),
            )
        except ItemSearchRuntimeFailure as error:
            return self._commit_error(
                error=error,
                command=command,
                before=before,
                request=request,
            )
        return ItemSearchStepResultV2(
            persisted=persisted,
            page=None,
            provider_mode=self._provider_mode,
            external_actions=0,
        )

    def _verify_success_commit_boundary(
        self,
        *,
        command: object,
        expected_command: ItemSearchStepCommandV2,
        before: object,
        expected_before: ItemSearchIngestionSessionV2,
        after: object,
        expected_after: ItemSearchIngestionSessionV2,
        request: object,
        expected_request: ItemSearchWireRequestV2,
        observation: object,
        expected_observation: ItemSearchProviderObservationV2,
        page: object,
        expected_page: ParsedItemSearchPageV2,
    ) -> None:
        _store_action_count(
            self._store,
            failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
        )
        if (
            _copy_command(command) != expected_command
            or _copy_session(before) != expected_before
            or _copy_session(after) != expected_after
            or _copy_request(request) != expected_request
            or _copy_observation(observation) != expected_observation
            or _copy_page(page) != expected_page
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)

    def _verify_failure_commit_boundary(
        self,
        *,
        command: object,
        expected_command: ItemSearchStepCommandV2,
        before: object,
        expected_before: ItemSearchIngestionSessionV2,
        after: object,
        expected_after: ItemSearchIngestionSessionV2,
        request: object,
        expected_request: ItemSearchWireRequestV2,
        observation: object,
        expected_observation: ItemSearchProviderObservationV2 | None,
    ) -> None:
        _store_action_count(
            self._store,
            failure_code=ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN,
        )
        copied_observation = (
            None if observation is None else _copy_observation(observation)
        )
        if (
            _copy_command(command) != expected_command
            or _copy_session(before) != expected_before
            or _copy_session(after) != expected_after
            or _copy_request(request) != expected_request
            or copied_observation != expected_observation
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)

    @staticmethod
    def _validate_committed_step(
        *,
        persisted: PersistedItemSearchStepV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        expected_outcome: IngestionStepOutcomeV2,
        expected_failure_class: ProviderFailureClassV2 | None,
        receipt_required: bool,
    ) -> None:
        if (
            persisted.session != after
            or persisted.outcome is not expected_outcome
            or persisted.request_fingerprint != request.request_fingerprint
            or persisted.failure_class is not expected_failure_class
            or (persisted.receipt is not None) is not receipt_required
            or (
                persisted.receipt is not None and persisted.receipt.page != request.page
            )
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)

    def _commit_error(
        self,
        *,
        error: ItemSearchRuntimeFailure,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
    ) -> ItemSearchStepResultV2:
        mapping = {
            ItemSearchRuntimeFailureCode.COMMIT_KNOWN_ROLLBACK: (
                IngestionStepOutcomeV2.COMMIT_KNOWN_ROLLBACK
            ),
            ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN: (
                IngestionStepOutcomeV2.COMMIT_UNKNOWN
            ),
        }
        outcome = mapping.get(error.code)
        if outcome is None:
            fail_item_search_runtime(error.code)
        persisted = PersistedItemSearchStepV2(
            outcome=outcome,
            session=before,
            request_fingerprint=request.request_fingerprint,
            receipt=None,
            failure_class=None,
        )
        return ItemSearchStepResultV2(
            persisted=persisted,
            page=None,
            provider_mode=self._provider_mode,
            external_actions=0,
        )

    def _rehydrate(
        self,
        persisted: PersistedItemSearchStepV2,
    ) -> ItemSearchStepResultV2:
        persisted = _validated_persisted(persisted)
        page = None
        if persisted.receipt is not None and persisted.outcome in {
            IngestionStepOutcomeV2.PAGE_ARCHIVED,
            IngestionStepOutcomeV2.COMPLETED,
            IngestionStepOutcomeV2.COMPLETED_BOUNDED,
            IngestionStepOutcomeV2.WAIT_RATE_LIMIT,
        }:
            request = ItemSearchWireRequestV2.from_plan(
                persisted.session.plan,
                page=persisted.receipt.page,
            )
            store_receipt = _copy_receipt(persisted.receipt)
            store_request = _copy_request(request)
            _store_action_count(self._store)
            candidate = _checked_collaborator_call(
                lambda: self._store.read_page(
                    receipt=store_receipt,
                    request=store_request,
                ),
                verify_after=lambda: self._verify_read_page_boundary(
                    receipt=store_receipt,
                    expected_receipt=cast(
                        RawArchiveReceiptV2,
                        persisted.receipt,
                    ),
                    request=store_request,
                    expected_request=request,
                ),
                failure_code=ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE,
            )
            page = _validated_collaborator_value(candidate, _copy_page)
            if (
                page.page != persisted.receipt.page
                or page.request_fingerprint != request.request_fingerprint
                or page.raw_sha256 != persisted.receipt.artifact_sha256
                or page.observed_at != persisted.receipt.observed_at
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        return ItemSearchStepResultV2(
            persisted=persisted,
            page=page,
            provider_mode=self._provider_mode,
            external_actions=0,
        )

    def _verify_read_page_boundary(
        self,
        *,
        receipt: object,
        expected_receipt: RawArchiveReceiptV2,
        request: object,
        expected_request: ItemSearchWireRequestV2,
    ) -> None:
        _store_action_count(self._store)
        if (
            _copy_receipt(receipt) != expected_receipt
            or _copy_request(request) != expected_request
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)


__all__ = ["RakutenItemSearchRuntimeServiceV2"]
