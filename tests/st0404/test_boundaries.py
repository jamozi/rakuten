"""Static dependency and dangerous-surface assertions for ST-0404."""

from __future__ import annotations

import ast
from pathlib import Path

from .support import REPOSITORY_ROOT


DOMAIN_SOURCE = Path("python/raos/domain/http/security.py")
APPLICATION_SOURCE = Path("python/raos/application/http/security.py")
OWNED_SOURCE = (DOMAIN_SOURCE, APPLICATION_SOURCE)


def _tree(path: Path) -> ast.Module:
    return ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_dependencies_stay_framework_neutral_and_point_inward() -> None:
    domain_imports = _imports(DOMAIN_SOURCE)
    application_imports = _imports(APPLICATION_SOURCE)
    assert not {name for name in domain_imports if name.startswith("raos.")}
    assert {name for name in application_imports if name.startswith("raos.")} == {
        "raos.domain.http.security"
    }

    forbidden_roots = {
        "boto3",
        "fastapi",
        "httpx",
        "openai",
        "psycopg",
        "requests",
        "sqlalchemy",
        "starlette",
    }
    all_imports = domain_imports | application_imports
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }


def test_owned_source_has_no_file_network_process_env_db_or_secret_surface() -> None:
    prohibited_names = {
        "body",
        "cookie_value",
        "cookies",
        "environ",
        "getenv",
        "open",
        "password",
        "secret",
        "socket",
        "subprocess",
        "token_value",
    }
    prohibited_attributes = {
        "connect",
        "getenv",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "system",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    for path in OWNED_SOURCE:
        tree = _tree(path)
        identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert identifiers.isdisjoint(prohibited_names)
        assert attributes.isdisjoint(prohibited_attributes)


def test_request_metadata_surface_excludes_raw_request_and_authentication_data() -> (
    None
):
    tree = _tree(DOMAIN_SOURCE)
    metadata = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HttpRequestMetadata"
    )
    fields = {
        node.target.id
        for node in metadata.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert fields == {
        "method",
        "origin",
        "credential_mode",
        "content_type",
        "content_length",
        "request_header_names",
        "presented_csrf_proof",
        "expected_csrf_proof",
        "correlation_id",
    }
    assert fields.isdisjoint(
        {
            "authorization",
            "body",
            "cookie",
            "cookies",
            "password",
            "raw_headers",
            "secret",
            "token",
        }
    )


def test_problem_details_and_response_header_literals_exclude_unsafe_surface() -> None:
    source = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8") for path in OWNED_SOURCE
    )
    application_source = (REPOSITORY_ROOT / APPLICATION_SOURCE).read_text(
        encoding="utf-8"
    )
    assert "'unsafe-inline'" not in application_source
    assert "'unsafe-eval'" not in application_source
    assert 'Access-Control-Allow-Origin", "*' not in application_source

    problem = next(
        node
        for node in _tree(DOMAIN_SOURCE).body
        if isinstance(node, ast.ClassDef) and node.name == "ProblemDetails"
    )
    fields = {
        node.target.id
        for node in problem.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert fields == {"type", "title", "status", "code", "correlation_id"}
    assert "traceback" not in source
    assert "raw_body" not in source
