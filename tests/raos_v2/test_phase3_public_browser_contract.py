from __future__ import annotations

import json
import shutil
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/raos_v2/phase3-public-validation.mjs"
ADVERSARIAL_HARNESS = ROOT / "tests/raos_v2/phase3-public-adversarial.mjs"


def _source() -> str:
    return HARNESS.read_text(encoding="utf-8")


def test_phase3_public_harness_is_fixed_to_one_public_read_only_target() -> None:
    source = _source()
    assert "const TARGET_ORIGIN = 'https://kurashinoshirube.com'" in source
    assert "const TARGET_ROUTE = '/carry-on-suitcase-comparison/'" in source
    assert "const TARGET_URL = `${TARGET_ORIGIN}${TARGET_ROUTE}`" in source
    assert "from './browser-validation.mjs'" in source
    assert "--target" not in source
    assert "--url" not in source
    assert "Page.addScriptToEvaluateOnNewDocument" in source
    assert "Fetch.requestPaused" in source
    assert "Fetch.failRequest" in source
    assert "method !== 'GET' && method !== 'HEAD'" in source
    assert "origin !== TARGET_ORIGIN" in source
    assert "? 'CROSS_ORIGIN'" in source
    assert "launchSandboxedBrowser" in source
    assert "await stopBrowserProcess(browser)" in source
    assert "--no-sandbox" not in source
    assert "Target.setAutoAttach" in source
    assert "waitForDebuggerOnStart: true" in source
    assert "unexpectedAttachedTargets" in source


def test_phase3_public_harness_fails_closed_without_exact_v2_marker() -> None:
    source = _source()
    for contract in (
        "RAOS_V2_A05_POST_CONTENT_V1",
        "RAOS_V2_A05_ENVELOPE_V1",
        "PHASE3_PUBLIC_V2_MARKER_MISSING_OR_AMBIGUOUS",
        "result.markerCount !== 1",
        "result.affiliateAnchorCount !== 0",
        "result.envelopeCount !== 1",
        "!result.envelopeContainsMarker",
        "result.ctaStateCount !== 3",
        "result.blockedCtaCount !== 3",
        "result.visibleBlockedCtaCount !== 3",
        "!result.disclosureComputedVisible",
        "result.documentHorizontalOverflow",
    ):
        assert contract in source


def test_phase3_public_harness_covers_visual_keyboard_zoom_and_axe_contracts() -> None:
    source = _source()
    for contract in (
        "height: 844, name: 'mobile-390', width: 390",
        "height: 1024, name: 'tablet-768', width: 768",
        "height: 900, name: 'desktop-1440', width: 1440",
        "const REQUIRED_AXE_VERSION = '4.12.1'",
        "require.resolve('axe-core/axe.min.js')",
        "'wcag21a','wcag21aa','wcag22aa'",
        "Input.dispatchKeyEvent",
        "PHASE3_PUBLIC_KEYBOARD_TRAVERSAL_INCOMPLETE_",
        "root.style.setProperty('font-size', '200%', 'important')",
        "PHASE3_PUBLIC_ZOOM_200_PERCENT_INVALID_",
        "Page.captureScreenshot",
        "carry-on-suitcase-comparison__${viewport.width}.png",
    ):
        assert contract in source


