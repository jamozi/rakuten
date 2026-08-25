import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import {
  chmodSync,
  closeSync,
  createReadStream,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const ROOT = realpathSync(resolve(dirname(SCRIPT_PATH), '..'));
const CONTRACT_PATH = join(
  ROOT,
  'changes/st-1007/contracts/public-accessibility-local-browser.v2.json',
);
const MAX_TEXT_BYTES = 4 * 1024 * 1024;
const MAX_PROCESS_OUTPUT_BYTES = 4 * 1024 * 1024;
const PROCESS_TIMEOUT_MS = 120_000;
const SERVER_TIMEOUT_MS = 20_000;
const BROWSER_TIMEOUT_MS = 15_000;
const PAGE_TIMEOUT_MS = 15_000;
const LOOPBACK_HOST = '127.0.0.1';

class ClosedFailure extends Error {
  constructor(code) {
    super(code);
    this.name = 'ClosedFailure';
    this.code = code;
  }
}

function fail(code) {
  throw new ClosedFailure(code);
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

function parseArguments(argv) {
  let mode = null;
  let browserExecutable = null;

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--write' || argument === '--check') {
      if (mode !== null) fail('ARGUMENT_MODE_INVALID');
      mode = argument.slice(2);
      continue;
    }
    if (argument === '--browser-executable') {
      if (browserExecutable !== null || index + 1 >= argv.length) {
        fail('ARGUMENT_BROWSER_INVALID');
      }
      browserExecutable = argv[index + 1];
      index += 1;
      continue;
    }
    fail('ARGUMENT_UNKNOWN');
  }

  if (mode === null) fail('ARGUMENT_MODE_REQUIRED');
  if (browserExecutable === null || !isAbsolute(browserExecutable)) {
    fail('ARGUMENT_BROWSER_REQUIRED');
  }
  return Object.freeze({ browserExecutable, mode });
}

function readBounded(path) {
  const info = lstatSync(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_TEXT_BYTES) {
    fail('SOURCE_FILE_INVALID');
  }
  return readFileSync(path);
}

function sha256Bytes(value) {
  return createHash('sha256').update(value).digest('hex');
}

async function sha256File(path) {
  const hash = createHash('sha256');
  await new Promise((resolvePromise, rejectPromise) => {
    const stream = createReadStream(path);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.once('error', rejectPromise);
    stream.once('end', resolvePromise);
  });
  return hash.digest('hex');
}

function parseJsonObject(bytes, failureCode) {
  let parsed;
  try {
    parsed = JSON.parse(bytes.toString('utf8'));
  } catch {
    fail(failureCode);
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    fail(failureCode);
  }
  return parsed;
}

function requireExactKeys(value, expected, failureCode) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) fail(failureCode);
}

function requireString(value, failureCode) {
  if (typeof value !== 'string' || value.length === 0) fail(failureCode);
  return value;
}

function requireInteger(value, failureCode) {
  if (!Number.isSafeInteger(value)) fail(failureCode);
  return value;
}

function requireArray(value, failureCode) {
  if (!Array.isArray(value)) fail(failureCode);
  return value;
}

function requireMapping(value, failureCode) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail(failureCode);
  return value;
}

