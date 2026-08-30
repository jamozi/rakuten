"""Adversarial tests for the source-constrained CI hydration validator."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPOSITORY_ROOT / "scripts/validate_ci_hydration.py"
SYSTEM_PYTHON = Path("/usr/bin/python3")
ROOT_INPUTS = (
    ".python-version",
    "pyproject.toml",
    "uv.toml",
    "uv.lock",
    ".npmrc",
    "package.json",
    "package-lock.json",
)
WORKSPACE_MANIFESTS = (
    "apps/web/package.json",
    "packages/wordpress-mcp-bridge/package.json",
    "packages/web-contracts/package.json",
    "packages/web-ui/package.json",
)


def make_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository with spaces"
    (repository / "scripts").mkdir(parents=True)
    shutil.copy2(VALIDATOR, repository / "scripts/validate_ci_hydration.py")
    for relative in (*ROOT_INPUTS, *WORKSPACE_MANIFESTS):
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative, destination)
    return repository


def run_validator(repository: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(SYSTEM_PYTHON),
            "-I",
            str(repository / "scripts/validate_ci_hydration.py"),
        ],
        cwd=repository.parent,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def failure_payload(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    assert result.returncode != 0
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["status"] == "FAIL"
    assert set(payload) == {"error", "source", "status"}
    assert all(isinstance(value, str) for value in payload.values())
    return payload


def read_json(repository: Path, relative: str) -> dict[str, Any]:
    parsed = json.loads((repository / relative).read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def write_json(repository: Path, relative: str, value: dict[str, Any]) -> None:
    (repository / relative).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def replace_once(repository: Path, relative: str, old: str, new: str) -> None:
    path = repository / relative
    content = path.read_text(encoding="utf-8")
    assert content.count(old) == 1
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def first_external_lock_package(package_lock: dict[str, Any]) -> dict[str, Any]:
    packages = package_lock["packages"]
    assert isinstance(packages, dict)
    for path, metadata in packages.items():
        if (
            isinstance(path, str)
            and "node_modules/" in path
            and isinstance(metadata, dict)
            and metadata.get("link") is not True
        ):
            return metadata
    raise AssertionError("fixture has no external package")


def test_current_tree_passes_under_isolated_system_python_deterministically() -> None:
    assert SYSTEM_PYTHON == Path("/usr/bin/python3")
    assert SYSTEM_PYTHON.is_file()
    assert VALIDATOR.is_file() and not VALIDATOR.is_symlink()

    first = run_validator(REPOSITORY_ROOT)
    second = run_validator(REPOSITORY_ROOT)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    assert json.loads(first.stdout) == {
        "npm": {
            "external_packages": 631,
            "lockfile_version": 3,
            "manifests": 5,
            "workspaces": 4,
        },
        "python": {
            "artifacts": 482,
            "lock_packages": 67,
            "lock_revision": 3,
            "lock_version": 1,
            "requirements": 16,
            "version": "3.14.6",
        },
        "status": "PASS",
    }
    assert str(REPOSITORY_ROOT) not in first.stdout
    assert "https://" not in first.stdout


@pytest.mark.parametrize(
    "relative",
    [
        ".python-version",
        "pyproject.toml",
        "uv.toml",
        "uv.lock",
        ".npmrc",
        "package.json",
        "package-lock.json",
        "apps/web/package.json",
    ],
)
def test_required_inputs_must_be_regular_non_symlink_files(
    tmp_path: Path, relative: str
) -> None:
    repository = make_repository(tmp_path)
    path = repository / relative
    replacement = path.with_name(path.name + ".regular")
    path.rename(replacement)
    try:
        path.symlink_to(replacement)
    except OSError:
        pytest.skip("symlinks are not supported")

    payload = failure_payload(run_validator(repository))

    assert payload["error"] in {"UNSAFE_OR_MISSING_FILE", "UNSAFE_WORKSPACE_PATH"}


@pytest.mark.parametrize(
    "specifier",
    [
        "pydantic @ https://example.invalid/pydantic.whl",
        "pydantic @ git+https://example.invalid/repository.git",
        "pydantic @ file:///tmp/pydantic.whl",
        "../vendor/pydantic",
        "pydantic>=2.13.4",
        "pydantic~=2.13.4",
        "pydantic==*",
    ],
)
def test_python_manifest_rejects_remote_git_file_path_and_range_specs(
    tmp_path: Path, specifier: str
) -> None:
    repository = make_repository(tmp_path)
    replace_once(repository, "pyproject.toml", "pydantic==2.13.4", specifier)

    payload = failure_payload(run_validator(repository))

    assert payload == {
        "error": "UNSAFE_PYTHON_REQUIREMENT",
        "source": "pyproject.toml",
        "status": "FAIL",
    }


@pytest.mark.parametrize(
    "requirement",
    [
        "psycopg==3.3.4",
        "psycopg[pool]==3.3.4",
        "psycopg[binary,pool]==3.3.4",
        "psycopg[Binary]==3.3.4",
        "psycopg[binary,binary]==3.3.4",
        "psycopg[]==3.3.4",
    ],
)
def test_python_manifest_accepts_only_the_reviewed_psycopg_extra(
    tmp_path: Path, requirement: str
) -> None:
    repository = make_repository(tmp_path)
    replace_once(
        repository,
        "pyproject.toml",
        "psycopg[binary]==3.3.4",
        requirement,
    )

    payload = failure_payload(run_validator(repository))

    assert payload == {
        "error": "UNSAFE_PYTHON_REQUIREMENT",
        "source": "pyproject.toml",
        "status": "FAIL",
    }


@pytest.mark.parametrize(
    ("old", "new", "expected_error"),
    [
        ('extra = ["binary"]', 'extra = ["pool"]', "LOCK_PROJECT_PIN_MISMATCH"),
        (
            'extra = ["binary"]',
            'extra = ["binary", "binary"]',
            "UNSAFE_LOCK_DEPENDENCY",
        ),
        (
            'extras = ["binary"]',
            'extras = ["pool"]',
            "LOCK_PROJECT_PIN_MISMATCH",
        ),
        (
            'extras = ["binary"]',
            'extras = ["binary", "binary"]',
            "UNSAFE_LOCK_METADATA",
        ),
        (
            "[package.optional-dependencies]\nbinary = [",
            "[package.optional-dependencies]\npool = [",
            "UNSAFE_UV_LOCK_PACKAGE",
        ),
    ],
)
def test_uv_lock_extra_shapes_are_exactly_bound_to_the_project_requirement(
    tmp_path: Path, old: str, new: str, expected_error: str
) -> None:
    repository = make_repository(tmp_path)
    replace_once(repository, "uv.lock", old, new)

    payload = failure_payload(run_validator(repository))

    assert payload == {
        "error": expected_error,
        "source": "uv.lock",
        "status": "FAIL",
    }


def test_python_manifest_rejects_uv_source_overrides(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    path = repository / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n[tool.uv.sources]\npydantic = { path = "../pydantic" }\n',
        encoding="utf-8",
    )

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_UV_PROJECT_CONFIG"


@pytest.mark.parametrize(
    ("old", "new", "expected_error"),
    [
        (
            'source = { registry = "https://pypi.org/simple" }',
            'source = { registry = "https://mirror.invalid/simple" }',
            "UNSAFE_PYTHON_SOURCE",
        ),
        (
            "https://files.pythonhosted.org/packages/",
            "http://files.pythonhosted.org/packages/",
            "UNSAFE_URL",
        ),
        (
            "https://files.pythonhosted.org/packages/",
            "https://mirror.invalid/packages/",
            "UNSAFE_URL",
        ),
        (
            "https://files.pythonhosted.org/packages/",
            "https://user:password@files.pythonhosted.org/packages/",
            "UNSAFE_URL",
        ),
        (
            '.tar.gz", hash = "sha256:',
            '.tar.gz?download=1", hash = "sha256:',
            "UNSAFE_URL",
        ),
        (
            '.tar.gz", hash = "sha256:',
            '.tar.gz#archive", hash = "sha256:',
            "UNSAFE_URL",
        ),
    ],
)
def test_uv_lock_rejects_unreviewed_or_ambiguous_urls(
    tmp_path: Path, old: str, new: str, expected_error: str
) -> None:
    repository = make_repository(tmp_path)
    path = repository / "uv.lock"
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new, 1), encoding="utf-8")

    result = run_validator(repository)
    payload = failure_payload(result)

    assert payload["error"] == expected_error
    assert "password" not in result.stderr


def test_uv_lock_rejects_an_artifact_without_sha256(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    path = repository / "uv.lock"
    content = path.read_text(encoding="utf-8")
    mutated, replacements = re.subn(
        r', hash = "sha256:[0-9a-f]{64}"', "", content, count=1
    )
    assert replacements == 1
    path.write_text(mutated, encoding="utf-8")

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_PYTHON_ARTIFACT"


@pytest.mark.parametrize(
    "upload_time",
    [
        "2026-08-02T00:00:00Z",
        "2026-08-01T16:50:16+00:00",
        "not-a-timestamp",
    ],
)
def test_uv_lock_rejects_artifacts_after_or_outside_the_utc_cutoff_contract(
    tmp_path: Path,
    upload_time: str,
) -> None:
    repository = make_repository(tmp_path)
    path = repository / "uv.lock"
    content = path.read_text(encoding="utf-8")
    mutated, replacements = re.subn(
        r'upload-time = "[^"]+"',
        f'upload-time = "{upload_time}"',
        content,
        count=1,
    )
    assert replacements == 1
    path.write_text(mutated, encoding="utf-8")

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_PYTHON_ARTIFACT"


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("version", 2, "WRONG_UV_LOCK_VERSION"),
        ("revision", 4, "WRONG_UV_LOCK_REVISION"),
    ],
)
def test_uv_lock_format_and_revision_are_exact(
    tmp_path: Path, field: str, value: int, expected_error: str
) -> None:
    repository = make_repository(tmp_path)
    replace_once(repository, "uv.lock", f"{field} = {value - 1}", f"{field} = {value}")

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == expected_error


@pytest.mark.parametrize(
    "specifier",
    [
        "https://example.invalid/archive.tgz",
        "git+https://example.invalid/repository.git",
        "file:../archive.tgz",
        "../vendor/package",
        "^0.99.0",
        "~0.99.0",
        ">=0.99.0",
        "latest",
        "*",
    ],
)
def test_npm_manifests_reject_remote_git_file_path_and_ranges(
    tmp_path: Path, specifier: str
) -> None:
    repository = make_repository(tmp_path)
    manifest = read_json(repository, "package.json")
    manifest["devDependencies"]["@hey-api/openapi-ts"] = specifier
    write_json(repository, "package.json", manifest)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_NPM_SPECIFIER"
    assert payload["source"] == "package.json"


def test_workspace_star_is_limited_to_a_declared_other_workspace(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    manifest = read_json(repository, "package.json")
    manifest["dependencies"] = {"@raos/web": "workspace:*"}
    write_json(repository, "package.json", manifest)
    package_lock = read_json(repository, "package-lock.json")
    package_lock["packages"][""]["dependencies"] = {"@raos/web": "workspace:*"}
    write_json(repository, "package-lock.json", package_lock)

    result = run_validator(repository)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_workspace_star_rejects_an_undeclared_package(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    manifest = read_json(repository, "package.json")
    manifest["dependencies"] = {"unreviewed-package": "workspace:*"}
    write_json(repository, "package.json", manifest)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_NPM_SPECIFIER"


def mutate_npm_resolved(
    metadata: dict[str, Any], transform: Callable[[str], str]
) -> None:
    resolved = metadata["resolved"]
    assert isinstance(resolved, str)
    metadata["resolved"] = transform(resolved)


@pytest.mark.parametrize(
    "transform",
    [
        lambda value: value.replace(
            "https://registry.npmjs.org/", "http://registry.npmjs.org/", 1
        ),
        lambda value: value.replace(
            "https://registry.npmjs.org/", "https://mirror.invalid/", 1
        ),
        lambda value: value + "?download=1",
        lambda value: value + "#archive",
        lambda value: value.replace(
            "https://registry.npmjs.org/",
            "https://user:TOP_SECRET@registry.npmjs.org/",
            1,
        ),
    ],
    ids=("http", "wrong-registry", "query", "fragment", "credentials"),
)
def test_package_lock_rejects_unsafe_resolved_urls(
    tmp_path: Path, transform: Callable[[str], str]
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    mutate_npm_resolved(metadata, transform)
    write_json(repository, "package-lock.json", package_lock)

    result = run_validator(repository)
    payload = failure_payload(result)

    assert payload["error"] == "UNSAFE_URL"
    assert "TOP_SECRET" not in result.stderr


@pytest.mark.parametrize(
    "section",
    ["dependencies", "optionalDependencies", "peerDependencies"],
)
@pytest.mark.parametrize(
    "specifier",
    [
        "",
        " ",
        " 1.2.3",
        "1.2.3 ",
        "1.2.3  || 2.0.0",
        "ssh://git@example.invalid/repository.git",
        "git+ssh://git@example.invalid/repository.git",
        "git@example.invalid:repository.git",
        "github:user/repository",
        "user/repository#ref",
        "http://example.invalid/archive.tgz",
        "https://example.invalid/archive.tgz",
        "file:../archive.tgz",
        "path:../package",
        "link:../package",
        "npm:other-package@1.2.3",
        "workspace:*",
        "/absolute/path",
        "./relative/path",
        "../relative/path",
        r"C:\absolute\path",
        r"\\server\share\package",
        "alias@1.2.3",
        "1.2.3#ref",
        "1.2.3%2farchive",
        "1.2.3\n",
        "１.２.３",
        "1-foo",
        "^1-foo",
        "< *",
        "* || 1.2.3-alpha",
        "x || 1.2.3-alpha",
        ">=0.0.0 || 1.2.3-alpha",
        ">= 0.0.0 || 1.2.3-alpha",
        "1",
        "1.2",
        "~1",
        ">=1",
        "^1.2.3 <2.0.0",
        "1.2.3 2.0.0",
        ">=1.0.0 <2.0.0 || ^3.0.0",
        "||",
        "1.2.3 ||",
        "|| 1.2.3",
    ],
    ids=[
        "empty",
        "whitespace",
        "leading-whitespace",
        "trailing-whitespace",
        "repeated-whitespace",
        "ssh-url",
        "git-plus-ssh",
        "git-at-host",
        "github-shorthand",
        "git-shorthand-with-ref",
        "http-url",
        "https-url",
        "file-alias",
        "path-alias",
        "link-alias",
        "npm-alias",
        "workspace-alias",
        "absolute-path",
        "dot-relative-path",
        "parent-relative-path",
        "windows-drive-path",
        "windows-unc-path",
        "at-sign",
        "hash",
        "percent",
        "control-character",
        "non-ascii",
        "partial-prerelease",
        "caret-partial-prerelease",
        "wildcard-comparator",
        "wildcard-union",
        "x-wildcard-union",
        "universal-comparator-union",
        "spaced-universal-comparator-union",
        "bare-major-partial",
        "bare-minor-partial",
        "tilde-partial",
        "comparator-partial",
        "caret-comparator-set",
        "bare-comparator-set",
        "union-with-comparator-set",
        "empty-union",
        "missing-union-right",
        "missing-union-left",
    ],
)
def test_package_lock_dependency_descriptors_accept_only_semver_ranges(
    tmp_path: Path, specifier: str, section: str
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    metadata.setdefault(section, {})["injected-package"] = specifier
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload == {
        "error": "UNSAFE_NPM_LOCK_REFERENCE",
        "source": "package-lock.json",
        "status": "FAIL",
    }


@pytest.mark.parametrize("section", ["dependencies", "optionalDependencies"])
def test_non_peer_lock_dependencies_require_a_captured_package_entry(
    tmp_path: Path, section: str
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    metadata.setdefault(section, {})["uncaptured-package"] = "1.2.3"
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload == {
        "error": "MISSING_NPM_LOCK_DEPENDENCY",
        "source": "package-lock.json",
        "status": "FAIL",
    }


def test_missing_required_peer_lock_dependency_is_rejected(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    metadata.setdefault("peerDependencies", {})["uncaptured-peer"] = "^1.2.3"
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "MISSING_NPM_LOCK_DEPENDENCY"


def test_missing_explicitly_optional_peer_lock_dependency_is_allowed(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    metadata.setdefault("peerDependencies", {})["uncaptured-peer"] = "^1.2.3"
    metadata.setdefault("peerDependenciesMeta", {})["uncaptured-peer"] = {
        "optional": True
    }
    write_json(repository, "package-lock.json", package_lock)

    result = run_validator(repository)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


@pytest.mark.parametrize(
    "peer_metadata",
    [
        [],
        {"uncaptured-peer": []},
        {"uncaptured-peer": {}},
        {"uncaptured-peer": {"optional": "true"}},
        {"uncaptured-peer": {"optional": True, "unexpected": True}},
    ],
    ids=["not-object", "flags-not-object", "missing-flag", "non-bool", "extra-flag"],
)
def test_peer_dependency_metadata_has_a_closed_shape(
    tmp_path: Path, peer_metadata: Any
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    metadata.setdefault("peerDependencies", {})["uncaptured-peer"] = "^1.2.3"
    metadata["peerDependenciesMeta"] = peer_metadata
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_NPM_LOCK_REFERENCE"


def test_false_optional_peer_metadata_does_not_exempt_closure(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    metadata.setdefault("peerDependencies", {})["uncaptured-peer"] = "^1.2.3"
    metadata.setdefault("peerDependenciesMeta", {})["uncaptured-peer"] = {
        "optional": False
    }
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "MISSING_NPM_LOCK_DEPENDENCY"


@pytest.mark.parametrize(
    "section", ["dependencies", "optionalDependencies", "peerDependencies"]
)
def test_captured_lock_dependency_version_must_satisfy_descriptor(
    tmp_path: Path, section: str
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = package_lock["packages"]["node_modules/@babel/code-frame"]
    metadata.setdefault(section, {})["picocolors"] = "1.0.0"
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "NPM_LOCK_RANGE_MISMATCH"


@pytest.mark.parametrize(
    "section", ["dependencies", "optionalDependencies", "peerDependencies"]
)
def test_captured_lock_dependency_accepts_a_satisfied_semver_range(
    tmp_path: Path, section: str
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = package_lock["packages"]["node_modules/@babel/code-frame"]
    metadata.setdefault(section, {})["picocolors"] = "^1.1.0"
    write_json(repository, "package-lock.json", package_lock)

    result = run_validator(repository)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_root_manifest_dependency_requires_exact_captured_version(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    del package_lock["packages"]["node_modules/@hey-api/openapi-ts"]
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "MISSING_NPM_LOCK_DEPENDENCY"


def test_workspace_dependency_requires_the_expected_workspace_link(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    workspace_manifest = read_json(repository, "apps/web/package.json")
    workspace_manifest.setdefault("dependencies", {})["@raos/web-ui"] = "workspace:*"
    write_json(repository, "apps/web/package.json", workspace_manifest)
    package_lock = read_json(repository, "package-lock.json")
    package_lock["packages"]["apps/web"].setdefault("dependencies", {})[
        "@raos/web-ui"
    ] = "workspace:*"
    package_lock["packages"]["node_modules/@raos/web-ui"]["resolved"] = (
        "packages/web-contracts"
    )
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_NPM_WORKSPACE_LINK"


def test_root_manifest_security_overrides_are_an_exact_closed_contract(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    manifest = read_json(repository, "package.json")
    manifest["overrides"]["vite"] = "8.1.0"
    write_json(repository, "package.json", manifest)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_NPM_OVERRIDE"


@pytest.mark.parametrize("mode", ["missing", "sha256", "invalid-base64"])
def test_external_lock_packages_require_valid_sha512_integrity(
    tmp_path: Path, mode: str
) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    metadata = first_external_lock_package(package_lock)
    if mode == "missing":
        del metadata["integrity"]
    elif mode == "sha256":
        metadata["integrity"] = "sha256-" + base64.b64encode(bytes(32)).decode()
    else:
        metadata["integrity"] = "sha512-not+valid==="
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "MISSING_OR_UNSAFE_SHA512"


def test_package_lock_must_be_v3(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    package_lock = read_json(repository, "package-lock.json")
    package_lock["lockfileVersion"] = 2
    write_json(repository, "package-lock.json", package_lock)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "WRONG_NPM_LOCK_CONTRACT"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("registry=https://registry.npmjs.org/", "registry=https://mirror.invalid/"),
        ("ignore-scripts=true", "ignore-scripts=false"),
        ("cache=.npm-cache", "cache=/tmp/npm-cache"),
        (
            "omit-lockfile-registry-resolved=false",
            "omit-lockfile-registry-resolved=true",
        ),
    ],
)
def test_npmrc_requires_the_closed_safe_configuration(
    tmp_path: Path, old: str, new: str
) -> None:
    repository = make_repository(tmp_path)
    replace_once(repository, ".npmrc", old, new)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_NPM_CONFIG"


def test_npmrc_rejects_credentials_without_echoing_them(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    path = repository / ".npmrc"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "//registry.npmjs.org/:_authToken=TOP_SECRET\n",
        encoding="utf-8",
    )

    result = run_validator(repository)
    payload = failure_payload(result)

    assert payload["error"] == "UNSAFE_NPM_CONFIG"
    assert "TOP_SECRET" not in result.stderr


@pytest.mark.parametrize("workspace", ["apps/*", "../outside", "/tmp/workspace"])
def test_workspace_paths_cannot_be_globs_or_escape_the_repository(
    tmp_path: Path, workspace: str
) -> None:
    repository = make_repository(tmp_path)
    manifest = read_json(repository, "package.json")
    manifest["workspaces"][0] = workspace
    write_json(repository, "package.json", manifest)

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "UNSAFE_WORKSPACE_PATH"


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    path = repository / "package.json"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("{\n")
    path.write_text('{\n  "name": "shadow",' + content[1:], encoding="utf-8")

    payload = failure_payload(run_validator(repository))

    assert payload["error"] == "INVALID_JSON"


def test_validator_rejects_cli_extensions() -> None:
    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-I", str(VALIDATOR), "--root", "/tmp"],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )

    payload = failure_payload(result)
    assert result.returncode == 64
    assert payload["error"] == "INVALID_ARGUMENTS"
