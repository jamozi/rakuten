#!/usr/bin/env python3
"""Bind completed browser/Lighthouse originals to the exact private mixed preview.

This report is local evidence, not an approval or an independent-audit signature.
The publication adapter must compare it with the validated manifest's byte hashes.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from incremental_scope import ROOT, ScopeFailure, load_scope, read_private

SCHEMA = "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V1"
BROWSER = ROOT / "changes/wordpress-local-preview-v1/browser"
INVENTORY = (
    ROOT / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
REPORT = ROOT / "output/playwright/local-preview.audit.v1.json"
ORIGINAL = ROOT / "output/playwright/local-preview.audit.cli.txt"
ARTIFACTS = ROOT / "output/playwright/local-preview"
LIGHTHOUSE = ROOT / "output/lighthouse/local-preview"
COUNT_FIELDS = frozenset(
    (
        "actionableAxeViolations",
        "brokenImages",
        "missingAlt",
        "unlabeledControls",
        "brokenAriaReferences",
        "horizontalOverflow",
        "browserCookies",
        "unhandledRuntimeErrors",
        "failedResources",
    )
)


class ReportFailure(ValueError):
    pass


def reject() -> None:
    raise ReportFailure("RAOS_WORDPRESS_MIXED_BROWSER_REPORT_INVALID")


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_regular(path: Path, maximum: int = 16 * 1024 * 1024) -> bytes:
    if not path.is_absolute() or path.resolve(strict=True) != path:
        reject()
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= maximum
    ):
        reject()
    raw = path.read_bytes()
    if len(raw) != metadata.st_size or path.stat().st_mtime_ns != metadata.st_mtime_ns:
        reject()
    return raw


def write_result(path: Path, raw: bytes) -> None:
    if path.exists() and path.is_symlink():
        reject()
    temporary = path.with_name(path.name + f".pending.{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def current_inputs(fixture_root: Path, origin: str) -> dict[str, object]:
    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{4,5}", origin):
        reject()
    inventory_raw = read_regular(INVENTORY)
    inventory = json.loads(inventory_raw)
    scope = load_scope(fixture_root, inventory)
    binding = json.loads(read_private(fixture_root / "preparation-binding.v1.json"))
    if binding.get("metadata_status") != "VERIFIED_FIELDS_ONLY" or binding.get(
        "metadata_blockers"
    ):
        reject()
    relative_theme = THEME.relative_to(ROOT).as_posix()
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", relative_theme],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    paths = [ROOT / item.decode() for item in tracked.split(b"\0") if item]
    if (
        not paths
        or len(paths) > 128
        or set(paths) != {path for path in THEME.rglob("*") if path.is_file()}
    ):
        reject()
    manifest = []
    for path in sorted(paths):
        raw = read_regular(path)
        manifest.append(
            {
                "path": path.relative_to(THEME).as_posix(),
                "size": len(raw),
                "sha256": sha(raw),
            }
        )
    theme_raw = read_regular(THEME / "theme-contract.v1.json")
    theme = json.loads(theme_raw)
    revision = theme.get("runtime_evidence", {}).get("revision")
    if not re.fullmatch(r"[a-f0-9]{64}", str(revision)) or revision != theme.get(
        "runtime_evidence", {}
    ).get("source_fingerprint"):
        reject()
    return {
        "origin": origin,
        "preparation_binding_sha256": scope["preparation_binding_sha256"],
        "scope": scope,
        "source_snapshot_sha256": binding["source_snapshot_sha256"],
        "article_body_sha256": binding["article_body_sha256"],
        "baseline_document_sha256": binding["baseline_document_sha256"],
        "page_body_sha256": binding["page_body_sha256"],
        "policy_states": binding["policy_states"],
        "home_state": binding["home_state"],
        "seed_metadata_sha256": binding["seed_metadata_sha256"],
        "audit_inventory_sha256": sha(inventory_raw),
        "audit_script_sha256": sha(
            read_regular(BROWSER / "wordpress_local_preview_audit.function.js")
        ),
        "runner_sha256": sha(read_regular(BROWSER / "check.sh")),
        "report_validator_sha256": sha(read_regular(Path(__file__).resolve())),
        "scope_loader_sha256": sha(read_regular(BROWSER / "incremental_scope.py")),
        "baseline_media_validator_sha256": sha(
            read_regular(ROOT / "scripts/raos_wordpress_baseline_media.py")
        ),
        "theme_contract_sha256": sha(theme_raw),
        "theme_tree_sha256": sha(canonical(manifest)),
        "theme_runtime_revision": revision,
        "theme_source_fingerprint": revision,
        "navigation_sha256": sha(
            read_regular(THEME / "assets/editorial-navigation.v3.json")
        ),
    }


def parse_results(raw: bytes) -> list[dict[str, object]]:
    text = raw.decode("utf-8", errors="strict")
    markers = list(re.finditer(r"(?m)^### Result\n", text))
    if len(markers) != 1 or re.search(r"(?m)^### Error\b", text):
        reject()
    result, end = json.JSONDecoder().raw_decode(text[markers[0].end() :].lstrip())
    remainder = text[markers[0].end() :].lstrip()[end:].strip()
    if remainder and not remainder.startswith("### Ran Playwright code\n"):
        reject()
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        reject()
    return result


def validate_results(
    results: list[dict[str, object]], inventory: dict, inputs: dict
) -> list[str]:
    surfaces = {
        row["surface_id"]: row
        for row in [*inventory["surfaces"], *inventory["local_surfaces"]]
    }
    widths = inventory["viewports"]
    expected = {(key, width) for key in surfaces for width in widths}
    if (
        len(surfaces) != 26
        or widths != [360, 390, 768, 1440]
        or len(results) != 104
        or {(row.get("surface"), row.get("width")) for row in results} != expected
    ):
        reject()
    screenshots: list[str] = []
    for row in results:
        surface = surfaces[row["surface"]]
        semantics = row.get("profileSemantics")
        counts = row.get("mandatoryCounts")
        if (
            row.get("auditResultSchema") != "RAOS_WORDPRESS_LOCAL_BROWSER_RESULT_V1"
            or row.get("localPath") != surface["local_path"]
            or row.get("productionPath") != surface.get("production_path")
            or row.get("httpStatus") != surface.get("expected_http_status", 200)
            or not isinstance(semantics, dict)
            or semantics.get("publicationProfile") != "verified-incremental"
            or semantics.get("linkMode") != "standard-api"
            or semantics.get("preparationBindingSha256")
            != inputs["preparation_binding_sha256"]
            or not isinstance(counts, dict)
            or set(counts) != COUNT_FIELDS
            or any(type(value) is not int or value != 0 for value in counts.values())
        ):
            reject()
        if surface.get("kind") == "article":
            article_id = surface["article_id"]
            selected = article_id in inputs["scope"]["selected_article_ids"]
            expected_article = next(
                (
                    item
                    for item in inputs["scope"]["articles"]
                    if item["article_id"] == article_id
                ),
                None,
            )
            if expected_article is None:
                reject()
            commerce_status = (
                "UNCHANGED_NOT_REVERIFIED"
                if not selected
                else (
                    "EXPECTED_VERIFIED_SET_PRESENT"
                    if expected_article["expected_ctas"]
                    else "NOT_INCLUDED"
                )
            )
            if semantics.get("incrementalCommerceStatus") != commerce_status:
                reject()
            if semantics.get("legacyMediaDisplayProjection") != expected_article.get(
                "display_projection"
            ):
                reject()
        name = f"local-preview-{row['surface']}-{row['width']}.png"
        if (
            not isinstance(row.get("screenshot"), str)
            or Path(row["screenshot"]).name != name
        ):
            reject()
        screenshots.append(name)
        if row["width"] == 390:
            zoom = f"local-preview-{row['surface']}-zoom200.png"
            if (
                not isinstance(row.get("zoomScreenshot"), str)
                or Path(row["zoomScreenshot"]).name != zoom
            ):
                reject()
            screenshots.append(zoom)
        elif row.get("zoomScreenshot") is not None:
            reject()
    if len(screenshots) != 130 or len(set(screenshots)) != 130:
        reject()
    return sorted(screenshots)


def assemble_report(
    *,
    inputs: dict,
    raw_result: bytes,
    artifact_directory: Path,
    started_at: str,
    captured_at: str,
) -> dict[str, object]:
    start, end = datetime.fromisoformat(started_at), datetime.fromisoformat(captured_at)
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or not start <= end <= start + timedelta(hours=2)
    ):
        reject()
    inventory = json.loads(read_regular(INVENTORY))
    results = parse_results(raw_result)
    names = validate_results(results, inventory, inputs)
    if set(names) != {path.name for path in artifact_directory.iterdir()}:
        reject()
    screenshots = {}
    for name in names:
        raw = read_regular(artifact_directory / name, 64 * 1024 * 1024)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            reject()
        screenshots[name] = sha(raw)
    lighthouse_raw = read_regular(LIGHTHOUSE / "summary.json")
    lighthouse = json.loads(lighthouse_raw)
    if (
        lighthouse.get("schema") != "RAOS_WORDPRESS_LIGHTHOUSE_MEDIAN_V2"
        or lighthouse.get("passed") is not True
        or lighthouse.get("sample_count") != 6
        or lighthouse.get("repetitions") != 3
        or not start
        <= datetime.fromisoformat(lighthouse["started_at"])
        <= datetime.fromisoformat(lighthouse["captured_at"])
        <= end
    ):
        reject()
    for key in (
        "audit_inventory_sha256",
        "audit_script_sha256",
        "theme_contract_sha256",
        "theme_runtime_revision",
        "theme_source_fingerprint",
        "navigation_sha256",
    ):
        if lighthouse.get("inputs", {}).get(key) != inputs[key]:
            reject()
    reports = {}
    if len(lighthouse.get("results", [])) != 2 or {
        row.get("target") for row in lighthouse.get("results", [])
    } != {
        "home",
        "article-a04",
    }:
        reject()
    for target in lighthouse["results"]:
        if (
            target.get("passed") is not True
            or target.get("sample_count") != 3
            or len(target.get("reports", [])) != 3
            or any(
                target["medians"].get(key, float("inf")) > limit
                for key, limit in {"lcp_ms": 2500, "cls": 0.1, "tbt_ms": 200}.items()
            )
        ):
            reject()
        samples = []
        for index, report in enumerate(target["reports"], start=1):
            name = f"{target['target']}-{index}.json"
            raw = read_regular(LIGHTHOUSE / name, 50 * 1024 * 1024)
            if sha(raw) != report.get("report_sha256"):
                reject()
            document = json.loads(raw)
            expected_url = inputs["origin"] + (
                "/"
                if target["target"] == "home"
                else "/local-preview-countertop-dishwasher-for-small-households/"
            )
            if (
                document.get("lighthouseVersion") != "12.8.2"
                or document.get("requestedUrl") != expected_url
                or document.get("finalDisplayedUrl") != expected_url
                or document.get("runtimeError")
                or not start <= datetime.fromisoformat(document["fetchTime"]) <= end
            ):
                reject()
            sample = {}
            for key, audit_id in {
                "lcp_ms": "largest-contentful-paint",
                "cls": "cumulative-layout-shift",
                "tbt_ms": "total-blocking-time",
            }.items():
                value = document.get("audits", {}).get(audit_id, {}).get("numericValue")
                if (
                    type(value) not in {int, float}
                    or not math.isfinite(value)
                    or value < 0
                ):
                    reject()
                sample[key] = value
            samples.append(sample)
            reports[name] = sha(raw)
        medians = {
            key: sorted(sample[key] for sample in samples)[1]
            for key in ("lcp_ms", "cls", "tbt_ms")
        }
        if samples != target.get("samples") or medians != target.get("medians"):
            reject()
    return {
        "schema": SCHEMA,
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "status": "LOCAL_MIXED_BROWSER_AUDIT_PASSED",
        "publication_authority": False,
        "started_at": started_at,
        "captured_at": captured_at,
        "inputs": inputs,
        "core_document_slugs": sorted(
            "home" if row["kind"] == "home" else row["production_path"].strip("/")
            for row in inventory["surfaces"]
        ),
        "viewports": inventory["viewports"],
        "zoom_percent": 200,
        "browser_result_count": len(results),
        "actionable_findings": 0,
        "browser_result_original_sha256": sha(raw_result),
        "browser_results": results,
        "screenshots": screenshots,
        "lighthouse_summary_sha256": sha(lighthouse_raw),
        "lighthouse_reports": reports,
        "not_verified_by_this_report": [
            "independent_codex_audits",
            "real_reader_tests",
            "owner_approval",
            "production_readback",
        ],
    }


def validate_report(
    report_path: Path, *, fixture_root: Path, origin: str, now: datetime | None = None
) -> dict[str, object]:
    """Replay originals and current inputs; return a report only after exact equality."""
    if report_path != REPORT:
        reject()
    report = json.loads(read_regular(report_path))
    captured = datetime.fromisoformat(report["captured_at"])
    now = now or datetime.now(UTC)
    if now.tzinfo is None or not captured <= now <= captured + timedelta(hours=2):
        reject()
    inputs = current_inputs(fixture_root, origin)
    if inputs != report.get("inputs"):
        reject()
    expected = assemble_report(
        inputs=inputs,
        raw_result=read_regular(ORIGINAL),
        artifact_directory=ARTIFACTS,
        started_at=report["started_at"],
        captured_at=report["captured_at"],
    )
    if report != expected:
        reject()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("action", choices=("begin", "finish", "verify"))
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--binding-file", type=Path)
    parser.add_argument("--raw-result", type=Path)
    parser.add_argument("--artifact-directory", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.action == "verify":
            report = validate_report(
                REPORT, fixture_root=arguments.fixture_root, origin=arguments.origin
            )
            print(f"Mixed browser report verified: {sha(canonical(report))}")
            return 0
        if arguments.binding_file is None:
            reject()
        inputs = current_inputs(arguments.fixture_root, arguments.origin)
        if arguments.action == "begin":
            started = datetime.now(UTC).isoformat()
            write_result(
                arguments.binding_file,
                canonical({"inputs": inputs, "started_at": started}),
            )
            write_result(
                REPORT,
                canonical(
                    {
                        "schema": SCHEMA,
                        "status": "RUNNING_NOT_VERIFIED",
                        "started_at": started,
                    }
                ),
            )
            return 0
        binding = json.loads(read_regular(arguments.binding_file))
        if (
            binding.get("inputs") != inputs
            or arguments.raw_result is None
            or arguments.artifact_directory is None
        ):
            reject()
        raw = read_regular(arguments.raw_result)
        report = assemble_report(
            inputs=inputs,
            raw_result=raw,
            artifact_directory=arguments.artifact_directory,
            started_at=binding["started_at"],
            captured_at=datetime.now(UTC).isoformat(),
        )
        write_result(ORIGINAL, raw)
        write_result(REPORT, canonical(report))
        print(f"Mixed browser report: {REPORT}")
        return 0
    except (
        ReportFailure,
        ScopeFailure,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ):
        sys.stderr.write("RAOS_WORDPRESS_MIXED_BROWSER_REPORT_INVALID\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