function loadContract() {
  const contract = parseJsonObject(readBounded(CONTRACT_PATH), 'CONTRACT_INVALID');
  requireExactKeys(
    contract,
    [
      'authority',
      'classification',
      'formal_boundary',
      'local_checks',
      'observed_routes',
      'output_path',
      'runtime',
      'schema_version',
      'source_paths',
      'story_id',
      'unavailable_canonical_screens',
      'viewport_profiles',
    ],
    'CONTRACT_SHAPE_INVALID',
  );
  if (
    contract.schema_version !== 2 ||
    contract.story_id !== 'ST-1007' ||
    contract.classification !== 'LOCAL_BROWSER_AUTOMATED_ACCESSIBILITY_EVIDENCE_NON_FORMAL_V2'
  ) {
    fail('CONTRACT_IDENTITY_INVALID');
  }
  const runtime = requireMapping(contract.runtime, 'CONTRACT_RUNTIME_INVALID');
  const browser = requireMapping(runtime.browser, 'CONTRACT_BROWSER_INVALID');
  const axe = requireMapping(runtime.axe, 'CONTRACT_AXE_INVALID');
  if (
    browser.product !== 'Chrome for Testing' ||
    typeof browser.version !== 'string' ||
    !/^[0-9]+(?:\.[0-9]+){3}$/u.test(browser.version) ||
    typeof browser.executable_sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/u.test(browser.executable_sha256) ||
    axe.version !== '4.12.1' ||
    typeof axe.script_sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/u.test(axe.script_sha256)
  ) {
    fail('CONTRACT_TOOLCHAIN_INVALID');
  }
  return contract;
}

function ensureRepositoryRoot() {
  if (realpathSync(process.cwd()) !== ROOT) fail('WORKSPACE_ROOT_INVALID');
}

function resolveOwnedPath(relativePath) {
  if (
    typeof relativePath !== 'string' ||
    relativePath.length === 0 ||
    relativePath.startsWith('/') ||
    relativePath.includes('\0')
  ) {
    fail('SOURCE_PATH_INVALID');
  }
  const absolute = resolve(ROOT, relativePath);
  const fromRoot = relative(ROOT, absolute);
  if (fromRoot === '..' || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    fail('SOURCE_PATH_INVALID');
  }
  return absolute;
}

async function buildSourceArtifacts(contract) {
  const sourcePaths = requireArray(contract.source_paths, 'CONTRACT_SOURCE_PATHS_INVALID');
  if (new Set(sourcePaths).size !== sourcePaths.length) {
    fail('CONTRACT_SOURCE_PATHS_INVALID');
  }
  const artifacts = [];
  for (const relativePath of sourcePaths) {
    const path = resolveOwnedPath(relativePath);
    const info = lstatSync(path);
    if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_TEXT_BYTES) {
      fail('SOURCE_FILE_INVALID');
    }
    artifacts.push({
      bytes: info.size,
      path: relativePath,
      sha256: await sha256File(path),
    });
  }
  return artifacts;
}

async function verifyBrowserExecutable(path, contract) {
  const info = lstatSync(path);
  if (!info.isFile() || info.isSymbolicLink() || (info.mode & 0o111) === 0) {
    fail('BROWSER_EXECUTABLE_INVALID');
  }
  const browserContract = contract.runtime.browser;
  if ((await sha256File(path)) !== browserContract.executable_sha256) {
    fail('BROWSER_EXECUTABLE_HASH_DRIFT');
  }
}

function closedEnvironment(extra = {}) {
  return {
    HOME: tmpdir(),
    LANG: 'C.UTF-8',
    LC_ALL: 'C.UTF-8',
    NODE_ENV: 'production',
    PATH: `${dirname(process.execPath)}:/usr/bin:/bin`,
    ...extra,
  };
}

async function waitForExit(child, timeoutMilliseconds, timeoutCode) {
  let timer;
  const result = await Promise.race([
    new Promise((resolvePromise) => {
      child.once('exit', (code, signal) => resolvePromise({ code, signal }));
    }),
    new Promise((resolvePromise) => {
      timer = setTimeout(() => resolvePromise(null), timeoutMilliseconds);
    }),
  ]);
  clearTimeout(timer);
  if (result === null) {
    child.kill('SIGTERM');
    await sleep(500);
    if (child.exitCode === null) child.kill('SIGKILL');
    fail(timeoutCode);
  }
  return result;
}

