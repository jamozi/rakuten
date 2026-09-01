from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_wordpress_deployment_operator.py"
SPEC = importlib.util.spec_from_file_location(
    "raos_wordpress_deployment_operator", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def package(entries: list[tuple[str, bytes, int | None]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload, mode in entries:
            info = zipfile.ZipInfo(name, (2026, 8, 29, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (
                (stat.S_IFREG | 0o644) if mode is None else mode
            ) << 16
            archive.writestr(info, payload)
    return output.getvalue()


def plugin_php(version: str = "1.2.3", body: bytes = b"") -> bytes:
    return (
        b"<?php\n/*\nPlugin Name: Safe Test Plugin\nVersion: "
        + version.encode()
        + b"\nRequires at least: 7.1\nRequires PHP: 8.1\n*/\n"
        + body
    )


def validate(payload: bytes, version: str = "1.2.3"):
    return operator.validate_package(
        payload, kind="plugin", slug="safe-plugin", expected_version=version
    )


def assert_code(code: str, callable_) -> None:
    with pytest.raises(operator.OperatorFailure) as raised:
        callable_()
    assert str(raised.value) == code


def test_package_manifest_and_digest_are_deterministic() -> None:
    payload = package(
        [
            ("safe-plugin/safe-plugin.php", plugin_php(), None),
            ("safe-plugin/readme.txt", b"safe\n", None),
        ]
    )
    first = validate(payload)
    second = validate(payload)
    assert first == second
    manifest, digest, version, migration_safe = first
    assert [entry["path"] for entry in manifest] == ["readme.txt", "safe-plugin.php"]
    assert len(digest) == 64
    assert version == "1.2.3"
    assert migration_safe is True


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        ("safe-plugin/../escape.php", "WORDPRESS_MCP_ZIP_PATH_INVALID"),
        ("../safe-plugin/safe.php", "WORDPRESS_MCP_ZIP_PATH_INVALID"),
        ("/safe-plugin/safe.php", "WORDPRESS_MCP_ZIP_PATH_INVALID"),
        ("safe-plugin\\safe.php", "WORDPRESS_MCP_ZIP_PATH_INVALID"),
    ],
)
def test_zip_traversal_and_noncanonical_paths_are_refused(
    entry: str, code: str
) -> None:
    payload = package([(entry, plugin_php(), None)])
    assert_code(code, lambda: validate(payload))


def test_symlink_is_refused() -> None:
    payload = package(
        [
            ("safe-plugin/safe-plugin.php", plugin_php(), None),
            ("safe-plugin/link", b"target", stat.S_IFLNK | 0o777),
        ]
    )
    assert_code("WORDPRESS_MCP_ZIP_SYMLINK_REFUSED", lambda: validate(payload))


def test_case_collision_is_refused() -> None:
    payload = package(
        [
            ("safe-plugin/safe-plugin.php", plugin_php(), None),
            ("safe-plugin/Readme.txt", b"one", None),
            ("safe-plugin/readme.txt", b"two", None),
        ]
    )
    assert_code("WORDPRESS_MCP_ZIP_CASE_COLLISION", lambda: validate(payload))


def test_special_files_are_refused() -> None:
    payload = package(
        [
            ("safe-plugin/safe-plugin.php", plugin_php(), None),
            ("safe-plugin/device", b"device", stat.S_IFCHR | 0o600),
        ]
    )
    assert_code("WORDPRESS_MCP_ZIP_SPECIAL_FILE_REFUSED", lambda: validate(payload))


def test_multiple_plugin_headers_are_refused() -> None:
    payload = package(
        [
            ("safe-plugin/safe-plugin.php", plugin_php(), None),
            ("safe-plugin/second.php", plugin_php(), None),
        ]
    )
    assert_code("WORDPRESS_MCP_PACKAGE_HEADER_MISSING", lambda: validate(payload))


def test_version_mismatch_is_refused() -> None:
    payload = package([("safe-plugin/safe-plugin.php", plugin_php("1.2.4"), None)])
    assert_code("WORDPRESS_MCP_PACKAGE_VERSION_MISMATCH", lambda: validate(payload))


@pytest.mark.parametrize(
    "signal",
    [
        b"register_activation_hook(__FILE__, 'install');",
        b"dbDelta($sql);",
        b"$wpdb->query($sql);",
        b"update_option('schema', 2);",
        b"ALTER TABLE example ADD value INT;",
        b"function run_migration() {}",
    ],
)
def test_irreversible_or_unknown_migration_signals_require_manual_review(
    signal: bytes,
) -> None:
    payload = package([("safe-plugin/safe-plugin.php", plugin_php(body=signal), None)])
    *_, migration_safe = validate(payload)
    assert migration_safe is False


def test_theme_package_is_reproducible_from_the_tracked_child_theme() -> None:
    first_payload, first_descriptor = operator.theme_package()
    second_payload, second_descriptor = operator.theme_package()
    assert first_payload == second_payload
    assert first_descriptor == second_descriptor
    assert first_descriptor["slug"] == "kurashinoshirube-child"
    assert first_descriptor["source"] == "tracked_child_theme"
    assert first_descriptor["automatic_apply_eligible"] is True


def test_cli_refuses_unknown_fields_before_credentials_or_transport() -> None:
    result = operator.run
    with pytest.raises(operator.OperatorFailure) as raised:
        result("deployment-status", {"url": "https://x"})
    assert str(raised.value) == "WORDPRESS_MCP_INPUT_INVALID"


def test_arbitrary_plugin_source_is_refused() -> None:
    with pytest.raises(operator.OperatorFailure) as raised:
        operator.plugin_package(
            {
                "source": "https_url",
                "slug": "safe-plugin",
                "version": "1.2.3",
                "activation_intent": "preserve",
            }
        )
    assert str(raised.value) == "WORDPRESS_MCP_PLUGIN_SOURCE_REFUSED"


def test_repo_artifact_digest_mismatch_is_refused(tmp_path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    os.chmod(artifacts, 0o700)
    package_path = artifacts / "safe-artifact.zip"
    package_path.write_bytes(b"not-the-registered-package")
    os.chmod(package_path, 0o600)
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "RAOS_WORDPRESS_REPO_PLUGIN_ARTIFACTS_V1",
                "artifacts": [
                    {
                        "artifact_id": "safe-artifact",
                        "slug": "safe-plugin",
                        "version": "1.2.3",
                        "package_sha256": "0" * 64,
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(operator, "ARTIFACT_REGISTRY", registry)
    monkeypatch.setattr(operator, "REPO_ARTIFACT_DIRECTORY", artifacts)
    monkeypatch.setattr(
        operator, "_secure_regular_file", lambda path, maximum: path.read_bytes()
    )
    assert_code(
        "WORDPRESS_MCP_ARTIFACT_DIGEST_MISMATCH",
        lambda: operator._repo_artifact("safe-artifact", "safe-plugin", "1.2.3"),
    )


def _reviewed_migration_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    review_mutation: tuple[str, object] | None = None,
) -> dict[str, object]:
    payload = package(
        [
            (
                "safe-plugin/safe-plugin.php",
                plugin_php(body=b"register_activation_hook(__FILE__, 'install');"),
                None,
            )
        ]
    )
    manifest, manifest_sha256, _, migration_safe = validate(payload)
    assert migration_safe is False
    package_sha256 = __import__("hashlib").sha256(payload).hexdigest()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    os.chmod(artifacts, 0o700)
    package_path = artifacts / "reviewed-artifact.zip"
    package_path.write_bytes(payload)
    os.chmod(package_path, 0o600)
    review: dict[str, object] = {
        "schema": "RAOS_WORDPRESS_PLUGIN_MIGRATION_REVIEW_V1",
        "assessment": operator.REVIEWED_MIGRATION_ASSESSMENT,
        "package_sha256": package_sha256,
        "file_manifest_sha256": manifest_sha256,
    }
    if review_mutation is not None:
        review[review_mutation[0]] = review_mutation[1]
    binding = {
        "artifact_id": "reviewed-artifact",
        "slug": "safe-plugin",
        "version": "1.2.3",
        "package_sha256": package_sha256,
        "migration_review": review,
    }
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "RAOS_WORDPRESS_REPO_PLUGIN_ARTIFACTS_V1",
                "artifacts": [binding],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(operator, "ARTIFACT_REGISTRY", registry)
    monkeypatch.setattr(operator, "REPO_ARTIFACT_DIRECTORY", artifacts)
    monkeypatch.setattr(
        operator,
        "REVIEWED_MIGRATION_BINDINGS",
        {
            "reviewed-artifact": {
                "slug": "safe-plugin",
                "version": "1.2.3",
                "package_sha256": package_sha256,
                "file_manifest_sha256": manifest_sha256,
            }
        },
    )
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "package_sha256": package_sha256,
    }


def test_only_exact_registered_reviewed_migration_becomes_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = _reviewed_migration_artifact(tmp_path, monkeypatch)
    _, descriptor = operator.plugin_package(
        {
            "source": "repo_artifact",
            "artifact_id": "reviewed-artifact",
            "slug": "safe-plugin",
            "version": "1.2.3",
            "activation_intent": "activate",
        }
    )
    assert descriptor["migration_assessment"] == (
        "REVIEWED_PLUGIN_OWNED_ACTIVATION_MIGRATION"
    )
    assert descriptor["automatic_apply_eligible"] is True
    assert descriptor["package_sha256"] == expected["package_sha256"]
    assert descriptor["file_manifest_sha256"] == expected["manifest_sha256"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assessment", "MANUAL_REVIEW_REQUIRED"),
        ("package_sha256", "0" * 64),
        ("file_manifest_sha256", "1" * 64),
        ("unexpected_bypass", True),
    ],
)
def test_reviewed_migration_tamper_remains_manual_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    _reviewed_migration_artifact(
        tmp_path,
        monkeypatch,
        review_mutation=(field, value),
    )
    _, descriptor = operator.plugin_package(
        {
            "source": "repo_artifact",
            "artifact_id": "reviewed-artifact",
            "slug": "safe-plugin",
            "version": "1.2.3",
            "activation_intent": "activate",
        }
    )
    assert descriptor["migration_assessment"] == "MANUAL_REVIEW_REQUIRED"
    assert descriptor["automatic_apply_eligible"] is False


@pytest.mark.parametrize("activation_intent", ["preserve", "deactivate"])
def test_reviewed_migration_requires_exact_activate_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    activation_intent: str,
) -> None:
    _reviewed_migration_artifact(tmp_path, monkeypatch)
    _, descriptor = operator.plugin_package(
        {
            "source": "repo_artifact",
            "artifact_id": "reviewed-artifact",
            "slug": "safe-plugin",
            "version": "1.2.3",
            "activation_intent": activation_intent,
        }
    )
    assert descriptor["migration_assessment"] == "MANUAL_REVIEW_REQUIRED"
    assert descriptor["automatic_apply_eligible"] is False
