"""Fail-closed and adversarial contract tests for ST-0201."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from yaml.constructor import ConstructorError

from conftest import RejectContract
from scripts import build_st0201_postgres_service as generator


def test_yaml_duplicate_mapping_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("image: one\nimage: two\n", encoding="utf-8")
    with pytest.raises(ConstructorError, match="found duplicate key 'image'"):
        generator.load_yaml(path)


@pytest.mark.parametrize(
    "content",
    [
        "shared: &shared\n  value: one\n",
        "shared: &shared\n  value: one\ncopy: *shared\n",
    ],
    ids=["anchor", "alias"],
)
def test_yaml_anchor_or_alias_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "alias.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError, match="anchors and aliases are forbidden"):
        generator.load_yaml(path)


def test_yaml_symlink_input_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    link = tmp_path / "link.yaml"
    target.write_text("value: safe\n", encoding="utf-8")
    link.symlink_to(target)
    with pytest.raises(RuntimeError, match="regular non-symlink file"):
        generator.load_yaml(link)


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.invalid/source",
        "repo://",
        "repo:///absolute",
        "repo://../escape",
        "repo://a/../escape",
        "repo://./source",
        "repo://a//source",
        "repo://a\\source",
    ],
)
def test_untrusted_source_uri_is_rejected(uri: str) -> None:
    with pytest.raises(RuntimeError, match="source uri|unsafe repository source uri"):
        generator._repo_relative_uri(uri)


def test_pinned_source_symlink_is_rejected_even_with_matching_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(b"safe: content\n")
    (repository / "pinned.yaml").symlink_to(outside)
    digest = generator.sha256_file(outside)
    monkeypatch.setattr(generator, "PINNED_SOURCES", {"pinned.yaml": digest})
    contract = {"sources": [{"uri": "repo://pinned.yaml", "sha256": digest}]}
    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator._validate_sources(contract, repository)


def test_repository_file_ancestor_symlink_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    (outside / "source.yaml").write_text("safe: true\n", encoding="utf-8")
    (repository / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="ancestor must be a real directory"):
        generator._repository_regular_file(
            repository, Path("linked/source.yaml"), "source artifact"
        )


def test_unknown_top_level_contract_key_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["unexpected"] = {}
    reject_contract(mutable_contract, "PostgreSQL contract keys differ")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "VALIDATED"),
        ("formal_verification", "PASS"),
        ("story_id", "ST-9999"),
    ],
)
def test_document_identity_or_status_promotion_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
) -> None:
    mutable_contract["document"][field] = value
    reject_contract(mutable_contract, rf"document\.{field} differs")


def test_source_inventory_addition_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["sources"].append({"uri": "repo://README.md", "sha256": "0" * 64})
    reject_contract(mutable_contract, "source inventory differs")


def test_duplicate_source_uri_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["sources"].append(dict(mutable_contract["sources"][0]))
    reject_contract(mutable_contract, "duplicate source uri")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("reference",), "postgres:18.4-bookworm"),
        (("tag",), "latest"),
        (("index_digest",), "sha256:" + "0" * 64),
        (("platform", "architecture"), "arm64"),
        (("platform", "manifest_digest"), "sha256:" + "0" * 64),
        (("platform", "config_digest"), "sha256:" + "0" * 64),
        (("expected_environment", "PG_VERSION"), "18.3"),
        (("expected_environment", "PGDATA"), "/var/lib/postgresql/data"),
    ],
)
def test_image_pin_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    path: tuple[str, ...],
    value: str,
) -> None:
    target = mutable_contract["image"]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    reject_contract(mutable_contract, r"image\.")


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("service", "init", False),
        ("service", "restart", "always"),
        ("service", "stop_grace_period", "1s"),
        ("port", "host_ip", "0.0.0.0"),
        ("port", "default", 5433),
        ("password_secret", "source_variable", "POSTGRES_PASSWORD"),
        ("password_secret", "mount_path", "/tmp/password"),
        ("data", "mount_path", "/host/data"),
        ("data", "pgdata", "/var/lib/postgresql/data"),
        ("network", "internal", False),
        ("network", "driver", "host"),
        ("healthcheck", "interval", "60s"),
        ("healthcheck", "retries", 1),
    ],
)
def test_compose_security_or_health_field_cannot_drift(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    section: str,
    field: str,
    value: object,
) -> None:
    mutable_contract["compose"][section][field] = value
    reject_contract(mutable_contract, rf"compose\.{section}\.{field}")


def test_unknown_privileged_field_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["compose"]["service"]["privileged"] = True
    reject_contract(mutable_contract, "compose.service keys differ")


def test_bool_as_integer_does_not_bypass_strict_comparison(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["compose"]["service"]["init"] = 1
    reject_contract(mutable_contract, "compose.service.init type differs")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("docker_host", "tcp://127.0.0.1:2375"),
        ("expected_server_version_num", 180000),
        ("disposable_pull_policy", "missing"),
        ("local_project", "default"),
        ("commands", ["up", "down"]),
    ],
)
def test_runtime_contract_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: object,
) -> None:
    mutable_contract["runtime"][field] = value
    reject_contract(mutable_contract, rf"runtime\.{field}")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_use", "ALLOWED"),
        ("remote_database", "ALLOWED"),
        ("raw_password_environment", "ALLOWED"),
        ("docker_runtime", "PASS"),
        ("container_vulnerability_scan", "PASS"),
        ("formal_tst_008", "PASS"),
        ("effective_canonical_status", "VALIDATED"),
    ],
)
def test_boundary_cannot_be_promoted_locally(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
) -> None:
    mutable_contract["boundary"][field] = value
    reject_contract(mutable_contract, rf"boundary\.{field}")


def test_security_control_inventory_cannot_be_reduced(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["security_controls"].pop()
    reject_contract(mutable_contract, "security_controls length differs")


def test_architecture_snapshot_hash_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    snapshot = repository / generator.ARCHITECTURE_SNAPSHOT_PATH
    snapshot.parent.mkdir(parents=True)
    source = generator.REPO_ROOT / generator.ARCHITECTURE_SNAPSHOT_PATH
    snapshot.write_bytes(source.read_bytes() + b"# drift\n")
    with pytest.raises(RuntimeError, match="architecture snapshot hash mismatch"):
        generator._validate_architecture_snapshot(repository)
