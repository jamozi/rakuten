"""Static architecture and capability boundaries for ST-0503."""

from __future__ import annotations

import ast
from pathlib import Path

from raos.ports.catalog_normalization import CatalogNormalizationExchange


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATHS = (
    ROOT / "python/raos/domain/catalog/catalog_normalization.py",
    ROOT / "python/raos/ports/catalog_normalization.py",
    ROOT / "python/raos/application/catalog/catalog_normalization.py",
    ROOT / "python/raos/adapters/recorded_catalog_normalization.py",
)


def _trees() -> tuple[ast.AST, ...]:
    return tuple(
        ast.parse(path.read_text(encoding="utf-8")) for path in PRODUCTION_PATHS
    )


def test_port_exposes_only_one_normalize_exchange() -> None:
    assert {
        name
        for name, value in CatalogNormalizationExchange.__dict__.items()
        if callable(value) and not name.startswith("_")
    } == {"normalize"}


def test_production_slice_has_no_io_network_provider_or_database_imports() -> None:
    imported = {
        alias.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = {
        "boto3",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "sqlalchemy",
        "psycopg",
        "pathlib",
        "os",
        "random",
        "time",
    }
    assert imported.isdisjoint(forbidden)


def test_production_slice_has_no_external_io_or_state_lifecycle_calls() -> None:
    called_names = {
        node.func.id
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_names.isdisjoint(
        {
            "open",
            "getenv",
            "system",
            "exec",
            "eval",
            "uuid4",
            "uuid7",
            "sleep",
        }
    )
    assert called_attributes.isdisjoint(
        {
            "open",
            "read",
            "write",
            "connect",
            "execute",
            "request",
            "send",
            "save",
            "commit",
            "rollback",
            "delete",
            "publish",
            "now",
            "utcnow",
            "getenv",
        }
    )


def test_normalizer_never_reads_affiliate_shipping_or_source_body_fields() -> None:
    accessed_attributes = {
        node.attr
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name)
        and node.value.id == "item"
    }
    assert accessed_attributes.isdisjoint(
        {
            "affiliate_rate",
            "affiliate_url",
            "postage_included",
            "catchcopy",
            "item_caption",
            "shop_code",
            "shop_name",
        }
    )


def test_no_repository_uow_job_event_or_identity_service_surface_exists() -> None:
    public_methods = {
        node.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods.isdisjoint(
        {
            "save",
            "get",
            "list",
            "add",
            "commit",
            "rollback",
            "begin",
            "create_job",
            "emit_event",
            "merge",
            "split",
            "group",
            "identify",
            "persist",
            "delete",
        }
    )


def test_domain_and_port_preserve_inward_dependency_direction() -> None:
    domain_imports = {
        node.module or ""
        for node in ast.walk(_trees()[0])
        if isinstance(node, ast.ImportFrom)
    }
    port_imports = {
        node.module or ""
        for node in ast.walk(_trees()[1])
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(
        name.startswith(("raos.application", "raos.adapters", "raos.ports"))
        for name in domain_imports
    )
    assert not any(
        name.startswith(("raos.application", "raos.adapters")) for name in port_imports
    )
