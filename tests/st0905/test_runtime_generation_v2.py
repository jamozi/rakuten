"""Owner-generation, authority, and static-isolation checks for ST-0905 V2."""

from __future__ import annotations

import ast
from collections.abc import Callable
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st0905_publication_commands_runtime_v2 as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def read(relative: Path) -> bytes:
    return (REPOSITORY_ROOT / relative).read_bytes()


def test_owner_generation_is_deterministic_and_no_write_clean() -> None:
    assert generator.render_outputs() == generator.render_outputs()
    generator.build(check=True)
    for relative, expected in generator.render_outputs().items():
        assert read(relative) == expected


def test_manifest_binds_every_owner_dependency_and_generated_byte() -> None:
    manifest = yaml.safe_load(read(generator.MANIFEST_PATH))
    rows = manifest["source_artifacts"]
    observed = {row["uri"]: row for row in rows}
    expected = {
        f"repo://{path.as_posix()}"
        for path in (*generator.SOURCE_PATHS, *generator.DEPENDENCY_PATHS)
    }
    assert set(observed) == expected
    assert len(observed) == len(rows) == manifest["source_artifact_count"]
    for uri, row in observed.items():
        payload = read(Path(uri.removeprefix("repo://")))
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    fixture = read(generator.FIXTURE_PATH)
    generated = manifest["generated_artifacts"]
    assert generated == [
        {
            "uri": f"repo://{generator.FIXTURE_PATH.as_posix()}",
            "artifact_role": "GENERATED_RECORDED_PUBLICATION_COMMAND_FIXTURE",
            "media_type": "application/json",
            "bytes": len(fixture),
            "sha256": hashlib.sha256(fixture).hexdigest(),
        }
    ]
    assert set(manifest["authority"].values()) <= {False, "NOT_EXECUTED"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.replace(
            "  publication_authorized: false",
            "  publication_authorized: true",
            1,
        ),
        lambda value: value.replace(
            "schema_version: 2",
            "schema_version: 2\nschema_version: 2",
            1,
        ),
        lambda value: value.replace(
            "  unpublish: DENY_NO_CANONICAL_ROLE_ACTION",
            "  unpublish: PROCESS_LOCAL_RECORDED_TRANSACTION",
            1,
        ),
    ],
)
def test_contract_authority_duplicate_and_role_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[str], str],
) -> None:
    original_reader = generator._read_regular
    contract_path = REPOSITORY_ROOT / generator.CONTRACT_PATH
    mutated = mutate(read(generator.CONTRACT_PATH).decode("utf-8")).encode("utf-8")

    def reader(path: Path) -> bytes:
        return mutated if path == contract_path else original_reader(path)

    monkeypatch.setattr(generator, "_read_regular", reader)
    with pytest.raises(generator.PublicationCommandGenerationError):
        generator.load_contract()


def test_generated_fixture_has_no_external_authority_or_sensitive_material() -> None:
    document = json.loads(read(generator.FIXTURE_PATH))
    assert set(document["authority"].values()) == {False}
    assert set(document["external_gates"].values()) == {"NOT_EXECUTED"}
    serialized = read(generator.FIXTURE_PATH).decode("utf-8").casefold()
    for forbidden in (
        "access_token",
        "api_key",
        "credential",
        "password",
        "private_key",
        "raw_prompt",
        "secret",
        "affiliate_rate",
        "commission",
        "epc",
        "profit",
        "revenue",
        "rpm",
    ):
        assert forbidden not in serialized


def test_runtime_import_graph_has_no_network_database_route_or_cms_adapter() -> None:
    runtime_paths = (
        Path("python/raos/domain/publishing/publication_commands_v2.py"),
        Path("python/raos/ports/publishing/publication_commands_v2.py"),
        Path("python/raos/application/publishing/publication_commands_v2.py"),
        Path("python/raos/adapters/publishing/recorded_publication_commands_v2.py"),
        Path(
            "python/raos/adapters/publishing/recorded_publication_command_fixture_v2.py"
        ),
    )
    forbidden = {
        "boto3",
        "django",
        "flask",
        "httpx",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "urllib",
    }
    for path in runtime_paths:
        tree = ast.parse(read(path), filename=path.as_posix())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert {alias.name.split(".")[0] for alias in node.names}.isdisjoint(
                    forbidden
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden
