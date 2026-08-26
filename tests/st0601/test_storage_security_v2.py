"""Owner-private path, mode, symlink, and hardlink defenses."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from raos.adapters.sqlite_artifact_registry_runtime_v2 import (
    RecordedSqliteArtifactRegistryFactoryV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
)

from .runtime_v2_fixtures import (
    BODY_ONE,
    factory_for,
    private_root,
    receipt_for,
    request_for,
    service_for,
)


def _assert_store_unavailable(factory: RecordedSqliteArtifactRegistryFactoryV2) -> None:
    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open()
    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE


@pytest.mark.parametrize("mode", (0o755, 0o750, 0o710, 0o777))
def test_private_root_requires_exact_owner_only_mode(tmp_path: Path, mode: int) -> None:
    root = private_root(tmp_path)
    root.chmod(mode)

    _assert_store_unavailable(factory_for(root))


def test_relative_private_root_is_rejected(tmp_path: Path) -> None:
    del tmp_path
    factory = RecordedSqliteArtifactRegistryFactoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=Path("relative-owner-private"),
    )

    _assert_store_unavailable(factory)


def test_symlink_private_root_is_rejected(tmp_path: Path) -> None:
    real = private_root(tmp_path, name="real")
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)

    _assert_store_unavailable(factory_for(link))


def test_symlink_ancestor_component_is_rejected(tmp_path: Path) -> None:
    real_parent = private_root(tmp_path, name="real-parent")
    child = real_parent / "child"
    child.mkdir(mode=0o700)
    child.chmod(0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    _assert_store_unavailable(factory_for(linked_parent / "child"))


def test_database_requires_exact_mode_and_single_link(tmp_path: Path) -> None:
    receipt = receipt_for()
    root = private_root(tmp_path)
    service, factory = service_for(root, (receipt, BODY_ONE))
    service.register(request_for(receipt))
    database = factory.database_path

    database.chmod(0o640)
    _assert_store_unavailable(factory)
    database.chmod(0o600)
    hardlink = root / "unexpected-hardlink.sqlite3"
    os.link(database, hardlink)
    _assert_store_unavailable(factory)


def test_database_symlink_replacement_is_rejected_by_open_store(
    tmp_path: Path,
) -> None:
    receipt = receipt_for()
    root = private_root(tmp_path)
    service, factory = service_for(root, (receipt, BODY_ONE))
    service.register(request_for(receipt))
    store = factory.open()
    database = factory.database_path
    original = root / "original.sqlite3"
    database.rename(original)
    database.symlink_to(original)

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        store.verify_chain()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE


def test_production_environment_is_unrepresentable_and_creates_no_database(
    tmp_path: Path,
) -> None:
    root = private_root(tmp_path)
    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        RecordedSqliteArtifactRegistryFactoryV2(
            environment=RuntimeEnvironment.PRODUCTION,
            private_root=root,
        )

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
    assert tuple(root.iterdir()) == ()


def test_success_leaves_only_one_owner_private_database(tmp_path: Path) -> None:
    receipt = receipt_for()
    root = private_root(tmp_path)
    service, factory = service_for(root, (receipt, BODY_ONE))
    service.register(request_for(receipt))

    assert tuple(path.name for path in root.iterdir()) == (factory.database_path.name,)
    assert factory.database_path.stat().st_nlink == 1
    assert factory.database_path.stat().st_uid == os.getuid()
