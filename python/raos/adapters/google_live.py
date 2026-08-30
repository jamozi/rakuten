"""Live, read-only Google provider adapters and owner-private composition inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timezone
import importlib
import json
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any, cast, final
from urllib.parse import quote, urlsplit

from raos.domain.analytics.google_live import (
    AnalyticsSiteBinding,
    GA4_EVENT_PARAMETER_NAMES,
    GA4_READONLY_SCOPE,
    GSC_READONLY_SCOPE,
    GSC_URL_INSPECTION_LANGUAGE_CODE,
    Ga4ImportBatch,
    Ga4LiveQuery,
    Ga4Observation,
    Ga4PropertyConfigSnapshot,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    SearchConsoleImportBatch,
    SearchConsoleLiveQuery,
    SearchConsoleObservation,
    SearchConsoleUrlInspectionBatch,
    SearchConsoleUrlInspectionObservation,
    SearchConsoleUrlInspectionQuery,
    canonical_json_bytes,
    fail_google,
    gsc_url_inspection_request_sha256,
    is_google_utc_timestamp,
    normalize_url_inspection_state,
    sha256_hex,
)
from raos.ports.google_live import (
    GoogleAuthorizedJsonTransport,
    GoogleImportClock,
    GoogleJsonResponse,
    GoogleRetrySleeper,
)


_GOOGLE_ORIGINS = frozenset(
    {
        "https://www.googleapis.com",
        "https://searchconsole.googleapis.com",
        "https://analyticsdata.googleapis.com",
        "https://analyticsadmin.googleapis.com",
    }
)
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_PAGES = 200
_RETRY_ATTEMPTS = 4


def _is_runtime_instance(value: object, expected: type[object]) -> bool:
    """Retain fail-closed checks for values arriving from untyped composition."""

    return isinstance(value, expected)


@final
class SystemGoogleImportClock:
    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@final
class SystemGoogleRetrySleeper:
    __slots__ = ()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _safe_file(path: Path, *, expected_mode: int) -> os.stat_result:
    try:
        observed = path.lstat()
    except OSError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    if (
        not stat.S_ISREG(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != expected_mode
        or observed.st_uid != os.geteuid()
        or path.is_symlink()
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return observed


def _safe_directory(path: Path) -> None:
    try:
        observed = path.lstat()
    except OSError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o700
        or observed.st_uid != os.geteuid()
        or path.is_symlink()
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _read_binding(path: Path) -> dict[str, object]:
    before = _safe_file(path, expected_mode=0o600)
    if not 1 <= before.st_size <= 16 * 1024:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        raw = os.read(descriptor, 16 * 1024 + 1)
    except GoogleProviderFailure:
        raise
    except OSError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        value: object = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    if type(value) is not dict:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return cast(dict[str, object], value)


@final
class FixedOwnerPrivateAnalyticsSiteBindings:
    """Load two separate service-account bindings from a fixed 0700/0600 tree.

    Layout::

        <root>/google/gsc/{binding.v1.json,service-account.json}
        <root>/google/ga4/{binding.v1.json,service-account.json}
    """

    __slots__ = ("_ga4", "_gsc")

    def __init__(self, owner_private_root: Path) -> None:
        if (
            not _is_runtime_instance(owner_private_root, Path)
            or not owner_private_root.is_absolute()
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        google_root = owner_private_root / "google"
        gsc_root = google_root / "gsc"
        ga4_root = google_root / "ga4"
        for directory in (owner_private_root, google_root, gsc_root, ga4_root):
            _safe_directory(directory)
        self._gsc = self._load_provider(
            provider="GSC",
            provider_root=gsc_root,
            expected_scope=GSC_READONLY_SCOPE,
        )
        self._ga4 = self._load_provider(
            provider="GA4",
            provider_root=ga4_root,
            expected_scope=GA4_READONLY_SCOPE,
        )
        if (
            self._gsc.site_id != self._ga4.site_id
            or self._gsc.service_account_email_sha256
            == self._ga4.service_account_email_sha256
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

    @staticmethod
    def _load_provider(
        *, provider: str, provider_root: Path, expected_scope: str
    ) -> AnalyticsSiteBinding:
        credential_path = provider_root / "service-account.json"
        _safe_file(credential_path, expected_mode=0o600)
        document = _read_binding(provider_root / "binding.v1.json")
        expected_keys = {
            "schema_version",
            "provider",
            "site_id",
            "resource",
            "credential_file",
            "service_account_email_sha256",
            "scopes",
        }
        if set(document) != expected_keys:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        scopes = document["scopes"]
        if (
            document["schema_version"] != 1
            or document["provider"] != provider
            or document["credential_file"] != "service-account.json"
            or type(scopes) is not list
            or scopes != [expected_scope]
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        try:
            from uuid import UUID

            site_id = UUID(cast(str, document["site_id"]))
        except TypeError, ValueError, AttributeError:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        return AnalyticsSiteBinding(
            provider=provider,
            site_id=site_id,
            resource=cast(str, document["resource"]),
            credential_path=str(credential_path),
            service_account_email_sha256=cast(
                str, document["service_account_email_sha256"]
            ),
            scopes=(expected_scope,),
        )

    def gsc(self) -> AnalyticsSiteBinding:
        return self._gsc

    def ga4(self) -> AnalyticsSiteBinding:
        return self._ga4


@final
class GoogleServiceAccountAuthorizedTransport:
    """Authorized HTTPS JSON transport backed by a bound service account."""

    __slots__ = ("_credentials", "_lock", "_request_adapter", "_session", "_timeout")

    def __init__(
        self,
        *,
        binding: AnalyticsSiteBinding,
        timeout_seconds: float = 30.0,
    ) -> None:
        if (
            type(binding) is not AnalyticsSiteBinding
            or type(timeout_seconds) is not float
            or not 1.0 <= timeout_seconds <= 120.0
        ):
            fail_google()
        credential_path = Path(binding.credential_path)
        _safe_file(credential_path, expected_mode=0o600)
        try:
            service_account = importlib.import_module("google.oauth2.service_account")
            google_requests = importlib.import_module("google.auth.transport.requests")
            requests_module = importlib.import_module("requests")
            credentials = service_account.Credentials.from_service_account_file(
                str(credential_path), scopes=list(binding.scopes)
            )
            observed_email = cast(str, credentials.service_account_email)
            if (
                sha256_hex(observed_email.encode("utf-8"))
                != binding.service_account_email_sha256
            ):
                fail_google(GoogleProviderFailureCode.CREDENTIAL_INVALID)
            self._request_adapter = google_requests.Request()
            self._session = requests_module.Session()
            self._credentials = credentials
        except GoogleProviderFailure:
            raise
        except Exception:
            fail_google(GoogleProviderFailureCode.CREDENTIAL_INVALID)
        self._timeout = timeout_seconds
        self._lock = threading.RLock()

    def _access_token(self) -> str:
        try:
            with self._lock:
                if not bool(self._credentials.valid):
                    self._credentials.refresh(self._request_adapter)
                access_value = self._credentials.token
        except Exception:
            fail_google(GoogleProviderFailureCode.AUTHENTICATION_FAILED, retryable=True)
        if type(access_value) is not str or not access_value:
            fail_google(GoogleProviderFailureCode.AUTHENTICATION_FAILED)
        return access_value

    def request(
        self,
        *,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
    ) -> GoogleJsonResponse:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if (
            method not in {"GET", "POST"}
            or origin not in _GOOGLE_ORIGINS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (method == "GET" and body is not None)
            or (method == "POST" and type(body) is not dict)
        ):
            fail_google()
        json_body: dict[str, object] | None = (
            None if body is None else cast(dict[str, object], body).copy()
        )
        try:
            response: Any = self._session.request(
                method,
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self._access_token()}",
                    "Content-Type": "application/json",
                    "User-Agent": "raos-google-live/1",
                },
                json=json_body,
                timeout=self._timeout,
                allow_redirects=False,
            )
            content = cast(bytes, response.content)
        except GoogleProviderFailure:
            raise
        except Exception:
            fail_google(GoogleProviderFailureCode.PROVIDER_UNAVAILABLE, retryable=True)
        if len(content) > _MAX_RESPONSE_BYTES:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        try:
            document: object = json.loads(content.decode("utf-8")) if content else {}
        except UnicodeDecodeError, json.JSONDecodeError:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        safe_headers = tuple(
            (name.lower(), cast(str, response.headers.get(name)))
            for name in ("Retry-After", "Content-Type")
            if response.headers.get(name) is not None
        )
        return GoogleJsonResponse(
            status=cast(int, response.status_code),
            headers=safe_headers,
            document=document,
        )


def _retry_delay(response: GoogleJsonResponse | None, attempt: int) -> float:
    if response is not None:
        for name, value in response.headers:
            if name == "retry-after":
                try:
                    return float(min(max(int(value), 0), 60))
                except ValueError:
                    break
    return float(2**attempt)


def _request_with_retry(
    *,
    transport: GoogleAuthorizedJsonTransport,
    sleeper: GoogleRetrySleeper,
    method: str,
    url: str,
    body: Mapping[str, object] | None,
) -> GoogleJsonResponse:
    last_code = GoogleProviderFailureCode.PROVIDER_UNAVAILABLE
    for attempt in range(_RETRY_ATTEMPTS):
        response: GoogleJsonResponse | None = None
        try:
            response = transport.request(method=method, url=url, body=body)
        except GoogleProviderFailure as error:
            if not error.retryable:
                raise
            last_code = error.code
        except Exception:
            last_code = GoogleProviderFailureCode.PROVIDER_UNAVAILABLE
        else:
            if 200 <= response.status < 300:
                return response
            if response.status == 401:
                fail_google(GoogleProviderFailureCode.AUTHENTICATION_FAILED)
            if response.status == 403:
                fail_google(GoogleProviderFailureCode.AUTHORIZATION_FAILED)
            if response.status == 404:
                fail_google(GoogleProviderFailureCode.RESOURCE_NOT_FOUND)
            if response.status == 429:
                last_code = GoogleProviderFailureCode.RATE_LIMITED
            elif 500 <= response.status <= 599:
                last_code = GoogleProviderFailureCode.PROVIDER_UNAVAILABLE
            else:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if attempt + 1 < _RETRY_ATTEMPTS:
            sleeper.sleep(_retry_delay(response, attempt))
    fail_google(last_code, retryable=True)


def _dict(value: object) -> dict[str, object]:
    if type(value) is not dict:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return cast(list[object], value)


def _number(value: object) -> float:
    if type(value) not in {int, float}:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    observed = float(cast(int | float, value))
    if not observed == observed or observed in {float("inf"), float("-inf")}:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return observed


def _optional_utc_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not is_google_utc_timestamp(value):
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return cast(str, value)


@final
class LiveSearchConsoleProvider:
    __slots__ = ("_clock", "_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        clock: GoogleImportClock,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if (
            not _is_runtime_instance(transport, GoogleAuthorizedJsonTransport)
            or not _is_runtime_instance(clock, GoogleImportClock)
            or not _is_runtime_instance(sleeper, GoogleRetrySleeper)
        ):
            fail_google()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def query(self, query: SearchConsoleLiveQuery) -> SearchConsoleImportBatch:
        if type(query) is not SearchConsoleLiveQuery:
            fail_google()
        endpoint = (
            "https://www.googleapis.com/webmasters/v3/sites/"
            f"{quote(query.site_url, safe='')}/searchAnalytics/query"
        )
        rows: list[SearchConsoleObservation] = []
        request_hashes: list[str] = []
        seen_grains: set[str] = set()
        start_row = 0
        for _ in range(_MAX_PAGES):
            body: dict[str, object] = {
                "aggregationType": "auto",
                "dataState": "final",
                "dimensions": list(query.dimensions),
                "endDate": query.date_to.isoformat(),
                "rowLimit": query.row_limit,
                "startDate": query.date_from.isoformat(),
                "startRow": start_row,
                "type": "web",
            }
            page_hash = sha256_hex(
                canonical_json_bytes({"site_url": query.site_url, "body": body})
            )
            request_hashes.append(page_hash)
            response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="POST",
                url=endpoint,
                body=body,
            )
            document = _dict(response.document)
            page_rows = _list(document.get("rows", []))
            for candidate in page_rows:
                item = _dict(candidate)
                keys = _list(item.get("keys"))
                if len(keys) != len(query.dimensions) or not all(
                    type(value) is str for value in keys
                ):
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                key_values = cast(list[str], keys)
                try:
                    metric_date = date.fromisoformat(key_values[0])
                except ValueError:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                clicks_value = item.get("clicks")
                impressions_value = item.get("impressions")
                if type(clicks_value) is not int or type(impressions_value) is not int:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                grain_hash = sha256_hex(
                    canonical_json_bytes(
                        {
                            "country": key_values[3].lower(),
                            "date": metric_date.isoformat(),
                            "device": key_values[4].upper(),
                            "page": key_values[2],
                            "query": key_values[1],
                        }
                    )
                )
                if grain_hash in seen_grains:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                seen_grains.add(grain_hash)
                rows.append(
                    SearchConsoleObservation(
                        metric_date=metric_date,
                        query_text=key_values[1],
                        page_url=key_values[2],
                        country_code=key_values[3].lower(),
                        device=key_values[4].upper(),
                        clicks=clicks_value,
                        impressions=impressions_value,
                        ctr=_number(item.get("ctr")),
                        average_position=_number(item.get("position")),
                        dimension_key_sha256=grain_hash,
                        source_request_sha256=page_hash,
                    )
                )
            if len(rows) > 2_000_000:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            if len(page_rows) < query.row_limit:
                break
            start_row += len(page_rows)
        else:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        return SearchConsoleImportBatch(
            site_id=query.site_id,
            site_url=query.site_url,
            date_from=query.date_from,
            date_to=query.date_to,
            request_sha256=query.request_sha256,
            page_request_sha256s=tuple(request_hashes),
            rows=tuple(rows),
            retrieved_at=self._clock.now(),
            provider_row_count=len(rows),
        )


@final
class LiveSearchConsoleUrlInspectionProvider:
    """Inspect the closed URL set sequentially through the read-only GSC seam."""

    __slots__ = ("_clock", "_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        clock: GoogleImportClock,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if (
            not _is_runtime_instance(transport, GoogleAuthorizedJsonTransport)
            or not _is_runtime_instance(clock, GoogleImportClock)
            or not _is_runtime_instance(sleeper, GoogleRetrySleeper)
        ):
            fail_google()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def inspect(
        self, query: SearchConsoleUrlInspectionQuery
    ) -> SearchConsoleUrlInspectionBatch:
        if type(query) is not SearchConsoleUrlInspectionQuery:
            fail_google()
        endpoint = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
        results: list[SearchConsoleUrlInspectionObservation] = []
        for inspection_url in query.inspection_urls:
            body: dict[str, object] = {
                "inspectionUrl": inspection_url,
                "languageCode": GSC_URL_INSPECTION_LANGUAGE_CODE,
                "siteUrl": query.site_url,
            }
            request_sha256 = gsc_url_inspection_request_sha256(
                site_url=query.site_url,
                inspection_url=inspection_url,
            )
            response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="POST",
                url=endpoint,
                body=body,
            )
            document = _dict(response.document)
            inspection_result = _dict(document.get("inspectionResult"))
            index_status = _dict(inspection_result.get("indexStatusResult"))
            verdict = index_status.get("verdict")
            indexing_state = index_status.get("indexingState")
            if type(verdict) is not str or type(indexing_state) is not str:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            last_crawl_at = _optional_utc_timestamp(index_status.get("lastCrawlTime"))
            normalized_response = {
                "indexingState": indexing_state,
                "lastCrawlTime": last_crawl_at,
                "verdict": verdict,
            }
            results.append(
                SearchConsoleUrlInspectionObservation(
                    inspected_url=inspection_url,
                    state=normalize_url_inspection_state(
                        verdict=verdict, indexing_state=indexing_state
                    ),
                    verdict=verdict,
                    indexing_state=indexing_state,
                    last_crawl_at=last_crawl_at,
                    source_request_sha256=request_sha256,
                    provider_response_sha256=sha256_hex(
                        canonical_json_bytes(normalized_response)
                    ),
                )
            )
        return SearchConsoleUrlInspectionBatch(
            site_id=query.site_id,
            site_url=query.site_url,
            request_sha256=query.request_sha256,
            results=tuple(results),
            retrieved_at=self._clock.now(),
        )


@final
class LiveGa4AdminProvider:
    __slots__ = ("_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if not _is_runtime_instance(
            transport, GoogleAuthorizedJsonTransport
        ) or not _is_runtime_instance(sleeper, GoogleRetrySleeper):
            fail_google()
        self._transport = transport
        self._sleeper = sleeper

    def get_property_configuration(
        self,
        *,
        property_id: str,
        retrieved_at: datetime,
    ) -> Ga4PropertyConfigSnapshot:
        resource = f"properties/{property_id}"
        property_response = _request_with_retry(
            transport=self._transport,
            sleeper=self._sleeper,
            method="GET",
            url=f"https://analyticsadmin.googleapis.com/v1alpha/{resource}",
            body=None,
        )
        identity_response = _request_with_retry(
            transport=self._transport,
            sleeper=self._sleeper,
            method="GET",
            url=(
                "https://analyticsadmin.googleapis.com/v1alpha/"
                f"{resource}/reportingIdentitySettings"
            ),
            body=None,
        )
        property_document = _dict(property_response.document)
        identity_document = _dict(identity_response.document)
        for name in ("name", "displayName", "timeZone", "currencyCode"):
            if type(property_document.get(name)) is not str:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if (
            property_document["name"] != resource
            or identity_document.get("name") != f"{resource}/reportingIdentitySettings"
            or type(identity_document.get("reportingIdentity")) is not str
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        custom_dimension_hashes: list[str] = []
        custom_dimension_scopes: dict[str, str] = {}
        page_token: str | None = None
        for _ in range(_MAX_PAGES):
            custom_dimensions_url = (
                "https://analyticsadmin.googleapis.com/v1alpha/"
                f"{resource}/customDimensions?pageSize=200"
            )
            if page_token is not None:
                custom_dimensions_url += f"&pageToken={quote(page_token, safe='')}"
            custom_dimensions_response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="GET",
                url=custom_dimensions_url,
                body=None,
            )
            custom_dimensions_document = _dict(custom_dimensions_response.document)
            custom_dimension_hashes.append(
                sha256_hex(canonical_json_bytes(custom_dimensions_document))
            )
            for raw_dimension in _list(
                custom_dimensions_document.get("customDimensions", [])
            ):
                dimension = _dict(raw_dimension)
                dimension_resource = dimension.get("name")
                parameter_name = dimension.get("parameterName")
                scope = dimension.get("scope")
                if (
                    type(dimension_resource) is not str
                    or not dimension_resource.startswith(
                        f"{resource}/customDimensions/"
                    )
                    or type(parameter_name) is not str
                    or not parameter_name
                    or type(scope) is not str
                    or parameter_name in custom_dimension_scopes
                ):
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                custom_dimension_scopes[parameter_name] = scope
            next_page_token = custom_dimensions_document.get("nextPageToken")
            if next_page_token is None:
                break
            if type(next_page_token) is not str or not next_page_token:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            page_token = next_page_token
        else:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if any(
            custom_dimension_scopes.get(parameter_name) != "EVENT"
            for parameter_name in GA4_EVENT_PARAMETER_NAMES
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        property_hash = sha256_hex(canonical_json_bytes(property_document))
        identity_hash = sha256_hex(
            canonical_json_bytes(
                {
                    "custom_dimension_page_sha256s": custom_dimension_hashes,
                    "reporting_identity": identity_document,
                }
            )
        )
        snapshot_document = {
            "currency_code": property_document["currencyCode"],
            "display_name": property_document["displayName"],
            "property_resource": resource,
            "required_event_custom_dimensions": list(GA4_EVENT_PARAMETER_NAMES),
            "reporting_identity": identity_document["reportingIdentity"],
            "time_zone": property_document["timeZone"],
        }
        return Ga4PropertyConfigSnapshot(
            property_id=property_id,
            property_resource=resource,
            display_name=cast(str, property_document["displayName"]),
            time_zone=cast(str, property_document["timeZone"]),
            currency_code=cast(str, property_document["currencyCode"]),
            reporting_identity=cast(str, identity_document["reportingIdentity"]),
            retrieved_at=retrieved_at,
            property_response_sha256=property_hash,
            reporting_identity_response_sha256=identity_hash,
            snapshot_sha256=sha256_hex(canonical_json_bytes(snapshot_document)),
        )


@final
class LiveGa4DataProvider:
    __slots__ = ("_clock", "_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        clock: GoogleImportClock,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if (
            not _is_runtime_instance(transport, GoogleAuthorizedJsonTransport)
            or not _is_runtime_instance(clock, GoogleImportClock)
            or not _is_runtime_instance(sleeper, GoogleRetrySleeper)
        ):
            fail_google()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def run_report(
        self,
        query: Ga4LiveQuery,
        *,
        configuration: Ga4PropertyConfigSnapshot,
    ) -> Ga4ImportBatch:
        if (
            type(query) is not Ga4LiveQuery
            or type(configuration) is not Ga4PropertyConfigSnapshot
            or configuration.property_id != query.property_id
        ):
            fail_google()
        endpoint = (
            "https://analyticsdata.googleapis.com/v1beta/"
            f"properties/{query.property_id}:runReport"
        )
        rows: list[Ga4Observation] = []
        request_hashes: list[str] = []
        seen_grains: set[str] = set()
        offset = 0
        expected_row_count: int | None = None
        thresholding = False
        data_loss = False
        for _ in range(_MAX_PAGES):
            body: dict[str, object] = {
                "dateRanges": [
                    {
                        "endDate": query.date_to.isoformat(),
                        "startDate": query.date_from.isoformat(),
                    }
                ],
                "dimensions": [{"name": item} for item in query.dimensions],
                "keepEmptyRows": False,
                "limit": str(query.page_limit),
                "metrics": [{"name": item} for item in query.metrics],
                "offset": str(offset),
                "returnPropertyQuota": True,
            }
            page_hash = sha256_hex(
                canonical_json_bytes(
                    {"property": f"properties/{query.property_id}", "body": body}
                )
            )
            request_hashes.append(page_hash)
            response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="POST",
                url=endpoint,
                body=body,
            )
            document = _dict(response.document)
            dimension_headers = tuple(
                cast(str, _dict(item).get("name"))
                for item in _list(document.get("dimensionHeaders"))
            )
            metric_headers = tuple(
                cast(str, _dict(item).get("name"))
                for item in _list(document.get("metricHeaders"))
            )
            if dimension_headers != query.dimensions or metric_headers != query.metrics:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            declared_count = document.get("rowCount")
            if type(declared_count) is str and declared_count.isdigit():
                declared_count = int(declared_count)
            if type(declared_count) is not int or declared_count < 0:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            if expected_row_count is None:
                expected_row_count = declared_count
            elif expected_row_count != declared_count:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            metadata = _dict(document.get("metadata", {}))
            thresholding = (
                thresholding or metadata.get("subjectToThresholding", False) is True
            )
            data_loss = data_loss or metadata.get("dataLossFromOtherRow", False) is True
            page_rows = _list(document.get("rows", []))
            for candidate in page_rows:
                item = _dict(candidate)
                dimension_values = tuple(
                    cast(str, _dict(value).get("value"))
                    for value in _list(item.get("dimensionValues"))
                )
                metric_values = tuple(
                    cast(str, _dict(value).get("value"))
                    for value in _list(item.get("metricValues"))
                )
                if (
                    len(dimension_values) != len(query.dimensions)
                    or len(metric_values) != len(query.metrics)
                    or not all(type(value) is str for value in dimension_values)
                    or not all(type(value) is str for value in metric_values)
                ):
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                try:
                    metric_date = datetime.strptime(
                        dimension_values[0], "%Y%m%d"
                    ).date()
                except ValueError:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                dimensions = tuple(zip(query.dimensions, dimension_values, strict=True))
                metrics = tuple(zip(query.metrics, metric_values, strict=True))
                grain_hash = sha256_hex(
                    canonical_json_bytes(
                        {
                            "date": metric_date.isoformat(),
                            "dimensions": dict(dimensions),
                        }
                    )
                )
                if grain_hash in seen_grains:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                seen_grains.add(grain_hash)
                rows.append(
                    Ga4Observation(
                        metric_date=metric_date,
                        dimensions=dimensions,
                        metrics=metrics,
                        grain_key_sha256=grain_hash,
                        source_request_sha256=page_hash,
                        is_thresholded=thresholding,
                    )
                )
            offset += len(page_rows)
            if offset >= expected_row_count:
                break
            if not page_rows:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        else:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if len(rows) != expected_row_count:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if thresholding:
            rows = [replace(row, is_thresholded=True) for row in rows]
        return Ga4ImportBatch(
            site_id=query.site_id,
            property_id=query.property_id,
            date_from=query.date_from,
            date_to=query.date_to,
            dimensions=query.dimensions,
            metrics=query.metrics,
            request_sha256=query.request_sha256,
            page_request_sha256s=tuple(request_hashes),
            rows=tuple(rows),
            configuration=configuration,
            retrieved_at=self._clock.now(),
            provider_row_count=len(rows),
            subject_to_thresholding=thresholding,
            data_loss_from_other_row=data_loss,
        )


__all__ = [
    "FixedOwnerPrivateAnalyticsSiteBindings",
    "GoogleServiceAccountAuthorizedTransport",
    "LiveGa4AdminProvider",
    "LiveGa4DataProvider",
    "LiveSearchConsoleProvider",
    "LiveSearchConsoleUrlInspectionProvider",
    "SystemGoogleImportClock",
    "SystemGoogleRetrySleeper",
]