function captureProcessOutput(child) {
  let stdout = '';
  let stderr = '';
  let overflow = false;
  child.stdout?.setEncoding('utf8');
  child.stderr?.setEncoding('utf8');
  child.stdout?.on('data', (chunk) => {
    if (stdout.length + chunk.length > MAX_PROCESS_OUTPUT_BYTES) overflow = true;
    else stdout += chunk;
  });
  child.stderr?.on('data', (chunk) => {
    if (stderr.length + chunk.length > MAX_PROCESS_OUTPUT_BYTES) overflow = true;
    else stderr += chunk;
  });
  return Object.freeze({
    get overflow() {
      return overflow;
    },
    get stderr() {
      return stderr;
    },
    get stdout() {
      return stdout;
    },
  });
}

async function runBuild(contract) {
  const packageJson = parseJsonObject(
    readBounded(join(ROOT, 'apps/web/package.json')),
    'WEB_PACKAGE_INVALID',
  );
  const dependencies = requireMapping(packageJson.dependencies, 'WEB_PACKAGE_INVALID');
  if (dependencies.next !== contract.runtime.next_version) fail('NEXT_VERSION_DRIFT');
  const nextBinary = join(ROOT, 'node_modules/next/dist/bin/next');
  if (!lstatSync(nextBinary).isFile()) fail('NEXT_BINARY_INVALID');
  const child = spawn(process.execPath, [nextBinary, 'build', '--webpack'], {
    cwd: join(ROOT, 'apps/web'),
    env: closedEnvironment(),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const output = captureProcessOutput(child);
  const result = await waitForExit(child, PROCESS_TIMEOUT_MS, 'NEXT_BUILD_TIMEOUT');
  if (output.overflow || result.code !== 0 || result.signal !== null) fail('NEXT_BUILD_FAILED');
}

async function reserveLoopbackPort() {
  const server = createServer();
  server.unref();
  await new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, LOOPBACK_HOST, resolvePromise);
  });
  const address = server.address();
  if (address === null || typeof address === 'string') fail('LOOPBACK_PORT_INVALID');
  const port = address.port;
  await new Promise((resolvePromise, rejectPromise) => {
    server.close((error) => (error ? rejectPromise(error) : resolvePromise()));
  });
  return port;
}

async function startNextServer(port) {
  const nextBinary = join(ROOT, 'node_modules/next/dist/bin/next');
  const child = spawn(
    process.execPath,
    [nextBinary, 'start', '--hostname', LOOPBACK_HOST, '--port', String(port)],
    {
      cwd: join(ROOT, 'apps/web'),
      env: closedEnvironment(),
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  const output = captureProcessOutput(child);
  try {
    const deadline = Date.now() + SERVER_TIMEOUT_MS;
    while (Date.now() < deadline) {
      if (child.exitCode !== null || output.overflow) fail('NEXT_SERVER_FAILED');
      try {
        const response = await fetch(`http://${LOOPBACK_HOST}:${String(port)}/editorial-policy`, {
          redirect: 'manual',
          signal: AbortSignal.timeout(500),
        });
        if (response.status === 200) return { child, output };
      } catch {
        // The loopback listener is expected to be unavailable during startup.
      }
      await sleep(50);
    }
    fail('NEXT_SERVER_TIMEOUT');
  } catch (error) {
    await stopChild(child, 'NEXT_SERVER_STOP_FAILED');
    throw error;
  }
}

async function stopChild(child, timeoutCode) {
  if (child.exitCode !== null) return;
  child.kill('SIGTERM');
  const deadline = Date.now() + 3_000;
  while (child.exitCode === null && Date.now() < deadline) await sleep(25);
  if (child.exitCode === null) {
    child.kill('SIGKILL');
    const deadlineKill = Date.now() + 2_000;
    while (child.exitCode === null && Date.now() < deadlineKill) await sleep(25);
  }
  if (child.exitCode === null) fail(timeoutCode);
}

async function waitForDevTools(child, output) {
  const deadline = Date.now() + BROWSER_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || output.overflow) fail('BROWSER_START_FAILED');
    const match = output.stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/u);
    if (match) return match[1];
    await sleep(25);
  }
  fail('BROWSER_START_TIMEOUT');
}

