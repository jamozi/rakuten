from __future__ import annotations

import importlib.util
from pathlib import Path
import stat


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/minimum_start_readiness.py"
SPEC = importlib.util.spec_from_file_location("minimum_start_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _runtime(root: Path) -> None:
    for relative in MODULE._WORDPRESS_RUNTIME_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime\n", encoding="utf-8")


def _secrets(root: Path) -> Path:
    secret_root = root / MODULE._WORDPRESS_SECRET_ROOT
    secret_root.mkdir(parents=True, mode=0o700)
    secret_root.chmod(0o700)
    for name in MODULE._WORDPRESS_SECRET_FILES:
        path = secret_root / name
        path.write_text("must-not-be-read\n", encoding="ascii")
        path.chmod(0o600)
    return secret_root


def _rakuten(root: Path) -> None:
    for relative in MODULE._RAKUTEN_LIVE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime\n", encoding="utf-8")


def test_complete_metadata_is_ready_and_aws_is_not_required(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    _rakuten(tmp_path)

    receipt = MODULE.evaluate(tmp_path)

    assert receipt["status"] == "READY"
    assert receipt["components"]["aws"] == {
        "status": "NOT_REQUIRED",
        "reason_codes": ["MINIMUM_START_NO_AWS"],
    }
    assert receipt["network_request_count"] == 0
    assert receipt["secret_value_read_count"] == 0
    assert receipt["external_write_count"] == 0
    assert receipt["publication_action_count"] == 0


def test_missing_rakuten_live_boundary_blocks_without_affecting_wordpress(
    tmp_path: Path,
) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)

    receipt = MODULE.evaluate(tmp_path)

    assert receipt["status"] == "BLOCKED"
    assert receipt["components"]["wordpress_runtime"]["status"] == "READY"
    assert receipt["components"]["wordpress_credentials"]["status"] == "READY"
    assert receipt["components"]["rakuten_live"]["reason_codes"] == [
        "RAKUTEN_LIVE_BOUNDARY_NOT_IN_MAIN"
    ]


def test_missing_wordpress_credentials_requests_oauth_setup(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _rakuten(tmp_path)

    receipt = MODULE.evaluate(tmp_path)

    assert "WORDPRESS_OAUTH_SETUP_REQUIRED" in receipt["blocking_reason_codes"]
    assert receipt["secret_value_read_count"] == 0


def test_partial_secret_store_fails_closed(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _rakuten(tmp_path)
    secret_root = tmp_path / MODULE._WORDPRESS_SECRET_ROOT
    secret_root.mkdir(parents=True, mode=0o700)
    secret_root.chmod(0o700)
    first = secret_root / MODULE._WORDPRESS_SECRET_FILES[0]
    first.write_text("opaque\n", encoding="ascii")
    first.chmod(0o600)

    receipt = MODULE.evaluate(tmp_path)

    assert receipt["status"] == "BLOCKED"
    assert "WORDPRESS_SECRET_STORE_PARTIAL" in receipt["blocking_reason_codes"]


def test_unsafe_secret_permissions_fail_closed(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _rakuten(tmp_path)
    secret_root = _secrets(tmp_path)
    (secret_root / MODULE._WORDPRESS_SECRET_FILES[1]).chmod(0o644)

    receipt = MODULE.evaluate(tmp_path)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]


def test_symlinked_runtime_file_is_rejected(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    _rakuten(tmp_path)
    target = tmp_path / "target"
    target.write_text("runtime\n", encoding="utf-8")
    runtime = tmp_path / MODULE._WORDPRESS_RUNTIME_FILES[0]
    runtime.unlink()
    runtime.symlink_to(target)

    receipt = MODULE.evaluate(tmp_path)

    assert "WORDPRESS_RUNTIME_INCOMPLETE" in receipt["blocking_reason_codes"]


def test_secret_metadata_check_does_not_open_secret_values(
    tmp_path: Path, monkeypatch
) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    _rakuten(tmp_path)

    original_open = Path.open

    def guarded_open(path: Path, *args: object, **kwargs: object):
        if MODULE._WORDPRESS_SECRET_ROOT in path.parents:
            raise AssertionError("secret contents must never be opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    receipt = MODULE.evaluate(tmp_path)
    assert receipt["status"] == "READY"


def test_private_file_requires_owner_only_mode(tmp_path: Path) -> None:
    path = tmp_path / "secret"
    path.write_text("opaque", encoding="ascii")
    path.chmod(0o600)
    assert MODULE._private_file(path, path.stat().st_uid) is True
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    assert MODULE._private_file(path, path.stat().st_uid) is False
