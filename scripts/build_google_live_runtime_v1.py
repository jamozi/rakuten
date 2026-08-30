#!/usr/bin/env python3
"""Generate the closed runtime inventory for owner-private GSC/GA4 imports."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import stat
import sys
from typing import TYPE_CHECKING, Final, NoReturn


if TYPE_CHECKING:
    from scripts import build_st0301_migration_framework as migration_owner  # noqa: F401


ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.raos_build_core import atomic_write, canonical_json_bytes  # noqa: E402


GENERATOR_PATH: Final = Path("scripts/build_google_live_runtime_v1.py")
OUTPUT_PATH: Final = Path("changes/analytics-google-live-v1/runtime-manifest.v1.json")
RUNTIME_INPUT_PATHS: Final = (
    Path("migrations/versions/202608300001_google_analytics_live_persistence.py"),
    Path("python/raos/adapters/google_live.py"),
    Path("python/raos/adapters/google_live_database.py"),
    Path("python/raos/adapters/persistence/sqlalchemy/google_live.py"),
    Path("python/raos/application/analytics/google_live_import.py"),
    Path("python/raos/application/analytics/google_live_projection.py"),
    Path("python/raos/domain/analytics/google_live.py"),
    Path("python/raos/ports/google_live.py"),
    Path("python/raos/migrations/catalog.py"),
    Path("scripts/raos_editorial_economics_v3.py"),
    Path("scripts/raos_wordpress_seo_audit.py"),
    GENERATOR_PATH,
)
TEST_PATHS: Final = (Path("tests/google_live"),)
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024


class GoogleLiveRuntimeBuildFailure(RuntimeError):
    """Stable build failure without source or owner-private values."""


def _fail(code: str) -> NoReturn:
    raise GoogleLiveRuntimeBuildFailure(code) from None


def _read(relative: Path) -> bytes:
    path = ROOT / relative
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _fail("RAOS_GOOGLE_LIVE_RUNTIME_SOURCE_UNAVAILABLE")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 1 <= len(payload) <= MAX_SOURCE_BYTES
        or len(payload) != metadata.st_size
    ):
        _fail("RAOS_GOOGLE_LIVE_RUNTIME_SOURCE_INVALID")
    return payload


def document() -> dict[str, object]:
    files: list[dict[str, object]] = []
    for relative in RUNTIME_INPUT_PATHS:
        payload = _read(relative)
        files.append(
            {
                "path": relative.as_posix(),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return {
        "schema": "RAOS_GOOGLE_LIVE_RUNTIME_MANIFEST_V1",
        "version": "1.0.0",
        "revision": "202608300001",
        "provider_mode": "OWNER_PRIVATE_READ_ONLY",
        "credential_material_tracked": False,
        "raw_gsc_queries_tracked": False,
        "recorded_adapters_retained_for_tests": True,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        payload = canonical_json_bytes(document())
        if arguments.check:
            if _read(OUTPUT_PATH) != payload:
                _fail("RAOS_GOOGLE_LIVE_RUNTIME_MANIFEST_DRIFT")
        else:
            atomic_write(OUTPUT_PATH, payload, root=ROOT)
        return 0
    except GoogleLiveRuntimeBuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
