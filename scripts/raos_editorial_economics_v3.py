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
    LiveGoogleAnalyticsImport,
    compose_live_google_analytics_import,
)
from raos.application.analytics.google_live_projection import (  # noqa: E402
    ga4_baseline_document,
    ga4_purchase_document_v2,
    gsc_baseline_document,
)
from raos.domain.analytics.google_live import (  # noqa: E402
    GA4_BASELINE_DIMENSIONS,
    GA4_PURCHASE_DIMENSIONS_V2,
    GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2,
    Ga4ImportBatch,
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
DEFAULT_PURCHASE_BINDINGS: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
    "/assets/purchase-support.v1.json"
)
OBSERVATION_VALUE_BASES: Final = ("DIRECT_EVENT_COUNTS", "SAMPLED_ESTIMATE", "UNKNOWN")
OBSERVATION_QUALITY_FLAGS: Final = frozenset(
    {
        "SUBJECT_TO_THRESHOLDING",
        "OTHER_ROW_PRESENT",
        "PARTIAL_WINDOW",
        "CONTRACT_CHANGED",
        "REPORTED_SCHEMA_RESTRICTION",
        "CONSENT_SCOPE_CHANGED",
    }
)
OBSERVATION_BINDING_KEYS: Final = (
    "article_id",
    "product_id",
    "seller_id",
    "offer_id",
    "cta_id",
    "placement",
    "snapshot_id",
)
_UNSET_IDENTITY: Final = frozenset({"", "UNKNOWN", "UNAVAILABLE", "(not set)"})
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
    ga4 = commands.add_parser(
        "import-ga4", help="readonly Google fetch into local private aggregate storage"
    )
    ga4.add_argument("--profile", choices=("legacy", "purchase-v2"), required=True)
    ga4.add_argument(
        "--plan",
        action="store_true",
        help="print contract without credentials, database or network",
    )
    ga4.add_argument("--date-from", required=True)
    ga4.add_argument("--date-to", required=True)
    ga4.add_argument("--google-scope-receipt", default=DEFAULT_GOOGLE_SCOPE_RECEIPT)
    ga4.add_argument(
        "--ga4-views-job-id",
        help="distinct pre-registered GA4 analytics job UUID for purchase-v2 page-view report",
    )
    ga4.add_argument("--database-host", default="127.0.0.1")
    ga4.add_argument("--database-port", type=int, default=5432)
    for name in ("database-name", "database-user", "database-password", "ga4-output"):
        ga4.add_argument("--" + name)
    observation = commands.add_parser(
        "summarize-purchase-observations",
        help="classify an imported purchase-v2 GA4 document by publication bindings; no credentials, database or network",
    )
    observation.add_argument(
        "--ga4-input",
        required=True,
        help="private purchase-v2 GA4 document written by import-ga4",
    )
    observation.add_argument(
        "--bindings",
        default=DEFAULT_PURCHASE_BINDINGS,
        help="tracked runtime projection carrying the publication-time bindings",
    )
    observation.add_argument(
        "--value-basis", choices=OBSERVATION_VALUE_BASES, required=True
    )
    observation.add_argument(
        "--quality-flag",
        action="append",
        default=[],
        choices=sorted(OBSERVATION_QUALITY_FLAGS),
    )
    observation.add_argument(
        "--scope-unknown",
        action="store_true",
        help="the report population cannot be identified; keep reported counts only",
    )
    observation.add_argument("--output", help="optional private output name")
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
    portfolio: EditorialPortfolioV3 | None,
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
        if arguments.command == "import-ga4":
            _import_ga4_profile(
                service, arguments, site_id, ga4_job_id, started_at, private_root
            )
            return
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
        assert portfolio is not None
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


def _ga4_profile_plan(arguments: argparse.Namespace) -> dict[str, object]:
    if _date(arguments.date_to) < _date(arguments.date_from):
        raise EditorialEconomicsV3Failure("RAOS_EDITORIAL_V3_GOOGLE_DATE_INVALID")
    purchase = arguments.profile == "purchase-v2"
    return {
        "profile": arguments.profile,
        "date_from": arguments.date_from,
        "date_to": arguments.date_to,
        "click_dimensions": list(
            GA4_PURCHASE_DIMENSIONS_V2 if purchase else GA4_BASELINE_DIMENSIONS
        ),
        "page_view_dimensions": list(GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2)
        if purchase
        else [],
        "required_custom_dimensions": [
            name.removeprefix("customEvent:")
            for name in GA4_PURCHASE_DIMENSIONS_V2
            if name.startswith("customEvent:")
        ]
        if purchase
        else [],
        "denominator": "page_view sessions per article_id/snapshot_id; never sum CTA sessions",
        "google_access": "READ_ONLY",
        "local_database_write": "IMPORT_ONLY",
        "credential_configuration": "NOT_CHECKED",
        "live_verification": "NOT_EXECUTED",
        "activation": "OFF/OWNER_CONFIRMATION_PENDING",
        "independent_views_job_required": purchase,
        "purchase_and_reward": "UNAVAILABLE",
    }


