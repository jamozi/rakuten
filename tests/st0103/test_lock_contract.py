"""Supply-chain, provenance, and freshness checks for package-lock v3."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from test_toolchain_contract import (
    DEPENDENCY_SECTIONS,
    EXPECTED_DIRECT_PINS,
    EXPECTED_OVERRIDES,
    EXPECTED_WORKSPACES,
    dependency_pins,
)


NPM_REGISTRY = "https://registry.npmjs.org/"
WORKSPACE_PATHS = {"apps/web", "packages/web-contracts", "packages/web-ui"}
FORBIDDEN_SPECIFIER_PREFIXES = (
    "file:",
    "git:",
    "git+",
    "github:",
    "http:",
    "https:",
    "link:",
    "npm:",
    "workspace:",
)


def lock_packages(package_lock: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    packages = package_lock["packages"]
    assert isinstance(packages, dict)
    assert all(
        isinstance(path, str) and isinstance(value, dict)
        for path, value in packages.items()
    )
    return packages


def test_lock_is_v3_and_identifies_the_same_private_workspace(
    package_lock: dict[str, Any],
    package_manifest: dict[str, Any],
) -> None:
    assert package_lock["name"] == package_manifest["name"]
    assert package_lock["version"] == package_manifest["version"]
    assert package_lock["lockfileVersion"] == 3
    assert package_lock["requires"] is True
    assert set(package_lock) == {
        "name",
        "version",
        "lockfileVersion",
        "requires",
        "packages",
    }

    root = lock_packages(package_lock)[""]
    for key in (
        "name",
        "version",
        "license",
        "workspaces",
        "engines",
        "devDependencies",
    ):
        assert root[key] == package_manifest[key]
    assert "devEngines" not in root


def test_lock_contains_only_the_allowlisted_workspace_links(
    package_lock: dict[str, Any],
) -> None:
    packages = lock_packages(package_lock)
    assert set(EXPECTED_WORKSPACES) == WORKSPACE_PATHS
    assert WORKSPACE_PATHS.issubset(packages)

    links = {
        path: metadata["resolved"]
        for path, metadata in packages.items()
        if metadata.get("link") is True
    }
    assert set(links.values()) == WORKSPACE_PATHS
    assert all(path.startswith("node_modules/") for path in links)
    assert all(set(packages[path]) == {"resolved", "link"} for path in links)


def test_every_external_lock_entry_is_registry_only_and_integrity_bearing(
    package_lock: dict[str, Any],
) -> None:
    packages = lock_packages(package_lock)
    external = {
        path: metadata
        for path, metadata in packages.items()
        if path.startswith("node_modules/") and metadata.get("link") is not True
    }
    assert external

    for path, metadata in external.items():
        resolved = metadata.get("resolved")
        integrity = metadata.get("integrity")
        assert isinstance(resolved, str), path
        parsed = urlsplit(resolved)
        assert parsed.scheme == "https", path
        assert parsed.hostname == "registry.npmjs.org", path
        assert parsed.username is None and parsed.password is None, path
        assert parsed.query == "" and parsed.fragment == "", path
        assert isinstance(integrity, str), path
        algorithms = integrity.split()
        assert algorithms, path
        for value in algorithms:
            algorithm, encoded = value.split("-", 1)
            assert algorithm == "sha512", path
            digest = base64.b64decode(encoded, validate=True)
            assert len(digest) == 64, path


def test_lock_contains_no_git_file_remote_alias_or_floating_direct_pin(
    package_lock: dict[str, Any],
    package_manifest: dict[str, Any],
    web_manifest: dict[str, Any],
    web_contracts_manifest: dict[str, Any],
    web_ui_manifest: dict[str, Any],
) -> None:
    for manifest in (
        package_manifest,
        web_manifest,
        web_contracts_manifest,
        web_ui_manifest,
    ):
        for section in DEPENDENCY_SECTIONS:
            dependencies = manifest.get(section, {})
            assert isinstance(dependencies, dict)
            for name, specifier in dependencies.items():
                assert isinstance(specifier, str), name
                assert not specifier.startswith(FORBIDDEN_SPECIFIER_PREFIXES), name
                assert not any(character in specifier for character in "*^~<>=| "), name

    for path, metadata in lock_packages(package_lock).items():
        if path == "" or path in WORKSPACE_PATHS or metadata.get("link") is True:
            continue
        resolved = metadata.get("resolved", "")
        assert isinstance(resolved, str), path
        assert resolved.startswith(NPM_REGISTRY), path
        assert not any(
            key in metadata
            for key in ("from", "inBundle", "resolvedGit", "resolvedFile")
        ), path


def test_direct_manifest_pins_and_locked_versions_are_identical(
    package_lock: dict[str, Any],
    package_manifest: dict[str, Any],
    web_manifest: dict[str, Any],
    web_contracts_manifest: dict[str, Any],
    web_ui_manifest: dict[str, Any],
) -> None:
    declared: dict[str, str] = {}
    for manifest in (
        package_manifest,
        web_manifest,
        web_contracts_manifest,
        web_ui_manifest,
    ):
        declared.update(dependency_pins(manifest))
    assert declared == EXPECTED_DIRECT_PINS

    packages = lock_packages(package_lock)
    assert {
        name: packages[f"node_modules/{name}"]["version"] for name in declared
    } == declared


def test_security_overrides_replace_every_vulnerable_lock_entry(
    package_lock: dict[str, Any],
    package_manifest: dict[str, Any],
) -> None:
    assert package_manifest["overrides"] == EXPECTED_OVERRIDES
    packages = lock_packages(package_lock)
    postcss = {
        path: metadata
        for path, metadata in packages.items()
        if path.rsplit("node_modules/", 1)[-1] == "postcss"
    }
    sharp = {
        path: metadata
        for path, metadata in packages.items()
        if path.rsplit("node_modules/", 1)[-1] == "sharp"
    }
    assert postcss == {"node_modules/postcss": postcss["node_modules/postcss"]}
    assert sharp == {"node_modules/sharp": sharp["node_modules/sharp"]}
    assert {metadata["version"] for metadata in postcss.values()} == {"8.5.25"}
    assert {metadata["version"] for metadata in sharp.values()} == {"0.35.3"}
    for path, metadata in {**postcss, **sharp}.items():
        assert metadata["resolved"].startswith(NPM_REGISTRY), path
        assert metadata["integrity"].startswith("sha512-"), path


def test_lock_workspace_metadata_matches_each_source_manifest(
    package_lock: dict[str, Any],
    web_manifest: dict[str, Any],
    web_contracts_manifest: dict[str, Any],
    web_ui_manifest: dict[str, Any],
) -> None:
    packages = lock_packages(package_lock)
    for path, manifest in (
        ("apps/web", web_manifest),
        ("packages/web-contracts", web_contracts_manifest),
        ("packages/web-ui", web_ui_manifest),
    ):
        locked = packages[path]
        for key in ("name", "version"):
            assert locked[key] == manifest[key]
        for section in DEPENDENCY_SECTIONS:
            if section in manifest:
                assert locked[section] == manifest[section]


def test_every_locked_dependency_reference_has_a_package_entry(
    package_lock: dict[str, Any],
) -> None:
    packages = lock_packages(package_lock)
    locked_names = {
        path.rsplit("node_modules/", 1)[-1]
        for path in packages
        if "node_modules/" in path
    }
    for path, metadata in packages.items():
        for section in ("dependencies", "optionalDependencies", "peerDependencies"):
            dependencies = metadata.get(section, {})
            assert isinstance(dependencies, dict), f"{path}:{section}"
            for name in dependencies:
                if section == "peerDependencies":
                    peer_meta = metadata.get("peerDependenciesMeta", {})
                    assert isinstance(peer_meta, dict), path
                    settings = peer_meta.get(name, {})
                    assert isinstance(settings, dict), f"{path}:{name}"
                    if settings.get("optional") is True:
                        continue
                assert name in locked_names, f"unresolved {name} from {path}"
