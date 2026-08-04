#!/usr/bin/env python3
"""Bootstrap and verify the ST-0202 local S3-compatible object service.

The client is intentionally implemented with the Python standard library.  It
only accepts a loopback HTTP endpoint and reads credentials from the same
file-backed static identity document mounted into the service container.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from typing import Final
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET


AWS_REGION: Final = "us-east-1"
AWS_SERVICE: Final = "s3"
DEFAULT_BUCKET: Final = "raos-raw"
DEFAULT_OBJECT_KEY: Final = "fixtures/st-0202/object-artifact.bin"
MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
MAX_CONFIG_BYTES: Final = 16 * 1024
REQUIRED_ACTIONS: Final = frozenset({"Admin", "Read", "List", "Tagging", "Write"})


class FixtureError(RuntimeError):
    """Raised when the candidate service violates the maintained fixture contract."""


class IntegrityError(FixtureError):
    """Raised when stored bytes or integrity metadata do not match expectations."""


class S3Error(FixtureError):
    """A bounded S3 error response."""

    def __init__(self, operation: str, status: int, code: str) -> None:
        self.operation = operation
        self.status = status
        self.code = code
        super().__init__(f"{operation} failed with HTTP {status} ({code})")


@dataclass(frozen=True)
class Credentials:
    access_key: str
    secret_key: str


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int

    @property
    def authority(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


def _read_bounded_response(response: http.client.HTTPResponse) -> bytes:
    declared = response.getheader("Content-Length")
    if declared is not None:
        try:
            length = int(declared, 10)
        except ValueError as error:
            raise FixtureError("response Content-Length is invalid") from error
        if length < 0 or length > MAX_RESPONSE_BYTES:
            raise FixtureError("response body exceeds the maintained size bound")
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise FixtureError("response body exceeds the maintained size bound")
    return body


def _xml_local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _xml_texts(body: bytes, name: str) -> list[str]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise FixtureError("S3 response is not well-formed XML") from error
    return [
        (element.text or "").strip()
        for element in root.iter()
        if _xml_local_name(element) == name
    ]


def _error_code(body: bytes) -> str:
    if not body:
        return "NO_ERROR_DOCUMENT"
    try:
        values = _xml_texts(body, "Code")
    except FixtureError:
        return "UNPARSEABLE_ERROR_DOCUMENT"
    if not values or not values[0]:
        return "UNKNOWN_S3_ERROR"
    code = values[0]
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", code) is None:
        return "INVALID_S3_ERROR_CODE"
    return code


def parse_endpoint(value: str) -> Endpoint:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise FixtureError(
            "endpoint must be an uncredentialed http://127.0.0.1:PORT URL"
        )
    try:
        port = parsed.port
    except ValueError as error:
        raise FixtureError("endpoint port is invalid") from error
    if port is None or not 1024 <= port <= 65535:
        raise FixtureError("endpoint port must be from 1024 through 65535")
    return Endpoint(host="127.0.0.1", port=port)


def _validate_credential_text(label: str, value: object, minimum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= 128:
        raise FixtureError(f"static identity {label} has an invalid length")
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise FixtureError(f"static identity {label} must contain printable ASCII")
    return value


def load_credentials(path: Path) -> Credentials:
    absolute = Path(os.path.abspath(path))
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as error:
        raise FixtureError(
            "unable to resolve the static identity file safely"
        ) from error
    if absolute != resolved:
        raise FixtureError(
            "static identity file and its ancestors must not be symlinks"
        )
    try:
        descriptor = os.open(absolute, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as error:
        raise FixtureError("unable to open the static identity file safely") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise FixtureError("static identity path must be a regular file")
        if metadata.st_uid != os.getuid():
            raise FixtureError("static identity file must be owned by the current user")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise FixtureError("static identity file mode must be exactly 0600")
        if not 1 <= metadata.st_size <= MAX_CONFIG_BYTES:
            raise FixtureError(
                "static identity file size is outside the maintained bound"
            )
        content = bytearray()
        while len(content) <= MAX_CONFIG_BYTES:
            chunk = os.read(descriptor, min(4096, MAX_CONFIG_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > MAX_CONFIG_BYTES:
            raise FixtureError("static identity file exceeds the maintained size bound")
    finally:
        os.close(descriptor)

    try:
        document = json.loads(bytes(content))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FixtureError(
            "static identity file must be one valid UTF-8 JSON document"
        ) from error
    if not isinstance(document, dict) or set(document) != {"identities"}:
        raise FixtureError("static identity document must contain only identities")
    identities = document["identities"]
    if not isinstance(identities, list) or len(identities) != 1:
        raise FixtureError("static identity document must contain exactly one identity")
    identity = identities[0]
    if not isinstance(identity, dict) or set(identity) != {
        "name",
        "credentials",
        "actions",
    }:
        raise FixtureError("static identity has unexpected or missing fields")
    if identity["name"] != "raos-local-object-storage":
        raise FixtureError("static identity name differs from the maintained contract")
    actions = identity["actions"]
    if (
        not isinstance(actions, list)
        or any(not isinstance(action, str) for action in actions)
        or len(actions) != len(set(actions))
        or frozenset(actions) != REQUIRED_ACTIONS
    ):
        raise FixtureError(
            "static identity actions differ from the maintained contract"
        )
    credentials = identity["credentials"]
    if not isinstance(credentials, list) or len(credentials) != 1:
        raise FixtureError("static identity must contain exactly one credential")
    credential = credentials[0]
    if not isinstance(credential, dict) or set(credential) != {
        "accessKey",
        "secretKey",
    }:
        raise FixtureError("static credential has unexpected or missing fields")
    return Credentials(
        _validate_credential_text("access key", credential["accessKey"], 16),
        _validate_credential_text("secret key", credential["secretKey"], 32),
    )


def create_identity_config(path: Path) -> None:
    document = {
        "identities": [
            {
                "name": "raos-local-object-storage",
                "credentials": [
                    {
                        "accessKey": f"RAOS{secrets.token_hex(12).upper()}",
                        "secretKey": secrets.token_urlsafe(48),
                    }
                ],
                "actions": ["Admin", "Read", "List", "Tagging", "Write"],
            }
        ]
    }
    encoded = (
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    absolute = Path(os.path.abspath(path))
    try:
        parent = absolute.parent.resolve(strict=True)
    except OSError as error:
        raise FixtureError("static identity parent directory is unavailable") from error
    if parent != absolute.parent:
        raise FixtureError("static identity parent directory must not be a symlink")
    created = False
    try:
        descriptor = os.open(
            absolute,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        created = True
    except OSError as error:
        raise FixtureError(
            "unable to create a new static identity file safely"
        ) from error
    written = 0
    complete = False
    try:
        os.fchmod(descriptor, 0o600)
        while written < len(encoded):
            count = os.write(descriptor, encoded[written:])
            if count <= 0:
                raise OSError("short write while creating static identity")
            written += count
        os.fsync(descriptor)
        complete = True
    except OSError as error:
        raise FixtureError("unable to write the static identity file safely") from error
    finally:
        os.close(descriptor)
        if created and not complete:
            try:
                absolute.unlink()
            except OSError:
                pass


def _aws_quote(value: str, *, safe: str = "-_.~") -> str:
    return quote(value, safe=safe, encoding="utf-8", errors="strict")


def _canonical_query(parameters: Sequence[tuple[str, str]]) -> str:
    encoded = [(_aws_quote(key), _aws_quote(value)) for key, value in parameters]
    return "&".join(f"{key}={value}" for key, value in sorted(encoded))


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


class S3Client:
    def __init__(
        self,
        endpoint: Endpoint,
        credentials: Credentials,
        *,
        clock: Callable[[], datetime] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = endpoint
        self.credentials = credentials
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.timeout = timeout

    def _authorization(
        self,
        method: str,
        canonical_uri: str,
        canonical_query: str,
        headers: Mapping[str, str],
        payload_hash: str,
        timestamp: datetime,
    ) -> str:
        normalized = {
            key.lower().strip(): " ".join(value.strip().split())
            for key, value in headers.items()
        }
        signed_headers = ";".join(sorted(normalized))
        canonical_headers = "".join(
            f"{key}:{normalized[key]}\n" for key in sorted(normalized)
        )
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        date = timestamp.strftime("%Y%m%d")
        scope = f"{date}/{AWS_REGION}/{AWS_SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                timestamp.strftime("%Y%m%dT%H%M%SZ"),
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        date_key = _sign(f"AWS4{self.credentials.secret_key}".encode(), date)
        region_key = _sign(date_key, AWS_REGION)
        service_key = _sign(region_key, AWS_SERVICE)
        signing_key = _sign(service_key, "aws4_request")
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        return (
            f"AWS4-HMAC-SHA256 Credential={self.credentials.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Sequence[tuple[str, str]] = (),
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> Response:
        if not path.startswith("/") or "?" in path or "#" in path:
            raise FixtureError("request path must be an absolute path without a query")
        canonical_uri = _aws_quote(path, safe="/-_.~")
        canonical_query = _canonical_query(query)
        payload_hash = hashlib.sha256(body).hexdigest()
        timestamp = self.clock().astimezone(timezone.utc)
        request_headers = {key.lower(): value for key, value in (headers or {}).items()}
        request_headers.update(
            {
                "host": self.endpoint.authority,
                "x-amz-content-sha256": payload_hash,
                "x-amz-date": timestamp.strftime("%Y%m%dT%H%M%SZ"),
            }
        )
        request_headers["authorization"] = self._authorization(
            method,
            canonical_uri,
            canonical_query,
            request_headers,
            payload_hash,
            timestamp,
        )
        target = canonical_uri
        if canonical_query:
            target = f"{target}?{canonical_query}"
        connection = http.client.HTTPConnection(
            self.endpoint.host, self.endpoint.port, timeout=self.timeout
        )
        try:
            connection.request(method, target, body=body, headers=dict(request_headers))
            raw = connection.getresponse()
            response_body = _read_bounded_response(raw)
            response_headers = {key.lower(): value for key, value in raw.getheaders()}
            return Response(raw.status, response_headers, response_body)
        except (OSError, http.client.HTTPException) as error:
            raise FixtureError("loopback S3 request failed") from error
        finally:
            connection.close()

    def require(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        expected: Iterable[int],
        query: Sequence[tuple[str, str]] = (),
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> Response:
        response = self.request(method, path, query=query, headers=headers, body=body)
        if response.status not in set(expected):
            raise S3Error(operation, response.status, _error_code(response.body))
        return response


def unsigned_request(
    endpoint: Endpoint,
    method: str,
    path: str,
    *,
    query: str = "",
    timeout: float = 5.0,
) -> Response:
    connection = http.client.HTTPConnection(
        endpoint.host, endpoint.port, timeout=timeout
    )
    target = path if not query else f"{path}?{query}"
    try:
        connection.request(method, target, headers={"host": endpoint.authority})
        raw = connection.getresponse()
        return Response(
            raw.status,
            {key.lower(): value for key, value in raw.getheaders()},
            _read_bounded_response(raw),
        )
    except (OSError, http.client.HTTPException) as error:
        raise FixtureError("unsigned loopback S3 request failed") from error
    finally:
        connection.close()


def wait_for_authenticated_ready(client: S3Client, attempts: int = 20) -> None:
    last_error: FixtureError | None = None
    for attempt in range(attempts):
        try:
            client.require("ListBuckets", "GET", "/", expected={200})
            return
        except FixtureError as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.5)
    raise FixtureError("authenticated S3 endpoint did not become ready") from last_error


def _bucket_path(bucket: str) -> str:
    if bucket != DEFAULT_BUCKET:
        raise FixtureError("bucket differs from the maintained ST-0202 contract")
    return f"/{bucket}"


def _object_path(bucket: str, key: str) -> str:
    if not key or key.startswith("/") or ".." in key.split("/"):
        raise FixtureError("object key is unsafe")
    return f"{_bucket_path(bucket)}/{key}"


def _bucket_names(response: Response) -> set[str]:
    return set(_xml_texts(response.body, "Name"))


def _assert_versioning_enabled(response: Response) -> None:
    if _xml_texts(response.body, "Status") != ["Enabled"]:
        raise FixtureError("bucket versioning is not Enabled")


def _assert_object_lock_enabled(response: Response) -> None:
    values = _xml_texts(response.body, "ObjectLockEnabled")
    if values != ["Enabled"]:
        raise FixtureError("bucket Object Lock capability is not Enabled")
    if _xml_texts(response.body, "DefaultRetention"):
        raise FixtureError("bucket unexpectedly defines a default retention period")


def bootstrap_bucket(
    client: S3Client, bucket: str = DEFAULT_BUCKET
) -> dict[str, object]:
    wait_for_authenticated_ready(client)
    anonymous = unsigned_request(client.endpoint, "GET", "/")
    if anonymous.status not in {401, 403}:
        raise FixtureError("anonymous S3 access is not fail-closed")

    listed = client.require("ListBuckets", "GET", "/", expected={200})
    if bucket not in _bucket_names(listed):
        client.require(
            "CreateBucket",
            "PUT",
            _bucket_path(bucket),
            expected={200},
            headers={"x-amz-bucket-object-lock-enabled": "true"},
        )

    versioning_document = (
        b'<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        b"<Status>Enabled</Status></VersioningConfiguration>"
    )
    client.require(
        "PutBucketVersioning",
        "PUT",
        _bucket_path(bucket),
        expected={200},
        query=(("versioning", ""),),
        headers={
            "content-md5": base64.b64encode(
                hashlib.md5(versioning_document, usedforsecurity=False).digest()
            ).decode(),
            "content-type": "application/xml",
        },
        body=versioning_document,
    )
    versioning = client.require(
        "GetBucketVersioning",
        "GET",
        _bucket_path(bucket),
        expected={200},
        query=(("versioning", ""),),
    )
    _assert_versioning_enabled(versioning)
    lock = client.require(
        "GetObjectLockConfiguration",
        "GET",
        _bucket_path(bucket),
        expected={200},
        query=(("object-lock", ""),),
    )
    _assert_object_lock_enabled(lock)

    anonymous_bucket = unsigned_request(
        client.endpoint, "GET", _bucket_path(bucket), query="list-type=2"
    )
    if anonymous_bucket.status not in {401, 403}:
        raise FixtureError("bucket permits anonymous listing")

    policy = client.request("GET", _bucket_path(bucket), query=(("policy", ""),))
    if policy.status == 200:
        raise FixtureError("bucket policy exists; the maintained local bucket has none")
    if policy.status not in {404, 405, 501}:
        raise S3Error("GetBucketPolicy", policy.status, _error_code(policy.body))

    lifecycle = client.request("GET", _bucket_path(bucket), query=(("lifecycle", ""),))
    if lifecycle.status == 200:
        raise FixtureError(
            "bucket lifecycle configuration exists; automatic deletion is forbidden"
        )
    if lifecycle.status != 404:
        raise S3Error(
            "GetBucketLifecycleConfiguration",
            lifecycle.status,
            _error_code(lifecycle.body),
        )
    if _error_code(lifecycle.body) != "NoSuchLifecycleConfiguration":
        raise FixtureError("bucket lifecycle absence was not proven by the S3 endpoint")

    return {
        "anonymous_access": "DENIED",
        "bucket": bucket,
        "default_retention": "UNSET_OD014_PENDING",
        "lifecycle_configuration": "ABSENT",
        "object_lock_capability": "Enabled",
        "versioning": "Enabled",
    }


def put_object(
    client: S3Client,
    bucket: str,
    key: str,
    payload: bytes,
    *,
    acquired_at: str,
) -> tuple[str, str]:
    digest = hashlib.sha256(payload).hexdigest()
    response = client.require(
        "PutObject",
        "PUT",
        _object_path(bucket, key),
        expected={200},
        headers={
            "content-type": "application/octet-stream",
            "x-amz-meta-raos-sha256": digest,
            "x-amz-meta-source": "st-0202-local-fixture",
            "x-amz-meta-acquired-at": acquired_at,
            "x-amz-meta-retention-class": "policy-pending",
            "x-amz-tagging": "raos-retention-class=policy-pending",
        },
        body=payload,
    )
    version_id = response.headers.get("x-amz-version-id", "")
    if not version_id or version_id == "null":
        raise FixtureError("PutObject did not return a non-null version ID")
    return version_id, digest


def verify_object(
    client: S3Client,
    bucket: str,
    key: str,
    version_id: str,
    expected_digest: str,
    *,
    expected_acquired_at: str,
) -> bytes:
    query = (("versionId", version_id),)
    head = client.require(
        "HeadObject",
        "HEAD",
        _object_path(bucket, key),
        expected={200},
        query=query,
    )
    if head.headers.get("x-amz-version-id") != version_id:
        raise IntegrityError("HeadObject version ID differs from the requested version")
    if (
        head.headers.get("content-type", "").split(";", 1)[0]
        != "application/octet-stream"
    ):
        raise IntegrityError("stored object Content-Type differs from the fixture")
    metadata = {
        "x-amz-meta-raos-sha256": expected_digest,
        "x-amz-meta-source": "st-0202-local-fixture",
        "x-amz-meta-retention-class": "policy-pending",
    }
    for name, expected in metadata.items():
        if head.headers.get(name) != expected:
            raise IntegrityError(f"stored object metadata mismatch: {name}")
    if head.headers.get("x-amz-meta-acquired-at") != expected_acquired_at:
        raise IntegrityError(
            "stored object acquired-at metadata differs from the fixture"
        )

    received = client.require(
        "GetObject",
        "GET",
        _object_path(bucket, key),
        expected={200},
        query=query,
    )
    if received.headers.get("x-amz-version-id") != version_id:
        raise IntegrityError("GetObject version ID differs from the requested version")
    observed_digest = hashlib.sha256(received.body).hexdigest()
    if not hmac.compare_digest(observed_digest, expected_digest):
        raise IntegrityError("stored object SHA-256 differs from the expected digest")
    return received.body


def _listed_version_ids(response: Response, key: str) -> set[str]:
    try:
        root = ET.fromstring(response.body)
    except ET.ParseError as error:
        raise FixtureError(
            "ListObjectVersions response is not well-formed XML"
        ) from error
    identifiers: set[str] = set()
    for version in root.iter():
        if _xml_local_name(version) != "Version":
            continue
        fields = {
            _xml_local_name(child): (child.text or "").strip() for child in version
        }
        if fields.get("Key") == key and fields.get("VersionId"):
            identifiers.add(fields["VersionId"])
    return identifiers


def _assert_retention_tag(
    client: S3Client, bucket: str, key: str, version_id: str
) -> None:
    response = client.require(
        "GetObjectTagging",
        "GET",
        _object_path(bucket, key),
        expected={200},
        query=(("tagging", ""), ("versionId", version_id)),
    )
    try:
        root = ET.fromstring(response.body)
    except ET.ParseError as error:
        raise FixtureError(
            "GetObjectTagging response is not well-formed XML"
        ) from error
    tags: dict[str, str] = {}
    for tag in root.iter():
        if _xml_local_name(tag) != "Tag":
            continue
        fields = {_xml_local_name(child): (child.text or "").strip() for child in tag}
        if "Key" in fields and "Value" in fields:
            tags[fields["Key"]] = fields["Value"]
    if tags != {"raos-retention-class": "policy-pending"}:
        raise FixtureError("object retention-class tag differs from the contract")


def run_acceptance(
    client: S3Client,
    bucket: str = DEFAULT_BUCKET,
    key: str = DEFAULT_OBJECT_KEY,
) -> dict[str, object]:
    bootstrap = bootstrap_bucket(client, bucket)
    acquired_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    payload_v1 = b"RAOS ST-0202 object fixture version 1\n"
    payload_v2 = b"RAOS ST-0202 object fixture version 2\n"
    version_v1, digest_v1 = put_object(
        client, bucket, key, payload_v1, acquired_at=acquired_at
    )
    verify_object(
        client,
        bucket,
        key,
        version_v1,
        digest_v1,
        expected_acquired_at=acquired_at,
    )
    version_v2, digest_v2 = put_object(
        client, bucket, key, payload_v2, acquired_at=acquired_at
    )
    if version_v1 == version_v2:
        raise FixtureError("two object writes returned the same version ID")
    verify_object(
        client,
        bucket,
        key,
        version_v2,
        digest_v2,
        expected_acquired_at=acquired_at,
    )

    versions = client.require(
        "ListObjectVersions",
        "GET",
        _bucket_path(bucket),
        expected={200},
        query=(("prefix", key), ("versions", "")),
    )
    listed = _listed_version_ids(versions, key)
    if not {version_v1, version_v2}.issubset(listed):
        raise FixtureError("ListObjectVersions omitted a fixture version")
    if (
        verify_object(
            client,
            bucket,
            key,
            version_v1,
            digest_v1,
            expected_acquired_at=acquired_at,
        )
        != payload_v1
    ):
        raise IntegrityError("the first version was not preserved")

    wrong_digest = "0" * 64 if digest_v2 != "0" * 64 else "1" * 64
    try:
        verify_object(
            client,
            bucket,
            key,
            version_v2,
            wrong_digest,
            expected_acquired_at=acquired_at,
        )
    except IntegrityError:
        tamper_detection = "PASS"
    else:
        raise FixtureError("tamper mismatch was not rejected")
    _assert_retention_tag(client, bucket, key, version_v2)

    return {
        **bootstrap,
        "formal_tst_014": "NOT_EXECUTED",
        "hash_verification": "PASS",
        "key": key,
        "retention_hook": "OBJECT_LOCK_CAPABILITY_AND_POLICY_PENDING_TAG",
        "status": "PASS",
        "tamper_detection": tamper_detection,
        "version_count_verified": 2,
        "version_1_sha256": digest_v1,
        "version_2_sha256": digest_v2,
    }


def _add_service_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--config-file", required=True, type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-config")
    create.add_argument("--output", required=True, type=Path)
    validate = commands.add_parser("validate-config")
    validate.add_argument("--config-file", required=True, type=Path)
    bootstrap = commands.add_parser("bootstrap")
    _add_service_arguments(bootstrap)
    acceptance = commands.add_parser("acceptance")
    _add_service_arguments(acceptance)
    acceptance.add_argument("--key", default=DEFAULT_OBJECT_KEY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "create-config":
            create_identity_config(arguments.output)
            result: dict[str, object] = {
                "mode": "create-config",
                "status": "PASS",
            }
        elif arguments.command == "validate-config":
            load_credentials(arguments.config_file)
            result = {
                "mode": "validate-config",
                "status": "PASS",
            }
        else:
            endpoint = parse_endpoint(arguments.endpoint)
            credentials = load_credentials(arguments.config_file)
            client = S3Client(endpoint, credentials)
            if arguments.command == "bootstrap":
                result = {
                    **bootstrap_bucket(client, arguments.bucket),
                    "formal_tst_014": "NOT_EXECUTED",
                    "mode": "bootstrap",
                    "status": "PASS",
                }
            elif arguments.command == "acceptance":
                result = {
                    **run_acceptance(client, arguments.bucket, arguments.key),
                    "mode": "acceptance",
                }
            else:  # pragma: no cover - argparse enforces the command set.
                raise FixtureError("unknown command")
    except FixtureError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
