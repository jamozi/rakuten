"""Fail-closed port, adapter, service, and mutation tests for ST-1407 V2."""

from __future__ import annotations

import builtins
from dataclasses import replace
from datetime import timedelta, timezone
import os
import pickle
import socket
import time
from typing import cast
from uuid import UUID

import pytest

from raos.adapters.recorded_external_policy_registry import (
    RecordedExternalPolicyRegistryAdapter,
    RecordedExternalPolicyRegistryFixture,
)
from raos.application.ops.external_policy_registry import ExternalPolicyRegistryService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.external_policy_registry import (
    ExternalPolicyRegistryReport,
    ExternalPolicyRegistryRequest,
    ExternalPolicySnapshot,
    RegistryContractBinding,
    RegistryFailure,
    RegistryFailureCode,
    article_binding_set_fingerprint,
    evaluate_external_policy_registry,
)
from raos.domain.shared.persistence import Sha256Digest
from raos.ports.external_policy_registry import ExternalPolicyRegistryExchange

from .support import ACQUIRED_AT, DUE_AT, build_request


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_adapter_and_service_reject_every_non_dev_ci_environment(
    environment: RuntimeEnvironment,
) -> None:
    request = build_request()
    fixture = RecordedExternalPolicyRegistryFixture(
        request,
        evaluate_external_policy_registry(request),
        "ST1407-OVERDUE-AFFECTED-001",
    )

    with pytest.raises(RegistryFailure) as adapter_error:
        RecordedExternalPolicyRegistryAdapter(
            environment=environment,
            fixture_capacity=1,
            fixtures=(fixture,),
        )
    with pytest.raises(RegistryFailure) as service_error:
        ExternalPolicyRegistryService(
            environment=environment,
            exchange=cast(ExternalPolicyRegistryExchange, object()),
        )

    assert adapter_error.value.code is RegistryFailureCode.DEVELOPMENT_ONLY
    assert service_error.value.code is RegistryFailureCode.DEVELOPMENT_ONLY


@pytest.mark.parametrize(
    "capacity",
    (True, 0, -1, 129, 1.0, "1", None),
)
def test_adapter_rejects_invalid_capacity(capacity: object) -> None:
    request = build_request()
    fixture = RecordedExternalPolicyRegistryFixture(
        request,
        evaluate_external_policy_registry(request),
        "ST1407-OVERDUE-AFFECTED-001",
    )

    with pytest.raises(RegistryFailure, match="INVALID_ARGUMENT"):
        RecordedExternalPolicyRegistryAdapter(
            environment=RuntimeEnvironment.CI,
            fixture_capacity=cast(int, capacity),
            fixtures=(fixture,),
        )


def test_adapter_rejects_duplicate_fixture_binding() -> None:
    request = build_request()
    fixture = RecordedExternalPolicyRegistryFixture(
        request,
        evaluate_external_policy_registry(request),
        "ST1407-OVERDUE-AFFECTED-001",
    )

    with pytest.raises(RegistryFailure, match="INVALID_ARGUMENT"):
        RecordedExternalPolicyRegistryAdapter(
            environment=RuntimeEnvironment.CI,
            fixture_capacity=2,
            fixtures=(fixture, fixture),
        )


def test_adapter_refuses_unrecorded_request() -> None:
    recorded = build_request()
    fixture = RecordedExternalPolicyRegistryFixture(
        recorded,
        evaluate_external_policy_registry(recorded),
        "ST1407-OVERDUE-AFFECTED-001",
    )
    adapter = RecordedExternalPolicyRegistryAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=1,
        fixtures=(fixture,),
    )
    unrecorded = build_request(source_content_sha256="a" * 64)

    with pytest.raises(RegistryFailure) as error:
        adapter.evaluate(unrecorded)

    assert error.value.code is RegistryFailureCode.EVALUATOR_UNAVAILABLE


