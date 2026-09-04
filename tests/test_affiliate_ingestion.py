from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.affiliate_ingestion.client import FetchBatch, RawPage, parse_records
from tools.affiliate_ingestion.config import (
    ConfigError,
    atomic_write_config,
    initial_config,
    load_config,
    provider_diagnostics,
    redact,
)
from tools.affiliate_ingestion.normalize import normalize_record
from tools.affiliate_ingestion.providers import PROVIDERS, get_provider
from tools.affiliate_ingestion.storage import persist_batch


# These tests use synthetic payloads and prohibit any real provider or DNS call.
import gzip
import io
import socket
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from email.message import Message
from unittest.mock import Mock, patch

import pytest

from tools.affiliate_ingestion.cli import main
from tools.affiliate_ingestion.client import (
    AffiliateHttpClient,
    EndpointSecurityError,
    EndpointValidator,
    FetchError,
    _NoUnsafeRedirect,
    _PinnedHTTPSConnection,
    _authentication,
    fetch_resource,
)
from tools.affiliate_ingestion.config import validate_config


class ProviderTests(unittest.TestCase):
    def test_all_six_manifests_exist(self) -> None:
        self.assertEqual(
            set(PROVIDERS),
            {"a8net", "valuecommerce", "moshimo", "linkshare", "accesstrade", "afb"},
        )
        self.assertEqual(get_provider("A8.net").key, "a8net")
        self.assertEqual(get_provider("リンクシェア").key, "linkshare")

    def test_skeleton_has_all_six_sections(self) -> None:
        config = initial_config()
        self.assertEqual(set(config["providers"]), set(PROVIDERS))
        self.assertTrue(
            all(not section["enabled"] for section in config["providers"].values())
        )


class ConfigTests(unittest.TestCase):
    def test_owner_only_atomic_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            atomic_write_config(path, initial_config())
            loaded = load_config(path)
            self.assertEqual(loaded["schema_version"], 1)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_diagnostics_require_account_and_resource(self) -> None:
        config = initial_config()
        config["providers"]["a8net"]["enabled"] = True
        errors = provider_diagnostics(config, "a8net")
        self.assertIn("account_id is empty", errors)
        self.assertIn("no resource is enabled", errors)

    def test_redaction_is_recursive(self) -> None:
        redacted = redact(
            {"token": "abc", "nested": {"client_secret": "def", "name": "visible"}}
        )
        self.assertEqual(redacted["token"], "***REDACTED***")
        self.assertEqual(redacted["nested"]["client_secret"], "***REDACTED***")
        self.assertEqual(redacted["nested"]["name"], "visible")


class ParseTests(unittest.TestCase):
    def test_json_record_path(self) -> None:
        records, parsed = parse_records(
            json.dumps({"data": {"items": [{"id": "1"}, {"id": "2"}]}}).encode(),
            configured_format="json",
            record_path="data.items",
        )
        self.assertEqual([record["id"] for record in records], ["1", "2"])
        self.assertIsInstance(parsed, dict)

    def test_cp932_csv(self) -> None:
        body = "商品ID,商品名,価格\n1,テスト,1,000\n".encode("cp932")
        # Quote the thousands separator to keep the fixture valid CSV.
        body = '商品ID,商品名,価格\n1,テスト,"1,000"\n'.encode("cp932")
        records, _ = parse_records(body, configured_format="csv")
        self.assertEqual(records[0]["商品名"], "テスト")

    def test_zip_csv(self) -> None:
        with tempfile.TemporaryFile() as handle:
            with zipfile.ZipFile(handle, "w") as archive:
                archive.writestr("products.csv", "id,name\n1,Example\n")
            handle.seek(0)
            records, _ = parse_records(handle.read(), configured_format="auto")
        self.assertEqual(records, [{"id": "1", "name": "Example"}])


