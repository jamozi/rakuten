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
_EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")

_WORDPRESS_RUNTIME_FILES: Final = (
    "scripts/wordpresscom_review_draft.py",
    "scripts/wordpresscom_review_draft_python.sh",
    "changes/st-1703/wordpresscom-mvp-draft-preparation.wave3.runtime-manifest.v1.json",
    "changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml",
    "python/raos/adapters/wordpresscom_mvp_draft_https.py",
    "python/raos/adapters/wordpresscom_mvp_draft_journal.py",
    "python/raos/adapters/wordpresscom_oauth.py",
)
_WORDPRESS_SECRET_PARENT: Final = Path(".secrets")
_WORDPRESS_SECRET_ROOT: Final = Path(".secrets/wordpresscom-review-draft")
_WORDPRESS_SECRET_FILES: Final = (
    "wordpresscom_oauth_client_id",
    "wordpresscom_oauth_client_secret",
    "wordpresscom_oauth_access_token",
)
_WORDPRESS_SECRET_FILE_MAX_BYTES: Final = 4097
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


def _nonsymlink_ancestors(path: Path) -> bool:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(metadata.st_mode):
            return False
        if current.parent == current:
            return True
        current = current.parent


def _safe_repository_root(path: Path, uid: int) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return bool(
        path.is_absolute()
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == uid
        and _nonsymlink_ancestors(path)
    )


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
        and 1 <= metadata.st_size <= _WORDPRESS_SECRET_FILE_MAX_BYTES
    )


def _wordpress_runtime(root: Path) -> tuple[str, tuple[str, ...]]:
    missing = tuple(
        relative
        for relative in _WORDPRESS_RUNTIME_FILES
        if not _regular_nonsymlink(root / relative)
        or not _nonsymlink_ancestors((root / relative).parent)
    )
    if missing:
        return "BLOCKED", ("WORDPRESS_RUNTIME_INCOMPLETE",)
    return "READY", ()


def _wordpress_credentials(root: Path, uid: int) -> tuple[str, tuple[str, ...]]:
    secret_parent = root / _WORDPRESS_SECRET_PARENT
    try:
        secret_parent.lstat()
    except FileNotFoundError:
        return "BLOCKED", ("WORDPRESS_OAUTH_SETUP_REQUIRED",)
    except OSError:
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)
    if not _nonsymlink_ancestors(secret_parent) or not _private_directory(
        secret_parent, uid
    ):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)

    secret_root = root / _WORDPRESS_SECRET_ROOT
    try:
        secret_root.lstat()
    except FileNotFoundError:
        return "BLOCKED", ("WORDPRESS_OAUTH_SETUP_REQUIRED",)
    except OSError:
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)
    if not _nonsymlink_ancestors(secret_root) or not _private_directory(
        secret_root, uid
    ):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)

    presence: list[bool] = []
    for name in _WORDPRESS_SECRET_FILES:
        try:
            (secret_root / name).lstat()
        except FileNotFoundError:
            presence.append(False)
        except OSError:
            return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)
        else:
            presence.append(True)
    if not any(presence):
        return "BLOCKED", ("WORDPRESS_OAUTH_SETUP_REQUIRED",)
    if not all(presence):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_PARTIAL",)
    if not all(
        _private_file(secret_root / name, uid) for name in _WORDPRESS_SECRET_FILES
    ):
        return "BLOCKED", ("WORDPRESS_SECRET_STORE_INVALID",)
    return "READY", ()


def _next_commands(
    *,
    wordpress_runtime: str,
    wordpress_credentials: str,
    wordpress_credential_reasons: tuple[str, ...],
) -> list[str]:
    if wordpress_runtime != "READY":
        return []
    if wordpress_credentials == "READY":
        return ["make wordpresscom-preview-mvp"]
    if wordpress_credential_reasons == ("WORDPRESS_OAUTH_SETUP_REQUIRED",):
        return ["make wordpresscom-oauth-setup"]
    return []


def _rakuten_runtime(root: Path) -> tuple[str, tuple[str, ...]]:
    if not all(
        _regular_nonsymlink(root / relative) for relative in _RAKUTEN_LIVE_FILES
    ):
        return "POST_LAUNCH_OPTIONAL", ("RAKUTEN_LIVE_NOT_REQUIRED_FOR_FIRST_DRAFT",)
    return "AVAILABLE_GATED", ("RAKUTEN_LIVE_EXECUTION_REQUIRES_SEPARATE_AUTHORITY",)


def evaluate(
    root: Path, *, expected_root: Path, uid: int | None = None
) -> dict[str, object]:
    """Return a value-free readiness receipt without reading credential bytes."""

    exact_root = Path(os.path.abspath(root))
    exact_expected_root = Path(os.path.abspath(expected_root))
    owner = os.geteuid() if uid is None else uid
    if exact_root == exact_expected_root and _safe_repository_root(exact_root, owner):
        wordpress_runtime, wordpress_runtime_reasons = _wordpress_runtime(exact_root)
        wordpress_credentials, wordpress_credential_reasons = _wordpress_credentials(
            exact_root, owner
        )
        rakuten_runtime, rakuten_reasons = _rakuten_runtime(exact_root)
    else:
        wordpress_runtime, wordpress_runtime_reasons = (
            "BLOCKED",
            ("WORDPRESS_REPOSITORY_ROOT_INVALID",),
        )
        wordpress_credentials, wordpress_credential_reasons = (
            "BLOCKED",
            ("WORDPRESS_REPOSITORY_ROOT_INVALID",),
        )
        rakuten_runtime, rakuten_reasons = (
            "POST_LAUNCH_OPTIONAL",
            ("RAKUTEN_LIVE_NOT_REQUIRED_FOR_FIRST_DRAFT",),
        )

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
        {
            reason
            for component in components.values()
            if component["status"] == "BLOCKED"
            for reason in component["reason_codes"]
        }
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
        "next_commands": _next_commands(
            wordpress_runtime=wordpress_runtime,
            wordpress_credentials=wordpress_credentials,
            wordpress_credential_reasons=wordpress_credential_reasons,
        ),
    }


def main() -> int:
    receipt = evaluate(
        REPOSITORY_ROOT,
        expected_root=_EXPECTED_REPOSITORY_ROOT,
    )
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
