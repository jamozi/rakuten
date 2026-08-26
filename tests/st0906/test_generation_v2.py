"""Owner-generation and hostile boundary tests for ST-0906 V2."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st0906_publication_review_workspace_v2 as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read(relative: Path) -> bytes:
    return (REPOSITORY_ROOT / relative).read_bytes()


def test_owner_generation_is_deterministic_current_and_no_write() -> None:
    first = generator.expected_artifacts()
    second = generator.expected_artifacts()
    assert first == second
    before = {
        relative: (_read(relative), (REPOSITORY_ROOT / relative).stat().st_mtime_ns)
        for relative, _payload in first
    }
    generator.build(check=True)
    assert before == {
        relative: (_read(relative), (REPOSITORY_ROOT / relative).stat().st_mtime_ns)
        for relative, _payload in first
    }
    for relative, expected in first:
        assert _read(relative) == expected


def test_manifest_hash_binds_all_owner_dependency_and_generated_bytes() -> None:
    manifest = yaml.safe_load(_read(generator.MANIFEST_PATH))
    source_rows = manifest["source_artifacts"]
    expected_paths = set(generator.SOURCE_PATHS)
    assert manifest["source_artifact_count"] == len(source_rows)
    assert {Path(row["uri"].removeprefix("repo://")) for row in source_rows} == (
        expected_paths
    )
    for row in source_rows:
        payload = _read(Path(row["uri"].removeprefix("repo://")))
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()

    generated = {
        Path(row["uri"].removeprefix("repo://")): row
        for row in manifest["generated_artifacts"]
    }
    assert set(generated) == {generator.FIXTURE_PATH, generator.GENERATED_TS_PATH}
    for relative, row in generated.items():
        payload = _read(relative)
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert set(manifest["authority"].values()) == {False}
    assert set(manifest["verification"].values()) == {"NOT_EXECUTED"}


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
            "  ui_dispatch: DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE",
            "  ui_dispatch: ENABLED",
            1,
        ),
        lambda value: value.replace(
            "  unpublish_enabled: false",
            "  unpublish_enabled: true",
            1,
        ),
    ],
)
def test_contract_authority_duplicate_dispatch_and_unpublish_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[str], str],
) -> None:
    original_read = generator._read
    mutated = mutate(_read(generator.CONTRACT_PATH).decode("utf-8")).encode("utf-8")

    def reader(
        root: Path, relative: Path, *, maximum: int = generator.MAX_SOURCE_BYTES
    ) -> bytes:
        if relative == generator.CONTRACT_PATH:
            return mutated
        return original_read(root, relative, maximum=maximum)

    monkeypatch.setattr(generator, "_read", reader)
    with pytest.raises(generator.PublicationReviewGenerationError):
        generator.expected_artifacts()


def test_fixture_closes_sensitive_data_and_all_external_authority() -> None:
    document = json.loads(_read(generator.FIXTURE_PATH))
    assert document["rawPayloadPresent"] is False
    assert document["financeDataPresent"] is False
    assert document["credentialDataPresent"] is False
    assert document["authority"]["backendReauthorizationRequired"] is True
    assert all(
        value is False
        for key, value in document["authority"].items()
        if key != "backendReauthorizationRequired"
    )
    serialized = _read(generator.FIXTURE_PATH).decode("ascii").casefold()
    for forbidden in (
        "access_token",
        "api_key",
        "password",
        "private_key",
        "raw_prompt",
        "affiliate_rate",
        "commission",
        "epc",
        "profit",
        "revenue",
        "rpm",
    ):
        assert forbidden not in serialized


def test_dependency_digest_is_not_an_implementation_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sha = generator._sha

    def digest(root: Path, relative: Path) -> str:
        if relative == generator.DEPENDENCY_BINDINGS[0][0]:
            return "f" * 64
        return original_sha(root, relative)

    monkeypatch.setattr(generator, "_sha", digest)
    assert generator.expected_artifacts()
