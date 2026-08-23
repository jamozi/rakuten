"""Fail-closed secret and application escape-hatch boundaries for ST-0308."""

from __future__ import annotations

from dataclasses import replace

import pytest

from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.adapters.persistence.sqlalchemy import identity as sqlalchemy_identity
from raos.domain.catalog.enums import ProviderEndpointStatus
from raos.domain.catalog.values import ProviderEndpointNonSecretConfigJson
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import UriReference
from tests.st0308_persistence.test_w2a_state_cas_and_ownership import _provider


@pytest.mark.parametrize(
    "payload",
    (
        {"api_key": "redacted"},
        {"nested": {"accessToken": "redacted"}},
        {"affiliate_id": "redacted"},
        {"header": "Bearer credential"},
        {"mapping": "a" * 40},
        {"callback": "https://user:pass@example.test/path"},
        {"callback": "https://example.test/path?client_secret=redacted"},
        {"value": "abc123"},
        {"auth": "short-secret"},
        {"field_mapping": {"title": "abc123"}},
        {"field_mapping": {"auth": "itemName"}},
    ),
)
def test_provider_non_secret_config_rejects_secret_material(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="INVALID_PROVIDER_NON_SECRET_CONFIG"):
        ProviderEndpointNonSecretConfigJson(FrozenJsonObject.from_mapping(payload))


def test_provider_non_secret_config_accepts_bounded_operational_fields() -> None:
    value = ProviderEndpointNonSecretConfigJson(
        FrozenJsonObject.from_mapping(
            {
                "timeout_seconds": 10,
                "page_size": 30,
                "field_mapping": {"title": "itemName"},
                "live_enabled": False,
            }
        )
    )
    assert tuple(value.value) == (
        "field_mapping",
        "live_enabled",
        "page_size",
        "timeout_seconds",
    )


@pytest.mark.parametrize(
    "payload",
    (
        {"timeout_seconds": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": 601},
        {"page_size": False},
        {"page_size": 0},
        {"page_size": 101},
        {"field_mapping": []},
        {"live_enabled": 0},
        {"live_enabled": True},
    ),
)
def test_provider_non_secret_config_rejects_values_outside_closed_contract(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="INVALID_PROVIDER_NON_SECRET_CONFIG"):
        ProviderEndpointNonSecretConfigJson(FrozenJsonObject.from_mapping(payload))


def test_provider_non_secret_config_accepts_empty_disabled_default() -> None:
    value = ProviderEndpointNonSecretConfigJson(FrozenJsonObject())
    assert not value.value


@pytest.mark.parametrize(
    "base_host",
    (
        "https://app.rakuten.co.jp",
        "user:pass@app.rakuten.co.jp",
        "app.rakuten.co.jp?api_key=redacted",
        "APP.RAKUTEN.CO.JP",
        "app..rakuten.co.jp",
    ),
)
def test_provider_endpoint_rejects_non_host_or_credential_bearing_host(
    base_host: str,
) -> None:
    state = _provider(ProviderEndpointStatus.DRAFT).state
    with pytest.raises(ValueError, match="INVALID_CATALOG_PERSISTENCE_VALUE"):
        replace(state, base_host=base_host)


@pytest.mark.parametrize(
    "documentation_url",
    (
        "http://example.test/docs",
        "https://user:pass@example.test/docs",
        "https://example.test/docs?access_token=redacted",
        "https://example.test/docs#private",
    ),
)
def test_provider_endpoint_rejects_non_public_documentation_uri(
    documentation_url: str,
) -> None:
    state = _provider(ProviderEndpointStatus.DRAFT).state
    with pytest.raises(ValueError, match="INVALID_CATALOG_PERSISTENCE_VALUE"):
        replace(state, documentation_url=UriReference(documentation_url))


def test_engine_provider_has_no_public_raw_connection_or_session_method() -> None:
    assert {
        name for name in dir(SqlAlchemyEngineProvider) if not name.startswith("_")
    } == {"expected_profile"}
    assert "VerifiedDatabaseIdentity" not in sqlalchemy_identity.__all__