class CdpConnection {
  constructor(url) {
    this.url = url;
    this.sequence = 0;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket = null;
  }

  async open() {
    const socket = new WebSocket(this.url);
    this.socket = socket;
    await new Promise((resolvePromise, rejectPromise) => {
      socket.addEventListener('open', resolvePromise, { once: true });
      socket.addEventListener('error', rejectPromise, { once: true });
    });
    socket.addEventListener('message', (event) => this.handleMessage(event));
    socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) {
        pending.reject(new ClosedFailure('CDP_CONNECTION_CLOSED'));
      }
      this.pending.clear();
    });
  }

  handleMessage(event) {
    let message;
    try {
      message = JSON.parse(String(event.data));
    } catch {
      fail('CDP_MESSAGE_INVALID');
    }
    if (message.id !== undefined) {
      const pending = this.pending.get(message.id);
      if (pending === undefined) return;
      this.pending.delete(message.id);
      if (message.error !== undefined) pending.reject(new ClosedFailure('CDP_COMMAND_FAILED'));
      else pending.resolve(message.result);
      return;
    }
    if (typeof message.method !== 'string') return;
    for (const listener of this.listeners.get(message.method) ?? []) listener(message.params ?? {});
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  call(method, params = {}) {
    if (this.socket === null || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new ClosedFailure('CDP_CONNECTION_INVALID'));
    }
    const id = (this.sequence += 1);
    return new Promise((resolvePromise, rejectPromise) => {
      this.pending.set(id, { reject: rejectPromise, resolve: resolvePromise });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket?.close();
  }
}

async function evaluate(connection, expression) {
  const result = await connection.call('Runtime.evaluate', {
    awaitPromise: true,
    expression,
    returnByValue: true,
  });
  if (result.exceptionDetails !== undefined || result.result?.type === 'undefined') {
    fail('BROWSER_EVALUATION_FAILED');
  }
  return result.result.value;
}

async function waitForDocument(connection) {
  const deadline = Date.now() + PAGE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const ready = await evaluate(connection, 'document.readyState');
      if (ready === 'complete') {
        await sleep(100);
        return;
      }
    } catch (error) {
      if (!(error instanceof ClosedFailure) || error.code !== 'CDP_COMMAND_FAILED') throw error;
    }
    await sleep(25);
  }
  fail('PAGE_READY_TIMEOUT');
}

function dispatchKey(connection, type, key, code, modifiers = 0) {
  return connection.call('Input.dispatchKeyEvent', {
    code,
    key,
    modifiers,
    type,
    windowsVirtualKeyCode: key === 'Tab' ? 9 : 13,
  });
}

async function pressKey(connection, key, code) {
  await dispatchKey(connection, 'keyDown', key, code);
  await dispatchKey(connection, 'keyUp', key, code);
}

function assertLoopbackRequest(url, origin) {
  if (url === 'about:blank' || url.startsWith('data:') || url.startsWith('blob:')) return;
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    fail('BROWSER_REQUEST_URL_INVALID');
  }
  if (parsed.origin !== origin) fail('UNEXPECTED_OUTBOUND_REQUEST');
}

async function navigate(connection, state, origin, route, viewport) {
  state.documentStatus = null;
  state.consoleErrors = 0;
  state.pageErrors = 0;
  state.currentDocumentUrl = `${origin}${route.path}`;
  await connection.call('Emulation.setDeviceMetricsOverride', {
    deviceScaleFactor: 1,
    height: viewport.height,
    mobile: false,
    screenHeight: viewport.height,
    screenWidth: viewport.width,
    width: viewport.width,
  });
  const navigation = await connection.call('Page.navigate', { url: state.currentDocumentUrl });
  if (navigation.errorText !== undefined) fail('PAGE_NAVIGATION_FAILED');
  await waitForDocument(connection);
  if (state.documentStatus !== route.expected_status) fail('PAGE_STATUS_INVALID');
  if (state.unexpectedOutboundRequests !== 0) fail('UNEXPECTED_OUTBOUND_REQUEST');
  if (state.consoleErrors !== 0) fail('PAGE_CONSOLE_ERROR');
  if (state.pageErrors !== 0) fail('PAGE_RUNTIME_ERROR');
}

