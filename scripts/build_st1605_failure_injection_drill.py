#!/usr/bin/env python3
"""Build deterministic non-attesting ST-1605 local drill evidence."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    if sys.flags.isolated != 1:
        print(
            "ST1605_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1605_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)

import argparse
from collections.abc import Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import importlib.abc
import importlib.machinery
import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Final, NoReturn, cast
from uuid import UUID

import yaml


def _lexical_repository_root(script_path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.fspath(script_path))).parents[1]


REPO_ROOT: Final = _lexical_repository_root(__file__)
PYTHON_ROOT: Final = REPO_ROOT / "python"

SECURE_IO_PATH: Final = Path("scripts/build_st1506_production_deployment.py")
SECURE_IO_MODULE_NAME: Final = "scripts.build_st1506_production_deployment"
SECURE_IO_SHA256: Final = (
    "cc6ba0582e40f697ce670ff9a28ad3e8af8bba9c2dc8af68061d77f6ff0044be"
)
SECURE_IO_MAX_BYTES: Final = 256 * 1024
_BOOTSTRAP_READ_BYTES: Final = 64 * 1024


class SecureIoBootstrapError(RuntimeError):
    """Sanitized failure before any repository helper code executes."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"ST1605_BOOTSTRAP_ERROR code={code}")


def _bootstrap_fail(code: str) -> NoReturn:
    raise SecureIoBootstrapError(code) from None


def _bootstrap_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        _bootstrap_fail("UNSUPPORTED_SAFE_IO")
    return value


def _bootstrap_close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _bootstrap_read_secure_io(root: Path) -> bytes:
    if not root.is_absolute() or any(
        part in {"", ".", ".."} for part in root.parts[1:]
    ):
        _bootstrap_fail("UNSAFE_ROOT")
    directory_flags = (
        os.O_RDONLY
        | _bootstrap_flag("O_CLOEXEC")
        | _bootstrap_flag("O_DIRECTORY")
        | _bootstrap_flag("O_NOFOLLOW")
    )
    file_flags = (
        os.O_RDONLY
        | _bootstrap_flag("O_CLOEXEC")
        | _bootstrap_flag("O_NOFOLLOW")
        | _bootstrap_flag("O_NONBLOCK")
    )
    descriptors: list[int] = []
    file_descriptor = -1
    try:
        descriptors.append(os.open(os.path.sep, directory_flags))
        for part in (*root.parts[1:], *SECURE_IO_PATH.parts[:-1]):
            try:
                child = os.open(part, directory_flags, dir_fd=descriptors[-1])
            except OSError:
                _bootstrap_fail("UNSAFE_ANCESTOR")
            descriptors.append(child)
        try:
            file_descriptor = os.open(
                SECURE_IO_PATH.name, file_flags, dir_fd=descriptors[-1]
            )
        except OSError:
            _bootstrap_fail("UNSAFE_HELPER_FILE")
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            _bootstrap_fail("UNSAFE_HELPER_FILE")
        if before.st_size < 0 or before.st_size > SECURE_IO_MAX_BYTES:
            _bootstrap_fail("HELPER_SIZE_LIMIT")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                file_descriptor,
                min(_BOOTSTRAP_READ_BYTES, SECURE_IO_MAX_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > SECURE_IO_MAX_BYTES:
                _bootstrap_fail("HELPER_SIZE_LIMIT")
        after = os.fstat(file_descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        content = b"".join(chunks)
        if before_identity != after_identity or len(content) != before.st_size:
            _bootstrap_fail("HELPER_CHANGED_DURING_READ")
        if hashlib.sha256(content).hexdigest() != SECURE_IO_SHA256:
            _bootstrap_fail("HELPER_HASH_DRIFT")
        return content
    except SecureIoBootstrapError:
        raise
    except OSError:
        _bootstrap_fail("HELPER_UNAVAILABLE")
    finally:
        if file_descriptor >= 0:
            _bootstrap_close(file_descriptor)
        while descriptors:
            _bootstrap_close(descriptors.pop())


def _load_secure_io_bootstrap(root: Path) -> ModuleType:
    if SECURE_IO_MODULE_NAME in sys.modules:
        _bootstrap_fail("HELPER_MODULE_PRELOADED")
    content = _bootstrap_read_secure_io(root)
    module = ModuleType(SECURE_IO_MODULE_NAME)
    module.__file__ = str(root / SECURE_IO_PATH)
    module.__package__ = "scripts"
    sys.modules[SECURE_IO_MODULE_NAME] = module
    try:
        exec(compile(content, module.__file__, "exec"), module.__dict__)
    except Exception:
        if sys.modules.get(SECURE_IO_MODULE_NAME) is module:
            del sys.modules[SECURE_IO_MODULE_NAME]
        _bootstrap_fail("HELPER_EXECUTION_FAILED")
    if sys.modules.get(SECURE_IO_MODULE_NAME) is not module:
        _bootstrap_fail("HELPER_MODULE_IDENTITY_DRIFT")
    return module


base: Any = _load_secure_io_bootstrap(REPO_ROOT)


def _compat_fail(code: str, field: str) -> NoReturn:
    """Raise the helper's closed error without retaining rejected material."""

    raise base.ProductionDeploymentContractError(code, field) from None


def _compat_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        _compat_fail("UNSUPPORTED_SAFE_IO", "filesystem")
    return value


def _compat_close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _compat_validate_relative(relative: Path, field: str, path_error_code: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _compat_fail(path_error_code, field)


def _compat_absolute_root(root: Path, field: str) -> Path:
    absolute = root if root.is_absolute() else Path.cwd() / root
    if any(part in {"", ".", ".."} for part in absolute.parts[1:]):
        _compat_fail("UNSAFE_ROOT_TYPE", field)
    return absolute


def _compat_open_physical_directory(root: Path, field: str) -> int:
    absolute = _compat_absolute_root(root, field)
    flags = (
        os.O_RDONLY
        | _compat_flag("O_CLOEXEC")
        | _compat_flag("O_DIRECTORY")
        | _compat_flag("O_NOFOLLOW")
    )
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.path.sep, flags))
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=descriptors[-1])
            except FileNotFoundError:
                _compat_fail("ROOT_UNAVAILABLE", field)
            except OSError:
                _compat_fail("UNSAFE_ROOT_TYPE", field)
            descriptors.append(child)
        return descriptors.pop()
    except base.ProductionDeploymentContractError:
        raise
    except OSError:
        _compat_fail("ROOT_UNAVAILABLE", field)
    finally:
        while descriptors:
            _compat_close(descriptors.pop())


