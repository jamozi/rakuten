#!/usr/bin/env python3
"""Closed five-command CLI for the ST-1704 self-hosted editorial pilot."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types
from typing import Any, Final, NoReturn, Protocol, TextIO, cast
from urllib.parse import urlencode


CLI_PATH: Final = Path(os.path.abspath(__file__))
REPOSITORY_ROOT: Final = CLI_PATH.parent.parent
OWNER_PYTHON: Final = (REPOSITORY_ROOT / ".venv/bin/python").as_posix()
SITE_PACKAGES: Final = (
    REPOSITORY_ROOT / ".venv/lib/python3.14/site-packages"
).as_posix()
_BASE_PREFIX: Final = Path(sys.base_prefix)
_STDLIB_PATHS: Final = (
    (_BASE_PREFIX / "lib/python314.zip").as_posix(),
    (_BASE_PREFIX / "lib/python3.14").as_posix(),
    (_BASE_PREFIX / "lib/python3.14/lib-dynload").as_posix(),
)
_BASELINE_META_PATH: Final = (
    importlib.machinery.BuiltinImporter,
    importlib.machinery.FrozenImporter,
    importlib.machinery.PathFinder,
)
MANIFEST_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
)
SOURCE_BOOTSTRAP_RELATIVE: Final = "scripts/st1704_official_source_capture.py"
BOOTSTRAP_RELATIVE: Final = "scripts/st1704_self_hosted_editorial_pilot.py"
MAX_MANIFEST_BYTES: Final = 256 * 1024
MAX_RUNTIME_BYTES: Final = 4 * 1024 * 1024
MAX_COMMAND_LINE_BYTES: Final = 64 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_GIT_OBJECT_ID: Final = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT_ENVIRONMENT: Final = {
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
_PROCESS_ENVIRONMENT: Final = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_PACKAGE_NAMES: Final = (
    "raos",
    "raos.adapters",
    "raos.application",
    "raos.application.editorial",
    "raos.domain",
    "raos.domain.editorial",
    "raos.generated",
    "raos.ports",
)
_MODULE_PATHS: Final = (
    (
        "raos.domain.editorial.self_hosted_editorial_pilot",
        "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.domain.editorial.self_hosted_wordpress",
        "python/raos/domain/editorial/self_hosted_wordpress.py",
    ),
    (
        "raos.domain.editorial.market_learning_pilot",
        "python/raos/domain/editorial/market_learning_pilot.py",
    ),
    (
        "raos.ports.self_hosted_editorial_pilot",
        "python/raos/ports/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.adapters.self_hosted_wordpress_credentials",
        "python/raos/adapters/self_hosted_wordpress_credentials.py",
    ),
    (
        "raos.adapters.wordpress_rest",
        "python/raos/adapters/wordpress_rest.py",
    ),
    (
        "raos.adapters.self_hosted_wordpress_rest",
        "python/raos/adapters/self_hosted_wordpress_rest.py",
    ),
    (
        "raos.adapters.self_hosted_wordpress_https",
        "python/raos/adapters/self_hosted_wordpress_https.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_pilot_json",
        "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    ),
    (
        "raos.domain.editorial.content_ast",
        "python/raos/domain/editorial/content_ast.py",
    ),
    (
        "raos.application.editorial.self_hosted_editorial_pilot",
        "python/raos/application/editorial/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_pilot_https",
        "python/raos/adapters/self_hosted_editorial_pilot_https.py",
    ),
)
_GENERATED_PREFIX: Final = "python/raos/generated/contracts/"
_TRACKED_APPLICATION_PATHS: Final = frozenset(
    {
        "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/media/product-media-registry.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
    }
)
_THEME_CONTRACT_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/theme-contract.v1.json"
)
_CONTENT_AST_PINNED_PATHS: Final = frozenset(
    {
        "contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json",
        "python/raos/generated/contracts/__init__.py",
        "python/raos/generated/contracts/_internal.py",
        "python/raos/generated/contracts/content_ast.py",
    }
)
_EXTERNAL_DEPENDENCIES: Final = (
    "pydantic",
    "jsonschema",
    "jsonschema.exceptions",
)
_MUTABLE_MODULE_GLOBALS: Final = {
    "raos.domain.editorial.content_ast": frozenset(
        {"_generated_models_ready", "_validator"}
    )
}
_COMMON_MUTABLE_MODULE_GLOBALS: Final = frozenset({"__warningregistry__"})
RootIdentity = tuple[int, int]
ModuleSeal = dict[str, dict[str, object]]

COMMANDS: Final = (
    "prepare",
    "create-review-draft",
    "recover-create-review-draft",
    "verify-carry-on-single-url",
    "verify-public",
)
ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)


class _RuntimeFailure(RuntimeError):
    """Sanitized refusal for an unbound operational runtime."""


class _CliRefusal(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _RuntimeVerifier(Protocol):
    def __call__(self, root: object) -> tuple[dict[str, bytes], RootIdentity]: ...


class _VerifiedSourceLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Import only RAOS module bytes frozen by the committed manifest."""

    def __init__(self, sources: Mapping[str, bytes]) -> None:
        self._sources: dict[str, tuple[bytes, str, bool]] = {}
        self._loaded: dict[str, types.ModuleType] = {}
        for module_name, relative in _MODULE_PATHS:
            raw = sources.get(relative)
            if type(raw) is not bytes or module_name in self._sources:
                _fail_runtime()
            self._sources[module_name] = (raw, relative, False)
        for relative, raw in sources.items():
            if not relative.startswith(_GENERATED_PREFIX) or not relative.endswith(
                ".py"
            ):
                continue
            if type(raw) is not bytes:
                _fail_runtime()
            portable = relative.removeprefix("python/").removesuffix(".py")
            is_package = portable.endswith("/__init__")
            if is_package:
                portable = portable.removesuffix("/__init__")
            module_name = portable.replace("/", ".")
            if not module_name or module_name in self._sources:
                _fail_runtime()
            self._sources[module_name] = (raw, relative, is_package)
        if not all(
            name in self._sources
            for name in (
                "raos.generated.contracts",
                "raos.generated.contracts._internal",
                "raos.generated.contracts.content_ast",
            )
        ):
            _fail_runtime()

    @property
    def module_names(self) -> frozenset[str]:
        return frozenset(self._sources)

    @property
    def loaded_modules(self) -> dict[str, types.ModuleType]:
        return dict(self._loaded)

    def owns(self, name: str, module: types.ModuleType) -> bool:
        return self._loaded.get(name) is module

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        entry = self._sources.get(fullname)
        if entry is None:
            return None
        return importlib.util.spec_from_loader(fullname, self, is_package=entry[2])

    def create_module(
        self, spec: importlib.machinery.ModuleSpec
    ) -> types.ModuleType | None:
        del spec
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        entry = self._sources.get(module.__name__)
        if entry is None or module.__name__ in self._loaded:
            _fail_runtime()
        self._loaded[module.__name__] = module
        raw, relative, _is_package = entry
        filename = (REPOSITORY_ROOT / relative).as_posix()
        module.__file__ = filename
        try:
            code = compile(raw, filename, "exec", dont_inherit=True)
            exec(code, module.__dict__)
            if sys.modules.get(module.__name__) is not module:
                _fail_runtime()
        except _RuntimeFailure:
            raise
        except BaseException:
            _fail_runtime()