def test_fixture_rejects_a_report_from_another_request() -> None:
    request = build_request()
    other = build_request(source_content_sha256="a" * 64)

    with pytest.raises(RegistryFailure) as error:
        RecordedExternalPolicyRegistryFixture(
            request,
            evaluate_external_policy_registry(other),
            "ST1407-OVERDUE-AFFECTED-001",
        )

    assert error.value.code is RegistryFailureCode.EVALUATION_MISMATCH


@pytest.mark.parametrize(
    "variant",
    (
        "missing",
        "duplicate",
        "cross_snapshot",
        "cross_rule",
        "unordered",
    ),
)
def test_version_link_set_fails_closed(variant: str) -> None:
    request = build_request(external_rule_id="EXT-GOOGLE-001")
    links = request.version_links
    if variant == "missing":
        changed = links[:-1]
    elif variant == "duplicate":
        changed = (*links[:-1], links[0])
    elif variant == "cross_snapshot":
        changed = (
            replace(
                links[0],
                snapshot_id=UUID("10000000-0000-4000-8000-000000001499"),
            ),
            *links[1:],
        )
    elif variant == "cross_rule":
        changed = (replace(links[0], external_rule_id="EXT-GOOGLE-002"), *links[1:])
    else:
        changed = tuple(reversed(links))

    with pytest.raises(RegistryFailure) as error:
        evaluate_external_policy_registry(replace(request, version_links=changed))

    assert error.value.code is RegistryFailureCode.VERSION_LINK_SET_MISMATCH


def test_snapshot_must_bind_exact_current_contract() -> None:
    request = build_request()
    changed = replace(
        request.snapshot,
        contract_binding_sha256=Sha256Digest("a" * 64),
    )

    with pytest.raises(RegistryFailure) as error:
        evaluate_external_policy_registry(replace(request, snapshot=changed))

    assert error.value.code is RegistryFailureCode.SNAPSHOT_BINDING_MISMATCH


@pytest.mark.parametrize(
    "variant",
    ("unordered", "duplicate", "duplicate_article", "unknown_policy"),
)
def test_article_binding_set_fails_closed(variant: str) -> None:
    request = build_request()
    articles = request.article_bindings
    if variant == "unordered":
        changed = tuple(reversed(articles))
    elif variant == "duplicate":
        changed = (articles[0], articles[0])
    elif variant == "duplicate_article":
        changed = (
            articles[0],
            replace(
                articles[1],
                article_id=articles[0].article_id,
                article_version_id=articles[0].article_version_id,
            ),
        )
    else:
        with pytest.raises(RegistryFailure) as error:
            replace(articles[0], policy_ids=("POL-CONT-999",))
        assert error.value.code is RegistryFailureCode.ARTICLE_BINDING_SET_INVALID
        return

    with pytest.raises(RegistryFailure) as error:
        evaluate_external_policy_registry(replace(request, article_bindings=changed))

    assert error.value.code is RegistryFailureCode.ARTICLE_BINDING_SET_INVALID


def test_article_policy_ids_must_be_unique_sorted_and_nonempty() -> None:
    request = build_request()
    article = request.article_bindings[0]

    for invalid in ((), ("POL-CONT-020", "POL-CONT-010"), ("POL-CONT-010",) * 2):
        with pytest.raises(RegistryFailure) as error:
            replace(article, policy_ids=invalid)
        assert error.value.code is RegistryFailureCode.ARTICLE_BINDING_SET_INVALID


def test_snapshot_rejects_non_utc_due_order_and_attestation() -> None:
    request = build_request()
    snapshot = request.snapshot

    invalid_changes = (
        {"review_due_at": ACQUIRED_AT},
        {"review_due_at": DUE_AT.replace(tzinfo=timezone(timedelta(hours=9)))},
        {"official_source_attested": True},
        {"current_source_verified": True},
    )
    for change in invalid_changes:
        with pytest.raises(RegistryFailure, match="INVALID_ARGUMENT"):
            replace(snapshot, **change)


