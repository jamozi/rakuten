"""Static architecture and non-execution boundaries for ST-0802."""

from __future__ import annotations

import ast
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
import inspect

import pytest

from raos.adapters.recorded_article_lifecycle import (
    RecordedArticleLifecycleExchange,
)
from raos.domain.editorial import article_lifecycle as domain
from raos.ports.article_lifecycle import ArticleLifecycleExchange

from .support import REPOSITORY_ROOT, create_request, create_service


OWNED_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/editorial/article_lifecycle.py",
    REPOSITORY_ROOT / "python/raos/ports/article_lifecycle.py",
    REPOSITORY_ROOT / "python/raos/application/editorial/article_lifecycle.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_article_lifecycle.py",
)


def _trees() -> tuple[ast.Module, ...]:
    return tuple(ast.parse(path.read_text(encoding="utf-8")) for path in OWNED_SOURCES)


def test_sources_import_no_repository_database_http_filesystem_or_provider() -> None:
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


def test_port_exposes_only_one_exchange_method() -> None:
    methods = {
        name
        for name, value in ArticleLifecycleExchange.__dict__.items()
        if inspect.isfunction(value)
    }
    assert methods - {"__init__"} == {"exchange"}


def test_exact_seven_request_and_outcome_types_exist_without_delete() -> None:
    requests = {
        name
        for name, value in vars(domain).items()
        if name.endswith("Request") and inspect.isclass(value) and is_dataclass(value)
    }
    outcomes = {
        name
        for name, value in vars(domain).items()
        if name.endswith("Outcome") and inspect.isclass(value) and is_dataclass(value)
    }
    assert requests == {
        "CreateArticleRequest",
        "ListArticlesRequest",
        "GetArticleRequest",
        "UpdateArticleRequest",
        "CreateVersionRequest",
        "GetVersionRequest",
        "UpdateVersionRequest",
    }
    assert outcomes == {
        "CreateArticleOutcome",
        "ListArticlesOutcome",
        "GetArticleOutcome",
        "UpdateArticleOutcome",
        "CreateVersionOutcome",
        "GetVersionOutcome",
        "UpdateVersionOutcome",
    }
    assert all("Delete" not in name for name in requests | outcomes)


def test_application_contains_one_exchange_call_and_no_retry_or_transition_call() -> (
    None
):
    tree = _trees()[2]
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.count("exchange") == 1
    assert set(calls).isdisjoint(
        {
            "approve",
            "commit",
            "connect",
            "fetch",
            "persist",
            "publish",
            "retry",
            "review",
            "save",
            "sleep",
            "transition",
            "write",
        }
    )


def test_sources_define_no_repository_uow_storage_or_external_method() -> None:
    forbidden = {
        "add",
        "commit",
        "connect",
        "delete",
        "fetch",
        "flush",
        "open",
        "persist",
        "publish",
        "release",
        "repository",
        "rollback",
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


def test_no_clock_random_uuid_environment_or_external_io_calls() -> None:
    forbidden = {
        "getenv",
        "now",
        "open",
        "request",
        "time",
        "time_ns",
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
    request = create_request()
    with pytest.raises(FrozenInstanceError):
        setattr(request, "plan", request.plan)
    for value in vars(domain).values():
        if inspect.isclass(value) and is_dataclass(value):
            assert all(
                field.default is MISSING and field.default_factory is MISSING
                for field in fields(value)
            )


def test_adapter_has_no_business_map_history_or_generated_values() -> None:
    adapter = create_service()._exchange
    assert type(adapter) is RecordedArticleLifecycleExchange
    assert RecordedArticleLifecycleExchange.__slots__ == (
        "_index",
        "_lock",
        "_scripts",
    )
    for name in (
        "history",
        "items",
        "repository",
        "records",
        "save",
        "snapshot",
    ):
        assert not hasattr(adapter, name)


def test_readiness_and_execution_vocabularies_cannot_claim_runtime_success() -> None:
    assert {value.value for value in domain.LifecycleDecision} == {"NOT_READY"}
    assert {value.value for value in domain.LifecycleExecution} == {
        "RECORDED_ONLY",
        "NOT_EXECUTED",
    }
    prohibited = {
        "APPROVED",
        "EXECUTED",
        "PERSISTED",
        "PUBLISHED",
        "READY",
        "SUCCEEDED",
        "VERIFIED",
    }
    assert prohibited.isdisjoint(value.value for value in domain.LifecycleDecision)
    assert prohibited.isdisjoint(value.value for value in domain.LifecycleExecution)
