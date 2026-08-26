"""Owner-generation and authority-boundary tests for ST-1201 V2."""

from __future__ import annotations

import ast
import hashlib
import json
from typing import cast

from .support import REPOSITORY_ROOT
from scripts import build_st1201_durable_event_store as generator


def _json(relative: str) -> dict[str, object]:
    value: object = json.loads((REPOSITORY_ROOT / relative).read_bytes())
    assert type(value) is dict
    return cast(dict[str, object], value)


def _mapping(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    assert type(value) is list
    return cast(list[object], value)


def test_render_is_deterministic_and_matches_committed_outputs() -> None:
    generated, manifest = generator.render()
    assert generated == (REPOSITORY_ROOT / generator.GENERATED).read_bytes()
    assert manifest == (REPOSITORY_ROOT / generator.MANIFEST).read_bytes()
    assert generator.main(["--check"]) == 0


def test_contract_keeps_od012_tracking_and_all_external_authority_disabled() -> None:
    contract = _json("changes/st-1201/contracts/durable-recorded-event-store.v2.json")
    assert contract["local_implementation_status"] == "LOCAL_CODE_COMPLETE"
    consent = _mapping(contract["consent_boundary"])
    assert consent["open_decision"] == "OD-012"
    assert consent["browser_tracking_activation"] is False
    assert consent["consent_authority_claimed"] is False
    authority = _mapping(contract["authority"])
    assert authority["external_action_count"] == 0
    assert all(
        value is False
        for key, value in authority.items()
        if key != "external_action_count"
    )
    durable = _mapping(contract["durability_boundary"])
    assert durable["retention_period"] is None
    assert durable["delete_purge_export_query_lifecycle_surface"] is False


def test_manifest_binds_every_owned_and_canonical_source() -> None:
    manifest = _json("changes/st-1201/manifest.v2.json")
    sources = _list(manifest["sources"])
    assert len(sources) == len(generator.OWNED_SOURCES + generator.BOUND_SOURCES)
    for row in sources:
        source = _mapping(row)
        path = source["path"]
        assert type(path) is str
        payload = (REPOSITORY_ROOT / path).read_bytes()
        assert source["bytes"] == len(payload)
        assert source["sha256"] == hashlib.sha256(payload).hexdigest()


def test_owned_runtime_has_no_network_provider_or_external_process_surface() -> None:
    forbidden_modules = {
        "boto3",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib.request",
    }
    runtime_paths = tuple(
        path
        for path in generator.OWNED_SOURCES
        if path.suffix == ".py" and path.parts[0] == "python"
    )
    for relative in runtime_paths:
        tree = ast.parse((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        assert forbidden_modules.isdisjoint(imported)
        names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        assert {
            "activate_tracking",
            "delete",
            "deploy",
            "export",
            "publish",
            "purge",
            "release",
        }.isdisjoint(names)


def test_generated_projection_binds_exact_canonical_counts_and_formal_boundary() -> (
    None
):
    generated = _json("changes/st-1201/generated/durable-recorded-event-store.v2.json")
    checks = _mapping(generated["canonical_checks"])
    assert checks["canonical_event_count"] == 20
    assert checks["mvp_public_event_count"] == 11
    assert checks["open_decision"] == "OD-012_UNRESOLVED_SAFE_DEFAULT"
    formal = _mapping(generated["formal_evidence"])
    assert set(formal.values()) <= {
        "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED",
        "NOT_EXECUTED",
    }
