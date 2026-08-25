#!/usr/bin/env python3
"""Fixed-command launcher for the owner-private ST-1704 learning ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import NoReturn, cast


_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _ROOT / "changes/st-1704/affiliate-learning-v2/runtime-manifest.v2.json"
_CONTRACT = _ROOT / "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
_EXPECTED_SOURCES = frozenset(
    {
        "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json",
        "python/raos/adapters/affiliate_learning_json.py",
        "python/raos/application/editorial/affiliate_learning.py",
        "python/raos/domain/editorial/affiliate_learning.py",
        "python/raos/domain/editorial/owner_local_pilot.py",
        "python/raos/ports/affiliate_learning.py",
        "scripts/build_st1704_affiliate_learning.py",
        "scripts/st1704_affiliate_learning.py",
    }
)


class _RuntimeFailure(RuntimeError):
    pass


def _fail() -> NoReturn:
    raise _RuntimeFailure("ST1704_AFFILIATE_LEARNING_RUNTIME_INVALID") from None


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail()


def _decode(raw: bytes) -> object:
    if not raw or raw.startswith(b"\xef\xbb\xbf"):
        _fail()
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (
        _RuntimeFailure,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ):
        _fail()


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail()
    return cast(dict[str, object], value)


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
        _fail()


def _safe_read(path: Path, *, maximum: int) -> bytes:
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or path.is_symlink()
            or before.st_nlink != 1
            or not 0 < before.st_size <= maximum
        ):
            _fail()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        _fail()
    try:
        observed = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino) != (before.st_dev, before.st_ino):
            _fail()
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail()
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
            _fail()
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _verify_runtime() -> tuple[bytes, tuple[int, int]]:
    if Path.cwd().resolve() != _ROOT or any(
        name == "raos" or name.startswith("raos.") for name in sys.modules
    ):
        _fail()
    root_stat = _ROOT.stat()
    if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.getuid():
        _fail()
    manifest = _mapping(_decode(_safe_read(_MANIFEST, maximum=262_144)))
    if set(manifest) != {
        "authority",
        "contract_sha256",
        "fixtures",
        "generated_by",
        "program",
        "runtime_sources",
        "schema",
        "slice_id",
        "story_id",
    }:
        _fail()
    if (
        manifest["schema"] != "ST1704_AFFILIATE_LEARNING_RUNTIME_MANIFEST_V2"
        or manifest["story_id"] != "ST-1704"
        or manifest["slice_id"] != "AFFILIATE_LEARNING_MEASUREMENT_V2"
        or manifest["program"] != "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
        or manifest["generated_by"] != "scripts/build_st1704_affiliate_learning.py"
        or manifest["authority"]
        != {
            "analytics_activation": False,
            "external_writes": False,
            "network_requests": False,
            "publication": False,
            "recommendation_mutation": False,
            "tracking": False,
        }
    ):
        _fail()
    sources_value = manifest["runtime_sources"]
    if type(sources_value) is not list:
        _fail()
    sources = cast(list[object], sources_value)
    observed_paths: set[str] = set()
    contract_bytes: bytes | None = None
    for raw_source in sources:
        source = _mapping(raw_source)
        if set(source) != {"path", "sha256", "size"}:
            _fail()
        relative = source["path"]
        if (
            type(relative) is not str
            or relative not in _EXPECTED_SOURCES
            or relative in observed_paths
            or type(source["sha256"]) is not str
            or len(source["sha256"]) != 64
            or type(source["size"]) is not int
            or source["size"] <= 0
        ):
            _fail()
        observed_paths.add(relative)
        raw = _safe_read(_ROOT / relative, maximum=4_194_304)
        if (
            len(raw) != source["size"]
            or hashlib.sha256(raw).hexdigest() != source["sha256"]
        ):
            _fail()
        if (_ROOT / relative) == _CONTRACT:
            contract_bytes = raw
    if observed_paths != _EXPECTED_SOURCES or contract_bytes is None:
        _fail()
    contract_sha256 = hashlib.sha256(_canonical(_decode(contract_bytes))).hexdigest()
    if manifest["contract_sha256"] != contract_sha256:
        _fail()
    rebound = _ROOT.stat()
    if (rebound.st_dev, rebound.st_ino) != (root_stat.st_dev, root_stat.st_ino):
        _fail()
    return contract_bytes, (root_stat.st_dev, root_stat.st_ino)


def _execute(
    command: str, contract_bytes: bytes, root_identity: tuple[int, int]
) -> object:
    python_root = str(_ROOT / "python")
    if python_root in sys.path:
        sys.path.remove(python_root)
    sys.path.insert(0, python_root)

    from raos.adapters.affiliate_learning_json import (  # noqa: PLC0415
        AffiliateLearningJsonStore,
        decode_strict_json,
    )
    from raos.application.editorial.affiliate_learning import (  # noqa: PLC0415
        AffiliateLearningService,
    )
    from raos.domain.editorial.affiliate_learning import (  # noqa: PLC0415
        MeasurementContract,
    )

    contract = MeasurementContract.parse(decode_strict_json(contract_bytes))
    store = AffiliateLearningJsonStore(
        _ROOT,
        contract=contract,
        expected_root_identity=root_identity,
    )
    service = AffiliateLearningService(
        contract=contract,
        store=store,
        observation_input=store,
    )
    if command == "doctor":
        return service.doctor()
    if command == "init":
        return service.initialize()
    if command == "record":
        return service.record()
    if command == "report":
        return service.report()
    _fail()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("doctor", "init", "record", "report"))
    args = parser.parse_args(argv)
    try:
        contract_bytes, root_identity = _verify_runtime()
        result = _execute(cast(str, args.command), contract_bytes, root_identity)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except _RuntimeFailure as error:
        print(str(error))
        return 1
    except BaseException as error:
        code = getattr(error, "code", None)
        value = getattr(code, "value", None)
        if type(value) is str and value.isupper():
            print(value)
        else:
            print("ST1704_AFFILIATE_LEARNING_COMMAND_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
