#!/usr/bin/env python3
"""Run the owner-private Editorial V3 economics workflow."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Final, Mapping, cast
from uuid import UUID


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    EditorialPortfolioV3,
    EditorialPortfolioV3Failure,
    load_editorial_portfolio_v3,
)
from raos.adapters.google_live_database import (  # noqa: E402
    OwnerPrivateDatabaseCredentialSnapshot,
    SealedLocalGoogleAnalyticsDatabaseTarget,
    create_sealed_local_google_analytics_engine,
    seal_owner_private_database_credential,
)
from raos.adapters.persistence.sqlalchemy.identity import (  # noqa: E402
    WorkloadProfile,
)
from raos.adapters.persistence.sqlalchemy.provider import (  # noqa: E402
    SqlAlchemyEngineProvider,
)
from raos.application.analytics.google_live_import import (  # noqa: E402
    compose_live_google_analytics_import,
)
from raos.application.analytics.google_live_projection import (  # noqa: E402
    ga4_baseline_document,
    gsc_baseline_document,
)
from raos.domain.analytics.google_live import (  # noqa: E402
    GoogleImportExecutionContext,
    GoogleProviderFailure,
)
from raos.migrations.catalog import GOOGLE_ANALYTICS_LIVE_REVISION  # noqa: E402
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    TRUSTED_T0_EVIDENCE_REQUIRED,
    bind_rakuten_profile,
    build_baseline_report,
    candidate_query_demand_template,
    canonical_json_bytes,
    commit_rakuten_report,
    cost_input_template,
    detect_rakuten_sample,
    evaluate_followups,
    parse_rakuten_report,
    production_readback_template,
    rakuten_binding_template,
    read_private_bytes,
    read_private_json,
    render_baseline_html,
    sha256_bytes,
    write_private_bytes,
    write_private_json,
)


DEFAULT_PRIVATE_ROOT: Final = REPOSITORY_ROOT / ".secrets/editorial-portfolio-v3"
DEFAULT_GOOGLE_SCOPE_RECEIPT: Final = "google/local-scope.v1.json"
GOOGLE_SCOPE_RECEIPT_SCHEMA: Final = "raos.owner-private.google-local-scope.v1"
GOOGLE_SCOPE_RECEIPT_KEYS: Final = frozenset(
    {
        "database_revision",
        "ga4_ops_job_id",
        "gsc_ops_job_id",
        "schema_version",
        "scope_initialized",
        "site_id",
    }
)
PRIVATE_PATH_COMPONENT_RE: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII
)
MAX_PRIVATE_PATH_LENGTH: Final = 512
MAX_PRIVATE_PATH_DEPTH: Final = 8
MAX_GOOGLE_SCOPE_RECEIPT_BYTES: Final = 64 * 1024
MAX_DATABASE_PASSWORD_BYTES: Final = 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="absolute owner-private directory (must be mode 0700)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    detect = commands.add_parser(
        "rakuten-detect", help="detect an exact sanitized report header"
    )
    detect.add_argument("--sample", required=True)
    detect.add_argument("--encoding", choices=("utf-8-sig", "cp932"), required=True)
    detect.add_argument("--delimiter", choices=("comma", "tab"), required=True)
    detect.add_argument("--output", required=True)

    template = commands.add_parser(
        "rakuten-binding-template", help="create a disabled binding request template"
    )
    template.add_argument("--detection", required=True)
    template.add_argument("--output", required=True)

    bind = commands.add_parser(
        "rakuten-bind-profile", help="bind a closed parser profile to a verified sample"
    )
    bind.add_argument("--sample", required=True)
    bind.add_argument("--detection", required=True)
    bind.add_argument("--binding", required=True)
    bind.add_argument("--output", required=True)

    dry_run = commands.add_parser(
        "rakuten-dry-run", help="parse and aggregate without committing"
    )
    dry_run.add_argument("--report", required=True)
    dry_run.add_argument("--profile", required=True)
    dry_run.add_argument("--output", required=True)

    commit = commands.add_parser(
        "rakuten-commit", help="commit only the exact reconciled dry-run source"
    )
    commit.add_argument("--report", required=True)
    commit.add_argument("--profile", required=True)
    commit.add_argument("--dry-run", required=True)
    commit.add_argument("--expected-source-sha256", required=True)
    commit.add_argument("--provider-row-count", type=int, required=True)
    commit.add_argument("--provider-pending-jpy", type=int, required=True)
    commit.add_argument("--provider-confirmed-jpy", type=int, required=True)
    commit.add_argument("--provider-cancelled-jpy", type=int, required=True)
    commit.add_argument("--output", required=True)

    cost = commands.add_parser(
        "cost-template", help="create a ten-article owner-attestation template"
    )
    cost.add_argument("--output", required=True)

    t0_template = commands.add_parser(
        "t0-template", help="create a disabled production-readback template"
    )
    t0_template.add_argument("--output", required=True)

    establish_t0 = commands.add_parser(
        "establish-t0", help="derive T0 from all exact successful readbacks"
    )
    establish_t0.add_argument("--observation", required=True)
    establish_t0.add_argument(
        "--rakuten-activation-dry-run",
        required=True,
        help="exact owner-private Rakuten activation dry-run bound to live links",
    )
    establish_t0.add_argument(
        "--separate-admin-apply-receipt",
        required=True,
        help=("owner-private-root-relative mode-0600 separate-admin apply receipt"),
    )
    establish_t0.add_argument(
        "--publication-receipt",
        required=True,
        help="owner-private-root-relative mode-0600 applied publication receipt",
    )
    establish_t0.add_argument(
        "--public-readback-receipt",
        required=True,
        help=(
            "owner-private-root-relative mode-0600 receipt created by a "
            "separate administrator; owner/Codex must not synthesize it"
        ),
    )
    establish_t0.add_argument("--output", required=True)

    baseline = commands.add_parser(
        "baseline", help="build owner-private JSON and noindex HTML reports"
    )
    baseline.add_argument("--rakuten-commit")
    baseline.add_argument("--cost-input")
    baseline.add_argument("--gsc-input")
    baseline.add_argument("--ga4-input")
    baseline.add_argument("--t0-receipt")
    baseline.add_argument("--json-output", required=True)
    baseline.add_argument("--html-output", required=True)

    followups = commands.add_parser(
        "evaluate-followups",
        help="emit Day 30/90 reviews and the non-automatic article gate",
    )
    followups.add_argument("--baseline", required=True)
    followups.add_argument("--candidate-query-demand")
    followups.add_argument("--as-of", required=True)
    followups.add_argument("--output", required=True)

    candidate_template = commands.add_parser(
        "candidate-query-template",
        help="create the owner-private independent GSC query-cluster template",
    )
    candidate_template.add_argument("--output", required=True)

    refresh = commands.add_parser(
        "refresh-baseline",
        help=(
            "import live GSC/GA4 into PostgreSQL, project owner-private inputs, "
            "and rebuild the baseline"
        ),
    )
    refresh.add_argument("--date-from", required=True)
    refresh.add_argument("--date-to", required=True)
    refresh.add_argument(
        "--google-scope-receipt",
        default=DEFAULT_GOOGLE_SCOPE_RECEIPT,
        help=(
            "relative 0600 local scope receipt below --private-root; "
            "defaults to google/local-scope.v1.json"
        ),
    )
    refresh.add_argument("--database-host", default="127.0.0.1")
    refresh.add_argument("--database-port", type=int, default=5432)
    refresh.add_argument("--database-name", required=True)
    refresh.add_argument("--database-user", required=True)
    refresh.add_argument(
        "--database-password",
        required=True,
        help="safe relative 0600 password file below --private-root",
    )
    refresh.add_argument("--gsc-output", required=True)
    refresh.add_argument("--ga4-output", required=True)
    refresh.add_argument("--rakuten-commit")
    refresh.add_argument("--cost-input")
    refresh.add_argument("--t0-receipt")
    refresh.add_argument("--json-output", required=True)
    refresh.add_argument("--html-output", required=True)
    return parser


def _optional_json(private_root: Path, name: str | None) -> Mapping[str, object] | None:
    return read_private_json(private_root, name) if name is not None else None


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except TypeError, ValueError:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_DATE_INVALID"
        ) from None


def _uuid(value: object) -> UUID:
    if type(value) is not str:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_IDENTITY_INVALID"
        ) from None
    try:
        return UUID(value)
    except AttributeError, TypeError, ValueError:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_IDENTITY_INVALID"
        ) from None


def _private_relative_parts(name: object) -> tuple[str, ...]:
    if (
        type(name) is not str
        or not 1 <= len(name) <= MAX_PRIVATE_PATH_LENGTH
        or "\\" in name
    ):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_NAME_INVALID"
        ) from None
    candidate = Path(name)
    parts = candidate.parts
    if (
        candidate.is_absolute()
        or not 1 <= len(parts) <= MAX_PRIVATE_PATH_DEPTH
        or candidate.as_posix() != name
        or any(PRIVATE_PATH_COMPONENT_RE.fullmatch(part) is None for part in parts)
    ):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_NAME_INVALID"
        ) from None
    return parts


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _is_private_directory(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o700
    )


def _validate_private_directory(metadata: os.stat_result) -> None:
    if not _is_private_directory(metadata):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID"
        ) from None


def _open_pinned_private_root(
    private_root: Path, flags: int
) -> tuple[list[int], list[tuple[int, int]]]:
    descriptors: list[int] = []
    identities: list[tuple[int, int]] = []
    try:
        root_descriptor = os.open(
            os.sep,
            flags | getattr(os, "O_DIRECTORY", 0),
        )
        descriptors.append(root_descriptor)
        root_metadata = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
            ) from None
        identities.append(_directory_identity(root_metadata))

        directory_descriptor = root_descriptor
        for component in private_root.parts[1:]:
            named_directory = os.stat(
                component,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(named_directory.st_mode) or stat.S_ISLNK(
                named_directory.st_mode
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
                ) from None
            child_descriptor = os.open(
                component,
                flags | getattr(os, "O_DIRECTORY", 0),
                dir_fd=directory_descriptor,
            )
            descriptors.append(child_descriptor)
            opened_directory = os.fstat(child_descriptor)
            if not stat.S_ISDIR(opened_directory.st_mode) or _directory_identity(
                named_directory
            ) != _directory_identity(opened_directory):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
                ) from None
            identities.append(_directory_identity(opened_directory))
            directory_descriptor = child_descriptor
        if not _is_private_directory(os.fstat(directory_descriptor)):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
            ) from None
        return descriptors, identities
    except EditorialEconomicsV3Failure:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise
    except OSError:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
        ) from None


def _verify_pinned_private_root(
    private_root: Path,
    descriptors: list[int],
    identities: list[tuple[int, int]],
) -> None:
    try:
        named_root = os.stat(os.sep, follow_symlinks=False)
        if (
            _directory_identity(named_root) != identities[0]
            or _directory_identity(os.fstat(descriptors[0])) != identities[0]
        ):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
            ) from None
        for index, component in enumerate(private_root.parts[1:], start=1):
            named_directory = os.stat(
                component,
                dir_fd=descriptors[index - 1],
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(named_directory.st_mode)
                or stat.S_ISLNK(named_directory.st_mode)
                or _directory_identity(named_directory) != identities[index]
                or _directory_identity(os.fstat(descriptors[index]))
                != identities[index]
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
                ) from None
        if not _is_private_directory(os.fstat(descriptors[-1])):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
            ) from None
    except EditorialEconomicsV3Failure:
        raise
    except OSError:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
        ) from None


def _read_private_relative_snapshot(
    private_root: Path,
    name: object,
    *,
    maximum_bytes: int,
) -> bytes:
    if not private_root.is_absolute():
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
        ) from None
    try:
        lexical_root = Path(os.path.abspath(private_root))
    except OSError:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
        ) from None
    if private_root != lexical_root:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID"
        ) from None
    parts = _private_relative_parts(name)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    directory_descriptors, directory_identities = _open_pinned_private_root(
        private_root, flags
    )
    private_root_index = len(directory_descriptors) - 1
    directory_descriptor = directory_descriptors[private_root_index]
    file_descriptor = -1
    try:
        for component in parts[:-1]:
            named_directory = os.stat(
                component,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            child_descriptor = os.open(
                component,
                flags | getattr(os, "O_DIRECTORY", 0),
                dir_fd=directory_descriptor,
            )
            directory_descriptors.append(child_descriptor)
            opened_directory = os.fstat(child_descriptor)
            _validate_private_directory(opened_directory)
            if _directory_identity(named_directory) != _directory_identity(
                opened_directory
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
                ) from None
            directory_identities.append(_directory_identity(opened_directory))
            directory_descriptor = child_descriptor

        leaf = parts[-1]
        file_descriptor = os.open(leaf, flags, dir_fd=directory_descriptor)
        before = os.fstat(file_descriptor)
        named_before = os.stat(
            leaf,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if (
            _file_identity(before) != _file_identity(named_before)
            or not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum_bytes
        ):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID"
            ) from None

        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
                ) from None
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)

        after = os.fstat(file_descriptor)
        named_after = os.stat(
            leaf,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if _file_identity(after) != _file_identity(before) or _file_identity(
            named_after
        ) != _file_identity(before):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
            ) from None

        _verify_pinned_private_root(
            private_root,
            directory_descriptors[: private_root_index + 1],
            directory_identities[: private_root_index + 1],
        )
        for index, component in enumerate(parts[:-1], start=1):
            descriptor_index = private_root_index + index
            expected_identity = directory_identities[descriptor_index]
            named_directory_after = os.stat(
                component,
                dir_fd=directory_descriptors[descriptor_index - 1],
                follow_symlinks=False,
            )
            if (
                _directory_identity(named_directory_after) != expected_identity
                or _directory_identity(
                    os.fstat(directory_descriptors[descriptor_index])
                )
                != expected_identity
                or not _is_private_directory(
                    os.fstat(directory_descriptors[descriptor_index])
                )
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED"
                ) from None
        return content
    except EditorialEconomicsV3Failure:
        raise
    except OSError:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID"
        ) from None
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


def _database_credential_snapshot(
    private_root: Path, name: object
) -> OwnerPrivateDatabaseCredentialSnapshot:
    content = _read_private_relative_snapshot(
        private_root,
        name,
        maximum_bytes=MAX_DATABASE_PASSWORD_BYTES,
    )
    return seal_owner_private_database_credential(content)


def _unique_scope_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
            ) from None
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise EditorialEconomicsV3Failure(
        "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
    ) from None


def _google_local_scope(private_root: Path, name: object) -> tuple[UUID, UUID, UUID]:
    content = _read_private_relative_snapshot(
        private_root,
        name,
        maximum_bytes=MAX_GOOGLE_SCOPE_RECEIPT_BYTES,
    )
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_scope_object,
            parse_constant=_reject_json_constant,
        )
    except EditorialEconomicsV3Failure:
        raise
    except UnicodeError, json.JSONDecodeError, RecursionError, ValueError:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
        ) from None
    if type(value) is not dict:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
        ) from None
    document = cast(dict[str, object], value)
    if (
        frozenset(document) != GOOGLE_SCOPE_RECEIPT_KEYS
        or document.get("schema_version") != GOOGLE_SCOPE_RECEIPT_SCHEMA
        or document.get("scope_initialized") is not True
        or document.get("database_revision") != GOOGLE_ANALYTICS_LIVE_REVISION
    ):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
        ) from None
    try:
        site_id = _uuid(document.get("site_id"))
        gsc_job_id = _uuid(document.get("gsc_ops_job_id"))
        ga4_job_id = _uuid(document.get("ga4_ops_job_id"))
    except EditorialEconomicsV3Failure:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
        ) from None
    if (
        any(identifier.int == 0 for identifier in (site_id, gsc_job_id, ga4_job_id))
        or len({site_id, gsc_job_id, ga4_job_id}) != 3
        or str(site_id) != document["site_id"]
        or str(gsc_job_id) != document["gsc_ops_job_id"]
        or str(ga4_job_id) != document["ga4_ops_job_id"]
    ):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID"
        ) from None
    return site_id, gsc_job_id, ga4_job_id


def _refresh_baseline(
    *,
    arguments: argparse.Namespace,
    private_root: Path,
    portfolio: EditorialPortfolioV3,
) -> None:
    # Imported here so all non-live owner workflows remain usable without
    # opening a database seam.
    from raos.adapters.persistence.sqlalchemy.google_live import (
        SqlAlchemyAnalyticsImportRepository,
    )

    date_from = _date(arguments.date_from)
    date_to = _date(arguments.date_to)
    if date_to < date_from:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_DATE_INVALID"
        ) from None
    site_id, gsc_job_id, ga4_job_id = _google_local_scope(
        private_root, arguments.google_scope_receipt
    )
    started_at = datetime.now(UTC)
    credential = _database_credential_snapshot(
        private_root, arguments.database_password
    )
    target = SealedLocalGoogleAnalyticsDatabaseTarget(
        host=arguments.database_host,
        port=arguments.database_port,
        database=arguments.database_name,
        user=arguments.database_user,
        credential=credential,
    )
    engine = create_sealed_local_google_analytics_engine(target)
    try:
        provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.WORKER_COMMAND)
        repository = SqlAlchemyAnalyticsImportRepository(provider)
        service = compose_live_google_analytics_import(
            owner_private_root=private_root,
            repository=repository,
        )
        suffix = f"{date_from:%Y%m%d}-{date_to:%Y%m%d}"
        gsc_batch, _ = service.import_search_console_with_batch(
            context=GoogleImportExecutionContext(
                display_id=f"AIR-GSC-{suffix}",
                site_id=site_id,
                ops_job_id=gsc_job_id,
                started_at=started_at,
            ),
            date_from=date_from,
            date_to=date_to,
        )
        ga4_batch, _ = service.import_ga4_with_batch(
            context=GoogleImportExecutionContext(
                display_id=f"AIR-GA4-{suffix}",
                site_id=site_id,
                ops_job_id=ga4_job_id,
                started_at=started_at,
            ),
            date_from=date_from,
            date_to=date_to,
        )
        gsc_document = gsc_baseline_document(gsc_batch)
        ga4_document = ga4_baseline_document(ga4_batch)
        write_private_json(private_root, arguments.gsc_output, gsc_document)
        write_private_json(private_root, arguments.ga4_output, ga4_document)
        report = build_baseline_report(
            portfolio=portfolio,
            rakuten_commit=_optional_json(private_root, arguments.rakuten_commit),
            cost_input=_optional_json(private_root, arguments.cost_input),
            gsc_input=gsc_document,
            ga4_input=ga4_document,
            t0_receipt=_optional_json(private_root, arguments.t0_receipt),
            generated_at=datetime.now(UTC),
        )
        write_private_bytes(
            private_root, arguments.json_output, canonical_json_bytes(report)
        )
        write_private_bytes(
            private_root, arguments.html_output, render_baseline_html(report)
        )
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    private_root = arguments.private_root
    try:
        portfolio = load_editorial_portfolio_v3(REPOSITORY_ROOT)
        if arguments.command == "rakuten-detect":
            sample = read_private_bytes(private_root, arguments.sample)
            document = detect_rakuten_sample(
                sample,
                encoding=arguments.encoding,
                delimiter_name=arguments.delimiter,
            )
            write_private_json(private_root, arguments.output, document)
        elif arguments.command == "rakuten-binding-template":
            detection_content = read_private_bytes(private_root, arguments.detection)
            detection = read_private_json(private_root, arguments.detection)
            document = rakuten_binding_template(
                detection,
                detection_sha256=sha256_bytes(detection_content),
                portfolio=portfolio,
            )
            write_private_json(private_root, arguments.output, document)
        elif arguments.command == "rakuten-bind-profile":
            sample = read_private_bytes(private_root, arguments.sample)
            detection_content = read_private_bytes(private_root, arguments.detection)
            detection = read_private_json(private_root, arguments.detection)
            binding = read_private_json(private_root, arguments.binding)
            document = bind_rakuten_profile(
                sample_content=sample,
                detection=detection,
                detection_content_sha256=sha256_bytes(detection_content),
                request=binding,
                portfolio=portfolio,
            )
            write_private_json(private_root, arguments.output, document)
        elif arguments.command == "rakuten-dry-run":
            report = read_private_bytes(private_root, arguments.report)
            profile_content = read_private_bytes(private_root, arguments.profile)
            profile = read_private_json(private_root, arguments.profile)
            document = parse_rakuten_report(
                content=report,
                profile=profile,
                profile_sha256=sha256_bytes(profile_content),
                portfolio=portfolio,
            )
            write_private_json(private_root, arguments.output, document)
        elif arguments.command == "rakuten-commit":
            rakuten_report_content = read_private_bytes(private_root, arguments.report)
            profile_content = read_private_bytes(private_root, arguments.profile)
            profile = read_private_json(private_root, arguments.profile)
            dry_run = read_private_json(private_root, arguments.dry_run)
            reparsed = parse_rakuten_report(
                content=rakuten_report_content,
                profile=profile,
                profile_sha256=sha256_bytes(profile_content),
                portfolio=portfolio,
            )
            document = commit_rakuten_report(
                dry_run=dry_run,
                reparsed=reparsed,
                expected_source_sha256=arguments.expected_source_sha256,
                provider_row_count=arguments.provider_row_count,
                provider_totals_jpy={
                    "PENDING": arguments.provider_pending_jpy,
                    "CONFIRMED": arguments.provider_confirmed_jpy,
                    "CANCELLED": arguments.provider_cancelled_jpy,
                },
                portfolio=portfolio,
            )
            write_private_json(private_root, arguments.output, document)
        elif arguments.command == "cost-template":
            write_private_json(
                private_root, arguments.output, cost_input_template(portfolio)
            )
        elif arguments.command == "candidate-query-template":
            write_private_json(
                private_root,
                arguments.output,
                candidate_query_demand_template(),
            )
        elif arguments.command == "t0-template":
            write_private_json(
                private_root,
                arguments.output,
                production_readback_template(portfolio),
            )
        elif arguments.command == "establish-t0":
            # No current input carries independently verifiable trusted
            # evidence.  Fail before reading any owner-private candidate files
            # and never create a T0 receipt from self-asserted JSON.
            raise EditorialEconomicsV3Failure(TRUSTED_T0_EVIDENCE_REQUIRED)
        elif arguments.command == "baseline":
            baseline_report = build_baseline_report(
                portfolio=portfolio,
                rakuten_commit=_optional_json(private_root, arguments.rakuten_commit),
                cost_input=_optional_json(private_root, arguments.cost_input),
                gsc_input=_optional_json(private_root, arguments.gsc_input),
                ga4_input=_optional_json(private_root, arguments.ga4_input),
                t0_receipt=_optional_json(private_root, arguments.t0_receipt),
                generated_at=datetime.now(UTC),
            )
            write_private_bytes(
                private_root,
                arguments.json_output,
                canonical_json_bytes(baseline_report),
            )
            write_private_bytes(
                private_root,
                arguments.html_output,
                render_baseline_html(baseline_report),
            )
        elif arguments.command == "evaluate-followups":
            baseline_content = read_private_bytes(private_root, arguments.baseline)
            evaluation = evaluate_followups(
                baseline=read_private_json(private_root, arguments.baseline),
                baseline_sha256=sha256_bytes(baseline_content),
                portfolio=portfolio,
                as_of=arguments.as_of,
                candidate_query_demand=_optional_json(
                    private_root, arguments.candidate_query_demand
                ),
                generated_at=datetime.now(UTC),
            )
            write_private_json(private_root, arguments.output, evaluation)
        elif arguments.command == "refresh-baseline":
            _refresh_baseline(
                arguments=arguments,
                private_root=private_root,
                portfolio=portfolio,
            )
        else:
            raise AssertionError("unreachable")
        print(
            f"RAOS_EDITORIAL_V3_OWNER_PRIVATE command={arguments.command} status=PASS"
        )
        return 0
    except (
        EditorialEconomicsV3Failure,
        EditorialPortfolioV3Failure,
        GoogleProviderFailure,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
