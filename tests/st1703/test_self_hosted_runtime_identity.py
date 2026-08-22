"""Reviewed-byte runtime binding for the self-hosted owner-local entry."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts/self_hosted_wordpress.py"
GENERATOR_PATH = ROOT / "scripts/build_st1703_self_hosted_runtime_manifest.py"
MANIFEST_PATH = (
    ROOT / "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
PYTHON_INVENTORY_PATH = (
    ROOT / "changes/st-1703/self-hosted-minimum-start-v1/"
    "python-runtime-code-inventory.v1.sha256"
)
SHIPPED_PR_BASE = "b5a6157b878ca0435ee4120d33162aba5ae51f77"
BRANCH_LOCAL_REVIEW_COMMIT = "7598e127adee6027d086619a720071a550b7a290"


def _load(path: Path, name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["/usr/bin/git", *arguments],
        cwd=repository,
        env={
            "GIT_AUTHOR_EMAIL": "runtime@example.invalid",
            "GIT_AUTHOR_NAME": "Runtime Test",
            "GIT_COMMITTER_EMAIL": "runtime@example.invalid",
            "GIT_COMMITTER_NAME": "Runtime Test",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


def _identity_repository(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, str]:
    repository = tmp_path / "identity-repository"
    runtime = repository / "runtime.py"
    unrelated = repository / "unrelated.txt"
    manifest = repository / "runtime-manifest.json"
    script = repository / "scripts/self_hosted_wordpress.py"
    script.parent.mkdir(parents=True)
    runtime.write_bytes(b"runtime-v1\n")
    unrelated.write_bytes(b"unrelated\n")
    script.write_bytes(CLI_PATH.read_bytes())
    runtime_inputs = (runtime, script)
    manifest_value = {
        "approved_base_commit": "PLACEHOLDER",
        "external_action_authority": "NONE",
        "generated_by": "scripts/build_st1703_self_hosted_runtime_manifest.py",
        "paths": [
            {
                "bytes": len(path.read_bytes()),
                "path": path.relative_to(repository).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in runtime_inputs
        ],
        "repository_development_authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
        "schema": "SELF_HOSTED_WORDPRESS_RUNTIME_MANIFEST_V1",
        "slice_id": "SELF_HOSTED_MINIMUM_START_V1",
        "story_id": "ST-1703",
    }
    assert _git(repository, "init", "-q").returncode == 0
    manifest.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    assert _git(repository, "add", ".").returncode == 0
    assert _git(repository, "commit", "-qm", "base").returncode == 0
    base = _git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    manifest_value["approved_base_commit"] = base
    manifest.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    assert _git(repository, "add", ".").returncode == 0
    assert _git(repository, "commit", "-qm", "manifest").returncode == 0
    monkeypatch.setattr(module, "_EXPECTED_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(module, "_RUNTIME_MANIFEST_PATH", Path("runtime-manifest.json"))
    monkeypatch.setattr(
        module,
        "_RUNTIME_REQUIRED_PATHS",
        ("runtime.py", "scripts/self_hosted_wordpress.py"),
    )
    monkeypatch.setattr(module, "_RUNTIME_APPROVED_BASE_COMMIT", base)
    monkeypatch.setattr(module, "_valid_runtime_python", lambda: True)
    monkeypatch.setattr(module, "_valid_runtime_entry", lambda: True)
    return repository, runtime, manifest, base


def _stage_binding(repository: Path) -> dict[str, str]:
    stage_head = _git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    stage_cli_blob = (
        _git(
            repository,
            "rev-parse",
            f"{stage_head}:scripts/self_hosted_wordpress.py",
        )
        .stdout.decode()
        .strip()
    )
    stage_cli_sha256 = hashlib.sha256(
        (repository / "scripts/self_hosted_wordpress.py").read_bytes()
    ).hexdigest()
    return {
        "stage_head": stage_head,
        "stage_cli_blob": stage_cli_blob,
        "stage_cli_sha256": stage_cli_sha256,
    }


def _fetch_shipped_pr_base(repository: Path) -> None:
    result = _git(
        repository,
        "-c",
        "protocol.file.allow=always",
        "fetch",
        "--quiet",
        "--no-tags",
        str(ROOT),
        f"{SHIPPED_PR_BASE}:refs/heads/shipped-pr-base",
    )
    assert result.returncode == 0, result.stderr


def _synthetic_squash_repository(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    repository = tmp_path / "synthetic-squash-repository"
    repository.mkdir()
    assert _git(repository, "init", "-q").returncode == 0
    _fetch_shipped_pr_base(repository)
    assert (
        _git(
            repository,
            "checkout",
            "-qb",
            "synthetic-squash",
            "refs/heads/shipped-pr-base",
        ).returncode
        == 0
    )
    runtime = repository / "runtime.py"
    manifest = repository / "runtime-manifest.json"
    script = repository / "scripts/self_hosted_wordpress.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(b"synthetic squashed runtime\n")
    script.write_bytes(CLI_PATH.read_bytes())
    runtime_inputs = (runtime, script)
    manifest_value = {
        "approved_base_commit": SHIPPED_PR_BASE,
        "external_action_authority": "NONE",
        "generated_by": "scripts/build_st1703_self_hosted_runtime_manifest.py",
        "paths": [
            {
                "bytes": len(path.read_bytes()),
                "path": path.relative_to(repository).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in runtime_inputs
        ],
        "repository_development_authority": ("ROOT_STANDING_DEVELOPMENT_AUTHORIZATION"),
        "schema": "SELF_HOSTED_WORDPRESS_RUNTIME_MANIFEST_V1",
        "slice_id": "SELF_HOSTED_MINIMUM_START_V1",
        "story_id": "ST-1703",
    }
    manifest.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    assert _git(repository, "add", ".").returncode == 0
    assert _git(repository, "commit", "-qm", "synthetic squash").returncode == 0
    monkeypatch.setattr(module, "_EXPECTED_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(module, "_RUNTIME_MANIFEST_PATH", Path("runtime-manifest.json"))
    monkeypatch.setattr(
        module,
        "_RUNTIME_REQUIRED_PATHS",
        ("runtime.py", "scripts/self_hosted_wordpress.py"),
    )
    monkeypatch.setattr(module, "_valid_runtime_python", lambda: True)
    monkeypatch.setattr(module, "_valid_runtime_entry", lambda: True)
    return repository


def test_runtime_identity_exact_clean_head_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(CLI_PATH, "self_hosted_runtime_identity_pass")
    repository, _, _, _ = _identity_repository(module, tmp_path, monkeypatch)
    module._verify_self_hosted_runtime_identity(
        repository, **_stage_binding(repository)
    )


def test_runtime_lineage_accepts_synthetic_squash_above_shipped_pr_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, "self_hosted_runtime_shipped_base_squash")
    assert module._RUNTIME_APPROVED_BASE_COMMIT == SHIPPED_PR_BASE
    repository = _synthetic_squash_repository(module, tmp_path, monkeypatch)
    head = _git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    assert (
        _git(repository, "rev-parse", "HEAD^").stdout.decode().strip()
        == SHIPPED_PR_BASE
    )
    assert (
        _git(
            repository, "merge-base", "--is-ancestor", SHIPPED_PR_BASE, head
        ).returncode
        == 0
    )
    assert (
        _git(
            repository, "cat-file", "-e", f"{BRANCH_LOCAL_REVIEW_COMMIT}^{{commit}}"
        ).returncode
        != 0
    )
    module._verify_self_hosted_runtime_identity(
        repository, **_stage_binding(repository)
    )


def test_runtime_lineage_rejects_unrelated_history_with_shipped_base_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, "self_hosted_runtime_unrelated_shipped_base")
    assert module._RUNTIME_APPROVED_BASE_COMMIT == SHIPPED_PR_BASE
    repository = _synthetic_squash_repository(module, tmp_path, monkeypatch)
    reviewed_tree = _git(repository, "rev-parse", "HEAD^{tree}").stdout.decode().strip()
    unrelated_head = (
        _git(repository, "commit-tree", reviewed_tree, "-m", "unrelated root")
        .stdout.decode()
        .strip()
    )
    assert len(unrelated_head) == 40
    assert (
        _git(repository, "checkout", "-q", "--detach", unrelated_head).returncode == 0
    )
    assert (
        _git(repository, "rev-parse", "HEAD^{tree}").stdout.decode().strip()
        == reviewed_tree
    )
    assert (
        _git(repository, "cat-file", "-e", f"{SHIPPED_PR_BASE}^{{commit}}").returncode
        == 0
    )
    assert (
        _git(
            repository, "merge-base", "--is-ancestor", SHIPPED_PR_BASE, "HEAD"
        ).returncode
        != 0
    )
    reads: list[object] = []

    def forbidden_read(*args: object, **kwargs: object) -> bytes:
        del args, kwargs
        reads.append("payload")
        raise AssertionError("unrelated lineage reached manifest payload")

    monkeypatch.setattr(module, "_read_runtime_file", forbidden_read)
    with pytest.raises(module._RuntimeIdentityFailure):
        module._verify_self_hosted_runtime_identity(
            repository, **_stage_binding(repository)
        )
    assert reads == []
    assert not (repository / ".secrets").exists()


@pytest.mark.parametrize("field", ["stage_head", "stage_cli_blob"])
def test_runtime_identity_rejects_stage_discontinuity_before_manifest_read(
    field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, f"self_hosted_runtime_stage_{field}")
    repository, _, _, _ = _identity_repository(module, tmp_path, monkeypatch)
    binding = _stage_binding(repository)
    binding[field] = "f" * len(binding[field])
    reads: list[object] = []

    def forbidden_read(*args: object, **kwargs: object) -> bytes:
        del args, kwargs
        reads.append("payload")
        raise AssertionError("stage discontinuity reached repository payload")

    monkeypatch.setattr(module, "_read_runtime_file", forbidden_read)
    with pytest.raises(module._RuntimeIdentityFailure):
        module._verify_self_hosted_runtime_identity(repository, **binding)
    assert reads == []


def test_runtime_identity_rejects_stage_cli_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, "self_hosted_runtime_stage_cli_digest")
    repository, _, _, _ = _identity_repository(module, tmp_path, monkeypatch)
    binding = _stage_binding(repository)
    binding["stage_cli_sha256"] = "f" * 64
    with pytest.raises(module._RuntimeIdentityFailure):
        module._verify_self_hosted_runtime_identity(repository, **binding)
    assert not (repository / ".secrets").exists()


@pytest.mark.parametrize(
    "case",
    [
        "dirty",
        "staged",
        "untracked",
        "manifest-mismatch",
        "non-ancestor",
        "skip-worktree",
        "unrelated-skip-worktree",
        "unrelated-assume-unchanged",
    ],
)
def test_runtime_identity_drift_fails_before_secret_or_network(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, f"self_hosted_runtime_identity_{case}")
    repository, runtime, manifest, _ = _identity_repository(
        module, tmp_path, monkeypatch
    )
    if case == "dirty":
        runtime.write_bytes(b"runtime-dirty\n")
    elif case == "staged":
        runtime.write_bytes(b"runtime-staged\n")
        assert _git(repository, "add", "runtime.py").returncode == 0
    elif case == "untracked":
        (repository / "unreviewed.py").write_bytes(b"raise RuntimeError\n")
    elif case == "manifest-mismatch":
        value = json.loads(manifest.read_text(encoding="ascii"))
        value["paths"][0]["sha256"] = "0" * 64
        manifest.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="ascii",
        )
    elif case == "non-ancestor":
        monkeypatch.setattr(module, "_RUNTIME_APPROVED_BASE_COMMIT", "f" * 40)
    elif case == "skip-worktree":
        assert (
            _git(repository, "update-index", "--skip-worktree", "runtime.py").returncode
            == 0
        )
        runtime.write_bytes(b"runtime-hidden-dirty\n")
    elif case == "unrelated-skip-worktree":
        assert (
            _git(
                repository, "update-index", "--skip-worktree", "unrelated.txt"
            ).returncode
            == 0
        )
    else:
        assert (
            _git(
                repository, "update-index", "--assume-unchanged", "unrelated.txt"
            ).returncode
            == 0
        )
    with pytest.raises(module._RuntimeIdentityFailure):
        module._verify_self_hosted_runtime_identity(
            repository, **_stage_binding(repository)
        )
    assert not (repository / ".secrets").exists()


def test_manifest_path_inventory_is_closed_before_any_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, "self_hosted_runtime_manifest_path_gate")
    repository, _, manifest, _ = _identity_repository(module, tmp_path, monkeypatch)
    secret = repository / ".secrets/wordpress-owner-local/credentials.v1.json"
    secret.parent.mkdir(parents=True, mode=0o700)
    secret.write_bytes(b"synthetic credential bytes that must not be opened\n")
    secret.chmod(0o600)
    value = json.loads(manifest.read_text(encoding="ascii"))
    value["paths"][0]["path"] = secret.relative_to(repository).as_posix()
    manifest.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    original_read = module._read_runtime_file
    opened: list[str] = []

    def traced_read(
        repository_root: Path,
        relative: object,
        *,
        maximum_bytes: int,
    ) -> bytes:
        opened.append(str(relative))
        return original_read(
            repository_root,
            relative,
            maximum_bytes=maximum_bytes,
        )

    monkeypatch.setattr(module, "_read_runtime_file", traced_read)
    with pytest.raises(module._RuntimeIdentityFailure):
        module._verify_self_hosted_runtime_identity(
            repository, **_stage_binding(repository)
        )
    assert opened == ["runtime-manifest.json"]


def test_runtime_reader_rejects_symlinked_ancestor_before_leaf_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(CLI_PATH, "self_hosted_runtime_descriptor_reader")
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "credential.json").write_bytes(b"synthetic private value\n")
    (repository / "linked").symlink_to(outside, target_is_directory=True)
    original_open = module.os.open
    opened_names: list[str] = []

    def traced_open(path: object, *args: object, **kwargs: object) -> int:
        opened_names.append(str(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", traced_open)
    with pytest.raises(module._RuntimeIdentityFailure):
        module._read_runtime_file(
            repository,
            Path("linked/credential.json"),
            maximum_bytes=4096,
        )
    assert "credential.json" not in opened_names


def test_runtime_binding_precedes_raos_imports_and_rejects_ambient_raos() -> None:
    source = CLI_PATH.read_text(encoding="utf-8")
    bootstrap_call = (
        'if __name__ == "__main__":\n'
        "    _verified_bootstrap_bytes = _bootstrap_runtime_identity_or_exit()"
    )
    assert source.index(bootstrap_call) < source.index(
        "from raos.adapters.self_hosted_wordpress_credentials import"
    )
    assert source.index("_install_scoped_runtime_packages(") < source.index(
        "from raos.adapters.self_hosted_wordpress_credentials import"
    )
    assert (
        "if not _runtime_authorized:\n"
        "    for _development_import_root in (_SCRIPTS_ROOT, _PYTHON_ROOT):"
    ) in source
    module = _load(CLI_PATH, "self_hosted_runtime_ambient_test")
    with pytest.raises(module._RuntimeIdentityFailure):
        module._install_scoped_runtime_packages(ROOT, {})


def test_scoped_import_closure_is_exact_and_repo_pyc_is_not_opened(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "open.trace"
    code = r"""
