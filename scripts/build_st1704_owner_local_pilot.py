#!/usr/bin/env python3
"""Generate/check ST-1704 owner-local pilot policy and runtime manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Final, NoReturn


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE_ROOT: Final = ROOT / "changes/st-1704/owner-local-pilot-v1"
POLICY_PATH: Final = SLICE_ROOT / "pilot-policy.v1.json"
MANIFEST_PATH: Final = SLICE_ROOT / "runtime-manifest.v1.json"
POLICY: Final = {
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
RUNTIME_PATHS: Final = (
    "changes/st-1704/owner-local-pilot-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1704/owner-local-pilot-v1/Makefile",
    "changes/st-1704/owner-local-pilot-v1/PREFLIGHT.md",
    "changes/st-1704/owner-local-pilot-v1/README.md",
    "changes/st-1704/owner-local-pilot-v1/examples/bootstrap-first-publication.v1.json",
    "changes/st-1704/owner-local-pilot-v1/pilot-policy.v1.json",
    "python/raos/adapters/owner_local_pilot_json.py",
    "python/raos/application/editorial/owner_local_pilot.py",
    "python/raos/domain/editorial/owner_local_pilot.py",
    "python/raos/ports/owner_local_pilot.py",
    "scripts/build_st1704_owner_local_pilot.py",
    "scripts/st1704_owner_local_pilot.py",
)


class BuildFailure(RuntimeError):
    pass


def _fail() -> NoReturn:
    raise BuildFailure("ST1704_OWNER_LOCAL_PILOT_BUILD_INVALID") from None


def _render(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _read(path: Path) -> bytes:
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > 2 * 1024 * 1024
        ):
            _fail()
        raw = path.read_bytes()
        after = path.lstat()
    except OSError:
        _fail()
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
    ) or len(raw) != before.st_size:
        _fail()
    return raw


def _manifest() -> bytes:
    entries = []
    for relative in RUNTIME_PATHS:
        raw = _read(ROOT / relative)
        entries.append(
            {
                "bytes": len(raw),
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return _render(
        {
            "external_action_authority": "NONE",
            "generated_by": "scripts/build_st1704_owner_local_pilot.py",
            "paths": entries,
            "schema": "ST1704_OWNER_LOCAL_PILOT_RUNTIME_MANIFEST_V1",
            "slice_id": "ST1704_OWNER_LOCAL_PILOT_LEDGER_V1",
            "story_id": "ST-1704",
        }
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    stage = path.with_name(f".{path.name}.preparing")
    try:
        fd = os.open(
            stage,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    _fail()
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(stage, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        _fail()


def generate(*, check: bool) -> None:
    policy = _render(
        {
            "generated_by": "scripts/build_st1704_owner_local_pilot.py",
            "policy": POLICY,
            "schema": "ST1704_OWNER_LOCAL_PILOT_POLICY_V1",
        }
    )
    if check:
        if _read(POLICY_PATH) != policy or _read(MANIFEST_PATH) != _manifest():
            _fail()
        return
    _atomic_write(POLICY_PATH, policy)
    _atomic_write(MANIFEST_PATH, _manifest())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        generate(check=arguments.check)
    except BuildFailure as error:
        print(str(error))
        return 2
    print("ST1704_OWNER_LOCAL_PILOT_BUILD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
