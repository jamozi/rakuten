"""Fail-closed Alembic runner for the cumulative RAOS migration graph."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import psycopg
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine, URL
from sqlalchemy.pool import NullPool

from .catalog import (
    ALEMBIC_RUNTIME_SPECS,
    ANCHOR_REVISION,
    DOMAIN_REVISION,
    FOUNDATION_REVISION,
    HEAD_REVISION,
    IAM_OPS_REVISION,
    PUBLICATION_ANALYTICS_FINANCE_REVISION,
    REVISION_SPECS,
    CatalogVerification,
    verify_all_sources,
)


EXPECTED_SERVER_VERSION_NUM: Final = 180004
ADVISORY_LOCK_KEY: Final = -4304770990298879982
_ADVISORY_LOCK_UNSIGNED: Final = ADVISORY_LOCK_KEY % (1 << 64)
_ADVISORY_LOCK_CLASS_ID: Final = _ADVISORY_LOCK_UNSIGNED >> 32
_ADVISORY_LOCK_OBJECT_ID: Final = _ADVISORY_LOCK_UNSIGNED & 0xFFFFFFFF
DOMAIN_SCHEMAS: Final = (
    "ai",
    "analytics",
    "catalog",
    "editorial",
    "evidence",
    "finance",
    "freshness",
    "iam",
    "ops",
    "policy",
    "portfolio",
    "publishing",
    "readmodel",
)
FOUNDATION_SCHEMAS: Final = ("iam", "ops")
ST0304_SCHEMAS: Final = (
    "portfolio",
    "catalog",
    "evidence",
    "editorial",
    "ai",
    "policy",
)
ST0304_SCHEMA_COMMENTS: Final = {
    "portfolio": "サイト、カテゴリ、検索意図、キーワード、機会評価、優先アクション",
    "catalog": "楽天取得、商品同定、ショップ、Offer、外部事実Observation、Current Projection",
    "evidence": "Source、Snapshot、Fact、Source Packet、Claim、根拠対応",
    "editorial": "記事企画、構造化記事版、比較、推薦、レビューコメント、内部リンク",
    "ai": "AI Task、Prompt、Schema、Model Route、Job、Attempt、Token・費用、評価",
    "policy": "Policy Bundle、Rule、品質検査、Finding、Score、Waiver、Gate",
}
ST0304_RLS_TABLES: Final = (
    "editorial.article_disclosure_context",
    "editorial.article_methodology_binding",
    "editorial.article_template_version",
    "editorial.article_type_version",
    "editorial.content_schema_version",
    "editorial.editorial_methodology_version",
    "editorial.media_asset",
    "editorial.seo_metadata_version",
    "editorial.structured_data_manifest",
    "evidence.first_hand_experience_asset",
    "evidence.first_hand_experience_record",
)
ST0305_SCHEMAS: Final = (
    "publishing",
    "freshness",
    "analytics",
    "finance",
    "readmodel",
)
ST0305_SCHEMA_COMMENTS: Final = {
    "publishing": "人間Review、Approval、Publication Snapshot、公開状態、Route、Rollback",
    "freshness": "鮮度SLA、Refresh、Staleness、Affiliate Link検査、影響分析",
    "analytics": "匿名行動、楽天クリック、GSC・GA4取込、帰属推定、日次指標",
    "finance": "成果原本取込、発生・確定・取消、費用配賦、確定ユニットエコノミクス",
    "readmodel": "公開Rendererが読む安全な再生成可能Projection",
}
_ST0304_CATALOG_DIGESTS: Final = {
    "relations": (87, "692fe9230d7c72823ceb716758d16b9d"),
    "columns": (1141, "ed47ed9dad9060fcf55573143653de09"),
    "constraints": (1757, "cf4c5ac88bf3476e433de1f35c48af6e"),
    "indexes": (453, "b5049f3b168dad1bb7dfe6296f0d60e6"),
    "functions": (48, "5e994dea08bd1b7f9fe80cf0e23b0951"),
    "triggers": (81, "7ec669ff04f1c99c5d144b3e234983bf"),
}
_ST0305_CATALOG_DIGESTS: Final = {
    "relations": (39, "8b7c92be0f2fd5402a424d95eea5233a"),
    "columns": (629, "5b45839a79986b7f09e97d9c18ab2ebb"),
    "constraints": (855, "486df24518366f36689d83135245b0fa"),
    "indexes": (239, "caa0c0ba455c58af334ea02bd0afa319"),
    "functions": (3, "92c2ea81850bf9cb5357e173476705f7"),
    "triggers": (17, "abbe0bced5705576cfce1a2dc2e0e615"),
}
FOUNDATION_SCHEMA_COMMENTS: Final = {
    "iam": "OIDC主体、アプリケーションRole、権限、緊急アクセス",
    "ops": "ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定",
}
_IAM_OPS_TABLE_SHAPE: Final = (
    (
        "ops",
        "object_artifact",
        "id!,display_id!,artifact_kind!,storage_provider!,bucket_name!,object_key!,"
        "object_version?,content_type!,byte_size!,sha256!,encryption_state!,"
        "retention_class!,is_immutable!,source_system!,acquired_at?,"
        "created_by_principal_id?,metadata!,created_at!",
    ),
    (
        "ops",
        "job",
        "id!,display_id!,job_type!,queue_name!,status!,priority!,idempotency_key?,"
        "site_id?,aggregate_type?,aggregate_id?,payload!,payload_artifact_id?,"
        "scheduled_at?,available_at!,started_at?,completed_at?,max_attempts!,"
        "attempt_count!,lease_owner?,lease_expires_at?,correlation_id!,causation_id?,"
        "parent_job_id?,budget_jpy?,created_by_actor_type!,created_by_actor_id?,"
        "last_error_class?,last_error_code?,last_error_message?,created_at!,updated_at!,"
        "lock_version!,job_version!,deadline_at?,cancel_requested_at?",
    ),
    (
        "ops",
        "job_attempt",
        "id!,job_id!,attempt_no!,status!,worker_id!,handler_version!,started_at!,"
        "completed_at?,provider_request_id?,input_artifact_id?,output_artifact_id?,"
        "error_class?,error_code?,error_message?,retry_after_at?,metrics!,created_at!",
    ),
    (
        "ops",
        "outbox_event",
        "id!,event_type!,event_version!,producer!,aggregate_type!,aggregate_id!,"
        "aggregate_version!,correlation_id!,causation_id?,actor_type!,actor_id?,"
        "payload!,payload_schema_hash!,status!,available_at!,published_at?,"
        "publish_attempts!,last_error?,created_at!",
    ),
    (
        "ops",
        "inbox_receipt",
        "id!,consumer_name!,handler_version!,event_id!,status!,received_at!,"
        "processed_at?,result_hash?,error_code?,created_at!",
    ),
    (
        "ops",
        "idempotency_record",
        "id!,actor_fingerprint!,route_key!,idempotency_key!,request_hash!,status!,"
        "response_status?,response_body?,response_artifact_id?,resource_type?,"
        "resource_id?,expires_at!,completed_at?,created_at!",
    ),
    (
        "ops",
        "audit_event",
        "id!,occurred_at!,actor_type!,actor_id?,action!,target_type!,target_id?,"
        "outcome!,severity!,correlation_id!,request_id?,before_hash?,after_hash?,"
        "details!,created_at!",
    ),
    (
        "ops",
        "runtime_setting_version",
        "id!,setting_key!,scope_type!,scope_id?,version_no!,setting_class!,value!,"
        "value_sha256!,status!,effective_from?,effective_to?,created_by_principal_id!,"
        "approved_by_principal_id?,approval_reason?,created_at!",
    ),
    (
        "iam",
        "principal",
        "id!,display_id!,principal_type!,status!,display_name!,deactivated_at?,"
        "deactivation_reason?,created_at!,updated_at!,lock_version!",
    ),
    (
        "iam",
        "user_account",
        "principal_id!,oidc_issuer!,oidc_subject!,email?,email_verified!,mfa_required!,"
        "last_login_at?,last_mfa_at?,created_at!",
    ),
    (
        "iam",
        "service_principal",
        "principal_id!,service_code!,workload_identity!,allowed_environment!,"
        "credential_rotated_at?,last_used_at?,created_at!",
    ),
    (
        "iam",
        "role",
        "id!,role_code!,name!,description!,is_system_role!,status!,created_at!",
    ),
    (
        "iam",
        "permission",
        "id!,permission_code!,description!,risk_level!,status!,created_at!",
    ),
    ("iam", "role_permission", "role_id!,permission_id!,created_at!"),
    (
        "iam",
        "principal_role_assignment",
        "id!,principal_id!,role_id!,scope_type!,scope_id?,valid_from!,valid_to?,"
        "assigned_by_principal_id!,assignment_reason!,revoked_at?,"
        "revoked_by_principal_id?,revocation_reason?,created_at!",
    ),
    (
        "iam",
        "session_revocation",
        "id!,principal_id!,oidc_issuer!,oidc_subject!,revoke_before!,reason!,"
        "created_by_principal_id!,expires_at?,created_at!",
    ),
    (
        "iam",
        "break_glass_record",
        "id!,display_id!,principal_id!,incident_id!,reason!,"
        "approved_by_principal_id!,permissions!,started_at!,expires_at!,ended_at?,"
        "end_reason?,created_at!",
    ),
)
_IAM_OPS_CONSTRAINT_COUNTS: Final = {
    "c": 66,
    "f": 20,
    "n": 151,
    "p": 17,
    "u": 13,
}
_IAM_OPS_FOREIGN_KEY_DELETE_ACTIONS: Final = (
    ("fk_ops_job_payload_artifact_id", "r"),
    ("fk_ops_job_parent_job_id", "n"),
    ("fk_ops_job_attempt_job_id", "r"),
    ("fk_ops_job_attempt_input_artifact_id", "r"),
    ("fk_ops_job_attempt_output_artifact_id", "r"),
    ("fk_ops_idempotency_record_response_artifact_id", "r"),
    ("fk_ops_runtime_setting_version_created_by_principal_id", "r"),
    ("fk_ops_runtime_setting_version_approved_by_principal_id", "r"),
    ("fk_iam_user_account_principal_id", "r"),
    ("fk_iam_service_principal_principal_id", "r"),
    ("fk_iam_role_permission_role_id", "r"),
    ("fk_iam_role_permission_permission_id", "r"),
    ("fk_iam_principal_role_assignment_principal_id", "r"),
    ("fk_iam_principal_role_assignment_role_id", "r"),
    ("fk_iam_principal_role_assignment_assigned_by_principal_id", "r"),
    ("fk_iam_principal_role_assignment_revoked_by_principal_id", "r"),
    ("fk_iam_session_revocation_principal_id", "r"),
    ("fk_iam_session_revocation_created_by_principal_id", "r"),
    ("fk_iam_break_glass_record_principal_id", "r"),
    ("fk_iam_break_glass_record_approved_by_principal_id", "r"),
)
_IAM_OPS_DEFERRED_FOREIGN_KEYS: Final = (
    (
        "fk_iam_break_glass_record_incident_id",
        "iam.ix_iam_break_glass_record_incident_id",
    ),
    ("fk_ops_job_site_id", "ops.ix_ops_job_site_id"),
)
_IDENTIFIER_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_AMBIENT_PG_PATTERN: Final = re.compile(r"^PG[A-Z0-9_]*$")


class MigrationEnvironment(StrEnum):
    """Environments allowed by the local/CI candidate runner."""

    DEV = "ENV-DEV"
    CI = "ENV-CI"
    INTEGRATION = "ENV-INTEGRATION"


class MigrationErrorCode(StrEnum):
    """Stable public error codes."""

    INVALID_TARGET = "MIG-RUN-001"
    AMBIENT_CONFIGURATION = "MIG-RUN-002"
    INVALID_PASSWORD_FILE = "MIG-RUN-003"
    CONNECTION_FAILED = "MIG-RUN-004"
    SERVER_VERSION_MISMATCH = "MIG-RUN-005"
    LOCK_BUSY = "MIG-RUN-006"
    GRAPH_MISMATCH = "MIG-RUN-007"
    UNMANAGED_DATABASE = "MIG-RUN-008"
    MIGRATION_FAILED = "MIG-RUN-009"
    HISTORY_INVALID = "MIG-RUN-010"
    SESSION_CLEANUP_FAILED = "MIG-RUN-011"
    DOWNGRADE_FORBIDDEN = "MIG-RUN-012"


_ERROR_MESSAGES: Final = {
    MigrationErrorCode.INVALID_TARGET: "database target is invalid",
    MigrationErrorCode.AMBIENT_CONFIGURATION: "ambient database configuration is forbidden",
    MigrationErrorCode.INVALID_PASSWORD_FILE: "password file is invalid",
    MigrationErrorCode.CONNECTION_FAILED: "database connection failed",
    MigrationErrorCode.SERVER_VERSION_MISMATCH: "database server version does not match",
    MigrationErrorCode.LOCK_BUSY: "migration lock is already held",
    MigrationErrorCode.GRAPH_MISMATCH: "migration graph or current revision is not recognized",
    MigrationErrorCode.UNMANAGED_DATABASE: "database is not an empty or managed RAOS database",
    MigrationErrorCode.MIGRATION_FAILED: "migration failed and requires forward recovery",
    MigrationErrorCode.HISTORY_INVALID: "migration version or history is invalid",
    MigrationErrorCode.SESSION_CLEANUP_FAILED: "migration session cleanup failed",
    MigrationErrorCode.DOWNGRADE_FORBIDDEN: "history anchor downgrade is forbidden",
}


class MigrationError(RuntimeError):
    """A sanitized operational failure."""

    __slots__ = ("code",)

    def __init__(self, code: MigrationErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    """Explicit local/CI database target without a DSN or secret value."""

    environment: MigrationEnvironment
    host: str
    port: int
    database: str
    user: str
    password_file: Path


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Allowlisted public result."""

    command: str
    environment: str | None
    changed: bool
    current_revision: str
    catalog_sha256: str
    revision_source_count: int
    checkpoint_source_count: int

    def public_dict(self) -> dict[str, object]:
        return {
            "catalog_sha256": self.catalog_sha256,
            "changed": self.changed,
            "checkpoint_source_count": self.checkpoint_source_count,
            "command": self.command,
            "current_revision": self.current_revision,
            "environment": self.environment,
            "revision_source_count": self.revision_source_count,
            "status": "PASS",
        }


EngineFactory = Callable[[DatabaseTarget], Engine]


def _validate_identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER_PATTERN.fullmatch(value) is not None


def _is_path(value: object) -> bool:
    return isinstance(value, Path)


def _real_directory(path: Path) -> bool:
    if not path.is_absolute():
        return False
    try:
        lexical = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError:
        return False
    return (
        lexical == resolved
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
    )


def _reject_ambient_postgres_configuration() -> None:
    if any(_AMBIENT_PG_PATTERN.fullmatch(key) for key in os.environ):
        raise MigrationError(MigrationErrorCode.AMBIENT_CONFIGURATION)


