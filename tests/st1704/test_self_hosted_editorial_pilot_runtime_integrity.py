"""Stage-zero integrity tests for the closed ST-1704 WordPress CLI."""

from __future__ import annotations

import ast
import hashlib
import http.client
import json
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
import types
from typing import Any, Callable, cast

import pytest

import raos.adapters.self_hosted_editorial_pilot_json as json_adapter_module
import raos.adapters.self_hosted_wordpress_credentials as credential_module


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts/st1704_self_hosted_editorial_pilot.py"
SOURCE_CLI_PATH = ROOT / "scripts/st1704_official_source_capture.py"
CLI = runpy.run_path(str(CLI_PATH))
CLI_GLOBALS = cast(types.FunctionType, CLI["_load_verified_runtime"]).__globals__
SOURCE_CLI = runpy.run_path(str(SOURCE_CLI_PATH))
RUNTIME_PATHS = cast(tuple[str, ...], SOURCE_CLI["EXPECTED_RUNTIME_PATHS"])
MANIFEST_RELATIVE = cast(str, CLI["MANIFEST_RELATIVE"])
PREDECESSOR_RELATIVE = cast(str, SOURCE_CLI["PREDECESSOR_RELATIVE"])
DEPENDENCY_RELATIVE = "python/raos/adapters/self_hosted_wordpress_credentials.py"
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


def _commit(root: Path, message: str, *paths: str) -> None:
    _git(root, "add", "--", *(paths or (".",)))
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
    for relative in (*RUNTIME_PATHS, MANIFEST_RELATIVE, PREDECESSOR_RELATIVE):
        source = ROOT / relative
        target = copied_root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o600)
    _git(copied_root, "init", "-q")
    _commit(copied_root, "baseline")
    return copied_root


def _rewrite_dependency_and_manifest(root: Path) -> None:
    dependency_path = root / DEPENDENCY_RELATIVE
    dependency = dependency_path.read_bytes() + b"\n# unreviewed dependency drift\n"
    dependency_path.write_bytes(dependency)
    manifest_path = root / MANIFEST_RELATIVE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matches = [row for row in manifest["paths"] if row["path"] == DEPENDENCY_RELATIVE]
    assert len(matches) == 1
    matches[0]["bytes"] = len(dependency)
    matches[0]["sha256"] = hashlib.sha256(dependency).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load(root: Path) -> tuple[dict[str, bytes], tuple[int, int]]:
    previous_root = CLI_GLOBALS["REPOSITORY_ROOT"]
    try:
        CLI_GLOBALS["REPOSITORY_ROOT"] = root
        return cast(
            Callable[[], tuple[dict[str, bytes], tuple[int, int]]],
            CLI["_load_verified_runtime"],
        )()
    finally:
        CLI_GLOBALS["REPOSITORY_ROOT"] = previous_root


def _forbid_post_stage_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    calls = {
        "credential": 0,
        "dns": 0,
        "http": 0,
        "journal": 0,
        "loader": 0,
        "run": 0,
        "site": 0,
    }

    def forbidden(name: str) -> Callable[..., object]:
        def call(*_args: object, **_kwargs: object) -> object:
            calls[name] += 1
            raise AssertionError(f"{name} must remain unreachable")

        return call

    monkeypatch.setitem(CLI_GLOBALS, "_enable_site_packages", forbidden("site"))
    monkeypatch.setitem(CLI_GLOBALS, "_load_verified_modules", forbidden("loader"))
    monkeypatch.setitem(CLI_GLOBALS, "_run", forbidden("run"))
    monkeypatch.setattr(
        credential_module,
        "OwnerPrivateSelfHostedWordPressCredentialStore",
        forbidden("credential"),
    )
    monkeypatch.setattr(
        json_adapter_module,
        "OwnerPrivateLiveReviewDraftJournal",
        forbidden("journal"),
    )
    monkeypatch.setattr(socket, "getaddrinfo", forbidden("dns"))
    monkeypatch.setattr(http.client, "HTTPSConnection", forbidden("http"))
    return calls


