"""Positive contract and generated Compose semantics for ST-0201."""

from __future__ import annotations

from typing import Any

import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0201_postgres_service as generator


EXPECTED_REFERENCE = (
    "postgres:18.4-bookworm@sha256:"
    "1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296"
)


def _compose(contract: dict[str, Any]) -> dict[str, Any]:
    value = yaml.safe_load(generator.render_compose(contract))
    assert isinstance(value, dict)
    return value


def test_contract_is_pinned_to_reviewed_sources_and_honest_status(
    postgres_contract: dict[str, Any],
) -> None:
    assert postgres_contract["document"] == generator.EXPECTED_DOCUMENT
    assert {
        row["uri"].removeprefix("repo://"): row["sha256"]
        for row in postgres_contract["sources"]
    } == generator.PINNED_SOURCES
    assert postgres_contract["boundary"] == generator.EXPECTED_BOUNDARY


def test_image_identity_pins_index_platform_manifest_and_config(
    postgres_contract: dict[str, Any],
) -> None:
    image = postgres_contract["image"]
    assert image == generator.EXPECTED_IMAGE
    assert image["reference"] == EXPECTED_REFERENCE
    assert image["tag"] == "18.4-bookworm"
    assert image["platform"] == {
        "os": "linux",
        "architecture": "amd64",
        "manifest_digest": "sha256:16fa100a3a6e92c0556632870455e7f8c6f3df5cefddd67d6b95292732bd7ff0",
        "config_digest": "sha256:0a314d409a9633cff4f89dc18482262625c0ee78cb1aa2ff8e47bc6da0251e1b",
    }
    assert image["expected_environment"] == {
        "PG_VERSION": "18.4-1.pgdg12+1",
        "PGDATA": "/var/lib/postgresql/18/docker",
    }


def test_compose_has_exactly_one_postgres_service(
    postgres_contract: dict[str, Any],
) -> None:
    compose = _compose(postgres_contract)
    assert set(compose) == {"services", "secrets", "volumes", "networks"}
    assert set(compose["services"]) == {"postgres"}
    service = compose["services"]["postgres"]
    assert service["image"] == EXPECTED_REFERENCE
    assert service["platform"] == "linux/amd64"
    assert service["pull_policy"] == "always"
    assert service["init"] is True
    assert service["restart"] == "no"
    assert service["stop_grace_period"] == "30s"
    generator.validate_wrapper_compose_binding(
        REPOSITORY_ROOT, generator.render_compose(postgres_contract)
    )


def test_password_is_only_a_file_backed_compose_secret(
    postgres_contract: dict[str, Any],
) -> None:
    rendered = generator.render_compose(postgres_contract).decode("utf-8")
    compose = yaml.safe_load(rendered)
    service = compose["services"]["postgres"]
    assert service["environment"] == {
        "POSTGRES_DB": "raos",
        "POSTGRES_USER": "raos",
        "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
        "PGDATA": "/var/lib/postgresql/18/docker",
    }
    assert "POSTGRES_PASSWORD:" not in rendered
    assert "POSTGRES_PASSWORD=" not in rendered
    assert compose["secrets"] == {
        "postgres_password": {
            "file": "${RAOS_POSTGRES_PASSWORD_FILE:-.secrets/postgres_password}"
        }
    }
    assert service["secrets"] == [
        {"source": "postgres_password", "target": "postgres_password"}
    ]


def test_data_mount_matches_postgres_18_layout_without_host_bind(
    postgres_contract: dict[str, Any],
) -> None:
    compose = _compose(postgres_contract)
    service = compose["services"]["postgres"]
    assert service["volumes"] == ["postgres_data:/var/lib/postgresql"]
    assert compose["volumes"] == {"postgres_data": None}
    assert service["environment"]["PGDATA"] == "/var/lib/postgresql/18/docker"
    assert all(not row.startswith(("/", "./", "../")) for row in service["volumes"])


