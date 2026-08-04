"""Local structural and safety checks for the ST-0101 workspace bootstrap."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_NAME = "workspace-layout.json"
SCRIPT_PATH = Path("scripts/bootstrap_workspace.py")
GENERATED_HEADER = (
    "<!-- Generated from workspace-layout.json by "
    "scripts/bootstrap_workspace.py. Do not edit directly. -->"
)
EXPECTED_DIRECTORIES = (
    "apps/api",
    "apps/web",
    "apps/worker",
    "contracts",
    "docs/adr",
    "docs/architecture",
    "docs/runbooks",
    "infra/docker",
    "infra/terraform",
    "migrations",
    "packages/policy-schemas",
    "packages/web-contracts",
    "packages/web-ui",
    "policies",
    "prompts",
    "python/raos/adapters",
    "python/raos/api",
    "python/raos/application",
    "python/raos/domain/ai",
    "python/raos/domain/analytics",
    "python/raos/domain/catalog",
    "python/raos/domain/editorial",
    "python/raos/domain/evidence",
    "python/raos/domain/finance",
    "python/raos/domain/freshness",
    "python/raos/domain/iam",
    "python/raos/domain/ops",
    "python/raos/domain/policy",
    "python/raos/domain/portfolio",
    "python/raos/domain/publishing",
    "python/raos/ports",
    "python/raos/shared",
    "python/raos/workers",
    "schemas/ai",
    "schemas/content",
    "schemas/events",
    "schemas/openapi",
    "tests/contract",
    "tests/e2e",
    "tests/evals",
    "tests/fixtures",
    "tests/security",
)
EXPECTED_MANAGED_ROOTS = (
    "apps",
    "contracts",
    "docs",
    "infra",
    "migrations",
    "packages",
    "policies",
    "prompts",
    "python",
    "schemas",
    "tests",
)
EXPECTED_REQUIRED_FILES = (
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "Makefile",
    "README.md",
    "scripts/bootstrap_workspace.py",
    "workspace-layout.json",
)


def minimal_environment() -> dict[str, str]:
    """Return a bounded environment that carries no repository credential."""

    result = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for name in ("LANG", "LC_ALL"):
        if value := os.environ.get(name):
            result[name] = value
    return result


def parse_result(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Assert the CLI's one-document JSON protocol and return its payload."""

    if process.returncode == 0:
        assert process.stderr == ""
        serialized = process.stdout
    else:
        assert process.stdout == ""
        serialized = process.stderr
    assert serialized.endswith("\n")
    assert serialized.count("\n") == 1
    payload = json.loads(serialized)
    assert isinstance(payload, dict)
    assert payload["story_id"] == "ST-0101"
    assert payload["status"] in {"PASS", "FAIL"}
    return payload