def _invoke_refusal(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> dict[str, int]:
    calls = _forbid_post_stage_zero(monkeypatch)
    monkeypatch.setitem(CLI_GLOBALS, "_verify_stage_zero", lambda: None)
    monkeypatch.setitem(CLI_GLOBALS, "REPOSITORY_ROOT", root)
    main = cast(Callable[[list[str] | None], int], CLI["main"])
    status = main(["prepare", "--article-id", "st1704-portable-power-station-guide"])
    captured = capfd.readouterr()
    assert status == 1
    assert captured.out == ""
    refusal = json.loads(captured.err)
    assert refusal == {
        "article_id": "st1704-portable-power-station-guide",
        "command": "prepare",
        "error": "SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID",
        "production_evidence": False,
        "publication_authority": False,
        "status": "REFUSED",
    }
    return calls


def test_stage_zero_source_has_no_top_level_raos_import_or_path_mutation() -> None:
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
        < main.index("_load_verified_runtime()")
        < main.index("_enable_site_packages(root_identity)")
        < main.index("_load_verified_modules(sources, root_identity)")
        < main.index("_run(")
    )


def test_exact_head_bound_runtime_verifies_all_committed_bytes(tmp_path: Path) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    sources, identity = _load(copied_root)
    observed = copied_root.stat()
    assert identity == (observed.st_dev, observed.st_ino)
    assert set(sources) == set(RUNTIME_PATHS)
    assert (
        sources[DEPENDENCY_RELATIVE] == (copied_root / DEPENDENCY_RELATIVE).read_bytes()
    )


def test_external_dependency_cannot_prepopulate_raos_before_verified_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    sources, identity = _load(copied_root)
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "raos" or name.startswith("raos.")
    }
    previous_root = CLI_GLOBALS["REPOSITORY_ROOT"]
    saved_meta_path = list(sys.meta_path)
    baseline_meta_path = cast(
        Any, list(cast(tuple[object, ...], CLI["_BASELINE_META_PATH"]))
    )
    imported = cast(types.ModuleType, CLI_GLOBALS["importlib"])
    original_import = cast(Callable[[str], types.ModuleType], imported.import_module)
    # Load the fixed external set before replacing ``importlib.import_module``.
    # Otherwise a first import can retain the test injector as a module-local
    # alias after monkeypatch teardown and contaminate the following test.
    for dependency in cast(tuple[str, ...], CLI["_EXTERNAL_DEPENDENCIES"]):
        original_import(dependency)
    loader_calls = 0

    def injecting_import(name: str) -> types.ModuleType:
        if name == "pydantic":
            injected = "raos.adapters.self_hosted_wordpress_credentials"
            sys.modules[injected] = types.ModuleType(injected)
        return original_import(name)

    def forbidden_loader(_sources: object) -> object:
        nonlocal loader_calls
        loader_calls += 1
        raise AssertionError("verified loader must remain unreachable")

    try:
        for name in saved_modules:
            sys.modules.pop(name, None)
        sys.meta_path[:] = baseline_meta_path
        CLI_GLOBALS["REPOSITORY_ROOT"] = copied_root
        monkeypatch.setattr(imported, "import_module", injecting_import)
        monkeypatch.setitem(CLI_GLOBALS, "_VerifiedSourceLoader", forbidden_loader)
        with pytest.raises(Exception) as refusal:
            cast(Callable[..., object], CLI["_load_verified_modules"])(
                sources, identity
            )
        assert str(refusal.value) == "SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID"
        assert loader_calls == 0
    finally:
        sys.meta_path[:] = saved_meta_path
        CLI_GLOBALS["REPOSITORY_ROOT"] = previous_root
        for name in tuple(sys.modules):
            if name == "raos" or name.startswith("raos."):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


def test_dirty_dependency_and_regenerated_mutable_manifest_refuse_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    _rewrite_dependency_and_manifest(copied_root)
    calls = _invoke_refusal(copied_root, monkeypatch, capfd)
    assert set(calls.values()) == {0}


