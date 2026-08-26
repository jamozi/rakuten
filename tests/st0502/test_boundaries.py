"""Static trust-boundary checks for the ST-0502 recorded-only slice."""

from __future__ import annotations

import ast
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
import inspect
import pickle

import pytest

from raos.adapters.recorded_rakuten_item_search import (
    RecordedRakutenItemSearchAdapter,
)
from raos.application.catalog.rakuten_item_search import RakutenItemSearchService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import RawItemSearchResponse
from raos.ports.rakuten_item_search import (
    RakutenItemSearchProvider,
    RawResponseRecorder,
)

from .support import (
    REPOSITORY_ROOT,
    item_search_command,
    item_search_request,
    recorded_adapter,
)


OWNED_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/catalog/rakuten_item_search.py",
    REPOSITORY_ROOT / "python/raos/ports/rakuten_item_search.py",
    REPOSITORY_ROOT / "python/raos/application/catalog/rakuten_item_search.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_rakuten_item_search.py",
)


def _trees() -> tuple[ast.Module, ...]:
    return tuple(ast.parse(path.read_text(encoding="utf-8")) for path in OWNED_SOURCES)


def test_sources_import_no_network_storage_provider_or_environment_surface() -> None:
    forbidden = {
        "boto3",
        "botocore",
        "http",
        "httpx",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
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


def test_ports_expose_only_closed_recorded_capabilities() -> None:
    provider_methods = {
        name
        for name, value in RakutenItemSearchProvider.__dict__.items()
        if inspect.isfunction(value)
    } - {"__init__"}
    recorder_methods = {
        name
        for name, value in RawResponseRecorder.__dict__.items()
        if inspect.isfunction(value)
    } - {"__init__"}
    assert provider_methods == {
        "capabilities",
        "health",
        "execute",
        "normalize",
        "classify",
        "rate",
    }
    assert recorder_methods == {"record"}
    assert provider_methods.isdisjoint(
        {"read", "list", "delete", "save", "commit", "repository", "storage"}
    )


def test_application_calls_execute_once_and_never_health_retry_or_sleep() -> None:
    tree = ast.parse(OWNED_SOURCES[2].read_text(encoding="utf-8"))
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.count("execute") == 1
    assert calls.count("record") == 1
    assert calls.count("normalize") == 1
    assert calls.count("rate") == 1
    assert "health" not in calls
    assert "sleep" not in calls


def test_sources_generate_no_clock_random_uuid_or_external_action() -> None:
    forbidden_calls = {
        "delete",
        "getenv",
        "open",
        "publish",
        "request",
        "sleep",
        "time",
        "time_ns",
        "unlink",
        "upload",
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
    assert calls.isdisjoint(forbidden_calls)


def test_raw_response_has_no_public_body_or_serialization_surface() -> None:
    public = {name for name in dir(RawItemSearchResponse) if not name.startswith("_")}
    assert "body" not in public
    assert "read" not in public
    assert "export" not in public


def test_domain_values_are_immutable_non_pickleable_and_have_no_defaults() -> None:
    request = item_search_request()
    with pytest.raises(FrozenInstanceError):
        setattr(request, "hits", 2)
    for value in (request, item_search_command()):
        with pytest.raises(TypeError):
            pickle.dumps(value)
    module = inspect.getmodule(type(request))
    assert module is not None
    for value in vars(module).values():
        if inspect.isclass(value) and is_dataclass(value):
            assert all(
                field.default is MISSING and field.default_factory is MISSING
                for field in fields(value)
            )


def test_recorded_adapter_has_no_history_or_mutable_business_map() -> None:
    adapter = recorded_adapter()
    assert type(adapter) is RecordedRakutenItemSearchAdapter
    assert not hasattr(adapter, "history")
    assert not hasattr(adapter, "items")
    assert not hasattr(adapter, "repository")
    assert RecordedRakutenItemSearchAdapter.__slots__ == ("_fixtures",)


def test_production_environment_is_rejected() -> None:
    adapter = recorded_adapter()
    with pytest.raises(Exception):
        RakutenItemSearchService(
            environment=RuntimeEnvironment.PRODUCTION,
            provider=adapter,
            recorder=adapter,
        )
