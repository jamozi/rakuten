"""Representative positive, missing, stale, and invalid-edge repository paths."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.mappers.portfolio import (
    map_portfolio_site_from_row,
    map_portfolio_site_to_row,
)
from raos.adapters.persistence.sqlalchemy.repositories import (
    catalog as catalog_adapters,
)
from raos.adapters.persistence.sqlalchemy.repositories import (
    portfolio as portfolio_adapters,
)
from raos.domain.catalog.aggregates import ProviderEndpoint, ProviderEndpointState
from raos.domain.catalog.enums import ProviderEndpointStatus
from raos.domain.catalog.ids import ProviderEndpointId
from raos.domain.catalog.values import ProviderEndpointNonSecretConfigJson
from raos.domain.portfolio.aggregates import Site, SiteState
from raos.domain.portfolio.enums import SiteStatus
from raos.domain.portfolio.ids import SiteId
from raos.domain.portfolio.values import SitePublicSettingsJson
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


FIXED_TIME = datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        scalar: object = None,
    ) -> None:
        self._row = row
        self._scalar = scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row

    def scalar_one_or_none(self) -> object:
        return self._scalar


class _ScriptedSession(Session):
    def __init__(self, *results: _Result) -> None:
        super().__init__()
        self._results = list(results)
        self.statements: list[object] = []

    def execute(self, statement: object, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        self.statements.append(statement)
        if not self._results:
            raise AssertionError("unexpected SQL execution")
        return self._results.pop(0)


def _site(*, version: int = 0, name: str = "暮らしのしるべ") -> Site:
    return Site(
        SiteState(
            id=SiteId(UUID("018f0000-0000-7000-8000-000000000001")),
            display_id="SITE-001",
            site_code="kurashi-shirube",
            name=name,
            primary_domain="example.test",
            brand_name="暮らしのしるべ",
            locale="ja-JP",
            timezone="Asia/Tokyo",
            currency="JPY",
            status=SiteStatus.ACTIVE,
            public_settings=SitePublicSettingsJson(
                FrozenJsonObject.from_mapping({"affiliate_disclosure": True})
            ),
            created_at=AwareUtcDateTime(FIXED_TIME),
            updated_at=AwareUtcDateTime(FIXED_TIME),
            lock_version=AggregateVersion(version),
        )
    )


def _site_row(site: Site) -> dict[str, object]:
    values = map_portfolio_site_to_row(site.state)
    columns = (
        "id",
        "display_id",
        "site_code",
        "name",
        "primary_domain",
        "brand_name",
        "locale",
        "timezone",
        "currency",
        "status",
        "public_settings",
        "created_at",
        "updated_at",
        "lock_version",
    )
    encoded: list[object] = []
    for value in values:
        if isinstance(value, SiteId):
            encoded.append(value.value)
        elif isinstance(value, SiteStatus):
            encoded.append(value.value)
        elif isinstance(value, SitePublicSettingsJson):
            encoded.append({"affiliate_disclosure": True})
        elif isinstance(value, AwareUtcDateTime):
            encoded.append(value.value)
        elif isinstance(value, AggregateVersion):
            encoded.append(value.value)
        else:
            encoded.append(value)
    return dict(zip(columns, encoded, strict=True))


def _provider(status: ProviderEndpointStatus) -> ProviderEndpoint:
    return ProviderEndpoint(
        ProviderEndpointState(
            id=ProviderEndpointId(UUID("018f0000-0000-7000-8000-000000000002")),
            provider_code="RAKUTEN",
            provider_name="Rakuten",
            api_name="IchibaItemSearch",
            api_version="2022-06-01",
            base_host="app.rakuten.co.jp",
            status=status,
            contract_sha256=Sha256Digest("0" * 64),
            documentation_url=None,
            non_secret_config=ProviderEndpointNonSecretConfigJson(
                FrozenJsonObject.from_mapping({"live_enabled": False})
            ),
            effective_from=AwareUtcDateTime(FIXED_TIME),
            effective_to=None,
            created_at=AwareUtcDateTime(FIXED_TIME),
        )
    )


def test_site_mapper_and_repository_positive_get_add_and_cas_save() -> None:
    site = _site()
    row = _site_row(site)
    decoded = map_portfolio_site_from_row(
        id=site.state.id,
        display_id=site.state.display_id,
        site_code=site.state.site_code,
        name=site.state.name,
        primary_domain=site.state.primary_domain,
        brand_name=site.state.brand_name,
        locale=site.state.locale,
        timezone=site.state.timezone,
        currency=site.state.currency,
        status=site.state.status,
        public_settings=site.state.public_settings,
        created_at=site.state.created_at,
        updated_at=site.state.updated_at,
        lock_version=site.state.lock_version,
    )
    assert decoded == site.state

    read_session = _ScriptedSession(_Result(row=row))
    assert (
        portfolio_adapters.SqlAlchemySiteRepository(read_session).get(site.state.id)
        == site
    )

    add_session = _ScriptedSession(_Result())
    assert portfolio_adapters.SqlAlchemySiteRepository(add_session).add(site) == (
        AggregateVersion(0)
    )
    assert len(add_session.statements) == 1

    save_session = _ScriptedSession(_Result(scalar=1))
    assert portfolio_adapters.SqlAlchemySiteRepository(save_session).save(
        site, AggregateVersion(0)
    ) == AggregateVersion(1)
    assert len(save_session.statements) == 1


@pytest.mark.parametrize(
    ("observed", "expected_code"),
    (
        (None, PersistenceErrorCode.NOT_FOUND),
        ({"lock_version": 2}, PersistenceErrorCode.CONCURRENCY_CONFLICT),
    ),
)
def test_site_cas_distinguishes_missing_from_stale(
    observed: dict[str, object] | None,
    expected_code: PersistenceErrorCode,
) -> None:
    session = _ScriptedSession(_Result(scalar=None), _Result(row=observed))
    repository = portfolio_adapters.SqlAlchemySiteRepository(session)
    with pytest.raises(PersistenceError) as captured:
        repository.save(_site(), AggregateVersion(0))
    assert captured.value.code is expected_code
    assert captured.value.__cause__ is None


def test_provider_transition_rejects_invalid_edge_before_io() -> None:
    session = _ScriptedSession()
    repository = catalog_adapters.SqlAlchemyProviderEndpointRepository(session)
    current = _provider(ProviderEndpointStatus.DRAFT)
    invalid = ProviderEndpoint(
        replace(current.state, status=ProviderEndpointStatus.DRAFT)
    )
    with pytest.raises(ValueError, match="INVALID_PROVIDER_ENDPOINT_TRANSITION"):
        repository.transition(current.state.id, invalid, ProviderEndpointStatus.DRAFT)
    assert session.statements == []


def test_domain_rejects_untyped_json_and_mapper_rejects_wrong_scalar() -> None:
    with pytest.raises(ValueError, match="INVALID_PORTFOLIO_JSON_VALUE"):
        SitePublicSettingsJson({})  # type: ignore[arg-type]
    with pytest.raises(PersistenceError) as captured:
        portfolio_adapters._decode_portfolio_site(
            {**_site_row(_site()), "lock_version": True}
        )
    assert captured.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