def run_bootstrap(
    root: Path,
    *arguments: str,
    use_default_root: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    command = [sys.executable, str(root / SCRIPT_PATH)]
    if not use_default_root:
        command.extend(("--root", str(root)))
    command.extend(arguments)
    process = subprocess.run(
        command,
        cwd=root,
        env=minimal_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return process, parse_result(process)


def run_make(
    root: Path, target: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    make = shutil.which("make")
    if make is None:
        pytest.skip("make is unavailable; Makefile clone acceptance cannot run")
    process = subprocess.run(
        [
            make,
            "--no-print-directory",
            "--silent",
            target,
            f"PYTHON={sys.executable}",
        ],
        cwd=root,
        env=minimal_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return process, parse_result(process)


def load_layout(root: Path) -> dict[str, Any]:
    value = json.loads((root / CONFIG_NAME).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_layout(root: Path, value: Mapping[str, Any]) -> None:
    (root / CONFIG_NAME).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def copy_seed(destination: Path) -> None:
    """Copy only bootstrap inputs, not any generated directory marker."""

    destination.mkdir(parents=True)
    for relative_text in EXPECTED_REQUIRED_FILES:
        relative = Path(relative_text)
        source = REPO_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


@pytest.fixture
def seed_root(tmp_path: Path) -> Path:
    root = tmp_path / "seed"
    copy_seed(root)
    return root


def assert_failure(
    result: tuple[subprocess.CompletedProcess[str], dict[str, Any]],
    message: str,
) -> dict[str, Any]:
    process, payload = result
    assert process.returncode == 1
    assert payload["status"] == "FAIL"
    assert message in payload["error"]
    return payload


def assert_success(
    result: tuple[subprocess.CompletedProcess[str], dict[str, Any]],
    *,
    mode: str,
    changed: Sequence[str] | None = None,
) -> dict[str, Any]:
    process, payload = result
    assert process.returncode == 0
    assert payload == {
        "changed": list(payload["changed"] if changed is None else changed),
        "directories": 42,
        "mode": mode,
        "status": "PASS",
        "story_id": "ST-0101",
        "workspace": "raos",
    }
    if changed is not None:
        assert payload["changed"] == list(changed)
    return payload


def tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("directory", "")
    return result


def test_committed_workspace_check_passes_with_machine_readable_result() -> None:
    process, payload = run_bootstrap(REPO_ROOT, "--check", use_default_root=True)
    assert process.returncode == 0
    assert payload == {
        "changed": [],
        "directories": 42,
        "mode": "check",
        "status": "PASS",
        "story_id": "ST-0101",
        "workspace": "raos",
    }


def test_layout_is_exact_canonical_sorted_42_directory_inventory() -> None:
    layout = load_layout(REPO_ROOT)
    assert layout["schema_version"] == 1
    assert layout["workspace"] == "raos"
    assert layout["marker_file"] == "README.md"
    assert tuple(layout["managed_roots"]) == EXPECTED_MANAGED_ROOTS
    assert tuple(layout["required_files"]) == EXPECTED_REQUIRED_FILES
    paths = tuple(entry["path"] for entry in layout["directories"])
    assert paths == EXPECTED_DIRECTORIES
    assert paths == tuple(sorted(paths))
    assert len(paths) == len(set(paths)) == 42


def test_seed_materialization_is_complete_idempotent_and_checkable(
    seed_root: Path,
) -> None:
    assert_failure(run_bootstrap(seed_root, "--check"), "managed directory is missing")

    first = assert_success(run_bootstrap(seed_root), mode="bootstrap")
    assert len(first["changed"]) == 42
    assert first["changed"] == [f"{path}/README.md" for path in EXPECTED_DIRECTORIES]
    for entry in load_layout(seed_root)["directories"]:
        marker = seed_root / entry["path"] / "README.md"
        assert marker.is_file() and not marker.is_symlink()
        text = marker.read_text(encoding="utf-8")
        assert text.startswith(f"{GENERATED_HEADER}\n\n# `{entry['path']}`\n\n")
        assert entry["purpose"] in text
        if entry["path"] == "packages/web-contracts":
            assert "ST-0105 activates and owns" in text
            assert "src/generated files by hand" in text
            assert "inert boundary" not in text
        else:
            assert "inert boundary" in text

    assert_success(run_bootstrap(seed_root), mode="bootstrap", changed=[])
    assert_success(run_bootstrap(seed_root, "--check"), mode="check", changed=[])


def test_local_git_clean_clone_bootstraps_via_make(
    seed_root: Path, tmp_path: Path
) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable; local clean-clone acceptance cannot run")

    git_environment = minimal_environment()
    commands = (
        [git, "init", "--quiet", str(seed_root)],
        [git, "-C", str(seed_root), "add", "--all"],
        [
            git,
            "-C",
            str(seed_root),
            "-c",
            "user.name=ST-0101 Test",
            "-c",
            "user.email=st0101@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "bootstrap seed",
        ],
    )
    for command in commands:
        subprocess.run(
            command,
            env=git_environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    clone = tmp_path / "clone"
    subprocess.run(
        [
            git,
            "clone",
            "--quiet",
            "--local",
            "--no-hardlinks",
            str(seed_root),
            str(clone),
        ],
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert (clone / ".git").is_dir()
    assert not (clone / "apps").exists()

    first = assert_success(run_make(clone, "bootstrap"), mode="bootstrap")
    assert len(first["changed"]) == 42
    assert_success(run_make(clone, "bootstrap"), mode="bootstrap", changed=[])
    assert_success(run_make(clone, "check-workspace"), mode="check", changed=[])


def test_synthetic_tracked_tree_clone_is_noop_and_git_clean(
    seed_root: Path,
    tmp_path: Path,
) -> None:
    """Model the eventual tracked tree even though this workspace has no Git index."""

    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable; tracked-tree clone acceptance cannot run")
    for relative_text in EXPECTED_DIRECTORIES:
        source = REPO_ROOT / relative_text / "README.md"
        target = seed_root / relative_text / "README.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    git_environment = minimal_environment()
    commands = (
        [git, "init", "--quiet", str(seed_root)],
        [git, "-C", str(seed_root), "add", "--all"],
        [
            git,
            "-C",
            str(seed_root),
            "-c",
            "user.name=ST-0101 Test",
            "-c",
            "user.email=st0101@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "tracked workspace",
        ],
    )
    for command in commands:
        subprocess.run(
            command,
            env=git_environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    clone = tmp_path / "tracked-clone"
    subprocess.run(
        [
            git,
            "clone",
            "--quiet",
            "--local",
            "--no-hardlinks",
            str(seed_root),
            str(clone),
        ],
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert_success(run_make(clone, "bootstrap"), mode="bootstrap", changed=[])
    assert_success(run_make(clone, "check-workspace"), mode="check", changed=[])
    status = subprocess.run(
        [git, "-C", str(clone), "status", "--porcelain"],
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert status.stdout == ""


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda value: value.update({"unexpected": True}), "unknown=['unexpected']"),
        (lambda value: value.pop("workspace"), "missing=['workspace']"),
        (
            lambda value: value["directories"][0].update({"unexpected": True}),
            "unknown=['unexpected']",
        ),
        (
            lambda value: value["directories"][0].pop("purpose"),
            "missing=['purpose']",
        ),
    ),
)
def test_unknown_and_missing_config_keys_fail_closed(
    seed_root: Path,
    mutation: Any,
    message: str,
) -> None:
    layout = load_layout(seed_root)
    mutation(layout)
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), message)
    assert not (seed_root / "apps").exists()


def test_duplicate_json_key_and_oversized_config_fail_before_writes(
    seed_root: Path,
) -> None:
    config = seed_root / CONFIG_NAME
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("{", '{\n  "workspace": "shadow",', 1), encoding="utf-8"
    )
    assert_failure(run_bootstrap(seed_root), "duplicate JSON object key: workspace")
    assert not (seed_root / "apps").exists()

    copy_seed(seed_root := seed_root.parent / "oversized")
    config = seed_root / CONFIG_NAME
    config.write_text(
        config.read_text(encoding="utf-8") + (" " * (256 * 1024)),
        encoding="utf-8",
    )
    assert_failure(run_bootstrap(seed_root), "exceeds 262144 bytes")
    assert not (seed_root / "apps").exists()


def test_oversized_generated_marker_fails_before_any_write(seed_root: Path) -> None:
    layout = load_layout(seed_root)
    layout["directories"][0]["purpose"] = "x" * (64 * 1024)
    write_layout(seed_root, layout)

    assert_failure(run_bootstrap(seed_root), "generated marker exceeds 65536 bytes")
    assert not (seed_root / "apps").exists()


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("schema_version", 2, "unsupported workspace schema_version"),
        ("schema_version", True, "unsupported workspace schema_version"),
        ("workspace", "other", "workspace name must be raos"),
        ("marker_file", "MARKER.md", "marker_file must be README.md"),
        ("managed_roots", list(reversed(EXPECTED_MANAGED_ROOTS)), "managed_roots"),
        ("managed_roots", [*EXPECTED_MANAGED_ROOTS, "outside"], "managed_roots"),
        (
            "required_files",
            list(reversed(EXPECTED_REQUIRED_FILES)),
            "required_files",
        ),
        ("required_files", list(EXPECTED_REQUIRED_FILES[:-1]), "required_files"),
    ),
)
def test_wrong_schema_name_root_and_file_contracts_fail_closed(
    seed_root: Path,
    field: str,
    replacement: Any,
    message: str,
) -> None:
    layout = load_layout(seed_root)
    layout[field] = replacement
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), message)
    assert not (seed_root / "apps").exists()


