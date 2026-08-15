"""Static ownership and dangerous-capability checks for ST-1406."""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import REPOSITORY_ROOT


README = Path("changes/st-1406/README.md")
DOMAIN = Path("python/raos/domain/ops/incident.py")
PORT = Path("python/raos/ports/incident.py")
APPLICATION = Path("python/raos/application/ops/incident.py")
ADAPTER = Path("python/raos/adapters/recorded_incident.py")
OWNED_SOURCE = (DOMAIN, PORT, APPLICATION, ADAPTER)
OWNED_PATHS = {
    README,
    *OWNED_SOURCE,
    Path("tests/st1406/conftest.py"),
    Path("tests/st1406/test_domain.py"),
    Path("tests/st1406/test_runtime.py"),
    Path("tests/st1406/test_boundaries.py"),
}


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


def _calls(path: Path) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def _public_methods(path: Path, class_name: str) -> set[str]:
    selected = next(
        node
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name
        for node in selected.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def test_dependency_directions_are_exactly_inward() -> None:
    assert {name for name in _imports(DOMAIN) if name.startswith("raos.")} == {
        "raos.domain.ops.kill_switch"
    }
    assert {name for name in _imports(PORT) if name.startswith("raos.")} == {
        "raos.domain.ops.incident"
    }
    assert {name for name in _imports(APPLICATION) if name.startswith("raos.")} == {
        "raos.domain.ops.incident",
        "raos.ports.incident",
    }
    assert {name for name in _imports(ADAPTER) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ops.incident",
        "raos.ports.incident",
    }


def test_no_database_http_provider_file_network_process_or_background_surface() -> None:
    all_imports = set().union(*(_imports(path) for path in OWNED_SOURCE))
    forbidden_roots = {
        "asyncio",
        "boto3",
        "botocore",
        "fastapi",
        "httpx",
        "logging",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "starlette",
        "subprocess",
        "urllib",
    }
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }
    forbidden_calls = {
        "create_task",
        "getenv",
        "open",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "sleep",
        "start",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    assert (
        set()
        .union(*(_calls(path) for path in OWNED_SOURCE))
        .isdisjoint(forbidden_calls)
    )
    assert not any(
        isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.While))
        for path in OWNED_SOURCE
        for node in ast.walk(_tree(path))
    )


def test_service_and_adapter_expose_only_the_bounded_local_surface() -> None:
    assert _public_methods(APPLICATION, "IncidentService") == {
        "declare",
        "append_timeline",
        "transition",
        "record_kill_switch_intent",
    }
    assert _public_methods(ADAPTER, "RecordedIncidentAdapter") == {
        "environment",
        "capacity",
        "apply",
        "current_state",
        "timeline",
        "contract_intents",
    }
    public = _public_methods(APPLICATION, "IncidentService") | _public_methods(
        ADAPTER, "RecordedIncidentAdapter"
    )
    assert public.isdisjoint(
        {
            "activate",
            "deploy",
            "disable",
            "engage",
            "enqueue",
            "execute",
            "notify",
            "publish",
            "release",
            "send",
            "serve",
            "start",
            "unpublish",
        }
    )


def test_st1405_is_input_only_and_st0405_atomicity_is_not_fabricated() -> None:
    combined = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8") for path in OWNED_SOURCE
    )
    assert "KillSwitchEventIntent" in combined
    assert "KillSwitchRuntimeService" not in combined
    assert "RecordedKillSwitchAdapter" not in combined
    assert "KillSwitchChangeCommand" not in combined
    assert "AuditService" not in combined
    assert "AuditCommitToken" not in combined


def test_domain_retains_only_evidence_references_and_no_arbitrary_mapping() -> None:
    domain_tree = _tree(DOMAIN)
    evidence = next(
        node
        for node in domain_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "IncidentEvidenceReference"
    )
    fields = {
        statement.target.id
        for statement in evidence.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
    }
    assert fields == {"artifact_id", "artifact_sha256"}
    forbidden_identifiers = {
        "artifact_body",
        "credential",
        "customer_message",
        "evidence_body",
        "exception_text",
        "personal_data",
        "provider_response",
        "raw_artifact",
        "raw_evidence",
        "secret",
        "token",
    }
    identifiers: set[str] = set()
    for node in ast.walk(domain_tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg.lower())
    assert forbidden_identifiers.isdisjoint(identifiers)


def test_adapter_is_exact_dev_ci_and_has_no_event_delivery_method() -> None:
    tree = ast.dump(_tree(ADAPTER), include_attributes=False)
    assert "ENV_DEV" in tree
    assert "CI" in tree
    assert "PRODUCTION" not in tree
    assert "STAGING" not in tree
    assert "RECOVERY" not in tree
    assert "INTEGRATION" not in tree
    source = (REPOSITORY_ROOT / ADAPTER).read_text(encoding="utf-8").lower()
    assert "publisher" in source
    assert "def publish" not in source
    assert "def send" not in source
    assert "def notify" not in source


def test_owned_scope_is_exact_and_shared_exports_are_untouched() -> None:
    assert OWNED_PATHS == {
        Path("changes/st-1406/README.md"),
        Path("python/raos/domain/ops/incident.py"),
        Path("python/raos/ports/incident.py"),
        Path("python/raos/application/ops/incident.py"),
        Path("python/raos/adapters/recorded_incident.py"),
        Path("tests/st1406/conftest.py"),
        Path("tests/st1406/test_domain.py"),
        Path("tests/st1406/test_runtime.py"),
        Path("tests/st1406/test_boundaries.py"),
    }
    assert Path("python/raos/domain/ops/__init__.py") not in OWNED_PATHS
    assert Path("python/raos/application/ops/__init__.py") not in OWNED_PATHS
    assert Path("python/raos/ports/__init__.py") not in OWNED_PATHS
    assert Path("python/raos/adapters/__init__.py") not in OWNED_PATHS


def test_readme_keeps_contract_mappings_and_formal_work_explicitly_deferred() -> None:
    readme = (REPOSITORY_ROOT / README).read_text(encoding="utf-8")
    required = {
        "P0/P1/P2/P3",
        "IncidentEventRequest",
        "ST-0405",
        "TST-012",
        "TST-028",
        "NOT_EXECUTED",
        "Production",
    }
    assert all(marker in readme for marker in required)
