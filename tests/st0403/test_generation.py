"""Deterministic owner generation and no-authority manifest coverage."""

from __future__ import annotations

import inspect
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import build_st0403_authorization_runtime as generator


OUTPUTS = (
    generator.GENERATED_JSON,
    generator.GENERATED_PYTHON,
    generator.MANIFEST,
)


def _snapshot() -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in OUTPUTS
    }


def test_installed_artifacts_equal_owner_generated_bytes() -> None:
    contract = generator._validate_contract_shape(generator._json(generator.CONTRACT))
    expected = generator._outputs(contract, generator._source_paths(contract))
    assert tuple(expected) == OUTPUTS
    assert all(path.read_bytes() == payload for path, payload in expected.items())


def test_check_mode_is_byte_and_metadata_no_write() -> None:
    before = _snapshot()
    completed = subprocess.run(
        [sys.executable, str(generator.__file__), "--check"],
        cwd=generator.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert _snapshot() == before


def test_unknown_cli_argument_fails_without_modifying_outputs() -> None:
    before = _snapshot()
    completed = subprocess.run(
        [sys.executable, str(generator.__file__), "--unknown"],
        cwd=generator.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert _snapshot() == before


def test_generated_manifest_keeps_every_external_authority_closed() -> None:
    manifest = json.loads(generator.MANIFEST.read_bytes())
    generated = json.loads(generator.GENERATED_JSON.read_bytes())
    assert manifest["story_id"] == generated["story_id"] == "ST-0403"
    assert manifest["status"] == generated["status"] == "LOCAL_CODE_COMPLETE"
    assert all(value is False for value in manifest["authority"].values())
    assert len(generated["matrix"]) == 19
    assert len(generated["bindings"]) == 20
    assert generated["service_principal"]["status"] == ("DISABLED_MAPPING_UNRESOLVED")
    assert generated["value_trust_boundary"] == {
        "business_action_execution": False,
        "constructor_scope": "INTERNAL_VALUE_NORMALIZATION_NOT_SERVICE_PROVENANCE",
        "external_input_construction": "FORBIDDEN",
        "runtime_enforcement_entrypoints": [
            "AuthorizationGuard.require",
            "DurableAuthorizationService.evaluate_admin",
            "DurableAuthorizationService.require_admin",
        ],
        "status": "TRUSTED_IN_PROCESS_TCB_ONLY",
        "unforgeable_capability": False,
    }
    assert manifest["implementation_sha256"] == {
        str(path.relative_to(generator.ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(generator._IMPLEMENTATION_PATHS, key=lambda item: str(item))
    }
    assert all(
        hashlib.sha256((generator.ROOT / path).read_bytes()).hexdigest() == digest
        for path, digest in manifest["source_sha256"].items()
    )


def test_generator_rejects_duplicate_or_partial_contract_shapes() -> None:
    with pytest.raises(SystemExit, match="duplicate JSON key"):
        generator._pairs([("story_id", "ST-0403"), ("story_id", "ST-0403")])
    with pytest.raises(SystemExit, match="contract.*unexpected keys"):
        generator._validate_contract_shape({"story_id": "ST-0403"})
    source = inspect.getsource(generator)
    for forbidden in ("httpx", "requests", "socket", "urllib"):
        assert forbidden not in source
