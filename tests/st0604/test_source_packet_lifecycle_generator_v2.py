"""Closed contract and deterministic owner-generation tests for ST-0604 V2."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


CONTRACT = Path("changes/st-0604/contracts/source-packet-lifecycle-runtime.v2.json")
FIXTURE = Path("changes/st-0604/fixtures/source-packet-lifecycle.synthetic.v2.json")
OUTPUT = Path("changes/st-0604/generated/source-packet-lifecycle-runtime.v2.json")
MANIFEST = Path("changes/st-0604/manifest.v2.json")
GENERATOR = Path("scripts/build_st0604_source_packet_lifecycle_runtime.py")


def _load_generator():
    specification = importlib.util.spec_from_file_location("st0604_v2_owner", GENERATOR)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def test_owner_check_is_no_write_and_deterministic() -> None:
    before = {
        path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in (OUTPUT, MANIFEST)
    }
    subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        check=True,
        cwd=Path.cwd(),
    )
    after = {
        path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in (OUTPUT, MANIFEST)
    }
    assert after == before


def test_manifest_binds_every_declared_source_and_generated_byte() -> None:
    manifest = _json(MANIFEST)
    sources = manifest["source_sha256"]
    generated = manifest["generated_sha256"]
    assert type(sources) is dict and type(generated) is dict
    for path_text, digest in sources.items():
        assert hashlib.sha256(Path(path_text).read_bytes()).hexdigest() == digest
    assert generated == {str(OUTPUT): hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}
    assert manifest["external_actions"] == []
    assert manifest["production_authority"] == "NONE"


def test_generated_report_is_exact_contract_plus_closed_runtime_report() -> None:
    contract = _json(CONTRACT)
    fixture = _json(FIXTURE)
    output = _json(OUTPUT)
    for key, value in contract.items():
        assert output[key] == value
    assert output["recorded_synthetic_fixture_report"] == fixture
    assert output["external_actions"] == []
    assert output["production_authority"] == "NONE"
    runtime = output["runtime_contract"]
    assert type(runtime) is dict
    assert (
        runtime["approved_generation_input_type"] == "ApprovedLockedGenerationInputV2"
    )
    assert runtime["replay_statuses"] == ["COMMITTED", "REPLAYED"]


@pytest.mark.parametrize(
    "mutator",
    (
        lambda value: {**value, "unknown": True},
        lambda value: {**value, "story_id": "ST-9999"},
        lambda value: {**value, "local_implementation_status": "VALIDATED"},
        lambda value: {
            **value,
            "authority_boundary": {
                **value["authority_boundary"],
                "publication": True,
            },
        },
        lambda value: {
            **value,
            "generation_gate": {
                **value["generation_gate"],
                "required_lock": False,
            },
        },
        lambda value: {
            **value,
            "lifecycle_boundary": {
                **value["lifecycle_boundary"],
                "idempotency_key": "command_id",
            },
        },
        lambda value: {
            **value,
            "durability_boundary": {
                **value["durability_boundary"],
                "unknown": True,
            },
        },
        lambda value: {
            **value,
            "formal_evidence": {
                **value["formal_evidence"],
                "TST-012": "VALIDATED",
            },
        },
        lambda value: {
            **value,
            "dependency_bindings": {
                **value["dependency_bindings"],
                "ST-0602": {
                    **value["dependency_bindings"]["ST-0602"],
                    "unknown": True,
                },
            },
        },
    ),
)
def test_closed_contract_mutations_are_rejected(mutator) -> None:
    module = _load_generator()
    changed = mutator(_json(CONTRACT))
    with pytest.raises(module.BuildError):
        module._validate_contract(changed)


def test_fixture_cannot_activate_or_add_external_actions() -> None:
    module = _load_generator()
    fixture = _json(FIXTURE)
    with pytest.raises(module.BuildError):
        module._validate_fixture({**fixture, "activation": True})
    changed = {
        **fixture,
        "expected_action_counts": {
            **fixture["expected_action_counts"],
            "provider": 1,
        },
    }
    with pytest.raises(module.BuildError):
        module._validate_fixture(changed)
    with pytest.raises(module.BuildError):
        module._validate_fixture(
            {
                **fixture,
                "input_summary": {
                    **fixture["input_summary"],
                    "unknown": 1,
                },
            }
        )
