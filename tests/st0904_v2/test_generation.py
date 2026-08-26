from __future__ import annotations

# pyright: reportPrivateUsage=false

from collections.abc import Callable
import hashlib
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
import pytest
import yaml

from .support import REPO_ROOT, read
from scripts import build_st0904_public_projection_runtime_v2 as generator
from raos.adapters.recorded_public_projection_fixture_v2 import (
    PUBLIC_PROJECTION_PASS_V2_JSON,
    PUBLIC_PROJECTION_PASS_V2_SHA256,
)


def test_owner_generator_is_no_write_clean() -> None:
    generator.build(REPO_ROOT, check=True)


def test_generated_module_is_exact_fixture_copy() -> None:
    fixture = read(generator.FIXTURE_PATH)
    assert PUBLIC_PROJECTION_PASS_V2_JSON == fixture
    assert PUBLIC_PROJECTION_PASS_V2_SHA256 == hashlib.sha256(fixture).hexdigest()


def test_manifest_binds_every_owner_and_dependency_source() -> None:
    manifest = yaml.safe_load(read(generator.MANIFEST_PATH))
    rows = manifest["source_artifacts"]
    observed = {row["uri"]: row for row in rows}
    assert manifest["source_artifact_count"] == len(rows)
    assert manifest["generated_artifact_count"] == 2
    assert len(observed) == len(rows)
    expected = {
        f"repo://{path.as_posix()}"
        for path in (*generator.SOURCE_PATHS, *generator.DEPENDENCY_PATHS)
    }
    assert set(observed) == expected
    for uri, row in observed.items():
        payload = (REPO_ROOT / Path(uri.removeprefix("repo://"))).read_bytes()
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()


def test_manifest_preserves_every_external_gate() -> None:
    authority = yaml.safe_load(read(generator.MANIFEST_PATH))["authority"]
    assert authority["database_write_authorized"] is False
    assert authority["public_projection_authorized"] is False
    assert authority["route_activation_authorized"] is False
    assert authority["public_read_authorized"] is False
    assert authority["publication_authorized"] is False
    assert authority["release_authorized"] is False
    assert authority["production_authorized"] is False
    assert set(authority.values()) <= {False, "NOT_EXECUTED"}


def test_generated_article_and_route_validate_against_public_openapi() -> None:
    document = yaml.safe_load(read(generator.FIXTURE_PATH))
    projection = cast(dict[str, object], document["output"]["projection"])
    openapi = cast(
        dict[str, object],
        yaml.safe_load(read(generator._BINDING_PATHS["public_openapi"])),
    )
    components = openapi["components"]
    format_checker = FormatChecker()
    for name, value in (
        ("PublicArticleDocument", projection["article"]),
        ("PublicRoute", projection["route"]),
    ):
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/components/schemas/{name}",
            "components": components,
        }
        Draft202012Validator(schema, format_checker=format_checker).validate(value)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda value: value.replace(
                "  public_projection_authorized: false",
                "  public_projection_authorized: true",
                1,
            ),
            "AUTHORITY_ESCALATION",
        ),
        (
            lambda value: value.replace(
                "schema_version: 2",
                "schema_version: 2\nschema_version: 2",
                1,
            ),
            "CONTRACT_MAPPING_INVALID",
        ),
        (
            lambda value: value.replace(
                "  unresolved_production_values_invented: false",
                "  unresolved_production_values_invented: true",
                1,
            ),
            "COMPATIBILITY_BOUNDARY_INVALID",
        ),
    ],
)
def test_contract_mutations_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[str], str],
    code: str,
) -> None:
    original_reader = generator._read_regular
    original = read(generator.CONTRACT_PATH).decode("utf-8")
    mutated = mutate(original).encode("utf-8")
    contract_path = REPO_ROOT / generator.CONTRACT_PATH

    def reader(path: Path) -> bytes:
        return mutated if path == contract_path else original_reader(path)

    monkeypatch.setattr(generator, "_read_regular", reader)
    with pytest.raises(generator.PublicProjectionGenerationError) as captured:
        generator.load_contract(REPO_ROOT)
    assert captured.value.code == code
