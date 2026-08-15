from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import yaml

from scripts import build_st1605_failure_injection_drill as builder

base = builder.base


_CREDENTIAL_ENVIRONMENT_PROBE = r"""
from collections.abc import MutableMapping
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import runpy
import sys
from types import ModuleType


class GuardedEnvironment(MutableMapping):
    def __init__(self, backing, denied_key, attempts, *, deny):
        self._backing = backing
        self._denied_key = denied_key
        self._attempts = attempts
        self._deny = deny

    def __getitem__(self, key):
        if key == self._denied_key:
            self._attempts.append(key)
            if self._deny:
                raise RuntimeError("DENIED_CREDENTIAL_ENVIRONMENT_READ")
        return self._backing[key]

    def __setitem__(self, key, value):
        self._backing[key] = value

    def __delitem__(self, key):
        del self._backing[key]

    def __iter__(self):
        return iter(self._backing)

    def __len__(self):
        return len(self._backing)


def _module_token_owners(token):
    owners = []
    for name, module in tuple(sys.modules.items()):
        if not isinstance(module, ModuleType):
            continue
        if any(value == token for value in vars(module).values() if isinstance(value, str)):
            owners.append(name)
    return sorted(owners)


def main():
    mode, generator = sys.argv[1:3]
    denied_key = "_".join(("AZURE", "OPENAI", "AD", "TOKEN"))
    synthetic_token = ":".join(("ST1605", "SYNTHETIC", "UNREAD"))
    backing = os.environ
    attempts = []
    os.environ = GuardedEnvironment(
        backing,
        denied_key,
        attempts,
        deny=mode == "deny",
    )
    generator_stdout = io.StringIO()
    generator_stderr = io.StringIO()
    original_argv = sys.argv
    exit_code = 97
    unexpected_exception = False
    try:
        sys.argv = [generator, "--check"]
        with redirect_stdout(generator_stdout), redirect_stderr(generator_stderr):
            try:
                runpy.run_path(generator, run_name="__main__")
            except SystemExit as error:
                if error.code is None:
                    exit_code = 0
                elif isinstance(error.code, int):
                    exit_code = error.code
                else:
                    exit_code = 1
            except BaseException:
                unexpected_exception = True
    finally:
        sys.argv = original_argv
        try:
            del backing[denied_key]
        except KeyError:
            pass

    provider_roots = ("azure", "openai")
    provider_sdk_modules = sorted(
        name
        for name in sys.modules
        if any(name == root or name.startswith(root + ".") for root in provider_roots)
    )
    capturing_modules = _module_token_owners(synthetic_token)
    os.environ = backing
    print(
        json.dumps(
            {
                "capturing_modules": capturing_modules,
                "generator_exit_code": exit_code,
                "generator_stderr_empty": generator_stderr.getvalue() == "",
                "generator_stdout_expected": generator_stdout.getvalue()
                == "ST-1605 local synthetic failure-injection evidence checked\n",
                "provider_sdk_modules": provider_sdk_modules,
                "secret_key_attempts": attempts,
                "unexpected_exception": unexpected_exception,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
"""


def _run_credential_environment_probe(
    repository_copy: Path, mode: str
) -> tuple[dict[str, object], subprocess.CompletedProcess[str], str]:
    denied_key = "_".join(("AZURE", "OPENAI", "AD", "TOKEN"))
    synthetic_token = ":".join(("ST1605", "SYNTHETIC", "UNREAD"))
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _CREDENTIAL_ENVIRONMENT_PROBE,
            mode,
            str(repository_copy / builder.GENERATOR_PATH),
        ],
        cwd=repository_copy,
        env={denied_key: synthetic_token},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert synthetic_token not in completed.stdout
    assert synthetic_token not in completed.stderr
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return payload, completed, denied_key


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path.relative_to(root): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _tree_snapshot(
    root: Path,
) -> dict[Path, tuple[str, int, int, bytes | str | None]]:
    snapshot: dict[Path, tuple[str, int, int, bytes | str | None]] = {}
    for path in root.rglob("*"):
        metadata = path.lstat()
        relative = path.relative_to(root)
        if stat.S_ISLNK(metadata.st_mode):
            kind = "symlink"
            payload: bytes | str | None = os.readlink(path)
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
            payload = path.read_bytes()
        elif stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            payload = None
        else:
            kind = "other"
            payload = None
        snapshot[relative] = (
            kind,
            metadata.st_mtime_ns,
            stat.S_IMODE(metadata.st_mode),
            payload,
        )
    return snapshot


def base_exception_types() -> tuple[type[BaseException], ...]:
    return (
        builder.FailureInjectionDrillError,
        base.ProductionDeploymentContractError,
    )


