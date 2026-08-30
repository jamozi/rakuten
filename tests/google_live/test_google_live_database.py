from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import pickle
from typing import Any, cast

import pytest
from sqlalchemy.engine import Engine

from raos.adapters import google_live_database as database_adapter
from raos.adapters.google_live_database import (
    LocalGoogleAnalyticsDatabaseTarget,
    OwnerPrivateDatabaseCredentialSnapshot,
    SealedLocalGoogleAnalyticsDatabaseTarget,
    _read_owner_password,
    create_local_google_analytics_engine,
    create_sealed_local_google_analytics_engine,
    seal_owner_private_database_credential,
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


def test_owner_private_credential_snapshot_is_immutable_redacted_and_unpicklable(
) -> None:
    snapshot = seal_owner_private_database_credential(b"fixture-value\n")
    target = SealedLocalGoogleAnalyticsDatabaseTarget(
        host="127.0.0.1",
        port=5432,
        database="raos",
        user="raos_worker",
        credential=snapshot,
    )

    assert type(snapshot) is OwnerPrivateDatabaseCredentialSnapshot
    assert "fixture-value" not in repr(snapshot)
    assert "fixture-value" not in repr(target)
    with pytest.raises(AttributeError, match="immutable"):
        snapshot._value = "changed-fixture"  # type: ignore[misc]
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(snapshot)
    with pytest.raises(TypeError, match="dataclass instances"):
        asdict(snapshot)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="dataclass instances"):
        asdict(target)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(target)


def test_sealed_engine_consumes_snapshot_without_reopening_replaced_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _password(tmp_path)
    snapshot = seal_owner_private_database_credential(path.read_bytes())
    target = SealedLocalGoogleAnalyticsDatabaseTarget(
        host="127.0.0.1",
        port=5432,
        database="raos",
        user="raos_worker",
        credential=snapshot,
    )
    creators: list[Any] = []
    engine_marker = object()

    def fake_create_engine(_url: object, **options: object) -> Engine:
        creators.append(options["creator"])
        assert options["hide_parameters"] is True
        return cast(Engine, engine_marker)

    monkeypatch.setattr(database_adapter.sa, "create_engine", fake_create_engine)
    engine = create_sealed_local_google_analytics_engine(target)
    assert engine is engine_marker
    assert len(creators) == 1

    path.rename(tmp_path / "original-credential.txt")
    path.write_bytes(b"changed-fixture\n")
    path.chmod(0o600)
    observed: dict[str, object] = {}
    connection_marker = object()

    def fake_connect(**options: object) -> object:
        observed.update(options)
        return connection_marker

    monkeypatch.setattr(database_adapter.psycopg, "connect", fake_connect)
    assert creators[0]() is connection_marker
    db_value = observed["password"]
    assert type(db_value) is str
    assert db_value.encode("utf-8") == b"fixture-value"


def test_sealed_engine_rejects_unsealed_target(tmp_path: Path) -> None:
    path = _password(tmp_path)
    unsealed = LocalGoogleAnalyticsDatabaseTarget(
        host="127.0.0.1",
        port=5432,
        database="raos",
        user="raos_worker",
        password_file=path,
    )

    with pytest.raises(GoogleProviderFailure):
        create_sealed_local_google_analytics_engine(unsealed)  # type: ignore[arg-type]


def test_sealed_engine_rejects_ambient_postgres_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = seal_owner_private_database_credential(b"fixture-value\n")
    target = SealedLocalGoogleAnalyticsDatabaseTarget(
        host="127.0.0.1",
        port=5432,
        database="raos",
        user="raos_worker",
        credential=snapshot,
    )
    monkeypatch.setenv("PGHOST", "unexpected")

    with pytest.raises(GoogleProviderFailure):
        create_sealed_local_google_analytics_engine(target)
    with pytest.raises(GoogleProviderFailure):
        snapshot.connect_local_database(
            host="127.0.0.1",
            port=5432,
            database="raos",
            user="raos_worker",
        )
