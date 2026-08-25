"""Static credential, network, activation, and ownership boundaries for ST-0502 V2."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import pickle

import pytest

from raos.adapters.recorded_rakuten_item_search_runtime_v2 import (
    DisabledRakutenItemSearchHttpActivationPortV2,
)
from raos.adapters.sqlite_rakuten_item_search_runtime_v2 import (
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
)
from raos.application.catalog.rakuten_item_search_runtime_v2 import (
    RakutenItemSearchRuntimeServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    FORBIDDEN_RECOMMENDATION_INPUTS_V2,
    ITEM_SEARCH_SECRET_NAME_BINDINGS_V2,
    OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256,
    OFFICIAL_ITEM_SEARCH_DOCUMENTATION_URL,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchWireRequestV2,
    ProviderModeV2,
)
from raos.ports.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionUnitOfWorkStoreV2,
    ItemSearchPageProviderV2,
)

from runtime_v2_fixtures import runtime_plan_v2, runtime_provider_v2, runtime_store_v2


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OWNED_RUNTIME_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/catalog/rakuten_item_search_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/ports/rakuten_item_search_runtime_v2.py",
    REPOSITORY_ROOT
    / "python/raos/application/catalog/rakuten_item_search_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_rakuten_item_search_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/sqlite_rakuten_item_search_runtime_v2.py",
)


def _trees() -> tuple[ast.Module, ...]:
    return tuple(
        ast.parse(path.read_text(encoding="utf-8")) for path in OWNED_RUNTIME_SOURCES
    )


def test_only_pure_url_encoding_and_sqlite_are_imported_not_network_clients() -> None:
    forbidden_roots = {
        "aiohttp",
        "boto3",
        "botocore",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib3",
    }
    imported: set[str] = set()
    imported_modules: set[str] = set()
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.partition(".")[0] for alias in node.names)
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.partition(".")[0])
                imported_modules.add(node.module)
    assert imported.isdisjoint(forbidden_roots)
    assert "urllib.request" not in imported_modules
    assert "http.client" not in imported_modules
    assert "sqlite3" in imported
    assert "urllib.parse" in imported_modules


def test_application_has_one_fetch_site_and_no_loop_sleep_worker_or_clock() -> None:
    tree = ast.parse(OWNED_RUNTIME_SOURCES[2].read_text(encoding="utf-8"))
    calls = [
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    ]
    assert calls.count("fetch_once") == 1
    assert "sleep" not in calls
    assert "create_task" not in calls
    assert "Thread" not in calls
    assert "Process" not in calls
    assert "now" not in calls
    assert "utcnow" not in calls
    assert not any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree))


def test_runtime_never_reads_ambient_credentials_or_builds_an_http_action() -> None:
    forbidden_calls = {
        "getenv",
        "get_environ",
        "request",
        "send",
        "urlopen",
    }
    forbidden_attributes = {"environ", "headers", "cookies", "authorization"}
    calls: set[str] = set()
    attributes: set[str] = set()
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
            elif isinstance(node, ast.Attribute):
                attributes.add(node.attr.lower())
    assert calls.isdisjoint(forbidden_calls)
    assert attributes.isdisjoint(forbidden_attributes)


def test_disabled_activation_constructor_accepts_no_client_or_secret_reader() -> None:
    signature = inspect.signature(DisabledRakutenItemSearchHttpActivationPortV2)
    assert tuple(signature.parameters) == ("environment",)
    assert DisabledRakutenItemSearchHttpActivationPortV2.__slots__ == ()
    adapter = DisabledRakutenItemSearchHttpActivationPortV2(
        environment=RuntimeEnvironment.CI
    )
    request = ItemSearchWireRequestV2.from_plan(runtime_plan_v2(), page=1)
    from runtime_v2_fixtures import OBSERVED_AT_V2

    observation = adapter.fetch_once(request, observed_at=OBSERVED_AT_V2)
    assert adapter.mode is observation.mode is ProviderModeV2.DISABLED
    assert adapter.external_action_count == observation.external_actions == 0


def test_secret_boundary_contains_names_and_transport_only() -> None:
    assert tuple(
        binding.secret_name for binding in ITEM_SEARCH_SECRET_NAME_BINDINGS_V2
    ) == (
        "rakuten_web_service_access_key",
        "rakuten_affiliate_id",
        "rakuten_web_service_application_id",
    )
    serialized = " ".join(
        path.read_text(encoding="utf-8") for path in OWNED_RUNTIME_SOURCES
    )
    assert "REPLACE_WITH" not in serialized
    assert "application_secret" not in serialized
    assert "Bearer " not in serialized
    assert "Basic " not in serialized
    assert "X-Access-Key:" not in serialized


def test_provider_text_and_failures_are_redacted_non_pickleable_values() -> None:
    request = ItemSearchWireRequestV2.from_plan(runtime_plan_v2(), page=1)
    assert "省スペース" not in repr(request)
    with pytest.raises(FrozenInstanceError):
        setattr(request, "page", 2)
    with pytest.raises(TypeError):
        pickle.dumps(request)
    failure = ItemSearchRuntimeFailure(ItemSearchRuntimeFailureCode.INVALID_ARGUMENT)
    with pytest.raises(TypeError):
        pickle.dumps(failure)


def test_closed_ports_have_no_network_delete_publish_or_general_repository_surface() -> (
    None
):
    provider_methods = {
        name
        for name, value in ItemSearchPageProviderV2.__dict__.items()
        if inspect.isfunction(value) or isinstance(value, property)
    } - {"__init__"}
    store_methods = {
        name
        for name, value in ItemSearchIngestionUnitOfWorkStoreV2.__dict__.items()
        if inspect.isfunction(value)
    } - {"__init__"}
    assert provider_methods == {"mode", "external_action_count", "fetch_once"}
    assert store_methods == {
        "create_session",
        "load_session",
        "lookup_step",
        "recover_commit",
        "commit_success",
        "commit_failure",
        "read_raw",
        "read_page",
    }
    assert (provider_methods | store_methods).isdisjoint(
        {"delete", "list", "publish", "upload", "http", "execute"}
    )


def test_runtime_contains_no_delete_statement_or_ranking_metric_input() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in OWNED_RUNTIME_SOURCES
    )
    assert "DELETE FROM" not in source.upper()
    assert "recommendation_inputs" in source
    for forbidden in FORBIDDEN_RECOMMENDATION_INPUTS_V2:
        assert source.count(f'"{forbidden}"') == 1


def test_official_source_binding_is_only_url_version_facts_and_raw_hash() -> None:
    assert OFFICIAL_ITEM_SEARCH_DOCUMENTATION_URL == (
        "https://webservice.rakuten.co.jp/index.php/documentation/ichiba-item-search"
    )
    assert OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256 == (
        "063d5a861f2f8677efca7e772256a980a45eb931bcba403f287025847e42e4cb"
    )
    assert len(OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256) == 64


def test_production_is_rejected_for_service_and_durable_store(tmp_path: Path) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    from runtime_v2_fixtures import (
        OBSERVED_AT_V2,
        runtime_exchange_v2,
        runtime_success_observation_v2,
    )

    provider = runtime_provider_v2(
        runtime_exchange_v2(
            request,
            runtime_success_observation_v2(request, observed_at=OBSERVED_AT_V2),
        )
    )
    store = runtime_store_v2(tmp_path / "private")
    with pytest.raises(ItemSearchRuntimeFailure):
        RakutenItemSearchRuntimeServiceV2(
            environment=RuntimeEnvironment.PRODUCTION,
            provider=provider,
            store=store,
        )
    with pytest.raises(ItemSearchRuntimeFailure):
        OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2(
            environment=RuntimeEnvironment.PRODUCTION,
            root=tmp_path / "production-private",
        )
