from __future__ import annotations

import ast
import inspect
from pathlib import Path

import yaml

from raos.application.publishing.final_approval import FinalApprovalService


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATHS = (
    Path("python/raos/domain/publishing/final_approval.py"),
    Path("python/raos/ports/final_approval.py"),
    Path("python/raos/application/publishing/final_approval.py"),
    Path("python/raos/adapters/recorded_final_approval.py"),
)
FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "boto3",
    "http",
    "httpx",
    "os",
    "pathlib",
    "requests",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
}


def test_runtime_modules_have_no_external_io_or_process_capability() -> None:
    for relative in PRODUCTION_PATHS:
        tree = ast.parse((REPO_ROOT / relative).read_text())
        imported: set[str] = set()
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
        assert not imported & FORBIDDEN_IMPORT_ROOTS
        assert not called_names & {"open", "exec", "eval", "compile", "__import__"}


def test_public_service_accepts_request_only() -> None:
    signature = inspect.signature(FinalApprovalService.execute)
    assert tuple(signature.parameters) == ("self", "request")
    assert signature.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert not {"actor", "approver", "role", "mfa", "step_up"} & set(
        signature.parameters
    )


def test_contract_and_runtime_export_no_external_authority() -> None:
    contract = yaml.safe_load(
        (
            REPO_ROOT / "changes/st-0902/contracts/final-approval-runtime.v2.yaml"
        ).read_text()
    )
    assert all(
        contract["runtime"][key] is False
        for key in (
            "real_final_approval_authorized",
            "publication_snapshot_authorized",
            "publication_authorized",
            "release_authorized",
            "production_authorized",
        )
    )
    assert all(
        value == "FORBIDDEN" for value in contract["execution_boundary"].values()
    )
    source = "\n".join((REPO_ROOT / path).read_text() for path in PRODUCTION_PATHS)
    assert "publication_authorized: bool = False" in source
    assert "production_authorized: bool = False" in source
    assert "requests." not in source
    assert "urllib." not in source


def test_import_direction_keeps_domain_and_ports_provider_neutral() -> None:
    domain_tree = ast.parse((REPO_ROOT / PRODUCTION_PATHS[0]).read_text())
    port_tree = ast.parse((REPO_ROOT / PRODUCTION_PATHS[1]).read_text())
    for tree in (domain_tree, port_tree):
        imported = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert not any(
            name.startswith("raos.adapters") or name.startswith("raos.application")
            for name in imported
        )
