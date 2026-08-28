from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/raos_v2/phase3-local-validation.mjs"


def _source() -> str:
    return HARNESS.read_text(encoding="utf-8")


def test_phase3_local_harness_is_one_route_and_assembly_scoped() -> None:
    source = _source()
    assert (
        "changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"
    ) in source
    assert "const TARGET_ROUTE = '/carry-on-suitcase-comparison/'" in source
    assert "LOCAL_WORDPRESS_ASSEMBLY_SIMULATION" in source
    assert "RAOS_V2_A05_POST_CONTENT_V1" in source
    assert "RAOS_V2_A05_ENVELOPE_V1" in source
    assert "result.envelopeCount !== 1" in source
    assert "!result.envelopeOnlyContainsMarker" in source
    assert "a.raos-v2-phase3-skip" in source
    assert "main#raos-v2-phase3-main" in source
    assert "h1.raos-v2-phase3-entry-title" in source
    assert "result.robots !== 'noindex,nofollow'" in source
    assert "changes/raos-v2/phase-2/preview" not in source
    assert "publicEvidence: 'NOT_CLAIMED'" in source
    assert "externalActions: 'NOT_EXECUTED'" in source


def test_phase3_local_harness_reuses_hash_bound_browser_and_axe_runtime() -> None:
    source = _source()
    for contract in (
        "from './browser-validation.mjs'",
        "SUPPORT_HARNESS_PATH",
        "supportHarness:",
        "const REQUIRED_NODE_MAJOR = 24",
        "const REQUIRED_AXE_VERSION = '4.12.1'",
        "require.resolve('axe-core/axe.min.js')",
        "PHASE3_AXE_DEPENDENCY_UNAVAILABLE",
        "PHASE3_AXE_DEPENDENCY_INVALID",
        "Accessibility.getFullAXTree",
        "wcag22aa",
    ):
        assert contract in source


def test_phase3_local_harness_covers_required_viewports_and_modes() -> None:
    source = _source()
    for contract in (
        "equivalentZoomPercent: 400",
        "height: 800, name: 'reflow-320', width: 320",
        "height: 844, name: 'mobile-390', width: 390",
        "height: 1024, name: 'tablet-768', width: 768",
        "height: 900, name: 'desktop-1440', width: 1440",
        "document.documentElement.style.fontSize = '200%'",
        "forced-colors",
        "prefers-reduced-motion",
        "PHASE3_ZOOM_200_PERCENT_INVALID",
        "PHASE3_FORCED_COLORS_REDUCED_MOTION_INVALID",
        "PHASE3_CSS_VIEWPORT_INVALID_",
        "PHASE3_KEYBOARD_SKIP_LINK_INVALID",
        "PHASE3_KEYBOARD_TRAVERSAL_INCOMPLETE",
        "Page.captureScreenshot",
        "carry-on-suitcase-comparison__${viewport.width}.png",
    ):
        assert contract in source


def test_phase3_local_harness_fails_closed_on_reader_and_resource_contracts() -> None:
    source = _source()
    for contract in (
        "result.h1Count !== 1",
        "result.blockedCtaCount !== 3",
        "result.blockedButtonCount !== 3",
        "result.imageCount !== 0",
        "result.inlineScriptCount !== 0",
        "result.resourceElementCount !== 0",
        "result.resourceEntryCount !== 0",
        "result.affiliateAnchorCount !== 0",
        "JSON.stringify(result.externalAnchorHrefs) !== JSON.stringify(OFFICIAL_SOURCE_URLS)",
        "result.documentHorizontalOverflow",
        "result.minimumBlockedButtonHeight < 44",
        "PHASE3_OUTBOUND_PAGE_REQUEST_PROHIBITED",
        "PHASE3_PAGE_RESOURCE_REQUEST_PROHIBITED",
        "PHASE3_BROWSER_PERSISTENCE_PROHIBITED",
    ):
        assert contract in source
    for boundary in (
        "document.cookie",
        "localStorage.length",
        "sessionStorage.length",
        "indexedDB.databases",
        "navigator.serviceWorker.getRegistrations",
    ):
        assert boundary in source


def test_phase3_local_receipt_is_sanitized_digest_only_and_argument_bound() -> None:
    source = _source()
    for contract in (
        "RAOS_V2_PHASE3_LOCAL_BROWSER_EVIDENCE_V1",
        "NODE24_LOCAL_CDP_AXE_PHASE3_WORDPRESS_ASSEMBLY_SANITIZED_RECEIPT_V1",
        "PASSED_LOCAL_ASSEMBLY_SIMULATION",
        "output/playwright",
        "PHASE3_OUTPUT_REQUIRED",
        "PHASE3_OUTPUT_PATH_INVALID",
        "sha256: sha256Bytes(preview.payload)",
        "harness:",
        "supportHarness:",
        "writeReceipt(argumentsValue.outputPath, receipt)",
        "visualCaptures: Object.freeze(visualCaptures)",
        "visualReview: 'PENDING_SEPARATE_MANUAL_REVIEW'",
        "PHASE3_SCREENSHOT_PNG_INVALID",
        "PHASE3_SCREENSHOT_DIMENSIONS_INVALID_",
        "information.isSymbolicLink()",
        "writeAtomic(path, payload)",
    ):
        assert contract in source
    for prohibited in (
        "outerHTML",
        "document.body.innerHTML",
        "networkUrls",
        "JSON.stringify(axe)",
        "JSON.stringify({ result",
    ):
        assert prohibited not in source


def test_phase3_local_errors_are_sanitized_and_classified() -> None:
    source = _source()
    for contract in (
        "function classifiedErrorCode(error)",
        "PHASE3_ASSEMBLED_PREVIEW_UNREADABLE",
        "PHASE3_BROWSER_VERSION_UNAVAILABLE",
        "PHASE3_SUPPORT_${candidate}",
        "PHASE3_RUNTIME_${candidate}",
        "PHASE3_LOCAL_VALIDATION_UNEXPECTED",
        "process.stderr.write(`${classifiedErrorCode(error)}\\n`)",
    ):
        assert contract in source
    assert "error.stack" not in source
    assert "error.message" not in source
    assert source.count("JSON.stringify(result.externalAnchorHrefs)") == 1
    for official_source in (
        "https://store.ace.jp/shop/g/g01471-02",
        "https://store.ace.jp/shop/g/g05721-04",
        "https://store.ace.jp/shop/g/g06316-01/",
    ):
        assert official_source in source
    assert source.count("process.stderr.write(") == 1


def test_phase3_local_receipt_captures_only_three_required_visual_widths() -> None:
    source = _source()
    assert "VIEWPORTS.filter((item) => item.width !== 320)" in source
    assert "visualCaptures.push(" in source
    for field in ("bytes", "height", "path", "sha256", "width"):
        assert f"{field}:" in source