def test_manifest_only_partial_commit_cannot_authorize_dirty_dependency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    committed_dependency = _git(copied_root, "show", f"HEAD:{DEPENDENCY_RELATIVE}")
    _rewrite_dependency_and_manifest(copied_root)
    _commit(copied_root, "manifest only", MANIFEST_RELATIVE)
    assert (copied_root / DEPENDENCY_RELATIVE).read_bytes() != committed_dependency
    assert (
        _git(copied_root, "show", f"HEAD:{DEPENDENCY_RELATIVE}") == committed_dependency
    )
    calls = _invoke_refusal(copied_root, monkeypatch, capfd)
    assert set(calls.values()) == {0}


def test_unmanifested_transitive_live_dependency_drift_refuses_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    dependency = copied_root / DEPENDENCY_RELATIVE
    dependency.write_bytes(dependency.read_bytes() + b"\n# drift\n")
    calls = _invoke_refusal(copied_root, monkeypatch, capfd)
    assert set(calls.values()) == {0}


def test_verified_modules_and_tracked_documents_survive_post_verify_swap(
    tmp_path: Path,
) -> None:
    copied_root = _copy_committed_runtime(tmp_path)
    sources, identity = _load(copied_root)
    changed = {
        DEPENDENCY_RELATIVE: b"raise RuntimeError('unverified credential code')\n",
        "python/raos/application/editorial/self_hosted_editorial_pilot.py": b"raise RuntimeError('unverified application code')\n",
        "python/raos/generated/contracts/content_ast.py": b"raise RuntimeError('unverified generated code')\n",
        "contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json": b"{}\n",
        "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json": b"{}\n",
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json": b"{}\n",
        "changes/st-1704/self-hosted-editorial-pilot-v1/media/product-media-registry.v1.json": b"{}\n",
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/theme-contract.v1.json": b"{}\n",
    }
    for relative, raw in changed.items():
        (copied_root / relative).write_bytes(raw)

    package_names = cast(tuple[str, ...], CLI["_PACKAGE_NAMES"])
    module_paths = cast(tuple[tuple[str, str], ...], CLI["_MODULE_PATHS"])
    generated_names = {
        relative.removeprefix("python/")
        .removesuffix("/__init__.py")
        .removesuffix(".py")
        .replace("/", ".")
        for relative in RUNTIME_PATHS
        if relative.startswith("python/raos/generated/contracts/")
        and relative.endswith(".py")
    }
    runtime_names = {
        *package_names,
        *(name for name, _relative in module_paths),
        *generated_names,
    }
    runtime_names.update(
        name for name in sys.modules if name == "raos" or name.startswith("raos.")
    )
    saved_modules = {name: sys.modules.get(name) for name in runtime_names}
    stage_zero_names = ("site", "sitecustomize", "usercustomize")
    saved_stage_zero_modules = {
        name: sys.modules.get(name) for name in stage_zero_names
    }
    saved_meta_path = list(sys.meta_path)
    baseline_meta_path = cast(
        Any, list(cast(tuple[object, ...], CLI["_BASELINE_META_PATH"]))
    )
    previous_root = CLI_GLOBALS["REPOSITORY_ROOT"]
    try:
        for name in runtime_names:
            sys.modules.pop(name, None)
        for name in stage_zero_names:
            sys.modules.pop(name, None)
        sys.meta_path[:] = baseline_meta_path
        CLI_GLOBALS["REPOSITORY_ROOT"] = copied_root
        modules = cast(
            dict[str, types.ModuleType],
            cast(Callable[..., object], CLI["_load_verified_modules"])(
                sources, identity
            ),
        )
        cast(Callable[..., None], CLI["_bind_verified_tracked_reads"])(
            modules, sources, identity
        )
        module_seal = cast(
            dict[str, dict[str, object]],
            cast(Callable[..., object], CLI["_seal_verified_modules"])(modules),
        )
        with pytest.raises(Exception) as refusal:
            cast(Callable[..., object], CLI["_run"])(
                "prepare",
                "st1704-portable-power-station-guide",
                modules=modules,
                root_identity=identity,
                module_seal=module_seal,
            )
        assert str(refusal.value) == "RESOURCE_NOT_READY"
        https_module = modules["raos.adapters.self_hosted_editorial_pilot_https"]
        adapter_type = getattr(
            https_module, "OfficialSelfHostedEditorialPilotWordPressAdapter"
        )
        adapter = adapter_type(copied_root)
        assert adapter.__class__.__module__ == (
            "raos.adapters.self_hosted_editorial_pilot_https"
        )
        replaced_name = "raos.adapters.self_hosted_wordpress_credentials"
        sys.modules[replaced_name] = types.ModuleType(replaced_name)
        with pytest.raises(Exception) as provenance_refusal:
            cast(Callable[..., object], CLI["_run"])(
                "prepare",
                "st1704-portable-power-station-guide",
                modules=modules,
                root_identity=identity,
                module_seal=module_seal,
            )
        assert str(provenance_refusal.value) == (
            "SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID"
        )
    finally:
        sys.meta_path[:] = saved_meta_path
        CLI_GLOBALS["REPOSITORY_ROOT"] = previous_root
        for name in runtime_names:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module
        for name in stage_zero_names:
            sys.modules.pop(name, None)
        for name, module in saved_stage_zero_modules.items():
            if module is not None:
                sys.modules[name] = module


