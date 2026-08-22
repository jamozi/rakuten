#!/usr/bin/env python3
"""Fixed owner-local commands for the ST-1703 self-hosted draft path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import termios
from typing import Any, Callable, Final, NoReturn, cast


_EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
_RUNTIME_MANIFEST_PATH: Final = Path(
    "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
_RUNTIME_CLI_PATH: Final = "scripts/self_hosted_wordpress.py"
_RUNTIME_STAGE_HEAD_ENV: Final = "RAOS_SELF_HOSTED_STAGE_HEAD"
_RUNTIME_STAGE_CLI_BLOB_ENV: Final = "RAOS_SELF_HOSTED_STAGE_CLI_BLOB"
_RUNTIME_STAGE_CLI_SHA256_ENV: Final = "RAOS_SELF_HOSTED_STAGE_CLI_SHA256"
_RUNTIME_APPROVED_BASE_COMMIT: Final = "b5a6157b878ca0435ee4120d33162aba5ae51f77"
_THEME_RUNTIME_PREFIX: Final = (
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/"
)
_RUNTIME_THEME_ASSET_MANIFEST_PATH: Final = (
    f"{_THEME_RUNTIME_PREFIX}raos-assets.v1.json"
)
_RUNTIME_FINAL_THEME_IMAGE_RELATIVE_PATHS: Final = (
    "assets/images/article-suitcase-guide.webp",
    "assets/images/home-hero.webp",
)
_RUNTIME_FINAL_THEME_IMAGE_PATHS: Final = tuple(
    f"{_THEME_RUNTIME_PREFIX}{relative}"
    for relative in _RUNTIME_FINAL_THEME_IMAGE_RELATIVE_PATHS
)
_RUNTIME_THEME_MANIFEST_KEYS: Final = frozenset(
    {
        "schema",
        "theme_slug",
        "source_files",
        "required_images",
        "generated_by",
        "package_command",
        "check_command",
    }
)
_RUNTIME_THEME_IMAGE_KEYS: Final = frozenset(
    {"path", "status", "sha256", "alt", "prompt", "usage"}
)
_RUNTIME_REQUIRED_PATHS: Final = (
    "changes/st-1703/self-hosted-minimum-start-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1703/self-hosted-minimum-start-v1/Makefile",
    "changes/st-1703/self-hosted-minimum-start-v1/content/first-suitcase-comparison.v1.json",
    "changes/st-1703/self-hosted-minimum-start-v1/python-runtime-code-inventory.v1.sha256",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/assets/theme.css",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/assets/theme.js",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/functions.php",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/parts/footer.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/parts/header.html",
    _RUNTIME_THEME_ASSET_MANIFEST_PATH,
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/style.css",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/templates/front-page.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/templates/single.html",
    "changes/st-1703/self-hosted-minimum-start-v1/theme/kurashinoshirube-child/theme.json",
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
    _RUNTIME_CLI_PATH,
    "scripts/self_hosted_wordpress_python.sh",
)
_RUNTIME_MANIFEST_MAX_BYTES: Final = 128 * 1024
_RUNTIME_FILE_MAX_BYTES: Final = 4 * 1024 * 1024
_RUNTIME_GIT: Final = Path("/usr/bin/git")
_RUNTIME_EXPECTED_PYTHON_BASE: Final = Path(
    "/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu"
)
_RUNTIME_EXPECTED_VENV: Final = _EXPECTED_REPOSITORY_ROOT / ".venv"
_RUNTIME_EXPECTED_PYTHON: Final = _RUNTIME_EXPECTED_PYTHON_BASE / "bin/python3.14"
_RUNTIME_EXPECTED_SYS_PATH: Final = (
    str(_RUNTIME_EXPECTED_PYTHON_BASE / "lib/python314.zip"),
    str(_RUNTIME_EXPECTED_PYTHON_BASE / "lib/python3.14"),
    str(_RUNTIME_EXPECTED_PYTHON_BASE / "lib/python3.14/lib-dynload"),
)
_RUNTIME_EXPECTED_ENVIRONMENT: Final = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_RUNTIME_MODULE_PATHS: Final = {
    "build_st1703_self_hosted_theme": "scripts/build_st1703_self_hosted_theme.py",
    "raos.adapters.self_hosted_wordpress_credentials": "python/raos/adapters/self_hosted_wordpress_credentials.py",
    "raos.adapters.self_hosted_wordpress_https": "python/raos/adapters/self_hosted_wordpress_https.py",
    "raos.adapters.self_hosted_wordpress_journal": "python/raos/adapters/self_hosted_wordpress_journal.py",
    "raos.adapters.self_hosted_wordpress_rest": "python/raos/adapters/self_hosted_wordpress_rest.py",
    "raos.adapters.wordpress_rest": "python/raos/adapters/wordpress_rest.py",
    "raos.application.editorial.self_hosted_minimum_start": "python/raos/application/editorial/self_hosted_minimum_start.py",
    "raos.domain.editorial.market_learning_pilot": "python/raos/domain/editorial/market_learning_pilot.py",
    "raos.domain.editorial.self_hosted_wordpress": "python/raos/domain/editorial/self_hosted_wordpress.py",
    "raos.ports.self_hosted_wordpress": "python/raos/ports/self_hosted_wordpress.py",
}
_CONTENT_PACKET_RUNTIME_PATH: Final = (
    "changes/st-1703/self-hosted-minimum-start-v1/"
    "content/first-suitcase-comparison.v1.json"
)
_runtime_authorized = False
_verified_runtime_bytes: dict[str, bytes] | None = None


class _RuntimeIdentityFailure(RuntimeError):
    """Sanitized pre-import runtime-binding failure."""


def _runtime_fail() -> NoReturn:
    raise _RuntimeIdentityFailure from None


def _runtime_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            _runtime_fail()
        value[key] = item
    return value


def _declared_final_theme_runtime_assets(payload: bytes) -> dict[str, str]:
    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_runtime_pairs,
            parse_constant=lambda _value: _runtime_fail(),
        )
    except _RuntimeIdentityFailure:
        raise
    except UnicodeError, ValueError, TypeError, RecursionError:
        _runtime_fail()
    if type(parsed) is not dict:
        _runtime_fail()
    manifest = cast(dict[str, object], parsed)
    if (
        frozenset(manifest) != _RUNTIME_THEME_MANIFEST_KEYS
        or manifest.get("schema") != "RAOS_WORDPRESS_THEME_ASSETS_V1"
        or manifest.get("theme_slug") != "kurashinoshirube-child"
        or manifest.get("generated_by") != "scripts/build_st1703_self_hosted_theme.py"
        or manifest.get("package_command")
        != "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package"
        or manifest.get("check_command")
        != "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check"
        or type(manifest.get("source_files")) is not list
        or type(manifest.get("required_images")) is not list
    ):
        _runtime_fail()
    images = cast(list[object], manifest["required_images"])
    if len(images) != len(_RUNTIME_FINAL_THEME_IMAGE_RELATIVE_PATHS):
        _runtime_fail()
    expected_paths: set[str] = set(_RUNTIME_FINAL_THEME_IMAGE_RELATIVE_PATHS)
    observed_paths: set[str] = set()
    final_assets: dict[str, str] = {}
    for item in images:
        if type(item) is not dict:
            _runtime_fail()
        image = cast(dict[str, object], item)
        path = image.get("path")
        status = image.get("status")
        digest = image.get("sha256")
        if (
            frozenset(image) != _RUNTIME_THEME_IMAGE_KEYS
            or type(path) is not str
            or path not in expected_paths
            or path in observed_paths
            or type(image.get("alt")) is not str
            or not cast(str, image["alt"]).strip()
            or type(image.get("prompt")) is not str
            or not cast(str, image["prompt"]).strip()
            or type(image.get("usage")) is not str
            or not cast(str, image["usage"]).strip()
            or status not in {"PENDING_FINAL_ASSET", "FINAL"}
        ):
            _runtime_fail()
        observed_paths.add(path)
        runtime_path = f"{_THEME_RUNTIME_PREFIX}{path}"
        if status == "PENDING_FINAL_ASSET":
            if digest is not None:
                _runtime_fail()
            continue
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _runtime_fail()
        final_assets[runtime_path] = digest
    if observed_paths != expected_paths:
        _runtime_fail()
    return final_assets


def _require_runtime_no_symlink_ancestors(path: Path, repository_root: Path) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            _runtime_fail()
        if stat.S_ISLNK(metadata.st_mode):
            _runtime_fail()
        if current == repository_root:
            return
        if repository_root not in current.parents:
            _runtime_fail()
        current = current.parent


def _read_runtime_file(
    repository_root: Path,
    relative: object,
    *,
    maximum_bytes: int,
) -> bytes:
    if (
        not isinstance(relative, Path)
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or type(maximum_bytes) is not int
        or not 1 <= maximum_bytes <= _RUNTIME_FILE_MAX_BYTES
    ):
        _runtime_fail()
    root_descriptor = -1
    parent_descriptor = -1
    descriptor = -1
    try:
        root_descriptor = os.open(
            repository_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        root_metadata = os.fstat(root_descriptor)
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or root_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(root_metadata.st_mode) & 0o022
        ):
            _runtime_fail()
        parent_descriptor = os.dup(root_descriptor)
        for part in relative.parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            child_metadata = os.fstat(child)
            if (
                not stat.S_ISDIR(child_metadata.st_mode)
                or child_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(child_metadata.st_mode) & 0o022
            ):
                os.close(child)
                _runtime_fail()
            os.close(parent_descriptor)
            parent_descriptor = child
        if parent_descriptor < 0 or not relative.parts:
            _runtime_fail()
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        named_before = os.stat(
            relative.parts[-1],
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or not 1 <= opened.st_size <= maximum_bytes
            or stat.S_IMODE(opened.st_mode) & 0o022
            or (opened.st_dev, opened.st_ino)
            != (named_before.st_dev, named_before.st_ino)
        ):
            _runtime_fail()
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _runtime_fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _runtime_fail()
        after = os.fstat(descriptor)
        named_after = os.stat(
            relative.parts[-1],
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_gid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if identity != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or identity != (
            named_after.st_dev,
            named_after.st_ino,
            named_after.st_mode,
            named_after.st_uid,
            named_after.st_gid,
            named_after.st_nlink,
            named_after.st_size,
            named_after.st_mtime_ns,
            named_after.st_ctime_ns,
        ):
            _runtime_fail()
        payload = b"".join(chunks)
        if len(payload) != opened.st_size:
            _runtime_fail()
        return payload
    except _RuntimeIdentityFailure:
        raise
    except OSError, ValueError:
        _runtime_fail()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)


def _require_runtime_path_absent(repository_root: Path, relative: Path) -> None:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        _runtime_fail()
    root_descriptor = -1
    parent_descriptor = -1
    try:
        root_descriptor = os.open(
            repository_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        root_metadata = os.fstat(root_descriptor)
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or root_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(root_metadata.st_mode) & 0o022
        ):
            _runtime_fail()
        parent_descriptor = os.dup(root_descriptor)
        for part in relative.parts[:-1]:
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=parent_descriptor,
                )
            except FileNotFoundError:
                return
            child_metadata = os.fstat(child)
            if (
                not stat.S_ISDIR(child_metadata.st_mode)
                or child_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(child_metadata.st_mode) & 0o022
            ):
                os.close(child)
                _runtime_fail()
            os.close(parent_descriptor)
            parent_descriptor = child
        try:
            os.stat(
                relative.parts[-1],
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        _runtime_fail()
    except _RuntimeIdentityFailure:
        raise
    except (OSError, ValueError):  # fmt: skip
        _runtime_fail()
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)


def _runtime_git_result(
    repository_root: Path,
    arguments: tuple[str, ...],
    *,
    capture_stdout: bool,
    maximum_stdout: int = 4096,
) -> subprocess.CompletedProcess[bytes]:
    if (
        type(arguments) is not tuple
        or not arguments
        or any(type(value) is not str or not value for value in arguments)
        or type(maximum_stdout) is not int
        or not 0 <= maximum_stdout <= _RUNTIME_FILE_MAX_BYTES
    ):
        _runtime_fail()
    try:
        metadata = _RUNTIME_GIT.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or not os.access(_RUNTIME_GIT, os.X_OK)
        ):
            _runtime_fail()
        result = subprocess.run(
            (
                str(_RUNTIME_GIT),
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                *arguments,
            ),
            cwd=repository_root,
            env={
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except _RuntimeIdentityFailure:
        raise
    except BaseException:
        _runtime_fail()
    if capture_stdout and len(result.stdout) > maximum_stdout:
        _runtime_fail()
    return result


def _runtime_head_blob(
    repository_root: Path,
    *,
    commit: str,
    path: str,
    maximum_bytes: int,
) -> bytes:
    object_name = f"{commit}:{path}"
    size_result = _runtime_git_result(
        repository_root,
        ("cat-file", "-s", object_name),
        capture_stdout=True,
        maximum_stdout=80,
    )
    if size_result.returncode != 0:
        _runtime_fail()
    try:
        size_text = size_result.stdout.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _runtime_fail()
    if str(size) != size_text or not 1 <= size <= maximum_bytes:
        _runtime_fail()
    blob = _runtime_git_result(
        repository_root,
        ("cat-file", "blob", object_name),
        capture_stdout=True,
        maximum_stdout=size,
    )
    if blob.returncode != 0 or len(blob.stdout) != size:
        _runtime_fail()
    return blob.stdout


def _require_runtime_head_path_absent(
    repository_root: Path, *, commit: str, path: str
) -> None:
    result = _runtime_git_result(
        repository_root,
        ("ls-tree", "--name-only", "--full-tree", commit, "--", path),
        capture_stdout=True,
        maximum_stdout=4096,
    )
    if result.returncode != 0 or result.stdout != b"":
        _runtime_fail()


def _runtime_tracked_theme_image_paths(repository_root: Path) -> tuple[str, ...]:
    image_directory = f"{_THEME_RUNTIME_PREFIX}assets/images"
    result = _runtime_git_result(
        repository_root,
        ("ls-files", "-z", "--", image_directory),
        capture_stdout=True,
        maximum_stdout=_RUNTIME_FILE_MAX_BYTES,
    )
    if result.returncode != 0:
        _runtime_fail()
    if not result.stdout:
        return ()
    if not result.stdout.endswith(b"\0"):
        _runtime_fail()
    try:
        paths = tuple(
            value.decode("utf-8", errors="strict")
            for value in result.stdout[:-1].split(b"\0")
        )
    except UnicodeError:
        _runtime_fail()
    if (
        not paths
        or any(not path for path in paths)
        or len(set(paths)) != len(paths)
        or paths != tuple(sorted(paths))
    ):
        _runtime_fail()
    return paths


def _valid_runtime_python() -> bool:
    return (
        sys.version_info[:3] == (3, 14, 6)
        and sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == "/dev/null"
        and Path(sys.prefix) == _RUNTIME_EXPECTED_VENV
        and Path(sys.base_prefix) == _RUNTIME_EXPECTED_PYTHON_BASE
        and Path(sys.executable).resolve() == _RUNTIME_EXPECTED_PYTHON
        and tuple(sys.path) == _RUNTIME_EXPECTED_SYS_PATH
        and dict(os.environ) == _RUNTIME_EXPECTED_ENVIRONMENT
    )


def _valid_runtime_entry() -> bool:
    return __name__ == "__main__" and globals().get("__file__") == "<stdin>"


def _take_runtime_stage_binding() -> tuple[str, str, str]:
    try:
        stage_head = os.environ.pop(_RUNTIME_STAGE_HEAD_ENV)
        stage_cli_blob = os.environ.pop(_RUNTIME_STAGE_CLI_BLOB_ENV)
        stage_cli_sha256 = os.environ.pop(_RUNTIME_STAGE_CLI_SHA256_ENV)
    except KeyError:
        _runtime_fail()
    if (
        len(stage_head) != 40
        or any(character not in "0123456789abcdef" for character in stage_head)
        or len(stage_cli_blob) != 40
        or any(character not in "0123456789abcdef" for character in stage_cli_blob)
        or len(stage_cli_sha256) != 64
        or any(character not in "0123456789abcdef" for character in stage_cli_sha256)
    ):
        _runtime_fail()
    return stage_head, stage_cli_blob, stage_cli_sha256


def _verify_self_hosted_runtime_identity(
    repository_root: Path,
    *,
    stage_head: str,
    stage_cli_blob: str,
    stage_cli_sha256: str,
) -> dict[str, bytes]:
    """Bind a reviewed clean HEAD and exact runtime bytes before RAOS imports."""

    if (
        repository_root != _EXPECTED_REPOSITORY_ROOT
        or not _valid_runtime_entry()
        or not _valid_runtime_python()
    ):
        _runtime_fail()
    if (
        type(stage_head) is not str
        or len(stage_head) != 40
        or any(character not in "0123456789abcdef" for character in stage_head)
        or type(stage_cli_blob) is not str
        or len(stage_cli_blob) != 40
        or any(character not in "0123456789abcdef" for character in stage_cli_blob)
        or type(stage_cli_sha256) is not str
        or len(stage_cli_sha256) != 64
        or any(character not in "0123456789abcdef" for character in stage_cli_sha256)
    ):
        _runtime_fail()
    top = _runtime_git_result(
        repository_root, ("rev-parse", "--show-toplevel"), capture_stdout=True
    )
    head = _runtime_git_result(
        repository_root, ("rev-parse", "--verify", "HEAD"), capture_stdout=True
    )
    cli_object = _runtime_git_result(
        repository_root,
        ("rev-parse", "--verify", f"{stage_head}:{_RUNTIME_CLI_PATH}"),
        capture_stdout=True,
        maximum_stdout=80,
    )
    if top.returncode != 0 or head.returncode != 0 or cli_object.returncode != 0:
        _runtime_fail()
    try:
        top_path = Path(top.stdout.decode("utf-8", errors="strict").strip())
        head_commit = head.stdout.decode("ascii", errors="strict").strip()
        cli_object_id = cli_object.stdout.decode("ascii", errors="strict").strip()
    except UnicodeError:
        _runtime_fail()
    if (
        top_path != repository_root
        or head_commit != stage_head
        or cli_object_id != stage_cli_blob
    ):
        _runtime_fail()
    if (
        _runtime_git_result(
            repository_root,
            (
                "merge-base",
                "--is-ancestor",
                _RUNTIME_APPROVED_BASE_COMMIT,
                head_commit,
            ),
            capture_stdout=False,
        ).returncode
        != 0
    ):
        _runtime_fail()
    manifest_raw = _read_runtime_file(
        repository_root,
        _RUNTIME_MANIFEST_PATH,
        maximum_bytes=_RUNTIME_MANIFEST_MAX_BYTES,
    )
    if (
        _runtime_head_blob(
            repository_root,
            commit=head_commit,
            path=_RUNTIME_MANIFEST_PATH.as_posix(),
            maximum_bytes=_RUNTIME_MANIFEST_MAX_BYTES,
        )
        != manifest_raw
    ):
        _runtime_fail()
    try:
        parsed = json.loads(
            manifest_raw.decode("ascii", errors="strict"),
            object_pairs_hook=_runtime_pairs,
            parse_constant=lambda _value: _runtime_fail(),
        )
    except _RuntimeIdentityFailure:
        raise
    except UnicodeError, ValueError, RecursionError:
        _runtime_fail()
    if type(parsed) is not dict:
        _runtime_fail()
    manifest = cast(dict[str, object], parsed)
    if set(manifest) != {
        "approved_base_commit",
        "external_action_authority",
        "generated_by",
        "paths",
        "repository_development_authority",
        "schema",
        "slice_id",
        "story_id",
    }:
        _runtime_fail()
    if (
        manifest.get("approved_base_commit") != _RUNTIME_APPROVED_BASE_COMMIT
        or manifest.get("external_action_authority") != "NONE"
        or manifest.get("generated_by")
        != "scripts/build_st1703_self_hosted_runtime_manifest.py"
        or manifest.get("repository_development_authority")
        != "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION"
        or manifest.get("schema") != "SELF_HOSTED_WORDPRESS_RUNTIME_MANIFEST_V1"
        or manifest.get("slice_id") != "SELF_HOSTED_MINIMUM_START_V1"
        or manifest.get("story_id") != "ST-1703"
    ):
        _runtime_fail()
    entries_value = manifest.get("paths")
    if type(entries_value) is not list:
        _runtime_fail()
    entries = cast(list[object], entries_value)
    if (
        not len(_RUNTIME_REQUIRED_PATHS)
        <= len(entries)
        <= len(_RUNTIME_REQUIRED_PATHS) + len(_RUNTIME_FINAL_THEME_IMAGE_PATHS)
    ):
        _runtime_fail()
    validated_entries: list[tuple[str, int, str]] = []
    for entry in entries:
        if type(entry) is not dict:
            _runtime_fail()
        entry_value = cast(dict[str, object], entry)
        if set(entry_value) != {"bytes", "path", "sha256"}:
            _runtime_fail()
        path = entry_value.get("path")
        expected_bytes = entry_value.get("bytes")
        expected_sha256 = entry_value.get("sha256")
        if (
            type(path) is not str
            or type(expected_bytes) is not int
            or not 1 <= expected_bytes <= _RUNTIME_FILE_MAX_BYTES
            or type(expected_sha256) is not str
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
        ):
            _runtime_fail()
        validated_entries.append((path, expected_bytes, expected_sha256))
    observed_paths = tuple(path for path, _size, _sha256 in validated_entries)
    base_paths = tuple(sorted(_RUNTIME_REQUIRED_PATHS))
    base_path_set = set(base_paths)
    allowed_final_path_set = set(_RUNTIME_FINAL_THEME_IMAGE_PATHS)
    observed_path_set = set(observed_paths)
    if (
        len(base_path_set) != len(base_paths)
        or base_path_set.intersection(allowed_final_path_set)
        or len(allowed_final_path_set) != len(_RUNTIME_FINAL_THEME_IMAGE_PATHS)
        or len(observed_path_set) != len(observed_paths)
        or observed_paths != tuple(sorted(observed_paths))
        or base_path_set - observed_path_set
        or observed_path_set - base_path_set - allowed_final_path_set
    ):
        _runtime_fail()
    entries_by_path = {
        path: (expected_bytes, expected_sha256)
        for path, expected_bytes, expected_sha256 in validated_entries
    }
    final_assets: dict[str, str] = {}
    head_theme_manifest: bytes | None = None
    if _RUNTIME_THEME_ASSET_MANIFEST_PATH in base_path_set:
        head_theme_manifest = _runtime_head_blob(
            repository_root,
            commit=head_commit,
            path=_RUNTIME_THEME_ASSET_MANIFEST_PATH,
            maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
        )
        theme_entry = entries_by_path.get(_RUNTIME_THEME_ASSET_MANIFEST_PATH)
        if theme_entry is None or theme_entry != (
            len(head_theme_manifest),
            hashlib.sha256(head_theme_manifest).hexdigest(),
        ):
            _runtime_fail()
        final_assets = _declared_final_theme_runtime_assets(head_theme_manifest)
        expected_paths = tuple(sorted((*base_paths, *final_assets)))
        if observed_paths != expected_paths:
            _runtime_fail()
        for path, declared_digest in final_assets.items():
            entry = entries_by_path.get(path)
            if entry is None or entry[1] != declared_digest:
                _runtime_fail()
        if _runtime_tracked_theme_image_paths(repository_root) != tuple(
            sorted(final_assets)
        ):
            _runtime_fail()
        for pending_path in allowed_final_path_set - set(final_assets):
            _require_runtime_head_path_absent(
                repository_root,
                commit=head_commit,
                path=pending_path,
            )
            _require_runtime_path_absent(repository_root, Path(pending_path))
    elif observed_paths != base_paths:
        _runtime_fail()

    runtime_contents: dict[str, bytes] = {}
    for path in base_paths:
        expected_bytes, expected_sha256 = entries_by_path[path]
        content = _read_runtime_file(
            repository_root,
            Path(path),
            maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
        )
        if (
            len(content) != expected_bytes
            or hashlib.sha256(content).hexdigest() != expected_sha256
        ):
            _runtime_fail()
        runtime_contents[path] = content
    if (
        head_theme_manifest is not None
        and runtime_contents.get(_RUNTIME_THEME_ASSET_MANIFEST_PATH)
        != head_theme_manifest
    ):
        _runtime_fail()
    for path, declared_digest in sorted(final_assets.items()):
        expected_bytes, expected_sha256 = entries_by_path[path]
        content = _read_runtime_file(
            repository_root,
            Path(path),
            maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
        )
        if (
            len(content) != expected_bytes
            or expected_sha256 != declared_digest
            or hashlib.sha256(content).hexdigest() != declared_digest
            or len(content) < 12
            or content[:4] != b"RIFF"
            or content[8:12] != b"WEBP"
        ):
            _runtime_fail()
        runtime_contents[path] = content

    cli_source = runtime_contents.get(_RUNTIME_CLI_PATH)
    if cli_source is None or hashlib.sha256(cli_source).hexdigest() != stage_cli_sha256:
        _runtime_fail()
    for path in observed_paths:
        if (
            _runtime_head_blob(
                repository_root,
                commit=head_commit,
                path=path,
                maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
            )
            != runtime_contents[path]
        ):
            _runtime_fail()
    tracked = (_RUNTIME_MANIFEST_PATH.as_posix(), *observed_paths)
    status = _runtime_git_result(
        repository_root,
        ("status", "--porcelain=v1", "--untracked-files=all"),
        capture_stdout=True,
        maximum_stdout=_RUNTIME_FILE_MAX_BYTES,
    )
    index_flags = _runtime_git_result(
        repository_root,
        ("ls-files", "-v"),
        capture_stdout=True,
        maximum_stdout=_RUNTIME_FILE_MAX_BYTES,
    )
    if (
        _runtime_git_result(
            repository_root,
            ("ls-files", "--error-unmatch", "--", *tracked),
            capture_stdout=False,
        ).returncode
        != 0
        or _runtime_git_result(
            repository_root,
            (
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--quiet",
                head_commit,
                "--",
            ),
            capture_stdout=False,
        ).returncode
        != 0
        or status.returncode != 0
        or status.stdout != b""
        or index_flags.returncode != 0
        or any(not line.startswith(b"H ") for line in index_flags.stdout.splitlines())
    ):
        _runtime_fail()
    return runtime_contents


def _runtime_refusal_and_exit() -> NoReturn:
    print(
        json.dumps(
            {
                "publication_authorized": False,
                "reason_code": "SELF_HOSTED_RUNTIME_BINDING_INVALID",
                "status": "BLOCKED",
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    raise SystemExit(2) from None


def _bootstrap_runtime_identity_or_exit() -> dict[str, bytes]:
    try:
        stage_head, stage_cli_blob, stage_cli_sha256 = _take_runtime_stage_binding()
        return _verify_self_hosted_runtime_identity(
            _EXPECTED_REPOSITORY_ROOT,
            stage_head=stage_head,
            stage_cli_blob=stage_cli_blob,
            stage_cli_sha256=stage_cli_sha256,
        )
    except _RuntimeIdentityFailure:
        _runtime_refusal_and_exit()


def _install_scoped_runtime_packages(
    repository_root: Path,
    verified_bytes: dict[str, bytes],
) -> None:
    """Avoid unrelated eager package initializers in the live owner process."""

    import importlib.abc
    import importlib.machinery
    import types

    if (
        any(name == "raos" or name.startswith("raos.") for name in sys.modules)
        or set(_RUNTIME_MODULE_PATHS.values()) - set(verified_bytes)
        or set(_RUNTIME_MODULE_PATHS.values()) - set(_RUNTIME_REQUIRED_PATHS)
    ):
        _runtime_fail()

    class _VerifiedSourceLoader(importlib.abc.Loader):
        def __init__(self, fullname: str, relative: str) -> None:
            self.fullname = fullname
            self.relative = relative

        def create_module(self, spec: object) -> None:
            del spec
            return None

        def exec_module(self, module: types.ModuleType) -> None:
            if module.__name__ != self.fullname:
                _runtime_fail()
            filename = str(repository_root / self.relative)
            try:
                code = compile(
                    verified_bytes[self.relative],
                    filename,
                    "exec",
                    dont_inherit=True,
                )
            except BaseException:
                _runtime_fail()
            module.__file__ = filename
            setattr(module, "__cached__", None)
            module.__loader__ = self
            module.__package__ = self.fullname.rpartition(".")[0]
            try:
                exec(code, module.__dict__)
            except _RuntimeIdentityFailure:
                raise
            except BaseException:
                _runtime_fail()

    class _VerifiedSourceFinder(importlib.abc.MetaPathFinder):
        def find_spec(
            self,
            fullname: str,
            path: object = None,
            target: object = None,
        ) -> importlib.machinery.ModuleSpec | None:
            del path, target
            relative = _RUNTIME_MODULE_PATHS.get(fullname)
            if relative is not None:
                return importlib.machinery.ModuleSpec(
                    fullname,
                    _VerifiedSourceLoader(fullname, relative),
                    origin=str(repository_root / relative),
                    is_package=False,
                )
            if fullname.startswith("raos."):
                raise ImportError("unlisted RAOS runtime module") from None
            return None

    package_roots = (
        ("raos", repository_root / "python/raos"),
        ("raos.adapters", repository_root / "python/raos/adapters"),
        ("raos.application", repository_root / "python/raos/application"),
        (
            "raos.application.editorial",
            repository_root / "python/raos/application/editorial",
        ),
        ("raos.domain", repository_root / "python/raos/domain"),
        (
            "raos.domain.editorial",
            repository_root / "python/raos/domain/editorial",
        ),
        ("raos.ports", repository_root / "python/raos/ports"),
    )
    for name, path in package_roots:
        try:
            _require_runtime_no_symlink_ancestors(path, repository_root)
            metadata = path.lstat()
        except OSError:
            _runtime_fail()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _runtime_fail()
        module = types.ModuleType(name)
        module.__package__ = name
        module.__path__ = [str(path)]
        specification = importlib.machinery.ModuleSpec(
            name, loader=None, is_package=True
        )
        specification.submodule_search_locations = [str(path)]
        module.__spec__ = specification
        sys.modules[name] = module
        parent_name, separator, child_name = name.rpartition(".")
        if separator:
            parent = sys.modules.get(parent_name)
            if parent is None:
                _runtime_fail()
            setattr(parent, child_name, module)
    sys.meta_path.insert(0, _VerifiedSourceFinder())


if __name__ == "__main__":
    _verified_bootstrap_bytes = _bootstrap_runtime_identity_or_exit()
    try:
        _install_scoped_runtime_packages(
            _EXPECTED_REPOSITORY_ROOT, _verified_bootstrap_bytes
        )
    except _RuntimeIdentityFailure:
        _runtime_refusal_and_exit()
    _verified_runtime_bytes = _verified_bootstrap_bytes
    _runtime_authorized = True

_SCRIPT_REPOSITORY_ROOT = (
    _EXPECTED_REPOSITORY_ROOT
    if _runtime_authorized
    else Path(__file__).resolve().parents[1]
)
_SCRIPTS_ROOT = _SCRIPT_REPOSITORY_ROOT / "scripts"
_PYTHON_ROOT = _SCRIPT_REPOSITORY_ROOT / "python"
if not _runtime_authorized:
    for _development_import_root in (_SCRIPTS_ROOT, _PYTHON_ROOT):
        if str(_development_import_root) not in sys.path:
            sys.path.insert(0, str(_development_import_root))

try:
    from build_st1703_self_hosted_theme import (  # noqa: E402
        source_check as theme_source_check,
        source_check_from_verified_files as verified_theme_source_check,
    )
    from raos.adapters.self_hosted_wordpress_credentials import (  # noqa: E402
        OwnerPrivateSelfHostedWordPressCredentialStore,
        SelfHostedWordPressCredentials,
    )
    from raos.adapters.self_hosted_wordpress_https import (  # noqa: E402
        OfficialSelfHostedWordPressDraftAdapter,
    )
    from raos.adapters.self_hosted_wordpress_journal import (  # noqa: E402
        DurableSelfHostedWordPressDraftAdapter,
    )
    from raos.application.editorial.self_hosted_minimum_start import (  # noqa: E402
        load_first_article_candidate,
    )
    from raos.domain.editorial.self_hosted_wordpress import (  # noqa: E402
        SelfHostedWordPressDraftReceipt,
        SelfHostedWordPressFailure,
        SelfHostedWordPressFailureCode,
        SelfHostedWordPressOperation,
        fail_self_hosted_wordpress,
    )
except BaseException:
    if _runtime_authorized:
        _runtime_refusal_and_exit()
    raise


EXPECTED_REPOSITORY_ROOT = _EXPECTED_REPOSITORY_ROOT
_MAX_TTY_BYTES = 4096


def _fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


class _ClosedArgumentParser(argparse.ArgumentParser):
    """Reject malformed controls without reflecting untrusted argv values."""

    def error(self, message: str) -> NoReturn:
        del message
        _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)


def _physical_repository_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
    try:
        if value.is_symlink() or value.resolve(strict=True) != value:
            _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
    except OSError:
        _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
    return value


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        offset += written


def _read_private_tty(prompt: bytes) -> bytes:
    descriptor = -1
    original: list[int | list[bytes | int]] | None = None
    try:
        descriptor = os.open(
            "/dev/tty", os.O_RDWR | os.O_CLOEXEC | os.O_NOCTTY | os.O_NOFOLLOW
        )
        if not os.isatty(descriptor):
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        original = termios.tcgetattr(descriptor)
        hidden = list(original)
        local_flags = hidden[3]
        if type(local_flags) is not int:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        hidden[3] = local_flags & ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(descriptor, termios.TCSAFLUSH, hidden)
        _write_all(descriptor, prompt)
        chunks: list[bytes] = []
        total = 0
        while total <= _MAX_TTY_BYTES:
            byte = os.read(descriptor, 1)
            if not byte or byte in {b"\n", b"\r"}:
                break
            chunks.append(byte)
            total += len(byte)
        _write_all(descriptor, b"\n")
        value = b"".join(chunks)
        if not 1 <= len(value) <= _MAX_TTY_BYTES:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        return value
    except SelfHostedWordPressFailure:
        raise
    except BaseException:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
    finally:
        if descriptor >= 0:
            if original is not None:
                try:
                    termios.tcsetattr(descriptor, termios.TCSAFLUSH, original)
                except BaseException:
                    pass
            os.close(descriptor)


def _install_credentials(
    repository_root: Path,
    *,
    tty_reader: Callable[[bytes], bytes],
) -> dict[str, object]:
    store = OwnerPrivateSelfHostedWordPressCredentialStore(repository_root)
    if store.metadata_status() != "MISSING":
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
    username_raw = tty_reader(b"WordPress username (hidden): ")
    password_raw = tty_reader(b"WordPress application password (hidden): ")
    try:
        username = username_raw.decode("ascii", errors="strict")
        decoded_second_field = password_raw.decode("ascii", errors="strict")
    except UnicodeError:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
    store.install(
        SelfHostedWordPressCredentials(
            username=username,
            _application_password=decoded_second_field,
        )
    )
    return {
        "credential_metadata": "METADATA_READY",
        "network_requests": 0,
        "publication_actions": 0,
        "secret_values_printed": 0,
        "status": "INSTALLED",
    }


def _doctor(
    repository_root: Path,
    *,
    content_packet_bytes: bytes | None = None,
    theme_payloads: dict[str, bytes] | None = None,
) -> dict[str, object]:
    credential_status = OwnerPrivateSelfHostedWordPressCredentialStore(
        repository_root
    ).metadata_status()
    load_first_article_candidate(
        repository_root,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        packet_bytes=content_packet_bytes,
    )
    theme = (
        theme_source_check()
        if theme_payloads is None
        else verified_theme_source_check(theme_payloads)
    )
    blockers = ["AFFILIATE_SLOTS_PENDING"]
    if credential_status != "METADATA_READY":
        blockers.append("WORDPRESS_CREDENTIAL_INSTALL_REQUIRED")
    if theme["package_ready"] is not True:
        blockers.append("FINAL_THEME_ASSETS_MISSING")
    return {
        "blockers": blockers,
        "content_packet": "VALID",
        "credential_metadata": credential_status,
        "credential_value_reads": 0,
        "external_writes": 0,
        "network_requests": 0,
        "publication_actions": 0,
        "status": "LOCAL_PREPARATION_REQUIRED" if blockers else "LOCAL_READY",
        "theme_source": theme["status"],
    }


def _receipt_output(receipt: SelfHostedWordPressDraftReceipt) -> dict[str, object]:
    return {
        "content_sha256": receipt.content_sha256,
        "disposition": receipt.disposition.value,
        "draft_id": receipt.draft_id,
        "operation": receipt.operation.value,
        "operation_sha256": receipt.operation_sha256,
        "production_eligible": False,
        "publication_authorized": False,
        "response_sha256": receipt.response_sha256,
        "status": receipt.status,
    }


def _apply_draft(
    repository_root: Path,
    *,
    content_packet_bytes: bytes | None = None,
) -> dict[str, object]:
    if (
        OwnerPrivateSelfHostedWordPressCredentialStore(
            repository_root
        ).metadata_status()
        != "METADATA_READY"
    ):
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_METADATA_INVALID)
    candidate = load_first_article_candidate(
        repository_root,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        packet_bytes=content_packet_bytes,
    )
    attempt = OfficialSelfHostedWordPressDraftAdapter(repository_root)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=repository_root,
        attempt_port=attempt,
    )
    return _receipt_output(durable.apply(candidate))


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", allow_abbrev=False)
    commands.add_parser("install-credentials", allow_abbrev=False)
    commands.add_parser("create-draft", allow_abbrev=False)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path = EXPECTED_REPOSITORY_ROOT,
    tty_reader: Callable[[bytes], bytes] = _read_private_tty,
) -> int:
    os.umask(0o077)
    if not _runtime_authorized or _verified_runtime_bytes is None:
        print(
            json.dumps(
                {
                    "publication_authorized": False,
                    "reason_code": "SELF_HOSTED_RUNTIME_BINDING_INVALID",
                    "status": "BLOCKED",
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2
    try:
        arguments = _parser().parse_args(argv)
        root = _physical_repository_root(repository_root)
        content_packet_bytes = _verified_runtime_bytes[_CONTENT_PACKET_RUNTIME_PATH]
        theme_payloads = {
            path.removeprefix(_THEME_RUNTIME_PREFIX): payload
            for path, payload in _verified_runtime_bytes.items()
            if path.startswith(_THEME_RUNTIME_PREFIX)
        }
        if arguments.command == "doctor":
            result = _doctor(
                root,
                content_packet_bytes=content_packet_bytes,
                theme_payloads=theme_payloads,
            )
        elif arguments.command == "install-credentials":
            result = _install_credentials(root, tty_reader=tty_reader)
        elif arguments.command == "create-draft":
            result = _apply_draft(root, content_packet_bytes=content_packet_bytes)
        else:
            _fail(SelfHostedWordPressFailureCode.OPERATION_NOT_ALLOWED)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except SelfHostedWordPressFailure as error:
        print(
            json.dumps(
                {
                    "publication_authorized": False,
                    "reason_code": error.code.value,
                    "status": "BLOCKED",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    except KeyError, _RuntimeIdentityFailure:
        print(
            json.dumps(
                {
                    "publication_authorized": False,
                    "reason_code": "SELF_HOSTED_RUNTIME_BINDING_INVALID",
                    "status": "BLOCKED",
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
