#!/usr/bin/env python3
"""Run the owner-private Editorial V3 economics workflow."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Final, Mapping


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    EditorialPortfolioV3Failure,
    load_editorial_portfolio_v3,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    bind_rakuten_profile,
    build_baseline_report,
    canonical_json_bytes,
    commit_rakuten_report,
    cost_input_template,
    detect_rakuten_sample,
    establish_t0_receipt,
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
    followups.add_argument("--as-of", required=True)
    followups.add_argument("--output", required=True)
    return parser


def _optional_json(private_root: Path, name: str | None) -> Mapping[str, object] | None:
    return read_private_json(private_root, name) if name is not None else None


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
            report = read_private_bytes(private_root, arguments.report)
            profile_content = read_private_bytes(private_root, arguments.profile)
            profile = read_private_json(private_root, arguments.profile)
            dry_run = read_private_json(private_root, arguments.dry_run)
            reparsed = parse_rakuten_report(
                content=report,
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
            receipt = establish_t0_receipt(
                document=observation,
                observation_sha256=sha256_bytes(observation_content),
                portfolio=portfolio,
                evaluated_at=datetime.now(UTC),
            )
            write_private_json(private_root, arguments.output, receipt)
        elif arguments.command == "baseline":
            report = build_baseline_report(
                portfolio=portfolio,
                rakuten_commit=_optional_json(private_root, arguments.rakuten_commit),
                cost_input=_optional_json(private_root, arguments.cost_input),
                gsc_input=_optional_json(private_root, arguments.gsc_input),
                ga4_input=_optional_json(private_root, arguments.ga4_input),
                t0_receipt=_optional_json(private_root, arguments.t0_receipt),
                generated_at=datetime.now(UTC),
            )
            write_private_bytes(
                private_root, arguments.json_output, canonical_json_bytes(report)
            )
            write_private_bytes(
                private_root, arguments.html_output, render_baseline_html(report)
            )
        elif arguments.command == "evaluate-followups":
            baseline_content = read_private_bytes(private_root, arguments.baseline)
            evaluation = evaluate_followups(
                baseline=read_private_json(private_root, arguments.baseline),
                baseline_sha256=sha256_bytes(baseline_content),
                portfolio=portfolio,
                as_of=arguments.as_of,
                generated_at=datetime.now(UTC),
            )
            write_private_json(private_root, arguments.output, evaluation)
        else:
            raise AssertionError("unreachable")
        print(
            f"RAOS_EDITORIAL_V3_OWNER_PRIVATE command={arguments.command} status=PASS"
        )
        return 0
    except (EditorialEconomicsV3Failure, EditorialPortfolioV3Failure) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
