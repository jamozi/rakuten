from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

from raos.application.publishing.review_completion import ReviewCompletionService


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATHS = (
    Path("python/raos/domain/publishing/review_completion_v2.py"),
    Path("python/raos/ports/review_completion.py"),
    Path("python/raos/application/publishing/review_completion.py"),
    Path("python/raos/adapters/recorded_review_completion.py"),
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
    "subprocess",
    "urllib",
}
LEGACY_HASHES = {
    "python/raos/domain/publishing/review_workflow.py": "f7c84e1911d4570a4dc3492c395255da3fcef5eee5ec7b891058caf596e1efb5",
    "python/raos/domain/publishing/review_assignment_operations.py": "e85341c4bc3f8ab840d1152319fe56169aa870d6a4c588d5b14166c3a4a34726",
    "python/raos/application/publishing/review_assignment.py": "76ae2ef807308aee0fb3b10d1b2eca6ee6fb5c09666ce584985252ae52c80538",
    "python/raos/adapters/recorded_review_assignment.py": "bc14606f3716e018f19358873c0818bfcb5296011ad9f0d84f50aeedd8d5936f",
    "python/raos/domain/publishing/review_decision_operations.py": "f267f2af141d1269bceb175095dc4a397cafb78a120516bb3fb82a8c0706bc71",
    "python/raos/application/publishing/review_decision.py": "003435c919fab8b8ef651a59281f3b80e42d4dabbd741b1439b98744f18969d4",
    "python/raos/adapters/recorded_review_decision.py": "de6b942f9c795ddc2694cbf47e364b676a121a9976046f4f603f0181c91a513a",
}


def test_production_modules_have_no_external_io_or_process_capability() -> None:
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
    signature = inspect.signature(ReviewCompletionService.execute)
    assert tuple(signature.parameters) == ("self", "request")
    assert signature.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert not {"actor", "reviewer", "grant", "approval"} & set(signature.parameters)


def test_legacy_st0901_sources_are_byte_unchanged() -> None:
    for relative, expected in LEGACY_HASHES.items():
        assert (
            hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest() == expected
        )


def test_no_external_authority_language_in_runtime_exports() -> None:
    source = "\n".join((REPO_ROOT / path).read_text() for path in PRODUCTION_PATHS)
    assert "publication_authorized: bool = False" in source
    assert "final_approval_authorized: bool = False" in source
    assert "production_authorized: bool = False" in source
    assert "requests." not in source
    assert "urllib." not in source