function validateBasics(value, route) {
  const basics = requireMapping(value, 'PAGE_BASICS_INVALID');
  requireExactKeys(
    basics,
    ['documentClientWidth', 'documentScrollWidth', 'h1Count', 'language', 'mainCount', 'title'],
    'PAGE_BASICS_INVALID',
  );
  const title = requireString(basics.title, 'PAGE_TITLE_INVALID').trim();
  if (title.length === 0 || basics.h1Count !== 1 || basics.language !== 'ja') {
    fail('PAGE_SEMANTICS_INVALID');
  }
  if (route.expected_status === 200 && basics.mainCount !== 1) fail('PAGE_MAIN_INVALID');
  const overflow = basics.documentScrollWidth - basics.documentClientWidth;
  if (!Number.isSafeInteger(overflow) || overflow > 1) fail('PAGE_HORIZONTAL_OVERFLOW');
  return {
    document_overflow_css_px: overflow,
    h1_count: basics.h1Count,
    language: basics.language,
    main_count: basics.mainCount,
    title,
  };
}

async function runAxe(connection, axeSource) {
  await connection.call('Runtime.evaluate', { expression: axeSource });
  const result = requireMapping(
    await evaluate(
      connection,
      `axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }).then((result) => ({ incomplete: result.incomplete.map((item) => item.id).sort(), passes: result.passes.length, violations: result.violations.map((item) => ({ id: item.id, impact: item.impact, node_count: item.nodes.length })).sort((left, right) => left.id.localeCompare(right.id)) }))`,
    ),
    'AXE_RESULT_INVALID',
  );
  const violations = requireArray(result.violations, 'AXE_RESULT_INVALID');
  const incomplete = requireArray(result.incomplete, 'AXE_RESULT_INVALID');
  if (violations.length !== 0 || incomplete.length !== 0) fail('AXE_FINDING_PRESENT');
  return {
    incomplete,
    pass_rule_count: requireInteger(result.passes, 'AXE_RESULT_INVALID'),
    violations,
  };
}

async function checkSkipLink(connection) {
  await evaluate(connection, 'document.body.focus(); true');
  await pressKey(connection, 'Tab', 'Tab');
  const focus = requireMapping(
    await evaluate(
      connection,
      `(() => { const active = document.activeElement; if (!(active instanceof HTMLAnchorElement)) return { href: null, outlineStyle: null, outlineWidth: null, visible: false }; const box = active.getBoundingClientRect(); const style = getComputedStyle(active); return { href: active.getAttribute('href'), outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, visible: box.width > 0 && box.height > 0 && box.bottom >= 0 && box.right >= 0 && box.top <= innerHeight && box.left <= innerWidth }; })()`,
    ),
    'SKIP_LINK_INVALID',
  );
  if (
    typeof focus.href !== 'string' ||
    !/^#[A-Za-z][A-Za-z0-9_-]*$/u.test(focus.href) ||
    focus.visible !== true ||
    focus.outlineStyle === 'none' ||
    focus.outlineWidth === '0px'
  ) {
    fail('SKIP_LINK_FOCUS_INVALID');
  }
  await pressKey(connection, 'Enter', 'Enter');
  await sleep(50);
  const targetReached = await evaluate(
    connection,
    `(() => { const target = document.querySelector(${JSON.stringify(focus.href)}); return target !== null && (document.activeElement === target || location.hash === ${JSON.stringify(focus.href)}); })()`,
  );
  if (targetReached !== true) fail('SKIP_LINK_TARGET_INVALID');
  return {
    first_focus: 'SKIP_LINK',
    focus_indicator_visible: true,
    target_reached: true,
  };
}

