"""Static architecture, predecessor, and non-activation boundaries for ST-1201."""

from __future__ import annotations

import ast
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
import hashlib
import inspect

import pytest

from raos.adapters.recorded_event_store import RecordedEventCollectionExchange
from raos.domain.analytics import event_collector as domain
from raos.ports.event_collector import EventCollectionExchange

from conftest import REPOSITORY_ROOT, envelope, recorded_exchange


OWNED_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/analytics/event_collector.py",
    REPOSITORY_ROOT / "python/raos/ports/event_collector.py",
    REPOSITORY_ROOT / "python/raos/application/analytics/event_collector.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_event_store.py",
)

PINNED_PREDECESSORS = {
    "changes/st-0305/README.md": "b45c333996c723ab1978c8b474420de86c563277a3c4a0d2e2a7d76cdbaed4bb",
    "changes/st-0305/contracts/publication-analytics-finance.v1.yaml": "2947fe100633a2611b9287c6530856b9679365bb10d4af4728a5148ed970377f",
    "changes/st-0305/generated/publication-analytics-finance-catalog.v1.json": "0757434a72b22ae54dadd13edbd3d7995eaf0776a18ba69be5064f2db8e75e61",
    "changes/st-0305/manifest.yaml": "5f8b663b5ebc72960dadf662c1cc251d5e36ff7849ddfbfb67bbc9a113d45353",
    "scripts/build_st0305_publication_analytics_finance.py": "6275ad1f451b16ff7a51fbaf7337917c262c668dca70257949c15ba015bb1435",
    "changes/st-0404/README.md": "e86677ccceaa0991ffa641ffe22de22815a32f9e837bb4c924bf76d6958d680d",
    "python/raos/domain/http/security.py": "954bf52f719e95402847f82cfab1e616cf8b3988ab6467e577b3225f611ed532",
    "python/raos/application/http/security.py": "9d7e6538dd3f126abd0a1ced9f7fd91f5ff799b2d26b60e6740af7dcf0fbfaba",
    "docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml": "b33049dc60814109b3a68c166c473f474789dd401a72116fe0a700aeeffb05fa",
    "contracts/raos-v0.4/contracts/schemas/imports/affiliate-click-input.schema.json": "fc99e614645a6dcb588c8ce9a3a417cfd90a79427f4c4b8da9181c0ba63df664",
    "python/raos/generated/contracts/affiliate_click_input.py": "2dd636cdcaf2ed968f62d00cd207260673db72e6dadabe828ab43286901549d2",
}


def _trees() -> tuple[ast.Module, ...]:
    return tuple(ast.parse(path.read_text(encoding="utf-8")) for path in OWNED_SOURCES)


def test_predecessor_and_conflicting_contract_bytes_are_exact() -> None:
    for relative, expected in PINNED_PREDECESSORS.items():
        observed = hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
        assert observed == expected


def test_sources_import_no_framework_browser_storage_database_or_network() -> None:
    forbidden = {
        "boto3",
        "botocore",
        "fastapi",
        "http",
        "httpx",
        "os",
        "pathlib",
        "playwright",
        "psycopg",
        "requests",
        "selenium",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    imported: set[str] = set()
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.partition(".")[0])
    assert imported.isdisjoint(forbidden)


def test_port_exposes_only_one_exchange_method() -> None:
    methods = {
        name
        for name, value in EventCollectionExchange.__dict__.items()
        if inspect.isfunction(value)
    }
    assert methods - {"__init__"} == {"exchange"}


def test_application_guards_once_and_exchanges_once() -> None:
    tree = _trees()[2]
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.count("require") == 1
    assert calls.count("exchange") == 1
    assert set(calls).isdisjoint({"invoke", "retry", "sleep", "track"})


def test_sources_define_no_repository_uow_http_storage_or_external_action() -> None:
    forbidden = {
        "add",
        "commit",
        "connect",
        "delete",
        "fetch",
        "flush",
        "get",
        "list",
        "open",
        "persist",
        "publish",
        "query",
        "release",
        "save",
        "send",
        "transaction",
        "upload",
        "write",
    }
    defined = {
        node.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined.isdisjoint(forbidden)


def test_sources_do_not_map_affiliate_input_or_physical_analytics_rows() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in OWNED_SOURCES)
    assert "AffiliateClickInput" not in source
    assert "anonymous_event" not in source
    assert "analytics.anonymous_event" not in source
    assert "PUB-004" not in source


def test_no_clock_random_uuid_cookie_retention_or_environment_calls() -> None:
    forbidden = {
        "environ",
        "getenv",
        "now",
        "open",
        "request",
        "time",
        "time_ns",
        "unlink",
        "urlopen",
        "uuid1",
        "uuid4",
        "uuid5",
        "uuid6",
        "uuid7",
    }
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint(forbidden)


def test_domain_dataclasses_are_immutable_and_have_no_defaults() -> None:
    value = envelope()
    with pytest.raises(FrozenInstanceError):
        setattr(value, "schema_version", value.schema_version)
    for candidate in vars(domain).values():
        if inspect.isclass(candidate) and is_dataclass(candidate):
            assert all(
                field.default is MISSING and field.default_factory is MISSING
                for field in fields(candidate)
            )


def test_adapter_exposes_no_body_history_query_or_business_map() -> None:
    adapter = recorded_exchange()
    assert type(adapter) is RecordedEventCollectionExchange
    assert RecordedEventCollectionExchange.__slots__ == (
        "_index",
        "_lock",
        "_scripts",
    )
    for name in (
        "body",
        "events",
        "history",
        "items",
        "query",
        "repository",
        "snapshot",
    ):
        assert not hasattr(adapter, name)


def test_status_vocabularies_cannot_claim_tracking_storage_or_validation() -> None:
    assert {value.value for value in domain.EventCollectorMode} == {
        "DISABLED_OD_012",
        "RECORDED_TEST_ONLY",
    }
    assert {value.value for value in domain.TrackingActivation} == {"DISABLED"}
    assert {value.value for value in domain.CollectorDecision} == {"NOT_READY"}
    prohibited = {
        "ENABLED",
        "LIVE",
        "PASS",
        "PERSISTED",
        "PRODUCTION",
        "READY",
        "STAGING",
        "STORED",
        "TRACKING_ENABLED",
        "VALIDATED",
    }
    vocabularies = (
        domain.EventCollectorMode,
        domain.TrackingActivation,
        domain.CollectorDecision,
        domain.RecordedStoreDisposition,
    )
    assert prohibited.isdisjoint(
        member.value for vocabulary in vocabularies for member in vocabulary
    )