def test_version_link_cannot_activate_or_use_unknown_policy() -> None:
    request = build_request()
    link = request.version_links[0]

    for change in (
        {"activation_authorized": True},
        {"reference_only": False},
        {"policy_id": "POL-CONT-999"},
        {"policy_version": "1.0"},
        {"policy_catalog_sha256": Sha256Digest("a" * 64)},
    ):
        with pytest.raises(RegistryFailure, match="INVALID_ARGUMENT"):
            replace(link, **change)


def test_contract_binding_is_closed_to_current_catalogs_and_decisions() -> None:
    binding = RegistryContractBinding.current()

    with pytest.raises(RegistryFailure) as error:
        replace(binding, notification_channel_decision="OD-999")

    assert error.value.code is RegistryFailureCode.CONTRACT_BINDING_MISMATCH


class _HostileString(str):
    __hash__ = str.__hash__

    def __eq__(self, other: object) -> bool:
        del other
        return True

    def __ne__(self, other: object) -> bool:
        del other
        return False


@pytest.mark.parametrize(
    "field",
    (
        "contract_id",
        "contract_version",
        "external_rule_catalog_id",
        "external_rule_catalog_version",
        "official_reference_catalog_id",
        "official_reference_catalog_version",
        "policy_catalog_id",
        "policy_catalog_version",
        "source_allowlist_decision",
        "legal_review_decision",
        "notification_channel_decision",
    ),
)
def test_contract_binding_rejects_hostile_string_subclasses(field: str) -> None:
    request = build_request()
    hostile = cast(str, _HostileString("attacker-controlled"))
    object.__setattr__(request.binding, field, hostile)

    with pytest.raises(RegistryFailure) as error:
        evaluate_external_policy_registry(request)

    assert error.value.code is RegistryFailureCode.CONTRACT_BINDING_MISMATCH


def test_article_binding_universe_rejects_omission_empty_and_forged_hash() -> None:
    request = build_request()
    omitted = request.article_bindings[:1]

    with pytest.raises(RegistryFailure) as omitted_error:
        replace(request, article_bindings=omitted)
    with pytest.raises(RegistryFailure) as empty_error:
        replace(request, article_bindings=())
    forged_digest = Sha256Digest(article_binding_set_fingerprint(omitted))
    with pytest.raises(RegistryFailure) as forged_error:
        replace(
            request,
            article_bindings=omitted,
            article_binding_set_sha256=forged_digest,
        )

    assert omitted_error.value.code is RegistryFailureCode.ARTICLE_BINDING_SET_INVALID
    assert empty_error.value.code is RegistryFailureCode.ARTICLE_BINDING_SET_INVALID
    assert forged_error.value.code is RegistryFailureCode.ARTICLE_BINDING_SET_INVALID


def test_recorded_fixture_rejects_self_consistent_unowned_request() -> None:
    unowned = build_request(source_content_sha256="a" * 64)

    with pytest.raises(RegistryFailure) as error:
        RecordedExternalPolicyRegistryFixture(
            unowned,
            evaluate_external_policy_registry(unowned),
            "ST1407-OVERDUE-AFFECTED-001",
        )

    assert error.value.code is RegistryFailureCode.EVALUATION_MISMATCH


class _UnavailableExchange:
    def evaluate(
        self, request: ExternalPolicyRegistryRequest
    ) -> ExternalPolicyRegistryReport:
        del request
        raise RuntimeError("untrusted provider details")


class _WrongExchange:
    def evaluate(self, request: ExternalPolicyRegistryRequest) -> object:
        del request
        return object()


class _OtherReportExchange:
    def evaluate(
        self,
        request: ExternalPolicyRegistryRequest,
    ) -> ExternalPolicyRegistryReport:
        del request
        return evaluate_external_policy_registry(
            build_request(source_content_sha256="a" * 64)
        )


