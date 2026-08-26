"""ST-1702 deterministic generation checks."""

from __future__ import annotations

import hashlib
import json

import yaml

from scripts import build_st1702_category_fixtures_rules_reference_plan as generator


def test_repository_outputs_are_current() -> None:
    generator.build(check=True)


def test_generate_then_check_is_stable(isolated_repository) -> None:
    generator.build(isolated_repository)
    generator.build(isolated_repository, check=True)
    payload = (isolated_repository / generator.REFERENCE_PLAN_PATH).read_bytes()
    plan = json.loads(payload)
    assert plan["fixture_boundary"]["runtime_category_config"] == "NOT_CREATED"
    manifest = yaml.safe_load(
        (isolated_repository / generator.MANIFEST_PATH).read_bytes()
    )
    assert manifest["generator_owner_id"] == (
        "build_st1702_category_fixtures_rules_reference_plan"
    )
    assert manifest["outputs"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert "base_commit" not in str(manifest).lower()
    assert "approval_sha256" not in str(manifest).lower()
