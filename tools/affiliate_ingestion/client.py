from __future__ import annotations

import base64
import csv
import gzip
import http.client
import io
import ipaddress
import json
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree

from .config import (
    ConfigError,
    provider_diagnostics,
    resolve_indirections,
    validate_config,
)


class FetchError(RuntimeError):
    pass


class EndpointSecurityError(FetchError):
    pass


@dataclass(slots=True)
class RawPage:
    index: int
    request_url: str
    content_type: str
    body: bytes
    status: int
    etag: str | None = None
    last_modified: str | None = None


@dataclass(slots=True)
class FetchBatch:
    provider: str
    resource: str
    fetched_at: str
    records: list[dict[str, Any]]
    pages: list[RawPage]
    warnings: list[str] = field(default_factory=list)


class _NoUnsafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, validator: "EndpointValidator") -> None:
        super().__init__()
        self._validator = validator

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        _require_same_origin(req.full_url, newurl)
        self._validator.validate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class EndpointValidator:
    def __init__(self, *, allow_private_network: bool = False) -> None:
        self.allow_private_network = allow_private_network

    @staticmethod
    def validate_syntax(url: str) -> urllib.parse.SplitResult:
        try:
            parsed = urllib.parse.urlsplit(url)
            parsed.port
        except ValueError as exc:
            raise EndpointSecurityError("Invalid provider endpoint") from exc
        if parsed.scheme.casefold() != "https":
            raise EndpointSecurityError("Only HTTPS provider endpoints are allowed")
        if not parsed.hostname:
            raise EndpointSecurityError("Provider endpoint has no hostname")
        if parsed.username or parsed.password:
            raise EndpointSecurityError("Credentials in provider URLs are forbidden")
        if any(character.isspace() or ord(character) < 32 for character in url):
            raise EndpointSecurityError("Whitespace in provider URLs is forbidden")
        return parsed

    def validate(self, url: str) -> urllib.parse.SplitResult:
        parsed = self.validate_syntax(url)
        self.addresses(parsed.hostname, parsed.port or 443)
        return parsed

    def addresses(self, hostname: str, port: int) -> list[Any]:
        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise EndpointSecurityError("Unable to resolve provider endpoint") from exc
        if not infos:
            raise EndpointSecurityError("Provider endpoint has no resolved address")
        for info in infos:
            address = ipaddress.ip_address(info[4][0])
            unsafe = (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            )
            if unsafe and not self.allow_private_network:
                raise EndpointSecurityError(
                    f"Provider endpoint resolves to a non-public address: {address}"
                )
        return infos


