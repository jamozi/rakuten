#!/usr/bin/env python3
"""Closed operator CLI for kurashinoshirube.com WordPress maintenance.

Human approval is intentionally absent.  A proposal must be approved in the
separate WordPress administrator Tools screen before its matching apply command
can succeed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import io
import importlib
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
from typing import Final, NoReturn, Protocol, cast
import types
import zipfile


_EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
_EXPECTED_PYTHON: Final = _EXPECTED_REPOSITORY_ROOT / ".venv/bin/python"
_EXPECTED_PYTHON_BASE: Final = Path(
    "/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu"
)
_STAGE_HEAD_ENV: Final = "RAOS_ST1506_STAGE_HEAD"
_STAGE_CLI_BLOB_ENV: Final = "RAOS_ST1506_STAGE_CLI_BLOB"
_STAGE_CLI_SHA256_ENV: Final = "RAOS_ST1506_STAGE_CLI_SHA256"
_STAGE_REFUSAL: Final = "ST1506_WORDPRESS_OPERATOR_LAUNCH_REFUSED"
_STAGE_MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
_STAGE_GIT_ENVIRONMENT: Final = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_STAGE_RUNTIME_PATHS: Final = (
    "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/runtime-manifest.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json",
    "python/raos/__init__.py",
    "python/raos/adapters/__init__.py",
    "python/raos/adapters/self_hosted_wordpress_operator_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_operator_https.py",
    "python/raos/domain/operations/self_hosted_wordpress_operator.py",
    "python/raos/ports/__init__.py",
    "python/raos/ports/self_hosted_wordpress_operator.py",
    "scripts/build_st1704_self_hosted_editorial_manifest.py",
    "scripts/build_st1704_self_hosted_theme.py",
    "scripts/st1506_wordpress_operator.py",
    "scripts/st1506_wordpress_operator_python.sh",
)
_STAGE_MODULE_PATHS: Final = {
    "raos.adapters.self_hosted_wordpress_operator_credentials": (
        "python/raos/adapters/self_hosted_wordpress_operator_credentials.py"
    ),
    "raos.adapters.self_hosted_wordpress_operator_https": (
        "python/raos/adapters/self_hosted_wordpress_operator_https.py"
    ),
    "raos.domain.operations.self_hosted_wordpress_operator": (
        "python/raos/domain/operations/self_hosted_wordpress_operator.py"
    ),
    "raos.ports.self_hosted_wordpress_operator": (
        "python/raos/ports/self_hosted_wordpress_operator.py"
    ),
    "scripts.build_st1704_self_hosted_editorial_manifest": (
        "scripts/build_st1704_self_hosted_editorial_manifest.py"
    ),
    "scripts.build_st1704_self_hosted_theme": (
        "scripts/build_st1704_self_hosted_theme.py"
    ),
}
_STAGE_PACKAGE_NAMES: Final = (
    "raos",
    "raos.adapters",
    "raos.domain",
    "raos.domain.operations",
    "raos.ports",
    "scripts",
)
_STAGE_ZERO_VERIFIED = False
_STAGE_VERIFIED_BYTES: dict[str, bytes] | None = None


def _stage_refuse() -> NoReturn:
    print(_STAGE_REFUSAL, file=sys.stderr)
    raise SystemExit(69) from None


def _stage_git(*arguments: str, maximum_stdout: int) -> bytes:
    if (
        not arguments
        or any(type(value) is not str or not value for value in arguments)
        or type(maximum_stdout) is not int
        or not 0 <= maximum_stdout <= _STAGE_MAX_SOURCE_BYTES
    ):
        _stage_refuse()
    try:
        result = subprocess.run(
            (
                "/usr/bin/git",
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                _EXPECTED_REPOSITORY_ROOT.as_posix(),
                *arguments,
            ),
            check=False,
            env=_STAGE_GIT_ENVIRONMENT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except BaseException:
        _stage_refuse()
    if result.returncode != 0 or len(result.stdout) > maximum_stdout:
        _stage_refuse()
    return result.stdout


def _stage_head_bytes(head: str, relative: str) -> bytes:
    object_name = f"{head}:{relative}"
    raw_size = _stage_git("cat-file", "-s", object_name, maximum_stdout=80)
    try:
        size_text = raw_size.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _stage_refuse()
    if str(size) != size_text or not 1 <= size <= _STAGE_MAX_SOURCE_BYTES:
        _stage_refuse()
    payload = _stage_git(
        "cat-file", "blob", object_name, maximum_stdout=_STAGE_MAX_SOURCE_BYTES
    )
    if len(payload) != size:
        _stage_refuse()
    return payload


def _stage_working_bytes(relative: str) -> bytes:
    path = _EXPECTED_REPOSITORY_ROOT / relative
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _stage_refuse()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or not 1 <= metadata.st_size <= _STAGE_MAX_SOURCE_BYTES
        or len(payload) != metadata.st_size
    ):
        _stage_refuse()
    return payload


class _VerifiedSourceLoader(importlib.abc.Loader):
    """Compile one already verified committed source without reopening its path."""

    __slots__ = ("_fullname", "_payload", "_relative")

    def __init__(self, fullname: str, relative: str, payload: bytes) -> None:
        if (
            type(fullname) is not str
            or not fullname
            or type(relative) is not str
            or relative not in _STAGE_RUNTIME_PATHS
            or type(payload) is not bytes
            or not 1 <= len(payload) <= _STAGE_MAX_SOURCE_BYTES
        ):
            _stage_refuse()
        self._fullname = fullname
        self._relative = relative
        self._payload = payload

    def create_module(
        self, spec: importlib.machinery.ModuleSpec
    ) -> types.ModuleType | None:
        del spec
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        if module.__name__ != self._fullname:
            _stage_refuse()
        filename = (_EXPECTED_REPOSITORY_ROOT / self._relative).as_posix()
        try:
            code = compile(self._payload, filename, "exec", dont_inherit=True)
            module.__file__ = filename
            setattr(module, "__cached__", None)
            module.__loader__ = self
            module.__package__ = self._fullname.rpartition(".")[0]
            exec(code, module.__dict__)
        except SystemExit:
            raise
        except BaseException:
            _stage_refuse()


class _VerifiedSourceFinder(importlib.abc.MetaPathFinder):
    """Resolve the closed operator module set only from captured committed bytes."""

    __slots__ = ("_payloads",)

    def __init__(self, verified_bytes: dict[str, bytes]) -> None:
        required_paths = set(_STAGE_MODULE_PATHS.values())
        if required_paths - set(verified_bytes):
            _stage_refuse()
        self._payloads = {
            fullname: verified_bytes[relative]
            for fullname, relative in _STAGE_MODULE_PATHS.items()
        }

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        relative = _STAGE_MODULE_PATHS.get(fullname)
        if relative is not None:
            return importlib.machinery.ModuleSpec(
                fullname,
                _VerifiedSourceLoader(fullname, relative, self._payloads[fullname]),
                origin=(_EXPECTED_REPOSITORY_ROOT / relative).as_posix(),
                is_package=False,
            )
        if fullname.startswith("raos.") or fullname.startswith("scripts."):
            _stage_refuse()
        return None


def _install_verified_runtime_imports(verified_bytes: dict[str, bytes]) -> None:
    """Install sealed package roots and an in-memory finder before runtime imports."""

    if (
        not _STAGE_ZERO_VERIFIED
        or type(verified_bytes) is not dict
        or any(
            name == package or name.startswith(f"{package}.")
            for name in sys.modules
            for package in ("raos", "scripts")
        )
    ):
        _stage_refuse()
    for name in _STAGE_PACKAGE_NAMES:
        module = types.ModuleType(name)
        module.__package__ = name
        module.__loader__ = None
        specification = importlib.machinery.ModuleSpec(
            name, loader=None, is_package=True
        )
        specification.submodule_search_locations = []
        module.__spec__ = specification
        setattr(module, "__path__", [])
        sys.modules[name] = module
        parent_name, separator, child_name = name.rpartition(".")
        if separator:
            parent = sys.modules.get(parent_name)
            if parent is None:
                _stage_refuse()
            setattr(parent, child_name, module)
    sys.meta_path.insert(0, _VerifiedSourceFinder(verified_bytes))


def _verify_stage_zero() -> None:
    """Verify the fixed launcher, interpreter, HEAD, and source bytes pre-import."""

    global _STAGE_VERIFIED_BYTES, _STAGE_ZERO_VERIFIED
    expected_environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    try:
        stage_head = os.environ.pop(_STAGE_HEAD_ENV)
        stage_cli_blob = os.environ.pop(_STAGE_CLI_BLOB_ENV)
        stage_cli_sha256 = os.environ.pop(_STAGE_CLI_SHA256_ENV)
        stdin_metadata = os.fstat(0)
        current_directory = os.getcwd()
        resolved_root = _EXPECTED_REPOSITORY_ROOT.resolve(strict=True)
    except (KeyError, OSError):  # fmt: skip
        _stage_refuse()
    if (
        __name__ != "__main__"
        or globals().get("__file__") != "<stdin>"
        or current_directory != _EXPECTED_REPOSITORY_ROOT.as_posix()
        or resolved_root != _EXPECTED_REPOSITORY_ROOT
        or dict(os.environ) != expected_environment
        or sys.version_info[:3] != (3, 14, 6)
        or sys.executable != _EXPECTED_PYTHON.as_posix()
        or Path(sys.prefix) != _EXPECTED_REPOSITORY_ROOT / ".venv"
        or Path(sys.base_prefix) != _EXPECTED_PYTHON_BASE
        or sys.flags.dont_write_bytecode != 1
        or sys.flags.ignore_environment != 1
        or sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or sys.flags.no_user_site != 1
        or not sys.flags.safe_path
        or sys.pycache_prefix != "/dev/null"
        or sys.argv[0] != "-"
        or tuple(sys.orig_argv[:7])
        != (
            _EXPECTED_PYTHON.as_posix(),
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            "-",
        )
        or sys.orig_argv[7:] != sys.argv[1:]
        or os.isatty(0)
        or not stat.S_ISFIFO(stdin_metadata.st_mode)
        or any(
            name == "raos"
            or name.startswith("raos.")
            or name == "scripts"
            or name.startswith("scripts.")
            or name in {"site", "sitecustomize", "usercustomize"}
            for name in sys.modules
        )
        or len(stage_head) != 40
        or any(character not in "0123456789abcdef" for character in stage_head)
        or len(stage_cli_blob) != 40
        or any(character not in "0123456789abcdef" for character in stage_cli_blob)
        or len(stage_cli_sha256) != 64
        or any(character not in "0123456789abcdef" for character in stage_cli_sha256)
    ):
        _stage_refuse()
    top = _stage_git("rev-parse", "--show-toplevel", maximum_stdout=256)
    current_head = _stage_git(
        "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=80
    ).strip()
    if top != os.fsencode(
        _EXPECTED_REPOSITORY_ROOT.as_posix()
    ) + b"\n" or current_head != stage_head.encode("ascii"):
        _stage_refuse()
    verified_bytes: dict[str, bytes] = {}
    cli_bytes: bytes | None = None
    for relative in _STAGE_RUNTIME_PATHS:
        committed = _stage_head_bytes(stage_head, relative)
        if committed != _stage_working_bytes(relative):
            _stage_refuse()
        verified_bytes[relative] = committed
        if relative == "scripts/st1506_wordpress_operator.py":
            cli_bytes = committed
            object_id = _stage_git(
                "rev-parse",
                "--verify",
                f"{stage_head}:{relative}",
                maximum_stdout=80,
            ).strip()
            if object_id != stage_cli_blob.encode("ascii"):
                _stage_refuse()
    if cli_bytes is None or hashlib.sha256(cli_bytes).hexdigest() != stage_cli_sha256:
        _stage_refuse()
    if _stage_git(
        "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=80
    ).strip() != current_head or set(verified_bytes) != set(_STAGE_RUNTIME_PATHS):
        _stage_refuse()
    _STAGE_VERIFIED_BYTES = verified_bytes
    _STAGE_ZERO_VERIFIED = True


if __name__ == "__main__":
    _verify_stage_zero()
    if _STAGE_VERIFIED_BYTES is None:
        _stage_refuse()
    _install_verified_runtime_imports(_STAGE_VERIFIED_BYTES)


REPOSITORY_ROOT: Final = (
    _EXPECTED_REPOSITORY_ROOT
    if _STAGE_ZERO_VERIFIED
    else Path(__file__).resolve().parents[1]
)
if not _STAGE_ZERO_VERIFIED:
    for _import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "python"):
        if str(_import_root) not in sys.path:
            sys.path.insert(0, str(_import_root))

from raos.adapters.self_hosted_wordpress_operator_https import (  # noqa: E402
    OfficialSelfHostedWordPressOperatorAdapter,
)
from raos.adapters.self_hosted_wordpress_operator_credentials import (  # noqa: E402
    OwnerPrivateWordPressOperatorProposalIntentJournal,
)
from raos.domain.operations.self_hosted_wordpress_operator import (  # noqa: E402
    OperatorProposal,
    ProposalReceipt,
    ThemeFileManifestEntry,
    ThemePackage,
    WORDPRESS_OPERATOR_THEME_FROM_VERSION,
    WordPressOperatorFailure,
    WordPressOperatorFailureCode,
    WordPressOperatorChecksumStatus,
    WordPressOperatorOperation,
    WordPressOperatorProposalState,
    fail_wordpress_operator,
    require_sha256,
)


class _ThemeBuilder(Protocol):
    THEME_SLUG: str
    THEME_VERSION: str
    SOURCE_FILES: tuple[str, ...]

    def validate_sources(self) -> dict[str, str]: ...

    def build_package(self) -> bytes: ...


class _RuntimeManifestBuilder(Protocol):
    OUTPUT_PATH: Path

    def build_manifest(self) -> bytes: ...


theme_builder = cast(
    _ThemeBuilder, importlib.import_module("scripts.build_st1704_self_hosted_theme")
)
runtime_manifest_builder = cast(
    _RuntimeManifestBuilder,
    importlib.import_module("scripts.build_st1704_self_hosted_editorial_manifest"),
)


_RESULT_SCHEMA: Final = "RAOS_WORDPRESS_OPERATOR_CLI_RESULT_V1"
_ERROR_SCHEMA: Final = "RAOS_WORDPRESS_OPERATOR_CLI_ERROR_V1"
_SANITIZED_EXCEPTIONS: Final = (OSError, ValueError, TypeError, RuntimeError)
_ST1704_RUNTIME_MANIFEST_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
)
_ST1704_THEME_PREFIX: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/"
)
_MAX_RUNTIME_MANIFEST_BYTES: Final = 256 * 1024
_GIT_ENVIRONMENT: Final = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}


def _fail(code: WordPressOperatorFailureCode) -> NoReturn:
    fail_wordpress_operator(code)


class _SanitizedArgumentParser(argparse.ArgumentParser):
    """Argparse without echoing untrusted argv in an error message."""

    def error(self, message: str) -> NoReturn:
        del message
        _fail(WordPressOperatorFailureCode.INVALID_ARGUMENT)


def _git(*arguments: str, maximum_stdout: int) -> bytes:
    if type(maximum_stdout) is not int or not 1 <= maximum_stdout <= 4 * 1024 * 1024:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    try:
        completed = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-C",
                REPOSITORY_ROOT.as_posix(),
                *arguments,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_GIT_ENVIRONMENT,
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    if completed.returncode != 0 or len(completed.stdout) > maximum_stdout:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    return completed.stdout


def _committed_st1704_runtime_manifest() -> bytes:
    expected_root = os.fsencode(REPOSITORY_ROOT.as_posix()) + b"\n"
    if (
        _git(
            "rev-parse",
            "--show-toplevel",
            maximum_stdout=max(128, len(expected_root)),
        )
        != expected_root
    ):
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    head = _git("rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=128).strip()
    if len(head) not in {40, 64} or any(
        byte not in b"0123456789abcdef" for byte in head
    ):
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    object_spec = head.decode("ascii") + ":" + _ST1704_RUNTIME_MANIFEST_RELATIVE
    raw_size = _git("cat-file", "-s", object_spec, maximum_stdout=128)
    try:
        size_text = raw_size.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    if str(size) != size_text or not 1 <= size <= _MAX_RUNTIME_MANIFEST_BYTES:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    payload = _git("cat-file", "blob", object_spec, maximum_stdout=size)
    if len(payload) != size:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    final_head = _git(
        "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=128
    ).strip()
    if final_head != head:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    return payload


def _bound_st1704_runtime_manifest() -> bytes:
    if not _STAGE_ZERO_VERIFIED:
        return _committed_st1704_runtime_manifest()
    if _STAGE_VERIFIED_BYTES is None:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    payload = _STAGE_VERIFIED_BYTES.get(_ST1704_RUNTIME_MANIFEST_RELATIVE)
    if (
        type(payload) is not bytes
        or not 1 <= len(payload) <= _MAX_RUNTIME_MANIFEST_BYTES
    ):
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    return payload


def _strict_manifest_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise ValueError
        value[key] = item
    return value


def _bound_theme_entries(manifest: bytes) -> dict[str, tuple[int, str]]:
    try:
        value = json.loads(
            manifest.decode("ascii", errors="strict"),
            object_pairs_hook=_strict_manifest_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, TypeError, RecursionError):  # fmt: skip
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    if (
        type(value) is not dict
        or value.get("schema") != "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1"
        or value.get("slice_id") != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or value.get("story_id") != "ST-1704"
        or type(value.get("paths")) is not list
    ):
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    entries: dict[str, tuple[int, str]] = {}
    for raw in cast(list[object], value["paths"]):
        if type(raw) is not dict:
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        item = cast(dict[object, object], raw)
        if (
            set(item) != {"bytes", "path", "sha256"}
            or type(item["path"]) is not str
            or type(item["bytes"]) is not int
            or type(item["sha256"]) is not str
        ):
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        path = item["path"]
        if not path.startswith(_ST1704_THEME_PREFIX):
            continue
        relative = path.removeprefix(_ST1704_THEME_PREFIX)
        size = item["bytes"]
        digest = item["sha256"]
        if (
            relative in entries
            or relative not in theme_builder.SOURCE_FILES
            or not 1 <= size <= 4 * 1024 * 1024
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        entries[relative] = (size, digest)
    if tuple(entries) != theme_builder.SOURCE_FILES:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    return entries


def _verify_st1704_runtime_manifest() -> bytes:
    path = runtime_manifest_builder.OUTPUT_PATH
    try:
        metadata = path.lstat()
        current = runtime_manifest_builder.OUTPUT_PATH.read_bytes()
        expected = runtime_manifest_builder.build_manifest()
    except BaseException:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    if (
        path != REPOSITORY_ROOT / _ST1704_RUNTIME_MANIFEST_RELATIVE
        or path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or not 1 <= metadata.st_size <= _MAX_RUNTIME_MANIFEST_BYTES
        or len(current) != metadata.st_size
        or current != expected
        or current != _bound_st1704_runtime_manifest()
    ):
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
    return current


def _theme_package() -> ThemePackage:
    """Build and re-check the exact deterministic ST-1704 package in memory."""

    try:
        bound_manifest = _verify_st1704_runtime_manifest()
        bound_entries = _bound_theme_entries(bound_manifest)
        declared_hashes = theme_builder.validate_sources()
        if declared_hashes != {
            relative: digest for relative, (_size, digest) in bound_entries.items()
        }:
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        first = theme_builder.build_package()
        second = theme_builder.build_package()
        if (
            first != second
            or hashlib.sha256(first).digest() != hashlib.sha256(second).digest()
        ):
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        manifest: list[ThemeFileManifestEntry] = []
        with zipfile.ZipFile(io.BytesIO(first), "r") as archive:
            expected_names = [
                f"{theme_builder.THEME_SLUG}/{relative}"
                for relative in theme_builder.SOURCE_FILES
            ]
            if archive.namelist() != expected_names:
                _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
            for relative, archive_name in zip(
                theme_builder.SOURCE_FILES, expected_names, strict=True
            ):
                info = archive.getinfo(archive_name)
                payload = archive.read(archive_name)
                digest = hashlib.sha256(payload).hexdigest()
                expected_size, expected_digest = bound_entries[relative]
                try:
                    archive_name.encode("ascii", errors="strict")
                except UnicodeError:
                    _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
                if (
                    info.is_dir()
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.file_size != len(payload)
                    or info.compress_size != len(payload)
                    or len(payload) != expected_size
                    or digest != expected_digest
                ):
                    _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
                manifest.append(
                    ThemeFileManifestEntry(
                        path=relative,
                        size=len(payload),
                        sha256=digest,
                    )
                )
        if _verify_st1704_runtime_manifest() != bound_manifest:
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        return ThemePackage.bind(
            from_version=WORDPRESS_OPERATOR_THEME_FROM_VERSION,
            to_version=theme_builder.THEME_VERSION,
            package_bytes=first,
            file_manifest=tuple(manifest),
        )
    except WordPressOperatorFailure:
        raise
    except BaseException:
        _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)


def _request_token() -> str:
    request_token = secrets.token_hex(32)
    return require_sha256(request_token)


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedArgumentParser(
        prog="st1506-wordpress-operator",
        description=(
            "Fixed kurashinoshirube.com operator. Proposal approval occurs only "
            "in WordPress admin and is not a CLI command."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Read the fixed operator status.")
    commands.add_parser(
        "verify-yoast-checksums",
        help="Verify the installed Yoast 28.3 files against the fixed manifest.",
    )
    commands.add_parser(
        "propose-yoast-profile",
        help="Create a proposal for the exact fixed Yoast profile.",
    )
    commands.add_parser(
        "propose-theme-update",
        help="Create a proposal for the deterministic reviewed theme package.",
    )
    for name, help_text in (
        (
            "apply-yoast-profile",
            "Apply an already human-approved exact Yoast profile proposal.",
        ),
        (
            "apply-theme-update",
            "Apply an already human-approved deterministic theme proposal.",
        ),
    ):
        command = commands.add_parser(name, help=help_text, allow_abbrev=False)
        command.add_argument(
            "--proposal-id",
            required=True,
            metavar="PROPOSAL_ID",
            help="Exact approved lowercase 64-hex proposal identifier.",
        )
    return parser


def _write_result(command: str, result: dict[str, object]) -> None:
    print(
        json.dumps(
            {"command": command, "result": result, "schema": _RESULT_SCHEMA},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _write_failure(code: WordPressOperatorFailureCode) -> None:
    print(
        json.dumps(
            {"code": code.value, "schema": _ERROR_SCHEMA},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def _proposal_result(
    proposal: OperatorProposal, receipt: object
) -> tuple[dict[str, object], bool]:
    if type(receipt) is not ProposalReceipt:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    value = receipt.public_payload()
    if (
        receipt.proposal_id != proposal.proposal_id
        or receipt.operation is not proposal.operation
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    expired = receipt.is_expired()
    value["human_approval_required"] = (
        receipt.state is WordPressOperatorProposalState.PROPOSED and not expired
    )
    if expired:
        value["approval_surface"] = "NOT_APPLICABLE"
        value["next_action"] = "NEW_PROPOSAL_REQUIRED"
    elif receipt.state is WordPressOperatorProposalState.PROPOSED:
        value["approval_surface"] = "WORDPRESS_ADMIN_TOOLS_ONLY"
        value["next_action"] = "HUMAN_APPROVAL_REQUIRED_BEFORE_MATCHING_APPLY_COMMAND"
    elif receipt.state is WordPressOperatorProposalState.APPROVED:
        value["approval_surface"] = "NOT_APPLICABLE"
        value["next_action"] = "RUN_MATCHING_APPLY_COMMAND"
    else:
        value["approval_surface"] = "NOT_APPLICABLE"
        value["next_action"] = "VERIFY_STATUS_BEFORE_ANY_RETRY"
    return value, expired


def _proposal_from_intent(
    *,
    adapter: OfficialSelfHostedWordPressOperatorAdapter,
    operation: WordPressOperatorOperation,
    theme: ThemePackage | None = None,
) -> tuple[dict[str, object], bool]:
    if (
        type(operation) is not WordPressOperatorOperation
        or (operation is WordPressOperatorOperation.APPLY_YOAST_PROFILE)
        != (theme is None)
        or (
            operation is WordPressOperatorOperation.UPDATE_CHILD_THEME
            and type(theme) is not ThemePackage
        )
    ):
        _fail(WordPressOperatorFailureCode.OPERATION_NOT_ALLOWED)
    journal = OwnerPrivateWordPressOperatorProposalIntentJournal(REPOSITORY_ROOT)
    with journal.exclusive(operation):
        intent = journal.load(operation)
        request_token = _request_token() if intent is None else intent.request_token
        if operation is WordPressOperatorOperation.APPLY_YOAST_PROFILE:
            proposal = OperatorProposal.yoast(request_token)
        elif theme is not None:
            proposal = OperatorProposal.theme_update(theme, request_token)
        else:
            _fail(WordPressOperatorFailureCode.OPERATION_NOT_ALLOWED)
        if intent is None:
            journal.record(proposal)
        elif intent.proposal_id != proposal.proposal_id:
            _fail(WordPressOperatorFailureCode.CREDENTIAL_STORE_INVALID)
        receipt = adapter.propose(proposal)
        if intent is None and receipt.replayed:
            _fail(WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS)
        result = _proposal_result(proposal, receipt)
        journal.clear(proposal)
        return result


def _clear_matching_intent_after_apply(
    operation: WordPressOperatorOperation, proposal_id: str
) -> None:
    journal = OwnerPrivateWordPressOperatorProposalIntentJournal(REPOSITORY_ROOT)
    with journal.exclusive(operation):
        journal.clear_matching_proposal_id(operation, proposal_id)


def _run(arguments: argparse.Namespace) -> int:
    command = arguments.command
    if type(command) is not str:
        _fail(WordPressOperatorFailureCode.INVALID_ARGUMENT)
    adapter = OfficialSelfHostedWordPressOperatorAdapter(REPOSITORY_ROOT)
    if command == "status":
        _write_result(command, adapter.status().public_payload())
        return 0
    if command == "verify-yoast-checksums":
        checksum = adapter.verify_yoast_checksums()
        _write_result(command, checksum.public_payload())
        return 0 if checksum.status is WordPressOperatorChecksumStatus.PASS else 2
    if command == "propose-yoast-profile":
        result, expired = _proposal_from_intent(
            adapter=adapter,
            operation=WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        )
        _write_result(command, result)
        return 2 if expired else 0
    if command == "propose-theme-update":
        result, expired = _proposal_from_intent(
            adapter=adapter,
            operation=WordPressOperatorOperation.UPDATE_CHILD_THEME,
            theme=_theme_package(),
        )
        _write_result(command, result)
        return 2 if expired else 0
    proposal_id = require_sha256(getattr(arguments, "proposal_id", None))
    if command == "apply-yoast-profile":
        applied = adapter.apply_yoast_profile(proposal_id)
        operation = WordPressOperatorOperation.APPLY_YOAST_PROFILE
    elif command == "apply-theme-update":
        applied = adapter.apply_theme_update(proposal_id, _theme_package())
        operation = WordPressOperatorOperation.UPDATE_CHILD_THEME
    else:
        _fail(WordPressOperatorFailureCode.OPERATION_NOT_ALLOWED)
    _clear_matching_intent_after_apply(operation, proposal_id)
    _write_result(command, applied.public_payload())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if not _STAGE_ZERO_VERIFIED:
        _stage_refuse()
    try:
        arguments = _parser().parse_args(argv)
        return _run(arguments)
    except WordPressOperatorFailure as failure:
        _write_failure(failure.code)
        return 2
    except _SANITIZED_EXCEPTIONS:
        _write_failure(WordPressOperatorFailureCode.INTERNAL_FAILURE)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