def _compat_read_repository_file(
    root: Path,
    relative: Path,
    field: str,
    *,
    max_bytes: int,
    size_error_code: str,
    path_error_code: str = "UNSAFE_REPOSITORY_PATH",
    missing_error_code: str = "FILE_UNAVAILABLE",
    ancestor_error_code: str = "UNSAFE_ANCESTOR",
    file_type_error_code: str = "UNSAFE_FILE_TYPE",
) -> bytes:
    """Descriptor-read one bounded regular file without following a symlink."""

    _compat_validate_relative(relative, field, path_error_code)
    if type(max_bytes) is not int or max_bytes <= 0:
        _compat_fail(size_error_code, field)
    directory_flags = (
        os.O_RDONLY
        | _compat_flag("O_CLOEXEC")
        | _compat_flag("O_DIRECTORY")
        | _compat_flag("O_NOFOLLOW")
    )
    file_flags = (
        os.O_RDONLY
        | _compat_flag("O_CLOEXEC")
        | _compat_flag("O_NOFOLLOW")
        | _compat_flag("O_NONBLOCK")
    )
    directories = [_compat_open_physical_directory(root, field)]
    descriptor = -1
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directories[-1])
            except FileNotFoundError:
                _compat_fail(missing_error_code, field)
            except OSError:
                _compat_fail(ancestor_error_code, field)
            directories.append(child)
        try:
            descriptor = os.open(relative.name, file_flags, dir_fd=directories[-1])
        except FileNotFoundError:
            _compat_fail(missing_error_code, field)
        except OSError:
            _compat_fail(file_type_error_code, field)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _compat_fail(file_type_error_code, field)
        if before.st_size < 0 or before.st_size > max_bytes:
            _compat_fail(size_error_code, field)
        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = max_bytes + 1 - total
            if remaining <= 0:
                _compat_fail(size_error_code, field)
            chunk = os.read(descriptor, min(_BOOTSTRAP_READ_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                _compat_fail(size_error_code, field)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity or total != before.st_size:
            _compat_fail("FILE_CHANGED_DURING_READ", field)
        return b"".join(chunks)
    except base.ProductionDeploymentContractError:
        raise
    except OSError:
        _compat_fail("FILE_UNAVAILABLE", field)
    finally:
        if descriptor >= 0:
            _compat_close(descriptor)
        while directories:
            _compat_close(directories.pop())


def _compat_parse_yaml_bytes(content: bytes, field: str) -> Any:
    if type(content) is not bytes or len(content) > base.MAX_DOCUMENT_BYTES:
        _compat_fail("YAML_SIZE_LIMIT", field)
    try:
        text_value = content.decode("utf-8")
        tokens = cast(
            Iterator[object],
            yaml.scan(text_value),  # pyright: ignore[reportUnknownMemberType]
        )
        for token in tokens:
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                _compat_fail("YAML_ALIAS_FORBIDDEN", field)
            if isinstance(token, yaml.tokens.TagToken):
                _compat_fail("YAML_TAG_FORBIDDEN", field)
        return yaml.load(text_value, Loader=base.UniqueKeyLoader)
    except base.ProductionDeploymentContractError:
        raise
    except UnicodeError, yaml.YAMLError:
        _compat_fail("YAML_INVALID", field)


def _compat_parse_json_bytes(content: bytes, field: str) -> Any:
    if type(content) is not bytes or len(content) > base.MAX_DOCUMENT_BYTES:
        _compat_fail("JSON_SIZE_LIMIT", field)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _compat_fail("JSON_DUPLICATE_KEY", field)
            result[key] = value
        return result

    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: _compat_fail("JSON_INVALID", field),
        )
    except base.ProductionDeploymentContractError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _compat_fail("JSON_INVALID", field)


def _compat_open_output_parent(root: Path, relative: Path, *, create: bool) -> int:
    _compat_validate_relative(relative, "output", "UNSAFE_OUTPUT_PATH")
    flags = (
        os.O_RDONLY
        | _compat_flag("O_CLOEXEC")
        | _compat_flag("O_DIRECTORY")
        | _compat_flag("O_NOFOLLOW")
    )
    directories = [_compat_open_physical_directory(root, "repository")]
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=directories[-1])
            except FileNotFoundError:
                if not create:
                    _compat_fail("GENERATED_OUTPUT_MISSING", "output")
                try:
                    os.mkdir(part, mode=0o755, dir_fd=directories[-1])
                    os.fsync(directories[-1])
                except FileExistsError:
                    pass
                except OSError:
                    _compat_fail("OUTPUT_DIRECTORY_FAILED", "output")
                try:
                    child = os.open(part, flags, dir_fd=directories[-1])
                except OSError:
                    _compat_fail("UNSAFE_OUTPUT_ANCESTOR", "output")
            except OSError:
                _compat_fail("UNSAFE_OUTPUT_ANCESTOR", "output")
            directories.append(child)
        return directories.pop()
    except base.ProductionDeploymentContractError:
        raise
    except OSError:
        _compat_fail("OUTPUT_DIRECTORY_FAILED", "output")
    finally:
        while directories:
            _compat_close(directories.pop())