async function auditRoutes(connection, contract, origin, axeSource) {
  const state = {
    consoleErrors: 0,
    currentDocumentUrl: null,
    documentStatus: null,
    pageErrors: 0,
    unexpectedOutboundRequests: 0,
  };
  connection.on('Network.requestWillBeSent', ({ request }) => {
    if (request && typeof request.url === 'string') {
      try {
        assertLoopbackRequest(request.url, origin);
      } catch {
        state.unexpectedOutboundRequests += 1;
      }
    }
  });
  connection.on('Network.responseReceived', ({ response, type }) => {
    if (
      type === 'Document' &&
      response &&
      response.url === state.currentDocumentUrl &&
      Number.isSafeInteger(response.status)
    ) {
      state.documentStatus = response.status;
    }
  });
  connection.on('Runtime.consoleAPICalled', ({ type }) => {
    if (type === 'error' || type === 'assert') state.consoleErrors += 1;
  });
  connection.on('Runtime.exceptionThrown', () => {
    state.pageErrors += 1;
  });

  await connection.call('Page.enable');
  await connection.call('Runtime.enable');
  await connection.call('Network.enable');

  const routes = requireArray(contract.observed_routes, 'CONTRACT_ROUTES_INVALID');
  const viewports = requireArray(contract.viewport_profiles, 'CONTRACT_VIEWPORTS_INVALID');
  const results = [];
  const titles = new Set();
  for (const routeValue of routes) {
    const route = requireMapping(routeValue, 'CONTRACT_ROUTE_INVALID');
    const viewportResults = [];
    let primaryBasics = null;
    let axe = null;
    let keyboard = { status: 'NOT_APPLICABLE_NON_200' };
    for (const viewportValue of viewports) {
      const viewport = requireMapping(viewportValue, 'CONTRACT_VIEWPORT_INVALID');
      await navigate(connection, state, origin, route, viewport);
      const basics = validateBasics(
        await evaluate(
          connection,
          `({ documentClientWidth: document.documentElement.clientWidth, documentScrollWidth: document.documentElement.scrollWidth, h1Count: document.querySelectorAll('h1').length, language: document.documentElement.lang, mainCount: document.querySelectorAll('main').length, title: document.title })`,
        ),
        route,
      );
      viewportResults.push({
        document_overflow_css_px: basics.document_overflow_css_px,
        height: viewport.height,
        id: viewport.id,
        width: viewport.width,
      });
      if (viewport.id === 'MOBILE_360') {
        primaryBasics = basics;
        axe = await runAxe(connection, axeSource);
        if (route.expected_status === 200) keyboard = await checkSkipLink(connection);
      }
    }
    if (primaryBasics === null || axe === null) fail('CONTRACT_PRIMARY_VIEWPORT_MISSING');
    if (titles.has(primaryBasics.title)) fail('PAGE_TITLE_DUPLICATE');
    titles.add(primaryBasics.title);
    results.push({
      axe,
      expected_status: route.expected_status,
      h1_count: primaryBasics.h1_count,
      keyboard,
      language: primaryBasics.language,
      main_count: primaryBasics.main_count,
      observed_status: route.expected_status,
      path: route.path,
      runtime_kind: route.runtime_kind,
      screen_id: route.screen_id,
      title: primaryBasics.title,
      viewports: viewportResults,
    });
  }
  return results;
}