def test_owner_generation_is_deterministic_and_check_is_no_write(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    first = {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }
    before = _snapshot(repository_copy)
    builder.build(repository_copy, check=True)
    after = _snapshot(repository_copy)
    assert before == after
    builder.build(repository_copy)
    assert first == {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }


def test_hardened_cli_is_fresh_tree_hostile_and_byte_for_byte_no_write(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    hostile_python = repository_copy / "hostile-python"
    hostile_package = hostile_python / "raos"
    hostile_package.mkdir(parents=True)
    raos_marker = repository_copy / "hostile-raos-executed"
    yaml_marker = repository_copy / "hostile-yaml-executed"
    (hostile_package / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(raos_marker)!r}).write_text('EXECUTED', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (hostile_python / "yaml.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(yaml_marker)!r}).write_text('EXECUTED', encoding='utf-8')\n",
        encoding="utf-8",
    )
    environment = {"PYTHONPATH": hostile_python.as_posix()}
    command = [
        sys.executable,
        str(repository_copy / builder.GENERATOR_PATH),
        "--check",
    ]
    assert not any(
        path.name == "__pycache__" or path.suffix == ".pyc"
        for path in repository_copy.rglob("*")
    )
    before = _tree_snapshot(repository_copy)

    rejected = subprocess.run(
        [command[0], "-B", *command[1:]],
        cwd=repository_copy,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert rejected.returncode == 1
    assert rejected.stderr == (
        "ST1605_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python\n"
    )
    assert not raos_marker.exists()
    assert not yaml_marker.exists()

    missing_no_bytecode = subprocess.run(
        [command[0], "-I", *command[1:]],
        cwd=repository_copy,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert missing_no_bytecode.returncode == 1
    assert missing_no_bytecode.stderr == (
        "ST1605_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python\n"
    )
    assert not raos_marker.exists()
    assert not yaml_marker.exists()

    hardened = subprocess.run(
        [command[0], "-I", "-B", *command[1:]],
        cwd=repository_copy,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert hardened.returncode == 0, f"{hardened.stdout}\n{hardened.stderr}"
    assert hardened.stdout == (
        "ST-1605 local synthetic failure-injection evidence checked\n"
    )
    assert hardened.stderr == ""
    assert not raos_marker.exists()
    assert not yaml_marker.exists()
    assert _tree_snapshot(repository_copy) == before
    assert not any(
        path.name == "__pycache__" or path.suffix == ".pyc"
        for path in repository_copy.rglob("*")
    )


def test_fresh_process_denies_credential_read_and_provider_sdk_import(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)

    payload, _completed, _denied_key = _run_credential_environment_probe(
        repository_copy,
        "deny",
    )

    assert payload == {
        "capturing_modules": [],
        "generator_exit_code": 0,
        "generator_stderr_empty": True,
        "generator_stdout_expected": True,
        "provider_sdk_modules": [],
        "secret_key_attempts": [],
        "unexpected_exception": False,
    }


def test_fresh_process_does_not_retain_synthetic_provider_token(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)

    payload, completed, denied_key = _run_credential_environment_probe(
        repository_copy,
        "allow",
    )

    assert payload["generator_exit_code"] == 0
    assert payload["generator_stderr_empty"] is True
    assert payload["generator_stdout_expected"] is True
    assert payload["unexpected_exception"] is False
    assert payload["secret_key_attempts"] == []
    assert payload["provider_sdk_modules"] == []
    assert payload["capturing_modules"] == []
    assert denied_key not in completed.stderr


def test_manifest_records_exact_owner_inventory(repository_copy: Path) -> None:
    builder.build(repository_copy)
    manifest = yaml.safe_load((repository_copy / builder.MANIFEST_PATH).read_text())
    assert manifest["document"]["generation_command"] == builder.GENERATION_COMMAND
    assert " python -I -B " in builder.GENERATION_COMMAND
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    assert manifest["generated_artifact_count"] == 1
    assert manifest["generated_artifacts"][0]["uri"] == (
        f"repo://{builder.EVIDENCE_PATH.as_posix()}"
    )
    assert manifest["provenance"]["implementation_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in builder.EXPECTED_IMPLEMENTATION_HASHES.items()
    ]
    assert manifest["provenance"]["runtime_module_inputs"] == [
        {
            "module": module_name,
            "uri": f"repo://{path}",
            "sha256": digest,
        }
        for module_name, (path, digest) in builder.EXPECTED_RUNTIME_MODULES.items()
    ]
    assert manifest["provenance"]["runtime_namespace_packages"] == list(
        builder.RUNTIME_NAMESPACE_PACKAGES
    )
    assert manifest["boundary"] == {
        "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
        "formal_tst_028": "NOT_EXECUTED",
        "owner_response": "NOT_EXECUTED",
        "runbook_validation": "NOT_EXECUTED",
        "staging_drill": "NOT_EXECUTED",
        "story_acceptance": False,
        "st_1607_eligible": False,
        "effective_canonical_status": "UNCHANGED",
    }


def test_generated_evidence_preserves_zero_actions_and_false_acceptance(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    evidence = json.loads((repository_copy / builder.EVIDENCE_PATH).read_text())
    assert evidence["classification"] == "LOCAL_SYNTHETIC_NON_ATTESTING"
    assert all(
        type(value) is int and value == 0
        for value in evidence["summary"]["external_action_counts"].values()
    )
    assert evidence["summary"]["behavioral_observation_count"] == 1
    assert evidence["summary"]["static_tabletop_reference_count"] == 5
    assert evidence["summary"]["behavioral_observation_scenario_ids"] == ["FI-005"]
    assert evidence["evidence_boundary"]["formal_tst_028"] == "NOT_EXECUTED"
    assert evidence["evidence_boundary"]["staging_drill"] == "NOT_EXECUTED"
    assert evidence["evidence_boundary"]["story_acceptance"] is False


def test_check_detects_generated_output_drift(repository_copy: Path) -> None:
    builder.build(repository_copy)
    (repository_copy / builder.EVIDENCE_PATH).write_text("{}\n")
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.build(repository_copy, check=True)
    assert error.value.code == "GENERATED_OUTPUT_DRIFT"


def test_authority_hash_drift_fails_closed(repository_copy: Path) -> None:
    relative = Path(next(iter(builder.EXPECTED_AUTHORITY_SOURCES.values()))[0])
    target = repository_copy / relative
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.render_outputs(repository_copy)
    assert error.value.code == "SOURCE_HASH_DRIFT"


def test_dependency_hash_drift_fails_closed(repository_copy: Path) -> None:
    relative = Path(next(iter(builder.EXPECTED_ST1405_HASHES)))
    target = repository_copy / relative
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.render_outputs(repository_copy)
    assert error.value.code == "DEPENDENCY_HASH_DRIFT"


def test_runtime_module_hash_drift_fails_before_import(repository_copy: Path) -> None:
    relative = Path(
        builder.EXPECTED_RUNTIME_MODULES["raos.adapters.development_oidc"][0]
    )
    target = repository_copy / relative
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.render_outputs(repository_copy)
    assert error.value.code == "RUNTIME_MODULE_HASH_DRIFT"
    assert error.value.field == "raos.adapters.development_oidc"


def test_runtime_executes_captured_bytes_after_post_capture_path_swap(
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path(
        builder.EXPECTED_RUNTIME_MODULES["raos.adapters.recorded_kill_switch"][0]
    )
    target = repository_copy / relative
    marker = repository_copy / "reopened-runtime-source"
    original_capture = builder._capture_runtime_module_inputs  # noqa: SLF001
    meta_path_before = tuple(sys.meta_path)
    swapped = False

    def capture_then_swap(
        root: Path,
    ) -> object:
        nonlocal swapped
        captured = original_capture(root)
        target.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('REOPENED', encoding='utf-8')\n"
            "raise RuntimeError('reopened source executed')\n",
            encoding="utf-8",
        )
        swapped = True
        return captured

    monkeypatch.setattr(builder, "_capture_runtime_module_inputs", capture_then_swap)
    observation = builder._kill_switch_observation(  # noqa: SLF001
        builder.EXPECTED_FIXTURE,
        repository_copy,
    )

    assert swapped is True
    assert observation["eligibility_code"] == "ENGAGED"
    assert observation["allowed"] is False
    assert not marker.exists()
    assert tuple(sys.meta_path) == meta_path_before
    assert not any(name == "raos" or name.startswith("raos.") for name in sys.modules)


def test_secure_io_bootstrap_is_descriptor_read_and_exact_hash_bound(
    repository_copy: Path,
) -> None:
    content = builder._bootstrap_read_secure_io(repository_copy)  # noqa: SLF001
    assert builder._sha256_bytes(content) == builder.SECURE_IO_SHA256  # noqa: SLF001
    assert content == (repository_copy / builder.SECURE_IO_PATH).read_bytes()


def test_secure_io_bootstrap_rejects_helper_hash_drift(repository_copy: Path) -> None:
    helper = repository_copy / builder.SECURE_IO_PATH
    helper.write_bytes(helper.read_bytes() + b"\n")
    with pytest.raises(builder.SecureIoBootstrapError) as captured:
        builder._bootstrap_read_secure_io(repository_copy)  # noqa: SLF001
    assert captured.value.code == "HELPER_HASH_DRIFT"


def test_secure_io_bootstrap_rejects_leaf_swap_without_following_outside(
    repository_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = repository_copy / builder.SECURE_IO_PATH
    outside = tmp_path / "outside-secure-io.py"
    outside_bytes = helper.read_bytes()
    outside.write_bytes(outside_bytes)
    original_open = os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == helper.name and dir_fd is not None and not swapped:
            swapped = True
            helper.unlink()
            helper.symlink_to(outside)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", interleaved_open)
    with pytest.raises(builder.SecureIoBootstrapError) as captured:
        builder._bootstrap_read_secure_io(repository_copy)  # noqa: SLF001
    assert captured.value.code == "UNSAFE_HELPER_FILE"
    assert outside.read_bytes() == outside_bytes


def test_secure_io_bootstrap_rejects_ancestor_swap_without_following_outside(
    repository_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts = repository_copy / builder.SECURE_IO_PATH.parent
    moved = repository_copy / "scripts-owned"
    outside = tmp_path / "outside-scripts"
    outside.mkdir()
    (outside / builder.SECURE_IO_PATH.name).write_bytes(
        (scripts / builder.SECURE_IO_PATH.name).read_bytes()
    )
    marker = outside / "marker"
    marker.write_bytes(b"outside\n")
    original_open = os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == scripts.name and dir_fd is not None and not swapped:
            swapped = True
            scripts.rename(moved)
            scripts.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", interleaved_open)
    with pytest.raises(builder.SecureIoBootstrapError) as captured:
        builder._bootstrap_read_secure_io(repository_copy)  # noqa: SLF001
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert marker.read_bytes() == b"outside\n"


def test_symlinked_output_target_is_rejected(repository_copy: Path) -> None:
    builder.build(repository_copy)
    output = repository_copy / builder.EVIDENCE_PATH
    output.unlink()
    output.symlink_to(repository_copy / builder.CONTRACT_PATH)
    with pytest.raises(base_exception_types()):
        builder.build(repository_copy)


def test_symlinked_output_ancestor_is_rejected(repository_copy: Path) -> None:
    generated = repository_copy / builder.EVIDENCE_PATH.parent
    if generated.exists():
        os.rmdir(generated)
    generated.symlink_to(
        repository_copy / "changes/st-1605/contracts", target_is_directory=True
    )
    with pytest.raises(base_exception_types()):
        builder.build(repository_copy)


@pytest.mark.parametrize(
    "relative",
    (
        builder.CONTRACT_PATH,
        Path("changes/st-1602/generated/slo-alert-reference-plan.v1.json"),
    ),
)
def test_input_leaf_swap_is_rejected_without_outside_read(
    repository_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
) -> None:
    target = repository_copy / relative
    outside = tmp_path / f"outside-{target.name}"
    outside_bytes = target.read_bytes()
    outside.write_bytes(outside_bytes)
    original_open = os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == target.name and dir_fd is not None and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(outside)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", interleaved_open)
    with pytest.raises(base.ProductionDeploymentContractError) as captured:
        builder.load_contract(repository_copy)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == outside_bytes


def test_input_ancestor_swap_is_rejected_without_outside_read(
    repository_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical_ops = repository_copy / "docs/canonical/06_ops"
    moved = repository_copy / "docs/canonical/06_ops-owned"
    outside = tmp_path / "outside-ops"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"outside\n")
    original_open = os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == canonical_ops.name and dir_fd is not None and not swapped:
            swapped = True
            canonical_ops.rename(moved)
            canonical_ops.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", interleaved_open)
    with pytest.raises(base.ProductionDeploymentContractError) as captured:
        builder.load_contract(repository_copy)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert marker.read_bytes() == b"outside\n"


def test_check_rejects_leaf_swap_without_reading_outside(
    repository_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    expected = builder.render_outputs(repository_copy)
    output = repository_copy / builder.EVIDENCE_PATH
    outside = tmp_path / "outside-evidence.json"
    outside.write_bytes(b"outside\n")
    original_open = os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == output.name and dir_fd is not None and not swapped:
            swapped = True
            output.unlink()
            output.symlink_to(outside)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", interleaved_open)
    with pytest.raises(base.ProductionDeploymentContractError) as captured:
        builder.check_outputs(repository_copy, expected)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == b"outside\n"


def test_build_rejects_output_ancestor_swap_without_outside_write(
    repository_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = builder.render_outputs(repository_copy)
    generated = repository_copy / builder.EVIDENCE_PATH.parent
    generated.mkdir(parents=True)
    moved = repository_copy / "changes/st-1605/generated-owned"
    outside = tmp_path / "outside-generated"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"outside\n")
    original_open = os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == generated.name and dir_fd is not None and not swapped:
            swapped = True
            generated.rename(moved)
            generated.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", interleaved_open)
    with pytest.raises(base.ProductionDeploymentContractError) as captured:
        for relative, content in expected.items():
            base._atomic_write(repository_copy, relative, content)  # noqa: SLF001
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert marker.read_bytes() == b"outside\n"
    assert not (outside / builder.EVIDENCE_PATH.name).exists()
