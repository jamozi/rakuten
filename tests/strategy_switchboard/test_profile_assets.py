from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts import build_all_story_strategy_catalog as generator

from raos.strategy_switchboard.catalog import (
    ADVANCED_EXTERNAL_PROFILE,
    BALANCED_STAGING_PROFILE,
    SAFE_LOCAL_PROFILE,
)
from raos.strategy_switchboard.config import load_profile_json


ASSET_ROOT = (
    generator.REPOSITORY_ROOT / "changes/all-stories-switchable-strategies"
)
PROFILE_SCHEMA = ASSET_ROOT / "schemas/strategy-profile.v1.schema.json"
GATE_SCHEMA = ASSET_ROOT / "schemas/gate-context.v1.schema.json"
PROFILE_ROOT = ASSET_ROOT / "profiles"


def _json(path: Path) -> object:
    return json.loads(path.read_bytes())


def test_distributed_schemas_are_valid_draft_2020_12() -> None:
    for path in (PROFILE_SCHEMA, GATE_SCHEMA):
        document = _json(path)
        Draft202012Validator.check_schema(document)


def test_distributed_profiles_validate_against_schema() -> None:
    validator = Draft202012Validator(_json(PROFILE_SCHEMA))

    for path in sorted(PROFILE_ROOT.glob("*.json")):
        errors = sorted(validator.iter_errors(_json(path)), key=lambda item: item.json_path)
        assert errors == [], (path, errors)


def test_distributed_profiles_match_builtin_semantics() -> None:
    expected = {
        "safe-local.v1.json": SAFE_LOCAL_PROFILE,
        "balanced-staging.v1.json": BALANCED_STAGING_PROFILE,
        "advanced-external.v1.json": ADVANCED_EXTERNAL_PROFILE,
    }

    assert {path.name for path in PROFILE_ROOT.glob("*.json")} == set(expected)
    for filename, profile in expected.items():
        loaded = load_profile_json((PROFILE_ROOT / filename).read_bytes())
        assert loaded == profile
        assert loaded.to_record() == profile.to_record()