def test_phase3_public_harness_prevents_writes_navigation_and_persistence() -> None:
    source = _source()
    for contract in (
        "formSubmissionAttempts",
        "HTMLFormElement.prototype",
        "event.preventDefault()",
        "affiliateNavigationAttempts",
        "cookieMutationAttempts",
        "CookieStore",
        "cookieStoreMutationAttempts",
        "localStorageMutationAttempts",
        "sessionStorageMutationAttempts",
        "indexedDbMutationAttempts",
        "serviceWorkerRegistrationAttempts",
        "streamingChannelAttempts",
        "workerConstructionAttempts",
        "['Worker', 'SharedWorker']",
        "nonHttpChannelAttempts",
        "BlockedWebTransport",
        "BlockedWebSocketStream",
        "['RTCPeerConnection', 'webkitRTCPeerConnection']",
        "navigator.serviceWorker.getRegistrations",
        "globalThis.caches ? caches.keys()",
        "StorageManager.prototype.getDirectory",
        "cacheStorageMutationAttempts",
        "opfsMutationAttempts",
        "StorageBucketManager",
        "storageBucketMutationAttempts",
        "navigator.storageBuckets.keys()",
        "sharedStorageMutationAttempts",
        "globalThis.sharedStorage",
        "storage.worklet",
        "createWorklet",
        "protectedAudienceMutationAttempts",
        "joinAdInterestGroup",
        "leaveAdInterestGroup",
        "clearOriginJoinedAdInterestGroups",
        "updateAdInterestGroups",
        "indexedDB.databases",
        "Network.getAllCookies",
        "PHASE3_PUBLIC_BROWSER_PERSISTENCE_CHANGED",
        "DOMStorage.enable",
        "DOMStorage.domStorageItemAdded",
        "PHASE3_PUBLIC_DOM_STORAGE_MUTATION_DETECTED",
        "Network.responseReceivedExtraInfo",
        "browserStateMutationHeaderNames",
        "attribution-reporting-register-source",
        "attribution-reporting-register-trigger",
        "clear-site-data",
        "observe-browsing-topics",
        "PHASE3_PUBLIC_RESPONSE_STATE_MUTATION_DETECTED",
        "PHASE3_PUBLIC_BROWSER_COOKIE_STORE_CHANGED",
        "PHASE3_PUBLIC_NETWORK_READ_ONLY_CONTRACT_INVALID",
        "Network.loadingFailed",
        "resourceFailureCount",
        "Page.windowOpen",
        "PHASE3_PUBLIC_FINAL_DOCUMENT_SCOPE_INVALID",
        "finalDocumentRows.length !== 1",
        "Network.webSocketCreated",
        "Network.webTransportCreated",
        "MAX_NETWORK_REQUESTS = 80",
        "PHASE3_PUBLIC_REQUEST_LIMIT_EXCEEDED",
        "PHASE3_PUBLIC_NON_HTTP_TRANSPORT_DETECTED",
        "Object.freeze({ ...state })",
        "Emulation.setVirtualTimePolicy",
        "Runtime.terminateExecution",
        "Target.closeTarget",
        "PHASE3_PUBLIC_TERMINAL_BOUNDARY_DRIFT",
    ):
        assert contract in source
    for prohibited in (
        "Input.insertText",
        "Input.dispatchMouseEvent",
        "Runtime.callFunctionOn",
        "document.querySelector('form').submit",
    ):
        assert prohibited not in source


def test_phase3_public_raw_receipt_is_owner_held_sanitized_and_non_authoritative() -> (
    None
):
    source = _source()
    for contract in (
        "RAOS_V2_PHASE3_PUBLIC_BROWSER_RAW_RECEIPT_V1",
        "OWNER_HELD_RAW_PUBLIC_BROWSER_EVIDENCE",
        "RECORDED_PUBLIC_READ_ONLY",
        "acceptanceAuthority: false",
        "phaseExitEligible: false",
        "independentRecalculationStatus: 'PENDING'",
        "OWNER_CONTROLLED_OUTPUT_PLAYWRIGHT_NOT_GIT",
        "output/playwright",
        "resourceManifestSha256",
        "resourceManifest,",
        "decodedPublicBodySha256",
        "screenshotPath:",
        "screenshotSha256:",
        "commitEvidence(argumentsValue, temporaryCapturesDirectory, receipt)",
        "PHASE3_PUBLIC_OUTPUT_ALREADY_EXISTS",
    ):
        assert contract in source
    for prohibited in (
        "document.body.innerHTML",
        "JSON.stringify(networkRows)",
        "error.stack",
        "error.message",
        "PUBLISHED",
        "acceptanceAuthority: true",
        "phaseExitEligible: true",
    ):
        assert prohibited not in source


