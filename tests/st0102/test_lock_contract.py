"""Supply-chain and freshness checks for the generated ``uv.lock``."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit

from test_toolchain_contract import (
    DIRECT_DEV_PINS,
    DIRECT_RUNTIME_PINS,
    PYTHON_VERSION,
)


PYPI_REGISTRY = "https://pypi.org/simple"
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_lock_format_runtime_and_resolution_cutoff_match_project(
    lock_config: dict[str, Any],
    project_config: dict[str, Any],
    uv_config: dict[str, Any],
) -> None:
    assert lock_config["version"] == 1
    assert lock_config["revision"] == 3
    assert lock_config["requires-python"] == f"=={PYTHON_VERSION}"
    assert (
        lock_config["requires-python"] == project_config["project"]["requires-python"]
    )
    assert lock_config["options"] == {
        "exclude-newer": uv_config["exclude-newer"],
        "prerelease-mode": uv_config["prerelease"],
    }


def test_lock_has_one_virtual_root_and_only_the_pypi_registry(
    lock_config: dict[str, Any],
) -> None:
    packages = lock_config["package"]
    roots = [package for package in packages if "virtual" in package["source"]]
    assert len(roots) == 1
    assert roots[0]["name"] == "raos"
    assert roots[0]["version"] == "0.0.0"
    assert roots[0]["source"] == {"virtual": "."}

    names: set[str] = set()
    for package in packages:
        assert package["name"] not in names
        names.add(package["name"])
        if package is roots[0]:
            continue
        assert package["source"] == {"registry": PYPI_REGISTRY}


def test_every_registry_artifact_is_https_hash_bearing_and_before_cutoff(
    lock_config: dict[str, Any],
) -> None:
    cutoff = timestamp(lock_config["options"]["exclude-newer"])
    registry_packages = [
        package
        for package in lock_config["package"]
        if package["source"] == {"registry": PYPI_REGISTRY}
    ]
    assert registry_packages

    for package in registry_packages:
        artifacts = [package.get("sdist"), *package.get("wheels", [])]
        artifacts = [artifact for artifact in artifacts if artifact is not None]
        assert artifacts, package["name"]
        for artifact in artifacts:
            parsed_url = urlsplit(artifact["url"])
            assert parsed_url.scheme == "https"
            assert parsed_url.hostname == "files.pythonhosted.org"
            assert HASH_PATTERN.fullmatch(artifact["hash"])
            assert artifact["size"] > 0
            assert timestamp(artifact["upload-time"]) <= cutoff


def test_direct_pin_metadata_and_locked_versions_are_identical(
    lock_config: dict[str, Any],
) -> None:
    packages = {package["name"]: package for package in lock_config["package"]}
    root = packages["raos"]
    locked_direct = {
        requirement["name"]: requirement["specifier"].removeprefix("==")
        for requirement in root["metadata"]["requires-dev"]["dev"]
    }
    assert locked_direct == DIRECT_DEV_PINS
    assert {
        name: packages[name]["version"] for name in DIRECT_DEV_PINS
    } == DIRECT_DEV_PINS
    locked_runtime = {
        requirement["name"]: requirement["specifier"].removeprefix("==")
        for requirement in root["metadata"]["requires-dist"]
    }
    assert locked_runtime == DIRECT_RUNTIME_PINS
    assert {
        name: packages[name]["version"] for name in DIRECT_RUNTIME_PINS
    } == DIRECT_RUNTIME_PINS


def test_every_dependency_reference_resolves_to_a_locked_package(
    lock_config: dict[str, Any],
) -> None:
    locked_names = {package["name"] for package in lock_config["package"]}
    for package in lock_config["package"]:
        for dependency in package.get("dependencies", []):
            assert dependency["name"] in locked_names


def test_lock_contains_no_untrusted_source_or_artifact_shape(
    lock_config: dict[str, Any],
) -> None:
    serialized_sources = [package["source"] for package in lock_config["package"]]
    forbidden_keys = {"editable", "git", "path", "url"}
    assert not any(forbidden_keys.intersection(source) for source in serialized_sources)