import json
from pathlib import Path
import runpy
import sys

root = Path(sys.argv[1])
doctor_root = Path(sys.argv[2])
script = root / "scripts/self_hosted_wordpress.py"
source = script.read_text(encoding="utf-8")
prefix = source.split("_SCRIPT_REPOSITORY_ROOT =", maxsplit=1)[0]
scope = {"__file__": str(script), "__name__": "runtime_prefix_probe"}
exec(compile(prefix, str(script), "exec"), scope)
verified = {
    relative: (root / relative).read_bytes()
    for relative in scope["_RUNTIME_REQUIRED_PATHS"]
}
scope["_install_scoped_runtime_packages"](root, verified)
for name in (
    "raos", "raos.adapters", "raos.application",
    "raos.application.editorial", "raos.domain",
    "raos.domain.editorial", "raos.ports",
):
    package = sys.modules[name]
    assert package.__spec__.name == name
    assert package.__spec__.submodule_search_locations == package.__path__
    parent, separator, child = name.rpartition(".")
    if separator:
        assert getattr(sys.modules[parent], child) is package
sys.path[:0] = [str(root / "scripts"), str(root / "python")]
before = set(sys.modules)
runtime = runpy.run_path(str(script), run_name="runtime_import_probe")
assert sorted(runtime["_parser"]()._subparsers._group_actions[0].choices) == [
    "create-draft", "doctor", "install-credentials"
]
for name in runtime["_RUNTIME_MODULE_PATHS"]:
    leaf = sys.modules[name]
    parent, separator, child = name.rpartition(".")
    if separator:
        assert getattr(sys.modules[parent], child) is leaf
    assert leaf.__loader__.__class__.__name__ == "_VerifiedSourceLoader"
