"""Checksum-pinned migration source catalog through ST-0306."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final


MAX_REVISION_BYTES: Final = 256 * 1024
MAX_CHECKPOINT_BYTES: Final = 8 * 1024 * 1024


class Direction(StrEnum):
    """Supported migration directions."""

    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"


class CatalogErrorCode(StrEnum):
    """Public catalog failure codes with no source data."""

    INVALID_CATALOG = "MIG-CATALOG-001"
    INVALID_ROOT = "MIG-CATALOG-002"
    INVALID_SOURCE = "MIG-CATALOG-003"
    SOURCE_TOO_LARGE = "MIG-CATALOG-004"
    SOURCE_DIGEST_MISMATCH = "MIG-CATALOG-005"
    SOURCE_TEXT_INVALID = "MIG-CATALOG-006"


_CATALOG_MESSAGES: Final = {
    CatalogErrorCode.INVALID_CATALOG: "migration catalog is invalid",
    CatalogErrorCode.INVALID_ROOT: "repository root is invalid",
    CatalogErrorCode.INVALID_SOURCE: "migration source is not a regular file",
    CatalogErrorCode.SOURCE_TOO_LARGE: "migration source exceeds its size limit",
    CatalogErrorCode.SOURCE_DIGEST_MISMATCH: "migration source digest does not match",
    CatalogErrorCode.SOURCE_TEXT_INVALID: "migration source is not valid text",
}


class CatalogError(RuntimeError):
    """Sanitized failure raised before any database connection is opened."""

    __slots__ = ("code",)

    def __init__(self, code: CatalogErrorCode) -> None:
        self.code = code
        super().__init__(_CATALOG_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class RevisionSpec:
    """One reviewed Alembic revision."""

    revision: str
    down_revision: str | None
    story_id: str
    relative_path: Path
    sha256: str
    runner_version: str
    server_version_num: int


@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    """One deferred, integrity-bound SQL checkpoint."""

    revision: str
    story_id: str
    phase: str
    direction: Direction
    repeatable: bool
    relative_path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeSourceSpec:
    """One executable Alembic runtime source outside the revision graph."""

    relative_path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedSource:
    """A source whose bytes were securely opened and checksum verified."""

    relative_path: Path
    sha256: str
    size: int
    content: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CatalogVerification:
    """Public-safe summary of complete offline source verification."""

    runtime_sources: tuple[VerifiedSource, ...]
    revision_sources: tuple[VerifiedSource, ...]
    checkpoint_sources: tuple[VerifiedSource, ...]
    catalog_sha256: str


ANCHOR_REVISION: Final = "202608030001"
FOUNDATION_REVISION: Final = "202608030002"
IAM_OPS_REVISION: Final = "202608030003"
DOMAIN_REVISION: Final = "202608030004"
PUBLICATION_ANALYTICS_FINANCE_REVISION: Final = "202608030005"
DATABASE_ROLES_REVISION: Final = "202608030006"
HEAD_REVISION: Final = DATABASE_ROLES_REVISION
RUNNER_VERSION: Final = "1.5.0"

REVISION_SPECS: Final = (
    RevisionSpec(
        revision=ANCHOR_REVISION,
        down_revision=None,
        story_id="ST-0301",
        relative_path=Path(
            "migrations/versions/202608030001_framework_install_history.py"
        ),
        sha256="edc9accc402947ff9d1fa9b93d5028fb762b2cfc10deb54e555985acde09e2d3",
        runner_version="1.0.0",
        server_version_num=180004,
    ),
    RevisionSpec(
        revision=FOUNDATION_REVISION,
        down_revision=ANCHOR_REVISION,
        story_id="ST-0302",
        relative_path=Path("migrations/versions/202608030002_foundation_schemas.py"),
        sha256="f91f6315779a045871d955cedb4b7a2606a562fbd8fdddae48810e54ef7dded4",
        runner_version="1.1.0",
        server_version_num=180004,
    ),
    RevisionSpec(
        revision=IAM_OPS_REVISION,
        down_revision=FOUNDATION_REVISION,
        story_id="ST-0303",
        relative_path=Path("migrations/versions/202608030003_iam_ops_tables.py"),
        sha256="a9e162915e7450e30a6c96bafd1a65485447f6163b88ef5771dedc3df14c2f4e",
        runner_version="1.2.0",
        server_version_num=180004,
    ),
    RevisionSpec(
        revision=DOMAIN_REVISION,
        down_revision=IAM_OPS_REVISION,
        story_id="ST-0304",
        relative_path=Path("migrations/versions/202608030004_domain_schemas.py"),
        sha256="632fc5146a57e2c7768745e3ed665aba0f91f229afc174c17fca8e9e2d88c407",
        runner_version="1.3.0",
        server_version_num=180004,
    ),
    RevisionSpec(
        revision=PUBLICATION_ANALYTICS_FINANCE_REVISION,
        down_revision=DOMAIN_REVISION,
        story_id="ST-0305",
        relative_path=Path(
            "migrations/versions/202608030005_publication_analytics_finance.py"
        ),
        sha256="08e7f75a005e960dca0af9a7fe7cacbe90040aaafeea01d1f5a279a84bcdf38b",
        runner_version="1.4.0",
        server_version_num=180004,
    ),
    RevisionSpec(
        revision=DATABASE_ROLES_REVISION,
        down_revision=PUBLICATION_ANALYTICS_FINANCE_REVISION,
        story_id="ST-0306",
        relative_path=Path("migrations/versions/202608030006_database_roles.py"),
        sha256="472690c8ca8080e3e3c0e294e40ea31b30c7d9314daa4cd5ee83a4841d439825",
        runner_version=RUNNER_VERSION,
        server_version_num=180004,
    ),
)
ALEMBIC_RUNTIME_SPECS: Final = (
    RuntimeSourceSpec(
        relative_path=Path("migrations/env.py"),
        sha256="208e6fc0740347a35e40c9a2501aa726e10f6ef44bea36c3078e4cd6211f343f",
    ),
)


def _checkpoint(
    revision: str,
    story_id: str,
    phase: str,
    direction: Direction,
    repeatable: bool,
    filename: str,
    digest: str,
) -> CheckpointSpec:
    return CheckpointSpec(
        revision=revision,
        story_id=story_id,
        phase=phase,
        direction=direction,
        repeatable=repeatable,
        relative_path=Path(f"changes/{story_id.lower()}/database/{filename}"),
        sha256=digest,
    )


CHECKPOINT_SPECS: Final = (
    _checkpoint(
        "202607300001",
        "ST-0002",
        "EXPAND",
        Direction.UPGRADE,
        False,
        "202607300001_job_state_expand.sql",
        "6171d33b0ac8a15d48a7ccfdff5ff6872ba8de5c919ca836effea3523d39ff31",
    ),
    _checkpoint(
        "202607300002",
        "ST-0002",
        "EXPAND_VALIDATE",
        Direction.UPGRADE,
        False,
        "202607300002_job_state_expand_validate.sql",
        "50fb0c65d8482817ffa7fbbb84e02965683fcb8dda2a6f9ecb0a3e7766d75c95",
    ),
    _checkpoint(
        "202607300003",
        "ST-0002",
        "MIGRATE_BATCH",
        Direction.UPGRADE,
        True,
        "202607300003_job_state_migrate_batch.sql",
        "4b6508b8c5a082695b1c4c48365c5932b51e3a6ca9a93c83ec599cd6aa7b1eb8",
    ),
    _checkpoint(
        "202607300004",
        "ST-0002",
        "CONTRACT_PREPARE",
        Direction.UPGRADE,
        False,
        "202607300004_job_state_contract_prepare.sql",
        "6e0bca4e086547fb9035971fcef812a79edb155ef0af69a9e2b55de30b2ac779",
    ),
    _checkpoint(
        "202607300005",
        "ST-0002",
        "CONTRACT",
        Direction.UPGRADE,
        False,
        "202607300005_job_state_contract.sql",
        "9e54b1719d9fdd02a2790916d02875a909dbb027be33c3108285f5d788a91897",
    ),
    _checkpoint(
        "202607300006",
        "ST-0002",
        "GUARDED_DOWNGRADE",
        Direction.DOWNGRADE,
        False,
        "202607300006_job_state_guarded_downgrade.sql",
        "3c1602421352babb8241cca6cc7748cf7f519ee7dc8cec9834b284fd95161cab",
    ),
    _checkpoint(
        "202607300007",
        "ST-0003",
        "EXPAND",
        Direction.UPGRADE,
        False,
        "202607300007_ai_governance_expand.sql",
        "a9d07f07ed15541ca19cf8b6324b680ac2addf9370c70b35f86afa9d2bd82064",
    ),
    _checkpoint(
        "202607300008",
        "ST-0003",
        "EXPAND_VALIDATE",
        Direction.UPGRADE,
        False,
        "202607300008_ai_governance_expand_validate.sql",
        "9bd988e4fdd9e8c4fc9b631481092af3d92cbf649c7164c83eb7d6ab64efc978",
    ),
    _checkpoint(
        "202607300009",
        "ST-0003",
        "MIGRATE_BATCH",
        Direction.UPGRADE,
        True,
        "202607300009_ai_governance_migrate_batch.sql",
        "30cd41619c7b59c8d759bf854c86d0ac2b381b7d5c320051402919816602545a",
    ),
    _checkpoint(
        "202607300010",
        "ST-0003",
        "CONTRACT_PREPARE",
        Direction.UPGRADE,
        False,
        "202607300010_ai_governance_contract_prepare.sql",
        "380ab7c96bdc73c1a562baef4918c4c4dfbc533e05014435363db9eeea682b25",
    ),
    _checkpoint(
        "202607300011",
        "ST-0003",
        "CONTRACT",
        Direction.UPGRADE,
        False,
        "202607300011_ai_governance_contract.sql",
        "8aa37799806be8bbbafd952b03627d16ec6dce459a77a03503f562b61550d9da",
    ),
    _checkpoint(
        "202607300012",
        "ST-0003",
        "GUARDED_DOWNGRADE",
        Direction.DOWNGRADE,
        False,
        "202607300012_ai_governance_guarded_downgrade.sql",
        "dae027887c7950ca03a9b0997cfadbe4b86f1e968cb00079fc178775f8b4b8ba",
    ),
    _checkpoint(
        "202607300013",
        "ST-0004",
        "EXPAND",
        Direction.UPGRADE,
        False,
        "202607300013_content_expand.sql",
        "cdb4ba3f94691425059b2282f343b0cdc82e6b82bb93fdbfe8dd3a6a3dd4290e",
    ),
    _checkpoint(
        "202607300014",
        "ST-0004",
        "EXPAND_VALIDATE",
        Direction.UPGRADE,
        False,
        "202607300014_content_expand_validate.sql",
        "16333a0a0aa8cb1f30d488faaef2dc387043619aed2937ed0d9a0aebd4d32704",
    ),
    _checkpoint(
        "202607300015",
        "ST-0004",
        "MIGRATE_BATCH",
        Direction.UPGRADE,
        True,
        "202607300015_content_migrate_batch.sql",
        "271af87f846489ac855ba66b371dc659698604f35f1dd82e34b8eb0b52a8c00c",
    ),
    _checkpoint(
        "202607300016",
        "ST-0004",
        "CONTRACT_PREPARE",
        Direction.UPGRADE,
        False,
        "202607300016_content_contract_prepare.sql",
        "b61ffcba92a270a90c9a2492fa602b43b8e048ea75e74ef57016852079ddf968",
    ),
    _checkpoint(
        "202607300017",
        "ST-0004",
        "CONTRACT",
        Direction.UPGRADE,
        False,
        "202607300017_content_contract.sql",
        "c3598c730dfb0c2354f227e574db88d56399c2cfd78974827738d5cceaf0a845",
    ),
    _checkpoint(
        "202607300018",
        "ST-0004",
        "GUARDED_DOWNGRADE",
        Direction.DOWNGRADE,
        False,
        "202607300018_content_guarded_downgrade.sql",
        "005eb43bcc8692a22ae7cf237fdd7d721165e8ea54988f4d7d6acada45366381",
    ),
)

FORWARD_PLAN: Final = (
    "202607300001",
    "202607300002",
    "202607300003",
    "202607300004",
    "202607300005",
    "202607300007",
    "202607300008",
    "202607300009",
    "202607300010",
    "202607300011",
    "202607300013",
    "202607300014",
    "202607300015",
    "202607300016",
    "202607300017",
)
GUARDED_REVERSE_PLAN: Final = (
    "202607300018",
    "202607300012",
    "202607300006",
)


def _validate_relative_path(path: Path) -> None:
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CatalogError(CatalogErrorCode.INVALID_CATALOG)


def validate_catalog() -> None:
    """Validate catalog shape without reading source files."""

    revisions = [item.revision for item in REVISION_SPECS]
    checkpoints = [item.revision for item in CHECKPOINT_SPECS]
    if (
        not revisions
        or revisions[0] != ANCHOR_REVISION
        or HEAD_REVISION != revisions[-1]
        or len(set(revisions)) != len(revisions)
    ):
        raise CatalogError(CatalogErrorCode.INVALID_CATALOG)
    for index, revision_spec in enumerate(REVISION_SPECS):
        expected_parent = None if index == 0 else REVISION_SPECS[index - 1].revision
        if (
            revision_spec.down_revision != expected_parent
            or len(revision_spec.revision) != 12
            or not revision_spec.revision.isdigit()
            or not revision_spec.story_id.startswith("ST-")
            or len(revision_spec.story_id) != 7
            or not revision_spec.story_id[3:].isdigit()
            or re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+", revision_spec.runner_version)
            is None
            or type(revision_spec.server_version_num) is not int
            or not 100000 <= revision_spec.server_version_num <= 999999
        ):
            raise CatalogError(CatalogErrorCode.INVALID_CATALOG)
    if len(set(checkpoints)) != 18 or checkpoints != sorted(checkpoints):
        raise CatalogError(CatalogErrorCode.INVALID_CATALOG)
    if (
        tuple(
            item.revision
            for item in CHECKPOINT_SPECS
            if item.direction is Direction.UPGRADE
        )
        != FORWARD_PLAN
    ):
        raise CatalogError(CatalogErrorCode.INVALID_CATALOG)
    if (
        tuple(
            reversed(
                [
                    item.revision
                    for item in CHECKPOINT_SPECS
                    if item.direction is Direction.DOWNGRADE
                ]
            )
        )
        != GUARDED_REVERSE_PLAN
    ):
        raise CatalogError(CatalogErrorCode.INVALID_CATALOG)
    for source_spec in (
        *ALEMBIC_RUNTIME_SPECS,
        *REVISION_SPECS,
        *CHECKPOINT_SPECS,
    ):
        _validate_relative_path(source_spec.relative_path)
        if len(source_spec.sha256) != 64 or any(
            char not in "0123456789abcdef" for char in source_spec.sha256
        ):
            raise CatalogError(CatalogErrorCode.INVALID_CATALOG)


def _read_regular_file(root: Path, relative: Path, maximum: int) -> bytes:
    """Read a bounded repository file without following any symlink."""

    root_stat: os.stat_result | None
    try:
        root_stat = root.lstat()
    except OSError:
        root_stat = None
    if root_stat is None:
        raise CatalogError(CatalogErrorCode.INVALID_ROOT)
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise CatalogError(CatalogErrorCode.INVALID_ROOT)

    flags = os.O_RDONLY | os.O_CLOEXEC
    nofollow = getattr(os, "O_NOFOLLOW", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    if (
        type(nofollow) is not int
        or nofollow == 0
        or type(nonblock) is not int
        or nonblock == 0
    ):
        raise CatalogError(CatalogErrorCode.INVALID_SOURCE)
    directory = getattr(os, "O_DIRECTORY", 0)
    descriptors: list[int] = []
    os_failed = False
    try:
        current = os.open(root, flags | directory | nofollow)
        descriptors.append(current)
        for component in relative.parts[:-1]:
            current = os.open(
                component,
                flags | directory | nofollow,
                dir_fd=current,
            )
            descriptors.append(current)
        source = os.open(
            relative.parts[-1],
            flags | nofollow | nonblock,
            dir_fd=current,
        )
        descriptors.append(source)
        metadata = os.fstat(source)
        if not stat.S_ISREG(metadata.st_mode):
            raise CatalogError(CatalogErrorCode.INVALID_SOURCE)
        if metadata.st_size < 1 or metadata.st_size > maximum:
            raise CatalogError(CatalogErrorCode.SOURCE_TOO_LARGE)
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(source, min(remaining, 1024 * 1024))
            if not chunk:
                raise CatalogError(CatalogErrorCode.INVALID_SOURCE)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(source, 1):
            raise CatalogError(CatalogErrorCode.INVALID_SOURCE)
        return b"".join(chunks)
    except CatalogError:
        raise
    except OSError:
        os_failed = True
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
    if os_failed:
        raise CatalogError(CatalogErrorCode.INVALID_SOURCE)
    raise CatalogError(CatalogErrorCode.INVALID_SOURCE)


def _verify_source(
    root: Path,
    relative: Path,
    expected_sha256: str,
    maximum: int,
    *,
    retain_content: bool = False,
) -> VerifiedSource:
    content = _read_regular_file(root, relative, maximum)
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_sha256:
        raise CatalogError(CatalogErrorCode.SOURCE_DIGEST_MISMATCH)
    text: str | None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is None:
        raise CatalogError(CatalogErrorCode.SOURCE_TEXT_INVALID)
    if "\x00" in text:
        raise CatalogError(CatalogErrorCode.SOURCE_TEXT_INVALID)
    return VerifiedSource(
        relative_path=relative,
        sha256=digest,
        size=len(content),
        content=content if retain_content else None,
    )


def _catalog_digest() -> str:
    value = {
        "runtime_sources": [
            {
                "path": item.relative_path.as_posix(),
                "sha256": item.sha256,
            }
            for item in ALEMBIC_RUNTIME_SPECS
        ],
        "revisions": [
            {
                "revision": item.revision,
                "down_revision": item.down_revision,
                "story_id": item.story_id,
                "path": item.relative_path.as_posix(),
                "sha256": item.sha256,
                "runner_version": item.runner_version,
                "server_version_num": item.server_version_num,
            }
            for item in REVISION_SPECS
        ],
        "checkpoints": [
            {
                "revision": item.revision,
                "story_id": item.story_id,
                "phase": item.phase,
                "direction": item.direction.value,
                "repeatable": item.repeatable,
                "path": item.relative_path.as_posix(),
                "sha256": item.sha256,
            }
            for item in CHECKPOINT_SPECS
        ],
        "forward_plan": FORWARD_PLAN,
        "guarded_reverse_plan": GUARDED_REVERSE_PLAN,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_all_sources(repository_root: Path) -> CatalogVerification:
    """Verify the full source catalog before any database operation."""

    validate_catalog()
    root = repository_root.absolute()
    runtime_sources = tuple(
        _verify_source(
            root,
            item.relative_path,
            item.sha256,
            MAX_REVISION_BYTES,
            retain_content=True,
        )
        for item in ALEMBIC_RUNTIME_SPECS
    )
    revisions = tuple(
        _verify_source(
            root,
            item.relative_path,
            item.sha256,
            MAX_REVISION_BYTES,
            retain_content=True,
        )
        for item in REVISION_SPECS
    )
    required_metadata_labels = (
        "- requirement IDs:",
        "- architecture:",
        "- risk class:",
        "- estimated lock:",
        "- backfill job:",
        "- rollback category:",
    )
    for spec, source in zip(REVISION_SPECS, revisions, strict=True):
        content = source.content
        if content is None:
            raise CatalogError(CatalogErrorCode.SOURCE_TEXT_INVALID)
        text = content.decode("utf-8")
        if f"- story: {spec.story_id}" not in text or any(
            label not in text for label in required_metadata_labels
        ):
            raise CatalogError(CatalogErrorCode.SOURCE_TEXT_INVALID)
    checkpoints = tuple(
        _verify_source(root, item.relative_path, item.sha256, MAX_CHECKPOINT_BYTES)
        for item in CHECKPOINT_SPECS
    )
    return CatalogVerification(
        runtime_sources=runtime_sources,
        revision_sources=revisions,
        checkpoint_sources=checkpoints,
        catalog_sha256=_catalog_digest(),
    )