def _binding_bucket(binding: Mapping[str, object]) -> str | None:
    """Classify one publication-time binding; non-purchase links are ignored."""
    affiliate = binding.get("affiliate") in (True, "true")
    purpose = binding.get("link_purpose")
    if purpose == "affiliate_purchase" and affiliate:
        surface = binding.get("surface")
        if surface is None:
            surface = (
                "product_image"
                if str(binding.get("offer_id", "")).startswith("image-")
                else "product_text"
            )
        return {
            "product_image": "affiliate_image",
            "product_text": "affiliate_text",
        }.get(str(surface), "affiliate_surface_unknown")
    if purpose == "merchant_purchase" and binding.get("affiliate") in (False, "false"):
        return "merchant"
    if purpose in {"affiliate_purchase", "merchant_purchase"}:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_OBSERVATION_BINDING_PURPOSE_CONFLICT"
        )
    return None


def classify_offer_click_rows(rows: object, bindings: object) -> dict[str, object]:
    """Join retained offer_click rows to the publication-time bindings by 7 IDs.

    A row whose identity has no binding stays unclassified; historic snapshots are
    never re-read against newer bindings. Counts are the provider's row values and
    do not extend to visits that were not returned.
    """
    if not isinstance(rows, list) or not isinstance(bindings, list):
        raise EditorialEconomicsV3Failure("RAOS_EDITORIAL_V3_OBSERVATION_INPUT_INVALID")
    index: dict[tuple[str, ...], str] = {}
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_BINDING_INVALID"
            )
        bucket = _binding_bucket(binding)
        if bucket is None:
            continue
        key = tuple(str(binding.get(name, "")) for name in OBSERVATION_BINDING_KEYS)
        if any(value in _UNSET_IDENTITY for value in key):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_BINDING_INVALID"
            )
        if key in index:
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_BINDING_DUPLICATE"
            )
        index[key] = bucket
    counts = {
        "affiliate_text": 0,
        "affiliate_image": 0,
        "affiliate_surface_unknown": 0,
        "merchant": 0,
        "unclassified": 0,
    }
    flags: set[str] = set()
    grains: set[tuple[object, tuple[str, ...]]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_ROW_INVALID"
            )
        dimensions = {
            str(item.get("name", "")).removeprefix("customEvent:"): str(
                item.get("value", "")
            )
            for item in row.get("dimensions", [])
            if isinstance(item, Mapping)
        }
        if dimensions.get("eventName", "offer_click") != "offer_click":
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_OFFER_CLICK_REQUIRED"
            )
        metric = next(
            (
                item
                for item in row.get("metrics", [])
                if isinstance(item, Mapping) and item.get("name") == "eventCount"
            ),
            None,
        )
        if metric is None or not re.fullmatch(
            r"\d{1,12}", str(metric.get("value", ""))
        ):
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_EVENT_COUNT_INVALID"
            )
        key = tuple(dimensions.get(name, "") for name in OBSERVATION_BINDING_KEYS)
        grain = (row.get("metric_date", row.get("date")), key)
        if grain in grains:
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_OBSERVATION_ROW_DUPLICATE"
            )
        grains.add(grain)
        counts[index.get(key, "unclassified")] += int(str(metric["value"]))
        if row.get("is_thresholded"):
            flags.add("SUBJECT_TO_THRESHOLDING")
    return {"counts": counts, "quality_flags": sorted(flags)}