def _compat_atomic_write(root: Path, relative: Path, content: bytes) -> None:
    if type(content) is not bytes or len(content) > base.MAX_DOCUMENT_BYTES:
        _compat_fail("OUTPUT_WRITE_FAILED", "output")
    parent_descriptor = _compat_open_output_parent(root, relative, create=True)
    descriptor = -1
    temporary_name: str | None = None
    try:
        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            _compat_fail("UNSAFE_FILE_TYPE", "generated_output")
        for attempt in range(100):
            candidate = f".{relative.name}.st1605-{os.getpid()}-{attempt}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | _compat_flag("O_CLOEXEC")
                    | _compat_flag("O_NOFOLLOW"),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor < 0 or temporary_name is None:
            _compat_fail("OUTPUT_WRITE_FAILED", "output")
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _compat_fail("OUTPUT_WRITE_FAILED", "output")
            view = view[written:]
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
        _compat_close(descriptor)
        descriptor = -1
        os.replace(
            temporary_name,
            relative.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    except base.ProductionDeploymentContractError:
        raise
    except OSError:
        _compat_fail("OUTPUT_WRITE_FAILED", "output")
    finally:
        if descriptor >= 0:
            _compat_close(descriptor)
        try:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
        finally:
            _compat_close(parent_descriptor)


# ST-1506 no longer exposes the old descriptor I/O internals used by this
# historical candidate. Bind exact, Story-owned compatibility functions while
# retaining the helper's closed error type and byte-pinned bootstrap boundary.
base._read_repository_file = _compat_read_repository_file
base._parse_yaml_bytes = _compat_parse_yaml_bytes
base._parse_json_bytes = _compat_parse_json_bytes
base._atomic_write = _compat_atomic_write


CONTRACT_PATH: Final = Path("changes/st-1605/contracts/failure-injection-drill.v1.yaml")
EVIDENCE_PATH: Final = Path(
    "changes/st-1605/generated/failure-injection-drill.local-synthetic-evidence.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1605/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1605_failure_injection_drill.py")
README_PATH: Final = Path("changes/st-1605/README.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1605/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
TEST_PATHS: Final = (
    Path("tests/st1605/conftest.py"),
    Path("tests/st1605/test_contract.py"),
    Path("tests/st1605/test_generation.py"),
    Path("tests/st1605/test_scenarios.py"),
    Path("tests/st1605/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    README_PATH,
    COMPLETION_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (EVIDENCE_PATH, MANIFEST_PATH)

SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python -I -B "
    "scripts/build_st1605_failure_injection_drill.py"
)

TOP_LEVEL_KEYS: Final = (
    "document",
    "authority_sources",
    "dependency_bindings",
    "execution_boundary",
    "deterministic_fixture",
    "scenarios",
    "evidence_boundary",
)

EXPECTED_AUTHORITY_SOURCES: Final = {
    "integration": (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    "canonical_decisions": (
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    "open_decisions": (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    "story_backlog": (
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    "test_catalog": (
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    "operations_design": (
        "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md",
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8",
    ),
    "alert_catalog": (
        "docs/canonical/06_ops/RAOS_12_alert_catalog_v1.0.yaml",
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0",
    ),
    "runbook_catalog": (
        "docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml",
        "2aed21892e78ead32fc647b928f50014971d280142d0f49f4e0d1e7d68897100",
    ),
    "security_design": (
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    "security_controls": (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    "threat_register": (
        "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml",
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    ),
    "implementation_first_execplan": (
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
        "4d4cffb36f790f15fb467713ee93f9f55e00ea2f3c2b74c19fe3436c56755234",
    ),
}

EXPECTED_ST1602_HASHES: Final = {
    "changes/st-1602/README.md": (
        "9ed7dfa14f736cf30aa166c8c79d3f42386abfab90ec31b2792454e89ad976bc"
    ),
    "changes/st-1602/contracts/slo-alert-reference-plan.v1.yaml": (
        "31c8d3c57501e351bd9bcde3c796abe70eb80277b4cb7a1c738cf93817ba65b1"
    ),
    "changes/st-1602/generated/slo-alert-reference-plan.v1.json": (
        "b4a8723c3fa4b70d30bf8ac8b145daaa4d7e41c993d53de3364d1c0a6a8ad4b3"
    ),
    "changes/st-1602/manifest.yaml": (
        "89b37ab9fc483573aa9743a7e36edc9963f4865126a26e1b0c1ae938b0a79809"
    ),
}
EXPECTED_ST1405_HASHES: Final = {
    "changes/st-1405/README.md": (
        "032b2d3bd517aa4f6069e5e4d46f05e6032f4cd04d1660c3ce6f621032ef7cec"
    ),
    "python/raos/domain/ops/kill_switch.py": (
        "6b4c014b89cb8b330885e5deae0849b9b0e2089272f7c8371627cd7f4eb353d3"
    ),
    "python/raos/application/ops/kill_switch.py": (
        "15f4deef25bd60d07a69dab81c5427677c184be9b67a8c4b2cfe6eb96937f0de"
    ),
    "python/raos/adapters/recorded_kill_switch.py": (
        "f88f23c6003e0a3d7859487426aa4dfa3c60f8687f4aab349501c01d3c72eeed"
    ),
    "python/raos/ports/kill_switch.py": (
        "857f53d3e6f1efd41a31858d9c31241aef554f8322809276d6e435584a6c2880"
    ),
}
EXPECTED_IMPLEMENTATION_HASHES: Final = {
    SECURE_IO_PATH.as_posix(): SECURE_IO_SHA256,
}

DIRECT_RUNTIME_IMPORTS: Final = (
    "raos.adapters.development_oidc",
    "raos.adapters.development_step_up",
    "raos.adapters.recorded_kill_switch",
    "raos.application.iam.authentication",
    "raos.application.iam.step_up",
    "raos.application.ops.kill_switch",
    "raos.config.runtime",
    "raos.domain.iam.authentication",
    "raos.domain.iam.step_up",
    "raos.domain.ops.kill_switch",
)
RUNTIME_NAMESPACE_PACKAGES: Final = (
    "raos.adapters",
    "raos.application",
    "raos.application.ops",
    "raos.domain",
    "raos.domain.ops",
    "raos.ports",
)

EXPECTED_RUNTIME_MODULES: Final = {
    "raos": (
        "python/raos/__init__.py",
        "700d7d03288b2e80438a468cc5e45d308026ad82120a9d0f7d509664519ce596",
    ),
    "raos.adapters.development_oidc": (
        "python/raos/adapters/development_oidc.py",
        "f962b13a62890dea606ed8c07a80c44f177365abce8d180661e80c828409b135",
    ),
    "raos.adapters.development_step_up": (
        "python/raos/adapters/development_step_up.py",
        "bfc55e2b952db59972591816c0d85f0fab3d0c8c40e8c6860a54483a59923d5d",
    ),
    "raos.adapters.recorded_kill_switch": (
        "python/raos/adapters/recorded_kill_switch.py",
        "f88f23c6003e0a3d7859487426aa4dfa3c60f8687f4aab349501c01d3c72eeed",
    ),
    "raos.application.iam": (
        "python/raos/application/iam/__init__.py",
        "7fe03d690c880cd0694c12f35ff2e01a2ca9427e90b166b15362951f79c10e2d",
    ),
    "raos.application.iam.authentication": (
        "python/raos/application/iam/authentication.py",
        "edb92df10bf68bcb1fc76f9c5635f6dd87340a562e24d58c44fcc136df2aa32a",
    ),
    "raos.application.iam.step_up": (
        "python/raos/application/iam/step_up.py",
        "a1bf4216013e6cbe878f8964c936c95a9bc41c31a87b9a2272c0b26a6e70181b",
    ),
    "raos.application.ops.kill_switch": (
        "python/raos/application/ops/kill_switch.py",
        "15f4deef25bd60d07a69dab81c5427677c184be9b67a8c4b2cfe6eb96937f0de",
    ),
    "raos.config": (
        "python/raos/config/__init__.py",
        "e893d5e333ec1b4d84d74cb59a6cc4ac62672b493d5905c379ee4ebe9936c314",
    ),
    "raos.config.runtime": (
        "python/raos/config/runtime.py",
        "2a1b7b550bcf5365df610c8ebffe1994d12ab888a5be4042dde032ed7c5a0ac3",
    ),
    "raos.domain.iam": (
        "python/raos/domain/iam/__init__.py",
        "ca8540dc060f08cdad74855e90aed5fa56e8beff311b22c6b89370b46060bbca",
    ),
    "raos.domain.iam.authentication": (
        "python/raos/domain/iam/authentication.py",
        "a7a06f72244318696dc37c76dfd4b6ac030db8a9fb3872ed69747201f6fc690d",
    ),
    "raos.domain.iam.step_up": (
        "python/raos/domain/iam/step_up.py",
        "ae17d9db24acf4133c41e2aef8c8f035a12ec063b77da3d9c3a182605052f4a9",
    ),
    "raos.domain.ops.kill_switch": (
        "python/raos/domain/ops/kill_switch.py",
        "6b4c014b89cb8b330885e5deae0849b9b0e2089272f7c8371627cd7f4eb353d3",
    ),
    "raos.ports.kill_switch": (
        "python/raos/ports/kill_switch.py",
        "857f53d3e6f1efd41a31858d9c31241aef554f8322809276d6e435584a6c2880",
    ),
    "raos.ports.oidc": (
        "python/raos/ports/oidc.py",
        "57fcca6de54cae9c206018a264ea34632f4c3adcc94b2a5d4e4063d635a96269",
    ),
    "raos.ports.step_up": (
        "python/raos/ports/step_up.py",
        "756822270b9c71b2600ec2d631c6696d004eb1ebd51e2d3fac9d8212d7de92e9",
    ),
}

EXPECTED_DOCUMENT: Final[dict[str, object]] = {
    "id": "RAOS-ST1605-FAILURE-INJECTION-DRILL-001",
    "version": "1.0.0",
    "story_id": "ST-1605",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
    "local_synthetic_execution": True,
    "operational_execution": False,
    "acceptance_criteria_satisfied": False,
    "formal_verification": "NOT_EXECUTED",
}

ACTION_NAMES: Final = (
    "network_request",
    "provider_call",
    "credential_read",
    "database_write",
    "queue_publish",
    "notification",
    "browser",
    "publication",
    "rollback",
    "staging",
    "release",
    "production",
)
EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "mode": "DETERMINISTIC_IN_PROCESS_LOCAL_SYNTHETIC",
    "cli_python_isolated_mode": "REQUIRED",
    "cli_python_no_bytecode_mode": "REQUIRED",
    "runtime_module_loading": "DESCRIPTOR_CAPTURED_HASH_VERIFIED_IN_MEMORY",
    "runtime_module_inventory_scope": "FI_005_TRANSITIVE_IMPORT_CLOSURE",
    "runtime_adapter_package_boundary": "SOURCE_FREE_ADAPTER_AND_PORT_NAMESPACES",
    "preloaded_raos_modules": "FORBIDDEN",
    "unlisted_raos_dependencies": "FORBIDDEN",
    "unrelated_provider_sdk_imports": "FORBIDDEN",
    "runtime_module_cleanup": "OWNED_IDENTITY_ONLY",
    "foreign_raos_modules_during_scope": "PRESERVE_AND_FAIL",
    "preloaded_helper_module": "FORBIDDEN",
    "process_context": "LOCAL_SYNTHETIC",
    "target_adapter_environment": "ENV-CI",
    "step_up_fixture_environment": "ENV-DEV",
    "fixed_observation_time": "2026-08-16T00:00:00Z",
    "fixed_inputs_only": True,
    "live_fault_injection_enabled": False,
    "kill_switch_mutation_enabled": False,
    "rollback_execution_enabled": False,
    "owner_notification_enabled": False,
    "ambient_clock": "FORBIDDEN",
    "randomness": "FORBIDDEN",
    "network_access": "FORBIDDEN",
    "provider_calls": "FORBIDDEN",
    "credential_access": "FORBIDDEN",
    "credential_environment_reads": "FORBIDDEN",
    "browser_access": "FORBIDDEN",
    "subprocess_execution": "FORBIDDEN",
    "database_connection": "FORBIDDEN",
    "queue_connection": "FORBIDDEN",
    "notification_delivery": "FORBIDDEN",
    "staging_access": "FORBIDDEN",
    "production_access": "FORBIDDEN",
    "filesystem_inputs": "REPOSITORY_PINNED_READ_ONLY",
    "filesystem_output_allowlist": [
        EVIDENCE_PATH.as_posix(),
        MANIFEST_PATH.as_posix(),
    ],
    "external_action_counts": {name: 0 for name in ACTION_NAMES},
}
EXPECTED_FIXTURE: Final[dict[str, object]] = {
    "observation_time": "2026-08-16T00:00:00Z",
    "site_id": "00000000-0000-0000-0000-000000001605",
    "category_id": "00000000-0000-0000-0000-000000002605",
    "article_id": "00000000-0000-0000-0000-000000003605",
    "event_namespace": "00000000-0000-0000-0000-000000004605",
    "kill_switch_id": "00000000-0000-0000-0000-000000005605",
    "kill_switch_generation": 7,
    "kill_switch_reason": "SYNTHETIC_DRILL_ENGAGED",
}

ZERO_ACTIONS: Final = {name: 0 for name in ACTION_NAMES}

STATIC_OBSERVATIONS: Final[dict[str, dict[str, object]]] = {
    "FI-001": {
        "outcome_code": "RAKUTEN_SAFE_DEGRADATION_SELECTED",
        "required_response": "HIDE_UNVERIFIED_PRICE_STOCK_AND_STOP_CTA",
        "guard_state": "PROVIDER_FAILURE_ISOLATED",
        "public_state": "LAST_SAFE_PUBLICATION_UNCHANGED",
        "operation_executed": False,
        "external_effect": "NONE",
    },
    "FI-002": {
        "outcome_code": "OPENAI_SAFE_DEGRADATION_SELECTED",
        "required_response": "DISABLE_GENERATION_ROUTE_AND_QUARANTINE",
        "guard_state": "APPROVED_FALLBACK_REQUIRED",
        "public_state": "PUBLISHED_CONTENT_UNCHANGED",
        "operation_executed": False,
        "external_effect": "NONE",
    },
    "FI-003": {
        "outcome_code": "DATABASE_SAFE_DEGRADATION_SELECTED",
        "required_response": "FREEZE_WRITES_AND_SERVE_LAST_SAFE_SNAPSHOT",
        "guard_state": "DATABASE_PATH_ISOLATED",
        "public_state": "LAST_SAFE_PUBLICATION_PREFERRED",
        "operation_executed": False,
        "external_effect": "NONE",
    },
    "FI-004": {
        "outcome_code": "QUEUE_SAFE_DEGRADATION_SELECTED",
        "required_response": "PAUSE_PRODUCER_AND_REQUIRE_IDEMPOTENT_REPLAY",
        "guard_state": "DELIVERY_AND_REPLAY_NOT_EXECUTED",
        "public_state": "PUBLICATION_UNCHANGED",
        "operation_executed": False,
        "external_effect": "NONE",
    },
    "FI-006": {
        "outcome_code": "ROLLBACK_RESPONSE_HELD_FOR_AUTHORIZED_EXECUTION",
        "required_response": "STOP_ROLLOUT_AND_RESTORE_SAFE_ARTIFACT",
        "guard_state": "TABLETOP_ONLY",
        "public_state": "LAST_SAFE_PUBLICATION_PREFERRED",
        "operation_executed": False,
        "external_effect": "NONE",
    },
}

RECORDED_RESPONSE_TIMES: Final = {
    f"FI-{index:03d}": f"2026-08-16T00:00:{index:02d}Z" for index in range(1, 7)
}

EXPECTED_SCENARIOS: Final[list[dict[str, object]]] = [
    {
        "id": "FI-001",
        "category": "PROVIDER_FAILURE",
        "target": "RAKUTEN",
        "fault": "SYNTHETIC_PROVIDER_UNAVAILABLE",
        "runbook_id": "RB-008",
        "alert_id": None,
        "expected_observation": STATIC_OBSERVATIONS["FI-001"],
    },
    {
        "id": "FI-002",
        "category": "PROVIDER_FAILURE",
        "target": "OPENAI",
        "fault": "SYNTHETIC_PROVIDER_UNAVAILABLE",
        "runbook_id": "RB-009",
        "alert_id": None,
        "expected_observation": STATIC_OBSERVATIONS["FI-002"],
    },
    {
        "id": "FI-003",
        "category": "DATA_FAILURE",
        "target": "DATABASE",
        "fault": "SYNTHETIC_DATABASE_UNAVAILABLE",
        "runbook_id": "RB-005",
        "alert_id": "ALT-005",
        "expected_observation": STATIC_OBSERVATIONS["FI-003"],
    },
    {
        "id": "FI-004",
        "category": "QUEUE_FAILURE",
        "target": "QUEUE",
        "fault": "SYNTHETIC_QUEUE_DELIVERY_FAILURE",
        "runbook_id": "RB-006",
        "alert_id": "ALT-006",
        "expected_observation": STATIC_OBSERVATIONS["FI-004"],
    },
    {
        "id": "FI-005",
        "category": "KILL_SWITCH",
        "target": "PUBLICATION",
        "fault": "SYNTHETIC_ENGAGED_GENERATION",
        "runbook_id": "RB-015",
        "alert_id": None,
        "expected_observation": {
            "outcome_code": "PUBLICATION_COMMANDS_DENIED",
            "required_response": "KEEP_SWITCH_ENGAGED",
            "guard_state": "ENGAGED_GENERATION_7",
            "public_state": "PUBLICATION_COMMAND_PATH_DENIED",
            "operation_executed": False,
            "external_effect": "NONE",
            "target_adapter_environment": "ENV-CI",
            "step_up_fixture_environment": "ENV-DEV",
            "eligibility_code": "ENGAGED",
            "allowed": False,
            "observed_generation": 7,
            "event_intent_count": 0,
        },
    },
    {
        "id": "FI-006",
        "category": "ROLLBACK_TABLETOP",
        "target": "RELEASE",
        "fault": "SYNTHETIC_RELEASE_REGRESSION",
        "runbook_id": "RB-014",
        "alert_id": "ALT-016",
        "expected_observation": STATIC_OBSERVATIONS["FI-006"],
    },
]

EXPECTED_EVIDENCE: Final[dict[str, object]] = {
    "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
    "scenario_inventory": 6,
    "behavioral_observation_scope": "FI-005_ONLY",
    "behavioral_observation_scenarios": 1,
    "static_tabletop_reference_scenarios": 5,
    "recorded_safe_degradation_evaluation_scenarios": 6,
    "recorded_synthetic_response_scenarios": 6,
    "recorded_synthetic_responder_is_actual_owner": False,
    "local_acceptance_coverage": "MAXIMUM_SAFE_RECORDED_SYNTHETIC",
    "operational_safe_degradation_claim": False,
    "provider_behavior_claim": False,
    "database_behavior_claim": False,
    "queue_behavior_claim": False,
    "rollback_behavior_claim": False,
    "formal_tst_028": "NOT_EXECUTED",
    "fault_proxy": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "owner_response": "NOT_EXECUTED",
    "runbook_validation": "NOT_EXECUTED",
    "alert_delivery": "NOT_EXECUTED",
    "staging_drill": "NOT_EXECUTED",
    "release": "NOT_AUTHORIZED",
    "production": "NOT_AUTHORIZED",
    "story_acceptance": False,
    "st_1607_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}


class FailureInjectionDrillError(RuntimeError):
    """Sanitized ST-1605 generation failure."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"ST1605_ERROR code={code} field={field}")
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise FailureInjectionDrillError(code, field) from None


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_TYPE", field)
    observed = cast(Mapping[object, object], value)
    if not all(type(key) is str for key in observed):
        _fail("INVALID_TYPE", field)
    return cast(Mapping[str, Any], observed)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("INVALID_TYPE", field)
    return cast(list[Any], value)  # type: ignore[redundant-cast]


def _exact(value: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        observed = _mapping(value, field)
        expected_mapping = _mapping(cast(object, expected), field)
        if tuple(observed.keys()) != tuple(expected_mapping.keys()):
            _fail("CLOSED_SCHEMA_DRIFT", field)
        for key, expected_value in expected_mapping.items():
            _exact(observed[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        observed_list = _list(value, field)
        expected_list = _list(cast(object, expected), field)
        if len(observed_list) != len(expected_list):
            _fail("FIXED_INVENTORY_DRIFT", field)
        for index, expected_value in enumerate(expected_list):
            _exact(observed_list[index], expected_value, f"{field}[{index}]")
        return
    if type(value) is not type(expected) or value != expected:
        if (
            expected is None
            or type(expected) is bool
            or (type(expected) is int and expected == 0)
        ):
            _fail("SAFE_BOUNDARY_DRIFT", field)
        _fail("FIXED_VALUE_DRIFT", field)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    return cast(
        bytes,
        base._read_repository_file(  # noqa: SLF001
            root,
            relative,
            field,
            max_bytes=base.MAX_DOCUMENT_BYTES,
            size_error_code="FILE_SIZE_LIMIT",
        ),
    )


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    return _mapping(base._parse_yaml_bytes(_read(root, relative, field), field), field)  # noqa: SLF001


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    return _mapping(base._parse_json_bytes(_read(root, relative, field), field), field)  # noqa: SLF001


@dataclass(frozen=True, slots=True)
class _RuntimeBindings:
    DevelopmentOidcAdapter: type[Any]
    InMemoryAuthenticationRepository: type[Any]
    DevelopmentScriptedStepUpVerifier: type[Any]
    RecordedKillSwitchAdapter: type[Any]
    AuthenticationService: type[Any]
    StepUpGuard: type[Any]
    KillSwitchRuntimeService: type[Any]
    RuntimeEnvironment: type[Any]
    Issuer: type[Any]
    PrincipalIdentity: type[Any]
    Session: type[Any]
    SessionId: type[Any]
    Subject: type[Any]
    StepUpAssuranceType: type[Any]
    StepUpGrant: type[Any]
    KillSwitchCacheEntry: type[Any]
    KillSwitchCacheSnapshot: type[Any]
    KillSwitchContext: type[Any]
    KillSwitchEligibilityCode: type[Any]
    KillSwitchKind: type[Any]
    KillSwitchReasonCode: type[Any]
    KillSwitchState: type[Any]


@dataclass(frozen=True, slots=True)
class _CapturedRuntimeModule:
    name: str
    relative: Path
    digest: str
    content: bytes

    @property
    def origin(self) -> str:
        return f"repo://{self.relative.as_posix()}"

    @property
    def package_location(self) -> str:
        return f"repo://{self.relative.parent.as_posix()}"

    @property
    def is_package(self) -> bool:
        return self.relative.name == "__init__.py"


class _CapturedRuntimeLoader(importlib.abc.Loader):
    """Execute exactly one descriptor-captured source without reopening its path."""

    def __init__(self, captured: _CapturedRuntimeModule, root: Path) -> None:
        self._captured = captured
        self._root = root
        self._owned_module: ModuleType | None = None

    def owned_module(self) -> ModuleType | None:
        return self._owned_module

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        captured = self._captured
        if self._owned_module is not None and self._owned_module is not module:
            _fail("RUNTIME_MODULE_IDENTITY_DRIFT", "runtime.modules")
        self._owned_module = module
        specification = module.__spec__
        if (
            module.__name__ != captured.name
            or specification is None
            or specification.loader is not self
            or specification.origin != captured.origin
        ):
            _fail("RUNTIME_MODULE_SPEC_DRIFT", "runtime.modules")
        module.__file__ = str(self._root / captured.relative)
        module.__dict__["__cached__"] = None
        module.__dict__["__st1605_captured_sha256__"] = captured.digest
        try:
            code = compile(
                captured.content,
                captured.origin,
                "exec",
                dont_inherit=True,
            )
            exec(code, module.__dict__)  # noqa: S102
        except FailureInjectionDrillError:
            raise
        except Exception:
            _fail("RUNTIME_MODULE_EXECUTION_FAILED", "runtime.modules")


class _RuntimeNamespaceLoader(importlib.abc.Loader):
    """Create one explicitly allowlisted source-free RAOS namespace package."""

    def __init__(self, name: str, origin: str) -> None:
        self._name = name
        self._origin = origin
        self._owned_module: ModuleType | None = None

    def owned_module(self) -> ModuleType | None:
        return self._owned_module

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        if self._owned_module is not None and self._owned_module is not module:
            _fail("RUNTIME_MODULE_IDENTITY_DRIFT", "runtime.modules")
        self._owned_module = module
        specification = module.__spec__
        if (
            module.__name__ != self._name
            or specification is None
            or specification.loader is not self
            or specification.origin != self._origin
        ):
            _fail("RUNTIME_MODULE_SPEC_DRIFT", "runtime.modules")
        module.__file__ = None
        module.__dict__["__cached__"] = None


class _ClosedRuntimeFinder(importlib.abc.MetaPathFinder):
    """Resolve only the exact captured RAOS source and namespace inventory."""

    def __init__(
        self,
        captured: Mapping[str, _CapturedRuntimeModule],
        root: Path,
    ) -> None:
        if tuple(captured) != tuple(EXPECTED_RUNTIME_MODULES):
            _fail("RUNTIME_MODULE_INVENTORY_DRIFT", "runtime.modules")
        self._captured = dict(captured)
        self._source_loaders = {
            name: _CapturedRuntimeLoader(record, root)
            for name, record in captured.items()
        }
        self._namespace_loaders = {
            name: _RuntimeNamespaceLoader(name, self.namespace_origin(name))
            for name in RUNTIME_NAMESPACE_PACKAGES
        }

    @staticmethod
    def namespace_origin(name: str) -> str:
        return f"repo://python/{name.replace('.', '/')}"

    def source_loader(self, name: str) -> _CapturedRuntimeLoader:
        return self._source_loaders[name]

    def namespace_loader(self, name: str) -> _RuntimeNamespaceLoader:
        return self._namespace_loaders[name]

    def owned_modules(self) -> tuple[tuple[str, ModuleType], ...]:
        owned: list[tuple[str, ModuleType]] = []
        for name, source_loader in self._source_loaders.items():
            module = source_loader.owned_module()
            if module is not None:
                owned.append((name, module))
        for name, namespace_loader in self._namespace_loaders.items():
            module = namespace_loader.owned_module()
            if module is not None:
                owned.append((name, module))
        return tuple(owned)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path
        if fullname != "raos" and not fullname.startswith("raos."):
            return None
        if target is not None:
            _fail("RUNTIME_MODULE_RELOAD_FORBIDDEN", "runtime.modules")
        captured = self._captured.get(fullname)
        if captured is not None:
            specification = importlib.machinery.ModuleSpec(
                fullname,
                self._source_loaders[fullname],
                origin=captured.origin,
                is_package=captured.is_package,
            )
            if captured.is_package:
                specification.submodule_search_locations = [captured.package_location]
            return specification
        namespace_loader = self._namespace_loaders.get(fullname)
        if namespace_loader is not None:
            origin = self.namespace_origin(fullname)
            specification = importlib.machinery.ModuleSpec(
                fullname,
                namespace_loader,
                origin=origin,
                is_package=True,
            )
            specification.submodule_search_locations = [origin]
            return specification
        _fail("RUNTIME_MODULE_DEPENDENCY_UNLISTED", "runtime.modules")


def _is_raos_module_name(name: str) -> bool:
    return name == "raos" or name.startswith("raos.")


def _reject_preloaded_runtime_modules() -> None:
    if any(_is_raos_module_name(name) for name in sys.modules):
        _fail("RUNTIME_MODULE_PRELOADED", "runtime.modules")


def _capture_runtime_module_inputs(
    root: Path,
) -> Mapping[str, _CapturedRuntimeModule]:
    captured: dict[str, _CapturedRuntimeModule] = {}
    for module_name, (path, digest) in EXPECTED_RUNTIME_MODULES.items():
        relative = Path(path)
        content = _read(root, relative, "runtime.module")
        if _sha256_bytes(content) != digest:
            _fail("RUNTIME_MODULE_HASH_DRIFT", module_name)
        captured[module_name] = _CapturedRuntimeModule(
            name=module_name,
            relative=relative,
            digest=digest,
            content=content,
        )
    return MappingProxyType(captured)


def _verify_runtime_module_inputs(root: Path) -> None:
    _capture_runtime_module_inputs(root)


def _verify_loaded_runtime_inventory(finder: _ClosedRuntimeFinder, root: Path) -> None:
    expected_names = {*EXPECTED_RUNTIME_MODULES, *RUNTIME_NAMESPACE_PACKAGES}
    observed_names = {name for name in sys.modules if _is_raos_module_name(name)}
    if (
        observed_names != expected_names
        or not sys.meta_path
        or sys.meta_path[0] is not finder
    ):
        _fail("RUNTIME_MODULE_INVENTORY_DRIFT", "runtime.modules")
    for name, (path, digest) in EXPECTED_RUNTIME_MODULES.items():
        module = sys.modules.get(name)
        specification = getattr(module, "__spec__", None)
        source_loader = finder.source_loader(name)
        relative = Path(path)
        expected_locations = [f"repo://{relative.parent.as_posix()}"]
        observed_locations = (
            list(specification.submodule_search_locations)
            if specification is not None
            and specification.submodule_search_locations is not None
            else None
        )
        if (
            not isinstance(module, ModuleType)
            or module is not source_loader.owned_module()
            or getattr(module, "__loader__", None) is not source_loader
            or specification is None
            or specification.loader is not source_loader
            or specification.origin != f"repo://{relative.as_posix()}"
            or getattr(module, "__file__", None) != str(root / relative)
            or getattr(module, "__cached__", None) is not None
            or getattr(module, "__st1605_captured_sha256__", None) != digest
            or (
                observed_locations != expected_locations
                if relative.name == "__init__.py"
                else observed_locations is not None
            )
        ):
            _fail("RUNTIME_MODULE_INVENTORY_DRIFT", "runtime.modules")
    for name in RUNTIME_NAMESPACE_PACKAGES:
        module = sys.modules.get(name)
        specification = getattr(module, "__spec__", None)
        namespace_loader = finder.namespace_loader(name)
        origin = finder.namespace_origin(name)
        if (
            not isinstance(module, ModuleType)
            or module is not namespace_loader.owned_module()
            or getattr(module, "__loader__", None) is not namespace_loader
            or getattr(module, "__file__", None) is not None
            or getattr(module, "__cached__", None) is not None
            or specification is None
            or specification.loader is not namespace_loader
            or specification.origin != origin
            or list(specification.submodule_search_locations or ()) != [origin]
        ):
            _fail("RUNTIME_MODULE_INVENTORY_DRIFT", "runtime.modules")


def _import_runtime_bindings() -> _RuntimeBindings:
    from raos.adapters.development_oidc import (
        DevelopmentOidcAdapter,
        InMemoryAuthenticationRepository,
    )
    from raos.adapters.development_step_up import DevelopmentScriptedStepUpVerifier
    from raos.adapters.recorded_kill_switch import RecordedKillSwitchAdapter
    from raos.application.iam.authentication import AuthenticationService
    from raos.application.iam.step_up import StepUpGuard
    from raos.application.ops.kill_switch import KillSwitchRuntimeService
    from raos.config.runtime import RuntimeEnvironment
    from raos.domain.iam.authentication import (
        Issuer,
        PrincipalIdentity,
        Session,
        SessionId,
        Subject,
    )
    from raos.domain.iam.step_up import StepUpAssuranceType, StepUpGrant
    from raos.domain.ops.kill_switch import (
        KillSwitchCacheEntry,
        KillSwitchCacheSnapshot,
        KillSwitchContext,
        KillSwitchEligibilityCode,
        KillSwitchKind,
        KillSwitchReasonCode,
        KillSwitchState,
    )

    return _RuntimeBindings(
        DevelopmentOidcAdapter=DevelopmentOidcAdapter,
        InMemoryAuthenticationRepository=InMemoryAuthenticationRepository,
        DevelopmentScriptedStepUpVerifier=DevelopmentScriptedStepUpVerifier,
        RecordedKillSwitchAdapter=RecordedKillSwitchAdapter,
        AuthenticationService=AuthenticationService,
        StepUpGuard=StepUpGuard,
        KillSwitchRuntimeService=KillSwitchRuntimeService,
        RuntimeEnvironment=RuntimeEnvironment,
        Issuer=Issuer,
        PrincipalIdentity=PrincipalIdentity,
        Session=Session,
        SessionId=SessionId,
        Subject=Subject,
        StepUpAssuranceType=StepUpAssuranceType,
        StepUpGrant=StepUpGrant,
        KillSwitchCacheEntry=KillSwitchCacheEntry,
        KillSwitchCacheSnapshot=KillSwitchCacheSnapshot,
        KillSwitchContext=KillSwitchContext,
        KillSwitchEligibilityCode=KillSwitchEligibilityCode,
        KillSwitchKind=KillSwitchKind,
        KillSwitchReasonCode=KillSwitchReasonCode,
        KillSwitchState=KillSwitchState,
    )


def _remove_owned_runtime_modules(finder: _ClosedRuntimeFinder) -> None:
    for name, module in sorted(
        finder.owned_modules(),
        key=lambda item: (item[0].count("."), item[0]),
        reverse=True,
    ):
        if sys.modules.get(name) is module:
            del sys.modules[name]


@contextmanager
def _runtime_binding_scope(root: Path) -> Generator[_RuntimeBindings, None, None]:
    _reject_preloaded_runtime_modules()
    captured = _capture_runtime_module_inputs(root)
    _reject_preloaded_runtime_modules()
    finder = _ClosedRuntimeFinder(captured, root)
    sys.meta_path.insert(0, finder)
    try:
        runtime = _import_runtime_bindings()
        _verify_loaded_runtime_inventory(finder, root)
        yield runtime
        _verify_loaded_runtime_inventory(finder, root)
    finally:
        sys.meta_path[:] = [
            candidate for candidate in sys.meta_path if candidate is not finder
        ]
        _remove_owned_runtime_modules(finder)


def _verify_authority_rows(root: Path, rows: object) -> None:
    records = _list(rows, "authority_sources")
    if len(records) != len(EXPECTED_AUTHORITY_SOURCES):
        _fail("SOURCE_INVENTORY_DRIFT", "authority_sources")
    for index, ((role, (path, digest)), raw) in enumerate(
        zip(EXPECTED_AUTHORITY_SOURCES.items(), records, strict=True)
    ):
        row = _mapping(raw, f"authority_sources[{index}]")
        _exact(
            row,
            {"role": role, "uri": f"repo://{path}", "sha256": digest},
            f"authority_sources[{index}]",
        )
        if _sha256_bytes(_read(root, Path(path), "authority.input")) != digest:
            _fail("SOURCE_HASH_DRIFT", f"authority_sources[{index}]")


def _artifact_rows(expected: Mapping[str, str]) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path}", "sha256": digest} for path, digest in expected.items()
    ]


def _verify_artifacts(root: Path, rows: object, expected: Mapping[str, str]) -> None:
    _exact(rows, _artifact_rows(expected), "dependency.inputs")
    for path, digest in expected.items():
        if _sha256_bytes(_read(root, Path(path), "dependency.input")) != digest:
            _fail("DEPENDENCY_HASH_DRIFT", "dependency.inputs")


def _find_record(
    document: Mapping[str, Any], collection: str, record_id: str, field: str
) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for row in _list(document.get(collection), field):
        record = _mapping(row, field)
        if record.get("id") == record_id:
            matches.append(record)
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_DRIFT", field)
    return matches[0]


def _validate_authority(root: Path) -> None:
    backlog = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "backlog",
    )
    _exact(
        _find_record(backlog, "stories", "ST-1605", "backlog.stories"),
        {
            "id": "ST-1605",
            "epic_id": "EPIC-16",
            "title": "Failure injection and runbook drill",
            "objective": "provider/db/queue/kill/rollbackを演習",
            "depends_on": ["ST-1602", "ST-1405"],
            "requirement_ids": [],
            "design_refs": [],
            "deliverables": ["drill evidence"],
            "acceptance_criteria": ["safe degradation and owner response"],
            "test_suites": ["TST-028"],
            "priority": "P0",
            "mvp": True,
            "size": "L",
            "open_decisions": [],
            "one_pr_preferred": False,
            "design_status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
        },
        "backlog.ST-1605",
    )
    tests = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "test_catalog",
    )
    _exact(
        _find_record(tests, "suites", "TST-028", "test_catalog.suites"),
        {
            "id": "TST-028",
            "name": "Reliability failure injection",
            "layer": "reliability",
            "purpose": "provider/queue/db/timeouts/retry/kill switch",
            "candidate_tools": ["fault proxy", "scripts"],
            "release_blocking": True,
            "environments": ["staging"],
            "owner": "Engineering",
            "design_status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_status": "NOT_STARTED",
            "execution_status": "NOT_EXECUTED",
        },
        "test_catalog.TST-028",
    )
    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "open_decisions",
    )
    _exact(
        _find_record(decisions, "items", "OD-011", "open_decisions.items"),
        {
            "id": "OD-011",
            "topic": "notification_channels",
            "status": "HUMAN_DECISION_REQUIRED",
            "required_by": "Incident operations",
            "owner": "Operations Owner",
            "decision_needed": "Critical/High通知先とEscalation連絡先を設定",
            "default_behavior": "Local logのみ。Production不可",
            "blocking": True,
        },
        "open_decisions.OD-011",
    )
    runbooks = _load_yaml(
        root,
        Path("docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml"),
        "runbooks",
    )
    expected_runbooks = {
        "RB-005": ("Database outage", "SEV2"),
        "RB-006": ("Queue backlog/retry storm", "SEV2"),
        "RB-008": ("Rakuten API outage/schema drift", "SEV2/3"),
        "RB-009": ("OpenAI outage/model regression", "SEV2/3"),
        "RB-014": ("Release rollback", "SEV2/3"),
        "RB-015": ("Kill switch activation/deactivation", "SEV1/2"),
    }
    for runbook_id, (title, severity) in expected_runbooks.items():
        row = _find_record(runbooks, "runbooks", runbook_id, "runbooks.rows")
        if (
            row.get("title") != title
            or row.get("severity") != severity
            or row.get("document_status") != "DESIGNED_INDEX_ONLY"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("drill_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_RECORD_DRIFT", f"runbooks.{runbook_id}")
    controls = _load_yaml(
        root,
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "security_controls",
    )
    for control_id in ("SEC-GOV-007", "SEC-IAM-003", "SEC-OPS-007"):
        row = _find_record(controls, "controls", control_id, "controls.rows")
        if (
            row.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_RECORD_DRIFT", f"controls.{control_id}")
    threats = _load_yaml(
        root,
        Path("docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"),
        "threats",
    )
    for threat_id in ("THR-016", "THR-017"):
        row = _find_record(threats, "threats", threat_id, "threats.rows")
        if (
            row.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_RECORD_DRIFT", f"threats.{threat_id}")


def _expected_dependencies() -> dict[str, object]:
    return {
        "slo_alert_reference": {
            "story_id": "ST-1602",
            "inputs": _artifact_rows(EXPECTED_ST1602_HASHES),
            "required_classification": (
                "SOURCE_DERIVED_NON_ATTESTING_SLO_ALERT_REFERENCE_PLAN"
            ),
            "required_decision": "NOT_READY",
            "required_story_acceptance": False,
            "required_production_eligible": False,
            "open_decision_id": "OD-011",
            "safe_default": "LOCAL_LOG_ONLY",
            "notifications_enabled": False,
            "formal_tst_028": "NOT_EXECUTED",
            "external_actions": "FORBIDDEN",
        },
        "kill_switch_runtime": {
            "story_id": "ST-1405",
            "inputs": _artifact_rows(EXPECTED_ST1405_HASHES),
            "target_adapter_environment": "ENV-CI",
            "step_up_fixture_environment": "ENV-DEV",
            "adapter": "RecordedKillSwitchAdapter",
            "service": "KillSwitchRuntimeService",
            "switch_kind": "PUBLICATION",
            "scope_types": ["GLOBAL", "SITE", "CATEGORY", "ARTICLE"],
            "expected_eligibility": "ENGAGED",
            "expected_allowed": False,
            "command_execution": "FORBIDDEN",
            "state_mutation": "FORBIDDEN",
            "event_delivery": "FORBIDDEN",
            "external_io": "FORBIDDEN",
        },
    }


def _validate_dependencies(contract: Mapping[str, Any], root: Path) -> None:
    dependencies = _mapping(contract["dependency_bindings"], "dependencies")
    _exact(dependencies, _expected_dependencies(), "dependencies")
    slo = _mapping(dependencies["slo_alert_reference"], "dependencies.ST-1602")
    kill = _mapping(dependencies["kill_switch_runtime"], "dependencies.ST-1405")
    _verify_artifacts(root, slo["inputs"], EXPECTED_ST1602_HASHES)
    _verify_artifacts(root, kill["inputs"], EXPECTED_ST1405_HASHES)
    for path, digest in EXPECTED_IMPLEMENTATION_HASHES.items():
        if _sha256_bytes(_read(root, Path(path), "implementation.input")) != digest:
            _fail("IMPLEMENTATION_DEPENDENCY_DRIFT", "implementation")
    _verify_runtime_module_inputs(root)

    st1602 = _load_json(
        root,
        Path("changes/st-1602/generated/slo-alert-reference-plan.v1.json"),
        "st1602.plan",
    )
    document = _mapping(st1602.get("document"), "st1602.document")
    if (
        document.get("classification")
        != "SOURCE_DERIVED_NON_ATTESTING_SLO_ALERT_REFERENCE_PLAN"
        or document.get("executable") is not False
        or document.get("decision") != "NOT_READY"
        or document.get("story_acceptance") is not False
        or document.get("production_eligible") is not False
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1602.document")
    open_decision = _mapping(st1602.get("open_decision"), "st1602.OD-011")
    if (
        open_decision.get("id") != "OD-011"
        or open_decision.get("safe_default") != "LOCAL_LOG_ONLY"
        or open_decision.get("notifications_enabled") is not False
        or open_decision.get("channel") is not None
        or open_decision.get("escalation_contact") is not None
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1602.OD-011")
    verification = _mapping(st1602.get("verification_boundary"), "st1602.verification")
    if (
        verification.get("formal_tst_028") != "NOT_EXECUTED"
        or verification.get("staging") != "NOT_EXECUTED"
        or verification.get("story_acceptance") is not False
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1602.verification")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _verify_authority_rows(root, contract["authority_sources"])
    _validate_authority(root)
    _validate_dependencies(contract, root)
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution")
    _exact(contract["deterministic_fixture"], EXPECTED_FIXTURE, "fixture")
    _exact(contract["scenarios"], EXPECTED_SCENARIOS, "scenarios")
    _exact(contract["evidence_boundary"], EXPECTED_EVIDENCE, "evidence")
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


class _ScriptedEntropy:
    """Fixed local entropy source required only to construct an inert guard."""

    def __init__(self) -> None:
        self._values = [bytes(range(32)), bytes(range(32, 64))]

    def token_bytes(self, size: int) -> bytes:
        if size != 32 or not self._values:
            _fail("FIXTURE_INVALID", "kill_switch.step_up")
        return self._values.pop(0)


def _fixed_step_up_guard(
    now: datetime, runtime: _RuntimeBindings, fixture_environment: object
) -> object:
    if fixture_environment is not runtime.RuntimeEnvironment.ENV_DEV:
        _fail("FIXTURE_ENVIRONMENT_INVALID", "kill_switch.step_up.environment")
    principal = runtime.PrincipalIdentity(
        issuer=runtime.Issuer("https://st1605.synthetic.invalid"),
        subject=runtime.Subject("st1605-synthetic-operator"),
        display_name="ST-1605 Synthetic Operator",
    )
    session = runtime.Session(
        session_id=runtime.SessionId.from_bytes(bytes(range(64, 96))),
        principal=principal,
        created_at=now - timedelta(minutes=10),
        last_seen_at=now - timedelta(minutes=1),
        idle_expires_at=now + timedelta(hours=2),
        absolute_expires_at=now + timedelta(hours=8),
    )
    repository = runtime.InMemoryAuthenticationRepository(
        environment=fixture_environment
    )
    repository.create_session(session)
    service = runtime.AuthenticationService(
        provider=runtime.DevelopmentOidcAdapter(
            environment=fixture_environment,
            principal=principal,
        ),
        repository=repository,
        entropy=_ScriptedEntropy(),
        session_idle_lifetime=timedelta(hours=2),
        session_absolute_lifetime=timedelta(hours=8),
    )
    grant = runtime.StepUpGrant(
        session_id=session.session_id,
        issuer=principal.issuer,
        subject=principal.subject,
        assurance_type=runtime.StepUpAssuranceType.MULTI_FACTOR,
        authenticated_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=8),
    )
    verifier = runtime.DevelopmentScriptedStepUpVerifier(
        environment=fixture_environment,
        grants=(grant,),
    )
    return runtime.StepUpGuard(session_service=service, verifier=verifier)


def _kill_switch_observation_with_runtime(
    fixture: Mapping[str, Any], runtime_modules: _RuntimeBindings
) -> dict[str, object]:
    now = datetime(2026, 8, 16, 0, 0, tzinfo=UTC)
    target_adapter_environment = runtime_modules.RuntimeEnvironment.CI
    step_up_fixture_environment = runtime_modules.RuntimeEnvironment.ENV_DEV
    if fixture.get("observation_time") != "2026-08-16T00:00:00Z":
        _fail("FIXTURE_INVALID", "fixture.observation_time")
    context = runtime_modules.KillSwitchContext(
        site_id=UUID(str(fixture["site_id"])),
        category_id=UUID(str(fixture["category_id"])),
        article_id=UUID(str(fixture["article_id"])),
    )
    keys = context.required_keys(runtime_modules.KillSwitchKind.PUBLICATION)
    reason = runtime_modules.KillSwitchReasonCode(str(fixture["kill_switch_reason"]))
    generation = fixture["kill_switch_generation"]
    if type(generation) is not int:
        _fail("FIXTURE_INVALID", "fixture.kill_switch_generation")
    states = tuple(
        runtime_modules.KillSwitchState(
            switch_id=(
                UUID(str(fixture["kill_switch_id"]))
                if index == 0
                else UUID(int=160_500 + index)
            ),
            key=key,
            engaged=index == 0,
            generation=generation if index == 0 else 0,
            reason=reason,
            changed_at=now - timedelta(minutes=1),
        )
        for index, key in enumerate(keys)
    )
    snapshot = runtime_modules.KillSwitchCacheSnapshot(
        switch_type=runtime_modules.KillSwitchKind.PUBLICATION,
        entries=tuple(
            runtime_modules.KillSwitchCacheEntry(
                state=state, minimum_generation=state.generation
            )
            for state in states
        ),
        loaded_at=now - timedelta(seconds=1),
        fresh_until=now + timedelta(minutes=1),
        complete=True,
    )
    adapter = runtime_modules.RecordedKillSwitchAdapter(
        environment=target_adapter_environment,
        event_namespace=UUID(str(fixture["event_namespace"])),
        capacity=16,
        states=states,
        cache_snapshots=(snapshot,),
    )
    runtime = runtime_modules.KillSwitchRuntimeService(
        store=adapter,
        cache=adapter,
        step_up_guard=_fixed_step_up_guard(
            now, runtime_modules, step_up_fixture_environment
        ),
    )
    decision = runtime.publication_commands_allowed(context=context, now=now)
    if (
        decision.code is not runtime_modules.KillSwitchEligibilityCode.ENGAGED
        or decision.allowed is not False
        or adapter.event_intents() != ()
        or any(adapter.current_state(state.key) != state for state in states)
    ):
        _fail("KILL_SWITCH_SEAM_FAILED", "scenario.FI-005")
    return {
        "outcome_code": "PUBLICATION_COMMANDS_DENIED",
        "required_response": "KEEP_SWITCH_ENGAGED",
        "guard_state": "ENGAGED_GENERATION_7",
        "public_state": "PUBLICATION_COMMAND_PATH_DENIED",
        "operation_executed": False,
        "external_effect": "NONE",
        "target_adapter_environment": target_adapter_environment.value,
        "step_up_fixture_environment": step_up_fixture_environment.value,
        "eligibility_code": decision.code.value,
        "allowed": decision.allowed,
        "observed_generation": generation,
        "event_intent_count": len(adapter.event_intents()),
    }


def _kill_switch_observation(
    fixture: Mapping[str, Any], root: Path
) -> dict[str, object]:
    with _runtime_binding_scope(root) as runtime_modules:
        return _kill_switch_observation_with_runtime(fixture, runtime_modules)


def _recorded_synthetic_response(
    scenario_id: str, observation: Mapping[str, object]
) -> dict[str, object]:
    """Record one deterministic responder selection without a real owner/action."""

    response_code = observation.get("required_response")
    response_time = RECORDED_RESPONSE_TIMES.get(scenario_id)
    if type(response_code) is not str or type(response_time) is not str:
        _fail("RECORDED_RESPONSE_INVALID", "scenario.response")
    return {
        "classification": "RECORDED_SYNTHETIC_RESPONDER_RESPONSE",
        "status": "LOCAL_RESPONSE_SELECTION_RECORDED",
        "responder_class": "SYNTHETIC_ENGINEERING_FIXTURE",
        "actual_owner_contacted": False,
        "route": "LOCAL_LOG_ONLY",
        "notification_delivery": "NOT_EXECUTED",
        "selected_response_code": response_code,
        "response_recorded_at": response_time,
        "operation_executed": False,
        "execution_authority": "NONE",
        "external_effect": "NONE",
    }


def execute_scenarios(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> list[dict[str, object]]:
    fixture = _mapping(contract["deterministic_fixture"], "fixture")
    rows = _list(contract["scenarios"], "scenarios")
    results: list[dict[str, object]] = []
    for index, raw in enumerate(rows):
        scenario = _mapping(raw, f"scenarios[{index}]")
        scenario_id = scenario.get("id")
        if type(scenario_id) is not str:
            _fail("SCENARIO_INVALID", f"scenarios[{index}].id")
        observation = (
            _kill_switch_observation(fixture, root)
            if scenario_id == "FI-005"
            else STATIC_OBSERVATIONS.get(scenario_id)
        )
        if observation is None:
            _fail("SCENARIO_UNKNOWN", f"scenarios[{index}]")
        _exact(
            observation,
            scenario.get("expected_observation"),
            f"scenarios[{index}].observation",
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                scenario,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        behavior_observed = scenario_id == "FI-005"
        recorded_response = _recorded_synthetic_response(scenario_id, observation)
        results.append(
            {
                "scenario_id": scenario_id,
                "target": scenario["target"],
                "fault": scenario["fault"],
                "runbook_reference": scenario["runbook_id"],
                "alert_reference": scenario["alert_id"],
                "status": (
                    "LOCAL_SYNTHETIC_BEHAVIOR_OBSERVED"
                    if behavior_observed
                    else "STATIC_TABLETOP_REFERENCE"
                ),
                "behavior_observed": behavior_observed,
                "recorded_safe_degradation_evaluation": True,
                "recorded_synthetic_response": recorded_response,
                "input_fingerprint": fingerprint,
                "observation": observation,
                "external_action_counts": dict(ZERO_ACTIONS),
            }
        )
    return results


def evidence_document(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, object]:
    results = execute_scenarios(contract, root)
    return {
        "schema_version": "1.0.0",
        "generator": {
            "uri": GENERATOR_URI,
            "command": GENERATION_COMMAND,
            "source_contract": SOURCE_URI,
        },
        "story": {
            "id": "ST-1605",
            "scope": "DETERMINISTIC_DEV_CI_LOCAL_SYNTHETIC_SLICE",
            "effective_canonical_status": "UNCHANGED",
            "acceptance_criteria_satisfied": False,
        },
        "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
        "authority_sources": contract["authority_sources"],
        "dependency_bindings": contract["dependency_bindings"],
        "execution_boundary": contract["execution_boundary"],
        "deterministic_fixture": contract["deterministic_fixture"],
        "scenario_results": results,
        "summary": {
            "scenario_count": len(results),
            "behavioral_observation_count": sum(
                row["behavior_observed"] is True for row in results
            ),
            "static_tabletop_reference_count": sum(
                row["status"] == "STATIC_TABLETOP_REFERENCE" for row in results
            ),
            "behavioral_observation_scenario_ids": [
                row["scenario_id"]
                for row in results
                if row["behavior_observed"] is True
            ],
            "recorded_safe_degradation_evaluation_count": sum(
                row["recorded_safe_degradation_evaluation"] is True for row in results
            ),
            "recorded_synthetic_response_count": sum(
                type(row["recorded_synthetic_response"]) is dict for row in results
            ),
            "external_action_counts": dict(ZERO_ACTIONS),
        },
        "evidence_boundary": contract["evidence_boundary"],
        "prohibited_interpretations": [
            "STATIC_TABLETOP_REFERENCE_IS_NOT_BEHAVIOR_OBSERVED",
            "LOCAL_SYNTHETIC_BEHAVIOR_OBSERVED_IS_NOT_FORMAL_TST_028",
            "MODELED_SAFE_RESPONSE_IS_NOT_OWNER_RESPONSE",
            "RECORDED_SYNTHETIC_RESPONSE_IS_NOT_ACTUAL_OWNER_RESPONSE",
            "RUNBOOK_REFERENCE_IS_NOT_RUNBOOK_VALIDATION",
            "PROVIDER_FAILURE_TOKEN_IS_NOT_PROVIDER_BEHAVIOR",
            "IN_PROCESS_SEAM_IS_NOT_STAGING_KILL_SWITCH_EVIDENCE",
            "ROLLBACK_TABLETOP_IS_NOT_ROLLBACK_EXECUTION",
            "NO_STORY_ACCEPTANCE_RELEASE_OR_PRODUCTION_ELIGIBILITY_MAY_BE_INFERRED",
        ],
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.input")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def _manifest_bytes(root: Path, evidence_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST1605-FAILURE-INJECTION-DRILL-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1605",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256_bytes(
                _read(root, CONTRACT_PATH, "manifest.contract")
            ),
            "authority_inputs": [
                {"role": role, "uri": f"repo://{path}", "sha256": digest}
                for role, (path, digest) in EXPECTED_AUTHORITY_SOURCES.items()
            ],
            "dependency_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in (
                    *EXPECTED_ST1602_HASHES.items(),
                    *EXPECTED_ST1405_HASHES.items(),
                )
            ],
            "implementation_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_IMPLEMENTATION_HASHES.items()
            ],
            "runtime_module_inputs": [
                {
                    "module": module_name,
                    "uri": f"repo://{path}",
                    "sha256": digest,
                }
                for module_name, (path, digest) in EXPECTED_RUNTIME_MODULES.items()
            ],
            "runtime_namespace_packages": list(RUNTIME_NAMESPACE_PACKAGES),
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{EVIDENCE_PATH.as_posix()}",
                "bytes": len(evidence_bytes),
                "sha256": _sha256_bytes(evidence_bytes),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
            "formal_tst_028": "NOT_EXECUTED",
            "recorded_safe_degradation_evaluations": 6,
            "recorded_synthetic_responder_responses": 6,
            "recorded_synthetic_responder_is_actual_owner": False,
            "owner_response": "NOT_EXECUTED",
            "runbook_validation": "NOT_EXECUTED",
            "staging_drill": "NOT_EXECUTED",
            "story_acceptance": False,
            "st_1607_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    evidence_bytes = _json_bytes(evidence_document(contract, root))
    return {
        EVIDENCE_PATH: evidence_bytes,
        MANIFEST_PATH: _manifest_bytes(root, evidence_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        actual = base._read_repository_file(  # noqa: SLF001
            root,
            relative,
            "output",
            max_bytes=base.MAX_DOCUMENT_BYTES,
            size_error_code="GENERATED_OUTPUT_DRIFT",
            path_error_code="UNSAFE_OUTPUT_PATH",
            missing_error_code="GENERATED_OUTPUT_UNAVAILABLE",
            ancestor_error_code="UNSAFE_OUTPUT_ANCESTOR",
            file_type_error_code="UNSAFE_FILE_TYPE",
        )
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(root, relative, content)  # noqa: SLF001


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def _require_hardened_cli() -> None:
    if sys.flags.isolated != 1:
        _fail("ISOLATED_MODE_REQUIRED", "cli.python")
    if sys.flags.dont_write_bytecode != 1:
        _fail("NO_BYTECODE_MODE_REQUIRED", "cli.python")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _require_hardened_cli()
        build(check=args.check)
    except (FailureInjectionDrillError, base.ProductionDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1605 local synthetic failure-injection evidence checked"
        if args.check
        else "ST-1605 local synthetic failure-injection evidence generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