def _fail_runtime() -> NoReturn:
    raise _RuntimeFailure("SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID") from None


def _safe_directory(fd: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o022
    ):
        _fail_runtime()
    return observed


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail_runtime()
    current = -1
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        for part in path.parts[1:]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        _safe_directory(current)
        return current
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _relative_parts(relative: str) -> tuple[str, ...]:
    if type(relative) is not str or not relative or relative != relative.strip():
        _fail_runtime()
    portable = Path(relative)
    if (
        portable.is_absolute()
        or portable.as_posix() != relative
        or any(part in {"", ".", ".."} for part in portable.parts)
    ):
        _fail_runtime()
    return portable.parts


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative_parts(relative)
    current = -1
    try:
        current = os.dup(root_fd)
        for part in parts[:-1]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            _safe_directory(following)
            os.close(current)
            current = following
        return current, parts[-1]
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _read_relative(root_fd: int, relative: str, *, maximum: int) -> bytes:
    if type(maximum) is not int or not 1 <= maximum <= MAX_RUNTIME_BYTES:
        _fail_runtime()
    parent_fd, name = _open_parent(root_fd, relative)
    descriptor = -1
    try:
        try:
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail_runtime()
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or not 0 < before.st_size <= maximum
        ):
            _fail_runtime()
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail_runtime()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail_runtime()
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail_runtime()
        rebound = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        try:
            rebound_metadata = os.fstat(rebound)
            if (before.st_dev, before.st_ino) != (
                rebound_metadata.st_dev,
                rebound_metadata.st_ino,
            ):
                _fail_runtime()
        finally:
            os.close(rebound)
        return b"".join(chunks)
    except _RuntimeFailure:
        raise
    except OSError:
        _fail_runtime()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _rebind_root(root: Path, identity: RootIdentity) -> None:
    descriptor = _open_absolute_directory(root)
    try:
        observed = _safe_directory(descriptor)
        if (observed.st_dev, observed.st_ino) != identity:
            _fail_runtime()
    finally:
        os.close(descriptor)


