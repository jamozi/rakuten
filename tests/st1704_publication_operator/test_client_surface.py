"""HTTPS and CLI-surface tests for publication operator v2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import ssl
from typing import cast

import pytest

import raos.adapters.self_hosted_wordpress_publication_operator_https_v2 as https
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    CommittedReviewDraftBinding,
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationProposal,
)
from tests.st1704_publication_operator.test_draft_revision import revision_proposal


def proposal() -> PublicationProposal:
    return PublicationProposal.bind(
        CommittedReviewDraftBinding(
            article_id="st1704-portable-power-station-guide",
            draft_post_id=28,
            packet_sha256="1" * 64,
            request_sha256="2" * 64,
            snapshot_payload_sha256="3" * 64,
            visible_content_sha256="4" * 64,
            public_slug="portable-power-station-guide",
        ),
        "5" * 64,
    )


def _time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Credentials:
    def authorization_header(self) -> str:
        return "Basic REDACTED"


class _Store:
    def __init__(self, root: Path) -> None:
        assert root.is_absolute()

    def read(self) -> _Credentials:
        return _Credentials()


class _Response:
    def __init__(
        self, value: dict[str, object], *, status: int, etag: str | None = None
    ) -> None:
        self.status = status
        self.payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        self.headers = {
            "Content-Length": str(len(self.payload)),
            "Content-Type": "application/json; charset=UTF-8",
        }
        if etag is not None:
            self.headers["ETag"] = f'"{etag}"'

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    def read(self, amount: int = -1) -> bytes:
        assert amount >= len(self.payload)
        return self.payload


class _Connection:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[tuple[str, str, bytes, dict[str, str]]] = []

    def connect(self) -> None:
        return None

    def set_read_timeout(self, seconds: int) -> None:
        assert seconds == 20

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self.calls.append((method, path, body, headers))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        return None


class _Factory:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> _Connection:
        assert host == "kurashinoshirube.com"
        assert port == 443
        assert connect_timeout_seconds == 5
        assert tls_context.check_hostname
        return self.connection


@pytest.fixture(autouse=True)
def credential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(https, "OwnerPrivateWordPressOperatorCredentialStore", _Store)


def test_propose_and_exact_get_recovery_use_only_closed_routes_and_receipts(
    tmp_path: Path,
) -> None:
    candidate = proposal()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = {
        "created_at": _time(now),
        "expires_at": _time(now + timedelta(seconds=900)),
        "operation": "PUBLISH_ST1704_ARTICLE",
        "proposal_id": candidate.proposal_id,
        "schema": "RAOS_ST1704_PUBLICATION_OPERATOR_PROPOSAL_V2",
        "state": "PROPOSED",
    }
    created_connection = _Connection(
        _Response(
            {**base, "replayed": False},
            status=201,
            etag=candidate.proposal_id,
        )
    )
    created = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(created_connection)
    ).propose(candidate)
    assert not created.replayed
    method, path, body, headers = created_connection.calls[0]
    assert (method, path, body) == (
        "POST",
        "/wp-json/raos-operator/v2/proposals",
        candidate.canonical_bytes(),
    )
    assert headers["Authorization"] == "Basic REDACTED"
    assert "If-Match" not in headers and "Idempotency-Key" not in headers

    recovered_connection = _Connection(
        _Response(
            {**base, "replayed": True, "state": "APPROVED"},
            status=200,
            etag=candidate.proposal_id,
        )
    )
    recovered = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(recovered_connection)
    ).recover_proposal(candidate)
    assert recovered.replayed and recovered.state.value == "APPROVED"
    assert recovered_connection.calls[0][0:3] == (
        "GET",
        f"/wp-json/raos-operator/v2/proposals/{candidate.proposal_id}",
        b"",
    )


def test_apply_is_empty_json_with_exact_cas_and_idempotency_headers(
    tmp_path: Path,
) -> None:
    candidate = proposal()
    connection = _Connection(
        _Response(
            {
                "operation": "PUBLISH_ST1704_ARTICLE",
                "proposal_id": candidate.proposal_id,
                "replayed": False,
                "result_code": "ST1704_ARTICLE_PUBLISHED",
                "schema": "RAOS_ST1704_PUBLICATION_OPERATOR_APPLY_V2",
                "state": "APPLIED",
            },
            status=200,
            etag=candidate.proposal_id,
        )
    )
    receipt = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(connection)
    ).apply(candidate.proposal_id)
    assert receipt.result_code == "ST1704_ARTICLE_PUBLISHED"
    method, path, body, headers = connection.calls[0]
    assert (method, path, body) == (
        "POST",
        f"/wp-json/raos-operator/v2/proposals/{candidate.proposal_id}/apply",
        b"{}",
    )
    assert headers["If-Match"] == f'"{candidate.proposal_id}"'
    assert headers["Idempotency-Key"] == candidate.proposal_id


def test_malformed_post_write_receipt_is_outcome_ambiguous_and_never_invalid(
    tmp_path: Path,
) -> None:
    candidate = proposal()
    connection = _Connection(
        _Response(
            {"schema": "INVALID", "untrusted_field": "must-not-surface"},
            status=201,
            etag=candidate.proposal_id,
        )
    )
    with pytest.raises(PublicationOperatorFailure) as failed:
        https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            tmp_path, _Factory(connection)
        ).propose(candidate)
    assert failed.value.code is PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
    assert "secret" not in str(failed.value)


def test_revision_uses_additive_status_propose_apply_and_verify_routes(
    tmp_path: Path,
) -> None:
    candidate = revision_proposal()
    status_connection = _Connection(
        _Response(
            {
                "master_writes_enabled": True,
                "operator_version": "2.1.0",
                "publication_writes_enabled": True,
                "schema": "RAOS_ST1704_DRAFT_REVISION_STATUS_V2",
                "supported_operations": ["REVISE_ST1704_DRAFT"],
                "writes_enabled": True,
            },
            status=200,
        )
    )
    status = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(status_connection)
    ).revision_status()
    assert status.writes_enabled
    assert status_connection.calls[0][0:3] == (
        "GET",
        "/wp-json/raos-operator/v2/revision-status",
        b"",
    )

    apply_connection = _Connection(
        _Response(
            {
                "operation": "REVISE_ST1704_DRAFT",
                "proposal_id": candidate.proposal_id,
                "replayed": False,
                "result_code": "ST1704_DRAFT_REVISED",
                "schema": "RAOS_ST1704_PUBLICATION_OPERATOR_APPLY_V2",
                "state": "APPLIED",
            },
            status=200,
            etag=candidate.proposal_id,
        )
    )
    applied = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(apply_connection)
    ).apply_revision(candidate.proposal_id)
    assert applied.result_code == "ST1704_DRAFT_REVISED"
    assert apply_connection.calls[0][0:3] == (
        "POST",
        f"/wp-json/raos-operator/v2/proposals/{candidate.proposal_id}/apply",
        b"{}",
    )

    verify_connection = _Connection(
        _Response(
            {
                "draft_post_id": 28,
                "operation": "REVISE_ST1704_DRAFT",
                "operation_sha256": candidate.binding.operation_sha256,
                "proposal_id": candidate.proposal_id,
                "result_code": "ST1704_DRAFT_REVISION_VERIFIED",
                "schema": "RAOS_ST1704_DRAFT_REVISION_VERIFY_V2",
                "state": "APPLIED",
            },
            status=200,
            etag=candidate.proposal_id,
        )
    )
    verified = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(verify_connection)
    ).verify_revision(candidate.proposal_id)
    assert verified.operation_sha256 == candidate.binding.operation_sha256
    assert verify_connection.calls[0][0:3] == (
        "GET",
        f"/wp-json/raos-operator/v2/proposals/{candidate.proposal_id}/verify",
        b"",
    )


def _revision_recovery_payload() -> dict[str, object]:
    candidate = revision_proposal()
    return {
        "disposition": "PREDECESSOR",
        "draft_post_id": candidate.binding.draft_id,
        "operation": "REVISE_ST1704_DRAFT",
        "operation_sha256": candidate.binding.operation_sha256,
        "proposal_id": candidate.proposal_id,
        "proposal_state": "FAILED",
        "result_code": "ST1704_DRAFT_REVISION_STATE_OBSERVED",
        "schema": "RAOS_ST1704_DRAFT_REVISION_RECOVERY_V2",
    }


def test_revision_state_recovery_is_exact_read_only_get_with_etag(
    tmp_path: Path,
) -> None:
    candidate = revision_proposal()
    connection = _Connection(
        _Response(
            _revision_recovery_payload(),
            status=200,
            etag=candidate.proposal_id,
        )
    )

    recovered = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(connection)
    ).recover_revision_state(candidate.proposal_id)

    assert recovered.proposal_id == candidate.proposal_id
    assert recovered.operation_sha256 == candidate.binding.operation_sha256
    assert recovered.draft_post_id == candidate.binding.draft_id
    assert recovered.proposal_state.value == "FAILED"
    assert recovered.disposition.value == "PREDECESSOR"
    method, path, body, headers = connection.calls[0]
    assert (method, path, body) == (
        "GET",
        (
            "/wp-json/raos-operator/v2/proposals/"
            f"{candidate.proposal_id}/revision-state"
        ),
        b"",
    )
    assert "If-Match" not in headers
    assert "Idempotency-Key" not in headers


@pytest.mark.parametrize(
    "malformation",
    [
        "extra-field",
        "wrong-schema",
        "wrong-proposal-id",
        "invalid-state-disposition",
    ],
)
def test_revision_state_recovery_refuses_malformed_receipts(
    tmp_path: Path, malformation: str
) -> None:
    candidate = revision_proposal()
    payload = _revision_recovery_payload()
    if malformation == "extra-field":
        payload["untrusted"] = True
    elif malformation == "wrong-schema":
        payload["schema"] = "RAOS_ST1704_DRAFT_REVISION_VERIFY_V2"
    elif malformation == "wrong-proposal-id":
        payload["proposal_id"] = "f" * 64
    elif malformation == "invalid-state-disposition":
        payload["proposal_state"] = "APPLIED"
    else:  # pragma: no cover - parametrization is closed above
        raise AssertionError("unreachable malformed recovery case")
    connection = _Connection(
        _Response(payload, status=200, etag=candidate.proposal_id)
    )

    with pytest.raises(PublicationOperatorFailure) as failure:
        https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            tmp_path, _Factory(connection)
        ).recover_revision_state(candidate.proposal_id)

    assert failure.value.code is PublicationOperatorFailureCode.RESPONSE_INVALID


def test_revision_state_recovery_requires_exact_etag(tmp_path: Path) -> None:
    candidate = revision_proposal()
    connection = _Connection(
        _Response(_revision_recovery_payload(), status=200, etag=None)
    )

    with pytest.raises(PublicationOperatorFailure) as failure:
        https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            tmp_path, _Factory(connection)
        ).recover_revision_state(candidate.proposal_id)

    assert failure.value.code is PublicationOperatorFailureCode.RESPONSE_INVALID


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "raos_st1704_proposal_invalid"),
        (409, "raos_st1704_publication_busy"),
        (429, "raos_st1704_proposal_capacity_reached"),
        (500, "raos_st1704_proposal_lookup_failed"),
        (503, "raos_st1704_writes_disabled"),
        (409, "raos_st1704_snapshot_not_bound"),
    ],
)
def test_exact_pre_mutation_create_rejection_is_terminal_not_created(
    tmp_path: Path, status: int, code: str
) -> None:
    connection = _Connection(
        _Response(
            {
                "code": code,
                "data": {"status": status},
                "message": ("The ST-1704 publication operator rejected the request."),
            },
            status=status,
        )
    )
    with pytest.raises(PublicationOperatorFailure) as failed:
        https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            tmp_path, _Factory(connection)
        ).propose(proposal())
    assert failed.value.code is PublicationOperatorFailureCode.PROPOSAL_NOT_CREATED


def test_exact_recovery_not_found_is_terminal_and_requires_new_proposal(
    tmp_path: Path,
) -> None:
    candidate = proposal()
    connection = _Connection(
        _Response(
            {
                "code": "raos_st1704_proposal_not_found",
                "data": {"status": 404},
                "message": ("The ST-1704 publication operator rejected the request."),
            },
            status=404,
        )
    )
    recovered = https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        tmp_path, _Factory(connection)
    ).recover_proposal(candidate)
    assert recovered.proposal_id == candidate.proposal_id
    assert recovered.replayed
    assert recovered.state.value == "FAILED"
    assert recovered.requires_new_proposal()


def test_recovery_not_found_requires_exact_closed_error_schema(tmp_path: Path) -> None:
    connection = _Connection(
        _Response(
            {
                "code": "raos_st1704_proposal_not_found",
                "data": {"status": 409},
                "message": "The ST-1704 publication operator rejected the request.",
            },
            status=404,
        )
    )
    with pytest.raises(PublicationOperatorFailure) as failed:
        https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            tmp_path, _Factory(connection)
        ).recover_proposal(proposal())
    assert failed.value.code is PublicationOperatorFailureCode.RESPONSE_INVALID


@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        (409, "raos_st1704_proposal_record_invalid", "exact"),
        (409, "raos_st1704_writes_disabled", "exact"),
        (503, "raos_st1704_writes_disabled", "wrong"),
    ],
)
def test_create_error_outside_exact_closed_set_remains_ambiguous(
    tmp_path: Path, status: int, code: str, message: str
) -> None:
    exact_message = "The ST-1704 publication operator rejected the request."
    connection = _Connection(
        _Response(
            {
                "code": code,
                "data": {"status": status},
                "message": exact_message if message == "exact" else message,
            },
            status=status,
        )
    )
    with pytest.raises(PublicationOperatorFailure) as failed:
        https.OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            tmp_path, _Factory(connection)
        ).propose(proposal())
    assert failed.value.code is PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS


def test_system_connection_forces_debuglevel_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed: list[object] = []

    class InheritedDebugConnection:
        debuglevel = 1

        def __init__(self, **kwargs: object) -> None:
            observed.append(kwargs)
            self.debuglevel = type(self).debuglevel
            self.sock = None

        def set_debuglevel(self, value: int) -> None:
            self.debuglevel = value

        def close(self) -> None:
            return None

    monkeypatch.setattr(http.client, "HTTPSConnection", InheritedDebugConnection)
    context = ssl.create_default_context()
    connection = https.SystemPublicationOperatorHttpsConnectionFactory().open(
        host="kurashinoshirube.com",
        port=443,
        connect_timeout_seconds=5,
        tls_context=context,
    )
    wrapped = cast(object, connection)
    assert getattr(wrapped, "_connection").debuglevel == 0
    connection.close()
    output = capsys.readouterr()
    assert "Authorization" not in output.out + output.err
    assert "REDACTED" not in output.out + output.err
