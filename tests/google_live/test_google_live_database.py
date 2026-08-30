from __future__ import annotations

import os
from pathlib import Path

import pytest

from raos.adapters.google_live_database import (
    LocalGoogleAnalyticsDatabaseTarget,
    _read_owner_password,
    create_local_google_analytics_engine,
)
from raos.domain.analytics.google_live import GoogleProviderFailure


def _password(tmp_path: Path) -> Path:
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "postgres-password.txt"
    path.write_text("fixture-value\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def test_local_database_target_rejects_remote_or_ambient_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _password(tmp_path)
    with pytest.raises(GoogleProviderFailure):
        LocalGoogleAnalyticsDatabaseTarget(
            host="db.example.invalid",
            port=5432,
            database="raos",
            user="raos_worker",
            password_file=path,
        )

    target = LocalGoogleAnalyticsDatabaseTarget(
        host="127.0.0.1",
        port=5432,
        database="raos",
        user="raos_worker",
        password_file=path,
    )
    monkeypatch.setenv("PGHOST", "unexpected")
    with pytest.raises(GoogleProviderFailure):
        create_local_google_analytics_engine(target)


def test_password_reader_requires_owner_0600_file_in_0700_directory(
    tmp_path: Path,
) -> None:
    path = _password(tmp_path)
    assert _read_owner_password(path) == "fixture-value"
    assert "fixture-value" not in repr(
        LocalGoogleAnalyticsDatabaseTarget(
            host="127.0.0.1",
            port=5432,
            database="raos",
            user="raos_worker",
            password_file=path,
        )
    )

    os.chmod(path, 0o644)
    with pytest.raises(GoogleProviderFailure):
        _read_owner_password(path)