async function launchBrowser(browserExecutable, contract, origin) {
  const profile = mkdtempSync(join(tmpdir(), 'raos-st1007-browser-'));
  const child = spawn(
    browserExecutable,
    [
      '--headless=new',
      '--no-sandbox',
      '--disable-background-networking',
      '--disable-component-update',
      '--disable-default-apps',
      '--disable-sync',
      '--disable-breakpad',
      '--disable-client-side-phishing-detection',
      '--disable-domain-reliability',
      '--disable-features=OptimizationHints,MediaRouter,Translate',
      '--metrics-recording-only',
      '--no-first-run',
      '--no-default-browser-check',
      '--remote-debugging-port=0',
      '--password-store=basic',
      '--use-mock-keychain',
      `--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE ${LOOPBACK_HOST}`,
      `--user-data-dir=${profile}`,
      'about:blank',
    ],
    {
      env: closedEnvironment(),
      stdio: ['ignore', 'ignore', 'pipe'],
    },
  );
  const output = captureProcessOutput(child);
  try {
    const browserWebSocketUrl = await waitForDevTools(child, output);
    const endpoint = new URL(browserWebSocketUrl);
    if (endpoint.hostname !== LOOPBACK_HOST && endpoint.hostname !== 'localhost') {
      fail('BROWSER_DEBUG_ORIGIN_INVALID');
    }
    const browserConnection = new CdpConnection(browserWebSocketUrl);
    await browserConnection.open();
    const version = await browserConnection.call('Browser.getVersion');
    const expectedProduct = `Chrome/${contract.runtime.browser.version}`;
    if (version.product !== expectedProduct) fail('BROWSER_VERSION_DRIFT');
    browserConnection.close();

    const targetResponse = await fetch(
      `http://${endpoint.host}/json/new?${encodeURIComponent('about:blank')}`,
      { method: 'PUT', signal: AbortSignal.timeout(2_000) },
    );
    if (!targetResponse.ok) fail('BROWSER_TARGET_FAILED');
    const target = parseJsonObject(
      Buffer.from(await targetResponse.arrayBuffer()),
      'BROWSER_TARGET_INVALID',
    );
    const targetWebSocketUrl = requireString(target.webSocketDebuggerUrl, 'BROWSER_TARGET_INVALID');
    const connection = new CdpConnection(targetWebSocketUrl);
    await connection.open();
    const axePath = resolveOwnedPath(contract.runtime.axe.script_path);
    const axeBytes = readBounded(axePath);
    if (sha256Bytes(axeBytes) !== contract.runtime.axe.script_sha256) fail('AXE_HASH_DRIFT');
    const routes = await auditRoutes(connection, contract, origin, axeBytes.toString('utf8'));
    connection.close();
    return {
      child,
      profile,
      result: {
        browser: {
          executable_sha256: contract.runtime.browser.executable_sha256,
          product: contract.runtime.browser.product,
          version: contract.runtime.browser.version,
        },
        routes,
      },
    };
  } catch (error) {
    await stopChild(child, 'BROWSER_STOP_FAILED');
    const profilePrefix = `${tmpdir()}${sep}raos-st1007-browser-`;
    if (profile.startsWith(profilePrefix)) rmSync(profile, { force: true, recursive: true });
    throw error;
  }
}

function sortJson(value) {
  if (Array.isArray(value)) return value.map((item) => sortJson(item));
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortJson(item)]),
    );
  }
  return value;
}

function encodeJson(value) {
  return Buffer.from(`${JSON.stringify(sortJson(value))}\n`, 'utf8');
}

function buildEvidence(contract, sourceArtifacts, browserResult) {
  const sourceBundle = encodeJson(sourceArtifacts);
  const unavailable = requireArray(
    contract.unavailable_canonical_screens,
    'CONTRACT_UNAVAILABLE_SCREENS_INVALID',
  );
  return {
    authority: contract.authority,
    automated_execution: {
      axe: {
        script_sha256: contract.runtime.axe.script_sha256,
        tags: contract.runtime.axe.tags,
        version: contract.runtime.axe.version,
      },
      browser: browserResult.browser,
      environment: 'LOCAL_ENV_DEV_NON_FORMAL',
      network: 'LOOPBACK_ONLY',
      result: 'LOCAL_AUTOMATED_PASS_IMPLEMENTED_SURFACES_ONLY',
      routes: browserResult.routes,
    },
    canonical_coverage: {
      implemented_screen_count: 5,
      observed_default_404_count: 1,
      unavailable_canonical_screens: unavailable,
    },
    classification: contract.classification,
    formal_boundary: contract.formal_boundary,
    schema_version: contract.schema_version,
    source_artifacts: sourceArtifacts,
    source_bundle_sha256: sha256Bytes(sourceBundle),
    story_id: contract.story_id,
  };
}