def purchase_observation_summary(
    document: Mapping[str, object] | None,
    bindings: object,
    *,
    value_basis: str,
    quality_flags: object = (),
    scope_unknown: bool = False,
) -> dict[str, object]:
    """Observation envelope for one already imported purchase-v2 GA4 document.

    Unretrieved reports carry null counts, an explicit empty report carries zero,
    and neither produces a ratio. Sampled or unresolved value bases and unknown
    scopes keep the provider's reported counts only. Direct counts describe the
    returned rows: no CTR/CVR/EPC, no causal effect, no all-visitor coverage.
    """
    if value_basis not in OBSERVATION_VALUE_BASES:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_OBSERVATION_VALUE_BASIS_INVALID"
        )
    if not isinstance(quality_flags, (list, tuple)):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_OBSERVATION_QUALITY_FLAG_INVALID"
        )
    flags = [str(flag) for flag in quality_flags]
    if len(set(flags)) != len(flags) or any(
        flag not in OBSERVATION_QUALITY_FLAGS for flag in flags
    ):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_OBSERVATION_QUALITY_FLAG_INVALID"
        )
    nulls: dict[str, object] = {
        "total_observed_clicks": None,
        "ad_clicks": None,
        "ordinary_clicks": None,
        "unclassified_clicks": None,
        "classification_coverage": None,
        "ad_share_exact": None,
        "ad_share_bounds": None,
    }
    base: dict[str, object] = {
        "value_basis": value_basis,
        "quality_flags": sorted(flags),
        "population": "OBSERVED_OFFER_CLICK_ROWS_ONLY",
        "unobserved_clicks": None,
        "reported_counts": None,
        "excluded_row_counts": None,
        "causal_effect_established": False,
        "all_visitors_covered": False,
        "purchase_and_reward": "UNAVAILABLE",
        "not_derived": ["CTR", "CVR", "EPC", "causal_effect"],
    }
    if document is None:
        return {
            **base,
            **nulls,
            "retrieval_state": "NOT_RETRIEVED",
            "scope_state": "UNKNOWN",
            "state": "NOT_RETRIEVED",
            "population": "NO_REPORT_RETRIEVED",
            "ratio_state": "NOT_RETRIEVED",
        }
    if not isinstance(document, Mapping):
        raise EditorialEconomicsV3Failure("RAOS_EDITORIAL_V3_OBSERVATION_INPUT_INVALID")
    scope_map = {
        "OBSERVED_ROWS_ONLY": "REPORT_SCOPE_CONFIRMED",
        "PARTIAL_SCOPE_UNKNOWN": "PARTIAL",
        "NO_PURCHASE_OBSERVATIONS": "REPORT_SCOPE_CONFIRMED",
    }
    scope_status = document.get("scope_status")
    if scope_status not in scope_map:
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_OBSERVATION_SCOPE_STATUS_INVALID"
        )
    scope_state = "UNKNOWN" if scope_unknown else scope_map[str(scope_status)]
    classified = classify_offer_click_rows(document.get("rows", []), bindings)
    counts = cast(dict[str, int], classified["counts"])
    ad = (
        counts["affiliate_text"]
        + counts["affiliate_image"]
        + counts["affiliate_surface_unknown"]
    )
    envelope: dict[str, object] = {
        **base,
        "quality_flags": sorted(
            set(flags) | set(cast(list[str], classified["quality_flags"]))
        ),
        "retrieval_state": "OBSERVED",
        "scope_state": scope_state,
        "scope_status": scope_status,
        "excluded_row_counts": document.get("excluded_row_counts"),
        "reported_counts": {
            "ad": ad,
            "ordinary": counts["merchant"],
            "unclassified": counts["unclassified"],
            "detail": counts,
        },
    }
    if scope_state == "UNKNOWN" or value_basis != "DIRECT_EVENT_COUNTS":
        if scope_state == "UNKNOWN":
            population, state, ratio_state = (
                "REPORT_SCOPE_UNRESOLVED",
                "SCOPE_UNKNOWN",
                "NOT_IDENTIFIED_SCOPE",
            )
        elif value_basis == "SAMPLED_ESTIMATE":
            population, state, ratio_state = (
                "REPORTED_ESTIMATES_ONLY",
                "ESTIMATED_NOT_OBSERVED",
                "NOT_IDENTIFIED_FROM_ESTIMATES",
            )
        else:
            population, state, ratio_state = (
                "REPORT_VALUE_BASIS_UNRESOLVED",
                "VALUE_BASIS_UNKNOWN",
                "NOT_IDENTIFIED_VALUE_BASIS",
            )
        return {
            **envelope,
            **nulls,
            "population": population,
            "state": state,
            "ratio_state": ratio_state,
        }
    total = ad + counts["merchant"] + counts["unclassified"]
    result: dict[str, object] = {
        **envelope,
        "total_observed_clicks": total,
        "ad_clicks": ad,
        "ordinary_clicks": counts["merchant"],
        "unclassified_clicks": counts["unclassified"],
        "classification_coverage": None,
        "ad_share_exact": None,
        "ad_share_bounds": None,
        "state": "NO_OBSERVATIONS"
        if total == 0
        else ("PARTIALLY_CLASSIFIED" if counts["unclassified"] else "CLASSIFIED"),
        "ratio_state": "RETURNED_EVENTS_ARITHMETIC_ONLY" if total else "NO_DENOMINATOR",
    }
    if total:
        result["classification_coverage"] = (ad + counts["merchant"]) / total
        result["ad_share_bounds"] = [ad / total, (ad + counts["unclassified"]) / total]
        if not counts["unclassified"]:
            result["ad_share_exact"] = ad / total
    return result