def _kernel_command_line() -> bytes:
    descriptor = -1
    try:
        descriptor = os.open("/proc/self/cmdline", _FILE_FLAGS)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or observed.st_nlink != 1
            or stat.S_IMODE(observed.st_mode) & 0o022
        ):
            _fail_runtime()
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_COMMAND_LINE_BYTES:
                _fail_runtime()
            chunks.append(chunk)
        return b"".join(chunks)
    except _RuntimeFailure:
        raise
    except OSError:
        _fail_runtime()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _verify_stage_zero() -> None:
    flags = sys.flags
    try:
        current_directory = os.getcwd()
    except OSError:
        _fail_runtime()
    expected_orig_argv = [
        OWNER_PYTHON,
        "-B",
        "-I",
        "-S",
        "-X",
        "pycache_prefix=/dev/null",
        BOOTSTRAP_RELATIVE,
        *sys.argv[1:],
    ]
    expected_kernel_command_line = (
        b"\0".join(os.fsencode(value) for value in expected_orig_argv) + b"\0"
    )
    if (
        CLI_PATH != REPOSITORY_ROOT / BOOTSTRAP_RELATIVE
        or sys.executable != OWNER_PYTHON
        or sys.version_info[:3] != (3, 14, 6)
        or flags.dont_write_bytecode != 1
        or flags.ignore_environment != 1
        or flags.isolated != 1
        or flags.no_site != 1
        or flags.no_user_site != 1
        or not flags.safe_path
        or sys.pycache_prefix != "/dev/null"
        or current_directory != REPOSITORY_ROOT.as_posix()
        or dict(os.environ) != _PROCESS_ENVIRONMENT
        or sys.argv[0] != BOOTSTRAP_RELATIVE
        or sys.orig_argv != expected_orig_argv
        or _kernel_command_line() != expected_kernel_command_line
        or tuple(sys.path) != _STDLIB_PATHS
        or tuple(sys.meta_path) != _BASELINE_META_PATH
        or any(
            name in sys.modules for name in ("site", "sitecustomize", "usercustomize")
        )
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(REPOSITORY_ROOT)
    try:
        root = _safe_directory(root_fd)
        cwd_fd = os.open(".", _DIRECTORY_FLAGS)
        try:
            cwd = _safe_directory(cwd_fd)
            if (root.st_dev, root.st_ino) != (cwd.st_dev, cwd.st_ino):
                _fail_runtime()
        finally:
            os.close(cwd_fd)
    finally:
        os.close(root_fd)


def _git(root: Path, *arguments: str, maximum_stdout: int) -> bytes:
    if type(maximum_stdout) is not int or not 1 <= maximum_stdout <= MAX_RUNTIME_BYTES:
        _fail_runtime()
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "--no-optional-locks", "-C", root.as_posix(), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_GIT_ENVIRONMENT,
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        _fail_runtime()
    if completed.returncode != 0 or len(completed.stdout) > maximum_stdout:
        _fail_runtime()
    return completed.stdout


def _committed_blob(root: Path, *, head: str, relative: str, maximum: int) -> bytes:
    if _GIT_OBJECT_ID.fullmatch(head) is None:
        _fail_runtime()
    _relative_parts(relative)
    object_spec = f"{head}:{relative}"
    raw_size = _git(root, "cat-file", "-s", object_spec, maximum_stdout=128)
    try:
        size_text = raw_size.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _fail_runtime()
    if str(size) != size_text or not 0 < size <= maximum:
        _fail_runtime()
    raw = _git(root, "cat-file", "blob", object_spec, maximum_stdout=size)
    if len(raw) != size:
        _fail_runtime()
    return raw


def _bootstrap_sources() -> tuple[bytes, bytes, bytes, RootIdentity, str]:
    root_fd = _open_absolute_directory(REPOSITORY_ROOT)
    try:
        root_metadata = _safe_directory(root_fd)
        manifest = _read_relative(
            root_fd, MANIFEST_RELATIVE, maximum=MAX_MANIFEST_BYTES
        )
        bootstrap = _read_relative(
            root_fd, SOURCE_BOOTSTRAP_RELATIVE, maximum=MAX_RUNTIME_BYTES
        )
        current_cli = _read_relative(
            root_fd, BOOTSTRAP_RELATIVE, maximum=MAX_RUNTIME_BYTES
        )
    finally:
        os.close(root_fd)
    expected_root = os.fsencode(REPOSITORY_ROOT.as_posix()) + b"\n"
    if (
        _git(
            REPOSITORY_ROOT,
            "rev-parse",
            "--show-toplevel",
            maximum_stdout=max(128, len(expected_root)),
        )
        != expected_root
    ):
        _fail_runtime()
    raw_head = _git(
        REPOSITORY_ROOT,
        "rev-parse",
        "--verify",
        "HEAD^{commit}",
        maximum_stdout=128,
    )
    try:
        head = raw_head.decode("ascii", errors="strict").strip()
    except UnicodeError:
        _fail_runtime()
    if _GIT_OBJECT_ID.fullmatch(head) is None:
        _fail_runtime()
    for relative, raw, maximum in (
        (MANIFEST_RELATIVE, manifest, MAX_MANIFEST_BYTES),
        (SOURCE_BOOTSTRAP_RELATIVE, bootstrap, MAX_RUNTIME_BYTES),
        (BOOTSTRAP_RELATIVE, current_cli, MAX_RUNTIME_BYTES),
    ):
        if raw != _committed_blob(
            REPOSITORY_ROOT, head=head, relative=relative, maximum=maximum
        ):
            _fail_runtime()
    observed_head = _git(
        REPOSITORY_ROOT,
        "rev-parse",
        "--verify",
        "HEAD^{commit}",
        maximum_stdout=128,
    )
    if observed_head != raw_head:
        _fail_runtime()
    identity = (root_metadata.st_dev, root_metadata.st_ino)
    _rebind_root(REPOSITORY_ROOT, identity)
    return manifest, bootstrap, current_cli, identity, head


def _load_verified_runtime() -> tuple[dict[str, bytes], RootIdentity]:
    initial_manifest, bootstrap, current_cli, initial_identity, initial_head = (
        _bootstrap_sources()
    )
    module = types.ModuleType("_raos_st1704_verified_source_bootstrap")
    module.__file__ = (REPOSITORY_ROOT / SOURCE_BOOTSTRAP_RELATIVE).as_posix()
    module.__package__ = ""
    try:
        exec(
            compile(bootstrap, module.__file__, "exec", dont_inherit=True),
            module.__dict__,
        )
        verifier = getattr(module, "_verify_runtime_integrity", None)
        if not callable(verifier):
            _fail_runtime()

        def committed_manifest(root: object) -> tuple[bytes, str]:
            if not isinstance(root, Path) or root != REPOSITORY_ROOT:
                _fail_runtime()
            _rebind_root(REPOSITORY_ROOT, initial_identity)
            return initial_manifest, initial_head

        setattr(module, "_committed_manifest", committed_manifest)
        sources, identity = cast(_RuntimeVerifier, verifier)(REPOSITORY_ROOT)
    except _RuntimeFailure:
        raise
    except BaseException:
        _fail_runtime()
    if (
        type(sources) is not dict
        or type(identity) is not tuple
        or len(identity) != 2
        or identity != initial_identity
        or sources.get(BOOTSTRAP_RELATIVE) != current_cli
        or sources.get(SOURCE_BOOTSTRAP_RELATIVE) != bootstrap
    ):
        _fail_runtime()
    final_head = _git(
        REPOSITORY_ROOT,
        "rev-parse",
        "--verify",
        "HEAD^{commit}",
        maximum_stdout=128,
    )
    if final_head != (initial_head + "\n").encode("ascii"):
        _fail_runtime()
    _rebind_root(REPOSITORY_ROOT, identity)
    return sources, identity


def _enable_site_packages(identity: RootIdentity) -> None:
    if SITE_PACKAGES in sys.path or any(
        name in sys.modules for name in ("site", "sitecustomize", "usercustomize")
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(REPOSITORY_ROOT)
    current = -1
    try:
        root = _safe_directory(root_fd)
        if (root.st_dev, root.st_ino) != identity:
            _fail_runtime()
        current = os.dup(root_fd)
        for part in (".venv", "lib", "python3.14", "site-packages"):
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            _safe_directory(following)
            os.close(current)
            current = following
    except _RuntimeFailure:
        raise
    except OSError:
        _fail_runtime()
    finally:
        if current >= 0:
            os.close(current)
        os.close(root_fd)
    sys.path.append(SITE_PACKAGES)


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__package__ = name
    setattr(module, "__path__", [])
    sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
    return module


def _preload_external_dependencies() -> None:
    if tuple(sys.meta_path) != _BASELINE_META_PATH or any(
        name == "raos" or name.startswith("raos.") for name in sys.modules
    ):
        _fail_runtime()
    for name in _EXTERNAL_DEPENDENCIES:
        try:
            module = cast(object, importlib.import_module(name))
        except BaseException:
            _fail_runtime()
        if (
            not isinstance(module, types.ModuleType)
            or sys.modules.get(name) is not module
        ):
            _fail_runtime()
    if tuple(sys.meta_path) != _BASELINE_META_PATH or any(
        name == "raos" or name.startswith("raos.") for name in sys.modules
    ):
        _fail_runtime()


def _validate_verified_modules(modules: Mapping[str, types.ModuleType]) -> None:
    observed = {
        name: module
        for name, module in sys.modules.items()
        if name == "raos" or name.startswith("raos.")
    }
    if set(observed) != set(modules):
        _fail_runtime()
    for name, candidate in cast(Mapping[str, object], modules).items():
        if not isinstance(candidate, types.ModuleType):
            _fail_runtime()
        module = candidate
        if observed.get(name) is not module:
            _fail_runtime()
        if name in _PACKAGE_NAMES:
            if getattr(module, "__loader__", None) is not None:
                _fail_runtime()
            continue
        loader = getattr(module, "__loader__", None)
        spec = getattr(module, "__spec__", None)
        if (
            not isinstance(loader, _VerifiedSourceLoader)
            or not loader.owns(name, module)
            or not isinstance(spec, importlib.machinery.ModuleSpec)
            or spec.loader is not loader
        ):
            _fail_runtime()


def _seal_verified_modules(modules: Mapping[str, types.ModuleType]) -> ModuleSeal:
    _validate_verified_modules(modules)
    seal: ModuleSeal = {}
    for name, module in modules.items():
        mutable = _COMMON_MUTABLE_MODULE_GLOBALS | _MUTABLE_MODULE_GLOBALS.get(
            name, frozenset()
        )
        seal[name] = {
            key: value for key, value in vars(module).items() if key not in mutable
        }
    return seal


def _validate_module_seal(
    modules: Mapping[str, types.ModuleType], seal: Mapping[str, Mapping[str, object]]
) -> None:
    _validate_verified_modules(modules)
    if set(seal) != set(modules):
        _fail_runtime()
    for name, module in modules.items():
        mutable = _COMMON_MUTABLE_MODULE_GLOBALS | _MUTABLE_MODULE_GLOBALS.get(
            name, frozenset()
        )
        expected = seal.get(name)
        if not isinstance(expected, Mapping):
            _fail_runtime()
        observed = vars(module)
        if set(observed) - mutable != set(expected):
            _fail_runtime()
        if any(observed.get(key) is not value for key, value in expected.items()):
            _fail_runtime()


def _load_verified_modules(
    sources: Mapping[str, bytes], identity: RootIdentity
) -> dict[str, types.ModuleType]:
    if any(name == "raos" or name.startswith("raos.") for name in sys.modules):
        _fail_runtime()
    _rebind_root(REPOSITORY_ROOT, identity)
    _preload_external_dependencies()
    loader = _VerifiedSourceLoader(sources)
    loaded: dict[str, types.ModuleType] = {}
    try:
        for name in _PACKAGE_NAMES:
            loaded[name] = _package(name)
        sys.meta_path.insert(0, loader)
        for module_name, _relative in _MODULE_PATHS:
            module = cast(object, importlib.import_module(module_name))
            if not isinstance(module, types.ModuleType):
                _fail_runtime()
    except _RuntimeFailure:
        raise
    except BaseException:
        _fail_runtime()
    finally:
        while loader in sys.meta_path:
            sys.meta_path.remove(loader)
    loaded.update(loader.loaded_modules)
    _validate_verified_modules(loaded)
    if tuple(sys.meta_path) != _BASELINE_META_PATH or any(
        name in sys.modules for name in ("site", "sitecustomize", "usercustomize")
    ):
        _fail_runtime()
    for module_name, _relative in _MODULE_PATHS:
        observed_module = loaded.get(module_name)
        if not isinstance(observed_module, types.ModuleType):
            _fail_runtime()
    _rebind_root(REPOSITORY_ROOT, identity)
    return loaded


def _bind_verified_tracked_reads(
    modules: Mapping[str, types.ModuleType],
    sources: Mapping[str, bytes],
    identity: RootIdentity,
) -> None:
    application = modules.get("raos.application.editorial.self_hosted_editorial_pilot")
    content_ast = modules.get("raos.domain.editorial.content_ast")
    https_adapter = modules.get("raos.adapters.self_hosted_editorial_pilot_https")
    domain = modules.get("raos.domain.editorial.self_hosted_editorial_pilot")
    if not all(
        isinstance(value, types.ModuleType)
        for value in (application, content_ast, https_adapter, domain)
    ):
        _fail_runtime()
    application = cast(types.ModuleType, application)
    content_ast = cast(types.ModuleType, content_ast)
    https_adapter = cast(types.ModuleType, https_adapter)
    domain = cast(types.ModuleType, domain)
    application_pairs = getattr(application, "_pairs", None)
    application_reject_number = getattr(application, "_reject_number", None)
    application_fail = getattr(application, "_fail", None)
    decode_response = getattr(https_adapter, "_decode_response", None)
    https_mapping = getattr(https_adapter, "_mapping", None)
    https_fail = getattr(https_adapter, "_fail", None)
    failure_code = getattr(domain, "EditorialPilotFailureCode", None)
    content_contract_fail = getattr(content_ast, "_raise_contract_error", None)
    if not all(
        callable(value)
        for value in (
            application_pairs,
            application_reject_number,
            application_fail,
            decode_response,
            https_mapping,
            https_fail,
            content_contract_fail,
        )
    ) or not isinstance(failure_code, type):
        _fail_runtime()
    application_raw = {
        relative: sources[relative] for relative in _TRACKED_APPLICATION_PATHS
    }
    theme_raw = sources.get(_THEME_CONTRACT_RELATIVE)
    pinned_raw = {relative: sources[relative] for relative in _CONTENT_AST_PINNED_PATHS}
    if type(theme_raw) is not bytes:
        _fail_runtime()

    def read_fixed_json(repository_root: object, relative: object) -> object:
        if (
            not isinstance(repository_root, Path)
            or repository_root != REPOSITORY_ROOT
            or not isinstance(relative, Path)
            or relative.is_absolute()
        ):
            _fail_runtime()
        raw = application_raw.get(relative.as_posix())
        if raw is None:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, identity)
        try:
            return json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=cast(Any, application_pairs),
                parse_float=cast(Any, application_reject_number),
                parse_constant=cast(Any, application_reject_number),
            )
        except BaseException as error:
            editorial_failure = getattr(domain, "EditorialPilotFailure", None)
            if isinstance(editorial_failure, type) and isinstance(
                error, editorial_failure
            ):
                raise
            cast(Any, application_fail)()
            _fail_runtime()

    def read_theme_contract(repository_root: object) -> Mapping[str, object]:
        if not isinstance(repository_root, Path) or repository_root != REPOSITORY_ROOT:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, identity)
        contract = cast(Any, https_mapping)(cast(Any, decode_response)(theme_raw))
        if contract.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_CONTRACT_V1":
            packet_invalid = getattr(failure_code, "PACKET_INVALID", None)
            cast(Any, https_fail)(packet_invalid)
        return cast(Mapping[str, object], contract)

    def read_pinned_file(
        relative: object, expected_sha256: object, expected_size: object
    ) -> bytes:
        if (
            not isinstance(relative, Path)
            or type(expected_sha256) is not str
            or _SHA256.fullmatch(expected_sha256) is None
            or type(expected_size) is not int
            or expected_size <= 0
        ):
            cast(Any, content_contract_fail)()
            _fail_runtime()
        raw = pinned_raw.get(relative.as_posix())
        if (
            raw is None
            or len(raw) != expected_size
            or hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            cast(Any, content_contract_fail)()
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, identity)
        return raw

    setattr(application, "_read_fixed_json", read_fixed_json)
    setattr(https_adapter, "_read_theme_contract", read_theme_contract)
    setattr(content_ast, "_read_pinned_file", read_pinned_file)