def _require_same_origin(original: str, destination: str) -> None:
    first = EndpointValidator.validate_syntax(original)
    second = EndpointValidator.validate_syntax(destination)
    if (first.hostname, first.port or 443) != (second.hostname, second.port or 443):
        raise EndpointSecurityError(
            "Cross-origin redirects and pagination are forbidden"
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect only to addresses checked in the same DNS result, preserving TLS SNI."""

    def __init__(
        self, host: str, *, validator: EndpointValidator, **kwargs: Any
    ) -> None:
        super().__init__(host, **kwargs)
        self._validator = validator
        self._create_connection = self._connect_validated

    def _connect_validated(
        self, address: tuple[str, int], timeout: Any, source_address: Any = None
    ) -> socket.socket:
        for family, socktype, proto, _, sockaddr in self._validator.addresses(*address):
            connection = socket.socket(family, socktype, proto)
            try:
                connection.settimeout(timeout)
                if source_address:
                    connection.bind(source_address)
                connection.connect(sockaddr)
                return connection
            except OSError:
                connection.close()
        raise OSError("Unable to connect to provider endpoint")


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, validator: EndpointValidator, context: ssl.SSLContext) -> None:
        super().__init__(context=context)
        self.validator = validator

    def https_open(self, request: urllib.request.Request) -> Any:
        def connection(host: str, **kwargs: Any) -> _PinnedHTTPSConnection:
            return _PinnedHTTPSConnection(host, validator=self.validator, **kwargs)

        return self.do_open(connection, request, context=self._context)


class AffiliateHttpClient:
    def __init__(
        self, http_config: Mapping[str, Any], storage_config: Mapping[str, Any]
    ) -> None:
        self.timeout = float(http_config.get("timeout_seconds", 30))
        self.max_attempts = max(1, int(http_config.get("max_attempts", 4)))
        self.minimum_interval = max(
            0.0, float(http_config.get("minimum_interval_seconds", 0.5))
        )
        self.user_agent = str(
            http_config.get("user_agent", "RAOS-AffiliateIngestion/1.0")
        )
        self.max_response_bytes = int(
            storage_config.get("max_response_bytes", 50 * 1024 * 1024)
        )
        self.max_uncompressed_bytes = int(
            storage_config.get("max_uncompressed_bytes", 200 * 1024 * 1024)
        )
        self.validator = EndpointValidator(
            allow_private_network=bool(http_config.get("allow_private_network", False))
        )
        context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _PinnedHTTPSHandler(self.validator, context),
            _NoUnsafeRedirect(self.validator),
        )
        self._last_request_monotonic = 0.0

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        if elapsed < self.minimum_interval:
            time.sleep(self.minimum_interval - elapsed)

    def _read_limited(self, response: Any) -> bytes:
        body = response.read(self.max_response_bytes + 1)
        if len(body) > self.max_response_bytes:
            raise FetchError(
                f"Provider response exceeds max_response_bytes={self.max_response_bytes}"
            )
        return body

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        data: bytes | None = None,
    ) -> tuple[int, Message, bytes, str]:
        self.validator.validate(url)
        safe_headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip"}
        safe_headers.update(headers or {})
        retry_after: float | None = None
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._pace()
            if retry_after:
                time.sleep(retry_after)
            request = urllib.request.Request(
                url=url, data=data, headers=safe_headers, method=method.upper()
            )
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    self._last_request_monotonic = time.monotonic()
                    body = self._read_limited(response)
                    if (
                        response.headers.get("Content-Encoding", "").casefold()
                        == "gzip"
                    ):
                        body = _safe_gzip(body, self.max_uncompressed_bytes)
                    return (
                        int(response.status),
                        response.headers,
                        body,
                        response.geturl(),
                    )
            except urllib.error.HTTPError as exc:
                self._last_request_monotonic = time.monotonic()
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt == self.max_attempts:
                    # Do not echo provider response bodies: an authentication
                    # service can reflect credentials or account identifiers.
                    raise FetchError(
                        f"Provider request failed with HTTP {exc.code}"
                    ) from exc
                retry_after = _parse_retry_after(exc.headers.get("Retry-After"))
                last_error = exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._last_request_monotonic = time.monotonic()
                if attempt == self.max_attempts:
                    raise FetchError("Provider connection failed") from exc
                last_error = exc
            if retry_after is None:
                retry_after = min(30.0, (2 ** (attempt - 1)) + random.random())
        raise FetchError("Provider request failed") from last_error

    def oauth2_token(self, auth: Mapping[str, Any]) -> str:
        token_url = str(auth["token_url"])
        client_id = str(auth["client_id"])
        client_secret = str(auth["client_secret"])
        form = {"grant_type": "client_credentials"}
        scope = str(auth.get("scope", "")).strip()
        if scope:
            form["scope"] = scope
        body = urllib.parse.urlencode(form).encode("ascii")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        status, _, payload, _ = self.request(
            token_url,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data=body,
        )
        if status < 200 or status >= 300:
            raise FetchError(f"OAuth token request returned HTTP {status}")
        try:
            token_response = json.loads(payload)
            access_value = token_response["access_token"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise FetchError("OAuth token response has no access_token") from exc
        if not isinstance(access_value, str) or not access_value.strip():
            raise FetchError("OAuth access_token is empty")
        return access_value


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, min(float(value), 120.0))
    except ValueError:
        return None


def _safe_gzip(body: bytes, maximum: int) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as handle:
            data = handle.read(maximum + 1)
    except (OSError, EOFError) as exc:
        raise FetchError("Invalid gzip provider payload") from exc
    if len(data) > maximum:
        raise FetchError("Gzip provider payload exceeds max_uncompressed_bytes")
    return data


def _safe_zip(body: bytes, maximum: int) -> tuple[bytes, str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise FetchError(f"Invalid ZIP provider payload: {exc}") from exc
    members = [item for item in archive.infolist() if not item.is_dir()]
    if not members:
        raise FetchError("ZIP provider payload contains no files")
    if len(members) > 100:
        raise FetchError("ZIP provider payload contains too many files")
    candidates = [
        item
        for item in members
        if Path(item.filename).suffix.casefold()
        in {".json", ".csv", ".tsv", ".xml", ".txt"}
    ]
    selected = candidates[0] if candidates else members[0]
    if selected.file_size > maximum:
        raise FetchError("ZIP member exceeds max_uncompressed_bytes")
    with archive.open(selected) as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise FetchError("ZIP member exceeds max_uncompressed_bytes")
    return data, selected.filename


def _nested_get(value: Any, path: str) -> Any:
    current = value
    for part in [part for part in path.split(".") if part]:
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def _decode_text(body: bytes, configured_encoding: str | None = None) -> str:
    encodings = [configured_encoding] if configured_encoding else []
    encodings.extend(["utf-8-sig", "utf-8", "cp932", "shift_jis"])
    seen: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding.casefold() in seen:
            continue
        seen.add(encoding.casefold())
        try:
            return body.decode(encoding)
        except UnicodeDecodeError, LookupError:
            continue
    raise FetchError("Provider payload cannot be decoded as UTF-8 or CP932")


def _flatten_xml_element(element: ElementTree.Element) -> dict[str, Any]:
    record: dict[str, Any] = {f"@{key}": value for key, value in element.attrib.items()}
    children = list(element)
    if not children:
        record["value"] = (element.text or "").strip()
        return record
    for child in children:
        tag = child.tag.rsplit("}", 1)[-1]
        if list(child):
            value: Any = _flatten_xml_element(child)
        else:
            value = (child.text or "").strip()
            if child.attrib:
                value = {
                    "value": value,
                    **{f"@{k}": v for k, v in child.attrib.items()},
                }
        if tag in record:
            existing = record[tag]
            if not isinstance(existing, list):
                existing = [existing]
            existing.append(value)
            record[tag] = existing
        else:
            record[tag] = value
    return record


class _NoDTDTreeBuilder(ElementTree.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise FetchError("XML provider payload contains a forbidden DTD declaration")


def parse_records(
    body: bytes,
    *,
    configured_format: str = "auto",
    content_type: str = "",
    filename: str = "",
    record_path: str = "",
    record_tag: str = "",
    encoding: str = "",
    maximum_uncompressed_bytes: int = 200 * 1024 * 1024,
) -> tuple[list[dict[str, Any]], Any]:
    format_name = configured_format.casefold().strip() or "auto"
    lowered_type = content_type.casefold()
    lowered_filename = filename.casefold()
    if body.startswith(b"\x1f\x8b"):
        body = _safe_gzip(body, maximum_uncompressed_bytes)
        lowered_filename = lowered_filename.removesuffix(".gz")
    if body.startswith(b"PK\x03\x04") or lowered_filename.endswith(".zip"):
        body, filename = _safe_zip(body, maximum_uncompressed_bytes)
        lowered_filename = filename.casefold()
    if format_name == "auto":
        if "json" in lowered_type or lowered_filename.endswith(".json"):
            format_name = "json"
        elif "csv" in lowered_type or lowered_filename.endswith(".csv"):
            format_name = "csv"
        elif "tab-separated" in lowered_type or lowered_filename.endswith(".tsv"):
            format_name = "tsv"
        elif "xml" in lowered_type or lowered_filename.endswith(".xml"):
            format_name = "xml"
        else:
            stripped = body.lstrip()
            if stripped.startswith((b"{", b"[")):
                format_name = "json"
            elif stripped.startswith(b"<"):
                format_name = "xml"
            else:
                format_name = "csv"
    if format_name == "json":
        try:
            parsed: Any = json.loads(_decode_text(body, encoding or None))
        except json.JSONDecodeError as exc:
            raise FetchError(f"Invalid JSON provider payload: {exc}") from exc
        selected = _nested_get(parsed, record_path) if record_path else None
        if record_path and selected is None:
            raise FetchError("Configured JSON record_path is missing")
        if selected is None and isinstance(parsed, Mapping):
            for candidate in (
                "data.items",
                "data.records",
                "items",
                "records",
                "results",
                "products",
                "programs",
                "transactions",
                "data",
            ):
                value = _nested_get(parsed, candidate)
                if isinstance(value, list):
                    selected = value
                    break
        if selected is None:
            selected = parsed
        values = selected if isinstance(selected, list) else [selected]
        records = [dict(value) for value in values if isinstance(value, Mapping)]
        return records, parsed
    if format_name in {"csv", "tsv"}:
        text = _decode_text(body, encoding or None)
        delimiter = "\t" if format_name == "tsv" else ","
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t;")
            delimiter = dialect.delimiter
        except csv.Error:
            pass
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        return [dict(row) for row in reader], None
    if format_name == "xml":
        if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
            raise FetchError(
                "XML provider payload contains a forbidden DTD/entity declaration"
            )
        try:
            root = ElementTree.fromstring(
                body, parser=ElementTree.XMLParser(target=_NoDTDTreeBuilder())
            )
        except ElementTree.ParseError as exc:
            raise FetchError(f"Invalid XML provider payload: {exc}") from exc
        tag = record_tag.strip()
        if tag:
            elements = [
                element
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1] == tag
            ]
        else:
            common = {"item", "product", "program", "record", "row", "transaction"}
            elements = [
                element
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].casefold() in common
            ]
            if not elements:
                elements = list(root)
        return [_flatten_xml_element(element) for element in elements], root
    raise FetchError(f"Unsupported provider payload format: {format_name}")


def _content_type(headers: Message) -> str:
    return headers.get_content_type() if headers else "application/octet-stream"


def _merge_config(
    provider: Mapping[str, Any], resource: Mapping[str, Any]
) -> dict[str, Any]:
    merged = dict(provider)
    merged.pop("resources", None)
    for key, value in resource.items():
        if key in {"auth", "query", "headers", "pagination"} and isinstance(
            value, Mapping
        ):
            base = merged.get(key, {})
            combined = dict(base) if isinstance(base, Mapping) else {}
            combined.update(value)
            merged[key] = combined
        else:
            merged[key] = value
    return merged


def _authentication(
    client: AffiliateHttpClient,
    config: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    raw_auth = config.get("auth", {})
    if not isinstance(raw_auth, Mapping):
        raise ConfigError("auth must be an object")
    auth = resolve_indirections(raw_auth)
    auth_type = str(auth.get("type", "none"))
    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    if auth_type == "none":
        pass
    elif auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif auth_type == "api_key_header":
        headers[str(auth.get("header", "X-API-Key"))] = str(auth["api_key"])
    elif auth_type == "api_key_query":
        query[str(auth.get("parameter", "api_key"))] = str(auth["api_key"])
    elif auth_type == "basic":
        value = base64.b64encode(
            f"{auth['username']}:{auth['password']}".encode("utf-8")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {value}"
    elif auth_type == "oauth2_client_credentials":
        headers["Authorization"] = f"Bearer {client.oauth2_token(auth)}"
    elif auth_type == "custom_headers":
        secret_headers = auth.get("secret_headers")
        if not isinstance(secret_headers, Mapping):
            raise ConfigError("auth.secret_headers must be an object")
        headers.update({str(key): str(value) for key, value in secret_headers.items()})
    else:
        raise ConfigError(f"Unsupported auth.type: {auth_type}")
    return headers, query


def _clean_request_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def fetch_resource(
    root_config: Mapping[str, Any],
    provider_key: str,
    resource_name: str,
) -> FetchBatch:
    validate_config(root_config)
    errors = provider_diagnostics(root_config, provider_key)
    if errors:
        raise ConfigError("Provider configuration is not ready: " + "; ".join(errors))
    providers = root_config["providers"]
    provider = providers[provider_key]
    resource = provider["resources"][resource_name]
    merged = _merge_config(provider, resource)
    if not provider.get("enabled") or not resource.get("enabled"):
        raise ConfigError(f"{provider_key}/{resource_name} is disabled")
    mode = str(merged.get("mode", "api"))
    fetched_at = datetime.now(UTC).isoformat()
    if mode == "file":
        path = Path(str(merged.get("path", ""))).expanduser().resolve()
        if not path.is_file():
            raise FetchError(f"Configured provider file does not exist: {path}")
        maximum_file_bytes = int(
            root_config["storage"].get("max_response_bytes", 50 * 1024 * 1024)
        )
        if path.stat().st_size > maximum_file_bytes:
            raise FetchError(
                f"Configured provider file exceeds max_response_bytes={maximum_file_bytes}"
            )
        with path.open("rb") as handle:
            body = handle.read(maximum_file_bytes + 1)
        if len(body) > maximum_file_bytes:
            raise FetchError("Provider file exceeds max_response_bytes")
        records, _ = parse_records(
            body,
            configured_format=str(merged.get("format", "auto")),
            filename=path.name,
            record_path=str(merged.get("record_path", "")),
            record_tag=str(merged.get("record_tag", "")),
            encoding=str(merged.get("encoding", "")),
            maximum_uncompressed_bytes=int(
                root_config["storage"].get("max_uncompressed_bytes", 200 * 1024 * 1024)
            ),
        )
        return FetchBatch(
            provider=provider_key,
            resource=resource_name,
            fetched_at=fetched_at,
            records=records,
            pages=[
                RawPage(
                    index=1,
                    request_url=f"file://{path.name}",
                    content_type="application/octet-stream",
                    body=body,
                    status=200,
                )
            ],
        )
    endpoint = str(merged.get("endpoint", "")).strip()
    if not endpoint:
        raise ConfigError(f"Missing endpoint for {provider_key}/{resource_name}")
    EndpointValidator.validate_syntax(endpoint)
    client = AffiliateHttpClient(root_config["http"], root_config["storage"])
    auth_headers, auth_query = _authentication(client, merged)
    regular_headers = resolve_indirections(merged.get("headers", {}))
    regular_query = resolve_indirections(merged.get("query", {}))
    if regular_headers and not isinstance(regular_headers, Mapping):
        raise ConfigError("headers must be an object")
    if regular_query and not isinstance(regular_query, Mapping):
        raise ConfigError("query must be an object")
    headers = {str(k): str(v) for k, v in dict(regular_headers or {}).items()}
    headers.update(auth_headers)
    base_query = {str(k): str(v) for k, v in dict(regular_query or {}).items()}
    base_query.update(auth_query)
    account_id = str(merged.get("account_id", "")).strip()
    if account_id and merged.get("account_id_header"):
        headers[str(merged["account_id_header"])] = account_id
    if account_id and merged.get("account_id_query"):
        base_query[str(merged["account_id_query"])] = account_id
    pagination = merged.get("pagination", {})
    if not isinstance(pagination, Mapping):
        raise ConfigError("pagination must be an object")
    pagination_type = str(pagination.get("type", "none"))
    max_pages = max(1, min(int(pagination.get("max_pages", 1)), 10000))
    page_number = int(pagination.get("start", 1))
    offset = int(pagination.get("start", 0))
    cursor = str(pagination.get("initial_cursor", ""))
    next_url = endpoint
    pages: list[RawPage] = []
    all_records: list[dict[str, Any]] = []
    warnings: list[str] = []
    batch_bytes = 0
    for page_index in range(1, max_pages + 1):
        query = dict(base_query)
        current_url = next_url
        if pagination_type == "page":
            query[str(pagination.get("page_param", "page"))] = str(page_number)
            if pagination.get("page_size"):
                query[str(pagination.get("page_size_param", "limit"))] = str(
                    pagination["page_size"]
                )
        elif pagination_type == "offset":
            query[str(pagination.get("offset_param", "offset"))] = str(offset)
            if pagination.get("page_size"):
                query[str(pagination.get("page_size_param", "limit"))] = str(
                    pagination["page_size"]
                )
        elif pagination_type == "cursor" and cursor:
            query[str(pagination.get("cursor_param", "cursor"))] = cursor
        parsed = urllib.parse.urlsplit(current_url)
        existing = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        existing.update(query)
        request_url = urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urllib.parse.urlencode(existing, doseq=True),
                parsed.fragment,
            )
        )
        status, response_headers, body, final_url = client.request(
            request_url,
            method=str(merged.get("method", "GET")),
            headers=headers,
        )
        batch_bytes += len(body)
        if batch_bytes > client.max_uncompressed_bytes:
            raise FetchError("Provider batch exceeds max_uncompressed_bytes")
        content_type = _content_type(response_headers)
        records, parsed_payload = parse_records(
            body,
            configured_format=str(merged.get("format", "auto")),
            content_type=content_type,
            filename=urllib.parse.urlsplit(final_url).path,
            record_path=str(merged.get("record_path", "")),
            record_tag=str(merged.get("record_tag", "")),
            encoding=str(merged.get("encoding", "")),
            maximum_uncompressed_bytes=client.max_uncompressed_bytes,
        )
        pages.append(
            RawPage(
                index=page_index,
                request_url=_clean_request_url(final_url),
                content_type=content_type,
                body=body,
                status=status,
                etag=response_headers.get("ETag"),
                last_modified=response_headers.get("Last-Modified"),
            )
        )
        all_records.extend(records)
        if pagination_type == "none":
            break
        if not records and pagination_type in {"page", "offset"}:
            break
        if pagination_type == "page":
            page_number += 1
            if pagination.get("page_size") and len(records) < int(
                pagination["page_size"]
            ):
                break
        elif pagination_type == "offset":
            page_size = int(pagination.get("page_size", len(records) or 1))
            offset += page_size
            if len(records) < page_size:
                break
        elif pagination_type == "next_url":
            path = str(pagination.get("next_url_path", "next"))
            value = _nested_get(parsed_payload, path)
            if not value:
                break
            next_url = urllib.parse.urljoin(final_url, str(value))
            _require_same_origin(endpoint, next_url)
            client.validator.validate(next_url)
        elif pagination_type == "cursor":
            path = str(pagination.get("next_cursor_path", "next_cursor"))
            value = _nested_get(parsed_payload, path)
            if value in (None, "") or str(value) == cursor:
                break
            cursor = str(value)
        else:
            warnings.append(
                f"Unknown pagination type {pagination_type}; fetched one page"
            )
            break
    else:
        warnings.append(f"Stopped at configured max_pages={max_pages}")
    return FetchBatch(
        provider=provider_key,
        resource=resource_name,
        fetched_at=fetched_at,
        records=all_records,
        pages=pages,
        warnings=warnings,
    )