def _validate_target(target: DatabaseTarget) -> None:
    if type(target) is not DatabaseTarget:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if type(target.environment) is not MigrationEnvironment:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if type(target.host) is not str or not target.host:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if target.host.startswith("/"):
        if not _real_directory(Path(target.host)):
            raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    elif target.host not in {"127.0.0.1", "::1"}:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if type(target.port) is not int or not 1024 <= target.port <= 65535:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if not _validate_identifier(target.database) or not _validate_identifier(
        target.user
    ):
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if not _is_path(target.password_file) or not target.password_file.is_absolute():
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    _reject_ambient_postgres_configuration()


def _read_password_file(path: Path) -> str:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    flags = os.O_RDONLY | os.O_CLOEXEC
    nofollow = getattr(os, "O_NOFOLLOW", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    if (
        type(nofollow) is not int
        or nofollow == 0
        or type(nonblock) is not int
        or nonblock == 0
    ):
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    directory_flags = flags | os.O_DIRECTORY | nofollow
    descriptors: list[int] = []
    open_failed = False
    try:
        current = os.open("/", directory_flags)
        descriptors.append(current)
        for component in path.parts[1:-1]:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(
            path.parts[-1],
            flags | nofollow | nonblock,
            dir_fd=current,
        )
        descriptors.append(descriptor)
    except MigrationError:
        raise
    except OSError:
        open_failed = True
        descriptor = -1
    if open_failed:
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    read_failed = False
    content = b""
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= 1024
        ):
            raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
        content = os.read(descriptor, metadata.st_size + 1)
        if len(content) != metadata.st_size:
            raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    except MigrationError:
        raise
    except OSError:
        read_failed = True
    finally:
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass
    if read_failed:
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    if content.endswith(b"\n"):
        content = content[:-1]
    if not content or b"\x00" in content or b"\r" in content or b"\n" in content:
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    password: str | None
    try:
        password = content.decode("utf-8")
    except UnicodeDecodeError:
        password = None
    if password is None:
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    return password


def _default_engine_factory(target: DatabaseTarget) -> Engine:
    def connect() -> Any:
        _reject_ambient_postgres_configuration()
        password = _read_password_file(target.password_file)
        return psycopg.connect(
            host=target.host,
            port=target.port,
            dbname=target.database,
            user=target.user,
            password=password,
            sslmode="disable",
            connect_timeout=5,
            application_name="raos-migration-st0301",
            options=(
                "-c lock_timeout=5000ms "
                "-c statement_timeout=300000ms "
                "-c idle_in_transaction_session_timeout=60000ms "
                "-c timezone=UTC "
                "-c search_path=pg_catalog"
            ),
        )

    return sa.create_engine(
        URL.create("postgresql+psycopg"),
        creator=connect,
        poolclass=NullPool,
        hide_parameters=True,
    )


def _alembic_config(repository_root: Path) -> Config:
    output = io.StringIO()
    configuration = Config(output_buffer=output, stdout=output)
    configuration.set_main_option(
        "script_location",
        str(repository_root / "migrations"),
    )
    return configuration


@contextmanager
def _verified_migration_root(
    verification: CatalogVerification,
) -> Generator[Path, None, None]:
    sources = (*verification.runtime_sources, *verification.revision_sources)
    expected_paths = tuple(
        item.relative_path
        for item in (
            *ALEMBIC_RUNTIME_SPECS,
            *REVISION_SPECS,
        )
    )
    if tuple(source.relative_path for source in sources) != expected_paths:
        raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
    with tempfile.TemporaryDirectory(prefix="raos-migration-snapshot-") as temporary:
        root = Path(temporary)
        try:
            for source in sources:
                content = source.content
                if (
                    content is None
                    or hashlib.sha256(content).hexdigest() != source.sha256
                    or source.relative_path.parts[0] != "migrations"
                ):
                    raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
                destination = root / source.relative_path
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    destination,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                    0o600,
                )
                try:
                    view = memoryview(content)
                    while view:
                        written = os.write(descriptor, view)
                        if written < 1:
                            raise OSError("snapshot write failed")
                        view = view[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except MigrationError:
            raise
        except OSError:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH) from None
        yield root


def _verify_graph(repository_root: Path) -> None:
    try:
        script = ScriptDirectory.from_config(_alembic_config(repository_root))
        revisions = tuple(script.walk_revisions())
        heads = tuple(script.get_heads())
        bases = tuple(script.get_bases())
    except Exception:
        pass
    else:
        if (
            heads != (HEAD_REVISION,)
            or bases != (ANCHOR_REVISION,)
            or len(revisions) != len(REVISION_SPECS)
        ):
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        expected_by_revision = {item.revision: item for item in REVISION_SPECS}
        for observed in revisions:
            expected = expected_by_revision.get(observed.revision)
            branch_labels = set(observed.branch_labels or ())
            if (
                expected is None
                or observed.down_revision != expected.down_revision
                or observed.dependencies is not None
                or not branch_labels.issubset({"raos_framework"})
                or (
                    observed.revision == ANCHOR_REVISION
                    and branch_labels != {"raos_framework"}
                )
            ):
                raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        return
    raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)


def verify_repository(repository_root: Path) -> CatalogVerification:
    """Verify all source bytes and the exact Alembic graph offline."""

    verification = verify_all_sources(repository_root)
    graph_error: MigrationErrorCode | None = None
    try:
        with _verified_migration_root(verification) as snapshot_root:
            _verify_graph(snapshot_root)
    except MigrationError as error:
        graph_error = error.code
    except Exception:
        graph_error = MigrationErrorCode.GRAPH_MISMATCH
    if graph_error is not None:
        raise MigrationError(graph_error)
    return verification


def _current_heads(connection: Connection) -> tuple[str, ...]:
    context = MigrationContext.configure(
        connection,
        opts={
            "version_table": "raos_migration_version",
            "version_table_schema": "public",
        },
    )
    return tuple(context.get_current_heads())


def _assert_empty_database(connection: Connection) -> None:
    unmanaged = connection.execute(
        sa.text(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_namespace AS n
                    WHERE n.nspname NOT IN ('public', 'information_schema')
                      AND n.nspname NOT LIKE 'pg_%'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS p
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_type AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_collation AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.collnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_conversion AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.connamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_operator AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.oprnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_opclass AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opcnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_opfamily AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opfnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_config AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.cfgnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_dict AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.dictnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_parser AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.prsnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_template AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.tmplnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_statistic_ext AS s
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = s.stxnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_largeobject_metadata)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_server)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_data_wrapper)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_event_trigger)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_publication)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_default_acl)
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_extension
                    WHERE extname <> 'plpgsql'
                )
            """
        )
    ).scalar_one()
    if unmanaged is not False:
        raise MigrationError(MigrationErrorCode.UNMANAGED_DATABASE)


@dataclass(frozen=True, slots=True)
class _OpenAttempt:
    attempt_id: str
    revision_index: int
    direction: str


@dataclass(frozen=True, slots=True)
class _LockedSession:
    """Opaque identity for the one PostgreSQL session holding the lock."""

    backend_pid: int
    driver_connection: Any = field(repr=False, compare=False)


def _history_rows(connection: Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT event_id, attempt_id::text, revision_id, story_id,
                       direction, status, source_sha256, runner_version,
                       server_version_num, error_code
                FROM public.raos_migration_history
                ORDER BY event_id
                """
            )
        ).all()
    ]


def _analyze_history(
    rows: list[tuple[Any, ...]],
    current_revision: str,
    *,
    allow_open: bool,
) -> _OpenAttempt | None:
    specs = tuple(REVISION_SPECS)
    by_revision = {item.revision: (index, item) for index, item in enumerate(specs)}
    completed_index = -1
    attempts: dict[str, tuple[int, str]] = {}
    closed_attempts: set[str] = set()
    previous_event_id = 0
    for row in rows:
        if len(row) != 10:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        (
            event_id,
            attempt_id,
            revision_id,
            story_id,
            direction,
            status,
            source_sha256,
            runner_version,
            server_version_num,
            error_code,
        ) = row
        located = by_revision.get(revision_id)
        if (
            type(event_id) is not int
            or event_id <= previous_event_id
            or not isinstance(attempt_id, str)
            or located is None
        ):
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        previous_event_id = event_id
        try:
            canonical_attempt_id = str(uuid.UUID(attempt_id))
        except ValueError, AttributeError:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID) from None
        index, spec = located
        if (
            canonical_attempt_id != attempt_id
            or story_id != spec.story_id
            or direction not in {"UPGRADE", "DOWNGRADE"}
            or source_sha256 != spec.sha256
            or runner_version != spec.runner_version
            or server_version_num != spec.server_version_num
            or status not in {"STARTED", "SUCCEEDED", "FAILED"}
        ):
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        if status == "STARTED":
            transition_valid = (
                direction == "UPGRADE" and index == completed_index + 1
            ) or (direction == "DOWNGRADE" and index > 0 and index == completed_index)
            if (
                index == 0
                or not transition_valid
                or attempts
                or attempt_id in closed_attempts
                or error_code is not None
            ):
                raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
            attempts[attempt_id] = (index, direction)
            continue
        if index == 0:
            if (
                direction != "UPGRADE"
                or status != "SUCCEEDED"
                or completed_index != -1
                or attempts
                or attempt_id in closed_attempts
                or error_code is not None
            ):
                raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
            completed_index = 0
            closed_attempts.add(attempt_id)
            continue
        transition_valid = (
            direction == "UPGRADE" and index == completed_index + 1
        ) or (direction == "DOWNGRADE" and index > 0 and index == completed_index)
        if (
            len(attempts) != 1
            or attempts.pop(attempt_id, None) != (index, direction)
            or not transition_valid
        ):
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        closed_attempts.add(attempt_id)
        if status == "SUCCEEDED":
            if error_code is not None:
                raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
            completed_index = index if direction == "UPGRADE" else index - 1
        elif error_code not in {"MIGRATION_FAILED", "INTERRUPTED_BEFORE_TERMINAL"}:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    expected_current = (
        specs[completed_index].revision if completed_index >= 0 else "base"
    )
    if expected_current != current_revision or len(attempts) > 1:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if not attempts:
        return None
    attempt_id, (revision_index, direction) = next(iter(attempts.items()))
    if not allow_open:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    return _OpenAttempt(
        attempt_id=attempt_id,
        revision_index=revision_index,
        direction=direction,
    )


def _append_attempt_event(
    connection: Connection,
    *,
    attempt_id: str,
    revision_index: int,
    direction: str,
    status: str,
    error_code: str | None,
) -> None:
    spec = REVISION_SPECS[revision_index]
    connection.execute(
        sa.text(
            """
            INSERT INTO public.raos_migration_history (
                attempt_id, revision_id, story_id, direction, status,
                source_sha256, runner_version, server_version_num, error_code
            ) VALUES (
                CAST(:attempt_id AS uuid), :revision_id, :story_id, :direction,
                :status, :source_sha256, :runner_version,
                :server_version_num, :error_code
            )
            """
        ),
        {
            "attempt_id": attempt_id,
            "revision_id": spec.revision,
            "story_id": spec.story_id,
            "direction": direction,
            "status": status,
            "source_sha256": spec.sha256,
            "runner_version": spec.runner_version,
            "server_version_num": spec.server_version_num,
            "error_code": error_code,
        },
    )
    connection.commit()


