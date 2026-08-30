#!/usr/bin/env python3
"""Run the owner-private Editorial V3 economics workflow."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path
import sys
from typing import Final, Mapping
from uuid import UUID


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    EditorialPortfolioV3,
    EditorialPortfolioV3Failure,
    PORTFOLIO_RELATIVE_PATH,
    load_editorial_portfolio_v3,
)
from raos.application.editorial.rakuten_measurement_activation_v3 import (  # noqa: E402
    RakutenMeasurementActivationV3Failure,
    validate_rakuten_measurement_activation_v3,
)
from raos.adapters.google_live_database import (  # noqa: E402
    LocalGoogleAnalyticsDatabaseTarget,
    create_local_google_analytics_engine,
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
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    bind_rakuten_profile,
    build_baseline_report,
    candidate_query_demand_template,
    canonical_json_bytes,
    commit_rakuten_report,
    cost_input_template,
    detect_rakuten_sample,
    establish_t0_receipt,
    evaluate_followups,
    parse_rakuten_report,
    production_readback_template,
    private_path,
    rakuten_binding_template,
    read_private_bytes,
    read_private_json,
    render_baseline_html,
    sha256_bytes,
    write_private_bytes,
    write_private_json,
)


DEFAULT_PRIVATE_ROOT: Final = REPOSITORY_ROOT / ".secrets/editorial-portfolio-v3"


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
    refresh.add_argument("--site-id", required=True)
    refresh.add_argument("--gsc-ops-job-id", required=True)
    refresh.add_argument("--ga4-ops-job-id", required=True)
    refresh.add_argument("--database-host", default="127.0.0.1")
    refresh.add_argument("--database-port", type=int, default=5432)
    refresh.add_argument("--database-name", required=True)
    refresh.add_argument("--database-user", required=True)
    refresh.add_argument(
        "--database-password",
        required=True,
        help="relative 0600 password file below --private-root",
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
    except (TypeError, ValueError):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_DATE_INVALID"
        ) from None


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise EditorialEconomicsV3Failure(
            "RAOS_EDITORIAL_V3_GOOGLE_IDENTITY_INVALID"
        ) from None


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
    site_id = _uuid(arguments.site_id)
    gsc_job_id = _uuid(arguments.gsc_ops_job_id)
    ga4_job_id = _uuid(arguments.ga4_ops_job_id)
    started_at = datetime.now(UTC)
    target = LocalGoogleAnalyticsDatabaseTarget(
        host=arguments.database_host,
        port=arguments.database_port,
        database=arguments.database_name,
        user=arguments.database_user,
        password_file=private_path(private_root, arguments.database_password),
    )
    engine = create_local_google_analytics_engine(target)
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
    private_root = arguments.private_root.resolve()
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
                detection, detection_sha256=sha256_bytes(detection_content)
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
            rakuten_report_content = read_private_bytes(
                private_root, arguments.report
            )
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
            observation_content = read_private_bytes(
                private_root, arguments.observation
            )
            observation = read_private_json(private_root, arguments.observation)
            activation_content = read_private_bytes(
                private_root, arguments.rakuten_activation_dry_run
            )
            activation = read_private_json(
                private_root, arguments.rakuten_activation_dry_run
            )
            activation_path = private_path(
                private_root, arguments.rakuten_activation_dry_run
            )
            validated_activation = validate_rakuten_measurement_activation_v3(
                repository_root=REPOSITORY_ROOT,
                dry_run_path=activation_path,
                portfolio=portfolio,
                require_recent=False,
            )
            if validated_activation.dry_run_sha256 != sha256_bytes(
                activation_content
            ):
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID"
                )
            try:
                portfolio_content = (REPOSITORY_ROOT / PORTFOLIO_RELATIVE_PATH).read_bytes()
            except OSError:
                raise EditorialEconomicsV3Failure(
                    "RAOS_EDITORIAL_V3_PORTFOLIO_UNAVAILABLE"
                ) from None
            receipt = establish_t0_receipt(
                document=observation,
                observation_sha256=sha256_bytes(observation_content),
                rakuten_activation=activation,
                rakuten_activation_sha256=sha256_bytes(activation_content),
                expected_portfolio_sha256=sha256_bytes(portfolio_content),
                portfolio=portfolio,
                evaluated_at=datetime.now(UTC),
            )
            write_private_json(private_root, arguments.output, receipt)
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
        RakutenMeasurementActivationV3Failure,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