def test_network_and_host_publish_are_private_by_default(
    postgres_contract: dict[str, Any],
) -> None:
    compose = _compose(postgres_contract)
    service = compose["services"]["postgres"]
    assert service["ports"] == ["127.0.0.1:${RAOS_POSTGRES_PORT-5432}:5432/tcp"]
    assert service["networks"] == ["postgres_internal"]
    assert compose["networks"] == {
        "postgres_internal": {"driver": "bridge", "internal": True}
    }
    assert "network_mode" not in service
    assert "privileged" not in service
    assert "/var/run/docker.sock" not in generator.render_compose(
        postgres_contract
    ).decode("utf-8")


def test_port_interpolation_supports_documented_ephemeral_host_port_omission(
    postgres_contract: dict[str, Any],
) -> None:
    rendered = generator.render_compose(postgres_contract).decode("utf-8")
    assert "${RAOS_POSTGRES_PORT-5432}" in rendered
    assert "${RAOS_POSTGRES_PORT:-5432}" not in rendered


def test_healthcheck_is_bounded_and_uses_container_environment(
    postgres_contract: dict[str, Any],
) -> None:
    health = _compose(postgres_contract)["services"]["postgres"]["healthcheck"]
    assert health == {
        "test": [
            "CMD-SHELL",
            'pg_isready --username "$$POSTGRES_USER" --dbname "$$POSTGRES_DB" --host 127.0.0.1 --port 5432',
        ],
        "interval": "5s",
        "timeout": "5s",
        "retries": 12,
        "start_period": "10s",
    }


def test_runtime_contract_requires_exact_18_4_not_only_major_version(
    postgres_contract: dict[str, Any],
) -> None:
    runtime = postgres_contract["runtime"]
    assert runtime == generator.EXPECTED_RUNTIME
    assert runtime["expected_server_version_num"] == 180004
    assert runtime["expected_image_config_digest"] == (
        "sha256:0a314d409a9633cff4f89dc18482262625c0ee78cb1aa2ff8e47bc6da0251e1b"
    )
    assert runtime["expected_platform"] == "linux/amd64"
    assert runtime["version_query"] == "SHOW server_version_num;"
    assert runtime["docker_host"] == "unix:///var/run/docker.sock"
    assert runtime["commands"] == ["config", "up", "check", "down", "test"]


def test_security_controls_have_exact_canonical_trace(
    postgres_contract: dict[str, Any],
) -> None:
    controls = postgres_contract["security_controls"]
    assert controls == generator.EXPECTED_SECURITY_CONTROLS
    assert [row["id"] for row in controls] == [
        "SEC-DATA-003",
        "SEC-INFRA-001",
        "SEC-SDLC-003",
        "SEC-SDLC-004",
    ]
    assert controls[-1]["verification"] == "NOT_EXECUTED"


def test_source_pins_match_current_regular_files() -> None:
    for relative, expected_sha256 in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert generator.sha256_file(path) == expected_sha256


def test_architecture_snapshot_is_strictly_parsed_and_hash_pinned() -> None:
    generator._validate_architecture_snapshot(REPOSITORY_ROOT)
    path = REPOSITORY_ROOT / generator.ARCHITECTURE_SNAPSHOT_PATH
    assert generator.sha256_file(path) == (
        generator.EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256
    )


def test_canonical_story_suite_and_security_records_match_exactly() -> None:
    generator._validate_canonical_contracts(REPOSITORY_ROOT)


def test_every_generated_artifact_has_provenance(
    postgres_contract: dict[str, Any],
) -> None:
    compose = generator.render_compose(postgres_contract).decode("utf-8")
    manifest = yaml.safe_load(
        generator.render_outputs(REPOSITORY_ROOT)[generator.MANIFEST_PATH]
    )
    assert generator.SOURCE_CONTRACT_URI in compose
    assert generator.GENERATION_COMMAND in compose
    document = manifest["document"]
    assert document["source_contract"] == generator.SOURCE_CONTRACT_URI
    assert document["generated_by"] == generator.GENERATOR_URI
    assert document["generation_command"] == generator.GENERATION_COMMAND


def test_rendered_compose_contains_no_unreviewed_service_capability(
    postgres_contract: dict[str, Any],
) -> None:
    service = _compose(postgres_contract)["services"]["postgres"]
    forbidden = {
        "build",
        "cap_add",
        "container_name",
        "devices",
        "env_file",
        "external_links",
        "network_mode",
        "pid",
        "privileged",
        "userns_mode",
    }
    assert forbidden.isdisjoint(service)