candidate = runtime["load_first_article_candidate"](
    root,
    operation=runtime["SelfHostedWordPressOperation"].CREATE_DRAFT,
    packet_bytes=verified[runtime["_CONTENT_PACKET_RUNTIME_PATH"]],
)
theme_prefix = runtime["_THEME_RUNTIME_PREFIX"]
theme_payloads = {
    path.removeprefix(theme_prefix): payload
    for path, payload in verified.items()
    if path.startswith(theme_prefix)
}
doctor = runtime["_doctor"](
    doctor_root,
    content_packet_bytes=verified[runtime["_CONTENT_PACKET_RUNTIME_PATH"]],
    theme_payloads=theme_payloads,
)
rows = set()
for name in set(sys.modules) - before:
    value = getattr(sys.modules[name], "__file__", None)
    if value is None:
        continue
    path = Path(value).resolve()
    if path.is_relative_to(root):
        if path.suffix == ".pyc" and "__pycache__" in path.parts:
            index = path.parts.index("__pycache__")
            path = Path(*path.parts[:index], path.name.split(".", maxsplit=1)[0] + ".py")
        rows.add(path.relative_to(root).as_posix())
print(json.dumps({
    "content_sha256": candidate.content_sha256,
    "doctor": doctor,
    "operation_sha256": candidate.operation_sha256,
    "paths": sorted(rows),
    "title": candidate.title,
}, ensure_ascii=True, sort_keys=True))
"""
    result = subprocess.run(
        [
            "/usr/bin/strace",
            "-f",
            "-e",
            "trace=openat",
            "-o",
            str(trace),
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            "-c",
            code,
            str(ROOT),
            str(tmp_path / "doctor-root"),
        ],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    evidence = json.loads(result.stdout)
    assert evidence["paths"] == [
        "python/raos/adapters/self_hosted_wordpress_credentials.py",
        "python/raos/adapters/self_hosted_wordpress_https.py",
        "python/raos/adapters/self_hosted_wordpress_journal.py",
        "python/raos/adapters/self_hosted_wordpress_rest.py",
        "python/raos/adapters/wordpress_rest.py",
        "python/raos/application/editorial/self_hosted_minimum_start.py",
        "python/raos/domain/editorial/market_learning_pilot.py",
        "python/raos/domain/editorial/self_hosted_wordpress.py",
        "python/raos/ports/self_hosted_wordpress.py",
        "scripts/build_st1703_self_hosted_theme.py",
    ]
    ordinary = _load(CLI_PATH, "self_hosted_runtime_parity_test")
    packet = (ROOT / ordinary._CONTENT_PACKET_RUNTIME_PATH).read_bytes()
    candidate = ordinary.load_first_article_candidate(
        ROOT,
        operation=ordinary.SelfHostedWordPressOperation.CREATE_DRAFT,
        packet_bytes=packet,
    )
    assert evidence["title"] == candidate.title
    assert evidence["content_sha256"] == candidate.content_sha256
    assert evidence["operation_sha256"] == candidate.operation_sha256
    assert evidence["doctor"]["credential_value_reads"] == 0
    assert evidence["doctor"]["network_requests"] == 0
    trace_text = trace.read_text(encoding="utf-8")
    assert ".pth" not in trace_text
    pyc_opens = [
        line
        for line in trace_text.splitlines()
        if str(ROOT) in line and "__pycache__" in line and ".pyc" in line
    ]
    assert pyc_opens == []


def test_runtime_manifest_generator_check_is_current_and_inventory_matches() -> None:
    manifest_before = MANIFEST_PATH.stat()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    python_inventory_before = PYTHON_INVENTORY_PATH.stat()
    python_inventory_bytes = PYTHON_INVENTORY_PATH.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            str(GENERATOR_PATH),
            "--check",
        ],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    manifest_after = MANIFEST_PATH.stat()
    python_inventory_after = PYTHON_INVENTORY_PATH.stat()
    assert MANIFEST_PATH.read_bytes() == manifest_bytes
    assert (
        manifest_after.st_dev,
        manifest_after.st_ino,
        manifest_after.st_size,
        manifest_after.st_mtime_ns,
        manifest_after.st_ctime_ns,
    ) == (
        manifest_before.st_dev,
        manifest_before.st_ino,
        manifest_before.st_size,
        manifest_before.st_mtime_ns,
        manifest_before.st_ctime_ns,
    )
    assert PYTHON_INVENTORY_PATH.read_bytes() == python_inventory_bytes
    assert (
        python_inventory_after.st_dev,
        python_inventory_after.st_ino,
        python_inventory_after.st_size,
        python_inventory_after.st_mtime_ns,
        python_inventory_after.st_ctime_ns,
    ) == (
        python_inventory_before.st_dev,
        python_inventory_before.st_ino,
        python_inventory_before.st_size,
        python_inventory_before.st_mtime_ns,
        python_inventory_before.st_ctime_ns,
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="ascii"))
    generator = _load(GENERATOR_PATH, "self_hosted_runtime_generator_test")
    cli = _load(CLI_PATH, "self_hosted_runtime_cli_inventory_test")
    assert generator.render() == manifest_bytes
    assert generator.render() == manifest_bytes
    assert generator.render_python_runtime_inventory() == python_inventory_bytes
    assert generator.render_python_runtime_inventory() == python_inventory_bytes
    paths = tuple(row["path"] for row in manifest["paths"])
    assert paths == tuple(sorted(generator.REQUIRED_RUNTIME_PATHS))
    assert paths == tuple(sorted(cli._RUNTIME_REQUIRED_PATHS))
    assert generator.APPROVED_BASE_COMMIT == SHIPPED_PR_BASE
    assert cli._RUNTIME_APPROVED_BASE_COMMIT == SHIPPED_PR_BASE
    assert manifest["approved_base_commit"] == SHIPPED_PR_BASE
    assert manifest["external_action_authority"] == "NONE"

    inventory_lines = python_inventory_bytes.decode("ascii").splitlines()
    assert inventory_lines[:5] == [
        "# schema=SELF_HOSTED_PYTHON_RUNTIME_CODE_INVENTORY_V1",
        "# generated_by=scripts/build_st1703_self_hosted_runtime_manifest.py",
        "# generate_command=make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile runtime-manifest-generate",
        f"# python_base={generator.PYTHON_BASE.as_posix()}",
        f"# stdlib_root={generator.PYTHON_STDLIB_ROOT.as_posix()}",
    ]
    headers = dict(line[2:].split("=", maxsplit=1) for line in inventory_lines[:22])
    assert inventory_lines[22] == ""
    checksum_rows = inventory_lines[23:]
    assert headers["dynamic_loader_path"] == generator.DYNAMIC_LOADER.as_posix()
    assert headers["system_runtime_file_count"] == str(
        len(generator.SYSTEM_RUNTIME_FILES)
    )
    assert (
        headers["system_runtime_sha256"]
        == hashlib.sha256(generator._system_runtime_material()).hexdigest()
    )
    assert headers["python_rpath_policy"] == "PINNED_LOADER_INHIBIT_RPATH"
    python_bin_inventory = generator._directory_path_inventory(
        generator.PYTHON_BIN_DIRECTORY
    )
    venv_bin_inventory = generator._directory_path_inventory(
        generator.VENV_BIN_DIRECTORY
    )
    assert headers["python_bin_entry_count"] == str(python_bin_inventory[0])
    assert (
        headers["python_bin_path_sha256"]
        == hashlib.sha256(python_bin_inventory[1]).hexdigest()
    )
    assert headers["venv_bin_entry_count"] == str(venv_bin_inventory[0])
    assert (
        headers["venv_bin_path_sha256"]
        == hashlib.sha256(venv_bin_inventory[1]).hexdigest()
    )
    startup_material = b"".join(
        os.fsencode(path) + b"\0" for path in generator.PYTHON_STARTUP_ABSENT_CANDIDATES
    )
    assert headers["python_startup_landmark_candidate_count"] == "4"
    assert (
        headers["python_startup_landmark_path_sha256"]
        == hashlib.sha256(startup_material).hexdigest()
    )
    assert headers["python_startup_landmark_state"] == "ABSENT"
    assert len(checksum_rows) == int(headers["code_file_count"])
    relative_paths: list[str] = []
    for row in checksum_rows:
        digest, absolute = row.split("  ", maxsplit=1)
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")
        relative = Path(absolute).relative_to(generator.PYTHON_STDLIB_ROOT).as_posix()
        assert "site-packages" not in Path(relative).parts
        assert "__pycache__" not in Path(relative).parts
        assert Path(relative).suffix in {".py", ".pyc", ".so"}
        relative_paths.append(relative)
    assert relative_paths == sorted(relative_paths, key=os.fsencode)
    assert len(set(relative_paths)) == len(relative_paths)
    path_material = b"".join(
        b"./" + relative.encode("ascii") + b"\0" for relative in relative_paths
    )
    assert hashlib.sha256(path_material).hexdigest() == headers["code_path_sha256"]
    checksum_check = subprocess.run(
        ["/usr/bin/busybox", "sha256sum", "-cs", "-"],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        input=("\n".join(checksum_rows) + "\n").encode("ascii"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    assert checksum_check.returncode == 0, checksum_check.stderr


def test_python_runtime_inventory_rejects_leading_zip_import_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load(GENERATOR_PATH, "self_hosted_runtime_zip_gate")
    zip_path = tmp_path / "python314.zip"
    zip_path.write_bytes(b"synthetic unreviewed import archive")
    monkeypatch.setattr(generator, "PYTHON_ZIP_PATH", zip_path)
    with pytest.raises(generator.RuntimeManifestFailure):
        generator.render_python_runtime_inventory()


def test_python_runtime_inventory_rejects_startup_landmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load(GENERATOR_PATH, "self_hosted_runtime_startup_gate")
    candidates = tuple(tmp_path / f"candidate-{index}" for index in range(4))
    candidates[2].write_bytes(b"unreviewed startup override\n")
    monkeypatch.setattr(generator, "PYTHON_STARTUP_ABSENT_CANDIDATES", candidates)
    with pytest.raises(generator.RuntimeManifestFailure):
        generator.render_python_runtime_inventory()


def test_pinned_loader_bypasses_owner_rpath_and_observed_landmarks_are_closed(
    tmp_path: Path,
) -> None:
    generator = _load(GENERATOR_PATH, "self_hosted_runtime_loader_probe")
    trace = tmp_path / "loader-open.trace"
    result = subprocess.run(
        [
            "/usr/bin/strace",
            "-f",
            "-s",
            "300",
            "-e",
            "trace=openat",
            "-o",
            str(trace),
            str(generator.DYNAMIC_LOADER),
            "--inhibit-cache",
            "--inhibit-rpath",
            "",
            "--glibc-hwcaps-mask",
            "",
            "--library-path",
            str(generator.SYSTEM_RUNTIME_DIRECTORY),
            "--argv0",
            "/home/minami/rakuten/.venv/bin/python",
            str(generator.PYTHON_EXECUTABLE),
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            "-c",
            "pass",
        ],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    trace_text = trace.read_text(encoding="utf-8")
    opened_landmarks: set[str] = set()
    for line in trace_text.splitlines():
        match = re.search(r'openat\(AT_FDCWD, ("(?:[^"\\]|\\.)*")', line)
        if match is None:
            continue
        opened = json.loads(match.group(1))
        if opened.endswith("._pth") or opened.endswith("pybuilddir.txt"):
            opened_landmarks.add(opened)
    assert opened_landmarks == {
        path.as_posix() for path in generator.PYTHON_STARTUP_ABSENT_CANDIDATES
    }
    owner_library_prefix = f"{generator.PYTHON_BASE.as_posix()}/lib/"
    loader_dependencies = {path.name for path in generator.SYSTEM_RUNTIME_FILES[1:]}
    owner_dependency_opens = [
        line
        for line in trace_text.splitlines()
        if owner_library_prefix in line
        and any(name in line for name in loader_dependencies)
    ]
    assert owner_dependency_opens == []
