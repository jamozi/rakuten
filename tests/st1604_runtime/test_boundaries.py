"""Architecture and forbidden-capability checks for ST-1604 V2."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OWNED = (
    ROOT / "python/raos/domain/ops/performance_load.py",
    ROOT / "python/raos/ports/performance_load.py",
    ROOT / "python/raos/application/ops/performance_load.py",
    ROOT / "python/raos/adapters/recorded_performance_load.py",
)


def test_runtime_has_no_network_browser_process_or_provider_capability() -> None:
    forbidden_import_roots = {
        "aiohttp",
        "boto3",
        "botocore",
        "httpx",
        "playwright",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    for path in OWNED:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden_import_roots), (path, imported)


def test_port_exposes_append_only_without_read_export_or_lifecycle() -> None:
    source = (ROOT / "python/raos/ports/performance_load.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PerformanceLoadJournalPort"
    )
    methods = {node.name for node in protocol.body if isinstance(node, ast.FunctionDef)}
    assert methods == {"action_count", "append"}


def test_runtime_contains_no_financial_ranking_or_live_claim_vocabulary() -> None:
    content = b"\n".join(path.read_bytes().lower() for path in OWNED)
    for token in (
        b"affiliate ranking",
        b"commission rate",
        b"epc",
        b"rpm",
        b"profit ranking",
        b"production_ready",
        b"formal_tst_027_pass",
    ):
        assert token not in content
