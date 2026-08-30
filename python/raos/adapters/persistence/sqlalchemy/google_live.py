"""PostgreSQL persistence for owner-authorized live Google analytics imports.

The adapter accepts only the verified worker-command Engine profile.  Each
provider batch, its import-run receipt, and every observation revision commit
in one transaction.  Search Console query text is reduced to a SHA-256 before
any SQL parameters are constructed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import NoReturn, cast, final
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import TextClause, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import (
    SqlAlchemyEngineProvider,
    checkout_verified,
    close_checkout,
    create_session,
    invalidate_and_close,
)
from raos.domain.analytics.google_live import (
    Ga4ImportBatch,
    GoogleImportCommitResult,
    GoogleImportExecutionContext,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    SearchConsoleImportBatch,
    canonical_json_bytes,
    fail_google,
    sha256_hex,
)


_GSC_DIMENSIONS = ("date", "query", "page", "country", "device")
_SHA256_PATTERN = "^[0-9a-f]{64}$"


def _persistence_failure() -> NoReturn:
    fail_google(GoogleProviderFailureCode.PERSISTENCE_FAILED)


def _json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.utcoffset() is None or value.fold:
        _persistence_failure()
    observed = value
    if observed.utcoffset() != timezone.utc.utcoffset(observed):
        _persistence_failure()
    return observed.astimezone(timezone.utc)


def _uuid(value: object) -> UUID:
    if type(value) is not UUID:
        _persistence_failure()
    return value


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        _persistence_failure()
    return value


def _mapping(row: object, fields: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(row, RowMapping):
        _persistence_failure()
    values = cast(Mapping[str, object], row)
    if frozenset(values) != fields:
        _persistence_failure()
    return values


def _decimal_text(value: float, quantum: str) -> str:
    return format(
        Decimal(str(value)).quantize(Decimal(quantum), rounding=ROUND_HALF_EVEN),
        "f",
    )


@dataclass(frozen=True, slots=True, repr=False)
class _PreparedGscRow:
    metric_date: date
    dimension_key_sha256: str
    query_sha256: str
    page_path: str
    page_url_sha256: str
    country_code: str
    device: str
    clicks: int
    impressions: int
    ctr: str
    average_position: str
    source_request_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class _PreparedGa4Row:
    metric_date: date
    grain_key_sha256: str
    dimensions_json: str
    metrics_json: str
    is_thresholded: bool
    source_request_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class _PreparedImport:
    provider_resource_sha256: str
    dimensions_document: Mapping[str, object]
    dimensions_json: str
    page_request_sha256s_json: str
    batch_sha256: str


def _prepare_gsc(
    batch: SearchConsoleImportBatch,
) -> tuple[_PreparedImport, tuple[_PreparedGscRow, ...]]:
    page_hashes = frozenset(batch.page_request_sha256s)
    if len(page_hashes) != len(batch.page_request_sha256s):
        _persistence_failure()
    rows: list[_PreparedGscRow] = []
    grains: set[tuple[date, str]] = set()
    for observation in batch.rows:
        grain = (observation.metric_date, observation.dimension_key_sha256)
        if (
            observation.metric_date < batch.date_from
            or observation.metric_date > batch.date_to
            or observation.source_request_sha256 not in page_hashes
            or grain in grains
        ):
            _persistence_failure()
        grains.add(grain)
        query_sha256 = sha256_hex(observation.query_text.encode("utf-8"))
        page_url_sha256 = sha256_hex(observation.page_url.encode("utf-8"))
        page_path = urlsplit(observation.page_url).path or "/"
        ctr = _decimal_text(observation.ctr, "0.00000001")
        average_position = _decimal_text(observation.average_position, "0.0001")
        content_sha256 = sha256_hex(
            canonical_json_bytes(
                {
                    "average_position": average_position,
                    "clicks": observation.clicks,
                    "country_code": observation.country_code,
                    "ctr": ctr,
                    "device": observation.device,
                    "dimension_key_sha256": observation.dimension_key_sha256,
                    "impressions": observation.impressions,
                    "page_path": page_path,
                    "page_url_sha256": page_url_sha256,
                    "query_sha256": query_sha256,
                }
            )
        )
        rows.append(
            _PreparedGscRow(
                metric_date=observation.metric_date,
                dimension_key_sha256=observation.dimension_key_sha256,
                query_sha256=query_sha256,
                page_path=page_path,
                page_url_sha256=page_url_sha256,
                country_code=observation.country_code,
                device=observation.device,
                clicks=observation.clicks,
                impressions=observation.impressions,
                ctr=ctr,
                average_position=average_position,
                source_request_sha256=observation.source_request_sha256,
                content_sha256=content_sha256,
            )
        )
    rows.sort(key=lambda item: (item.metric_date, item.dimension_key_sha256))
    dimensions_document: Mapping[str, object] = {
        "dimensions": list(_GSC_DIMENSIONS),
        "rows_not_guaranteed_complete": True,
    }
    provider_resource_sha256 = sha256_hex(batch.site_url.encode("utf-8"))
    batch_sha256 = sha256_hex(
        canonical_json_bytes(
            {
                "date_from": batch.date_from.isoformat(),
                "date_to": batch.date_to.isoformat(),
                "dimensions": dimensions_document,
                "page_request_sha256s": list(batch.page_request_sha256s),
                "provider_resource_sha256": provider_resource_sha256,
                "provider_row_count": batch.provider_row_count,
                "request_sha256": batch.request_sha256,
                "rows": [
                    {
                        "content_sha256": item.content_sha256,
                        "dimension_key_sha256": item.dimension_key_sha256,
                        "metric_date": item.metric_date.isoformat(),
                        "source_request_sha256": item.source_request_sha256,
                    }
                    for item in rows
                ],
                "site_id": str(batch.site_id),
            }
        )
    )
    return (
        _PreparedImport(
            provider_resource_sha256=provider_resource_sha256,
            dimensions_document=dimensions_document,
            dimensions_json=_json_text(dimensions_document),
            page_request_sha256s_json=_json_text(list(batch.page_request_sha256s)),
            batch_sha256=batch_sha256,
        ),
        tuple(rows),
    )


def _prepare_ga4(
    batch: Ga4ImportBatch,
) -> tuple[_PreparedImport, tuple[_PreparedGa4Row, ...]]:
    page_hashes = frozenset(batch.page_request_sha256s)
    if len(page_hashes) != len(batch.page_request_sha256s):
        _persistence_failure()
    rows: list[_PreparedGa4Row] = []
    grains: set[tuple[date, str]] = set()
    for observation in batch.rows:
        grain = (observation.metric_date, observation.grain_key_sha256)
        if (
            observation.metric_date < batch.date_from
            or observation.metric_date > batch.date_to
            or observation.source_request_sha256 not in page_hashes
            or grain in grains
            or tuple(name for name, _value in observation.dimensions)
            != batch.dimensions
            or tuple(name for name, _value in observation.metrics) != batch.metrics
        ):
            _persistence_failure()
        grains.add(grain)
        dimensions = dict(observation.dimensions)
        metrics = dict(observation.metrics)
        content_sha256 = sha256_hex(
            canonical_json_bytes(
                {
                    "dimensions": dimensions,
                    "grain_key_sha256": observation.grain_key_sha256,
                    "is_thresholded": observation.is_thresholded,
                    "metrics": metrics,
                    "property_id": batch.property_id,
                }
            )
        )
        rows.append(
            _PreparedGa4Row(
                metric_date=observation.metric_date,
                grain_key_sha256=observation.grain_key_sha256,
                dimensions_json=_json_text(dimensions),
                metrics_json=_json_text(metrics),
                is_thresholded=observation.is_thresholded,
                source_request_sha256=observation.source_request_sha256,
                content_sha256=content_sha256,
            )
        )
    rows.sort(key=lambda item: (item.metric_date, item.grain_key_sha256))
    dimensions_document: Mapping[str, object] = {
        "data_loss_from_other_row": batch.data_loss_from_other_row,
        "dimensions": list(batch.dimensions),
        "metrics": list(batch.metrics),
        "subject_to_thresholding": batch.subject_to_thresholding,
    }
    provider_resource_sha256 = sha256_hex(
        batch.configuration.property_resource.encode("utf-8")
    )
    configuration = batch.configuration
    batch_sha256 = sha256_hex(
        canonical_json_bytes(
            {
                "configuration": {
                    "property_response_sha256": (
                        configuration.property_response_sha256
                    ),
                    "reporting_identity_response_sha256": (
                        configuration.reporting_identity_response_sha256
                    ),
                    "snapshot_sha256": configuration.snapshot_sha256,
                },
                "date_from": batch.date_from.isoformat(),
                "date_to": batch.date_to.isoformat(),
                "dimensions": dimensions_document,
                "page_request_sha256s": list(batch.page_request_sha256s),
                "property_id": batch.property_id,
                "provider_resource_sha256": provider_resource_sha256,
                "provider_row_count": batch.provider_row_count,
                "request_sha256": batch.request_sha256,
                "rows": [
                    {
                        "content_sha256": item.content_sha256,
                        "grain_key_sha256": item.grain_key_sha256,
                        "metric_date": item.metric_date.isoformat(),
                        "source_request_sha256": item.source_request_sha256,
                    }
                    for item in rows
                ],
                "site_id": str(batch.site_id),
            }
        )
    )
    return (
        _PreparedImport(
            provider_resource_sha256=provider_resource_sha256,
            dimensions_document=dimensions_document,
            dimensions_json=_json_text(dimensions_document),
            page_request_sha256s_json=_json_text(list(batch.page_request_sha256s)),
            batch_sha256=batch_sha256,
        ),
        tuple(rows),
    )


_REPLAY_FIELDS = frozenset(
    {
        "id",
        "display_id",
        "site_id",
        "source_type",
        "status",
        "date_from",
        "date_to",
        "dimensions",
        "request_sha256",
        "page_request_sha256s",
        "provider_resource_sha256",
        "provider_property_id",
        "batch_sha256",
        "provider_row_count",
        "inserted_count",
        "unchanged_count",
        "superseded_count",
        "completed_at",
        "live_contract_version",
        "config_property_id",
        "config_snapshot_sha256",
        "config_property_response_sha256",
        "config_reporting_identity_response_sha256",
    }
)


_REPLAY_SQL = text(
    """
    SELECT run.id,
           run.display_id,
           run.site_id,
           run.source_type,
           run.status,
           run.date_from,
           run.date_to,
           run.dimensions,
           run.request_sha256,
           run.page_request_sha256s,
           run.provider_resource_sha256,
           run.provider_property_id,
           run.batch_sha256,
           run.provider_row_count,
           run.inserted_count,
           run.unchanged_count,
           run.superseded_count,
           run.completed_at,
           run.live_contract_version,
           config.property_id AS config_property_id,
           config.snapshot_sha256 AS config_snapshot_sha256,
           config.property_response_sha256 AS config_property_response_sha256,
           config.reporting_identity_response_sha256
               AS config_reporting_identity_response_sha256
      FROM analytics.import_run AS run
      LEFT JOIN analytics.ga4_property_config_snapshot AS config
        ON config.id = run.ga4_configuration_snapshot_id
     WHERE run.ops_job_id = :ops_job_id
     FOR UPDATE OF run
    """
)


def _replay_result(
    *,
    session: Session,
    context: GoogleImportExecutionContext,
    source_type: str,
    date_from: date,
    date_to: date,
    request_sha256: str,
    page_request_sha256s: tuple[str, ...],
    provider_row_count: int,
    prepared: _PreparedImport,
    property_id: str | None,
    config_hashes: tuple[str, str, str] | None,
) -> GoogleImportCommitResult | None:
    candidate = (
        session.execute(_REPLAY_SQL, {"ops_job_id": context.ops_job_id})
        .mappings()
        .one_or_none()
    )
    if candidate is None:
        return None
    row = _mapping(candidate, _REPLAY_FIELDS)
    stored_page_hashes = row["page_request_sha256s"]
    stored_dimensions = row["dimensions"]
    observed_config = (
        cast(str, row["config_property_id"]),
        cast(str, row["config_property_response_sha256"]),
        cast(str, row["config_reporting_identity_response_sha256"]),
        cast(str, row["config_snapshot_sha256"]),
    )
    expected_config = (
        None
        if config_hashes is None or property_id is None
        else (property_id, config_hashes[0], config_hashes[1], config_hashes[2])
    )
    if (
        row["display_id"] != context.display_id
        or row["site_id"] != context.site_id
        or row["source_type"] != source_type
        or row["status"] != "SUCCEEDED"
        or row["date_from"] != date_from
        or row["date_to"] != date_to
        or stored_dimensions != prepared.dimensions_document
        or row["request_sha256"] != request_sha256
        or type(stored_page_hashes) is not list
        or tuple(cast(list[object], stored_page_hashes)) != page_request_sha256s
        or row["provider_resource_sha256"] != prepared.provider_resource_sha256
        or row["provider_property_id"] != property_id
        or row["batch_sha256"] != prepared.batch_sha256
        or row["provider_row_count"] != provider_row_count
        or row["live_contract_version"] != 1
        or (observed_config if config_hashes is not None else None) != expected_config
        or (config_hashes is None and any(item is not None for item in observed_config))
    ):
        _persistence_failure()
    return GoogleImportCommitResult(
        import_run_id=_uuid(row["id"]),
        inserted_count=_integer(row["inserted_count"]),
        unchanged_count=_integer(row["unchanged_count"]),
        superseded_count=_integer(row["superseded_count"]),
        completed_at=_utc(row["completed_at"]),
    )


def _lock_scope(session: Session, context: GoogleImportExecutionContext) -> None:
    site_id = session.execute(
        text("SELECT id FROM portfolio.site WHERE id = :site_id FOR UPDATE"),
        {"site_id": context.site_id},
    ).scalar_one_or_none()
    job_site_id = session.execute(
        text("SELECT site_id FROM ops.job WHERE id = :job_id FOR UPDATE"),
        {"job_id": context.ops_job_id},
    ).scalar_one_or_none()
    if site_id != context.site_id or job_site_id != context.site_id:
        _persistence_failure()


_INSERT_IMPORT_SQL = text(
    """
    INSERT INTO analytics.import_run (
        display_id,
        site_id,
        source_type,
        ops_job_id,
        status,
        date_from,
        date_to,
        dimensions,
        row_count,
        inserted_count,
        rejected_count,
        unchanged_count,
        superseded_count,
        provider_row_count,
        request_sha256,
        page_request_sha256s,
        provider_resource_sha256,
        provider_property_id,
        batch_sha256,
        provider_retrieved_at,
        ga4_configuration_snapshot_id,
        live_contract_version,
        started_at
    ) VALUES (
        :display_id,
        :site_id,
        :source_type,
        :ops_job_id,
        'RUNNING',
        :date_from,
        :date_to,
        CAST(:dimensions AS jsonb),
        :row_count,
        0,
        0,
        0,
        0,
        :provider_row_count,
        :request_sha256,
        CAST(:page_request_sha256s AS jsonb),
        :provider_resource_sha256,
        :provider_property_id,
        :batch_sha256,
        :provider_retrieved_at,
        :ga4_configuration_snapshot_id,
        1,
        :started_at
    )
    RETURNING id
    """
)


def _insert_import_run(
    *,
    session: Session,
    context: GoogleImportExecutionContext,
    source_type: str,
    date_from: date,
    date_to: date,
    request_sha256: str,
    page_request_sha256s: tuple[str, ...],
    retrieved_at: datetime,
    provider_row_count: int,
    prepared: _PreparedImport,
    property_id: str | None,
    configuration_snapshot_id: UUID | None,
) -> UUID:
    value = session.execute(
        _INSERT_IMPORT_SQL,
        {
            "display_id": context.display_id,
            "site_id": context.site_id,
            "source_type": source_type,
            "ops_job_id": context.ops_job_id,
            "date_from": date_from,
            "date_to": date_to,
            "dimensions": prepared.dimensions_json,
            "row_count": provider_row_count,
            "provider_row_count": provider_row_count,
            "request_sha256": request_sha256,
            "page_request_sha256s": prepared.page_request_sha256s_json,
            "provider_resource_sha256": prepared.provider_resource_sha256,
            "provider_property_id": property_id,
            "batch_sha256": prepared.batch_sha256,
            "provider_retrieved_at": retrieved_at,
            "ga4_configuration_snapshot_id": configuration_snapshot_id,
            "started_at": context.started_at,
        },
    ).scalar_one()
    return _uuid(value)


def _finish_import(
    *,
    session: Session,
    import_run_id: UUID,
    inserted_count: int,
    unchanged_count: int,
    superseded_count: int,
) -> GoogleImportCommitResult:
    completed_at = session.execute(
        text(
            """
            UPDATE analytics.import_run
               SET status = 'SUCCEEDED',
                   inserted_count = :inserted_count,
                   unchanged_count = :unchanged_count,
                   superseded_count = :superseded_count,
                   completed_at = clock_timestamp()
             WHERE id = :import_run_id
               AND status = 'RUNNING'
            RETURNING completed_at
            """
        ),
        {
            "import_run_id": import_run_id,
            "inserted_count": inserted_count,
            "unchanged_count": unchanged_count,
            "superseded_count": superseded_count,
        },
    ).scalar_one()
    return GoogleImportCommitResult(
        import_run_id=import_run_id,
        inserted_count=inserted_count,
        unchanged_count=unchanged_count,
        superseded_count=superseded_count,
        completed_at=_utc(completed_at),
    )


def _configuration_snapshot_id(session: Session, batch: Ga4ImportBatch) -> UUID:
    configuration = batch.configuration
    session.execute(
        text(
            """
            INSERT INTO analytics.ga4_property_config_snapshot (
                site_id,
                property_id,
                property_resource,
                display_name,
                time_zone,
                currency_code,
                reporting_identity,
                retrieved_at,
                property_response_sha256,
                reporting_identity_response_sha256,
                snapshot_sha256
            ) VALUES (
                :site_id,
                :property_id,
                :property_resource,
                :display_name,
                :time_zone,
                :currency_code,
                :reporting_identity,
                :retrieved_at,
                :property_response_sha256,
                :reporting_identity_response_sha256,
                :snapshot_sha256
            )
            ON CONFLICT (
                site_id,
                property_id,
                property_response_sha256,
                reporting_identity_response_sha256
            ) DO NOTHING
            """
        ),
        {
            "site_id": batch.site_id,
            "property_id": configuration.property_id,
            "property_resource": configuration.property_resource,
            "display_name": configuration.display_name,
            "time_zone": configuration.time_zone,
            "currency_code": configuration.currency_code,
            "reporting_identity": configuration.reporting_identity,
            "retrieved_at": configuration.retrieved_at,
            "property_response_sha256": configuration.property_response_sha256,
            "reporting_identity_response_sha256": (
                configuration.reporting_identity_response_sha256
            ),
            "snapshot_sha256": configuration.snapshot_sha256,
        },
    )
    candidate = (
        session.execute(
            text(
                """
                SELECT id,
                       property_resource,
                       display_name,
                       time_zone,
                       currency_code,
                       reporting_identity,
                       snapshot_sha256
                  FROM analytics.ga4_property_config_snapshot
                 WHERE site_id = :site_id
                   AND property_id = :property_id
                   AND property_response_sha256 = :property_response_sha256
                   AND reporting_identity_response_sha256 =
                       :reporting_identity_response_sha256
                 FOR SHARE
                """
            ),
            {
                "site_id": batch.site_id,
                "property_id": configuration.property_id,
                "property_response_sha256": configuration.property_response_sha256,
                "reporting_identity_response_sha256": (
                    configuration.reporting_identity_response_sha256
                ),
            },
        )
        .mappings()
        .one_or_none()
    )
    fields = frozenset(
        {
            "id",
            "property_resource",
            "display_name",
            "time_zone",
            "currency_code",
            "reporting_identity",
            "snapshot_sha256",
        }
    )
    row = _mapping(candidate, fields)
    if (
        row["property_resource"] != configuration.property_resource
        or row["display_name"] != configuration.display_name
        or row["time_zone"] != configuration.time_zone
        or row["currency_code"] != configuration.currency_code
        or row["reporting_identity"] != configuration.reporting_identity
        or row["snapshot_sha256"] != configuration.snapshot_sha256
    ):
        _persistence_failure()
    return _uuid(row["id"])


_GSC_CURRENT_SQL = text(
    """
    SELECT id, content_sha256, observation_revision
      FROM analytics.gsc_observation
     WHERE site_id = :site_id
       AND metric_date = :metric_date
       AND dimension_key_sha256 = :grain_sha256
       AND is_current IS TRUE
     FOR UPDATE
    """
)


_GA4_CURRENT_SQL = text(
    """
    SELECT id, content_sha256, observation_revision
      FROM analytics.ga4_observation
     WHERE site_id = :site_id
       AND metric_date = :metric_date
       AND grain_key_sha256 = :grain_sha256
       AND is_current IS TRUE
     FOR UPDATE
    """
)


_CURRENT_FIELDS = frozenset({"id", "content_sha256", "observation_revision"})


def _current_revision(
    *,
    session: Session,
    statement: TextClause,
    site_id: UUID,
    metric_date: date,
    grain_sha256: str,
) -> tuple[UUID, str, int] | None:
    candidate = (
        session.execute(
            statement,
            {
                "site_id": site_id,
                "metric_date": metric_date,
                "grain_sha256": grain_sha256,
            },
        )
        .mappings()
        .one_or_none()
    )
    if candidate is None:
        return None
    row = _mapping(candidate, _CURRENT_FIELDS)
    content_sha256 = row["content_sha256"]
    revision = row["observation_revision"]
    if type(content_sha256) is not str or type(revision) is not int or revision < 1:
        _persistence_failure()
    return _uuid(row["id"]), content_sha256, revision


def _supersede(
    *, session: Session, table: str, observation_id: UUID, import_run_id: UUID
) -> None:
    statements = {
        "gsc": text(
            """
            UPDATE analytics.gsc_observation
               SET is_current = false,
                   superseded_by_import_run_id = :import_run_id,
                   superseded_at = clock_timestamp()
             WHERE id = :observation_id
               AND is_current IS TRUE
            RETURNING id
            """
        ),
        "ga4": text(
            """
            UPDATE analytics.ga4_observation
               SET is_current = false,
                   superseded_by_import_run_id = :import_run_id,
                   superseded_at = clock_timestamp()
             WHERE id = :observation_id
               AND is_current IS TRUE
            RETURNING id
            """
        ),
    }
    updated_id = session.execute(
        statements[table],
        {"observation_id": observation_id, "import_run_id": import_run_id},
    ).scalar_one_or_none()
    if updated_id != observation_id:
        _persistence_failure()


_INSERT_GSC_SQL = text(
    """
    INSERT INTO analytics.gsc_observation (
        import_run_id,
        site_id,
        metric_date,
        query_sha256,
        page_path,
        page_url_sha256,
        country_code,
        device,
        search_appearance,
        clicks,
        impressions,
        ctr,
        average_position,
        is_privacy_suppressed,
        dimension_key_sha256,
        source_request_sha256,
        content_sha256,
        observation_revision,
        supersedes_observation_id,
        is_current,
        live_contract_version
    ) VALUES (
        :import_run_id,
        :site_id,
        :metric_date,
        :query_sha256,
        :page_path,
        :page_url_sha256,
        :country_code,
        :device,
        NULL,
        :clicks,
        :impressions,
        CAST(:ctr AS numeric(10,8)),
        CAST(:average_position AS numeric(10,4)),
        false,
        :dimension_key_sha256,
        :source_request_sha256,
        :content_sha256,
        :observation_revision,
        :supersedes_observation_id,
        true,
        1
    )
    """
)


_INSERT_GA4_SQL = text(
    """
    INSERT INTO analytics.ga4_observation (
        import_run_id,
        site_id,
        metric_date,
        dimension_schema_version,
        dimensions,
        metrics,
        grain_key_sha256,
        is_thresholded,
        property_id,
        source_request_sha256,
        content_sha256,
        observation_revision,
        supersedes_observation_id,
        is_current,
        live_contract_version
    ) VALUES (
        :import_run_id,
        :site_id,
        :metric_date,
        1,
        CAST(:dimensions AS jsonb),
        CAST(:metrics AS jsonb),
        :grain_key_sha256,
        :is_thresholded,
        :property_id,
        :source_request_sha256,
        :content_sha256,
        :observation_revision,
        :supersedes_observation_id,
        true,
        1
    )
    """
)


@final
class SqlAlchemyAnalyticsImportRepository:
    """Atomic live-import repository bound to ``WORKER_COMMAND`` identity."""

    __slots__ = ("_provider",)

    def __init__(self, provider: SqlAlchemyEngineProvider) -> None:
        if (
            type(provider) is not SqlAlchemyEngineProvider
            or provider.expected_profile is not WorkloadProfile.WORKER_COMMAND
        ):
            raise ValueError("INVALID_GOOGLE_ANALYTICS_IMPORT_REPOSITORY") from None
        self._provider = provider

    def _execute(
        self, operation: Callable[[Session], GoogleImportCommitResult]
    ) -> GoogleImportCommitResult:
        checkout = None
        session: Session | None = None
        try:
            checkout = checkout_verified(self._provider, None)
            session = create_session(self._provider, checkout)
            with session.begin():
                session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
                result = operation(session)
            session.close()
            close_checkout(self._provider, checkout)
            return result
        except GoogleProviderFailure:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            if checkout is not None:
                try:
                    close_checkout(self._provider, checkout)
                except Exception:
                    pass
            raise
        except Exception:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            if checkout is not None:
                try:
                    invalidate_and_close(self._provider, checkout)
                except Exception:
                    pass
            _persistence_failure()

    def commit_gsc(
        self,
        *,
        context: GoogleImportExecutionContext,
        batch: SearchConsoleImportBatch,
    ) -> GoogleImportCommitResult:
        if (
            type(context) is not GoogleImportExecutionContext
            or type(batch) is not SearchConsoleImportBatch
            or context.site_id != batch.site_id
        ):
            _persistence_failure()
        try:
            prepared, rows = _prepare_gsc(batch)
        except GoogleProviderFailure:
            raise
        except Exception:
            _persistence_failure()

        def operation(session: Session) -> GoogleImportCommitResult:
            _lock_scope(session, context)
            replay = _replay_result(
                session=session,
                context=context,
                source_type="GSC",
                date_from=batch.date_from,
                date_to=batch.date_to,
                request_sha256=batch.request_sha256,
                page_request_sha256s=batch.page_request_sha256s,
                provider_row_count=batch.provider_row_count,
                prepared=prepared,
                property_id=None,
                config_hashes=None,
            )
            if replay is not None:
                return replay
            import_run_id = _insert_import_run(
                session=session,
                context=context,
                source_type="GSC",
                date_from=batch.date_from,
                date_to=batch.date_to,
                request_sha256=batch.request_sha256,
                page_request_sha256s=batch.page_request_sha256s,
                retrieved_at=batch.retrieved_at,
                provider_row_count=batch.provider_row_count,
                prepared=prepared,
                property_id=None,
                configuration_snapshot_id=None,
            )
            inserted_count = 0
            unchanged_count = 0
            superseded_count = 0
            for row in rows:
                current = _current_revision(
                    session=session,
                    statement=_GSC_CURRENT_SQL,
                    site_id=batch.site_id,
                    metric_date=row.metric_date,
                    grain_sha256=row.dimension_key_sha256,
                )
                if current is not None and current[1] == row.content_sha256:
                    unchanged_count += 1
                    continue
                supersedes_id: UUID | None = None
                revision = 1
                if current is not None:
                    supersedes_id = current[0]
                    revision = current[2] + 1
                    _supersede(
                        session=session,
                        table="gsc",
                        observation_id=supersedes_id,
                        import_run_id=import_run_id,
                    )
                    superseded_count += 1
                session.execute(
                    _INSERT_GSC_SQL,
                    {
                        "import_run_id": import_run_id,
                        "site_id": batch.site_id,
                        "metric_date": row.metric_date,
                        "query_sha256": row.query_sha256,
                        "page_path": row.page_path,
                        "page_url_sha256": row.page_url_sha256,
                        "country_code": row.country_code,
                        "device": row.device,
                        "clicks": row.clicks,
                        "impressions": row.impressions,
                        "ctr": row.ctr,
                        "average_position": row.average_position,
                        "dimension_key_sha256": row.dimension_key_sha256,
                        "source_request_sha256": row.source_request_sha256,
                        "content_sha256": row.content_sha256,
                        "observation_revision": revision,
                        "supersedes_observation_id": supersedes_id,
                    },
                )
                inserted_count += 1
            return _finish_import(
                session=session,
                import_run_id=import_run_id,
                inserted_count=inserted_count,
                unchanged_count=unchanged_count,
                superseded_count=superseded_count,
            )

        return self._execute(operation)

    def commit_ga4(
        self,
        *,
        context: GoogleImportExecutionContext,
        batch: Ga4ImportBatch,
    ) -> GoogleImportCommitResult:
        if (
            type(context) is not GoogleImportExecutionContext
            or type(batch) is not Ga4ImportBatch
            or context.site_id != batch.site_id
        ):
            _persistence_failure()
        try:
            prepared, rows = _prepare_ga4(batch)
        except GoogleProviderFailure:
            raise
        except Exception:
            _persistence_failure()
        configuration = batch.configuration
        config_hashes = (
            configuration.property_response_sha256,
            configuration.reporting_identity_response_sha256,
            configuration.snapshot_sha256,
        )

        def operation(session: Session) -> GoogleImportCommitResult:
            _lock_scope(session, context)
            replay = _replay_result(
                session=session,
                context=context,
                source_type="GA4",
                date_from=batch.date_from,
                date_to=batch.date_to,
                request_sha256=batch.request_sha256,
                page_request_sha256s=batch.page_request_sha256s,
                provider_row_count=batch.provider_row_count,
                prepared=prepared,
                property_id=batch.property_id,
                config_hashes=config_hashes,
            )
            if replay is not None:
                return replay
            configuration_snapshot_id = _configuration_snapshot_id(session, batch)
            import_run_id = _insert_import_run(
                session=session,
                context=context,
                source_type="GA4",
                date_from=batch.date_from,
                date_to=batch.date_to,
                request_sha256=batch.request_sha256,
                page_request_sha256s=batch.page_request_sha256s,
                retrieved_at=batch.retrieved_at,
                provider_row_count=batch.provider_row_count,
                prepared=prepared,
                property_id=batch.property_id,
                configuration_snapshot_id=configuration_snapshot_id,
            )
            inserted_count = 0
            unchanged_count = 0
            superseded_count = 0
            for row in rows:
                current = _current_revision(
                    session=session,
                    statement=_GA4_CURRENT_SQL,
                    site_id=batch.site_id,
                    metric_date=row.metric_date,
                    grain_sha256=row.grain_key_sha256,
                )
                if current is not None and current[1] == row.content_sha256:
                    unchanged_count += 1
                    continue
                supersedes_id: UUID | None = None
                revision = 1
                if current is not None:
                    supersedes_id = current[0]
                    revision = current[2] + 1
                    _supersede(
                        session=session,
                        table="ga4",
                        observation_id=supersedes_id,
                        import_run_id=import_run_id,
                    )
                    superseded_count += 1
                session.execute(
                    _INSERT_GA4_SQL,
                    {
                        "import_run_id": import_run_id,
                        "site_id": batch.site_id,
                        "metric_date": row.metric_date,
                        "dimensions": row.dimensions_json,
                        "metrics": row.metrics_json,
                        "grain_key_sha256": row.grain_key_sha256,
                        "is_thresholded": row.is_thresholded,
                        "property_id": batch.property_id,
                        "source_request_sha256": row.source_request_sha256,
                        "content_sha256": row.content_sha256,
                        "observation_revision": revision,
                        "supersedes_observation_id": supersedes_id,
                    },
                )
                inserted_count += 1
            return _finish_import(
                session=session,
                import_run_id=import_run_id,
                inserted_count=inserted_count,
                unchanged_count=unchanged_count,
                superseded_count=superseded_count,
            )

        return self._execute(operation)


__all__ = ["SqlAlchemyAnalyticsImportRepository"]