class _MutatingExchange:
    def evaluate(
        self,
        request: ExternalPolicyRegistryRequest,
    ) -> ExternalPolicyRegistryReport:
        expected = evaluate_external_policy_registry(request)
        object.__setattr__(
            request.snapshot,
            "source_content_sha256",
            Sha256Digest("a" * 64),
        )
        return expected


@pytest.mark.parametrize(
    ("exchange", "expected_code"),
    (
        (_UnavailableExchange(), RegistryFailureCode.EVALUATOR_UNAVAILABLE),
        (_WrongExchange(), RegistryFailureCode.EVALUATION_MISMATCH),
        (_OtherReportExchange(), RegistryFailureCode.EVALUATION_MISMATCH),
        (_MutatingExchange(), RegistryFailureCode.EVALUATION_MISMATCH),
    ),
)
def test_service_rejects_unavailable_wrong_or_mutating_collaborator(
    exchange: object,
    expected_code: RegistryFailureCode,
) -> None:
    service = ExternalPolicyRegistryService(
        environment=RuntimeEnvironment.CI,
        exchange=cast(ExternalPolicyRegistryExchange, exchange),
    )

    with pytest.raises(RegistryFailure) as error:
        service.evaluate(build_request())

    assert error.value.code is expected_code


def test_service_calls_exchange_once_and_returns_independent_exact_result() -> None:
    request = build_request()
    expected = evaluate_external_policy_registry(request)

    class CountingExchange:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(
            self,
            request: ExternalPolicyRegistryRequest,
        ) -> ExternalPolicyRegistryReport:
            self.calls += 1
            assert request is outer_request
            return evaluate_external_policy_registry(request)

    exchange = CountingExchange()
    outer_request = request
    service = ExternalPolicyRegistryService(
        environment=RuntimeEnvironment.CI,
        exchange=exchange,
    )

    result = service.evaluate(request)

    assert exchange.calls == 1
    assert result == expected
    assert result is not expected


def test_pure_evaluation_performs_no_io_clock_environment_or_uuid_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_request()

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("forbidden side effect")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(time, "time", forbidden)

    report = evaluate_external_policy_registry(request)

    assert report.request_sha256.value == request.fingerprint


def test_values_are_redacted_and_generic_pickle_is_disabled() -> None:
    request = build_request()
    report = evaluate_external_policy_registry(request)

    for value in (
        request.binding,
        request.snapshot,
        request.version_links[0],
        request.article_bindings[0],
        request,
        report,
    ):
        assert "http" not in repr(value).lower()
        assert "POL-CONT" not in repr(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_failure_text_never_reflects_hostile_input() -> None:
    hostile = "https://169.254.169.254/latest/meta-data?secret=token"

    with pytest.raises(RegistryFailure) as error:
        ExternalPolicySnapshot(
            snapshot_id=UUID("10000000-0000-4000-8000-000000001407"),
            external_rule_id=hostile,
            source_content_sha256=Sha256Digest("a" * 64),
            acquired_at=ACQUIRED_AT,
            review_due_at=DUE_AT,
            contract_binding_sha256=Sha256Digest("b" * 64),
        )

    assert error.value.code is RegistryFailureCode.INVALID_ARGUMENT
    assert hostile not in str(error.value)
    assert "secret" not in str(error.value).lower()


def test_post_construction_nested_tampering_is_sanitized() -> None:
    wrong_shape = build_request()
    object.__setattr__(wrong_shape, "binding", object())

    with pytest.raises(RegistryFailure) as shape_error:
        evaluate_external_policy_registry(wrong_shape)

    assert shape_error.value.code is RegistryFailureCode.INVALID_ARGUMENT
    assert shape_error.value.__cause__ is None

    wrong_digest = build_request()
    object.__setattr__(
        wrong_digest.snapshot.source_content_sha256,
        "value",
        object(),
    )

    with pytest.raises(RegistryFailure) as digest_error:
        evaluate_external_policy_registry(wrong_digest)

    assert digest_error.value.code is RegistryFailureCode.INVALID_ARGUMENT
    assert digest_error.value.__cause__ is None