def _import_ga4_profile(
    service: LiveGoogleAnalyticsImport,
    arguments: argparse.Namespace,
    site_id: UUID,
    ga4_job_id: UUID,
    started_at: datetime,
    private_root: Path,
) -> None:
    purchase = arguments.profile == "purchase-v2"
    date_from, date_to = _date(arguments.date_from), _date(arguments.date_to)
    suffix = f"{date_from:%Y%m%d}-{date_to:%Y%m%d}"
    views_job_id = ga4_job_id
    if purchase:
        views_job_id = _uuid(getattr(arguments, "ga4_views_job_id", None))
        if views_job_id.int == 0 or views_job_id == ga4_job_id:
            raise EditorialEconomicsV3Failure(
                "RAOS_EDITORIAL_V3_GOOGLE_DISTINCT_VIEWS_JOB_REQUIRED"
            )

    def fetch(dimensions: tuple[str, ...], label: str) -> Ga4ImportBatch:
        return service.import_ga4_with_batch(
            context=GoogleImportExecutionContext(
                display_id=f"AIR-GA4-{label}-{suffix}",
                site_id=site_id,
                ops_job_id=views_job_id if label == "VIEWS" else ga4_job_id,
                started_at=started_at,
            ),
            date_from=date_from,
            date_to=date_to,
            dimensions=dimensions,
        )[0]

    batch = fetch(
        GA4_PURCHASE_DIMENSIONS_V2 if purchase else GA4_BASELINE_DIMENSIONS,
        "PURCHASE" if purchase else "LEGACY",
    )
    document = (
        ga4_purchase_document_v2(
            batch, page_views=fetch(GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2, "VIEWS")
        )
        if purchase
        else ga4_baseline_document(batch)
    )
    write_private_json(private_root, arguments.ga4_output, document)


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    private_root = arguments.private_root
    try:
        if arguments.command == "import-ga4":
            plan = _ga4_profile_plan(arguments)
            if arguments.plan:
                print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
                return 0
            if not all(
                getattr(arguments, name)
                for name in (
                    "database_name",
                    "database_user",
                    "database_password",
                    "ga4_output",
                )
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_GOOGLE_IMPORT_ARGUMENT_REQUIRED"
                )
            if arguments.profile == "purchase-v2":
                _uuid(arguments.ga4_views_job_id)
            _refresh_baseline(
                arguments=arguments, private_root=private_root, portfolio=None
            )
            return 0
        if arguments.command == "summarize-purchase-observations":
            document = read_private_json(private_root, arguments.ga4_input)
            bindings_path = Path(arguments.bindings)
            if not bindings_path.is_absolute():
                bindings_path = REPOSITORY_ROOT / bindings_path
            bindings_path = bindings_path.resolve()
            if (
                not bindings_path.is_relative_to(REPOSITORY_ROOT.resolve())
                or not bindings_path.is_file()
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_OBSERVATION_BINDINGS_INVALID"
                )
            runtime = json.loads(bindings_path.read_text(encoding="utf-8"))
            bindings = [
                binding
                for article in runtime.get("articles", [])
                for binding in article.get("bindings", [])
            ]
            summary = purchase_observation_summary(
                document,
                bindings,
                value_basis=arguments.value_basis,
                quality_flags=arguments.quality_flag,
                scope_unknown=arguments.scope_unknown,
            )
            if arguments.output:
                write_private_json(private_root, arguments.output, summary)
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return 0
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