class NormalizationAndStorageTests(unittest.TestCase):
    def test_normalization_and_lossless_raw(self) -> None:
        source = {"product_id": "P-1", "product_name": "Sample", "price": "¥1,200"}
        normalized = normalize_record(
            "a8net", "products", source, fetched_at="2026-09-05T00:00:00+00:00"
        )
        self.assertEqual(normalized["source_id"], "P-1")
        self.assertEqual(normalized["name"], "Sample")
        self.assertEqual(normalized["price"], "1200")
        self.assertEqual(normalized["raw"], source)

    def test_persist_batch_writes_manifest_raw_and_ndjson(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            batch = FetchBatch(
                provider="afb",
                resource="programs",
                fetched_at="2026-09-05T00:00:00+00:00",
                records=[{"id": "1", "name": "Example"}],
                pages=[
                    RawPage(
                        index=1,
                        request_url="https://example.invalid/feed",
                        content_type="application/json",
                        body=b'{"items": [{"id": "1"}]}',
                        status=200,
                    )
                ],
            )
            manifest = persist_batch(batch, {"root": directory})
            self.assertEqual(manifest["record_count"], 1)
            self.assertTrue(Path(manifest["manifest_path"]).is_file())
            self.assertTrue(Path(manifest["state_path"]).is_file())
            normalized_path = Path(directory) / manifest["normalized_path"]
            self.assertTrue(normalized_path.is_file())


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline test attempted a network operation")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)


def ready_config(provider="a8net"):
    config = initial_config()
    section = config["providers"][provider]
    section.update(enabled=True, account_id="synthetic-account")
    section["resources"]["products"].update(
        enabled=True, endpoint="https://example.invalid/products", format="json"
    )
    return config


def response(payload):
    headers = Message()
    headers["Content-Type"] = "application/json"
    return (
        200,
        headers,
        json.dumps(payload).encode(),
        "https://example.invalid/products",
    )


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_each_provider_fetches_synthetic_payload(provider):
    config = ready_config(provider)
    with patch.object(
        AffiliateHttpClient, "request", return_value=response([{"id": "1"}])
    ) as request:
        batch = fetch_resource(config, provider, "products")
    assert batch.records == [{"id": "1"}]
    assert batch.provider == provider
    request.assert_called_once()


def test_disabled_resource_and_default_config_cannot_fetch():
    with pytest.raises(ConfigError):
        fetch_resource(initial_config(), "a8net", "products")
    config = ready_config()
    config["providers"]["a8net"]["resources"]["products"]["enabled"] = False
    with pytest.raises(ConfigError):
        fetch_resource(config, "a8net", "products")


@pytest.mark.parametrize("value", ["false", 1, None])
def test_non_boolean_enablement_is_rejected(value):
    config = ready_config()
    config["providers"]["a8net"]["enabled"] = value
    with pytest.raises(ConfigError):
        validate_config(config)


def test_invalid_limits_modes_and_write_methods_are_rejected():
    for field, value in [
        ("mode", "unknown"),
        ("method", "POST"),
        ("pagination", {"max_pages": -1}),
    ]:
        config = ready_config()
        config["providers"]["a8net"]["resources"]["products"][field] = value
        with pytest.raises(ConfigError):
            validate_config(config)
    config = ready_config()
    config["storage"]["max_response_bytes"] = -1
    with pytest.raises(ConfigError):
        validate_config(config)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid",
        "https://user:password@example.invalid",
        "https://example.invalid:bad",
        "https://example.invalid/with space",
    ],
)
def test_invalid_endpoint_syntax_is_rejected_without_dns(url):
    with pytest.raises(EndpointSecurityError):
        EndpointValidator.validate_syntax(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_private_destinations_are_rejected(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    with patch.object(
        socket,
        "getaddrinfo",
        return_value=[(family, socket.SOCK_STREAM, 6, "", (address, 443))],
    ):
        with pytest.raises(EndpointSecurityError):
            EndpointValidator().validate("https://example.invalid")


def test_connection_uses_the_validated_dns_result_once():
    address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
    validator = EndpointValidator()
    with (
        patch.object(socket, "getaddrinfo", return_value=[address]) as dns,
        patch.object(socket, "socket") as socket_factory,
    ):
        connection = _PinnedHTTPSConnection("example.invalid", validator=validator)
        connection._create_connection(("example.invalid", 443), 1)
    dns.assert_called_once()
    socket_factory.return_value.connect.assert_called_once_with(("8.8.8.8", 443))


def test_redirect_cannot_forward_credentials_to_another_origin():
    handler = _NoUnsafeRedirect(EndpointValidator())
    request = urllib.request.Request(
        "https://example.invalid/feed", headers={"Authorization": "Bearer synthetic"}
    )
    with pytest.raises(EndpointSecurityError, match="Cross-origin"):
        handler.redirect_request(
            request, None, 302, "", Message(), "https://other.invalid/feed"
        )


def test_same_origin_redirect_is_validated_and_preserves_headers():
    validator = Mock(spec=EndpointValidator)
    handler = _NoUnsafeRedirect(validator)
    request = urllib.request.Request(
        "https://example.invalid/feed", headers={"Authorization": "Bearer synthetic"}
    )
    redirected = handler.redirect_request(
        request, None, 302, "", Message(), "https://example.invalid/next"
    )
    assert redirected.get_header("Authorization") == "Bearer synthetic"
    validator.validate.assert_called_once_with("https://example.invalid/next")


@pytest.mark.parametrize("kind", ["page", "offset", "cursor", "next_url"])
def test_pagination_reads_second_page_and_stops(kind):
    config = ready_config()
    config["providers"]["a8net"]["resources"]["products"]["pagination"] = {
        "type": kind,
        "max_pages": 3,
        "page_size": 1,
    }
    first = {
        "items": [{"id": "1"}],
        "next_cursor": "second",
        "next": "/products?page=2",
    }
    second = {"items": []}
    with (
        patch.object(
            AffiliateHttpClient,
            "request",
            side_effect=[response(first), response(second)],
        ) as request,
        patch.object(EndpointValidator, "validate"),
    ):
        batch = fetch_resource(config, "a8net", "products")
    assert batch.records == [{"id": "1"}]
    assert request.call_count == 2


def test_next_url_cannot_forward_credentials_to_another_origin():
    config = ready_config()
    config["providers"]["a8net"]["resources"]["products"]["pagination"] = {
        "type": "next_url",
        "max_pages": 2,
    }
    with patch.object(
        AffiliateHttpClient,
        "request",
        return_value=response(
            {"items": [{"id": "1"}], "next": "https://other.invalid/feed"}
        ),
    ) as request:
        with pytest.raises(EndpointSecurityError, match="Cross-origin"):
            fetch_resource(config, "a8net", "products")
    request.assert_called_once()


@pytest.mark.parametrize(
    "auth,header,query",
    [
        ({"type": "none"}, {}, {}),
        (
            {"type": "bearer", "token": "synthetic"},
            {"Authorization": "Bearer synthetic"},
            {},
        ),
        (
            {"type": "api_key_header", "api_key": "synthetic"},
            {"X-API-Key": "synthetic"},
            {},
        ),
        (
            {"type": "api_key_query", "api_key": "synthetic"},
            {},
            {"api_key": "synthetic"},
        ),
        (
            {"type": "basic", "username": "a", "password": "b"},
            {"Authorization": "Basic YTpi"},
            {},
        ),
        (
            {"type": "oauth2_client_credentials"},
            {"Authorization": "Bearer synthetic"},
            {},
        ),
        (
            {"type": "custom_headers", "secret_headers": {"X-Auth": "synthetic"}},
            {"X-Auth": "synthetic"},
            {},
        ),
    ],
)
def test_authentication_routes_to_expected_headers_and_query(auth, header, query):
    client = Mock(spec=AffiliateHttpClient)
    client.oauth2_token.return_value = "synthetic"
    assert _authentication(client, {"auth": auth}) == (header, query)


def test_missing_environment_is_not_ready(monkeypatch):
    monkeypatch.delenv("RAOS_TEST_AFFILIATE_MISSING", raising=False)
    config = ready_config()
    ref = "env:RAOS_TEST_AFFILIATE_MISSING"
    config["providers"]["a8net"]["auth"] = {"type": "bearer", "token": ref}
    assert "required environment variable is missing or empty" in provider_diagnostics(
        config, "a8net"
    )


def test_redacted_config_hides_account_url_query_and_custom_headers():
    data = {
        "account_id": "synthetic",
        "endpoint": "https://example.invalid/private?key=synthetic",
        "headers": {"Authorization": "synthetic"},
        "query": {"opaque": "synthetic"},
    }
    assert "synthetic" not in json.dumps(redact(data))
    assert "example.invalid" not in json.dumps(redact(data))


def test_dry_run_checks_endpoints_and_disabled_resources_without_network(tmp_path):
    config = ready_config()
    path = tmp_path / "affiliate-networks.json"
    atomic_write_config(path, config)
    assert (
        main(
            [
                "--config",
                str(path),
                "fetch",
                "a8net",
                "--resource",
                "products",
                "--dry-run",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--config",
                str(path),
                "fetch",
                "a8net",
                "--resource",
                "programs",
                "--dry-run",
            ]
        )
        == 2
    )
    config["providers"]["a8net"]["resources"]["products"]["endpoint"] = (
        "http://example.invalid"
    )
    atomic_write_config(path, config)
    assert (
        main(
            [
                "--config",
                str(path),
                "fetch",
                "a8net",
                "--resource",
                "products",
                "--dry-run",
            ]
        )
        == 2
    )


def test_registration_preserves_account_and_numeric_secret_strings(tmp_path):
    path = tmp_path / "affiliate-networks.json"
    assert (
        main(
            [
                "--config",
                str(path),
                "register",
                "a8net",
                "--non-interactive",
                "--set",
                "account_id=00123",
                "--set",
                "auth.token=00001",
            ]
        )
        == 0
    )
    provider = load_config(path)["providers"]["a8net"]
    assert provider["account_id"] == "00123"
    assert provider["auth"]["token"] == "00001"
    assert provider["enabled"] is False


def test_cli_error_does_not_echo_invalid_assignment(tmp_path):
    output = io.StringIO()
    with redirect_stderr(output):
        assert (
            main(
                [
                    "--config",
                    str(tmp_path / "config.json"),
                    "register",
                    "a8net",
                    "--non-interactive",
                    "--set",
                    "synthetic-private-input",
                ]
            )
            == 2
        )
    assert "synthetic-private-input" not in output.getvalue()


def test_file_mode_does_not_require_remote_credentials(tmp_path):
    config = ready_config()
    path = tmp_path / "products.json.gz"
    path.write_bytes(gzip.compress(b'[{"id":"1"}]'))
    ref = "env:RAOS_TEST_AFFILIATE_MISSING"
    config["providers"]["a8net"]["auth"] = {"type": "bearer", "token": ref}
    config["providers"]["a8net"]["resources"]["products"].update(
        mode="file", path=str(path), format="auto"
    )
    batch = fetch_resource(config, "a8net", "products")
    assert batch.records == [{"id": "1"}]


def test_gzip_limit_and_explicit_missing_record_path_fail_closed():
    with pytest.raises(FetchError, match="max_uncompressed_bytes"):
        parse_records(gzip.compress(b"x" * 100), maximum_uncompressed_bytes=50)
    with pytest.raises(FetchError, match="record_path"):
        parse_records(b'{"items":[{"id":"1"}]}', record_path="missing.records")


def test_insecure_config_permissions_are_rejected(tmp_path):
    path = tmp_path / "config.json"
    atomic_write_config(path, initial_config())
    path.chmod(0o644)
    with pytest.raises(ConfigError):
        load_config(path)


def test_same_timestamp_batches_preserve_previous_run(tmp_path):
    batch = FetchBatch(
        "a8net",
        "products",
        "2026-09-05T00:00:00+00:00",
        [{"id": "1"}],
        [RawPage(1, "https://example.invalid", "application/json", b"[]", 200)],
    )
    first = persist_batch(batch, {"root": str(tmp_path)})
    previous = Path(first["manifest_path"]).read_bytes()
    second = persist_batch(batch, {"root": str(tmp_path)})
    assert first["manifest_path"] != second["manifest_path"]
    assert Path(first["manifest_path"]).read_bytes() == previous
    assert (
        json.loads(Path(second["state_path"]).read_bytes())["normalized_path"]
        == second["normalized_path"]
    )


def test_http_retry_is_bounded_and_honors_retry_after():
    config = initial_config()
    client = AffiliateHttpClient(config["http"], config["storage"])
    headers = Message()
    headers["Retry-After"] = "1"
    rejected = urllib.error.HTTPError(
        "https://example.invalid", 429, "slow down", headers, None
    )
    accepted = Mock()
    accepted.__enter__ = Mock(return_value=accepted)
    accepted.__exit__ = Mock(return_value=False)
    accepted.status = 200
    accepted.headers = Message()
    accepted.read.return_value = b"[]"
    accepted.geturl.return_value = "https://example.invalid"
    with (
        patch.object(client.validator, "validate"),
        patch.object(
            client.opener, "open", side_effect=[rejected, accepted]
        ) as request,
        patch("tools.affiliate_ingestion.client.time.sleep") as sleep,
    ):
        assert client.request("https://example.invalid")[2] == b"[]"
    assert request.call_count == 2
    assert any(call.args == (1.0,) for call in sleep.call_args_list)


def test_transport_failure_never_echoes_sensitive_url():
    config = initial_config()
    config["http"]["max_attempts"] = 1
    client = AffiliateHttpClient(config["http"], config["storage"])
    with (
        patch.object(client.validator, "validate"),
        patch.object(
            client.opener,
            "open",
            side_effect=urllib.error.URLError("synthetic-private-query"),
        ),
    ):
        with pytest.raises(FetchError) as error:
            client.request("https://example.invalid")
    assert "synthetic-private-query" not in str(error.value)


def test_oauth_token_request_uses_post_and_does_not_persist_payload():
    config = initial_config()
    client = AffiliateHttpClient(config["http"], config["storage"])
    with patch.object(
        client, "request", return_value=response({"access_token": "synthetic"})
    ) as request:
        assert (
            client.oauth2_token(
                {
                    "token_url": "https://example.invalid/token",
                    "client_id": "synthetic-id",
                    "client_secret": "fixture-secret",
                }
            )
            == "synthetic"
        )
    assert request.call_args.kwargs["method"] == "POST"
    assert request.call_args.kwargs["data"] == b"grant_type=client_credentials"


def test_response_and_aggregate_limits_stop_fetch():
    config = ready_config()
    client = AffiliateHttpClient(config["http"], {"max_response_bytes": 2})
    with pytest.raises(FetchError, match="max_response_bytes"):
        client._read_limited(io.BytesIO(b"123"))
    config["storage"]["max_uncompressed_bytes"] = 20
    with patch.object(
        AffiliateHttpClient, "request", return_value=response([{"name": "x" * 50}])
    ):
        with pytest.raises(FetchError, match="batch"):
            fetch_resource(config, "a8net", "products")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_xml_dtd_is_forbidden_for_every_encoding(encoding):
    payload = (
        '<!DOCTYPE root [<!ENTITY item "expanded">]><root><item>&item;</item></root>'
    )
    with pytest.raises(FetchError, match="DTD"):
        parse_records(payload.encode(encoding), configured_format="xml")


def test_xml_items_keep_attributes_and_repeated_children():
    records, _ = parse_records(
        b'<root><item id="1"><name>One</name><tag>A</tag><tag>B</tag></item></root>',
        configured_format="xml",
    )
    assert records == [{"@id": "1", "name": "One", "tag": ["A", "B"]}]


def test_example_config_remains_disabled_and_contains_no_assumed_auth():
    config = json.loads(
        (
            Path(__file__).parents[1] / "config/affiliate-networks.example.json"
        ).read_text()
    )
    validate_config(config)
    assert set(config["providers"]) == set(PROVIDERS)
    for provider in config["providers"].values():
        assert provider["enabled"] is False
        assert provider["auth"] == {"type": "none"}
        assert all(
            resource["enabled"] is False for resource in provider["resources"].values()
        )
