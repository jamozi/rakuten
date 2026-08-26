"""Generation checks for the ST-1703 low-cost pilot."""

from __future__ import annotations

import hashlib
import json

import yaml

from scripts import build_st1703_low_cost_publication_pilot as generator


def test_generate_then_check_is_stable(tmp_path) -> None:
    root = tmp_path / "repository"
    source = root / generator.CONTRACT_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes((generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes())
    generator.build(root)
    generator.build(root, check=True)
    output = (root / generator.OUTPUT_PATH).read_bytes()
    assert json.loads(output)["document"]["version"] == "2.0.0"
    manifest = yaml.safe_load((root / generator.MANIFEST_PATH).read_bytes())
    assert manifest["generator_owner_id"] == ("build_st1703_low_cost_publication_pilot")
    assert manifest["semantic_inputs"][0]["semantic_version"] == "2.0.0"
    assert manifest["outputs"] == [
        {
            "uri": f"repo://{generator.OUTPUT_PATH.as_posix()}",
            "bytes": len(output),
            "sha256": hashlib.sha256(output).hexdigest(),
        }
    ]


def test_repository_outputs_are_current() -> None:
    generator.build(check=True)