def test_phase3_public_harness_has_valid_node_syntax() -> None:
    completed = subprocess.run(
        ["node", "--check", str(HARNESS)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_phase3_public_response_header_guard_rejects_browser_state_registrations() -> (
    None
):
    script = (
        f"import {{ browserStateMutationHeaderNames }} from {json.dumps(HARNESS.as_uri())};"
        "const observed = browserStateMutationHeaderNames({"
        "'Set-Cookie': 'x=1',"
        "'Attribution-Reporting-Register-Source': '{}',"
        "'ATtribution-Reporting-Register-Trigger': '{}',"
        "'Clear-Site-Data': '\"storage\"',"
        "'Observe-Browsing-Topics': '?1',"
        "'Reporting-Endpoints': 'default=\"https://example.invalid/report\"',"
        "'Content-Type': 'text/html'"
        "});"
        "process.stdout.write(JSON.stringify(observed));"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == [
        "attribution-reporting-register-source",
        "attribution-reporting-register-trigger",
        "clear-site-data",
        "observe-browsing-topics",
        "reporting-endpoints",
        "set-cookie",
    ]


def test_phase3_public_browser_runtime_argv_keeps_chromium_sandbox(
    tmp_path: Path,
) -> None:
    argv_receipt = tmp_path / "browser-argv.txt"
    fake_browser = tmp_path / "fake-browser"
    fake_browser.write_text(
        "#!/bin/sh\n" f"printf '%s\\n' \"$@\" > {shlex.quote(str(argv_receipt))}\n",
        encoding="utf-8",
    )
    fake_browser.chmod(0o700)
    profile = tmp_path / "profile"
    profile.mkdir()
    script = (
        f"import {{ launchSandboxedBrowser }} from {json.dumps(HARNESS.as_uri())};"
        f"const browser = await launchSandboxedBrowser({json.dumps(str(fake_browser))}, 32123, "
        f"{json.dumps(str(profile))});"
        "await new Promise((resolvePromise, rejectPromise) => {"
        "browser.child.once('error', rejectPromise);"
        "browser.child.once('exit', resolvePromise);"
        "});"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    arguments = argv_receipt.read_text(encoding="utf-8").splitlines()
    assert "--no-sandbox" not in arguments
    assert "--remote-debugging-address=127.0.0.1" in arguments
    assert "--headless=new" in arguments


def test_phase3_public_receipt_commit_does_not_replace_competing_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "receipt.json"
    captures = tmp_path / "receipt-captures"
    temporary_captures = tmp_path / "temporary-captures"
    temporary_captures.mkdir()
    (temporary_captures / "capture.png").write_bytes(b"owner-capture")
    output.write_text("competing-owner-receipt\n", encoding="utf-8")
    script = (
        f"import {{ commitEvidence }} from {json.dumps(HARNESS.as_uri())};"
        "try {"
        f"commitEvidence({{ outputPath: {json.dumps(str(output))}, "
        f"capturesDirectory: {json.dumps(str(captures))} }}, "
        f"{json.dumps(str(temporary_captures))}, {{ schema: 'TEST' }});"
        "process.exitCode = 2;"
        "} catch (error) {"
        "process.stdout.write(`${error.code ?? 'UNKNOWN'}\\n`);"
        "}"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "PHASE3_PUBLIC_OUTPUT_ALREADY_EXISTS"
    assert output.read_text(encoding="utf-8") == "competing-owner-receipt\n"
    assert not captures.exists()


def test_phase3_public_harness_blocks_adversarial_runtime_channels() -> None:
    completed = subprocess.run(
        ["node", str(ADVERSARIAL_HARNESS)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "RAOS_V2_PHASE3_PUBLIC_ADVERSARIAL_RUNTIME_PASSED" in completed.stdout


def test_phase3_public_harness_blocks_real_chromium_persistence_cycles() -> None:
    browser = shutil.which("google-chrome") or shutil.which("chromium")
    if browser is None:
        raise AssertionError("REAL_CHROMIUM_REQUIRED_FOR_PHASE3_PUBLIC_GUARD")
    completed = subprocess.run(
        ["node", str(ADVERSARIAL_HARNESS), "--browser-executable", browser],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "RAOS_V2_PHASE3_PUBLIC_ADVERSARIAL_RUNTIME_PASSED" in completed.stdout