function ensureOutputPath(contract) {
  const relativePath = requireString(contract.output_path, 'OUTPUT_PATH_INVALID');
  const path = resolveOwnedPath(relativePath);
  const parent = dirname(path);
  const fromRoot = relative(ROOT, parent);
  if (fromRoot === '..' || fromRoot.startsWith(`..${sep}`)) fail('OUTPUT_PATH_INVALID');
  mkdirSync(parent, { recursive: true, mode: 0o755 });
  if (lstatSync(parent).isSymbolicLink()) fail('OUTPUT_PATH_INVALID');
  if (existsSync(path) && lstatSync(path).isSymbolicLink()) fail('OUTPUT_PATH_INVALID');
  return path;
}

function writeAtomic(path, bytes) {
  const temporary = join(dirname(path), `.${basename(path)}.${String(process.pid)}.tmp`);
  let descriptor = null;
  try {
    descriptor = openSync(temporary, 'wx', 0o600);
    writeFileSync(descriptor, bytes);
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = null;
    chmodSync(temporary, 0o644);
    renameSync(temporary, path);
    const directoryDescriptor = openSync(dirname(path), 'r');
    fsyncSync(directoryDescriptor);
    closeSync(directoryDescriptor);
  } finally {
    if (descriptor !== null) closeSync(descriptor);
    if (existsSync(temporary)) unlinkSync(temporary);
  }
}

async function execute(argv) {
  ensureRepositoryRoot();
  const args = parseArguments(argv);
  const contract = loadContract();
  await verifyBrowserExecutable(args.browserExecutable, contract);
  const sourceArtifacts = await buildSourceArtifacts(contract);
  await runBuild(contract);
  const port = await reserveLoopbackPort();
  const origin = `http://${LOOPBACK_HOST}:${String(port)}`;
  let server = null;
  let browser = null;
  try {
    server = await startNextServer(port);
    browser = await launchBrowser(args.browserExecutable, contract, origin);
    const evidence = buildEvidence(contract, sourceArtifacts, browser.result);
    const bytes = encodeJson(evidence);
    const outputPath = ensureOutputPath(contract);
    if (args.mode === 'write') {
      writeAtomic(outputPath, bytes);
      return 'ST1007_LOCAL_BROWSER_EVIDENCE_WRITTEN';
    }
    if (!existsSync(outputPath)) fail('GENERATED_EVIDENCE_MISSING');
    const current = readBounded(outputPath);
    if (!current.equals(bytes)) fail('GENERATED_EVIDENCE_DRIFT');
    return 'ST1007_LOCAL_BROWSER_EVIDENCE_CHECKED';
  } finally {
    if (browser !== null) {
      await stopChild(browser.child, 'BROWSER_STOP_FAILED');
      const profilePrefix = `${tmpdir()}${sep}raos-st1007-browser-`;
      if (!browser.profile.startsWith(profilePrefix)) fail('BROWSER_PROFILE_INVALID');
      rmSync(browser.profile, { force: true, recursive: true });
    }
    if (server !== null) {
      await stopChild(server.child, 'NEXT_SERVER_STOP_FAILED');
      if (server.output.overflow) fail('NEXT_SERVER_OUTPUT_INVALID');
    }
  }
}

export { ClosedFailure, buildEvidence, encodeJson, parseArguments, sortJson };

if (process.argv[1] !== undefined && realpathSync(process.argv[1]) === realpathSync(SCRIPT_PATH)) {
  try {
    const message = await execute(process.argv.slice(2));
    process.stdout.write(`${message}\n`);
  } catch (error) {
    const code = error instanceof ClosedFailure ? error.code : 'ST1007_BROWSER_RUN_FAILED';
    process.stderr.write(`${code}\n`);
    process.exitCode = 1;
  }
}