def _write_json(value: object, *, target: TextIO = sys.stdout) -> None:
    target.write(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _prepared_result(value: Any) -> dict[str, object]:
    return {
        "article_id": value.article_id,
        "command": "prepare",
        "content_sha256": value.content_sha256,
        "external_writes": value.external_writes,
        "network_requests": value.network_requests,
        "packet_sha256": value.packet_sha256,
        "payload_sha256": value.request.snapshot.payload_sha256,
        "product_count": value.product_count,
        "production_evidence": value.production_evidence,
        "publication_actions": value.publication_actions,
        "publication_authority": value.publication_authority,
        "request_sha256": value.request.request_sha256,
        "public_slug": value.request.public_slug,
        "review_slug": value.request.slug,
        "source_count": value.source_count,
        "status": "PREPARED_FOR_OWNER_REVIEW_DRAFT",
    }


def _receipt_result(command: str, value: Any, request: Any) -> dict[str, object]:
    owner_apply_path: str | None = None
    if value.article_id == "st1703-first-suitcase-comparison":
        if type(value.target_public_post_id) is not int:
            raise _CliRefusal("JOURNAL_MISMATCH")
        owner_apply_path = "/wp-admin/tools.php?" + urlencode(
            (
                ("page", "kurashinoshirube-at003-update-v1"),
                ("payload_sha256", request.snapshot.payload_sha256),
                ("packet_sha256", value.packet_sha256),
                ("request_sha256", value.request_sha256),
                ("review_draft_id", str(value.draft_id)),
                ("target_public_post_id", str(value.target_public_post_id)),
            )
        )
    return {
        "article_id": value.article_id,
        "command": command,
        "disposition": value.disposition.value,
        "draft_id": value.draft_id,
        "live_authority": value.live_authority,
        "packet_sha256": value.packet_sha256,
        "payload_sha256": request.snapshot.payload_sha256,
        "production_evidence": False,
        "publication_authority": value.publication_authority,
        "request_sha256": value.request_sha256,
        "response_sha256": value.response_sha256,
        "status": value.status,
        "target_public_post_id": value.target_public_post_id,
        "owner_apply_path": owner_apply_path,
    }


def _verification_result(value: Any) -> dict[str, object]:
    return {
        "article_id": value.article_id,
        "article_html_sha256": value.article_html_sha256,
        "category_sha256": value.category_sha256,
        "command": "verify-public",
        "core_sitemap_sha256": value.core_sitemap_sha256,
        "expected_public_post_id": value.expected_public_post_id,
        "homepage_html_sha256": value.homepage_html_sha256,
        "homepage_targets_sha256": value.homepage_targets_sha256,
        "live_read": value.live_read,
        "packet_sha256": value.packet_sha256,
        "page_sitemap_sha256": value.page_sitemap_sha256,
        "post_id": value.post_id,
        "post_sitemap_sha256": value.post_sitemap_sha256,
        "production_evidence": value.production_evidence,
        "public_surface_sha256": value.public_surface_sha256,
        "public_surface_verified": value.public_surface_verified,
        "related_target_sha256": value.related_target_sha256,
        "review_draft_post_id": value.review_draft_post_id,
        "review_draft_rest_evidence_sha256": (value.review_draft_rest_evidence_sha256),
        "review_public_rest_evidence_sha256": (
            value.review_public_rest_evidence_sha256
        ),
        "review_url_html_evidence_sha256": value.review_url_html_evidence_sha256,
        "publication_authority": False,
        "request_sha256": value.request_sha256,
        "response_sha256": value.response_sha256,
        "robots_sha256": value.robots_sha256,
        "sitemap_index_sha256": value.sitemap_index_sha256,
        "status": value.status,
        "target_public_post_id": value.target_public_post_id,
        "verified_checks": list(value.verified_checks),
    }


def _carry_on_reconciliation_result(value: Any) -> dict[str, object]:
    return {
        "article_html_sha256": value.article_html_sha256,
        "article_id": value.article_id,
        "authority": value.authority,
        "category_sha256": value.category_sha256,
        "command": value.command,
        "core_sitemap_sha256": value.core_sitemap_sha256,
        "expected_public_post_id": value.expected_public_post_id,
        "expected_review_draft_post_id": value.expected_review_draft_post_id,
        "formal_gate_eligible": value.formal_gate_eligible,
        "homepage_html_sha256": value.homepage_html_sha256,
        "homepage_targets_sha256": value.homepage_targets_sha256,
        "journal_mutated": value.journal_mutated,
        "journal_state": value.journal_state,
        "live_read": value.live_read,
        "packet_sha256": value.packet_sha256,
        "page_sitemap_sha256": value.page_sitemap_sha256,
        "payload_sha256": value.payload_sha256,
        "post_id": value.post_id,
        "post_sitemap_sha256": value.post_sitemap_sha256,
        "production_evidence": value.production_evidence,
        "public_post_status": value.public_post_status,
        "public_surface_sha256": value.public_surface_sha256,
        "public_surface_verified": value.public_surface_verified,
        "publication_authority": value.publication_authority,
        "reconciliation_status": value.reconciliation_status,
        "related_target_sha256": value.related_target_sha256,
        "request_artifact_sha256": value.request_artifact_sha256,
        "request_sha256": value.request_sha256,
        "response_sha256": value.response_sha256,
        "review_draft_post_id": value.review_draft_post_id,
        "review_draft_rest_evidence_sha256": (value.review_draft_rest_evidence_sha256),
        "review_public_rest_evidence_sha256": (
            value.review_public_rest_evidence_sha256
        ),
        "review_url_html_evidence_sha256": value.review_url_html_evidence_sha256,
        "robots_sha256": value.robots_sha256,
        "sitemap_index_sha256": value.sitemap_index_sha256,
        "status": value.status,
        "strict_public_checks_passed": value.strict_public_checks_passed,
        "target_public_post_id": value.target_public_post_id,
        "verified_checks": list(value.verified_checks),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="st1704_self_hosted_editorial_pilot.py",
        description=(
            "Prepare or owner-operate one allowlisted ST-1704 review draft. "
            "There is no publish, schedule, update, delete, media, taxonomy, "
            "theme, plugin, or generic HTTP command."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument(
            "--article-id",
            choices=(
                ARTICLE_IDS[:1] if name == "verify-carry-on-single-url" else ARTICLE_IDS
            ),
            required=True,
        )
    return parser


def _run(
    command: str,
    article_id: str,
    *,
    modules: Mapping[str, types.ModuleType] | None = None,
    root_identity: RootIdentity | None = None,
    module_seal: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if modules is None:
        modules = {
            name: importlib.import_module(name)
            for name in (
                "raos.adapters.self_hosted_editorial_pilot_https",
                "raos.adapters.self_hosted_editorial_pilot_json",
                "raos.application.editorial.self_hosted_editorial_pilot",
                "raos.domain.editorial.self_hosted_editorial_pilot",
            )
        }
    if root_identity is not None:
        if module_seal is None:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, root_identity)
        _validate_module_seal(modules, module_seal)
    https_adapter = modules["raos.adapters.self_hosted_editorial_pilot_https"]
    json_adapter = modules["raos.adapters.self_hosted_editorial_pilot_json"]
    application = modules["raos.application.editorial.self_hosted_editorial_pilot"]
    domain = modules["raos.domain.editorial.self_hosted_editorial_pilot"]
    adapter_type = getattr(
        https_adapter, "OfficialSelfHostedEditorialPilotWordPressAdapter", None
    )
    journal_type = getattr(json_adapter, "OwnerPrivateLiveReviewDraftJournal", None)
    prepare_editorial_article = getattr(application, "prepare_editorial_article", None)
    failure_type = getattr(domain, "EditorialPilotFailure", None)
    reconciliation_evidence_type = getattr(
        domain, "CarryOnSingleUrlReconciliationEvidence", None
    )
    if (
        not callable(adapter_type)
        or not callable(journal_type)
        or not callable(prepare_editorial_article)
        or not isinstance(failure_type, type)
        or not isinstance(reconciliation_evidence_type, type)
    ):
        _fail_runtime()

    def rebind() -> None:
        if root_identity is not None:
            if module_seal is None:
                _fail_runtime()
            _rebind_root(REPOSITORY_ROOT, root_identity)
            _validate_module_seal(modules, module_seal)

    try:
        if command == "prepare":
            rebind()
            prepared = cast(Any, prepare_editorial_article)(REPOSITORY_ROOT, article_id)
            return _prepared_result(prepared)
        rebind()
        adapter = cast(Any, adapter_type)(REPOSITORY_ROOT)
        rebind()
        journal = cast(Any, journal_type)(REPOSITORY_ROOT, adapter)
        if command == "create-review-draft":
            rebind()
            prepared = cast(Any, prepare_editorial_article)(REPOSITORY_ROOT, article_id)
            rebind()
            receipt = journal.create(prepared.request)
            return _receipt_result(command, receipt, prepared.request)
        if command == "recover-create-review-draft":
            rebind()
            persisted_request = journal.request_for_recovery(article_id)
            rebind()
            receipt = journal.recover(persisted_request)
            return _receipt_result(command, receipt, persisted_request)
        if command == "verify-public":
            rebind()
            persisted_request, expected_public_post_id = journal.committed_request(
                article_id
            )
            rebind()
            return _verification_result(
                adapter.verify_public(persisted_request, expected_public_post_id)
            )
        if command == "verify-carry-on-single-url":
            rebind()
            binding = journal.carry_on_single_url_reconciliation_binding(article_id)
            rebind()
            evidence = adapter.verify_carry_on_single_url(binding)
            if type(evidence) is not reconciliation_evidence_type:
                _fail_runtime()
            return _carry_on_reconciliation_result(evidence)
        raise AssertionError("unreachable command")
    except Exception as error:
        if isinstance(error, failure_type):
            code = getattr(getattr(error, "code", None), "value", None)
            if type(code) is str and code:
                raise _CliRefusal(code) from None
        raise


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _verify_stage_zero()
        sources, root_identity = _load_verified_runtime()
        _enable_site_packages(root_identity)
        modules = _load_verified_modules(sources, root_identity)
        _bind_verified_tracked_reads(modules, sources, root_identity)
        module_seal = _seal_verified_modules(modules)
        result = _run(
            arguments.command,
            arguments.article_id,
            modules=modules,
            root_identity=root_identity,
            module_seal=module_seal,
        )
    except _RuntimeFailure:
        _write_json(
            {
                "article_id": arguments.article_id,
                "command": arguments.command,
                "error": "SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID",
                "production_evidence": False,
                "publication_authority": False,
                "status": "REFUSED",
            },
            target=sys.stderr,
        )
        return 1
    except _CliRefusal as error:
        _write_json(
            {
                "article_id": arguments.article_id,
                "command": arguments.command,
                "error": error.code,
                "production_evidence": False,
                "publication_authority": False,
                "status": "REFUSED",
            },
            target=sys.stderr,
        )
        return 1
    except Exception:
        _write_json(
            {
                "article_id": arguments.article_id,
                "command": arguments.command,
                "error": "SELF_HOSTED_EDITORIAL_PILOT_INTERNAL_FAILURE",
                "production_evidence": False,
                "publication_authority": False,
                "status": "REFUSED",
            },
            target=sys.stderr,
        )
        return 1
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
