from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/raos_v2/visual-validation.mjs"


def test_t_v2_051_visual_harness_covers_every_route_at_three_widths() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    browser_source = (ROOT / "tests/raos_v2/browser-validation.mjs").read_text(
        encoding="utf-8"
    )
    assert "ROUTES," in source
    for viewport in (
        "minimumHeight: 844, name: 'mobile-390', width: 390",
        "minimumHeight: 1024, name: 'tablet-768', width: 768",
        "minimumHeight: 900, name: 'desktop-1440', width: 1440",
    ):
        assert viewport in source
    assert "for (const route of ROUTES)" in source
    assert "for (const viewport of VISUAL_VIEWPORTS)" in source
    assert "VISUAL_CAPTURE_SET_INVALID" in source
    assert "VISUAL_CAPTURE_DIMENSIONS_INVALID" in source
    assert "PENDING_SEPARATE_MANUAL_REVIEW" in source
    assert "export const ROUTES" in browser_source


def test_t_v2_051_visual_receipt_is_local_bound_and_review_explicit() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    for contract in (
        "RAOS_V2_LOCAL_VISUAL_CAPTURE_RECEIPT_V1",
        "PLAYWRIGHT_CLI_FULL_PAGE_CAPTURE_HASH_BINDING_V1",
        "VISUAL_NODE_RUNTIME_MAJOR_INVALID",
        "output/playwright",
        "PUBLIC_CANDIDATE",
        "PLANNED_LOCKED",
        "FIXTURE_ONLY",
        "criticalFindings",
        "majorFindings",
        "MANUAL_REVIEW_REQUIRED_SEPARATE_RECORD",
        "previewSha256",
        "screenshotSha256",
        "externalActions: 'NOT_EXECUTED'",
    ):
        assert contract in source
    assert "reviewerClass" not in source
    assert "reviewedAt" not in source
    assert "HOME:" not in source