def _validate_metadata_shape(connection: Connection) -> None:
    owner = connection.execute(sa.text("SELECT current_user")).scalar_one()
    relations = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner)
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version',
                      'raos_migration_history',
                      'raos_migration_history_event_id_seq'
                  )
                ORDER BY c.relname
                """
            )
        ).all()
    ]
    if relations != [
        ("raos_migration_history", "r", owner),
        ("raos_migration_history_event_id_seq", "S", owner),
        ("raos_migration_version", "r", owner),
    ]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    columns = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, a.attname,
                       pg_catalog.format_type(a.atttypid, a.atttypmod),
                       a.attnotnull, a.attidentity,
                       pg_catalog.pg_get_expr(d.adbin, d.adrelid)
                FROM pg_catalog.pg_attribute AS a
                JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                LEFT JOIN pg_catalog.pg_attrdef AS d
                  ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY c.relname, a.attnum
                """
            )
        ).all()
    ]
    expected_columns = [
        ("raos_migration_history", "event_id", "bigint", True, "a", None),
        ("raos_migration_history", "attempt_id", "uuid", True, "", None),
        (
            "raos_migration_history",
            "revision_id",
            "character varying(32)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "story_id",
            "character varying(16)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "direction",
            "character varying(9)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "status",
            "character varying(10)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "source_sha256",
            "character(64)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "runner_version",
            "character varying(32)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "server_version_num",
            "integer",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "error_code",
            "character varying(64)",
            False,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "occurred_at",
            "timestamp with time zone",
            True,
            "",
            "transaction_timestamp()",
        ),
        (
            "raos_migration_history",
            "transaction_id",
            "text",
            True,
            "",
            "(pg_current_xact_id())::text",
        ),
        (
            "raos_migration_version",
            "version_num",
            "character varying(32)",
            True,
            "",
            None,
        ),
    ]
    if columns != expected_columns:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    constraints = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, con.conname, con.contype, con.convalidated,
                       pg_catalog.pg_get_constraintdef(con.oid, true)
                FROM pg_catalog.pg_constraint AS con
                JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                ORDER BY c.relname, con.conname
                """
            )
        ).all()
    ]
    expected_constraints = [
        (
            "raos_migration_version",
            "raos_migration_version_pkc",
            "p",
            True,
            "PRIMARY KEY (version_num)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_revision",
            "c",
            True,
            "CHECK (revision_id::text ~ '^[0-9]{12}$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_story",
            "c",
            True,
            "CHECK (story_id::text ~ '^ST-[0-9]{4}$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_direction",
            "c",
            True,
            "CHECK (direction::text = ANY (ARRAY['UPGRADE'::character varying, "
            "'DOWNGRADE'::character varying]::text[]))",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_status",
            "c",
            True,
            "CHECK (status::text = ANY (ARRAY['STARTED'::character varying, "
            "'SUCCEEDED'::character varying, 'FAILED'::character varying]::text[]))",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_source_sha256",
            "c",
            True,
            "CHECK (source_sha256 ~ '^[0-9a-f]{64}$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_runner_version",
            "c",
            True,
            "CHECK (runner_version::text ~ '^[0-9]+[.][0-9]+[.][0-9]+$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_server_version",
            "c",
            True,
            "CHECK (server_version_num >= 100000 AND server_version_num <= 999999)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_error_code",
            "c",
            True,
            "CHECK (status::text = 'FAILED'::text AND error_code IS NOT NULL "
            "OR status::text <> 'FAILED'::text AND error_code IS NULL)",
        ),
        (
            "raos_migration_history",
            "pk_raos_migration_history",
            "p",
            True,
            "PRIMARY KEY (event_id)",
        ),
        (
            "raos_migration_history",
            "uq_raos_migration_history_attempt_status",
            "u",
            True,
            "UNIQUE (attempt_id, status)",
        ),
    ]
    expected_constraints.extend(
        (
            relation,
            f"{relation}_{column}_not_null",
            "n",
            True,
            f"NOT NULL {column}",
        )
        for relation, column, _, not_null, _, _ in expected_columns
        if not_null
    )
    expected_constraints.sort()
    if constraints != expected_constraints:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    sequence_dependencies = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT sequence.relname, table_relation.relname,
                       column_attribute.attname, dependency.deptype
                FROM pg_catalog.pg_class AS sequence
                JOIN pg_catalog.pg_namespace AS sequence_namespace
                  ON sequence_namespace.oid = sequence.relnamespace
                JOIN pg_catalog.pg_depend AS dependency
                  ON dependency.classid = 'pg_class'::regclass
                 AND dependency.objid = sequence.oid
                JOIN pg_catalog.pg_class AS table_relation
                  ON table_relation.oid = dependency.refobjid
                JOIN pg_catalog.pg_attribute AS column_attribute
                  ON column_attribute.attrelid = table_relation.oid
                 AND column_attribute.attnum = dependency.refobjsubid
                WHERE sequence_namespace.nspname = 'public'
                  AND sequence.relname =
                      'raos_migration_history_event_id_seq'
                """
            )
        ).all()
    ]
    if sequence_dependencies != [
        (
            "raos_migration_history_event_id_seq",
            "raos_migration_history",
            "event_id",
            "i",
        )
    ]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    unexpected_acl_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT x.grantee, c.relowner AS owner
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                CROSS JOIN LATERAL aclexplode(c.relacl) AS x
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version',
                      'raos_migration_history',
                      'raos_migration_history_event_id_seq'
                  )
                UNION ALL
                SELECT x.grantee, p.proowner AS owner
                FROM pg_catalog.pg_proc AS p
                JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                CROSS JOIN LATERAL aclexplode(p.proacl) AS x
                WHERE n.nspname = 'public'
                  AND p.proname =
                      'raos_reject_migration_history_mutation_st0301'
            ) AS privileges
            WHERE grantee <> owner
            """
        )
    ).scalar_one()
    acl_null_count = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT count(*)
                 FROM pg_catalog.pg_class AS c
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname IN (
                       'raos_migration_version',
                       'raos_migration_history',
                       'raos_migration_history_event_id_seq'
                   )
                   AND c.relacl IS NULL)
                +
                (SELECT count(*)
                 FROM pg_catalog.pg_proc AS p
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public'
                   AND p.proname =
                       'raos_reject_migration_history_mutation_st0301'
                   AND p.proacl IS NULL)
            """
        )
    ).scalar_one()
    trigger_functions = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, t.tgname, t.tgenabled, t.tgtype,
                       p.proname, l.lanname, p.prosecdef, p.provolatile,
                       p.proconfig,
                       trim(regexp_replace(p.prosrc, '\\s+', ' ', 'g'))
                FROM pg_catalog.pg_trigger AS t
                JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_catalog.pg_proc AS p ON p.oid = t.tgfoid
                JOIN pg_catalog.pg_language AS l ON l.oid = p.prolang
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                  AND NOT t.tgisinternal
                ORDER BY c.relname, t.tgname
                """
            )
        ).all()
    ]
    table_security = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, c.relpersistence, c.relrowsecurity,
                       c.relforcerowsecurity, c.relreplident
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                  AND c.relkind = 'r'
                ORDER BY c.relname
                """
            )
        ).all()
    ]
    unexpected_rewrite_or_policy_count = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT count(*)
                 FROM pg_catalog.pg_rewrite AS rewrite
                 JOIN pg_catalog.pg_class AS c ON c.oid = rewrite.ev_class
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname IN (
                       'raos_migration_version', 'raos_migration_history'
                   ))
                +
                (SELECT count(*)
                 FROM pg_catalog.pg_policy AS policy
                 JOIN pg_catalog.pg_class AS c ON c.oid = policy.polrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname IN (
                       'raos_migration_version', 'raos_migration_history'
                   ))
                +
                (SELECT count(*) FROM pg_catalog.pg_event_trigger)
            """
        )
    ).scalar_one()
    if (
        unexpected_acl_count != 0
        or acl_null_count != 0
        or table_security
        != [
            ("raos_migration_history", "p", False, False, "d"),
            ("raos_migration_version", "p", False, False, "d"),
        ]
        or unexpected_rewrite_or_policy_count != 0
        or trigger_functions
        != [
            (
                "raos_migration_history",
                "trg_raos_migration_history_append_only",
                "O",
                58,
                "raos_reject_migration_history_mutation_st0301",
                "plpgsql",
                False,
                "v",
                ["search_path=pg_catalog"],
                (
                    "BEGIN RAISE EXCEPTION USING ERRCODE = '55000', "
                    "MESSAGE = 'RAOS migration history is append-only'; END;"
                ),
            )
        ]
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _validate_current_head_boundary(
    connection: Connection, current_revision: str
) -> None:
    if current_revision not in {
        IAM_OPS_REVISION,
        DOMAIN_REVISION,
        PUBLICATION_ANALYTICS_FINANCE_REVISION,
    }:
        return

    allowed_schemas = ["public", "information_schema", *FOUNDATION_SCHEMAS]
    if current_revision in {DOMAIN_REVISION, PUBLICATION_ANALYTICS_FINANCE_REVISION}:
        allowed_schemas.extend(ST0304_SCHEMAS)
    if current_revision == PUBLICATION_ANALYTICS_FINANCE_REVISION:
        allowed_schemas.extend(ST0305_SCHEMAS)

    unmanaged_namespace_count = connection.execute(
        sa.text(
            """
            SELECT pg_catalog.count(*)
            FROM pg_catalog.pg_namespace AS namespace
            WHERE namespace.nspname <> ALL(CAST(:schemas AS pg_catalog.text[]))
              AND namespace.nspname NOT LIKE 'pg_%'
            """
        ),
        {"schemas": allowed_schemas},
    ).scalar_one()
    unexpected_public_object_count = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_collation AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.collnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_conversion AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.connamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_operator AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.oprnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_opclass AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.opcnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_opfamily AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.opfnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_config AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.cfgnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_dict AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.dictnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_parser AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.prsnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_template AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.tmplnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_statistic_ext AS object_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_record.stxnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_cast AS cast_record
                 JOIN pg_catalog.pg_type AS source_type
                   ON source_type.oid = cast_record.castsource
                 JOIN pg_catalog.pg_namespace AS source_namespace
                   ON source_namespace.oid = source_type.typnamespace
                 JOIN pg_catalog.pg_type AS target_type
                   ON target_type.oid = cast_record.casttarget
                 JOIN pg_catalog.pg_namespace AS target_namespace
                   ON target_namespace.oid = target_type.typnamespace
                 WHERE source_namespace.nspname = 'public'
                    OR target_namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_transform AS transform_record
                 JOIN pg_catalog.pg_type AS object_type
                   ON object_type.oid = transform_record.trftype
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_type.typnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_amop AS operator_record
                 JOIN pg_catalog.pg_type AS left_type
                   ON left_type.oid = operator_record.amoplefttype
                 JOIN pg_catalog.pg_namespace AS left_namespace
                   ON left_namespace.oid = left_type.typnamespace
                 JOIN pg_catalog.pg_type AS right_type
                   ON right_type.oid = operator_record.amoprighttype
                 JOIN pg_catalog.pg_namespace AS right_namespace
                   ON right_namespace.oid = right_type.typnamespace
                 WHERE left_namespace.nspname = 'public'
                    OR right_namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_amproc AS procedure_record
                 JOIN pg_catalog.pg_type AS left_type
                   ON left_type.oid = procedure_record.amproclefttype
                 JOIN pg_catalog.pg_namespace AS left_namespace
                   ON left_namespace.oid = left_type.typnamespace
                 JOIN pg_catalog.pg_type AS right_type
                   ON right_type.oid = procedure_record.amprocrighttype
                 JOIN pg_catalog.pg_namespace AS right_namespace
                   ON right_namespace.oid = right_type.typnamespace
                 WHERE left_namespace.nspname = 'public'
                    OR right_namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_inherits AS inheritance
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid IN (
                       inheritance.inhrelid, inheritance.inhparent
                   )
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_partitioned_table AS partitioned
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = partitioned.partrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = 'public')
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_attribute AS attribute
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = attribute.attrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = 'public'
                   AND relation.relkind = 'r'
                   AND attribute.attnum > 0
                   AND attribute.attisdropped IS TRUE)
            """
        )
    ).scalar_one()
    expected_digests = {
        "columns": (
            13,
            "7450538f1b7db9a11de2175ea5622895e01caed0bf3cf28e924f954b2581d081",
        ),
        "constraints": (
            23,
            "842667ca3195ac578717c89bee7abbb097d7f19367a1b5d1a07be12e23648d0c",
        ),
        "functions": (
            1,
            "431a5594030dcf81af7906e134110450becccd3333353d9738a1e60c52b89d76",
        ),
        "relations": (
            6,
            "a4075b6294159a742cce51eca570c72c88d7aee5ebbaafd903cffd47de2b21c6",
        ),
        "sequences": (
            1,
            "0923658403a24c645b5caf6289b3bd6eb640c4b9f20cd4da3a0640c0c531bb08",
        ),
        "triggers": (
            1,
            "8179d5669ea47504adcde30672faabddda56dddac22915c46253f272ef38b6b2",
        ),
        "types": (
            4,
            "b470c88e7f4f60e3e63d4a86373a736ea650c24871ff9268bda98b8c15b2787b",
        ),
    }
    if (
        unmanaged_namespace_count != 0
        or unexpected_public_object_count != 0
        or _public_metadata_catalog_digests(connection) != expected_digests
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _validate_foundation_shape(
    connection: Connection,
    current_revision: str,
    *,
    allow_foundation_objects: bool = False,
) -> None:
    revision_ids = [item.revision for item in REVISION_SPECS]
    if current_revision not in revision_ids:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if FOUNDATION_REVISION not in revision_ids:
        return
    current_index = revision_ids.index(current_revision)
    foundation_index = revision_ids.index(FOUNDATION_REVISION)
    if current_index < foundation_index:
        return

    owner = connection.execute(sa.text("SELECT current_user")).scalar_one()
    schemas = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT n.nspname,
                       pg_catalog.pg_get_userbyid(n.nspowner),
                       pg_catalog.obj_description(n.oid, 'pg_namespace'),
                       (
                           SELECT COALESCE(
                               array_agg(
                                   acl.privilege_type
                                   ORDER BY acl.privilege_type
                               ),
                               ARRAY[]::text[]
                           )
                           FROM pg_catalog.aclexplode(
                               COALESCE(
                                   n.nspacl,
                                   pg_catalog.acldefault('n', n.nspowner)
                               )
                           ) AS acl
                           WHERE acl.grantee = n.nspowner
                       ),
                       (
                           SELECT count(*)
                           FROM pg_catalog.aclexplode(
                               COALESCE(
                                   n.nspacl,
                                   pg_catalog.acldefault('n', n.nspowner)
                               )
                           ) AS acl
                           WHERE acl.grantee <> n.nspowner
                       )
                FROM pg_catalog.pg_namespace AS n
                WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                ORDER BY n.nspname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    if schemas != [
        ("iam", owner, FOUNDATION_SCHEMA_COMMENTS["iam"], ["CREATE", "USAGE"], 0),
        ("ops", owner, FOUNDATION_SCHEMA_COMMENTS["ops"], ["CREATE", "USAGE"], 0),
    ]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    default_acl_schemas: list[str] = list(FOUNDATION_SCHEMAS)
    if current_revision in {
        IAM_OPS_REVISION,
        DOMAIN_REVISION,
        PUBLICATION_ANALYTICS_FINANCE_REVISION,
    }:
        default_acl_schemas.append("public")
    if current_revision in {DOMAIN_REVISION, PUBLICATION_ANALYTICS_FINANCE_REVISION}:
        default_acl_schemas.extend(ST0304_SCHEMAS)
    if current_revision == PUBLICATION_ANALYTICS_FINANCE_REVISION:
        default_acl_schemas.extend(ST0305_SCHEMAS)
    default_acl_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM pg_catalog.pg_default_acl AS defaults
            LEFT JOIN pg_catalog.pg_namespace AS n
              ON n.oid = defaults.defaclnamespace
            WHERE defaults.defaclnamespace = 0
               OR n.nspname = ANY(CAST(:schemas AS text[]))
            """
        ),
        {"schemas": default_acl_schemas},
    ).scalar_one()
    if default_acl_count != 0:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    extensions = (
        connection.execute(
            sa.text("SELECT extname FROM pg_catalog.pg_extension ORDER BY extname")
        )
        .scalars()
        .all()
    )
    if extensions != ["plpgsql"]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    uuid_shape = connection.execute(
        sa.text(
            """
            WITH sample AS (
                SELECT pg_catalog.uuidv7() AS value
            )
            SELECT
                pg_catalog.pg_typeof(value)::text,
                pg_catalog.uuid_extract_version(value),
                pg_catalog.uuid_extract_timestamp(value) IS NOT NULL,
                pg_catalog.to_regprocedure('pg_catalog.uuidv7()') IS NOT NULL,
                pg_catalog.to_regprocedure(
                    'pg_catalog.uuidv7(interval)'
                ) IS NOT NULL
            FROM sample
            """
        )
    ).one()
    if tuple(uuid_shape) != ("uuid", 7, True, True, True):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    if current_revision != FOUNDATION_REVISION or allow_foundation_objects:
        return

    unexpected_object = connection.execute(
        sa.text(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS p
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_type AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_collation AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.collnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_conversion AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.connamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_operator AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.oprnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_opclass AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opcnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_opfamily AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opfnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_config AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.cfgnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_dict AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.dictnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_parser AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.prsnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_template AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.tmplnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_statistic_ext AS s
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = s.stxnamespace
                    WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                )
            """
        ),
        {"schemas": list(FOUNDATION_SCHEMAS)},
    ).scalar_one()
    if unexpected_object is not False:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _catalog_rows_digest(rows: list[tuple[Any, ...]]) -> str:
    encoded = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _public_metadata_catalog_digests(
    connection: Connection,
) -> dict[str, tuple[int, str]]:
    relations = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       pg_catalog.pg_get_userbyid(relation.relowner)
                           = current_user,
                       relation.relkind, relation.relpersistence,
                       relation.relispartition, relation.relrowsecurity,
                       relation.relforcerowsecurity, relation.relreplident,
                       COALESCE(relation.relacl::pg_catalog.text, ''),
                       pg_catalog.obj_description(relation.oid, 'pg_class')
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public'
                ORDER BY relation.relname
                """
            )
        ).all()
    ]
    columns = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       attribute.attnum, attribute.attname,
                       pg_catalog.format_type(
                           attribute.atttypid, attribute.atttypmod
                       ),
                       attribute.attnotnull, attribute.attidentity,
                       attribute.attgenerated,
                       COALESCE(
                           pg_catalog.pg_get_expr(
                               attribute_default.adbin,
                               attribute_default.adrelid,
                               false
                           ),
                           ''
                       ),
                       pg_catalog.col_description(
                           attribute.attrelid, attribute.attnum
                       ),
                       COALESCE(attribute.attacl::pg_catalog.text, '')
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN pg_catalog.pg_attribute AS attribute
                  ON attribute.attrelid = relation.oid
                 AND attribute.attnum > 0
                 AND attribute.attisdropped IS FALSE
                LEFT JOIN pg_catalog.pg_attrdef AS attribute_default
                  ON attribute_default.adrelid = attribute.attrelid
                 AND attribute_default.adnum = attribute.attnum
                WHERE namespace.nspname = 'public'
                  AND relation.relkind = 'r'
                ORDER BY relation.relname, attribute.attnum
                """
            )
        ).all()
    ]
    constraints = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       constraint_record.conname, constraint_record.contype,
                       pg_catalog.pg_get_constraintdef(
                           constraint_record.oid, false
                       ),
                       pg_catalog.obj_description(
                           constraint_record.oid, 'pg_constraint'
                       ),
                       constraint_record.convalidated,
                       constraint_record.conenforced,
                       constraint_record.condeferrable,
                       constraint_record.condeferred,
                       constraint_record.connoinherit,
                       constraint_record.conparentid,
                       constraint_record.conkey::pg_catalog.text,
                       constraint_record.confkey::pg_catalog.text,
                       COALESCE(index_namespace.nspname, ''),
                       COALESCE(index_relation.relname, ''),
                       pg_catalog.obj_description(
                           constraint_record.conindid, 'pg_class'
                       ),
                       COALESCE(indexed_namespace.nspname, ''),
                       COALESCE(indexed_relation.relname, ''),
                       constraint_index.indisunique,
                       constraint_index.indisprimary,
                       constraint_index.indisvalid,
                       constraint_index.indisready
                FROM pg_catalog.pg_constraint AS constraint_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constraint_record.conrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                LEFT JOIN pg_catalog.pg_class AS index_relation
                  ON index_relation.oid = constraint_record.conindid
                LEFT JOIN pg_catalog.pg_namespace AS index_namespace
                  ON index_namespace.oid = index_relation.relnamespace
                LEFT JOIN pg_catalog.pg_index AS constraint_index
                  ON constraint_index.indexrelid = constraint_record.conindid
                LEFT JOIN pg_catalog.pg_class AS indexed_relation
                  ON indexed_relation.oid = constraint_index.indrelid
                LEFT JOIN pg_catalog.pg_namespace AS indexed_namespace
                  ON indexed_namespace.oid = indexed_relation.relnamespace
                WHERE namespace.nspname = 'public'
                  AND relation.relkind = 'r'
                ORDER BY relation.relname, constraint_record.conname,
                         constraint_record.contype
                """
            )
        ).all()
    ]
    functions = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, routine.proname, routine.pronargs,
                       pg_catalog.pg_get_function_identity_arguments(routine.oid),
                       pg_catalog.format_type(routine.prorettype, NULL),
                       pg_catalog.pg_get_userbyid(routine.proowner)
                           = current_user,
                       language.lanname, routine.prokind, routine.provolatile,
                       routine.prosecdef,
                       pg_catalog.array_to_string(routine.proconfig, ','),
                       routine.prosrc,
                       COALESCE(routine.proacl::pg_catalog.text, ''),
                       pg_catalog.obj_description(routine.oid, 'pg_proc')
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                JOIN pg_catalog.pg_language AS language
                  ON language.oid = routine.prolang
                WHERE namespace.nspname = 'public'
                ORDER BY routine.proname,
                         pg_catalog.pg_get_function_identity_arguments(
                             routine.oid
                         )
                """
            )
        ).all()
    ]
    triggers = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       trigger_record.tgname, trigger_record.tgenabled,
                       trigger_record.tgtype,
                       function_namespace.nspname, routine.proname,
                       pg_catalog.pg_get_function_identity_arguments(routine.oid),
                       trigger_record.tgqual IS NULL,
                       trigger_record.tgnargs,
                       trigger_record.tgattr::pg_catalog.text,
                       pg_catalog.octet_length(trigger_record.tgargs),
                       trigger_record.tgconstraint,
                       trigger_record.tgdeferrable,
                       trigger_record.tginitdeferred,
                       trigger_record.tgparentid,
                       COALESCE(trigger_record.tgoldtable, ''),
                       COALESCE(trigger_record.tgnewtable, ''),
                       pg_catalog.pg_get_triggerdef(trigger_record.oid, false),
                       pg_catalog.obj_description(
                           trigger_record.oid, 'pg_trigger'
                       )
                FROM pg_catalog.pg_trigger AS trigger_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = trigger_record.tgrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN pg_catalog.pg_proc AS routine
                  ON routine.oid = trigger_record.tgfoid
                JOIN pg_catalog.pg_namespace AS function_namespace
                  ON function_namespace.oid = routine.pronamespace
                WHERE namespace.nspname = 'public'
                  AND trigger_record.tgisinternal IS FALSE
                ORDER BY relation.relname, trigger_record.tgname
                """
            )
        ).all()
    ]
    types = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, object_type.typname,
                       pg_catalog.pg_get_userbyid(object_type.typowner)
                           = current_user,
                       object_type.typtype, object_type.typcategory,
                       object_type.typispreferred, object_type.typisdefined,
                       object_type.typdelim,
                       COALESCE(relation_namespace.nspname, ''),
                       COALESCE(relation.relname, ''),
                       COALESCE(element_namespace.nspname, ''),
                       COALESCE(element_type.typname, ''),
                       COALESCE(array_namespace.nspname, ''),
                       COALESCE(array_type.typname, ''),
                       object_type.typlen, object_type.typbyval,
                       object_type.typalign, object_type.typstorage,
                       object_type.typnotnull,
                       COALESCE(object_type.typacl::pg_catalog.text, ''),
                       pg_catalog.obj_description(
                           object_type.oid, 'pg_type'
                       )
                FROM pg_catalog.pg_type AS object_type
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = object_type.typnamespace
                LEFT JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = object_type.typrelid
                LEFT JOIN pg_catalog.pg_namespace AS relation_namespace
                  ON relation_namespace.oid = relation.relnamespace
                LEFT JOIN pg_catalog.pg_type AS element_type
                  ON element_type.oid = object_type.typelem
                LEFT JOIN pg_catalog.pg_namespace AS element_namespace
                  ON element_namespace.oid = element_type.typnamespace
                LEFT JOIN pg_catalog.pg_type AS array_type
                  ON array_type.oid = object_type.typarray
                LEFT JOIN pg_catalog.pg_namespace AS array_namespace
                  ON array_namespace.oid = array_type.typnamespace
                WHERE namespace.nspname = 'public'
                ORDER BY object_type.typname
                """
            )
        ).all()
    ]
    sequences = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT sequence_namespace.nspname, sequence_relation.relname,
                       pg_catalog.pg_get_userbyid(sequence_relation.relowner)
                           = current_user,
                       pg_catalog.format_type(sequence_record.seqtypid, NULL),
                       sequence_record.seqstart,
                       sequence_record.seqincrement,
                       sequence_record.seqmin,
                       sequence_record.seqmax,
                       sequence_record.seqcache,
                       sequence_record.seqcycle,
                       owned_namespace.nspname, owned_relation.relname,
                       owned_attribute.attname, dependency.deptype
                FROM pg_catalog.pg_sequence AS sequence_record
                JOIN pg_catalog.pg_class AS sequence_relation
                  ON sequence_relation.oid = sequence_record.seqrelid
                JOIN pg_catalog.pg_namespace AS sequence_namespace
                  ON sequence_namespace.oid = sequence_relation.relnamespace
                JOIN pg_catalog.pg_depend AS dependency
                  ON dependency.classid =
                         'pg_catalog.pg_class'::pg_catalog.regclass
                 AND dependency.objid = sequence_relation.oid
                 AND dependency.objsubid = 0
                 AND dependency.refclassid =
                         'pg_catalog.pg_class'::pg_catalog.regclass
                JOIN pg_catalog.pg_class AS owned_relation
                  ON owned_relation.oid = dependency.refobjid
                JOIN pg_catalog.pg_namespace AS owned_namespace
                  ON owned_namespace.oid = owned_relation.relnamespace
                JOIN pg_catalog.pg_attribute AS owned_attribute
                  ON owned_attribute.attrelid = owned_relation.oid
                 AND owned_attribute.attnum = dependency.refobjsubid
                WHERE sequence_namespace.nspname = 'public'
                  AND sequence_relation.relname =
                      'raos_migration_history_event_id_seq'
                ORDER BY sequence_namespace.nspname, sequence_relation.relname,
                         owned_namespace.nspname, owned_relation.relname,
                         owned_attribute.attname, dependency.deptype
                """
            )
        ).all()
    ]
    return {
        "columns": (len(columns), _catalog_rows_digest(columns)),
        "constraints": (len(constraints), _catalog_rows_digest(constraints)),
        "functions": (len(functions), _catalog_rows_digest(functions)),
        "relations": (len(relations), _catalog_rows_digest(relations)),
        "sequences": (len(sequences), _catalog_rows_digest(sequences)),
        "triggers": (len(triggers), _catalog_rows_digest(triggers)),
        "types": (len(types), _catalog_rows_digest(types)),
    }


def _iam_ops_catalog_digests(
    connection: Connection,
    *,
    exclude_st0304_site_foreign_key: bool = False,
) -> dict[str, tuple[int, str]]:
    columns = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       pg_catalog.obj_description(relation.oid, 'pg_class'),
                       pg_catalog.pg_get_userbyid(relation.relowner) = current_user,
                       relation.relpersistence, relation.relreplident,
                       relation.relispartition,
                       relation.relrowsecurity, relation.relforcerowsecurity,
                       attribute.attnum, attribute.attname,
                       pg_catalog.format_type(
                           attribute.atttypid, attribute.atttypmod
                       ),
                       attribute.attnotnull, attribute.attidentity,
                       attribute.attgenerated,
                       COALESCE(
                           pg_catalog.pg_get_expr(
                               attribute_default.adbin,
                               attribute_default.adrelid,
                               false
                           ),
                           ''
                       ),
                       pg_catalog.col_description(
                           attribute.attrelid, attribute.attnum
                       ),
                       COALESCE(attribute.attacl::pg_catalog.text, ''),
                       (
                           SELECT pg_catalog.count(*)
                           FROM pg_catalog.aclexplode(
                               COALESCE(
                                   relation.relacl,
                                   pg_catalog.acldefault('r', relation.relowner)
                               )
                           ) AS acl
                           WHERE acl.grantee <> relation.relowner
                       ),
                       (
                           SELECT pg_catalog.count(*)
                           FROM pg_catalog.pg_inherits AS inheritance
                           WHERE inheritance.inhrelid = relation.oid
                              OR inheritance.inhparent = relation.oid
                       )
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN pg_catalog.pg_attribute AS attribute
                  ON attribute.attrelid = relation.oid
                 AND attribute.attnum > 0
                 AND attribute.attisdropped IS FALSE
                LEFT JOIN pg_catalog.pg_attrdef AS attribute_default
                  ON attribute_default.adrelid = attribute.attrelid
                 AND attribute_default.adnum = attribute.attnum
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND relation.relkind = 'r'
                ORDER BY namespace.nspname, relation.relname, attribute.attnum
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    types = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, object_type.typname,
                       pg_catalog.pg_get_userbyid(object_type.typowner)
                           = current_user,
                       object_type.typtype, object_type.typcategory,
                       object_type.typispreferred, object_type.typisdefined,
                       object_type.typdelim,
                       COALESCE(relation_namespace.nspname, ''),
                       COALESCE(relation.relname, ''),
                       COALESCE(element_namespace.nspname, ''),
                       COALESCE(element_type.typname, ''),
                       COALESCE(array_namespace.nspname, ''),
                       COALESCE(array_type.typname, ''),
                       object_type.typlen, object_type.typbyval,
                       object_type.typalign, object_type.typstorage,
                       object_type.typnotnull,
                       COALESCE(base_namespace.nspname, ''),
                       COALESCE(base_type.typname, ''),
                       object_type.typtypmod, object_type.typndims,
                       COALESCE(collation_namespace.nspname, ''),
                       COALESCE(collation_record.collname, ''),
                       COALESCE(object_type.typacl::pg_catalog.text, ''),
                       pg_catalog.obj_description(
                           object_type.oid, 'pg_type'
                       ),
                       COALESCE(object_type.typdefault, ''),
                       COALESCE(
                           object_type.typdefaultbin::pg_catalog.text, ''
                       )
                FROM pg_catalog.pg_type AS object_type
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = object_type.typnamespace
                LEFT JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = object_type.typrelid
                LEFT JOIN pg_catalog.pg_namespace AS relation_namespace
                  ON relation_namespace.oid = relation.relnamespace
                LEFT JOIN pg_catalog.pg_type AS element_type
                  ON element_type.oid = object_type.typelem
                LEFT JOIN pg_catalog.pg_namespace AS element_namespace
                  ON element_namespace.oid = element_type.typnamespace
                LEFT JOIN pg_catalog.pg_type AS array_type
                  ON array_type.oid = object_type.typarray
                LEFT JOIN pg_catalog.pg_namespace AS array_namespace
                  ON array_namespace.oid = array_type.typnamespace
                LEFT JOIN pg_catalog.pg_type AS base_type
                  ON base_type.oid = object_type.typbasetype
                LEFT JOIN pg_catalog.pg_namespace AS base_namespace
                  ON base_namespace.oid = base_type.typnamespace
                LEFT JOIN pg_catalog.pg_collation AS collation_record
                  ON collation_record.oid = object_type.typcollation
                LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
                  ON collation_namespace.oid = collation_record.collnamespace
                WHERE namespace.nspname = ANY(
                          CAST(:schemas AS pg_catalog.text[])
                      )
                ORDER BY namespace.nspname, object_type.typname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    constraints = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       constraint_record.conname, constraint_record.contype,
                       pg_catalog.pg_get_constraintdef(
                           constraint_record.oid, false
                       ),
                       pg_catalog.obj_description(
                           constraint_record.oid, 'pg_constraint'
                       ),
                       pg_catalog.obj_description(
                           constraint_record.conindid, 'pg_class'
                       ),
                       constraint_record.condeferrable,
                       constraint_record.condeferred,
                       constraint_record.convalidated,
                       constraint_record.conenforced,
                       constraint_record.connoinherit,
                       constraint_record.conparentid,
                       constraint_record.conkey::pg_catalog.text,
                       constraint_record.confkey::pg_catalog.text,
                       COALESCE(reference_namespace.nspname, ''),
                       COALESCE(reference_relation.relname, '')
                FROM pg_catalog.pg_constraint AS constraint_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constraint_record.conrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                LEFT JOIN pg_catalog.pg_class AS reference_relation
                  ON reference_relation.oid = constraint_record.confrelid
                LEFT JOIN pg_catalog.pg_namespace AS reference_namespace
                  ON reference_namespace.oid = reference_relation.relnamespace
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND relation.relkind = 'r'
                  AND (
                      CAST(:include_site_foreign_key AS pg_catalog.bool)
                      OR constraint_record.conname <> 'fk_ops_job_site_id'
                  )
                ORDER BY namespace.nspname, relation.relname,
                         constraint_record.conname, constraint_record.contype
                """
            ),
            {
                "schemas": list(FOUNDATION_SCHEMAS),
                "include_site_foreign_key": not exclude_st0304_site_foreign_key,
            },
        ).all()
    ]
    indexes = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       index_relation.relname,
                       pg_catalog.pg_get_indexdef(index_record.indexrelid),
                       pg_catalog.obj_description(
                           index_record.indexrelid, 'pg_class'
                       ),
                       COALESCE(
                           pg_catalog.pg_get_expr(
                               index_record.indpred,
                               index_record.indrelid,
                               false
                           ),
                           ''
                       ),
                       COALESCE(
                           pg_catalog.pg_get_expr(
                               index_record.indexprs,
                               index_record.indrelid,
                               false
                           ),
                           ''
                       ),
                       index_record.indkey::pg_catalog.text,
                       index_record.indclass::pg_catalog.text,
                       index_record.indcollation::pg_catalog.text,
                       index_record.indoption::pg_catalog.text,
                       index_record.indisunique,
                       index_record.indisprimary,
                       index_record.indisexclusion,
                       index_record.indimmediate,
                       index_record.indisclustered,
                       index_record.indisvalid,
                       index_record.indcheckxmin,
                       index_record.indisready,
                       index_record.indislive,
                       index_record.indisreplident,
                       index_record.indnullsnotdistinct
                FROM pg_catalog.pg_index AS index_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = index_record.indrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN pg_catalog.pg_class AS index_relation
                  ON index_relation.oid = index_record.indexrelid
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND NOT EXISTS (
                      SELECT 1
                      FROM pg_catalog.pg_constraint AS constraint_record
                      WHERE constraint_record.conindid = index_record.indexrelid
                  )
                ORDER BY namespace.nspname, relation.relname,
                         index_relation.relname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    functions = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, routine.proname, routine.pronargs,
                       pg_catalog.pg_get_function_identity_arguments(routine.oid),
                       pg_catalog.format_type(routine.prorettype, NULL),
                       language.lanname, routine.prokind, routine.provolatile,
                       routine.prosecdef,
                       pg_catalog.array_to_string(routine.proconfig, ','),
                       routine.prosrc,
                       pg_catalog.pg_get_userbyid(routine.proowner) = current_user,
                       pg_catalog.obj_description(routine.oid, 'pg_proc'),
                       (
                           SELECT pg_catalog.count(*)
                           FROM pg_catalog.aclexplode(
                               COALESCE(
                                   routine.proacl,
                                   pg_catalog.acldefault('f', routine.proowner)
                               )
                           ) AS acl
                           WHERE acl.grantee <> routine.proowner
                       )
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                JOIN pg_catalog.pg_language AS language
                  ON language.oid = routine.prolang
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                ORDER BY namespace.nspname, routine.proname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    triggers = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       trigger_record.tgname, trigger_record.tgenabled,
                       trigger_record.tgtype,
                       trigger_record.tgfoid::pg_catalog.regprocedure::pg_catalog.text,
                       COALESCE(
                           pg_catalog.pg_get_expr(
                               trigger_record.tgqual,
                               trigger_record.tgrelid,
                               false
                           ),
                           ''
                       ),
                       trigger_record.tgnargs,
                       trigger_record.tgattr::pg_catalog.text,
                       pg_catalog.octet_length(trigger_record.tgargs),
                       trigger_record.tgconstraint,
                       trigger_record.tgdeferrable,
                       trigger_record.tginitdeferred,
                       trigger_record.tgparentid,
                       COALESCE(trigger_record.tgoldtable, ''),
                       COALESCE(trigger_record.tgnewtable, ''),
                       pg_catalog.pg_get_triggerdef(trigger_record.oid, false),
                       pg_catalog.obj_description(
                           trigger_record.oid, 'pg_trigger'
                       )
                FROM pg_catalog.pg_trigger AS trigger_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = trigger_record.tgrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND trigger_record.tgisinternal IS FALSE
                ORDER BY namespace.nspname, relation.relname,
                         trigger_record.tgname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    return {
        "columns": (len(columns), _catalog_rows_digest(columns)),
        "constraints": (len(constraints), _catalog_rows_digest(constraints)),
        "functions": (len(functions), _catalog_rows_digest(functions)),
        "indexes": (len(indexes), _catalog_rows_digest(indexes)),
        "triggers": (len(triggers), _catalog_rows_digest(triggers)),
        "types": (len(types), _catalog_rows_digest(types)),
    }


