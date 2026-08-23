#!/usr/bin/env python3
"""Fixed-path, manifest-bound CLI for the ST-1704 local pilot ledger."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
from typing import cast, Final, NoReturn


OWNER_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
OWNER_CLI_PATH: Final = OWNER_REPOSITORY_ROOT / "scripts/st1704_owner_local_pilot.py"
OWNER_PYTHON: Final = "/home/minami/rakuten/.venv/bin/python"
SOURCE_ROOT: Final = Path(os.path.abspath(__file__)).parent.parent
MANIFEST_RELATIVE: Final = (
    "changes/st-1704/owner-local-pilot-v1/runtime-manifest.v1.json"
)
EXPECTED_CONTRACT_SHA256: Final = (
    "9251302614dc0e0901680236d29966ac3d51a20aa898890f7ed68f8ae068a580"
)
EXPECTED_POLICY: Final = {
    "article_slots": 5,
    "automatic_publication": "DISABLED",
    "duration_days": 14,
    "first_five_drafts": "CODEX_NOT_OPENAI_API",
    "improvement_output": "PROPOSAL_AND_DIFF_ONLY",
    "labor_cost_per_hour_jpy": 3000,
    "monthly_incremental_cost_cap_jpy": 2000,
    "nonessential_tracking": "DISABLED_OD_012",
    "site_origin": "https://kurashinoshirube.com",
}
EXPECTED_RUNTIME_PATHS: Final = (
    "changes/st-1704/owner-local-pilot-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1704/owner-local-pilot-v1/Makefile",
    "changes/st-1704/owner-local-pilot-v1/PREFLIGHT.md",
    "changes/st-1704/owner-local-pilot-v1/README.md",
    "changes/st-1704/owner-local-pilot-v1/examples/bootstrap-first-publication.v1.json",
    "python/raos/adapters/owner_local_pilot_json.py",
    "python/raos/application/editorial/owner_local_pilot.py",
    "python/raos/domain/editorial/owner_local_pilot.py",
    "python/raos/ports/owner_local_pilot.py",
    "scripts/build_st1704_owner_local_pilot.py",
    "scripts/st1704_owner_local_pilot.py",
)
_MODULE_PATHS: Final = (
    (
        "raos.domain.editorial.owner_local_pilot",
        "python/raos/domain/editorial/owner_local_pilot.py",
    ),
    ("raos.ports.owner_local_pilot", "python/raos/ports/owner_local_pilot.py"),
    (
        "raos.application.editorial.owner_local_pilot",
        "python/raos/application/editorial/owner_local_pilot.py",
    ),
    (
        "raos.adapters.owner_local_pilot_json",
        "python/raos/adapters/owner_local_pilot_json.py",
    ),
)
COMMANDS: Final = frozenset({"doctor", "init", "record", "report"})
MAX_MANIFEST_BYTES: Final = 512 * 1024
MAX_RUNTIME_BYTES: Final = 2 * 1024 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PILOT_FAILURE_CODES: Final = frozenset(
    {
        "INVALID_DOCUMENT",
        "OBSERVATION_ID_CONFLICT",
        "ARTICLE_IDENTITY_CONFLICT",
        "LEDGER_TAMPERED",
        "STORE_NOT_INITIALIZED",
        "STORE_UNSAFE",
        "STORE_BUSY",
        "RECOVERY_REQUIRED",
        "RUNTIME_INVALID",
    }
)
RootIdentity = tuple[int, int]


class _RuntimeFailure(RuntimeError):
    """Closed stage-zero refusal; never includes observed input."""


class _CommandFailure(RuntimeError):
    """Closed domain/adapter refusal."""


def _fail_runtime() -> NoReturn:
    raise _RuntimeFailure("OWNER_LOCAL_PILOT_RUNTIME_INVALID") from None


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail_runtime()


def _render(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail_runtime()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail_runtime()


def _parse_integer(value: str) -> int:
    if len(value) > 20:
        _fail_runtime()
    try:
        return int(value)
    except ValueError:
        _fail_runtime()


def _decode_manifest(raw: bytes) -> dict[str, object]:
    if not raw or raw.startswith(b"\xef\xbb\xbf"):
        _fail_runtime()
    try:
        decoded = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_int=_parse_integer,
            parse_constant=_reject_number,
        )
    except _RuntimeFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, RecursionError:
        _fail_runtime()
    if type(decoded) is not dict:
        _fail_runtime()
    return cast(dict[str, object], decoded)


def _open_absolute_directory(path: Path, *, safe_ancestors: bool) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail_runtime()
    current = -1
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        for part in path.parts[1:]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            if safe_ancestors and stat.S_IMODE(os.fstat(following).st_mode) & 0o022:
                os.close(following)
                _fail_runtime()
            os.close(current)
            current = following
        return current
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _safe_root(fd: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o022
    ):
        _fail_runtime()
    return observed


def _relative_parts(relative: str) -> tuple[str, ...]:
    path = Path(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail_runtime()
    return path.parts


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative_parts(relative)
    current = -1
    try:
        current = os.dup(root_fd)
        for part in parts[:-1]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        return current, parts[-1]
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _safe_file(fd: int, *, maximum: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.getuid()
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) & 0o022
        or not 0 < observed.st_size <= maximum
    ):
        _fail_runtime()
    return observed


def _read_relative(root_fd: int, relative: str, *, maximum: int) -> bytes:
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail_runtime()
        try:
            before = _safe_file(fd, maximum=maximum)
            remaining = before.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(fd, min(remaining, 65_536))
                if not chunk:
                    _fail_runtime()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(fd, 1):
                _fail_runtime()
            after = _safe_file(fd, maximum=maximum)
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
            try:
                rebound_fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
            except OSError:
                _fail_runtime()
            try:
                rebound = _safe_file(rebound_fd, maximum=maximum)
                if (before.st_dev, before.st_ino) != (
                    rebound.st_dev,
                    rebound.st_ino,
                ):
                    _fail_runtime()
            finally:
                os.close(rebound_fd)
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _rebind_root(root: Path, root_fd: int) -> None:
    rebound = _open_absolute_directory(root, safe_ancestors=False)
    try:
        expected = _safe_root(root_fd)
        observed = _safe_root(rebound)
        if (expected.st_dev, expected.st_ino) != (observed.st_dev, observed.st_ino):
            _fail_runtime()
    finally:
        os.close(rebound)


def _verify_runtime_integrity(
    root: Path,
) -> tuple[dict[str, bytes], RootIdentity]:
    """Read and verify the closed runtime tree without importing repository code."""

    root_fd = _open_absolute_directory(root, safe_ancestors=False)
    try:
        verified_root = _safe_root(root_fd)
        manifest = _decode_manifest(
            _read_relative(
                root_fd,
                MANIFEST_RELATIVE,
                maximum=MAX_MANIFEST_BYTES,
            )
        )
        if set(manifest) != {
            "contract_sha256",
            "external_action_authority",
            "generated_by",
            "observation_input_schema",
            "paths",
            "policy",
            "schema",
            "slice_id",
            "story_id",
        }:
            _fail_runtime()
        if (
            manifest["contract_sha256"] != EXPECTED_CONTRACT_SHA256
            or manifest["external_action_authority"] != "NONE"
            or manifest["generated_by"] != "scripts/build_st1704_owner_local_pilot.py"
            or manifest["policy"] != EXPECTED_POLICY
            or manifest["schema"] != "ST1704_OWNER_LOCAL_PILOT_RUNTIME_MANIFEST_V1"
            or manifest["slice_id"] != "ST1704_OWNER_LOCAL_PILOT_LEDGER_V1"
            or manifest["story_id"] != "ST-1704"
        ):
            _fail_runtime()
        contract = {
            "observation_input_schema": manifest["observation_input_schema"],
            "policy": manifest["policy"],
        }
        if hashlib.sha256(_canonical(contract)).hexdigest() != EXPECTED_CONTRACT_SHA256:
            _fail_runtime()
        entries_value = manifest["paths"]
        if type(entries_value) is not list:
            _fail_runtime()
        entries = cast(list[object], entries_value)
        if len(entries) != len(EXPECTED_RUNTIME_PATHS):
            _fail_runtime()
        sources: dict[str, bytes] = {}
        for expected_path, entry_value in zip(
            EXPECTED_RUNTIME_PATHS, entries, strict=True
        ):
            if type(entry_value) is not dict:
                _fail_runtime()
            entry = cast(dict[str, object], entry_value)
            if set(entry) != {
                "bytes",
                "path",
                "sha256",
            }:
                _fail_runtime()
            byte_count = entry["bytes"]
            sha256 = entry["sha256"]
            if (
                entry["path"] != expected_path
                or type(byte_count) is not int
                or not 0 < byte_count <= MAX_RUNTIME_BYTES
                or type(sha256) is not str
                or _SHA256.fullmatch(sha256) is None
            ):
                _fail_runtime()
            raw = _read_relative(root_fd, expected_path, maximum=MAX_RUNTIME_BYTES)
            if len(raw) != byte_count or hashlib.sha256(raw).hexdigest() != sha256:
                _fail_runtime()
            sources[expected_path] = raw
        _rebind_root(root, root_fd)
        final_root = _safe_root(root_fd)
        if (verified_root.st_dev, verified_root.st_ino) != (
            final_root.st_dev,
            final_root.st_ino,
        ):
            _fail_runtime()
        return sources, (final_root.st_dev, final_root.st_ino)
    except _RuntimeFailure:
        raise
    except Exception:
        _fail_runtime()
    finally:
        os.close(root_fd)


def _verify_stage_zero() -> None:
    flags = sys.flags
    if (
        SOURCE_ROOT != OWNER_REPOSITORY_ROOT
        or Path(os.path.abspath(__file__)) != OWNER_CLI_PATH
        or sys.executable != OWNER_PYTHON
        or sys.version_info[:3] != (3, 14, 6)
        or flags.isolated != 1
        or flags.ignore_environment != 1
        or flags.no_user_site != 1
        or flags.no_site != 1
        or flags.dont_write_bytecode != 1
        or not flags.safe_path
        or os.getcwd() != OWNER_REPOSITORY_ROOT.as_posix()
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(
        OWNER_REPOSITORY_ROOT,
        safe_ancestors=True,
    )
    try:
        root = _safe_root(root_fd)
        cwd_fd = os.open(".", _DIRECTORY_FLAGS)
        try:
            cwd = _safe_root(cwd_fd)
            if (root.st_dev, root.st_ino) != (cwd.st_dev, cwd.st_ino):
                _fail_runtime()
        finally:
            os.close(cwd_fd)
    finally:
        os.close(root_fd)


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__package__ = name
    module.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
    return module


def _load_verified_modules(sources: dict[str, bytes]) -> dict[str, types.ModuleType]:
    for name in (
        "raos",
        "raos.domain",
        "raos.domain.editorial",
        "raos.ports",
        "raos.application",
        "raos.application.editorial",
        "raos.adapters",
    ):
        _package(name)
    loaded: dict[str, types.ModuleType] = {}
    for module_name, relative in _MODULE_PATHS:
        raw = sources.get(relative)
        if type(raw) is not bytes:
            _fail_runtime()
        module = types.ModuleType(module_name)
        module.__file__ = (OWNER_REPOSITORY_ROOT / relative).as_posix()
        module.__package__ = module_name.rsplit(".", 1)[0]
        sys.modules[module_name] = module
        parent_name, child_name = module_name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
        try:
            code = compile(raw, module.__file__, "exec", dont_inherit=True)
            exec(code, module.__dict__)
        except Exception:
            _fail_runtime()
        loaded[module_name] = module
    return loaded


def _execute(
    command: str,
    sources: dict[str, bytes],
    root_identity: RootIdentity,
) -> dict[str, object]:
    if (
        type(root_identity) is not tuple
        or len(root_identity) != 2
        or any(type(value) is not int or value < 0 for value in root_identity)
    ):
        _fail_runtime()
    modules = _load_verified_modules(sources)
    domain = modules["raos.domain.editorial.owner_local_pilot"]
    adapter = modules["raos.adapters.owner_local_pilot_json"]
    application = modules["raos.application.editorial.owner_local_pilot"]
    if (
        getattr(domain, "PILOT_POLICY", None) != EXPECTED_POLICY
        or getattr(domain, "LEDGER_SCHEMA", None)
        != "ST1704_OWNER_LOCAL_PILOT_LEDGER_V1"
        or getattr(domain, "OBSERVATION_SCHEMA", None)
        != "ST1704_OWNER_LOCAL_PILOT_OBSERVATION_V1"
    ):
        _fail_runtime()
    failure_type = getattr(domain, "PilotFailure", None)
    try:
        store_type = getattr(adapter, "OwnerLocalPilotJsonStore")
        service_type = getattr(application, "OwnerLocalPilotService")
        store = store_type(
            OWNER_REPOSITORY_ROOT,
            expected_root_identity=root_identity,
        )
        service = service_type(store=store, observation_input=store)
        if command == "doctor":
            raw_result: object = service.doctor()
        elif command == "init":
            raw_result = service.initialize()
        elif command == "record":
            raw_result = service.record()
        else:
            raw_result = service.report()
    except Exception as error:
        if isinstance(failure_type, type) and isinstance(error, failure_type):
            code_value = getattr(getattr(error, "code", None), "value", None)
            if type(code_value) is str and code_value in _PILOT_FAILURE_CODES:
                raise _CommandFailure(code_value) from None
        raise
    if type(raw_result) is not dict:
        _fail_runtime()
    return cast(dict[str, object], raw_result)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv if argv is None else argv
    if (
        type(arguments) is not list
        or len(arguments) != 2
        or type(arguments[1]) is not str
        or arguments[1] not in COMMANDS
    ):
        print(
            _render(
                {
                    "code": "OWNER_LOCAL_PILOT_COMMAND_INVALID",
                    "status": "REFUSED",
                }
            )
        )
        return 2
    try:
        _verify_stage_zero()
        sources, root_identity = _verify_runtime_integrity(OWNER_REPOSITORY_ROOT)
        result = _execute(arguments[1], sources, root_identity)
    except _RuntimeFailure:
        print(
            _render(
                {
                    "code": "OWNER_LOCAL_PILOT_RUNTIME_INVALID",
                    "status": "REFUSED",
                }
            )
        )
        return 2
    except _CommandFailure as error:
        print(_render({"code": str(error), "status": "REFUSED"}))
        return 2
    except Exception:
        print(
            _render(
                {
                    "code": "OWNER_LOCAL_PILOT_INTERNAL_FAILURE",
                    "status": "REFUSED",
                }
            )
        )
        return 2
    print(_render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
