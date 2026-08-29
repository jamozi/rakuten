from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/raos_v2/browser-validation.mjs"
NODE_EXECUTABLE = os.environ.get("NODE") or shutil.which("node") or "node"


def test_t_v2_023_browser_harness_denies_network_and_persistence() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    assert "OUTBOUND_PAGE_REQUEST_PROHIBITED" in source
    assert "BROWSER_PERSISTENCE_PROHIBITED" in source
    assert "Network.requestWillBeSent" in source
    for boundary in (
        "document.cookie",
        "localStorage.length",
        "sessionStorage.length",
        "indexedDB.databases",
        "navigator.serviceWorker.getRegistrations",
    ):
        assert boundary in source
    assert "LOOPBACK = '127.0.0.1'" in source
    assert "redirect: 'error'" in source
    assert "HOME:" not in source


def test_t_v2_023_wait_for_debugger_clears_rejected_fetch_timer() -> None:
    port = 32123
    websocket_url = f"ws://127.0.0.1:{port}/devtools/page/test"
    script = (
        f"import {{ waitForDebugger }} from {json.dumps(HARNESS.as_uri())};"
        "let attempts = 0;"
        f"const expectedUrl = 'http://127.0.0.1:{port}/json/list';"
        "globalThis.fetch = async (url, options) => {"
        "attempts += 1;"
        "if (url !== expectedUrl || options?.method !== 'GET' || "
        "options?.redirect !== 'error') throw new Error('REQUEST_CONTRACT_DRIFT');"
        "if (attempts === 1) throw new Error('EXPECTED_STARTUP_REFUSAL');"
        "return { ok: true, json: async () => [{"
        "type: 'page',"
        f"webSocketDebuggerUrl: {json.dumps(websocket_url)}"
        "}] };"
        "};"
        f"const observed = await waitForDebugger({port});"
        f"if (observed !== {json.dumps(websocket_url)} || attempts !== 2) "
        "throw new Error('DEBUGGER_RETRY_INVALID');"
    )
    completed = subprocess.run(
        [NODE_EXECUTABLE, "--input-type=module", "--eval", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 0, completed.stderr


def test_t_v2_033_browser_matrix_has_required_viewports_and_modes() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    for contract in (
        "height: 800,",
        "name: 'reflow-320-equivalent-400pct'",
        "width: 320",
        "height: 844, name: 'mobile-390', width: 390",
        "height: 800, name: 'mobile-360', width: 360",
        "height: 1024, name: 'tablet-768', width: 768",
        "height: 900, name: 'desktop-1440', width: 1440",
        "wcag22aa",
        "forced-colors",
        "prefers-reduced-motion",
        "fontSize = '200%'",
        "KEYBOARD_SKIP_LINK_NOT_FIRST",
        "ROUTE_VIEWPORT_SEMANTICS_INVALID",
        "viewportAudits[viewport.name]",
        "axeRuns: ROUTES.length",
        "focusTraversalAllRoutes: true",
        "skipLinkAllRoutes: true",
        "KEYBOARD_FOCUS_PATH_INCOMPLETE",
        "KEYBOARD_EMPTY_SUBMIT_INVALID",
        "KEYBOARD_PASS_SUBMIT_INVALID",
        "KEYBOARD_RESET_INVALID",
        "Accessibility.getFullAXTree",
        "screenReaderSmokeAllRoutes: true",
        "Emulation.setScriptExecutionDisabled",
        "JAVASCRIPT_DISABLED_FALLBACK_INVALID",
        "equivalentZoomPercent: 400",
        "PAGE_TRANSFER_CEILING_EXCEEDED",
        "homeToolCeilingBytes: 800 * 1024",
        "articleCeilingBytes: 1_200 * 1024",
    ):
        assert contract in source


def test_t_v2_033_browser_harness_enforces_and_records_node24_runtime() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    for contract in (
        "const REQUIRED_NODE_MAJOR = 24",
        "process.versions.node",
        "NODE_RUNTIME_MAJOR_INVALID",
        "executableSha256: await sha256File(realpathSync(process.execPath))",
        "nodeMajor: REQUIRED_NODE_MAJOR",
        "nodeVersion: process.versions.node",
    ):
        assert contract in source


def test_t_v2_020_021_checker_browser_matrix_proves_segment_intersection() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    assert "allSegmentIntersection: true" in source
    assert "'carrier-2': 'PEACH'" in source
    assert "'journey-scope-2': 'DOMESTIC'" in source
    assert "anaUnknownScope !== 'UNKNOWN'" in source
    assert "anaInternationalNoMatch !== 'NO_MATCH'" in source
    assert "peachInternationalPass !== 'PASS'" in source
    assert "unknownDominatesNoMatch !== 'UNKNOWN'" in source
    assert "pass !== 'PASS'" in source
    assert "failState !== 'FAIL'" in source
    assert "countFail !== 'FAIL'" in source
    assert "underseatUnknown !== 'UNKNOWN'" in source
    assert "reviewDeadlineStale !== 'STALE'" in source
    assert "beforeObservedBoundaryUnknown !== 'UNKNOWN'" in source
    assert "unknown !== 'UNKNOWN'" in source


def test_t_v2_051_evidence_is_digest_only_and_local() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    assert "RAOS_V2_LOCAL_BROWSER_EVIDENCE_V1" in source
    assert "classification: 'PASSED_LOCAL'" in source
    assert "commandContract: COMMAND_CONTRACT" in source
    assert "exitStatus: 0" in source
    assert "externalActions: 'NOT_EXECUTED'" in source
    assert "harnessSha256: await sha256File(SCRIPT_PATH)" in source
    assert "previewDigests" in source
    assert "output/playwright" in source
    for prohibited in ("screenshot", "outerHTML", "document.body.innerHTML"):
        assert prohibited not in source
