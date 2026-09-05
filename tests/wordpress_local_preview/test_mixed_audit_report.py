from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BROWSER = ROOT / "changes/wordpress-local-preview-v1/browser"
sys.path.insert(0, str(BROWSER))
spec = importlib.util.spec_from_file_location(
    "mixed_audit_report_test_owner", BROWSER / "mixed_audit_report.py"
)
assert spec and spec.loader
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


def inputs_and_results() -> tuple[dict, list[dict], dict]:
    inventory = json.loads(owner.INVENTORY.read_bytes())
    articles = [row for row in inventory["surfaces"] if row["kind"] == "article"]
    inputs = {
        "preparation_binding_sha256": "a" * 64,
        "origin": "http://127.0.0.1:39330",
        "scope": {
            "selected_article_ids": [row["article_id"] for row in articles],
            "articles": [
                {
                    "article_id": row["article_id"],
                    "expected_ctas": [],
                    "display_projection": {"state": "NOT_APPLICABLE"},
                }
                for row in articles
            ],
        },
    }
    for key in (
        "audit_inventory_sha256",
        "audit_script_sha256",
        "theme_contract_sha256",
        "theme_runtime_revision",
        "theme_source_fingerprint",
        "navigation_sha256",
    ):
        inputs[key] = "b" * 64
    results = []
    for surface in [*inventory["surfaces"], *inventory["local_surfaces"]]:
        for width in inventory["viewports"]:
            name = surface["surface_id"]
            results.append(
                {
                    "auditResultSchema": "RAOS_WORDPRESS_LOCAL_BROWSER_RESULT_V1",
                    "surface": name,
                    "width": width,
                    "localPath": surface["local_path"],
                    "productionPath": surface.get("production_path"),
                    "httpStatus": surface.get("expected_http_status", 200),
                    "mandatoryCounts": {key: 0 for key in owner.COUNT_FIELDS},
                    "profileSemantics": {
                        "publicationProfile": "verified-incremental",
                        "linkMode": "standard-api",
                        "preparationBindingSha256": "a" * 64,
                        "incrementalCommerceStatus": "NOT_INCLUDED"
                        if surface["kind"] == "article"
                        else "NOT_AN_ARTICLE",
                        "legacyMediaDisplayProjection": {"state": "NOT_APPLICABLE"}
                        if surface["kind"] == "article"
                        else None,
                    },
                    "screenshot": f"/tmp/recorded-fixture/local-preview-{name}-{width}.png",
                    "zoomScreenshot": f"/tmp/recorded-fixture/local-preview-{name}-zoom200.png"
                    if width == 390
                    else None,
                }
            )
    return inputs, results, inventory


def test_exact_raw_browser_results_cover_130_images_without_anonymous_pass() -> None:
    inputs, results, inventory = inputs_and_results()
    raw = (
        b"### Result\n"
        + json.dumps(results).encode()
        + b"\n### Ran Playwright code\nRecorded fixture\n"
    )
    parsed = owner.parse_results(raw)
    assert parsed == results
    assert len(owner.validate_results(parsed, inventory, inputs)) == 130


@pytest.mark.parametrize(
    "mutation",
    [
        "generic_pass",
        "missing_surface",
        "same_count_wrong_surface",
        "same_count_wrong_width",
        "wrong_path",
        "wrong_binding",
        "measured_mode",
        "axe",
        "overflow",
        "missing_zoom",
        "wrong_zoom",
        "false_commerce",
    ],
)
def test_anonymous_or_tampered_browser_success_is_rejected(mutation: str) -> None:
    inputs, results, inventory = inputs_and_results()
    if mutation == "generic_pass":
        results = [{"passed": True, "actionable_findings": 0}]
    elif mutation == "missing_surface":
        results.pop()
    elif mutation == "same_count_wrong_surface":
        results[-1]["surface"] = results[0]["surface"]
    elif mutation == "same_count_wrong_width":
        results[-1]["width"] = 1920
    elif mutation == "wrong_path":
        results[0]["localPath"] = "/wrong/"
    elif mutation == "wrong_binding":
        results[0]["profileSemantics"]["preparationBindingSha256"] = "c" * 64
    elif mutation == "measured_mode":
        results[0]["profileSemantics"]["linkMode"] = "measured-admin"
    elif mutation == "axe":
        results[0]["mandatoryCounts"]["actionableAxeViolations"] = 1
    elif mutation == "overflow":
        results[0]["mandatoryCounts"]["horizontalOverflow"] = 12
    elif mutation == "missing_zoom":
        results[1]["zoomScreenshot"] = None
    elif mutation == "wrong_zoom":
        results[1]["zoomScreenshot"] = "/tmp/wrong.png"
    else:
        row = next(
            row
            for row in results
            if row["profileSemantics"]["incrementalCommerceStatus"] == "NOT_INCLUDED"
        )
        row["profileSemantics"]["incrementalCommerceStatus"] = (
            "EXPECTED_VERIFIED_SET_PRESENT"
        )
    with pytest.raises(owner.ReportFailure):
        owner.validate_results(results, inventory, inputs)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"passed":true}',
        b"### Result\n[]\n### Result\n[]",
        b"### Error\nFailed\n### Result\n[]",
        b"### Result\n[]\nUnexpected",
    ],
)
def test_original_cli_output_must_be_one_successful_result(raw: bytes) -> None:
    with pytest.raises(owner.ReportFailure):
        owner.parse_results(raw)


def evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, bytes, Path, dict]:
    inputs, results, inventory = inputs_and_results()
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()
    names = owner.validate_results(results, inventory, inputs)
    for name in names:
        (screenshots / name).write_bytes(
            b"\x89PNG\r\n\x1a\nRecorded synthetic PNG fixture"
        )
    lighthouse = tmp_path / "lighthouse"
    lighthouse.mkdir()
    monkeypatch.setattr(owner, "LIGHTHOUSE", lighthouse)
    summary = {
        "schema": "RAOS_WORDPRESS_LIGHTHOUSE_MEDIAN_V2",
        "passed": True,
        "sample_count": 6,
        "repetitions": 3,
        "started_at": "2026-09-05T02:03:00+00:00",
        "captured_at": "2026-09-05T02:04:00+00:00",
        "inputs": {
            key: inputs[key]
            for key in (
                "audit_inventory_sha256",
                "audit_script_sha256",
                "theme_contract_sha256",
                "theme_runtime_revision",
                "theme_source_fingerprint",
                "navigation_sha256",
            )
        },
        "results": [],
    }
    sample = {"lcp_ms": 1200, "cls": 0, "tbt_ms": 50}
    for target in ("home", "article-a04"):
        url = inputs["origin"] + (
            "/"
            if target == "home"
            else "/local-preview-countertop-dishwasher-for-small-households/"
        )
        reports = []
        for index in range(1, 4):
            report = {
                "lighthouseVersion": "12.8.2",
                "requestedUrl": url,
                "finalDisplayedUrl": url,
                "fetchTime": "2026-09-05T02:03:30+00:00",
                "audits": {
                    "largest-contentful-paint": {"numericValue": 1200},
                    "cumulative-layout-shift": {"numericValue": 0},
                    "total-blocking-time": {"numericValue": 50},
                },
            }
            raw = owner.canonical(report)
            (lighthouse / f"{target}-{index}.json").write_bytes(raw)
            reports.append({"report_sha256": owner.sha(raw)})
        summary["results"].append(
            {
                "target": target,
                "passed": True,
                "sample_count": 3,
                "samples": [deepcopy(sample) for _ in range(3)],
                "medians": deepcopy(sample),
                "reports": reports,
            }
        )
    (lighthouse / "summary.json").write_bytes(owner.canonical(summary))
    return inputs, b"### Result\n" + owner.canonical(results), screenshots, summary


def test_report_is_derived_from_browser_screenshots_and_lighthouse_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, raw, screenshots, _summary = evidence(tmp_path, monkeypatch)
    report = owner.assemble_report(
        inputs=inputs,
        raw_result=raw,
        artifact_directory=screenshots,
        started_at="2026-09-05T02:00:00+00:00",
        captured_at="2026-09-05T02:05:00+00:00",
    )
    assert report["schema"] == "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V1"
    assert report["publication_authority"] is False
    assert len(report["core_document_slugs"]) == 14
    assert len(report["screenshots"]) == 130
    assert len(report["lighthouse_reports"]) == 6
    assert report["actionable_findings"] == 0
    assert report["browser_result_original_sha256"] == owner.sha(raw)
    assert "owner_approval" in report["not_verified_by_this_report"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_image",
        "unexpected_image",
        "not_png",
        "summary_false_median",
        "raw_metric_tamper",
        "summary_old_run",
        "theme_drift",
    ],
)
def test_report_replays_original_files_and_refuses_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    inputs, raw, screenshots, summary = evidence(tmp_path, monkeypatch)
    if mutation == "missing_image":
        next(screenshots.iterdir()).unlink()
    elif mutation == "unexpected_image":
        (screenshots / "unexpected.png").write_bytes(b"recorded fixture")
    elif mutation == "not_png":
        next(screenshots.iterdir()).write_bytes(b"not an image")
    elif mutation == "summary_false_median":
        summary["results"][0]["medians"]["lcp_ms"] = 1
    elif mutation == "raw_metric_tamper":
        path = owner.LIGHTHOUSE / "home-1.json"
        report = json.loads(path.read_bytes())
        report["audits"]["largest-contentful-paint"]["numericValue"] = 9000
        report_raw = owner.canonical(report)
        path.write_bytes(report_raw)
        summary["results"][0]["reports"][0]["report_sha256"] = owner.sha(report_raw)
    elif mutation == "summary_old_run":
        summary["started_at"] = "2026-09-04T02:03:00+00:00"
    else:
        summary["inputs"]["theme_runtime_revision"] = "d" * 64
    (owner.LIGHTHOUSE / "summary.json").write_bytes(owner.canonical(summary))
    with pytest.raises(owner.ReportFailure):
        owner.assemble_report(
            inputs=inputs,
            raw_result=raw,
            artifact_directory=screenshots,
            started_at="2026-09-05T02:00:00+00:00",
            captured_at="2026-09-05T02:05:00+00:00",
        )


def test_current_report_validator_does_not_accept_generic_pass_or_stale_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(owner, "REPORT", report_path)
    report_path.write_text('{"captured_at":"2026-09-04T00:00:00+00:00","passed":true}')
    with pytest.raises(owner.ReportFailure):
        owner.validate_report(
            report_path,
            fixture_root=tmp_path,
            origin="http://127.0.0.1:39330",
            now=datetime(2026, 9, 5, tzinfo=UTC),
        )
