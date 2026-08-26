"""Stage-zero integrity tests for the closed ST-1704 source-capture CLI."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import types
from typing import Callable, cast, Protocol

import pytest


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts/st1704_official_source_capture.py"
CLI = runpy.run_path(str(CLI_PATH))
CLI_GLOBALS = cast(types.FunctionType, CLI["_verify_runtime_integrity"]).__globals__
MANIFEST_RELATIVE = cast(str, CLI["MANIFEST_RELATIVE"])
PREDECESSOR_RELATIVE = cast(str, CLI["PREDECESSOR_RELATIVE"])
BOOTSTRAP_RELATIVE = cast(str, CLI["BOOTSTRAP_RELATIVE"])
RUNTIME_PATHS = cast(tuple[str, ...], CLI["EXPECTED_RUNTIME_PATHS"])
REGISTRY_RELATIVE = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json"
)
LOCATOR_RELATIVE = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "source-locator-contract.v1.json"
)
_GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_PROCESS_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}


class _ReadRelative(Protocol):
    def __call__(self, root_fd: int, relative: str, *, maximum: int) -> bytes: ...


class _SourceTarget(Protocol):
    url: str


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "--no-optional-locks", "-C", str(root), *arguments],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_GIT_ENVIRONMENT,
        timeout=10,
    )
    return completed.stdout


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "--", ".")
    _git(
        root,
        "-c",
        "user.name=RAOS Test",
        "-c",
        "user.email=raos@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )


def _copy_committed_runtime(tmp_path: Path) -> Path:
    copied_root = tmp_path / "runtime"
    copied_root.mkdir(mode=0o700)
    relative_paths = (*RUNTIME_PATHS, MANIFEST_RELATIVE, PREDECESSOR_RELATIVE)
    for relative in relative_paths:
        source = ROOT / relative
        target = copied_root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o600)
    _git(copied_root, "init", "-q")
    _commit(copied_root, "baseline")
    return copied_root


def _runtime_failure() -> type[Exception]:
    return cast(type[Exception], CLI["_RuntimeFailure"])


def _verify(root: Path) -> tuple[dict[str, bytes], tuple[int, int]]:
    verifier = cast(
        Callable[[Path], tuple[dict[str, bytes], tuple[int, int]]],
        CLI["_verify_runtime_integrity"],
    )
    return verifier(root)


def _rewrite_registry_and_mutable_manifest(root: Path) -> None:
    registry_path = root / REGISTRY_RELATIVE
    original_url = b"https://www.ankerjapan.com/products/a1722"
    substituted_url = b"https://www.ankerjapan.net/products/a1722"
    assert len(original_url) == len(substituted_url)
    registry = registry_path.read_bytes()
    assert registry.count(original_url) == 1
    mutated = registry.replace(original_url, substituted_url)
    registry_path.write_bytes(mutated)

    registry_document = json.loads(mutated.decode("utf-8"))
    registry_canonical = json.dumps(
        registry_document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    locator_path = root / LOCATOR_RELATIVE
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["source_registry_sha256"] = hashlib.sha256(registry_canonical).hexdigest()
    locator_bytes = (json.dumps(locator, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    locator_path.write_bytes(locator_bytes)

    manifest_path = root / MANIFEST_RELATIVE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    replacements = {
        REGISTRY_RELATIVE: mutated,
        LOCATOR_RELATIVE: locator_bytes,
    }
    updated: set[str] = set()
    for row in manifest["paths"]:
        replacement = replacements.get(row["path"])
        if replacement is not None:
            row["bytes"] = len(replacement)
            row["sha256"] = hashlib.sha256(replacement).hexdigest()
            updated.add(row["path"])
    assert updated == set(replacements)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_stage_zero_source_has_no_raos_import_or_worktree_path_insertion() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert not any(name == "raos" or name.startswith("raos.") for name in imported)
    assert "sys.path.insert" not in source
    main = source[source.index("def main(") :]
    assert (
        main.index("_verify_stage_zero()")
        < main.index("_verify_runtime_integrity(REPOSITORY_ROOT)")
        < main.index("_execute(")
    )
    runtime_handler = main.split("except _RuntimeFailure:", 1)[1].split(
        "except _CommandFailure", 1
    )[0]
    assert "raos" not in runtime_handler


def test_exact_head_bound_runtime_verifies_closed_bytes(tmp_path: Path) -> None:
    copied_root = _copy_committed_runtime(tmp_path)

    sources, identity = _verify(copied_root)

    observed = copied_root.stat()
    assert identity == (observed.st_dev, observed.st_ino)
    assert set(sources) == set(RUNTIME_PATHS)
    assert sources[REGISTRY_RELATIVE] == (copied_root / REGISTRY_RELATIVE).read_bytes()
    assert MANIFEST_RELATIVE not in sources
    assert PREDECESSOR_RELATIVE not in sources


def test_runtime_validation_does_not_require_git_ancestry(
    tmp_path: Path,
) -> None:
    outer_root = _copy_committed_runtime(tmp_path)
    nested_root = outer_root / "unbound-runtime"
    nested_root.mkdir(mode=0o700)
    for relative in (*RUNTIME_PATHS, MANIFEST_RELATIVE, PREDECESSOR_RELATIVE):
        source = ROOT / relative
        target = nested_root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o600)

    sources, identity = _verify(nested_root)
    observed = nested_root.stat()
    assert identity == (observed.st_dev, observed.st_ino)
    assert set(sources) == set(RUNTIME_PATHS)


def test_consistent_runtime_manifest_regeneration_accepts_tracked_source_change(
    tmp_path: Path,
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    _rewrite_registry_and_mutable_manifest(copied_root)
    sources, _identity = _verify(copied_root)
    assert sources[REGISTRY_RELATIVE] == (copied_root / REGISTRY_RELATIVE).read_bytes()


def test_git_commit_state_does_not_authorize_or_block_runtime_manifest(
    tmp_path: Path,
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    _rewrite_registry_and_mutable_manifest(copied_root)
    _git(copied_root, "add", "--", MANIFEST_RELATIVE)
    _git(
        copied_root,
        "-c",
        "user.name=RAOS Test",
        "-c",
        "user.email=raos@example.invalid",
        "commit",
        "-q",
        "-m",
        "manifest only",
    )
    sources, _identity = _verify(copied_root)
    assert sources[LOCATOR_RELATIVE] == (copied_root / LOCATOR_RELATIVE).read_bytes()


@pytest.mark.parametrize("replacement", ["symlink", "directory", "oversize"])
def test_manifest_must_be_bounded_regular_nonsymlink(
    tmp_path: Path, replacement: str
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    manifest = copied_root / MANIFEST_RELATIVE
    if replacement == "symlink":
        detached = manifest.with_name("detached-manifest.json")
        shutil.copyfile(manifest, detached)
        manifest.unlink()
        manifest.symlink_to(detached.name)
    elif replacement == "directory":
        manifest.unlink()
        manifest.mkdir(mode=0o700)
    else:
        manifest.write_bytes(b"x" * (cast(int, CLI["MAX_MANIFEST_BYTES"]) + 1))

    with pytest.raises(_runtime_failure()) as captured:
        _verify(copied_root)
    assert str(captured.value) == "OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID"


def test_committed_manifest_cannot_list_itself_or_an_extra_runtime(
    tmp_path: Path,
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    manifest_path = copied_root / MANIFEST_RELATIVE
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    manifest["paths"].append(
        {
            "bytes": len(raw),
            "path": MANIFEST_RELATIVE,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _commit(copied_root, "invalid extra runtime")

    with pytest.raises(_runtime_failure()) as captured:
        _verify(copied_root)
    assert str(captured.value) == "OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID"


def test_st1703_predecessor_bytes_are_not_a_runtime_gate(tmp_path: Path) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    predecessor = copied_root / PREDECESSOR_RELATIVE
    predecessor.write_bytes(predecessor.read_bytes() + b" ")

    sources, _identity = _verify(copied_root)
    assert set(sources) == set(RUNTIME_PATHS)


def test_verified_module_and_registry_bytes_survive_post_verify_worktree_swap(
    tmp_path: Path,
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    sources, identity = _verify(copied_root)
    _rewrite_registry_and_mutable_manifest(copied_root)
    adapter_path = (
        copied_root / "python/raos/adapters/self_hosted_editorial_source_capture.py"
    )
    adapter_path.write_text("raise RuntimeError('unverified worktree code')\n")

    module_paths = cast(tuple[tuple[str, str], ...], CLI["_MODULE_PATHS"])
    package_names = cast(tuple[str, ...], CLI["_PACKAGE_NAMES"])
    runtime_names = {*package_names, *(name for name, _path in module_paths)}
    saved_modules = {name: sys.modules.get(name) for name in runtime_names}
    previous_root = CLI_GLOBALS["REPOSITORY_ROOT"]
    try:
        for name in runtime_names:
            sys.modules.pop(name, None)
        CLI_GLOBALS["REPOSITORY_ROOT"] = copied_root
        loader = cast(
            Callable[[dict[str, bytes]], dict[str, types.ModuleType]],
            CLI_GLOBALS["_load_verified_modules"],
        )
        modules = loader(sources)
        capture = modules["raos.adapters.self_hosted_editorial_source_capture"]
        binder = cast(
            Callable[[types.ModuleType, dict[str, bytes], tuple[int, int]], None],
            CLI_GLOBALS["_bind_verified_source_documents"],
        )
        binder(capture, sources, identity)
        load_plan = cast(
            Callable[[Path], object], getattr(capture, "load_source_capture_plan")
        )
        plan = load_plan(copied_root)
    finally:
        CLI_GLOBALS["REPOSITORY_ROOT"] = previous_root
        for name in runtime_names:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    target = cast(Callable[[str], _SourceTarget], getattr(plan, "target"))
    c300 = target("SRC-ANKER-SOLIX-C300")
    assert c300.url == "https://www.ankerjapan.com/products/a1722"
    assert "ankerjapan.net" not in c300.url


def test_documented_isolated_python_process_accepts_stage_zero() -> None:
    program = (
        "import runpy; "
        "namespace=runpy.run_path('scripts/st1704_official_source_capture.py'); "
        "namespace['_verify_stage_zero'](); "
        "print('OFFICIAL_SOURCE_CAPTURE_STAGE_ZERO_OK')"
    )
    completed = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            "-c",
            program,
        ],
        cwd=ROOT,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_PROCESS_ENVIRONMENT,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stdout == "OFFICIAL_SOURCE_CAPTURE_STAGE_ZERO_OK\n"
    assert completed.stderr == ""


def test_unsafe_ambient_python_process_refuses_before_runtime_verification(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    verification_calls = 0

    def verify(_root: Path) -> tuple[dict[str, bytes], tuple[int, int]]:
        nonlocal verification_calls
        verification_calls += 1
        raise AssertionError("unsafe process must stop before manifest verification")

    monkeypatch.setitem(CLI_GLOBALS, "_verify_runtime_integrity", verify)
    main = cast(Callable[[list[str] | None], int], CLI["main"])
    status = main(["capture-source", "--source-ref", "SRC-ANKER-SOLIX-C300"])

    captured = capfd.readouterr()
    assert status == 1
    assert verification_calls == 0
    refusal = json.loads(captured.err)
    assert refusal["error"] == "OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID"
    assert refusal["status"] == "REFUSED"
    assert "manifest" not in captured.err.casefold()
    assert captured.out == ""