def test_duplicate_and_unsorted_directory_entries_fail_closed(seed_root: Path) -> None:
    layout = load_layout(seed_root)
    layout["directories"].append(deepcopy(layout["directories"][0]))
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), "duplicate managed directory: apps/api")
    assert not (seed_root / "apps").exists()

    copy_seed(seed_root := seed_root.parent / "unsorted")
    layout = load_layout(seed_root)
    layout["directories"][0], layout["directories"][1] = (
        layout["directories"][1],
        layout["directories"][0],
    )
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), "directories must be sorted by path")
    assert not (seed_root / "apps").exists()


def test_missing_or_unknown_directory_contract_fails_closed(seed_root: Path) -> None:
    layout = load_layout(seed_root)
    layout["directories"].pop()
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), "directories differ")
    assert not (seed_root / "apps").exists()

    copy_seed(seed_root := seed_root.parent / "unknown-directory")
    layout = load_layout(seed_root)
    layout["directories"][0]["path"] = "apps/aaa"
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), "directories differ")
    assert not (seed_root / "apps").exists()


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "/absolute",
        "../outside",
        "apps/../outside",
        "apps\\api",
        "apps//api",
        "apps/./api",
        "apps/api/",
    ),
)
def test_unsafe_or_non_normalized_paths_cannot_write_outside_repository(
    seed_root: Path,
    unsafe_path: str,
) -> None:
    outside = seed_root.parent / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    before = tree_snapshot(outside)

    layout = load_layout(seed_root)
    layout["directories"][0]["path"] = unsafe_path
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), "path")
    assert tree_snapshot(outside) == before
    assert not (seed_root / "apps").exists()


