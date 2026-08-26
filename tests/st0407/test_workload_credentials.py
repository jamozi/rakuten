"""Focused behavior, lifecycle, rotation, and redaction tests for ST-0407."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
import json
import logging
import pickle
from typing import cast

import pytest

from .support import (
    LOGICAL_REFERENCE_CANARY,
    MAXIMUM_LEASE_LIFETIME,
    NOW,
    metadata,
    request,
    runtime_config,
)
from raos.adapters.development_workload_credentials import (
    DevelopmentScriptedWorkloadCredentialAdapter,
    DisabledWorkloadCredentialAdapter,
)
from raos.application.iam.workload_credentials import WorkloadCredentialService
from raos.config.runtime import RuntimeConfig, RuntimeEnvironment
from raos.domain.iam.workload_credentials import (
    CredentialAlias,
    CredentialFailure,
    CredentialFailureCode,
    CredentialLease,
    CredentialLeaseMetadata,
    CredentialLeaseState,
    CredentialPurpose,
    CredentialRequest,
    CredentialRotationNotice,
    WorkloadBinding,
    WorkloadEnvironment,
)
from raos.ports.workload_credentials import (
    CredentialRotationHook,
    WorkloadCredentialPort,
)


def _failure(
    code: CredentialFailureCode, operation: Callable[[], object]
) -> CredentialFailure:
    with pytest.raises(CredentialFailure) as captured:
        operation()
    assert captured.value.code is code
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    return captured.value


def _service(
    *,
    config: RuntimeConfig,
    port: WorkloadCredentialPort,
    hooks: tuple[CredentialRotationHook, ...] = (),
    maximum: timedelta = MAXIMUM_LEASE_LIFETIME,
) -> WorkloadCredentialService:
    return WorkloadCredentialService(
        config=config,
        port=port,
        maximum_lease_lifetime=maximum,
        rotation_hooks=hooks,
    )


class _StaticPort:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def acquire(self, *, request: CredentialRequest, now: datetime) -> CredentialLease:
        del request, now
        self.calls += 1
        return cast(CredentialLease, self.result)


class _ExplodingPort:
    def __init__(self, canary: str) -> None:
        self.canary = canary
        self.calls = 0

    def acquire(self, *, request: CredentialRequest, now: datetime) -> CredentialLease:
        del request, now
        self.calls += 1
        raise RuntimeError(self.canary)


class _RecordingHook:
    def __init__(
        self, name: str, calls: list[str], *, failure_canary: str | None = None
    ) -> None:
        self.name = name
        self.calls = calls
        self.failure_canary = failure_canary
        self.notices: list[CredentialRotationNotice] = []

    def notify(self, notice: CredentialRotationNotice) -> None:
        self.calls.append(self.name)
        self.notices.append(notice)
        if self.failure_canary is not None:
            raise RuntimeError(self.failure_canary)


def test_env_dev_metadata_lease_is_config_bound_and_has_explicit_lifetime(
    config: RuntimeConfig,
    provider_request: CredentialRequest,
    provider_metadata: CredentialLeaseMetadata,
) -> None:
    adapter = DevelopmentScriptedWorkloadCredentialAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        entries=(provider_metadata,),
    )

    lease = _service(config=config, port=adapter).acquire(
        request=provider_request,
        now=NOW,
    )

    assert type(lease) is CredentialLease
    assert lease.state is CredentialLeaseState.ACTIVE
    assert lease.metadata == provider_metadata
    assert lease.metadata is not provider_metadata
    assert lease.metadata.request == provider_request
    assert lease.metadata.expires_at - lease.metadata.issued_at < (
        MAXIMUM_LEASE_LIFETIME
    )


@pytest.mark.parametrize(
    ("credential_request", "code", "adapter_calls"),
    (
        (request(alias="missing_alias"), CredentialFailureCode.UNKNOWN_ALIAS, 0),
        (
            request(service_name="projection-worker"),
            CredentialFailureCode.CONFIGURATION_MISMATCH,
            0,
        ),
        (
            request(environment=WorkloadEnvironment.INTEGRATION),
            CredentialFailureCode.CONFIGURATION_MISMATCH,
            0,
        ),
    ),
)
def test_unknown_alias_and_cross_workload_requests_fail_before_adapter(
    credential_request: CredentialRequest,
    code: CredentialFailureCode,
    adapter_calls: int,
) -> None:
    port = _StaticPort(CredentialLease(metadata()))
    _failure(
        code,
        lambda: _service(config=runtime_config(), port=port).acquire(
            request=credential_request,
            now=NOW,
        ),
    )
    assert port.calls == adapter_calls


def test_wrong_purpose_is_not_satisfied_by_another_script_entry() -> None:
    provider = request()
    database = request(
        alias="database_primary",
        purpose=CredentialPurpose.DATABASE_CONNECTION,
    )
    adapter = DevelopmentScriptedWorkloadCredentialAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        entries=(metadata(credential_request=provider),),
    )
    _failure(
        CredentialFailureCode.BACKEND_FAILURE,
        lambda: _service(config=runtime_config(), port=adapter).acquire(
            request=database,
            now=NOW,
        ),
    )


def test_development_adapter_never_issues_ci_deployment_lease() -> None:
    ci_request = request(alias="ci_deploy", purpose=CredentialPurpose.CI_DEPLOYMENT)
    _failure(
        CredentialFailureCode.PURPOSE_NOT_ALLOWED,
        lambda: DevelopmentScriptedWorkloadCredentialAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            entries=(metadata(credential_request=ci_request),),
        ),
    )
    adapter = DevelopmentScriptedWorkloadCredentialAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        entries=(),
    )
    _failure(
        CredentialFailureCode.PURPOSE_NOT_ALLOWED,
        lambda: adapter.acquire(request=ci_request, now=NOW),
    )


@pytest.mark.parametrize(
    ("lease_metadata", "code"),
    (
        (
            metadata(
                issued_at=NOW + timedelta(seconds=1),
                not_before=NOW + timedelta(seconds=1),
                expires_at=NOW + timedelta(minutes=1),
            ),
            CredentialFailureCode.LEASE_NOT_YET_VALID,
        ),
        (
            metadata(
                issued_at=NOW - timedelta(minutes=2),
                not_before=NOW - timedelta(minutes=1),
                expires_at=NOW,
            ),
            CredentialFailureCode.LEASE_EXPIRED,
        ),
        (
            metadata(
                issued_at=NOW - timedelta(seconds=1),
                not_before=NOW,
                expires_at=NOW + MAXIMUM_LEASE_LIFETIME,
            ),
            CredentialFailureCode.LEASE_LIFETIME_EXCEEDED,
        ),
    ),
)
def test_future_expired_and_over_limit_leases_fail_closed(
    lease_metadata: CredentialLeaseMetadata,
    code: CredentialFailureCode,
) -> None:
    _failure(
        code,
        lambda: _service(
            config=runtime_config(),
            port=_StaticPort(CredentialLease(lease_metadata)),
        ).acquire(request=request(), now=NOW),
    )


def test_non_utc_and_malformed_or_foreign_lease_results_are_sanitized() -> None:
    valid_lease = CredentialLease(metadata())
    _failure(
        CredentialFailureCode.INVALID_REQUEST,
        lambda: _service(
            config=runtime_config(), port=_StaticPort(valid_lease)
        ).acquire(request=request(), now=NOW.astimezone(timezone(timedelta(hours=9)))),
    )
    _failure(
        CredentialFailureCode.LEASE_MALFORMED,
        lambda: _service(config=runtime_config(), port=_StaticPort(None)).acquire(
            request=request(), now=NOW
        ),
    )
    foreign = metadata(
        credential_request=request(service_name="projection-worker"),
        lease_id="foreign-lease",
    )
    _failure(
        CredentialFailureCode.LEASE_MALFORMED,
        lambda: _service(
            config=runtime_config(), port=_StaticPort(CredentialLease(foreign))
        ).acquire(request=request(), now=NOW),
    )


def test_close_is_idempotent_and_script_entries_cannot_be_reused() -> None:
    lease = CredentialLease(metadata())
    lease.close()
    lease.close()
    assert lease.state is CredentialLeaseState.CLOSED
    assert lease.closed is True

    adapter = DevelopmentScriptedWorkloadCredentialAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        entries=(metadata(),),
    )
    adapter.acquire(request=request(), now=NOW).close()
    _failure(
        CredentialFailureCode.LEASE_REUSED,
        lambda: adapter.acquire(request=request(), now=NOW),
    )


@pytest.mark.parametrize("environment", tuple(WorkloadEnvironment))
def test_disabled_adapter_fails_closed_in_every_environment(
    environment: WorkloadEnvironment,
) -> None:
    _failure(
        CredentialFailureCode.BACKEND_NOT_CONFIGURED,
        lambda: DisabledWorkloadCredentialAdapter().acquire(
            request=request(environment=environment),
            now=NOW,
        ),
    )


@pytest.mark.parametrize(
    "environment",
    tuple(
        item for item in RuntimeEnvironment if item is not RuntimeEnvironment.ENV_DEV
    ),
)
def test_development_adapter_construction_rejects_every_non_dev_environment(
    environment: RuntimeEnvironment,
) -> None:
    _failure(
        CredentialFailureCode.DEVELOPMENT_ONLY,
        lambda: DevelopmentScriptedWorkloadCredentialAdapter(
            environment=environment,
            entries=(),
        ),
    )


def test_development_adapter_rechecks_environment_on_each_operation() -> None:
    adapter = DevelopmentScriptedWorkloadCredentialAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        entries=(metadata(),),
    )
    object.__setattr__(adapter, "_environment", RuntimeEnvironment.STAGING)
    _failure(
        CredentialFailureCode.DEVELOPMENT_ONLY,
        lambda: adapter.acquire(request=request(), now=NOW),
    )


def test_rotation_hooks_run_synchronously_in_order_once() -> None:
    previous = metadata(
        lease_id="lease-before",
        issued_at=NOW - timedelta(minutes=10),
        not_before=NOW - timedelta(minutes=10),
        expires_at=NOW,
    )
    replacement = metadata(
        lease_id="lease-after",
        issued_at=NOW,
        not_before=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    calls: list[str] = []
    first = _RecordingHook("first", calls)
    second = _RecordingHook("second", calls)
    service = _service(
        config=runtime_config(),
        port=DisabledWorkloadCredentialAdapter(),
        hooks=(first, second),
    )

    service.notify_rotation(previous=previous, replacement=replacement)

    assert calls == ["first", "second"]
    assert len(first.notices) == len(second.notices) == 1
    assert first.notices[0].previous == previous
    assert first.notices[0].replacement == replacement
    _failure(
        CredentialFailureCode.ROTATION_INVALID,
        lambda: service.notify_rotation(previous=previous, replacement=replacement),
    )
    assert calls == ["first", "second"]


def test_rotation_stops_on_hook_failure_and_discards_exception() -> None:
    canary = "HOOK-PRIVATE-CANARY-0407"
    calls: list[str] = []
    first = _RecordingHook("first", calls)
    exploding = _RecordingHook("exploding", calls, failure_canary=canary)
    skipped = _RecordingHook("skipped", calls)
    service = _service(
        config=runtime_config(),
        port=DisabledWorkloadCredentialAdapter(),
        hooks=(first, exploding, skipped),
    )
    previous = metadata(
        lease_id="previous-hook",
        issued_at=NOW - timedelta(minutes=5),
        not_before=NOW - timedelta(minutes=5),
        expires_at=NOW,
    )
    replacement = metadata(
        lease_id="replacement-hook",
        issued_at=NOW,
        not_before=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    failure = _failure(
        CredentialFailureCode.ROTATION_HOOK_FAILED,
        lambda: service.notify_rotation(previous=previous, replacement=replacement),
    )

    assert calls == ["first", "exploding"]
    assert canary not in f"{failure!s} {failure!r} {failure.args!r}"


@pytest.mark.parametrize(
    "replacement",
    (
        metadata(
            lease_id="overlap",
            issued_at=NOW - timedelta(minutes=1),
            not_before=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=4),
        ),
        metadata(
            credential_request=request(
                alias="database_primary",
                purpose=CredentialPurpose.DATABASE_CONNECTION,
            ),
            lease_id="other-request",
            issued_at=NOW,
            not_before=NOW,
            expires_at=NOW + timedelta(minutes=5),
        ),
    ),
)
def test_rotation_requires_same_request_and_nonoverlapping_newer_window(
    replacement: CredentialLeaseMetadata,
) -> None:
    previous = metadata(
        lease_id="previous-invalid",
        issued_at=NOW - timedelta(minutes=5),
        not_before=NOW - timedelta(minutes=5),
        expires_at=NOW,
    )
    _failure(
        CredentialFailureCode.ROTATION_INVALID,
        lambda: _service(
            config=runtime_config(), port=DisabledWorkloadCredentialAdapter()
        ).notify_rotation(previous=previous, replacement=replacement),
    )


def test_rotation_rejects_a_same_but_foreign_workload_binding() -> None:
    foreign_request = request(service_name="projection-worker")
    previous = metadata(
        credential_request=foreign_request,
        lease_id="foreign-previous",
        issued_at=NOW - timedelta(minutes=5),
        not_before=NOW - timedelta(minutes=5),
        expires_at=NOW,
    )
    replacement = metadata(
        credential_request=foreign_request,
        lease_id="foreign-replacement",
        issued_at=NOW,
        not_before=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    _failure(
        CredentialFailureCode.CONFIGURATION_MISMATCH,
        lambda: _service(
            config=runtime_config(), port=DisabledWorkloadCredentialAdapter()
        ).notify_rotation(previous=previous, replacement=replacement),
    )


def test_port_failure_is_single_call_no_retry_and_is_sanitized() -> None:
    canary = "BACKEND-PRIVATE-CANARY-0407"
    port = _ExplodingPort(canary)
    failure = _failure(
        CredentialFailureCode.BACKEND_FAILURE,
        lambda: _service(config=runtime_config(), port=port).acquire(
            request=request(), now=NOW
        ),
    )
    assert port.calls == 1
    assert canary not in f"{failure!s} {failure!r} {failure.args!r}"


def test_lease_and_metadata_have_no_material_surface_and_are_redacted(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lease = CredentialLease(metadata())
    prohibited = {"bytes", "material", "password", "secret", "token"}
    public_names = {name.lower() for name in dir(lease) if not name.startswith("_")}
    assert all(not any(word in name for word in prohibited) for name in public_names)
    assert public_names == {"close", "closed", "metadata", "state"}

    displays = [
        str(lease),
        repr(lease),
        str(lease.metadata),
        repr(lease.metadata),
        str(lease.metadata.request),
        repr(lease.metadata.request),
    ]
    with pytest.raises(TypeError):
        pickle.dumps(lease)
    with pytest.raises(TypeError):
        json.dumps(lease)
    with pytest.raises(TypeError):
        asdict(lease)  # type: ignore[call-overload]
    logging.getLogger("st0407.redaction").warning("lease=%r", lease)
    print(lease)
    captured = capsys.readouterr()
    surfaces = " ".join(displays + [captured.out, captured.err, caplog.text])
    assert LOGICAL_REFERENCE_CANARY not in surfaces
    assert "secret://" not in surfaces


def test_config_reference_canary_never_reaches_failures_repr_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failure = _failure(
        CredentialFailureCode.UNKNOWN_ALIAS,
        lambda: _service(
            config=runtime_config(),
            port=DisabledWorkloadCredentialAdapter(),
        ).acquire(request=request(alias="missing_alias"), now=NOW),
    )
    logging.getLogger("st0407.canary").error("failure=%r", failure)
    surfaces = " ".join(
        (
            str(failure),
            repr(failure),
            repr(failure.args),
            caplog.text,
        )
    )
    assert LOGICAL_REFERENCE_CANARY not in surfaces
    assert "secret://" not in surfaces


class _HostileString(str):
    def __str__(self) -> str:
        raise RuntimeError("HOSTILE-STRING-CANARY")

    def __repr__(self) -> str:
        raise RuntimeError("HOSTILE-STRING-CANARY")


class _HostileDatetime(datetime):
    pass


def test_hostile_subclasses_and_forged_exact_objects_fail_without_input_echo() -> None:
    hostile = _HostileString("provider_api")
    _failure(
        CredentialFailureCode.INVALID_REQUEST,
        lambda: CredentialAlias(hostile),
    )
    _failure(
        CredentialFailureCode.INVALID_REQUEST,
        lambda: WorkloadBinding(
            service_name=_HostileString("catalog-worker"),
            environment=WorkloadEnvironment.ENV_DEV,
        ),
    )
    _failure(
        CredentialFailureCode.LEASE_MALFORMED,
        lambda: CredentialLeaseMetadata(
            request=request(),
            lease_id="hostile-time",
            issued_at=_HostileDatetime(2026, 8, 10, 12, tzinfo=UTC),
            not_before=NOW,
            expires_at=NOW + timedelta(minutes=1),
        ),
    )

    forged = object.__new__(CredentialLease)
    failure = _failure(
        CredentialFailureCode.LEASE_MALFORMED,
        lambda: _service(config=runtime_config(), port=_StaticPort(forged)).acquire(
            request=request(), now=NOW
        ),
    )
    assert "HOSTILE" not in f"{failure!s} {failure!r}"


def test_service_requires_exact_config_positive_lifetime_and_unique_hooks() -> None:
    config = runtime_config()
    port = DisabledWorkloadCredentialAdapter()
    hook = _RecordingHook("hook", [])
    with pytest.raises(ValueError):
        WorkloadCredentialService(
            config=config,
            port=port,
            maximum_lease_lifetime=timedelta(0),
            rotation_hooks=(),
        )
    with pytest.raises(ValueError):
        WorkloadCredentialService(
            config=config,
            port=port,
            maximum_lease_lifetime=MAXIMUM_LEASE_LIFETIME,
            rotation_hooks=(hook, hook),
        )
