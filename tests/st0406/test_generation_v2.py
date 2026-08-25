"""Owner-generation drift checks for the ST-0406 V2 runtime contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.build_st0406_secure_object_intake_runtime import (
    MANIFEST,
    OUTPUT,
    ROOT,
    _render,
)


_V2_SOURCE = (
    Path("python/raos/domain/ops/object_intake_runtime_v2.py"),
    Path("python/raos/ports/object_intake_runtime_v2.py"),
    Path("python/raos/application/ops/object_intake_runtime_v2.py"),
    Path("python/raos/adapters/recorded_object_intake_runtime_v2.py"),
)


def test_committed_runtime_projection_and_manifest_match_owner_render() -> None:
    output, manifest = _render()
    assert (ROOT / OUTPUT).read_bytes() == output
    assert (ROOT / MANIFEST).read_bytes() == manifest


def test_generated_projection_preserves_zero_external_authority() -> None:
    projection = json.loads((ROOT / OUTPUT).read_text(encoding="utf-8"))
    assert projection["story_id"] == "ST-0406"
    assert projection["local_implementation_status"] == "LOCAL_CODE_COMPLETE"
    assert projection["external_actions"] == []
    contract = projection["runtime_contract"]
    assert contract["authority"]["external_action_count"] == 0
    assert set(contract["formal_evidence"].values()) == {"NOT_EXECUTED"}


def test_v2_runtime_has_no_network_process_provider_or_credential_capability() -> None:
    forbidden_imports = {
        "boto3",
        "botocore",
        "httpx",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {"popen", "run", "system", "urlopen"}
    for relative in _V2_SOURCE:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module.partition(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr.lower())
        assert forbidden_imports.isdisjoint(imports)
        assert forbidden_calls.isdisjoint(calls)