def _selected_domain_catalog_digests(
    connection: Connection,
    schemas: Sequence[str],
) -> dict[str, tuple[int, str]]:
    rows = connection.execute(
        sa.text(
            """
            WITH selected(schema_name) AS (
                SELECT pg_catalog.unnest(CAST(:schemas AS pg_catalog.text[]))
            ),
            relation_rows AS (
                SELECT pg_catalog.concat_ws(
                           E'\\x1f', namespace.nspname, relation.relname,
                           relation.relkind, relation.relpersistence,
                           relation.relreplident, relation.relrowsecurity,
                           relation.relforcerowsecurity,
                           COALESCE(
                               pg_catalog.array_to_string(
                                   relation.reloptions, E'\\x1d'
                               ),
                               '<NULL>'
                           ),
                           COALESCE(
                               pg_catalog.obj_description(
                                   relation.oid, 'pg_class'
                               ),
                               '<NULL>'
                           )
                       ) AS row_value
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN selected ON selected.schema_name = namespace.nspname
                WHERE relation.relkind IN ('r', 'v')
            ),
            column_rows AS (
                SELECT pg_catalog.concat_ws(
                           E'\\x1f', namespace.nspname, relation.relname,
                           attribute.attnum, attribute.attname,
                           pg_catalog.format_type(
                               attribute.atttypid, attribute.atttypmod
                           ),
                           attribute.attnotnull, attribute.attidentity,
                           attribute.attgenerated, attribute.attisdropped,
                           COALESCE(
                               pg_catalog.pg_get_expr(
                                   attribute_default.adbin,
                                   attribute_default.adrelid,
                                   false
                               ),
                               '<NULL>'
                           ),
                           COALESCE(
                               collation_namespace.nspname || '.'
                               || collation_record.collname,
                               '<NULL>'
                           ),
                           attribute.attstorage, attribute.attcompression,
                           attribute.attstattarget,
                           COALESCE(
                               pg_catalog.col_description(
                                   relation.oid, attribute.attnum
                               ),
                               '<NULL>'
                           )
                       ) AS row_value
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN selected ON selected.schema_name = namespace.nspname
                JOIN pg_catalog.pg_attribute AS attribute
                  ON attribute.attrelid = relation.oid
                 AND attribute.attnum > 0
                LEFT JOIN pg_catalog.pg_attrdef AS attribute_default
                  ON attribute_default.adrelid = relation.oid
                 AND attribute_default.adnum = attribute.attnum
                LEFT JOIN pg_catalog.pg_collation AS collation_record
                  ON collation_record.oid = attribute.attcollation
                LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
                  ON collation_namespace.oid = collation_record.collnamespace
                WHERE relation.relkind = 'r'
            ),
            constraint_rows AS (
                SELECT pg_catalog.concat_ws(
                           E'\\x1f', namespace.nspname, relation.relname,
                           constraint_record.conname,
                           constraint_record.contype,
                           constraint_record.condeferrable,
                           constraint_record.condeferred,
                           constraint_record.convalidated,
                           constraint_record.connoinherit,
                           constraint_record.confmatchtype,
                           constraint_record.confupdtype,
                           constraint_record.confdeltype,
                           COALESCE(
                               pg_catalog.pg_get_constraintdef(
                                   constraint_record.oid, false
                               ),
                               '<NULL>'
                           )
                       ) AS row_value
                FROM pg_catalog.pg_constraint AS constraint_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constraint_record.conrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN selected ON selected.schema_name = namespace.nspname
                WHERE constraint_record.contype IN ('c', 'f', 'n', 'p', 'u')
            ),
            index_rows AS (
                SELECT pg_catalog.concat_ws(
                           E'\\x1f', namespace.nspname,
                           table_record.relname, index_record.relname,
                           index_catalog.indisunique,
                           index_catalog.indisprimary,
                           index_catalog.indisexclusion,
                           index_catalog.indimmediate,
                           index_catalog.indisclustered,
                           index_catalog.indisvalid,
                           index_catalog.indisready,
                           index_catalog.indislive,
                           index_catalog.indisreplident,
                           index_catalog.indnullsnotdistinct,
                           index_catalog.indnkeyatts,
                           index_catalog.indnatts,
                           index_catalog.indkey::pg_catalog.text,
                           index_catalog.indcollation::pg_catalog.text,
                           index_catalog.indclass::pg_catalog.text,
                           index_catalog.indoption::pg_catalog.text,
                           pg_catalog.pg_get_indexdef(
                               index_record.oid, 0, false
                           ),
                           COALESCE(
                               pg_catalog.pg_get_expr(
                                   index_catalog.indpred,
                                   index_catalog.indrelid,
                                   false
                               ),
                               '<NULL>'
                           ),
                           COALESCE(
                               pg_catalog.pg_get_expr(
                                   index_catalog.indexprs,
                                   index_catalog.indrelid,
                                   false
                               ),
                               '<NULL>'
                           ),
                           COALESCE(
                               pg_catalog.obj_description(
                                   index_record.oid, 'pg_class'
                               ),
                               '<NULL>'
                           )
                       ) AS row_value
                FROM pg_catalog.pg_index AS index_catalog
                JOIN pg_catalog.pg_class AS index_record
                  ON index_record.oid = index_catalog.indexrelid
                JOIN pg_catalog.pg_class AS table_record
                  ON table_record.oid = index_catalog.indrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = table_record.relnamespace
                JOIN selected ON selected.schema_name = namespace.nspname
            ),
            function_rows AS (
                SELECT pg_catalog.concat_ws(
                           E'\\x1f', namespace.nspname, routine.proname,
                           pg_catalog.pg_get_function_identity_arguments(
                               routine.oid
                           ),
                           pg_catalog.pg_get_function_result(routine.oid),
                           language_record.lanname, routine.provolatile,
                           routine.proisstrict, routine.prosecdef,
                           routine.proleakproof, routine.proparallel,
                           COALESCE(
                               pg_catalog.array_to_string(
                                   routine.proconfig, E'\\x1d'
                               ),
                               '<NULL>'
                           ),
                           pg_catalog.pg_get_functiondef(routine.oid),
                           COALESCE(
                               pg_catalog.obj_description(
                                   routine.oid, 'pg_proc'
                               ),
                               '<NULL>'
                           )
                       ) AS row_value
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                JOIN selected ON selected.schema_name = namespace.nspname
                JOIN pg_catalog.pg_language AS language_record
                  ON language_record.oid = routine.prolang
                WHERE routine.prokind = 'f'
            ),
            trigger_rows AS (
                SELECT pg_catalog.concat_ws(
                           E'\\x1f', namespace.nspname, relation.relname,
                           trigger_record.tgname, trigger_record.tgtype,
                           trigger_record.tgenabled,
                           trigger_record.tgisinternal,
                           routine_namespace.nspname, routine.proname,
                           pg_catalog.pg_get_function_identity_arguments(
                               routine.oid
                           ),
                           pg_catalog.pg_get_triggerdef(
                               trigger_record.oid, false
                           ),
                           COALESCE(
                               pg_catalog.pg_get_expr(
                                   trigger_record.tgqual,
                                   trigger_record.tgrelid,
                                   false
                               ),
                               '<NULL>'
                           ),
                           COALESCE(
                               pg_catalog.obj_description(
                                   trigger_record.oid, 'pg_trigger'
                               ),
                               '<NULL>'
                           )
                       ) AS row_value
                FROM pg_catalog.pg_trigger AS trigger_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = trigger_record.tgrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN selected ON selected.schema_name = namespace.nspname
                JOIN pg_catalog.pg_proc AS routine
                  ON routine.oid = trigger_record.tgfoid
                JOIN pg_catalog.pg_namespace AS routine_namespace
                  ON routine_namespace.oid = routine.pronamespace
                WHERE trigger_record.tgisinternal IS FALSE
            ),
            observed(kind, object_count, digest) AS (
                SELECT 'relations', pg_catalog.count(*),
                       pg_catalog.md5(
                           pg_catalog.string_agg(
                               row_value, E'\\x1e' ORDER BY row_value
                           )
                       )
                FROM relation_rows
                UNION ALL
                SELECT 'columns', pg_catalog.count(*),
                       pg_catalog.md5(
                           pg_catalog.string_agg(
                               row_value, E'\\x1e' ORDER BY row_value
                           )
                       )
                FROM column_rows
                UNION ALL
                SELECT 'constraints', pg_catalog.count(*),
                       pg_catalog.md5(
                           pg_catalog.string_agg(
                               row_value, E'\\x1e' ORDER BY row_value
                           )
                       )
                FROM constraint_rows
                UNION ALL
                SELECT 'indexes', pg_catalog.count(*),
                       pg_catalog.md5(
                           pg_catalog.string_agg(
                               row_value, E'\\x1e' ORDER BY row_value
                           )
                       )
                FROM index_rows
                UNION ALL
                SELECT 'functions', pg_catalog.count(*),
                       pg_catalog.md5(
                           pg_catalog.string_agg(
                               row_value, E'\\x1e' ORDER BY row_value
                           )
                       )
                FROM function_rows
                UNION ALL
                SELECT 'triggers', pg_catalog.count(*),
                       pg_catalog.md5(
                           pg_catalog.string_agg(
                               row_value, E'\\x1e' ORDER BY row_value
                           )
                       )
                FROM trigger_rows
            )
            SELECT kind, object_count, digest
            FROM observed
            ORDER BY kind
            """
        ),
        {"schemas": list(schemas)},
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _st0304_catalog_digests(connection: Connection) -> dict[str, tuple[int, str]]:
    return _selected_domain_catalog_digests(connection, ST0304_SCHEMAS)


def _validate_iam_ops_shape(connection: Connection, current_revision: str) -> None:
    revision_ids = [item.revision for item in REVISION_SPECS]
    if IAM_OPS_REVISION not in revision_ids:
        return
    current_index = revision_ids.index(current_revision)
    if current_index < revision_ids.index(IAM_OPS_REVISION):
        return

    includes_st0304_site_foreign_key = (
        DOMAIN_REVISION in revision_ids
        and current_index >= revision_ids.index(DOMAIN_REVISION)
    )
    includes_st0305_foreign_keys = (
        PUBLICATION_ANALYTICS_FINANCE_REVISION in revision_ids
        and current_index >= revision_ids.index(PUBLICATION_ANALYTICS_FINANCE_REVISION)
    )
    owner = connection.execute(sa.text("SELECT current_user")).scalar_one()
    table_rows = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname, relation.relname,
                       columns.column_shape,
                       pg_catalog.pg_get_userbyid(relation.relowner),
                       relation.relpersistence, relation.relreplident,
                       relation.relispartition,
                       relation.relrowsecurity, relation.relforcerowsecurity,
                       (
                           SELECT pg_catalog.count(*)
                           FROM pg_catalog.aclexplode(
                               COALESCE(
                                   relation.relacl,
                                   pg_catalog.acldefault('r', relation.relowner)
                               )
                           ) AS acl
                           WHERE acl.grantee <> relation.relowner
                       )
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                CROSS JOIN LATERAL (
                    SELECT pg_catalog.string_agg(
                               attribute.attname
                               || CASE
                                      WHEN attribute.attnotnull THEN '!'
                                      ELSE '?'
                                  END,
                               ',' ORDER BY attribute.attnum
                           ) AS column_shape
                    FROM pg_catalog.pg_attribute AS attribute
                    WHERE attribute.attrelid = relation.oid
                      AND attribute.attnum > 0
                      AND attribute.attisdropped IS FALSE
                ) AS columns
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND relation.relkind = 'r'
                ORDER BY namespace.nspname, relation.relname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    observed_tables = {(row[0], row[1], row[2]) for row in table_rows}
    if observed_tables != set(_IAM_OPS_TABLE_SHAPE) or any(
        row[3:] != (owner, "p", "d", False, False, False, 0) for row in table_rows
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    unexpected_object_count = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_class AS relation
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                   AND (
                       relation.relkind NOT IN ('r', 'i')
                       OR pg_catalog.pg_get_userbyid(relation.relowner)
                          <> current_user
                       OR relation.relpersistence <> 'p'
                       OR relation.relispartition IS TRUE
                   ))
                +
                (SELECT CASE WHEN pg_catalog.count(*) = 95 THEN 0 ELSE 1 END
                 FROM pg_catalog.pg_class AS relation
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_type AS object_type
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_type.typnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                   AND NOT EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_class AS relation
                       JOIN pg_catalog.pg_type AS row_type
                         ON row_type.oid = relation.reltype
                       WHERE relation.relnamespace = namespace.oid
                         AND relation.relkind = 'r'
                         AND (
                             object_type.oid = relation.reltype
                             OR object_type.oid = row_type.typarray
                         )
                   ))
                +
                (SELECT CASE WHEN pg_catalog.count(*) = 34 THEN 0 ELSE 1 END
                 FROM pg_catalog.pg_type AS object_type
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = object_type.typnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_attribute AS attribute
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = attribute.attrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                   AND relation.relkind = 'r'
                   AND attribute.attnum > 0
                   AND attribute.attisdropped IS TRUE)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_rewrite AS rewrite_record
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = rewrite_record.ev_class
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_policy AS policy_record
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = policy_record.polrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_collation AS collation_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = collation_record.collnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_conversion AS conversion_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = conversion_record.connamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_operator AS operator_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = operator_record.oprnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_opclass AS operator_class
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = operator_class.opcnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_opfamily AS operator_family
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = operator_family.opfnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_config AS search_configuration
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = search_configuration.cfgnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_dict AS search_dictionary
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = search_dictionary.dictnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_parser AS search_parser
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = search_parser.prsnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_ts_template AS search_template
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = search_template.tmplnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_statistic_ext AS statistics_record
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = statistics_record.stxnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_cast AS cast_record
                 JOIN pg_catalog.pg_type AS source_type
                   ON source_type.oid = cast_record.castsource
                 JOIN pg_catalog.pg_namespace AS source_namespace
                   ON source_namespace.oid = source_type.typnamespace
                 JOIN pg_catalog.pg_type AS target_type
                   ON target_type.oid = cast_record.casttarget
                 JOIN pg_catalog.pg_namespace AS target_namespace
                   ON target_namespace.oid = target_type.typnamespace
                 WHERE source_namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                    OR target_namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_transform AS transform_record
                 JOIN pg_catalog.pg_type AS managed_type
                   ON managed_type.oid = transform_record.trftype
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = managed_type.typnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_amop AS operator_record
                 JOIN pg_catalog.pg_type AS left_type
                   ON left_type.oid = operator_record.amoplefttype
                 JOIN pg_catalog.pg_namespace AS left_namespace
                   ON left_namespace.oid = left_type.typnamespace
                 JOIN pg_catalog.pg_type AS right_type
                   ON right_type.oid = operator_record.amoprighttype
                 JOIN pg_catalog.pg_namespace AS right_namespace
                   ON right_namespace.oid = right_type.typnamespace
                 WHERE left_namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                    OR right_namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_amproc AS procedure_record
                 JOIN pg_catalog.pg_type AS left_type
                   ON left_type.oid = procedure_record.amproclefttype
                 JOIN pg_catalog.pg_namespace AS left_namespace
                   ON left_namespace.oid = left_type.typnamespace
                 JOIN pg_catalog.pg_type AS right_type
                   ON right_type.oid = procedure_record.amprocrighttype
                 JOIN pg_catalog.pg_namespace AS right_namespace
                   ON right_namespace.oid = right_type.typnamespace
                 WHERE left_namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                    OR right_namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_publication)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_publication_namespace)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_publication_rel)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_subscription AS subscription
                 JOIN pg_catalog.pg_database AS database_record
                   ON database_record.oid = subscription.subdbid
                 WHERE database_record.datname =
                       pg_catalog.current_database())
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_largeobject_metadata)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_foreign_data_wrapper)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_foreign_server)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_inherits AS inheritance
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid IN (
                       inheritance.inhrelid, inheritance.inhparent
                   )
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_partitioned_table AS partitioned
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = partitioned.partrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       ))
                +
                (SELECT CASE
                            WHEN pg_catalog.count(*) =
                                 CAST(:internal_trigger_count AS pg_catalog.int8)
                            THEN 0
                            ELSE 1
                        END
                 FROM pg_catalog.pg_trigger AS trigger_record
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = trigger_record.tgrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                   AND trigger_record.tgisinternal IS TRUE)
                +
                (SELECT pg_catalog.count(*)
                 FROM pg_catalog.pg_trigger AS trigger_record
                 JOIN pg_catalog.pg_class AS relation
                   ON relation.oid = trigger_record.tgrelid
                 JOIN pg_catalog.pg_namespace AS namespace
                   ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = ANY(
                           CAST(:schemas AS pg_catalog.text[])
                       )
                   AND trigger_record.tgisinternal IS TRUE
                   AND (
                       trigger_record.tgenabled <> 'O'
                       OR trigger_record.tgconstraint = 0
                       OR trigger_record.tgparentid <> 0
                       OR pg_catalog.obj_description(
                              trigger_record.oid, 'pg_trigger'
                          ) IS NOT NULL
                   ))
            """
        ),
        {
            "schemas": list(FOUNDATION_SCHEMAS),
            "internal_trigger_count": (
                300
                if includes_st0305_foreign_keys
                else (226 if includes_st0304_site_foreign_key else 80)
            ),
        },
    ).scalar_one()
    if unexpected_object_count != 0:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    constraint_counts: dict[str, int] = {
        row[0]: row[1]
        for row in connection.execute(
            sa.text(
                """
                SELECT constraint_record.contype, pg_catalog.count(*)
                FROM pg_catalog.pg_constraint AS constraint_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constraint_record.conrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND relation.relkind = 'r'
                GROUP BY constraint_record.contype
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    }
    invalid_constraints = connection.execute(
        sa.text(
            """
            SELECT pg_catalog.count(*)
            FROM pg_catalog.pg_constraint AS constraint_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = constraint_record.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            LEFT JOIN pg_catalog.pg_class AS constraint_index_relation
              ON constraint_index_relation.oid = constraint_record.conindid
            LEFT JOIN pg_catalog.pg_index AS constraint_index
              ON constraint_index.indexrelid = constraint_record.conindid
            WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
              AND relation.relkind = 'r'
              AND (
                  constraint_record.convalidated IS FALSE
                  OR constraint_record.conenforced IS FALSE
                  OR constraint_record.condeferrable IS TRUE
                  OR constraint_record.condeferred IS TRUE
                  OR constraint_record.conparentid <> 0
                  OR constraint_record.connoinherit IS DISTINCT FROM
                     (constraint_record.contype::pg_catalog.text = ANY(
                         ARRAY['p', 'u', 'f']::pg_catalog.text[]
                     ))
                  OR (
                      constraint_record.contype::pg_catalog.text = ANY(
                          ARRAY['p', 'u']::pg_catalog.text[]
                      )
                      AND (
                          constraint_record.conindid = 0
                          OR constraint_index_relation.relkind
                             IS DISTINCT FROM 'i'
                          OR constraint_index_relation.relnamespace
                             IS DISTINCT FROM constraint_record.connamespace
                          OR constraint_index_relation.relname
                             IS DISTINCT FROM constraint_record.conname
                          OR constraint_index.indrelid
                             IS DISTINCT FROM constraint_record.conrelid
                          OR constraint_index.indisunique IS DISTINCT FROM TRUE
                          OR constraint_index.indisvalid IS DISTINCT FROM TRUE
                          OR constraint_index.indisready IS DISTINCT FROM TRUE
                          OR constraint_index.indisprimary IS DISTINCT FROM
                             (constraint_record.contype = 'p')
                      )
                  )
                  OR (
                      constraint_record.contype = 'f'
                      AND (
                          constraint_record.conindid = 0
                          OR constraint_index_relation.relkind
                             IS DISTINCT FROM 'i'
                          OR constraint_index.indrelid
                             IS DISTINCT FROM constraint_record.confrelid
                          OR constraint_index.indisunique IS DISTINCT FROM TRUE
                          OR constraint_index.indisvalid IS DISTINCT FROM TRUE
                          OR constraint_index.indisready IS DISTINCT FROM TRUE
                      )
                  )
                  OR (
                      constraint_record.contype::pg_catalog.text = ANY(
                          ARRAY['c', 'n']::pg_catalog.text[]
                      )
                      AND constraint_record.conindid <> 0
                  )
              )
            """
        ),
        {"schemas": list(FOUNDATION_SCHEMAS)},
    ).scalar_one()
    foreign_key_actions = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT constraint_record.conname, constraint_record.confdeltype
                FROM pg_catalog.pg_constraint AS constraint_record
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constraint_record.conrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                  AND relation.relkind = 'r'
                  AND constraint_record.contype = 'f'
                  AND constraint_record.confupdtype = 'a'
                  AND constraint_record.confmatchtype = 's'
                ORDER BY constraint_record.conname
                """
            ),
            {"schemas": list(FOUNDATION_SCHEMAS)},
        ).all()
    ]
    expected_constraint_counts = dict(_IAM_OPS_CONSTRAINT_COUNTS)
    expected_foreign_key_actions = list(_IAM_OPS_FOREIGN_KEY_DELETE_ACTIONS)
    deferred_foreign_keys = list(_IAM_OPS_DEFERRED_FOREIGN_KEYS)
    if includes_st0304_site_foreign_key:
        expected_constraint_counts["f"] += 1
        expected_foreign_key_actions.append(("fk_ops_job_site_id", "r"))
        deferred_foreign_keys.remove(("fk_ops_job_site_id", "ops.ix_ops_job_site_id"))
    if (
        constraint_counts != expected_constraint_counts
        or invalid_constraints != 0
        or foreign_key_actions != sorted(expected_foreign_key_actions)
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    for constraint_name, index_name in deferred_foreign_keys:
        deferred_shape = connection.execute(
            sa.text(
                """
                SELECT NOT EXISTS (
                           SELECT 1
                           FROM pg_catalog.pg_constraint
                           WHERE conname = :constraint_name
                       ),
                       pg_catalog.to_regclass(:index_name) IS NOT NULL
                """
            ),
            {"constraint_name": constraint_name, "index_name": index_name},
        ).one()
        if tuple(deferred_shape) != (True, True):
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    # Exact catalog hashes are version-specific PostgreSQL 18.4 fingerprints.
    expected_digests = {
        "columns": (
            219,
            "b967aacacffab3c2c064748105ca2d5d26a2083c69512f77d41813872ebf6472",
        ),
        "constraints": (
            267,
            "42badc67dd6cf74d40ed5ebec0eb3c9ac26739279d0f7a0fd84a68102ce3108e",
        ),
        "functions": (
            2,
            "12c201c731b358d156a332cfc4dc7c6c9cdd212760e415f9f2b7e2395bf0f17a",
        ),
        "indexes": (
            48,
            "b9215cb5d7efeba08c0e2b48659693adafab8bffbd4bbb5737b05be645633322",
        ),
        "triggers": (
            4,
            "9cf7aa1fa82cd05f2a7e2c205396ca53f4304fbe363e3ad0345a6d14e9f7c29d",
        ),
        "types": (
            34,
            "f767f9a16fea954ed0e1d83548dd8ce8f3ad59bff91bf8ba3fa634cc9883e039",
        ),
    }
    observed_digests = _iam_ops_catalog_digests(
        connection,
        exclude_st0304_site_foreign_key=includes_st0304_site_foreign_key,
    )
    if observed_digests != expected_digests:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _validate_st0304_shape(connection: Connection, current_revision: str) -> None:
    revision_ids = [item.revision for item in REVISION_SPECS]
    if DOMAIN_REVISION not in revision_ids:
        return
    if revision_ids.index(current_revision) < revision_ids.index(DOMAIN_REVISION):
        return

    owner = connection.execute(sa.text("SELECT current_user")).scalar_one()
    schema_rows = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname,
                       pg_catalog.pg_get_userbyid(namespace.nspowner),
                       pg_catalog.obj_description(
                           namespace.oid, 'pg_namespace'
                       ),
                       COALESCE(
                           (
                               SELECT pg_catalog.array_agg(
                                          acl.privilege_type
                                          ORDER BY acl.privilege_type
                                      )
                               FROM pg_catalog.aclexplode(
                                   COALESCE(
                                       namespace.nspacl,
                                       pg_catalog.acldefault(
                                           'n', namespace.nspowner
                                       )
                                   )
                               ) AS acl
                               WHERE acl.grantee = namespace.nspowner
                           ),
                           ARRAY[]::pg_catalog.text[]
                       ),
                       (
                           SELECT pg_catalog.count(*)
                           FROM pg_catalog.aclexplode(
                               COALESCE(
                                   namespace.nspacl,
                                   pg_catalog.acldefault(
                                       'n', namespace.nspowner
                                   )
                               )
                           ) AS acl
                           WHERE acl.grantee <> namespace.nspowner
                       )
                FROM pg_catalog.pg_namespace AS namespace
                WHERE namespace.nspname = ANY(
                          CAST(:schemas AS pg_catalog.text[])
                      )
                ORDER BY namespace.nspname
                """
            ),
            {"schemas": list(ST0304_SCHEMAS)},
        ).all()
    ]
    expected_schema_rows = [
        (name, owner, ST0304_SCHEMA_COMMENTS[name], ["CREATE", "USAGE"], 0)
        for name in sorted(ST0304_SCHEMAS)
    ]
    if schema_rows != expected_schema_rows:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    object_acl_shape = tuple(
        connection.execute(
            sa.text(
                """
                SELECT
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_class AS relation
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                          AND relation.relkind IN ('r', 'v')
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_class AS relation
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                          AND relation.relkind IN ('r', 'v')
                          AND pg_catalog.pg_get_userbyid(relation.relowner)
                              <> current_user
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_class AS relation
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        CROSS JOIN LATERAL pg_catalog.aclexplode(
                            COALESCE(
                                relation.relacl,
                                pg_catalog.acldefault('r', relation.relowner)
                            )
                        ) AS acl
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                          AND relation.relkind IN ('r', 'v')
                          AND acl.grantee <> relation.relowner
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_proc AS routine
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = routine.pronamespace
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                          AND routine.prokind = 'f'
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_proc AS routine
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = routine.pronamespace
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                          AND routine.prokind = 'f'
                          AND pg_catalog.pg_get_userbyid(routine.proowner)
                              <> current_user
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_proc AS routine
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = routine.pronamespace
                        CROSS JOIN LATERAL pg_catalog.aclexplode(
                            COALESCE(
                                routine.proacl,
                                pg_catalog.acldefault('f', routine.proowner)
                            )
                        ) AS acl
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                          AND routine.prokind = 'f'
                          AND acl.grantee <> routine.proowner
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_default_acl AS defaults
                        LEFT JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = defaults.defaclnamespace
                        WHERE defaults.defaclnamespace = 0
                           OR namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                    )
                """
            ),
            {"schemas": list(ST0304_SCHEMAS)},
        ).one()
    )
    if object_acl_shape != (87, 0, 0, 48, 0, 0, 0):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    if _st0304_catalog_digests(connection) != _ST0304_CATALOG_DIGESTS:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    rls_rows = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname || '.' || relation.relname,
                       relation.relrowsecurity,
                       relation.relforcerowsecurity
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = ANY(
                          CAST(:schemas AS pg_catalog.text[])
                      )
                  AND relation.relkind = 'r'
                  AND (
                      relation.relrowsecurity IS TRUE
                      OR relation.relforcerowsecurity IS TRUE
                  )
                ORDER BY namespace.nspname, relation.relname
                """
            ),
            {"schemas": list(ST0304_SCHEMAS)},
        ).all()
    ]
    expected_rls_rows = [(name, True, True) for name in sorted(ST0304_RLS_TABLES)]
    if rls_rows != expected_rls_rows:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    boundary_shape = tuple(
        connection.execute(
            sa.text(
                """
                SELECT
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_policy AS policy_record
                        JOIN pg_catalog.pg_class AS relation
                          ON relation.oid = policy_record.polrelid
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = ANY(
                                  CAST(:schemas AS pg_catalog.text[])
                              )
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_constraint AS constraint_record
                        WHERE constraint_record.conname =
                                  'fk_ops_job_site_id'
                          AND constraint_record.conrelid =
                                  'ops.job'::pg_catalog.regclass
                          AND constraint_record.confrelid =
                                  'portfolio.site'::pg_catalog.regclass
                          AND constraint_record.contype = 'f'
                          AND constraint_record.convalidated IS TRUE
                          AND constraint_record.condeferrable IS FALSE
                          AND constraint_record.condeferred IS FALSE
                          AND constraint_record.confupdtype = 'a'
                          AND constraint_record.confdeltype = 'r'
                          AND constraint_record.confmatchtype = 's'
                          AND pg_catalog.pg_get_constraintdef(
                                  constraint_record.oid, false
                              ) =
                              'FOREIGN KEY (site_id) REFERENCES '
                              'portfolio.site(id) ON DELETE RESTRICT'
                    ),
                    (
                        SELECT pg_catalog.count(*)
                        FROM pg_catalog.pg_constraint
                        WHERE conname =
                              'fk_iam_break_glass_record_incident_id'
                    )
                """
            ),
            {"schemas": list(ST0304_SCHEMAS)},
        ).one()
    )
    if boundary_shape != (0, 1, 0):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _validate_st0305_shape(connection: Connection, current_revision: str) -> None:
    if current_revision != PUBLICATION_ANALYTICS_FINANCE_REVISION:
        return

    owner = connection.execute(sa.text("SELECT current_user")).scalar_one()
    schema_rows = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT namespace.nspname,
                       pg_catalog.pg_get_userbyid(namespace.nspowner),
                       pg_catalog.obj_description(namespace.oid, 'pg_namespace'),
                       COALESCE(
                           (SELECT pg_catalog.array_agg(
                                       acl.privilege_type ORDER BY acl.privilege_type
                                   )
                            FROM pg_catalog.aclexplode(
                                COALESCE(
                                    namespace.nspacl,
                                    pg_catalog.acldefault('n', namespace.nspowner)
                                )
                            ) AS acl
                            WHERE acl.grantee = namespace.nspowner),
                           ARRAY[]::pg_catalog.text[]
                       ),
                       (SELECT pg_catalog.count(*)
                        FROM pg_catalog.aclexplode(
                            COALESCE(
                                namespace.nspacl,
                                pg_catalog.acldefault('n', namespace.nspowner)
                            )
                        ) AS acl
                        WHERE acl.grantee <> namespace.nspowner)
                FROM pg_catalog.pg_namespace AS namespace
                WHERE namespace.nspname = ANY(
                    CAST(:schemas AS pg_catalog.text[])
                )
                ORDER BY namespace.nspname
                """
            ),
            {"schemas": list(ST0305_SCHEMAS)},
        ).all()
    ]
    if schema_rows != [
        (name, owner, ST0305_SCHEMA_COMMENTS[name], ["CREATE", "USAGE"], 0)
        for name in sorted(ST0305_SCHEMAS)
    ]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    inventory = tuple(
        connection.execute(
            sa.text(
                """
                WITH selected AS (
                    SELECT oid FROM pg_catalog.pg_namespace
                    WHERE nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                )
                SELECT
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class
                     WHERE relnamespace IN (SELECT oid FROM selected)
                       AND relkind = 'r'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS a
                     JOIN pg_catalog.pg_class AS r ON r.oid = a.attrelid
                     WHERE r.relnamespace IN (SELECT oid FROM selected)
                       AND r.relkind = 'r' AND a.attnum > 0
                       AND a.attisdropped IS FALSE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS a
                     JOIN pg_catalog.pg_class AS r ON r.oid = a.attrelid
                     WHERE r.relnamespace IN (SELECT oid FROM selected)
                       AND r.relkind = 'r' AND a.attnum > 0
                       AND a.attisdropped IS FALSE AND a.attnotnull IS TRUE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype = 'p'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype = 'u'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype = 'c'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype = 'f'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_index AS i
                     JOIN pg_catalog.pg_class AS r ON r.oid = i.indrelid
                     WHERE r.relnamespace IN (SELECT oid FROM selected)
                       AND NOT EXISTS (
                           SELECT 1 FROM pg_catalog.pg_constraint
                           WHERE conindid = i.indexrelid
                       )),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_index AS i
                     JOIN pg_catalog.pg_class AS r ON r.oid = i.indrelid
                     WHERE r.relnamespace IN (SELECT oid FROM selected)),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc
                     WHERE pronamespace IN (SELECT oid FROM selected)
                       AND prokind = 'f'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger AS t
                     JOIN pg_catalog.pg_class AS r ON r.oid = t.tgrelid
                     WHERE r.relnamespace IN (SELECT oid FROM selected)
                       AND t.tgisinternal IS FALSE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class
                     WHERE relnamespace IN (SELECT oid FROM selected)
                       AND relispartition IS TRUE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class
                     WHERE relnamespace IN (SELECT oid FROM selected)
                       AND relkind = 'r' AND relrowsecurity IS TRUE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class
                     WHERE relnamespace IN (SELECT oid FROM selected)
                       AND relkind = 'r' AND relforcerowsecurity IS TRUE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_policy AS p
                     JOIN pg_catalog.pg_class AS r ON r.oid = p.polrelid
                     WHERE r.relnamespace IN (SELECT oid FROM selected))
                """
            ),
            {"schemas": list(ST0305_SCHEMAS)},
        ).one()
    )
    if inventory != (
        39,
        629,
        447,
        39,
        47,
        172,
        150,
        153,
        239,
        3,
        17,
        0,
        0,
        0,
        0,
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    acl_shape = tuple(
        connection.execute(
            sa.text(
                """
                SELECT
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class AS r
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = r.relnamespace
                     WHERE n.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                       AND r.relkind = 'r'
                       AND pg_catalog.pg_get_userbyid(r.relowner) <> current_user),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class AS r
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = r.relnamespace
                     CROSS JOIN LATERAL pg_catalog.aclexplode(
                         COALESCE(r.relacl, pg_catalog.acldefault('r', r.relowner))
                     ) AS acl
                     WHERE n.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                       AND r.relkind = 'r' AND acl.grantee <> r.relowner),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc AS p
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                     WHERE n.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                       AND p.prokind = 'f'
                       AND (pg_catalog.pg_get_userbyid(p.proowner) <> current_user
                            OR p.prosecdef IS TRUE
                            OR p.proconfig IS DISTINCT FROM
                               ARRAY['search_path=pg_catalog']::pg_catalog.text[])),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc AS p
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                     CROSS JOIN LATERAL pg_catalog.aclexplode(
                         COALESCE(p.proacl, pg_catalog.acldefault('f', p.proowner))
                     ) AS acl
                     WHERE n.nspname = ANY(CAST(:schemas AS pg_catalog.text[]))
                       AND p.prokind = 'f' AND acl.grantee <> p.proowner),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_default_acl AS d
                     LEFT JOIN pg_catalog.pg_namespace AS n
                       ON n.oid = d.defaclnamespace
                     WHERE d.defaclnamespace = 0
                        OR n.nspname = ANY(CAST(:schemas AS pg_catalog.text[])))
                """
            ),
            {"schemas": list(ST0305_SCHEMAS)},
        ).one()
    )
    if acl_shape != (0, 0, 0, 0, 0):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    boundary = tuple(
        connection.execute(
            sa.text(
                """
                SELECT
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
                     WHERE conname = ANY(CAST(:deferred AS pg_catalog.text[]))),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
                     WHERE conname = ANY(CAST(:cyclic AS pg_catalog.text[]))
                       AND contype = 'f' AND condeferrable IS TRUE
                       AND condeferred IS TRUE),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS a
                     JOIN pg_catalog.pg_class AS r ON r.oid = a.attrelid
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = r.relnamespace
                     WHERE n.nspname IN ('readmodel', 'editorial')
                       AND a.attnum > 0 AND a.attisdropped IS FALSE
                       AND a.attname ~ '(affiliate_rate|commission|revenue|profit|epc|rpm)'),
                    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS a
                     JOIN pg_catalog.pg_class AS r ON r.oid = a.attrelid
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = r.relnamespace
                     WHERE n.nspname = 'analytics'
                       AND r.relname IN ('anonymous_event','affiliate_click_event')
                       AND a.attnum > 0 AND a.attisdropped IS FALSE
                       AND a.attname = ANY(ARRAY[
                           'raw_ip','ip_address','full_user_agent','user_agent',
                           'email','raw_search_query','url_query','free_form_identifier'
                       ]))
                """
            ),
            {
                "deferred": [
                    "fk_publishing_publication_event_release_id",
                    "fk_publishing_rollback_record_incident_id",
                    "fk_iam_break_glass_record_incident_id",
                ],
                "cyclic": [
                    "fk_publishing_publication_candidate_publication_snapshot_id",
                    "fk_publishing_publication_snapshot_publication_candidate_id",
                    "fk_publishing_publication_current_route_id",
                    "fk_publishing_public_route_publication_id",
                ],
            },
        ).one()
    )
    if boundary != (0, 4, 0, 0):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    if (
        _selected_domain_catalog_digests(connection, ST0305_SCHEMAS)
        != _ST0305_CATALOG_DIGESTS
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _validate_installed_unchecked(
    connection: Connection,
    current_revision: str,
    *,
    allow_open: bool = False,
    allow_foundation_objects: bool = False,
) -> _OpenAttempt | None:
    if _current_heads(connection) != (current_revision,):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    version_rows = (
        connection.execute(
            sa.text(
                "SELECT version_num FROM public.raos_migration_version ORDER BY version_num"
            )
        )
        .scalars()
        .all()
    )
    if version_rows != [current_revision]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    open_attempt = _analyze_history(
        _history_rows(connection), current_revision, allow_open=allow_open
    )
    _validate_metadata_shape(connection)
    _validate_current_head_boundary(connection, current_revision)
    domain_schema_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM pg_catalog.pg_namespace
            WHERE nspname = ANY(CAST(:schemas AS text[]))
            """
        ),
        {"schemas": list(DOMAIN_SCHEMAS)},
    ).scalar_one()
    if current_revision == ANCHOR_REVISION and domain_schema_count != 0:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if current_revision == FOUNDATION_REVISION and domain_schema_count != 2:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if current_revision == IAM_OPS_REVISION and domain_schema_count != 2:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if current_revision == DOMAIN_REVISION and domain_schema_count != 8:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if (
        current_revision == PUBLICATION_ANALYTICS_FINANCE_REVISION
        and domain_schema_count != 13
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    _validate_foundation_shape(
        connection,
        current_revision,
        allow_foundation_objects=allow_foundation_objects,
    )
    _validate_iam_ops_shape(connection, current_revision)
    _validate_st0304_shape(connection, current_revision)
    _validate_st0305_shape(connection, current_revision)
    return open_attempt


def _validate_installed(
    connection: Connection,
    current_revision: str,
    *,
    allow_open: bool = False,
    allow_foundation_objects: bool = False,
) -> _OpenAttempt | None:
    validation_failed = False
    try:
        return _validate_installed_unchecked(
            connection,
            current_revision,
            allow_open=allow_open,
            allow_foundation_objects=allow_foundation_objects,
        )
    except MigrationError:
        raise
    except Exception:
        if connection.in_transaction():
            connection.rollback()
        validation_failed = True
    if validation_failed:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


class MigrationRunner:
    """Execute the reviewed linear migration graph on an explicit local target."""

    __slots__ = ("_engine_factory", "_repository_root", "_target")

    def __init__(
        self,
        repository_root: Path,
        target: DatabaseTarget,
        *,
        engine_factory: EngineFactory | None = None,
    ) -> None:
        self._repository_root = repository_root.absolute()
        self._target = target
        self._engine_factory = engine_factory or _default_engine_factory

    def _open_engine(self, verification: CatalogVerification) -> Engine:
        del verification
        _validate_target(self._target)
        engine_failed = False
        try:
            return self._engine_factory(self._target)
        except MigrationError:
            raise
        except Exception:
            engine_failed = True
        if engine_failed:
            raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)

    @staticmethod
    def _prepare_and_lock(connection: Connection) -> _LockedSession:
        connection_failed = False
        try:
            if connection.dialect.name != "postgresql":
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            if connection.closed or connection.invalidated:
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            driver_connection = connection.connection.driver_connection
            if driver_connection is None:
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            version = connection.exec_driver_sql("SHOW server_version_num").scalar_one()
            if str(version) != str(EXPECTED_SERVER_VERSION_NUM):
                raise MigrationError(MigrationErrorCode.SERVER_VERSION_MISMATCH)
            connection.exec_driver_sql("SET search_path = pg_catalog")
            search_path = connection.exec_driver_sql("SHOW search_path").scalar_one()
            if str(search_path) != "pg_catalog":
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            connection.exec_driver_sql("SET TIME ZONE 'UTC'")
            timezone = connection.exec_driver_sql("SHOW TimeZone").scalar_one()
            if str(timezone) != "UTC":
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            connection.exec_driver_sql("SET lock_timeout = '5000ms'")
            connection.exec_driver_sql("SET statement_timeout = '300000ms'")
            connection.exec_driver_sql(
                "SET idle_in_transaction_session_timeout = '60000ms'"
            )
            acquired, backend_pid = connection.execute(
                sa.text(
                    "SELECT pg_catalog.pg_try_advisory_lock(:key), "
                    "pg_catalog.pg_backend_pid()"
                ),
                {"key": ADVISORY_LOCK_KEY},
            ).one()
            if (
                type(backend_pid) is not int
                or connection.closed
                or connection.invalidated
                or connection.connection.driver_connection is not driver_connection
            ):
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            identity = _LockedSession(
                backend_pid=backend_pid,
                driver_connection=driver_connection,
            )
            connection.commit()
            if (
                connection.closed
                or connection.invalidated
                or connection.connection.driver_connection is not driver_connection
            ):
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        except MigrationError:
            if connection.in_transaction():
                connection.rollback()
            raise
        except Exception:
            if connection.in_transaction():
                connection.rollback()
            connection_failed = True
        else:
            if acquired is not True:
                raise MigrationError(MigrationErrorCode.LOCK_BUSY)
            return identity
        if connection_failed:
            raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)

    @staticmethod
    def _assert_same_session(connection: Connection, identity: _LockedSession) -> None:
        session_failed = False
        try:
            if connection.closed or connection.invalidated:
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            if (
                connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            backend_pid, exact_lock_held = connection.execute(
                sa.text(
                    """
                    SELECT pg_catalog.pg_backend_pid(),
                           (
                               SELECT pg_catalog.count(*) = 1
                               FROM pg_catalog.pg_locks
                               WHERE locktype = 'advisory'
                                 AND pid = pg_catalog.pg_backend_pid()
                                 AND classid::bigint = :class_id
                                 AND objid::bigint = :object_id
                                 AND objsubid = 1
                                 AND mode = 'ExclusiveLock'
                                 AND granted
                           )
                    """
                ),
                {
                    "class_id": _ADVISORY_LOCK_CLASS_ID,
                    "object_id": _ADVISORY_LOCK_OBJECT_ID,
                },
            ).one()
            if backend_pid != identity.backend_pid or exact_lock_held is not True:
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            if (
                connection.closed
                or connection.invalidated
                or connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
        except MigrationError:
            raise
        except Exception:
            if connection.in_transaction():
                try:
                    connection.rollback()
                except Exception:
                    pass
            session_failed = True
        if session_failed:
            raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)

    def _reconcile_interrupted_attempt(
        self,
        connection: Connection,
        current_revision: str,
        session_identity: _LockedSession,
        *,
        allow_foundation_objects: bool = False,
        strict_after_reconcile: bool = True,
    ) -> None:
        self._assert_same_session(connection, session_identity)
        open_attempt = _validate_installed(
            connection,
            current_revision,
            allow_open=True,
            allow_foundation_objects=allow_foundation_objects,
        )
        if open_attempt is None:
            if strict_after_reconcile:
                _validate_installed(connection, current_revision)
            return
        self._assert_same_session(connection, session_identity)
        _append_attempt_event(
            connection,
            attempt_id=open_attempt.attempt_id,
            revision_index=open_attempt.revision_index,
            direction=open_attempt.direction,
            status="FAILED",
            error_code="INTERRUPTED_BEFORE_TERMINAL",
        )
        _validate_installed(
            connection,
            current_revision,
            allow_foundation_objects=(
                allow_foundation_objects and not strict_after_reconcile
            ),
        )

    @staticmethod
    def _unlock(connection: Connection, identity: _LockedSession) -> None:
        cleanup_failed = False
        try:
            if connection.in_transaction():
                connection.rollback()
            if (
                connection.closed
                or connection.invalidated
                or connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            backend_pid, released = connection.execute(
                sa.text(
                    "SELECT pg_catalog.pg_backend_pid(), "
                    "pg_catalog.pg_advisory_unlock(:key)"
                ),
                {"key": ADVISORY_LOCK_KEY},
            ).one()
            connection.commit()
            if (
                backend_pid != identity.backend_pid
                or released is not True
                or connection.closed
                or connection.invalidated
                or connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
        except MigrationError:
            raise
        except Exception:
            if connection.in_transaction():
                connection.rollback()
            cleanup_failed = True
        if cleanup_failed:
            raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)

    def _result(
        self,
        command_name: str,
        changed: bool,
        current_revision: str,
        verification: CatalogVerification,
    ) -> MigrationResult:
        return MigrationResult(
            command=command_name,
            environment=self._target.environment.value,
            changed=changed,
            current_revision=current_revision,
            catalog_sha256=verification.catalog_sha256,
            revision_source_count=len(verification.revision_sources),
            checkpoint_source_count=len(verification.checkpoint_sources),
        )

    def _run_locked(
        self,
        engine: Engine,
        operation: Callable[[Connection, _LockedSession], MigrationResult],
    ) -> MigrationResult:
        """Run one operation and sanitize operation/cleanup failures separately."""

        result: MigrationResult | None = None
        error_code: MigrationErrorCode | None = None
        cleanup_failed = False
        try:
            try:
                with engine.connect() as connection:
                    identity: _LockedSession | None = None
                    try:
                        identity = self._prepare_and_lock(connection)
                        try:
                            result = operation(connection, identity)
                        except MigrationError as error:
                            error_code = error.code
                        except Exception:
                            error_code = MigrationErrorCode.CONNECTION_FAILED
                        try:
                            self._unlock(connection, identity)
                        except Exception:
                            cleanup_failed = True
                    except MigrationError as error:
                        if identity is None:
                            error_code = error.code
                    except Exception:
                        if identity is None:
                            error_code = MigrationErrorCode.CONNECTION_FAILED
            except MigrationError as error:
                if error_code is None:
                    error_code = error.code
            except Exception:
                if error_code is None:
                    error_code = MigrationErrorCode.CONNECTION_FAILED
        finally:
            try:
                engine.dispose()
            except Exception:
                pass
        if cleanup_failed:
            raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
        if error_code is not None:
            raise MigrationError(error_code)
        if result is None:
            raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        return result

    def _status_locked(
        self,
        connection: Connection,
        session_identity: _LockedSession,
        verification: CatalogVerification,
    ) -> MigrationResult:
        self._assert_same_session(connection, session_identity)
        heads = _current_heads(connection)
        if heads == ():
            _assert_empty_database(connection)
            current = "base"
        elif len(heads) == 1 and heads[0] in {item.revision for item in REVISION_SPECS}:
            current = heads[0]
            _validate_installed(connection, current)
        else:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        return self._result("status", False, current, verification)

    def status(self) -> MigrationResult:
        """Return managed base/head status under the migration lock."""

        verification = verify_repository(self._repository_root)
        engine = self._open_engine(verification)
        return self._run_locked(
            engine,
            lambda connection, identity: self._status_locked(
                connection, identity, verification
            ),
        )

    def _upgrade_locked(
        self,
        connection: Connection,
        session_identity: _LockedSession,
        verification: CatalogVerification,
    ) -> MigrationResult:
        self._assert_same_session(connection, session_identity)
        heads = _current_heads(connection)
        revision_ids = [item.revision for item in REVISION_SPECS]
        if heads == ():
            _assert_empty_database(connection)
            if connection.in_transaction():
                connection.commit()
            current_index = -1
        elif len(heads) == 1 and heads[0] in revision_ids:
            current_index = revision_ids.index(heads[0])
            self._reconcile_interrupted_attempt(
                connection,
                heads[0],
                session_identity,
                allow_foundation_objects=heads[0] == FOUNDATION_REVISION,
            )
        else:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        if current_index == len(REVISION_SPECS) - 1:
            _validate_installed(connection, HEAD_REVISION)
            return self._result("upgrade", False, HEAD_REVISION, verification)
        with _verified_migration_root(verification) as snapshot_root:
            for revision_index in range(current_index + 1, len(REVISION_SPECS)):
                spec = REVISION_SPECS[revision_index]
                attempt_id = str(uuid.uuid4())
                configuration = _alembic_config(snapshot_root)
                configuration.attributes.update(
                    {
                        "attempt_id": attempt_id,
                        "operation_direction": "UPGRADE",
                        "connection": connection,
                        "revision_digests": {
                            item.revision: item.sha256 for item in REVISION_SPECS
                        },
                        "revision_stories": {
                            item.revision: item.story_id for item in REVISION_SPECS
                        },
                        "revision_runner_versions": {
                            item.revision: item.runner_version
                            for item in REVISION_SPECS
                        },
                        "revision_server_versions": {
                            item.revision: item.server_version_num
                            for item in REVISION_SPECS
                        },
                    }
                )
                if revision_index > 0:
                    self._assert_same_session(connection, session_identity)
                    _append_attempt_event(
                        connection,
                        attempt_id=attempt_id,
                        revision_index=revision_index,
                        direction="UPGRADE",
                        status="STARTED",
                        error_code=None,
                    )
                migration_failed = False
                try:
                    self._assert_same_session(connection, session_identity)
                    command.upgrade(configuration, spec.revision)
                    self._assert_same_session(connection, session_identity)
                    if connection.in_transaction():
                        connection.commit()
                except Exception:
                    if connection.in_transaction():
                        connection.rollback()
                    if revision_index > 0:
                        try:
                            self._assert_same_session(connection, session_identity)
                            _append_attempt_event(
                                connection,
                                attempt_id=attempt_id,
                                revision_index=revision_index,
                                direction="UPGRADE",
                                status="FAILED",
                                error_code="MIGRATION_FAILED",
                            )
                        except Exception:
                            if connection.in_transaction():
                                connection.rollback()
                    migration_failed = True
                if migration_failed:
                    raise MigrationError(MigrationErrorCode.MIGRATION_FAILED)
                self._assert_same_session(connection, session_identity)
                _validate_installed(connection, spec.revision)
        return self._result("upgrade", True, HEAD_REVISION, verification)

    def upgrade(self) -> MigrationResult:
        """Upgrade an empty or managed database to the exact framework head."""

        verification = verify_repository(self._repository_root)
        engine = self._open_engine(verification)
        return self._run_locked(
            engine,
            lambda connection, identity: self._upgrade_locked(
                connection, identity, verification
            ),
        )

    def _downgrade_locked(
        self,
        connection: Connection,
        session_identity: _LockedSession,
        verification: CatalogVerification,
    ) -> MigrationResult:
        self._assert_same_session(connection, session_identity)
        heads = _current_heads(connection)
        revision_ids = [item.revision for item in REVISION_SPECS]
        if heads == ():
            _assert_empty_database(connection)
            raise MigrationError(MigrationErrorCode.DOWNGRADE_FORBIDDEN)
        if len(heads) != 1 or heads[0] not in revision_ids:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        current_index = revision_ids.index(heads[0])
        self._reconcile_interrupted_attempt(
            connection,
            heads[0],
            session_identity,
            allow_foundation_objects=True,
            strict_after_reconcile=False,
        )
        if current_index == 0:
            raise MigrationError(MigrationErrorCode.DOWNGRADE_FORBIDDEN)

        spec = REVISION_SPECS[current_index]
        target_revision = spec.down_revision
        if target_revision is None:
            raise MigrationError(MigrationErrorCode.DOWNGRADE_FORBIDDEN)
        attempt_id = str(uuid.uuid4())
        with _verified_migration_root(verification) as snapshot_root:
            configuration = _alembic_config(snapshot_root)
            configuration.attributes.update(
                {
                    "attempt_id": attempt_id,
                    "operation_direction": "DOWNGRADE",
                    "connection": connection,
                    "revision_digests": {
                        item.revision: item.sha256 for item in REVISION_SPECS
                    },
                    "revision_stories": {
                        item.revision: item.story_id for item in REVISION_SPECS
                    },
                    "revision_runner_versions": {
                        item.revision: item.runner_version for item in REVISION_SPECS
                    },
                    "revision_server_versions": {
                        item.revision: item.server_version_num
                        for item in REVISION_SPECS
                    },
                }
            )
            self._assert_same_session(connection, session_identity)
            _append_attempt_event(
                connection,
                attempt_id=attempt_id,
                revision_index=current_index,
                direction="DOWNGRADE",
                status="STARTED",
                error_code=None,
            )
            migration_failed = False
            try:
                self._assert_same_session(connection, session_identity)
                command.downgrade(configuration, target_revision)
                self._assert_same_session(connection, session_identity)
                if connection.in_transaction():
                    connection.commit()
            except Exception:
                if connection.in_transaction():
                    connection.rollback()
                try:
                    self._assert_same_session(connection, session_identity)
                    _append_attempt_event(
                        connection,
                        attempt_id=attempt_id,
                        revision_index=current_index,
                        direction="DOWNGRADE",
                        status="FAILED",
                        error_code="MIGRATION_FAILED",
                    )
                except Exception:
                    if connection.in_transaction():
                        connection.rollback()
                migration_failed = True
            if migration_failed:
                raise MigrationError(MigrationErrorCode.MIGRATION_FAILED)
            self._assert_same_session(connection, session_identity)
            _validate_installed(connection, target_revision)
        return self._result("downgrade", True, target_revision, verification)

    def downgrade(self) -> MigrationResult:
        """Downgrade exactly one reviewed revision without crossing the anchor."""

        verification = verify_repository(self._repository_root)
        engine = self._open_engine(verification)
        return self._run_locked(
            engine,
            lambda connection, identity: self._downgrade_locked(
                connection, identity, verification
            ),
        )


def verification_result(verification: CatalogVerification) -> MigrationResult:
    """Build the public result for an offline repository verification."""

    return MigrationResult(
        command="verify",
        environment=None,
        changed=False,
        current_revision=HEAD_REVISION,
        catalog_sha256=verification.catalog_sha256,
        revision_source_count=len(verification.revision_sources),
        checkpoint_source_count=len(verification.checkpoint_sources),
    )
