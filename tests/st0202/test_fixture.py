"""Tests for the bounded ST-0202 SigV4 fixture client."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import socket
import threading
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import object_storage_fixture as fixture


class _S3State:
    def __init__(self, lifecycle_configuration: bytes | None = None) -> None:
        self.bucket_exists = False
        self.object_lock = False
        self.versioning = False
        self.lifecycle_configuration = lifecycle_configuration
        self.next_version = 1
        self.objects: dict[str, dict[str, Any]] = {}
        self.authorization_headers: list[str] = []


def _handler(state: _S3State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _body(self) -> bytes:
            size = int(self.headers.get("Content-Length", "0"), 10)
            return self.rfile.read(size)

        def _send(
            self,
            status: int,
            body: bytes = b"",
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _signed(self) -> bool:
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("AWS4-HMAC-SHA256 Credential=RAOS"):
                return False
            state.authorization_headers.append(authorization)
            assert self.headers.get("X-Amz-Date")
            assert self.headers.get("X-Amz-Content-Sha256")
            return True

        def _parts(self) -> tuple[str, dict[str, list[str]]]:
            parsed = urlsplit(self.path)
            return parsed.path, parse_qs(parsed.query, keep_blank_values=True)

        def do_PUT(self) -> None:  # noqa: N802
            if not self._signed():
                self._send(403, b"<Error><Code>AccessDenied</Code></Error>")
                return
            path, query = self._parts()
            body = self._body()
            assert (
                self.headers["X-Amz-Content-Sha256"] == hashlib.sha256(body).hexdigest()
            )
            if path == "/raos-raw" and not query:
                assert self.headers["X-Amz-Bucket-Object-Lock-Enabled"] == "true"
                state.bucket_exists = True
                state.object_lock = True
                self._send(200)
                return
            if path == "/raos-raw" and "versioning" in query:
                assert b"<Status>Enabled</Status>" in body
                state.versioning = True
                self._send(200)
                return
            if path.startswith("/raos-raw/"):
                assert state.versioning
                version = f"version-{state.next_version}"
                state.next_version += 1
                state.objects[version] = {
                    "body": body,
                    "key": path.removeprefix("/raos-raw/"),
                    "headers": {
                        name.lower(): value for name, value in self.headers.items()
                    },
                }
                self._send(200, headers={"X-Amz-Version-Id": version})
                return
            self._send(404)

        def do_HEAD(self) -> None:  # noqa: N802
            self._get_or_head()

        def do_GET(self) -> None:  # noqa: N802
            self._get_or_head()

        def _get_or_head(self) -> None:
            path, query = self._parts()
            if not self._signed():
                self._send(403, b"<Error><Code>AccessDenied</Code></Error>")
                return
            if path == "/" and not query:
                buckets = (
                    "<Bucket><Name>raos-raw</Name></Bucket>"
                    if state.bucket_exists
                    else ""
                )
                self._send(
                    200,
                    f"<ListAllMyBucketsResult><Buckets>{buckets}</Buckets>"
                    f"</ListAllMyBucketsResult>".encode(),
                )
                return
            if path == "/raos-raw" and "versioning" in query:
                status = "<Status>Enabled</Status>" if state.versioning else ""
                self._send(
                    200,
                    f"<VersioningConfiguration>{status}</VersioningConfiguration>".encode(),
                )
                return
            if path == "/raos-raw" and "object-lock" in query:
                enabled = "Enabled" if state.object_lock else "Disabled"
                self._send(
                    200,
                    f"<ObjectLockConfiguration><ObjectLockEnabled>{enabled}</ObjectLockEnabled>"
                    f"</ObjectLockConfiguration>".encode(),
                )
                return
            if path == "/raos-raw" and "policy" in query:
                self._send(404, b"<Error><Code>NoSuchBucketPolicy</Code></Error>")
                return
            if path == "/raos-raw" and "lifecycle" in query:
                if state.lifecycle_configuration is None:
                    self._send(
                        404,
                        b"<Error><Code>NoSuchLifecycleConfiguration</Code></Error>",
                    )
                else:
                    self._send(200, state.lifecycle_configuration)
                return
            if path == "/raos-raw" and "versions" in query:
                prefix = query.get("prefix", [""])[0]
                versions = "".join(
                    f"<Version><Key>{item['key']}</Key><VersionId>{version}</VersionId>"
                    f"</Version>"
                    for version, item in state.objects.items()
                    if item["key"] == prefix
                )
                self._send(
                    200, f"<ListVersionsResult>{versions}</ListVersionsResult>".encode()
                )
                return
            if path.startswith("/raos-raw/"):
                version = query.get("versionId", [""])[0]
                item = state.objects.get(version)
                if item is None:
                    self._send(404, b"<Error><Code>NoSuchVersion</Code></Error>")
                    return
                if "tagging" in query:
                    self._send(
                        200,
                        b"<Tagging><TagSet><Tag><Key>raos-retention-class</Key>"
                        b"<Value>policy-pending</Value></Tag></TagSet></Tagging>",
                    )
                    return
                headers = {
                    name: value
                    for name, value in item["headers"].items()
                    if name == "content-type" or name.startswith("x-amz-meta-")
                }
                headers["X-Amz-Version-Id"] = version
                self._send(200, item["body"], headers=headers)
                return
            self._send(404)

    return Handler


@contextmanager
def _server(
    lifecycle_configuration: bytes | None = None,
) -> Iterator[tuple[_S3State, fixture.Endpoint]]:
    """Exercise real HTTP framing over socketpairs allowed by the CI sandbox."""

    state = _S3State(lifecycle_configuration)
    handler = _handler(state)
    threads: list[threading.Thread] = []

    class InMemoryServer:
        server_name = "127.0.0.1"
        server_port = 18333

    def serve(peer: socket.socket) -> None:
        try:
            handler(peer, ("socketpair", 0), InMemoryServer())
        finally:
            peer.close()

    class SocketPairHTTPConnection(HTTPConnection):
        def connect(self) -> None:
            client, server = socket.socketpair()
            self.sock = client
            thread = threading.Thread(target=serve, args=(server,), daemon=True)
            threads.append(thread)
            thread.start()

    with patch.object(fixture.http.client, "HTTPConnection", SocketPairHTTPConnection):
        yield state, fixture.Endpoint("127.0.0.1", InMemoryServer.server_port)

    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()


def _config(path: Path) -> fixture.Credentials:
    fixture.create_identity_config(path)
    return fixture.load_credentials(path)


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:8333",
        "http://localhost:8333",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://user@127.0.0.1:8333",
        "http://127.0.0.1:8333/path",
        "http://127.0.0.1:8333?query=true",
    ],
)
def test_endpoint_rejects_non_loopback_or_ambiguous_values(value: str) -> None:
    with pytest.raises(fixture.FixtureError):
        fixture.parse_endpoint(value)


def test_generated_config_is_private_valid_and_exclusive(tmp_path: Path) -> None:
    path = tmp_path / "identity.json"
    credentials = _config(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert credentials.access_key.startswith("RAOS")
    assert len(credentials.secret_key) >= 32
    before = path.read_bytes()
    with pytest.raises(fixture.FixtureError):
        fixture.create_identity_config(path)
    assert path.read_bytes() == before


def test_validate_config_cli_never_prints_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "identity.json"
    credentials = _config(path)
    assert fixture.main(["validate-config", "--config-file", str(path)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"mode": "validate-config", "status": "PASS"}
    assert credentials.access_key not in captured.out + captured.err
    assert credentials.secret_key not in captured.out + captured.err


def test_config_loader_rejects_symlink_and_permissions(tmp_path: Path) -> None:
    path = tmp_path / "identity.json"
    _config(path)
    link = tmp_path / "identity-link.json"
    link.symlink_to(path)
    with pytest.raises(fixture.FixtureError, match="must not be symlinks"):
        fixture.load_credentials(link)
    path.chmod(0o640)
    with pytest.raises(fixture.FixtureError, match="0600"):
        fixture.load_credentials(path)


def test_config_creator_rejects_a_symlinked_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(fixture.FixtureError, match="parent directory must not"):
        fixture.create_identity_config(linked_parent / "identity.json")
    assert not (real_parent / "identity.json").exists()


def test_untrusted_error_code_is_replaced_with_a_bounded_constant() -> None:
    body = b"<Error><Code>Denied&#10;terminal-control</Code></Error>"
    assert fixture._error_code(body) == "INVALID_S3_ERROR_CODE"


def test_config_loader_rejects_unexpected_identity_shape(tmp_path: Path) -> None:
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"identities": []}), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(fixture.FixtureError, match="exactly one identity"):
        fixture.load_credentials(path)


def test_full_acceptance_proves_hash_versions_tamper_and_retention_hook(
    tmp_path: Path,
) -> None:
    credentials = _config(tmp_path / "identity.json")
    with _server() as (state, endpoint):
        result = fixture.run_acceptance(fixture.S3Client(endpoint, credentials))

    assert result["status"] == "PASS"
    assert result["version_count_verified"] == 2
    assert result["hash_verification"] == "PASS"
    assert result["tamper_detection"] == "PASS"
    assert result["retention_hook"] == "OBJECT_LOCK_CAPABILITY_AND_POLICY_PENDING_TAG"
    assert result["default_retention"] == "UNSET_OD014_PENDING"
    assert result["lifecycle_configuration"] == "ABSENT"
    assert len(state.objects) == 2
    assert len(state.authorization_headers) >= 10
    assert all(
        credentials.secret_key not in value for value in state.authorization_headers
    )


def test_verify_object_rejects_wrong_digest(tmp_path: Path) -> None:
    credentials = _config(tmp_path / "identity.json")
    with _server() as (_state, endpoint):
        client = fixture.S3Client(endpoint, credentials)
        fixture.bootstrap_bucket(client)
        version, _digest = fixture.put_object(
            client,
            fixture.DEFAULT_BUCKET,
            fixture.DEFAULT_OBJECT_KEY,
            b"trusted bytes",
            acquired_at="2026-08-02T00:00:00Z",
        )
        with pytest.raises(fixture.IntegrityError):
            fixture.verify_object(
                client,
                fixture.DEFAULT_BUCKET,
                fixture.DEFAULT_OBJECT_KEY,
                version,
                "0" * 64,
                expected_acquired_at="2026-08-02T00:00:00Z",
            )


def test_verify_object_rejects_changed_acquired_at_metadata(tmp_path: Path) -> None:
    credentials = _config(tmp_path / "identity.json")
    acquired_at = "2026-08-02T00:00:00Z"
    with _server() as (state, endpoint):
        client = fixture.S3Client(endpoint, credentials)
        fixture.bootstrap_bucket(client)
        version, digest = fixture.put_object(
            client,
            fixture.DEFAULT_BUCKET,
            fixture.DEFAULT_OBJECT_KEY,
            b"trusted bytes",
            acquired_at=acquired_at,
        )
        state.objects[version]["headers"]["x-amz-meta-acquired-at"] = (
            "2026-08-02T00:00:01Z"
        )
        with pytest.raises(fixture.IntegrityError, match="acquired-at"):
            fixture.verify_object(
                client,
                fixture.DEFAULT_BUCKET,
                fixture.DEFAULT_OBJECT_KEY,
                version,
                digest,
                expected_acquired_at=acquired_at,
            )


def test_bootstrap_rejects_preexisting_lifecycle_configuration(
    tmp_path: Path,
) -> None:
    credentials = _config(tmp_path / "identity.json")
    lifecycle = (
        b"<LifecycleConfiguration><Rule><Status>Enabled</Status>"
        b"<Expiration><Days>1</Days></Expiration></Rule></LifecycleConfiguration>"
    )
    with _server(lifecycle) as (_state, endpoint):
        with pytest.raises(
            fixture.FixtureError, match="lifecycle configuration exists"
        ):
            fixture.bootstrap_bucket(fixture.S3Client(endpoint, credentials))
