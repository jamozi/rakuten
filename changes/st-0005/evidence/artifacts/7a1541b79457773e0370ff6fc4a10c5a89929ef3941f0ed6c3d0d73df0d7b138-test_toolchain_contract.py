"""Static contract checks for the pinned ST-0103 Node toolchain."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any

from conftest import EXPECTED_NODE_VERSION, EXPECTED_NPM_VERSION, REPOSITORY_ROOT


EXPECTED_WORKSPACES = ["apps/web", "packages/web-ui"]
EXPECTED_DIRECT_PINS = {
    "@types/node": "24.13.3",
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.4",
    "eslint": "9.39.5",
    "eslint-config-next": "16.2.12",
    "next": "16.2.12",
    "prettier": "3.9.6",
    "pyright": "1.1.411",
    "react": "19.2.8",
    "react-dom": "19.2.8",
    "typescript": "6.0.3",
    "vite": "8.2.0",
    "vitest": "4.1.10",
}
EXPECTED_OVERRIDES = {
    "next@16.2.12": {
        "postcss": "8.5.25",
        "sharp": "0.35.3",
    },
    "vite": "8.2.0",
}
DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def load_json(relative: str) -> dict[str, Any]:
    value = json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def dependency_pins(manifest: Mapping[str, Any]) -> dict[str, str]:
    """Return every direct external dependency declared by a manifest."""

    pins: dict[str, str] = {}
    for section in DEPENDENCY_SECTIONS:
        dependencies = manifest.get(section, {})
        assert isinstance(dependencies, dict), section
        for name, version in dependencies.items():
            assert isinstance(name, str)
            assert isinstance(version, str)
            assert name not in pins, f"duplicate direct dependency: {name}"
            pins[name] = version
    return pins


def test_node_and_package_manager_pins_are_exact(
    package_manifest: dict[str, Any],
) -> None:
    assert (REPOSITORY_ROOT / ".node-version").read_text(
        encoding="utf-8"
    ) == f"{EXPECTED_NODE_VERSION}\n"
    assert package_manifest["packageManager"] == f"npm@{EXPECTED_NPM_VERSION}"
    assert package_manifest["engines"] == {
        "node": EXPECTED_NODE_VERSION,
        "npm": EXPECTED_NPM_VERSION,
    }
    assert package_manifest["devEngines"] == {
        "runtime": {
            "name": "node",
            "version": EXPECTED_NODE_VERSION,
            "onFail": "error",
        },
        "packageManager": {
            "name": "npm",
            "version": EXPECTED_NPM_VERSION,
            "onFail": "error",
        },
    }


def test_root_is_a_private_exactly_scoped_workspace(
    package_manifest: dict[str, Any],
) -> None:
    assert package_manifest["name"] == "raos"
    assert package_manifest["version"] == "0.0.0"
    assert package_manifest["private"] is True
    assert package_manifest["license"] == "UNLICENSED"
    assert package_manifest["workspaces"] == EXPECTED_WORKSPACES
    assert set(package_manifest).isdisjoint(
        {"publishConfig", "repository", "bugs", "homepage"}
    )


def test_only_the_owned_web_boundaries_are_activated_as_workspaces(
    web_manifest: dict[str, Any],
    web_ui_manifest: dict[str, Any],
) -> None:
    assert web_manifest["name"] == "@raos/web"
    assert web_manifest["version"] == "0.0.0"
    assert web_manifest["private"] is True
    assert web_ui_manifest["name"] == "@raos/web-ui"
    assert web_ui_manifest["version"] == "0.0.0"
    assert web_ui_manifest["private"] is True
    assert set(web_ui_manifest).isdisjoint(
        {*DEPENDENCY_SECTIONS, "scripts", "exports", "main", "types"}
    )
    for relative in (
        "apps/web/app",
        "apps/web/pages",
        "apps/web/next.config.js",
        "apps/web/next.config.mjs",
        "apps/web/next.config.ts",
    ):
        assert not (REPOSITORY_ROOT / relative).exists()


def test_every_direct_external_dependency_is_an_exact_approved_pin(
    package_manifest: dict[str, Any],
    web_manifest: dict[str, Any],
    web_ui_manifest: dict[str, Any],
) -> None:
    combined: dict[str, str] = {}
    for manifest in (package_manifest, web_manifest, web_ui_manifest):
        for name, version in dependency_pins(manifest).items():
            assert name not in combined, (
                f"pin is owned by more than one manifest: {name}"
            )
            combined[name] = version
    assert combined == EXPECTED_DIRECT_PINS
    assert all(EXACT_VERSION.fullmatch(version) for version in combined.values())


def test_security_overrides_are_an_exact_closed_allowlist(
    package_manifest: dict[str, Any],
) -> None:
    assert package_manifest["overrides"] == EXPECTED_OVERRIDES
    assert EXACT_VERSION.fullmatch(package_manifest["overrides"]["vite"])
    assert all(
        EXACT_VERSION.fullmatch(version)
        for version in package_manifest["overrides"]["next@16.2.12"].values()
    )


def test_root_scripts_are_fixed_non_mutating_verification_commands(
    package_manifest: dict[str, Any],
) -> None:
    scripts = package_manifest["scripts"]
    assert set(scripts) == {
        "format:check",
        "lint",
        "typecheck",
        "pyright",
        "test:unit",
        "check",
    }
    serialized = "\n".join(scripts.values())
    assert "npx" not in serialized
    assert "corepack" not in serialized
    assert "npm install" not in serialized
    assert "npm ci" not in serialized
    assert "|| true" not in serialized
    assert "prettier" in scripts["format:check"]
    assert "--check" in scripts["format:check"]
    assert "eslint" in scripts["lint"]
    assert "--max-warnings=0" in scripts["lint"]
    assert "tsc" in scripts["typecheck"]
    assert "--noEmit" in scripts["typecheck"] or "noEmit" in (
        REPOSITORY_ROOT / "tsconfig.base.json"
    ).read_text(encoding="utf-8")
    assert "pyright" in scripts["pyright"]
    assert "vitest run" in scripts["test:unit"]
    assert "--configLoader native" in scripts["test:unit"]
    assert "--passWithNoTests" not in scripts["test:unit"]


def test_typescript_configuration_is_strict_and_story_scoped() -> None:
    base = load_json("tsconfig.base.json")
    root = load_json("tsconfig.json")
    options = base["compilerOptions"]
    assert options["strict"] is True
    assert options["noEmit"] is True
    assert options["noUncheckedIndexedAccess"] is True
    assert options["exactOptionalPropertyTypes"] is True
    assert options["noImplicitOverride"] is True
    assert options["noFallthroughCasesInSwitch"] is True
    assert options["forceConsistentCasingInFileNames"] is True
    assert options["isolatedModules"] is True
    assert options["moduleResolution"] == "Bundler"
    assert root["extends"] == "./tsconfig.base.json"
    serialized_includes = "\n".join(root["include"])
    assert "tests/st0103" in serialized_includes
    assert "apps/web" not in serialized_includes
    assert "packages/web-ui" not in serialized_includes


def test_lint_format_pyright_and_vitest_configs_are_explicit() -> None:
    eslint = (REPOSITORY_ROOT / "eslint.config.mjs").read_text(encoding="utf-8")
    prettier = (REPOSITORY_ROOT / "prettier.config.mjs").read_text(encoding="utf-8")
    pyright = load_json("pyrightconfig.json")
    vitest = (REPOSITORY_ROOT / "vitest.config.ts").read_text(encoding="utf-8")

    assert "eslint-config-next/core-web-vitals" in eslint
    assert "eslint-config-next/typescript" in eslint
    assert "node_modules" in eslint
    assert "semi" in prettier
    assert "singleQuote" in prettier
    assert pyright["typeCheckingMode"] == "strict"
    assert pyright["include"] == ["python/raos"]
    excluded = pyright["exclude"]
    assert ".venv" in excluded
    assert ".venv-offline-check" in excluded
    assert "venvPath" not in pyright
    assert "venv" not in pyright
    assert "tests/st0103/**/*.test.ts" in vitest
    assert "passWithNoTests: false" in vitest


def test_npm_configuration_fails_closed_and_disables_lifecycle_scripts() -> None:
    lines = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".npmrc")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for setting in (
        "audit=false",
        "cache=.npm-cache",
        "engine-strict=true",
        "fund=false",
        "ignore-scripts=true",
        "install-links=true",
        "legacy-peer-deps=false",
        "omit-lockfile-registry-resolved=false",
        "package-lock=true",
        "prefer-dedupe=true",
        "registry=https://registry.npmjs.org/",
        "save-exact=true",
        "strict-peer-deps=true",
        "update-notifier=false",
    ):
        assert setting in lines
    assert not any(line.startswith("//") for line in lines)
    assert not any("_auth" in line.lower() for line in lines)
    assert not any("token" in line.lower() for line in lines)


def test_required_contract_files_are_regular_nonempty_files() -> None:
    for relative in (
        ".node-version",
        ".npmrc",
        "package.json",
        "package-lock.json",
        "tsconfig.base.json",
        "tsconfig.json",
        "eslint.config.mjs",
        "prettier.config.mjs",
        "pyrightconfig.json",
        "vitest.config.ts",
        "apps/web/package.json",
        "packages/web-ui/package.json",
    ):
        path = REPOSITORY_ROOT / relative
        assert path.is_file(), relative
        assert not path.is_symlink(), relative
        assert Path(path).stat().st_size > 0, relative
    for relative in (
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        ".yarnrc",
        ".yarnrc.yml",
    ):
        assert not (REPOSITORY_ROOT / relative).exists(), relative