def test_managed_path_cannot_enter_docs_canonical(seed_root: Path) -> None:
    protected = seed_root / "docs/canonical"
    protected.mkdir(parents=True)
    sentinel = protected / "sentinel.txt"
    sentinel.write_text("immutable\n", encoding="utf-8")
    before = tree_snapshot(protected)

    layout = load_layout(seed_root)
    layout["directories"][4]["path"] = "docs/canonical/attempt"
    write_layout(seed_root, layout)
    assert_failure(run_bootstrap(seed_root), "enters an immutable design root")
    assert tree_snapshot(protected) == before
    assert not (protected / "attempt").exists()


def test_missing_required_file_fails_before_materialization(seed_root: Path) -> None:
    (seed_root / "AGENTS.md").unlink()
    assert_failure(run_bootstrap(seed_root), "required repository file")
    assert not (seed_root / "apps").exists()


def test_symlinked_configuration_is_rejected_without_reading_target(
    seed_root: Path,
) -> None:
    outside = seed_root.parent / "outside-config.json"
    outside.write_text('{"secret": "do-not-read"}\n', encoding="utf-8")
    before = outside.read_bytes()
    (seed_root / CONFIG_NAME).unlink()
    (seed_root / CONFIG_NAME).symlink_to(outside)

    assert_failure(run_bootstrap(seed_root), "is a symlink")
    assert outside.read_bytes() == before
    assert not (seed_root / "apps").exists()


def test_symlinked_required_file_parent_is_rejected(seed_root: Path) -> None:
    outside = seed_root.parent / "outside-scripts"
    outside.mkdir()
    shutil.copy2(seed_root / SCRIPT_PATH, outside / SCRIPT_PATH.name)
    shutil.rmtree(seed_root / "scripts")
    (seed_root / "scripts").symlink_to(outside, target_is_directory=True)

    assert_failure(run_bootstrap(seed_root), "symlink component")
    assert not (seed_root / "apps").exists()