def test_documented_direct_python_process_accepts_stage_zero(tmp_path: Path) -> None:
    probe_root = tmp_path / "direct-process"
    probe_script = probe_root / "scripts/st1704_self_hosted_editorial_pilot.py"
    probe_python = probe_root / ".venv/bin/python"
    probe_script.parent.mkdir(mode=0o700, parents=True)
    probe_python.parent.mkdir(mode=0o700, parents=True)
    probe_python.symlink_to(ROOT / ".venv/bin/python")
    source = CLI_PATH.read_text(encoding="utf-8")
    entrypoint = 'if __name__ == "__main__":\n    raise SystemExit(main())\n'
    assert source.count(entrypoint) == 1
    probe_script.write_text(
        source.replace(
            entrypoint,
            'if __name__ == "__main__":\n'
            "    _verify_stage_zero()\n"
            '    print("SELF_HOSTED_EDITORIAL_PILOT_STAGE_ZERO_OK")\n',
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            str(probe_python),
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            "scripts/st1704_self_hosted_editorial_pilot.py",
        ],
        cwd=probe_root,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_PROCESS_ENVIRONMENT,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stdout == "SELF_HOSTED_EDITORIAL_PILOT_STAGE_ZERO_OK\n"
    assert completed.stderr == ""


def test_runpy_process_and_injected_path_refuse_stage_zero() -> None:
    program = (
        "import runpy,sys; "
        "sys.path.insert(0,'/tmp/unverified'); "
        "namespace=runpy.run_path('scripts/st1704_self_hosted_editorial_pilot.py'); "
        "refusal=''; "
        "\ntry: namespace['_verify_stage_zero']()\n"
        "except RuntimeError as error: refusal=str(error)\n"
        "print(refusal)"
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
    assert completed.stdout == "SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID\n"
    assert completed.stderr == ""


def test_unsafe_process_refuses_before_manifest_loader_and_all_live_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    calls = _forbid_post_stage_zero(monkeypatch)
    verification_calls = 0

    def verify() -> tuple[dict[str, bytes], tuple[int, int]]:
        nonlocal verification_calls
        verification_calls += 1
        raise AssertionError("unsafe process must stop before manifest verification")

    monkeypatch.setitem(CLI_GLOBALS, "_load_verified_runtime", verify)
    main = cast(Callable[[list[str] | None], int], CLI["main"])
    status = main(["prepare", "--article-id", "st1704-portable-power-station-guide"])
    captured = capfd.readouterr()
    assert status == 1
    assert verification_calls == 0
    assert set(calls.values()) == {0}
    assert json.loads(captured.err)["error"] == (
        "SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID"
    )
    assert captured.out == ""
