"""Static contract checks for the pinned ST-0102 Python toolchain."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from conftest import REPOSITORY_ROOT


PYTHON_VERSION = "3.14.6"
DIRECT_DEV_PINS = {
    "datamodel-code-generator": "0.71.0",
    "jsonschema": "4.26.0",
    "mypy": "2.3.0",
    "pytest": "9.1.1",
    "pyyaml": "6.0.3",
    "referencing": "0.37.0",
    "ruff": "0.16.1",
    "types-pyyaml": "6.0.12.20260724",
}
DIRECT_RUNTIME_PINS = {"pydantic": "2.13.4"}
UV_SETTINGS = {
    "exclude-newer": "2026-08-01T16:50:16Z",
    "index-strategy": "first-index",
    "keyring-provider": "disabled",
    "link-mode": "copy",
    "no-sources": True,
    "prerelease": "disallow",
    "python-downloads": "manual",
    "python-preference": "only-managed",
    "required-version": "==0.12.1",
    "resolution": "highest",
}


def parse_exact_pins(requirements: list[str]) -> dict[str, str]:
    """Return normalized name/version pairs from exact direct requirements."""

    pins: dict[str, str] = {}
    for requirement in requirements:
        assert requirement.count("==") == 1, requirement
        name, version = requirement.split("==")
        normalized_name = name.lower().replace("_", "-")
        assert normalized_name not in pins
        assert name == normalized_name
        assert version
        pins[normalized_name] = version
    return pins


def test_suite_runs_on_the_exact_managed_python() -> None:
    assert sys.version_info[:3] == (3, 14, 6)
    assert sys.implementation.name == "cpython"


def test_python_version_file_and_project_requirement_are_exact(
    project_config: dict[str, Any],
) -> None:
    version_file = (REPOSITORY_ROOT / ".python-version").read_text(encoding="utf-8")
    assert version_file == f"{PYTHON_VERSION}\n"
    assert project_config["project"]["requires-python"] == f"=={PYTHON_VERSION}"


def test_project_remains_non_packaged_with_exact_owned_runtime_dependencies(
    project_config: dict[str, Any],
) -> None:
    project = project_config["project"]
    assert project["name"] == "raos"
    assert project["version"] == "0.0.0"
    assert parse_exact_pins(project["dependencies"]) == DIRECT_RUNTIME_PINS
    assert project_config["tool"]["uv"] == {
        "package": False,
        "default-groups": ["dev"],
    }
    assert "build-system" not in project_config


def test_every_direct_development_dependency_is_exactly_pinned(
    project_config: dict[str, Any],
) -> None:
    assert set(project_config["dependency-groups"]) == {"dev"}
    assert parse_exact_pins(project_config["dependency-groups"]["dev"]) == (
        DIRECT_DEV_PINS
    )


def test_uv_resolution_and_source_settings_fail_closed(
    uv_config: dict[str, Any],
) -> None:
    assert set(uv_config) == set(UV_SETTINGS) | {"index"}
    for name, expected in UV_SETTINGS.items():
        assert uv_config[name] == expected
    assert "sources" not in uv_config

    assert uv_config["index"] == [
        {
            "name": "pypi",
            "url": "https://pypi.org/simple",
            "default": True,
        }
    ]


def test_ruff_is_exact_and_targets_only_python_314(
    project_config: dict[str, Any],
) -> None:
    ruff = project_config["tool"]["ruff"]
    assert ruff["required-version"] == "==0.16.1"
    assert ruff["target-version"] == "py314"
    assert ruff["line-length"] == 88
    assert ruff["preview"] is False
    assert ruff["lint"] == {"select": ["E4", "E7", "E9", "F"]}
    assert ruff["format"] == {
        "docstring-code-format": False,
        "preview": False,
    }


def test_mypy_is_strict_and_scoped_to_production_python(
    project_config: dict[str, Any],
) -> None:
    mypy = project_config["tool"]["mypy"]
    assert mypy == {
        "exclude": ["^python/raos/generated/"],
        "files": ["python/raos"],
        "mypy_path": "python",
        "pretty": True,
        "python_version": "3.14",
        "show_error_codes": True,
        "strict": True,
        "warn_unreachable": True,
    }


def test_pytest_requires_the_pin_and_disables_ambient_plugins(
    project_config: dict[str, Any],
) -> None:
    pytest_config = project_config["tool"]["pytest"]["ini_options"]
    assert pytest_config["minversion"] == "9.1.1"
    assert pytest_config["addopts"] == [
        "-ra",
        "--strict-config",
        "--strict-markers",
        "--disable-plugin-autoload",
    ]
    assert "testpaths" not in pytest_config


def test_required_contract_files_are_regular_files() -> None:
    for relative in (".python-version", "pyproject.toml", "uv.toml", "uv.lock"):
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert Path(path).stat().st_size > 0
