"""Static trust-boundary checks for the ST-0501 local seam."""

from __future__ import annotations

import ast
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
import inspect

import pytest

from raos.domain.editorial import article_plan
from raos.domain.portfolio import workflow as portfolio
from raos.ports.portfolio_workflow import PortfolioWorkflowExchange

from conftest import REPOSITORY_ROOT, category_request


OWNED_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/portfolio/workflow.py",
    REPOSITORY_ROOT / "python/raos/domain/editorial/article_plan.py",
    REPOSITORY_ROOT / "python/raos/ports/portfolio_workflow.py",
    REPOSITORY_ROOT / "python/raos/application/portfolio/workflow.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_portfolio_workflow.py",
)


def _trees() -> tuple[ast.Module, ...]:
    return tuple(ast.parse(path.read_text(encoding="utf-8")) for path in OWNED_SOURCES)


def test_sources_import_no_external_or_io_surface() -> None:
    forbidden_roots = {
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
    assert imported.isdisjoint(forbidden_roots)


def test_sources_define_no_storage_or_external_action_method() -> None:
    forbidden = {
        "add",
        "commit",
        "connect",
        "delete",
        "execute_sql",
        "export",
        "fetch",
        "flush",
        "open",
        "publish",
        "release",
        "remove",
        "restore",
        "rollback",
        "save",
        "send",
        "unlink",
        "upload",
    }
    defined = {
        node.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined.isdisjoint(forbidden)


def test_port_exposes_only_one_exchange_method() -> None:
    methods = {
        name
        for name, value in PortfolioWorkflowExchange.__dict__.items()
        if inspect.isfunction(value)
    }
    assert methods - {"__init__"} == {"exchange"}


def test_domain_contract_has_exact_sixteen_request_types_without_delete() -> None:
    requests = {
        name: value
        for module in (portfolio, article_plan)
        for name, value in vars(module).items()
        if name.endswith("Request") and inspect.isclass(value) and is_dataclass(value)
    }
    assert len(requests) == 16
    assert all("Delete" not in name for name in requests)
    assert all(
        parameter.default is inspect.Parameter.empty
        for request in requests.values()
        for parameter in inspect.signature(request).parameters.values()
    )


def test_domain_records_expose_no_arbitrary_mapping_or_raw_bytes_field() -> None:
    for module in (portfolio, article_plan):
        for value in vars(module).values():
            if inspect.isclass(value) and is_dataclass(value):
                annotations = tuple(str(field.type) for field in fields(value))
                assert not any(
                    "dict" in annotation.lower() for annotation in annotations
                )
                assert not any(
                    "bytes" in annotation.lower() for annotation in annotations
                )


def test_request_values_are_immutable() -> None:
    request = category_request()
    with pytest.raises(FrozenInstanceError):
        setattr(request, "values", request.values)


def test_owned_sources_contain_no_random_clock_or_uuid_generation() -> None:
    forbidden_calls = {"now", "time", "time_ns", "uuid1", "uuid4", "uuid6", "uuid7"}
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint(forbidden_calls)


def test_no_defaulted_environment_or_business_policy_field() -> None:
    for module in (portfolio, article_plan):
        for value in vars(module).values():
            if not (inspect.isclass(value) and is_dataclass(value)):
                continue
            assert all(
                field.default is MISSING and field.default_factory is MISSING
                for field in fields(value)
            )