def test_symlinked_repository_root_is_rejected(seed_root: Path) -> None:
    linked_root = seed_root.parent / "linked-root"
    linked_root.symlink_to(seed_root, target_is_directory=True)

    assert_failure(run_bootstrap(linked_root), "repository root")
    assert not (seed_root / "apps").exists()


def test_symlinked_managed_directory_cannot_escape_repository(seed_root: Path) -> None:
    outside = seed_root.parent / "outside-directory"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    before = tree_snapshot(outside)
    (seed_root / "apps").symlink_to(outside, target_is_directory=True)

    assert_failure(run_bootstrap(seed_root), "symlink component")
    assert tree_snapshot(outside) == before


def test_symlinked_marker_cannot_escape_repository(seed_root: Path) -> None:
    assert_success(run_bootstrap(seed_root), mode="bootstrap")
    outside = seed_root.parent / "outside-marker.md"
    outside.write_text("unchanged\n", encoding="utf-8")
    before = outside.read_bytes()
    marker = seed_root / "apps/api/README.md"
    marker.unlink()
    marker.symlink_to(outside)

    assert_failure(run_bootstrap(seed_root), "is a symlink")
    assert outside.read_bytes() == before


@pytest.mark.parametrize("collision_kind", ("directory", "fifo"))
def test_non_regular_marker_collision_fails_without_blocking(
    seed_root: Path,
    collision_kind: str,
) -> None:
    assert_success(run_bootstrap(seed_root), mode="bootstrap")
    marker = seed_root / "apps/api/README.md"
    marker.unlink()
    if collision_kind == "directory":
        marker.mkdir()
    elif hasattr(os, "mkfifo"):
        os.mkfifo(marker)
    else:
        pytest.skip("FIFO creation is unavailable on this platform")

    assert_failure(run_bootstrap(seed_root), "regular non-symlink file")


def test_ancestor_file_collision_fails_before_any_generated_write(
    seed_root: Path,
) -> None:
    collision = seed_root / "contracts"
    collision.write_text("not a directory\n", encoding="utf-8")
    before = collision.read_bytes()

    assert_failure(run_bootstrap(seed_root), "collides with a file")
    assert collision.read_bytes() == before
    assert not (seed_root / "apps").exists()


def test_check_detects_generated_marker_drift_without_writing(seed_root: Path) -> None:
    assert_success(run_bootstrap(seed_root), mode="bootstrap")
    marker = seed_root / "apps/api/README.md"
    marker.write_text(f"{GENERATED_HEADER}\n\ndrift\n", encoding="utf-8")
    before = marker.read_bytes()

    assert_failure(run_bootstrap(seed_root, "--check"), "managed marker drift")
    assert marker.read_bytes() == before

    assert_failure(run_bootstrap(seed_root), "managed marker drift")
    assert marker.read_bytes() == before


def test_bootstrap_refuses_to_overwrite_unmanaged_marker(seed_root: Path) -> None:
    directory = seed_root / "contracts"
    directory.mkdir(parents=True)
    marker = directory / "README.md"
    marker.write_text("# Human-owned content\n", encoding="utf-8")
    before = marker.read_bytes()

    assert_failure(
        run_bootstrap(seed_root), "refusing to overwrite an unmanaged marker"
    )
    assert marker.read_bytes() == before
    assert not (seed_root / "apps").exists()


def test_bootstrap_preserves_all_immutable_import_artifact_bytes() -> None:
    protected = [REPO_ROOT / "docs/manifest.json"]
    for root_name in ("docs/canonical", "docs/upstream", "zip"):
        protected.extend(
            path
            for path in (REPO_ROOT / root_name).rglob("*")
            if path.is_file() and not path.is_symlink()
        )
    before = {path: path.read_bytes() for path in protected}

    assert_success(run_bootstrap(REPO_ROOT), mode="bootstrap", changed=[])

    assert {path: path.read_bytes() for path in protected} == before
