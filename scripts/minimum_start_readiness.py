#!/usr/bin/env python3
"""Offline readiness check for the no-AWS Minimum Start path.

This command performs no network I/O and never reads credential file contents.
It only checks repository/runtime presence and owner-private credential metadata.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Final, TypedDict


SCHEMA: Final = "RAOS_MINIMUM_START_READINESS_V1"
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]

_WORDPRESS_RUNTIME_FILES: Final = (
    "scripts/wordpresscom_review_draft.py",
    "scripts/wordpresscom_review_draft_python.sh",
    "changes/st-1703/wordpresscom-mvp-draft-preparation.wave3.runtime-manifest.v1.json",
    "changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml",
    "python/raos/adapters/wordpresscom_mvp_draft_https.py",
    "python/raos/adapters/wordpresscom_mvp_draft_journal.py",
    "python/raos/adapters/wordpresscom_oauth.py",
)
_WORDPRESS_SECRET_ROOT: Final = Path(".secrets/wordpresscom-review-draft")
_WORDPRESS_SECRET_FILES: Final = (
    "wordpresscom_oauth_client_id",
    "wordpresscom_oauth_client_secret",
    "wordpresscom_oauth_access_token",
)
_RAKUTEN_LIVE_FILES: Final = (
    "python/raos/domain/catalog/rakuten_live_smoke.py",
    "python/raos/adapters/rakuten_live_smoke.py",
)


class ComponentStatus(TypedDict):
    status: str
    reason_codes: list[str]


def _regular_nonsymlink(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def _private_directory(path: Path, uid: int) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == uid
        and stat.S_IMODE(metadata.st_mode) == 0o700
    )


def _private_file(path: Path, uid: int) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == uid
        and stat.S_IMODE(metadata.st_mode) == 0o600
    )


def _wordpress_runtime(root: Path) -> tuple[str, tuple[str, ...]]:
    missing = tuple(
        relative
        for relative in _WORDPRESS_RUNTIME_FILES
        if not _regular_nonsymlink(root / relative)
    )
    if missing:
        return "BLOCKED", ("WORDPRESS_RUNTIME_INCOMPLETE",)
    return "READY", ()


def _wordpress_credentials(
    root: Path, uid: int
) -> tuple[str, tuple[str, ...]]:
    secret_root = root / _WORDPRESS_SECRET_ROOT
    if not secret_root.exists():
        return "BLOCKED", ("WORDPRESS_OAUTH_SETUP_REQUIRED",)
    if not _private_directory(secret_root, uid):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)

    presence = tuple((secret_root / name).exists() for name in _WORDPRESS_SECRET_FILES)
    if not any(presence):
        return "BLOCKED", ("WORDPRESS_OAUTH_SETUP_REQUIRED",)
    if not all(presence):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_PARTIAL",)
    if not all(
        _private_file(secret_root / name, uid) for name in _WORDPRESS_SECRET_FILES
    ):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)
    return "READY", ()


def _rakuten_runtime(root: Path) -> tuple[str, tuple[str, ...]]:
    if not all(
        _regular_nonsymlink(root / relative) for relative in _RAKUTEN_LIVE_FILES
    ):
        return "POST_LAUNCH_OPTIONAL", (
            "RAKUTEN_LIVE_NOT_REQUIRED_FOR_FIRST_DRAFT",
        )
    return "AVAILABLE_GATED", (
        "RAKUTEN_LIVE_EXECUTION_REQUIRES_SEPARATE_AUTHORITY",
    )


def evaluate(root: Path, *, uid: int | None = None) -> dict[str, object]:
    """Return a value-free readiness receipt without reading credential bytes."""

    exact_root = Path(os.path.abspath(root))
    owner = os.geteuid() if uid is None else uid
    wordpress_runtime, wordpress_runtime_reasons = _wordpress_runtime(exact_root)
    wordpress_credentials, wordpress_credential_reasons = _wordpress_credentials(
        exact_root, owner
    )
    rakuten_runtime, rakuten_reasons = _rakuten_runtime(exact_root)

    components: dict[str, ComponentStatus] = {
        "aws": {
            "status": "NOT_REQUIRED",
            "reason_codes": ["MINIMUM_START_NO_AWS"],
        },
        "rakuten_live": {
            "status": rakuten_runtime,
            "reason_codes": list(rakuten_reasons),
        },
        "wordpress_credentials": {
            "status": wordpress_credentials,
            "reason_codes": list(wordpress_credential_reasons),
        },
        "wordpress_runtime": {
            "status": wordpress_runtime,
            "reason_codes": list(wordpress_runtime_reasons),
        },
    }
    blocking = sorted(
        reason
        for component in components.values()
        if component["status"] == "BLOCKED"
        for reason in component["reason_codes"]
    )
    status = "READY" if not blocking else "BLOCKED"
    return {
        "schema": SCHEMA,
        "status": status,
        "blocking_reason_codes": blocking,
        "components": components,
        "network_request_count": 0,
        "secret_value_read_count": 0,
        "external_write_count": 0,
        "publication_action_count": 0,
        "next_commands": [
            "make wordpresscom-oauth-setup",
            "make wordpresscom-preview-mvp",
            "make wordpresscom-prepare-mvp-drafts",
        ],
    }


def main() -> int:
    receipt = evaluate(REPOSITORY_ROOT)
    print(
        json.dumps(
            receipt,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if receipt["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
