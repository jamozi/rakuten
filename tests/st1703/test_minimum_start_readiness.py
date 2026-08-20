from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat

import pytest


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


def _secret_root(root: Path) -> Path:
    secret_parent = root / MODULE._WORDPRESS_SECRET_PARENT
    secret_parent.mkdir(parents=True, mode=0o700)
    secret_parent.chmod(0o700)
    secret_root = root / MODULE._WORDPRESS_SECRET_ROOT
    secret_root.mkdir(mode=0o700)
    secret_root.chmod(0o700)
    return secret_root


def _secrets(root: Path) -> Path:
    secret_root = _secret_root(root)
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


def test_exact_expected_root_with_wordpress_metadata_is_ready(
    tmp_path: Path,
) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert receipt["status"] == "READY"
    assert receipt["components"]["aws"] == {
        "status": "NOT_REQUIRED",
        "reason_codes": ["MINIMUM_START_NO_AWS"],
    }
    assert receipt["components"]["rakuten_live"] == {
        "status": "POST_LAUNCH_OPTIONAL",
        "reason_codes": ["RAKUTEN_LIVE_NOT_REQUIRED_FOR_FIRST_DRAFT"],
    }
    assert receipt["network_request_count"] == 0
    assert receipt["secret_value_read_count"] == 0
    assert receipt["external_write_count"] == 0
    assert receipt["publication_action_count"] == 0
    assert receipt["next_commands"] == ["make wordpresscom-preview-mvp"]


def test_repository_root_mismatch_is_a_value_free_blocker(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)

    receipt = MODULE.evaluate(
        tmp_path,
        expected_root=tmp_path / "different-root",
    )

    assert receipt["status"] == "BLOCKED"
    assert receipt["blocking_reason_codes"] == ["WORDPRESS_REPOSITORY_ROOT_INVALID"]
    assert receipt["components"]["wordpress_credentials"] == {
        "status": "BLOCKED",
        "reason_codes": ["WORDPRESS_REPOSITORY_ROOT_INVALID"],
    }
    assert receipt["components"]["wordpress_runtime"] == {
        "status": "BLOCKED",
        "reason_codes": ["WORDPRESS_REPOSITORY_ROOT_INVALID"],
    }
    assert receipt["network_request_count"] == 0
    assert receipt["secret_value_read_count"] == 0
    assert receipt["external_write_count"] == 0
    assert receipt["publication_action_count"] == 0
    assert receipt["next_commands"] == []


def test_main_binds_readiness_to_the_exact_production_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_evaluate(
        root: Path, *, expected_root: Path, uid: int | None = None
    ) -> dict[str, object]:
        captured["root"] = root
        captured["expected_root"] = expected_root
        captured["uid"] = uid
        return {"status": "BLOCKED"}

    monkeypatch.setattr(MODULE, "evaluate", fake_evaluate)

    assert MODULE.main() == 2
    assert captured == {
        "root": MODULE.REPOSITORY_ROOT,
        "expected_root": MODULE._EXPECTED_REPOSITORY_ROOT,
        "uid": None,
    }
    assert capsys.readouterr().out == '{"status":"BLOCKED"}\n'


def test_integrated_rakuten_live_boundary_is_available_but_gated(
    tmp_path: Path,
) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    _rakuten(tmp_path)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert receipt["status"] == "READY"
    assert receipt["components"]["rakuten_live"] == {
        "status": "AVAILABLE_GATED",
        "reason_codes": ["RAKUTEN_LIVE_EXECUTION_REQUIRES_SEPARATE_AUTHORITY"],
    }


def test_missing_wordpress_credentials_requests_oauth_setup(tmp_path: Path) -> None:
    _runtime(tmp_path)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_OAUTH_SETUP_REQUIRED" in receipt["blocking_reason_codes"]
    assert receipt["secret_value_read_count"] == 0
    assert receipt["next_commands"] == ["make wordpresscom-oauth-setup"]


def test_partial_secret_store_fails_closed(tmp_path: Path) -> None:
    _runtime(tmp_path)
    secret_root = _secret_root(tmp_path)
    first = secret_root / MODULE._WORDPRESS_SECRET_FILES[0]
    first.write_text("opaque\n", encoding="ascii")
    first.chmod(0o600)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert receipt["status"] == "BLOCKED"
    assert "WORDPRESS_SECRET_STORE_PARTIAL" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


def test_unsafe_secret_permissions_fail_closed(tmp_path: Path) -> None:
    _runtime(tmp_path)
    secret_root = _secrets(tmp_path)
    (secret_root / MODULE._WORDPRESS_SECRET_FILES[1]).chmod(0o644)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


@pytest.mark.parametrize(
    "relative",
    [MODULE._WORDPRESS_SECRET_PARENT, MODULE._WORDPRESS_SECRET_ROOT],
)
def test_unsafe_secret_directory_permissions_fail_closed(
    tmp_path: Path, relative: Path
) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    (tmp_path / relative).chmod(0o755)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


@pytest.mark.parametrize(
    "relative",
    [MODULE._WORDPRESS_SECRET_PARENT, MODULE._WORDPRESS_SECRET_ROOT],
)
def test_secret_directories_wrong_owner_fail_closed_without_privilege_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: Path
) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    wrong_owner_path = tmp_path / relative
    original_lstat = Path.lstat

    def wrong_owner_lstat(path: Path) -> os.stat_result:
        metadata = original_lstat(path)
        if path == wrong_owner_path:
            fields = list(metadata)
            fields[4] = metadata.st_uid + 1
            return os.stat_result(fields)
        return metadata

    monkeypatch.setattr(Path, "lstat", wrong_owner_lstat)
    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


@pytest.mark.parametrize("size", [0, MODULE._WORDPRESS_SECRET_FILE_MAX_BYTES + 1])
def test_empty_or_oversized_secret_file_fails_closed(tmp_path: Path, size: int) -> None:
    _runtime(tmp_path)
    secret_root = _secrets(tmp_path)
    path = secret_root / MODULE._WORDPRESS_SECRET_FILES[1]
    path.write_bytes(b"x" * size)
    path.chmod(0o600)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["secret_value_read_count"] == 0
    assert receipt["next_commands"] == []


def test_symlinked_runtime_file_is_rejected(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)
    target = tmp_path / "target"
    target.write_text("runtime\n", encoding="utf-8")
    runtime = tmp_path / MODULE._WORDPRESS_RUNTIME_FILES[0]
    runtime.unlink()
    runtime.symlink_to(target)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_RUNTIME_INCOMPLETE" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


def test_symlinked_runtime_ancestor_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _runtime(repository)
    _secrets(repository)
    outside_scripts = tmp_path / "outside-scripts"
    (repository / "scripts").rename(outside_scripts)
    (repository / "scripts").symlink_to(outside_scripts, target_is_directory=True)

    receipt = MODULE.evaluate(repository, expected_root=repository)

    assert receipt["components"]["wordpress_runtime"] == {
        "status": "BLOCKED",
        "reason_codes": ["WORDPRESS_RUNTIME_INCOMPLETE"],
    }
    assert receipt["network_request_count"] == 0
    assert receipt["secret_value_read_count"] == 0
    assert receipt["external_write_count"] == 0
    assert receipt["publication_action_count"] == 0
    assert receipt["next_commands"] == []


def test_symlinked_repository_root_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    _runtime(real_root)
    _secrets(real_root)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)

    receipt = MODULE.evaluate(linked_root, expected_root=linked_root)

    assert receipt["status"] == "BLOCKED"
    assert receipt["blocking_reason_codes"] == ["WORDPRESS_REPOSITORY_ROOT_INVALID"]
    assert receipt["next_commands"] == []


def test_repository_root_requires_expected_owner(tmp_path: Path) -> None:
    _runtime(tmp_path)
    _secrets(tmp_path)

    receipt = MODULE.evaluate(
        tmp_path,
        expected_root=tmp_path,
        uid=tmp_path.stat().st_uid + 1,
    )

    assert receipt["status"] == "BLOCKED"
    assert receipt["blocking_reason_codes"] == ["WORDPRESS_REPOSITORY_ROOT_INVALID"]
    assert receipt["next_commands"] == []


def test_symlinked_secret_parent_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _runtime(repository)
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    real_secret_parent = real_root / MODULE._WORDPRESS_SECRET_PARENT
    _secrets(real_root)
    (repository / MODULE._WORDPRESS_SECRET_PARENT).symlink_to(
        real_secret_parent, target_is_directory=True
    )

    receipt = MODULE.evaluate(repository, expected_root=repository)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


def test_symlinked_secret_root_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _runtime(repository)
    secret_parent = repository / MODULE._WORDPRESS_SECRET_PARENT
    secret_parent.mkdir(mode=0o700)
    secret_parent.chmod(0o700)
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    real_secret_root = _secrets(real_root)
    (repository / MODULE._WORDPRESS_SECRET_ROOT).symlink_to(
        real_secret_root, target_is_directory=True
    )

    receipt = MODULE.evaluate(repository, expected_root=repository)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


def test_symlinked_secret_alias_is_rejected(tmp_path: Path) -> None:
    _runtime(tmp_path)
    secret_root = _secrets(tmp_path)
    alias = secret_root / MODULE._WORDPRESS_SECRET_FILES[0]
    alias.unlink()
    target = tmp_path / "outside-secret"
    target.write_text("opaque\n", encoding="ascii")
    target.chmod(0o600)
    alias.symlink_to(target)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_SECRET_STORE_INVALID" in receipt["blocking_reason_codes"]
    assert receipt["secret_value_read_count"] == 0
    assert receipt["next_commands"] == []


def test_runtime_incomplete_suppresses_external_next_commands(
    tmp_path: Path,
) -> None:
    _secrets(tmp_path)

    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)

    assert "WORDPRESS_RUNTIME_INCOMPLETE" in receipt["blocking_reason_codes"]
    assert receipt["next_commands"] == []


def test_secret_metadata_check_does_not_open_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _runtime(tmp_path)
    secret_root = _secrets(tmp_path)

    original_open = Path.open
    original_os_open = os.open

    def guarded_open(path: Path, *args: object, **kwargs: object):
        if path == secret_root or secret_root in path.parents:
            raise AssertionError("secret contents must never be opened")
        return original_open(path, *args, **kwargs)

    def guarded_os_open(
        path: str | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        candidate = Path(path)
        if candidate == secret_root or secret_root in candidate.parents:
            raise AssertionError("secret contents must never be opened")
        return original_os_open(path, flags, mode)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    receipt = MODULE.evaluate(tmp_path, expected_root=tmp_path)
    assert receipt["status"] == "READY"
    assert receipt["secret_value_read_count"] == 0
    assert receipt["next_commands"] == ["make wordpresscom-preview-mvp"]


def test_private_file_requires_owner_only_mode(tmp_path: Path) -> None:
    path = tmp_path / "secret"
    path.write_text("opaque", encoding="ascii")
    path.chmod(0o600)
    assert MODULE._private_file(path, path.stat().st_uid) is True
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    assert MODULE._private_file(path, path.stat().st_uid) is False


def test_private_file_requires_expected_owner(tmp_path: Path) -> None:
    path = tmp_path / "secret"
    path.write_text("opaque", encoding="ascii")
    path.chmod(0o600)

    assert MODULE._private_file(path, path.stat().st_uid + 1) is False
