import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import {
  closeSync,
  createReadStream,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const SCRIPT_PATH = fileURLToPath(import.meta.url);
export const ROOT = realpathSync(resolve(dirname(SCRIPT_PATH), '../..'));
const PREVIEW_ROOT = join(ROOT, 'changes/raos-v2/phase-2/preview');
const HARNESS_PATH = 'tests/raos_v2/browser-validation.mjs';
const COMMAND_CONTRACT =
  'NODE24_LOCAL_CDP_AXE_WITH_ABSOLUTE_BROWSER_AND_OUTPUT_PLAYWRIGHT_RECEIPT_V1';
const REQUIRED_NODE_MAJOR = 24;
const LOOPBACK = '127.0.0.1';
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const TIMEOUT_MS = 20_000;
export const ROUTES = Object.freeze([
  '/',
  '/carry-on/',
  '/tools/carry-on-size-checker/',
  '/guides/carry-on-baggage-rules/',
  '/guides/low-cost-carrier-7kg-packing/',
  '/carry-on-suitcase-comparison/',
  '/guides/carry-on-bag-measurement/',
  '/policy/how-we-compare-carry-on-products/',
  '/differences/ace-cresta-vs-difference-vs-maxpass4/',
]);
const VIEWPORTS = Object.freeze([
  Object.freeze({
    equivalentZoomPercent: 400,
    height: 800,
    name: 'reflow-320-equivalent-400pct',
    width: 320,
  }),
  Object.freeze({ height: 844, name: 'mobile-390', width: 390 }),
  Object.freeze({ height: 800, name: 'mobile-360', width: 360 }),
  Object.freeze({ height: 1024, name: 'tablet-768', width: 768 }),
  Object.freeze({ height: 900, name: 'desktop-1440', width: 1440 }),
]);
const MOBILE_AUDIT_VIEWPORT = VIEWPORTS.find((viewport) => viewport.width === 390);
if (MOBILE_AUDIT_VIEWPORT === undefined) throw new Error('MOBILE_AUDIT_VIEWPORT_MISSING');

class BrowserValidationError extends Error {
  constructor(code) {
    super(code);
    this.name = 'BrowserValidationError';
    this.code = code;
  }
}

function fail(code) {
  throw new BrowserValidationError(code);
}

function parseArguments(argv) {
  let browserExecutable = null;
  let output = null;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--browser-executable' && browserExecutable === null) {
      browserExecutable = argv[index + 1] ?? null;
      index += 1;
      continue;
    }
    if (argument === '--output' && output === null) {
      output = argv[index + 1] ?? null;
      index += 1;
      continue;
    }
    fail('ARGUMENT_INVALID');
  }
  if (browserExecutable === null || !isAbsolute(browserExecutable)) {
    fail('BROWSER_EXECUTABLE_ABSOLUTE_REQUIRED');
  }
  let outputPath = null;
  if (output !== null) {
    outputPath = resolve(ROOT, output);
    const outputRoot = join(ROOT, 'output/playwright');
    const fromOutputRoot = relative(outputRoot, outputPath);
    if (
      fromOutputRoot === '' ||
      fromOutputRoot === '..' ||
      fromOutputRoot.startsWith(`..${sep}`) ||
      isAbsolute(fromOutputRoot) ||
      !outputPath.endsWith('.json')
    ) {
      fail('OUTPUT_PATH_INVALID');
    }
  }
  return Object.freeze({ browserExecutable, outputPath });
}

function readBounded(path) {
  const info = lstatSync(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_FILE_BYTES) {
    fail('PREVIEW_FILE_INVALID');
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

function pathForRoute(route) {
  const suffix = route === '/' ? 'index.html' : `${route.slice(1)}index.html`;
  const path = resolve(PREVIEW_ROOT, suffix);
  const fromRoot = relative(PREVIEW_ROOT, path);
  if (fromRoot === '..' || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    fail('ROUTE_PATH_INVALID');
  }
  return path;
}

export function verifyPreview() {
  const digests = {};
  for (const route of ROUTES) {
    const path = pathForRoute(route);
    if (!existsSync(path)) fail('PREVIEW_ROUTE_MISSING');
    digests[route] = sha256Bytes(readBounded(path));
  }
  return Object.freeze(digests);
}

function auditTransferBudgets() {
  const compactRoutes = new Set(['/', '/tools/carry-on-size-checker/']);
  const routes = {};
  for (const route of ROUTES) {
    const bytes = readBounded(pathForRoute(route)).length;
    const ceilingBytes = compactRoutes.has(route) ? 800 * 1024 : 1_200 * 1024;
    if (bytes > ceilingBytes) fail('PAGE_TRANSFER_CEILING_EXCEEDED');
    routes[route] = Object.freeze({
      additionalResourceBytes: 0,
      bytes,
      ceilingBytes,
      inlineSingleDocument: true,
      withinCeiling: true,
    });
  }
  return Object.freeze({
    articleCeilingBytes: 1_200 * 1024,
    homeToolCeilingBytes: 800 * 1024,
    routes: Object.freeze(routes),
  });
}

export function startServer() {
  const requests = [];
  const server = createServer((request, response) => {
    try {
      const parsed = new URL(request.url ?? '/', `http://${LOOPBACK}`);
      requests.push(Object.freeze({ method: request.method, path: parsed.pathname }));
      if (
        (request.method !== 'GET' && request.method !== 'HEAD') ||
        parsed.search !== '' ||
        !ROUTES.includes(parsed.pathname)
      ) {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('not found');
        return;
      }
      const body = readBounded(pathForRoute(parsed.pathname));
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Length': String(body.length),
        'Content-Security-Policy':
          "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src data:; form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
        'Content-Type': 'text/html; charset=utf-8',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
      });
      response.end(request.method === 'HEAD' ? undefined : body);
    } catch {
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('closed failure');
    }
  });
  return new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, LOOPBACK, () => {
      const address = server.address();
      if (address === null || typeof address === 'string') fail('SERVER_ADDRESS_INVALID');
      resolvePromise(
        Object.freeze({
          close: () => new Promise((resolveClose) => server.close(resolveClose)),
          origin: `http://${LOOPBACK}:${address.port}`,
          requests,
        }),
      );
    });
  });
}

function requestJson(url, method = 'GET') {
  return new Promise((resolvePromise, rejectPromise) => {
    const request = globalThis.fetch(url, { method, redirect: 'error' });
    const timer = setTimeout(() => rejectPromise(new Error('HTTP_TIMEOUT')), TIMEOUT_MS);
    request.then(async (response) => {
      clearTimeout(timer);
      if (!response.ok) {
        rejectPromise(new Error(`HTTP_${response.status}`));
        return;
      }
      resolvePromise(await response.json());
    }, rejectPromise);
  });
}

export async function waitForDebugger(port) {
  const deadline = Date.now() + TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const targets = await requestJson(`http://${LOOPBACK}:${port}/json/list`);
      const page = targets.find((target) => target.type === 'page');
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {
      // The browser endpoint is expected to be unavailable briefly during start-up.
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  fail('BROWSER_DEBUGGER_TIMEOUT');
}

export class CdpConnection {
  constructor(url) {
    this.nextId = 1;
    this.pending = new Map();
    this.events = new Map();
    this.socket = new WebSocket(url);
  }

  async open() {
    await new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error('CDP_OPEN_TIMEOUT')), TIMEOUT_MS);
      this.socket.addEventListener(
        'open',
        () => {
          clearTimeout(timer);
          resolvePromise();
        },
        { once: true },
      );
      this.socket.addEventListener('error', rejectPromise, { once: true });
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (typeof message.id === 'number') {
        const pending = this.pending.get(message.id);
        if (pending !== undefined) {
          this.pending.delete(message.id);
          if (message.error) pending.reject(new Error(message.error.message));
          else pending.resolve(message.result ?? {});
        }
        return;
      }
      const handlers = this.events.get(message.method) ?? [];
      for (const handler of handlers) handler(message.params ?? {});
    });
  }

  call(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectPromise(new Error(`CDP_TIMEOUT_${method}`));
      }, TIMEOUT_MS);
      this.pending.set(id, {
        reject: (error) => {
          clearTimeout(timer);
          rejectPromise(error);
        },
        resolve: (value) => {
          clearTimeout(timer);
          resolvePromise(value);
        },
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  on(method, handler) {
    const handlers = this.events.get(method) ?? [];
    handlers.push(handler);
    this.events.set(method, handlers);
  }

  close() {
    this.socket.close();
  }
}

export async function evaluate(connection, expression) {
  const result = await connection.call('Runtime.evaluate', {
    awaitPromise: true,
    expression,
    returnByValue: true,
  });
  if (result.exceptionDetails !== undefined) fail('BROWSER_EVALUATION_FAILED');
  return result.result?.value;
}

export async function navigate(connection, url) {
  await connection.call('Page.navigate', { url });
  const deadline = Date.now() + TIMEOUT_MS;
  while (Date.now() < deadline) {
    const ready = await evaluate(connection, 'document.readyState');
    if (ready === 'complete') return;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 50));
  }
  fail('PAGE_LOAD_TIMEOUT');
}

export async function setViewport(connection, viewport) {
  await connection.call('Emulation.setDeviceMetricsOverride', {
    deviceScaleFactor: 1,
    height: viewport.height,
    mobile: viewport.width < 768,
    screenHeight: viewport.height,
    screenWidth: viewport.width,
    width: viewport.width,
  });
}

async function auditBasics(connection) {
  return evaluate(
    connection,
    `(() => {
    const h1 = [...document.querySelectorAll('h1')];
    const focusables = [...document.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),summary,[tabindex]:not([tabindex="-1"])')]
      .filter((node) => {
        const closedDetails = node.closest('details:not([open])');
        const ownSummary = node.matches('summary') && node.parentElement === closedDetails;
        return !node.closest('[hidden]') && (!closedDetails || ownSummary) && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
      });
    return {
      h1Count: h1.length,
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      lang: document.documentElement.lang,
      disclosureVisible: Boolean(document.querySelector('.disclosure-bar')),
      focusableCount: focusables.length,
      resultStates: [...document.querySelectorAll('[data-state]')].map((node) => node.dataset.state),
    };
  })()`,
  );
}

async function auditAccessibilityTree(connection, route) {
  const tree = await connection.call('Accessibility.getFullAXTree');
  const nodes = Array.isArray(tree.nodes) ? tree.nodes.filter((node) => !node.ignored) : [];
  const value = (field) => (typeof field?.value === 'string' ? field.value : '');
  const roleCounts = {};
  const interactiveRoles = new Set([
    'button',
    'checkbox',
    'combobox',
    'DisclosureTriangle',
    'link',
    'textbox',
  ]);
  let unnamedInteractiveCount = 0;
  let levelOneHeadingCount = 0;
  const normalized = [];
  for (const node of nodes) {
    const role = value(node.role);
    const name = value(node.name).trim();
    roleCounts[role] = (roleCounts[role] ?? 0) + 1;
    if (interactiveRoles.has(role) && name.length === 0) unnamedInteractiveCount += 1;
    const level = (node.properties ?? []).find((property) => property.name === 'level')?.value
      ?.value;
    if (role === 'heading' && level === 1) levelOneHeadingCount += 1;
    normalized.push([role, name, level ?? null]);
  }
  if (
    nodes.length < 10 ||
    roleCounts.RootWebArea !== 1 ||
    (roleCounts.main ?? 0) !== 1 ||
    (roleCounts.banner ?? 0) < 1 ||
    (roleCounts.contentinfo ?? 0) < 1 ||
    (roleCounts.heading ?? 0) < 1 ||
    levelOneHeadingCount !== 1 ||
    unnamedInteractiveCount !== 0
  ) {
    fail(`AX_TREE_SCREEN_READER_SMOKE_INVALID_${diagnosticToken(route)}`);
  }
  return Object.freeze({
    fullTreeQueried: true,
    levelOneHeadingCount,
    nodeCount: nodes.length,
    screenReaderSmoke: true,
    structuralSha256: sha256Bytes(JSON.stringify(normalized)),
    unnamedInteractiveCount,
  });
}

function diagnosticToken(value) {
  const routeSlug = String(value)
    .replaceAll(/[^A-Za-z0-9]+/gu, '_')
    .replaceAll(/^_+|_+$/gu, '');
  return routeSlug.length === 0 ? 'ROOT' : routeSlug.slice(0, 80);
}

async function auditKeyboard(connection, route) {
  await evaluate(connection, 'document.activeElement?.blur(); window.scrollTo(0, 0); true');
  await dispatchKey(connection, 'Tab', 'Tab');
  const first = await evaluate(
    connection,
    `(() => {
    const node = document.activeElement;
    const style = getComputedStyle(node);
    return { className: node.className, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  })()`,
  );
  if (!String(first.className).includes('skip-link')) fail('KEYBOARD_SKIP_LINK_NOT_FIRST');
  if (first.outlineStyle === 'none' || Number.parseFloat(first.outlineWidth) < 3) {
    fail('KEYBOARD_FOCUS_NOT_VISIBLE');
  }
  await dispatchKey(connection, 'Enter', 'Enter');
  const skipped = await evaluate(
    connection,
    "location.hash === '#main' && document.activeElement?.id === 'main'",
  );
  if (!skipped) fail('KEYBOARD_SKIP_LINK_FAILED');
  // Start a fresh document for the complete tab-order walk. Continuing from
  // #main would intentionally skip header controls and hand focus to browser
  // chrome at the end instead of wrapping within the document.
  const currentUrl = await evaluate(
    connection,
    "(() => { const value = new URL(location.href); value.hash = ''; return value.href; })()",
  );
  await navigate(connection, currentUrl);
  await evaluate(connection, 'document.activeElement?.blur(); window.scrollTo(0, 0); true');
  const focusableDescriptors = await evaluate(
    connection,
    `(() => {
    const selector = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
    return [...document.querySelectorAll(selector)]
      .filter((node) => {
        const closedDetails = node.closest('details:not([open])');
        const ownSummary = node.matches('summary') && node.parentElement === closedDetails;
        return (!closedDetails || ownSummary) && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
      })
      .map((node) => [node.tagName, node.id, node.getAttribute('name') ?? '', node.getAttribute('href') ?? ''].join(':'));
  })()`,
  );
  const visibleCount = focusableDescriptors.length;
  const visited = new Set();
  let focusTraversalSteps = 0;
  // Native datetime controls expose several internal keyboard stops while the
  // document activeElement remains the host input. Allow those stops, but
  // still require every document-level focusable to be visited before success.
  const maximumSteps = visibleCount * 4 + 8;
  while (visited.size < visibleCount && focusTraversalSteps < maximumSteps) {
    focusTraversalSteps += 1;
    await dispatchKey(connection, 'Tab', 'Tab');
    const focus = await evaluate(
      connection,
      `(() => {
      const selector = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
      const visible = [...document.querySelectorAll(selector)].filter((node) => {
        const closedDetails = node.closest('details:not([open])');
        const ownSummary = node.matches('summary') && node.parentElement === closedDetails;
        return (!closedDetails || ownSummary) && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
      });
      const node = document.activeElement;
      const style = getComputedStyle(node);
      return {
        activeId: node?.id ?? '',
        activeName: node?.getAttribute?.('name') ?? '',
        activeTag: node?.tagName ?? 'NONE',
        browserBoundary: node === document.body || node === document.documentElement,
        index: visible.indexOf(node),
        outlineStyle: style.outlineStyle,
        outlineWidth: Number.parseFloat(style.outlineWidth) || 0,
      };
    })()`,
    );
    if (focus.index < 0) {
      if (focus.browserBoundary) continue;
      fail(
        `KEYBOARD_FOCUS_PATH_INVALID_${diagnosticToken(route)}_${diagnosticToken(
          `${focus.activeTag}_${focus.activeId}_${focus.activeName}`,
        )}`,
      );
    }
    if (
      !visited.has(focus.index) &&
      (focus.outlineStyle === 'none' || focus.outlineWidth < 3)
    ) {
      fail(
        `KEYBOARD_FOCUS_NOT_VISIBLE_${diagnosticToken(route)}_${diagnosticToken(
          `${focus.activeTag}_${focus.activeId}_${focus.activeName}_${focus.outlineStyle}_${focus.outlineWidth}`,
        )}`,
      );
    }
    visited.add(focus.index);
  }
  if (visited.size !== visibleCount) {
    const missing = focusableDescriptors
      .filter((_value, index) => !visited.has(index))
      .map(diagnosticToken)
      .join('_');
    fail(
      `KEYBOARD_FOCUS_PATH_INCOMPLETE_${diagnosticToken(route)}_${visited.size}_OF_${visibleCount}_STEPS_${focusTraversalSteps}_MISSING_${missing}`,
    );
  }
  return Object.freeze({
    focusRingPx: Number.parseFloat(first.outlineWidth),
    focusTraversal: true,
    focusTraversalSteps,
    focusableCount: visibleCount,
    mainFocused: true,
    skipLink: true,
  });
}

async function dispatchKey(connection, code, key) {
  const virtualKeyCodes = Object.freeze({ Enter: 13, Space: 32, Tab: 9 });
  const windowsVirtualKeyCode = virtualKeyCodes[code] ?? 0;
  const text = code === 'Enter' ? '\r' : code === 'Space' ? ' ' : undefined;
  await connection.call('Input.dispatchKeyEvent', {
    code,
    key,
    text,
    type: 'keyDown',
    windowsVirtualKeyCode,
  });
  await connection.call('Input.dispatchKeyEvent', {
    code,
    key,
    type: 'keyUp',
    windowsVirtualKeyCode,
  });
}

async function runAxe(connection, axeSource) {
  await evaluate(connection, `${axeSource}\ntrue`);
  return evaluate(
    connection,
    `axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] }
  }).then((result) => ({
    incomplete: result.incomplete.map((entry) => entry.id).sort(),
    violations: result.violations.map((entry) => ({ id: entry.id, impact: entry.impact, nodes: entry.nodes.length })).sort((a, b) => a.id.localeCompare(b.id)),
  }))`,
  );
}

async function auditPrivacy(connection) {
  return evaluate(
    connection,
    `Promise.all([
    navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then((items) => items.length) : 0,
    indexedDB.databases ? indexedDB.databases().then((items) => items.length) : 0,
  ]).then(([serviceWorkers, databases]) => ({
    cookies: document.cookie,
    databases,
    localStorage: localStorage.length,
    serviceWorkers,
    sessionStorage: sessionStorage.length,
  }))`,
  );
}

async function auditJavascriptDisabledFallback(connection, origin) {
  const routes = ['/', '/tools/carry-on-size-checker/'];
  const results = {};
  await connection.call('Emulation.setScriptExecutionDisabled', { value: true });
  try {
    for (const route of routes) {
      await navigate(connection, `${origin}${route}`);
      const result = await evaluate(
        connection,
        `(() => {
        const fallback = document.querySelector('noscript .no-js-note');
        const form = document.querySelector('#carry-on-checker');
        const resultPanel = document.querySelector('#checker-result');
        return {
          fallbackText: fallback?.textContent?.trim() ?? '',
          fallbackVisible: fallback !== null && fallback.getClientRects().length > 0,
          formVisible: form !== null && form.getClientRects().length > 0,
          initialState: resultPanel?.dataset.state ?? '',
        };
      })()`,
      );
      if (
        !result.fallbackVisible ||
        !result.formVisible ||
        result.initialState !== 'UNKNOWN' ||
        !result.fallbackText.includes('JavaScriptが無効') ||
        !result.fallbackText.includes('公式リンク')
      ) {
        fail(`JAVASCRIPT_DISABLED_FALLBACK_INVALID_${diagnosticToken(route)}`);
      }
      results[route] = Object.freeze({
        fallbackVisible: true,
        formVisible: true,
        initialState: 'UNKNOWN',
      });
    }
  } finally {
    await connection.call('Emulation.setScriptExecutionDisabled', { value: false });
  }
  return Object.freeze({ routes: Object.freeze(results), testedRoutes: routes.length });
}

async function auditZoomAndMedia(connection) {
  await evaluate(connection, "document.documentElement.style.fontSize = '200%'; true");
  const zoom = await evaluate(
    connection,
    `({
    horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    fontSize: getComputedStyle(document.body).fontSize,
  })`,
  );
  await evaluate(connection, "document.documentElement.style.fontSize = ''; true");
  await connection.call('Emulation.setEmulatedMedia', {
    features: [
      { name: 'forced-colors', value: 'active' },
      { name: 'prefers-reduced-motion', value: 'reduce' },
    ],
    media: '',
  });
  const media = await evaluate(
    connection,
    `(() => {
    const target = document.querySelector('.result-panel') ?? document.querySelector('.content-section');
    const style = getComputedStyle(target);
    return {
      forcedColors: matchMedia('(forced-colors: active)').matches,
      reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
      borderStyle: style.borderStyle,
      transitionSeconds: Number.parseFloat(style.transitionDuration) || 0,
    };
  })()`,
  );
  await connection.call('Emulation.setEmulatedMedia', { features: [], media: '' });
  return Object.freeze({ media, zoom });
}

async function fillCheckerAndSubmit(connection, values) {
  return evaluate(
    connection,
    `(() => {
    const values = ${JSON.stringify(values)};
    const form = document.querySelector('#carry-on-checker');
    for (const [name, value] of Object.entries(values)) {
      const field = form.elements.namedItem(name);
      if (field instanceof HTMLInputElement && field.type === 'checkbox') field.checked = value === true;
      else field.value = String(value);
    }
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    return document.querySelector('#checker-result').dataset.state;
  })()`,
  );
}

async function auditChecker(connection) {
  const common = {
    'appendages-included': true,
    'bag-state': 'NORMAL',
    'carry-on-count': '1',
    depth: '20',
    'departure-at-jst': '2026-09-01T10:00',
    height: '45',
    'journey-scope': 'DOMESTIC',
    'personal-item-count': '1',
    'personal-item-underseat-confirmed': true,
    weight: '6',
    width: '35',
  };
  const pass = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'fare-option': 'NOT_APPLICABLE',
  });
  const failState = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'fare-option': 'NOT_APPLICABLE',
    'carrier-2': 'PEACH',
    'departure-at-jst-2': '2026-09-01T12:00',
    'journey-scope-2': 'DOMESTIC',
    weight: '8',
  });
  const unknown = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: '',
    carrier: 'ANA',
    'fare-option': 'NOT_APPLICABLE',
    'carrier-2': '',
    height: '50',
    width: '35',
  });
  const countFail = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'carry-on-count': '2',
    'fare-option': 'NOT_APPLICABLE',
    'personal-item-count': '0',
  });
  const underseatUnknown = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: '',
    carrier: 'JETSTAR_JAPAN',
    'fare-option': 'STANDARD_7KG',
    'personal-item-underseat-confirmed': false,
  });
  const reviewDeadlineStale = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: '',
    carrier: 'JETSTAR_JAPAN',
    'departure-at-jst': '2026-09-27T06:42',
    'fare-option': 'STANDARD_7KG',
  });
  const beforeObservedBoundaryUnknown = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'departure-at-jst': '2026-08-28T06:41',
    'fare-option': 'NOT_APPLICABLE',
  });
  const anaUnknownScope = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'fare-option': 'NOT_APPLICABLE',
    'journey-scope': 'UNKNOWN',
  });
  const anaInternationalNoMatch = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'fare-option': 'NOT_APPLICABLE',
    'journey-scope': 'INTERNATIONAL',
  });
  const peachInternationalPass = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: '',
    carrier: 'PEACH',
    'fare-option': 'NOT_APPLICABLE',
    'journey-scope': 'INTERNATIONAL',
  });
  const unknownDominatesNoMatch = await fillCheckerAndSubmit(connection, {
    ...common,
    aircraft: 'LARGE',
    carrier: 'ANA',
    'fare-option': 'NOT_APPLICABLE',
    'journey-scope': 'INTERNATIONAL',
    'carrier-2': 'ANA',
    'departure-at-jst-2': '2026-09-01T12:00',
    'fare-option-2': 'NOT_APPLICABLE',
    'journey-scope-2': 'DOMESTIC',
  });
  if (
    pass !== 'PASS' ||
    failState !== 'FAIL' ||
    unknown !== 'UNKNOWN' ||
    countFail !== 'FAIL' ||
    underseatUnknown !== 'UNKNOWN' ||
    reviewDeadlineStale !== 'STALE' ||
    beforeObservedBoundaryUnknown !== 'UNKNOWN' ||
    anaUnknownScope !== 'UNKNOWN' ||
    anaInternationalNoMatch !== 'NO_MATCH' ||
    peachInternationalPass !== 'PASS' ||
    unknownDominatesNoMatch !== 'UNKNOWN'
  ) {
    fail('CHECKER_STATE_MATRIX_INVALID');
  }
  return Object.freeze({
    allSegmentIntersection: true,
    anaInternationalNoMatch,
    anaUnknownScope,
    beforeObservedBoundaryUnknown,
    countFail,
    fail: failState,
    reviewDeadlineStale,
    pass,
    peachInternationalPass,
    underseatUnknown,
    unknown,
    unknownDominatesNoMatch,
  });
}

async function auditCheckerKeyboard(connection) {
  const submitSelector = '#carry-on-checker button[type="submit"]';
  const resetSelector = '#carry-on-checker button[type="reset"]';
  await evaluate(connection, `document.querySelector('${submitSelector}').focus(); true`);
  await dispatchKey(connection, 'Enter', 'Enter');
  const empty = await evaluate(
    connection,
    `({
    activeId: document.activeElement?.id,
    state: document.querySelector('#checker-result').dataset.state,
  })`,
  );
  if (empty.activeId !== 'form-errors' || empty.state !== 'UNKNOWN') {
    fail(
      `KEYBOARD_EMPTY_SUBMIT_INVALID_${diagnosticToken(empty.activeId)}_${diagnosticToken(empty.state)}`,
    );
  }
  await evaluate(
    connection,
    `(() => {
    const values = ${JSON.stringify({
      'appendages-included': true,
      'bag-state': 'NORMAL',
      'carry-on-count': '1',
      depth: '20',
      'departure-at-jst': '2026-09-01T10:00',
      height: '45',
      'journey-scope': 'DOMESTIC',
      'personal-item-count': '1',
      weight: '6',
      width: '35',
      aircraft: 'LARGE',
      carrier: 'ANA',
      'fare-option': 'NOT_APPLICABLE',
    })};
    const form = document.querySelector('#carry-on-checker');
    for (const [name, value] of Object.entries(values)) {
      const field = form.elements.namedItem(name);
      if (field instanceof HTMLInputElement && field.type === 'checkbox') field.checked = value === true;
      else field.value = String(value);
    }
    document.querySelector('${submitSelector}').focus();
    return true;
  })()`,
  );
  await dispatchKey(connection, 'Enter', 'Enter');
  const pass = await evaluate(
    connection,
    "document.querySelector('#checker-result').dataset.state",
  );
  if (pass !== 'PASS') fail('KEYBOARD_PASS_SUBMIT_INVALID');
  await evaluate(connection, `document.querySelector('${resetSelector}').focus(); true`);
  await dispatchKey(connection, 'Enter', 'Enter');
  const reset = await evaluate(
    connection,
    "document.querySelector('#checker-result').dataset.state",
  );
  if (reset !== 'UNKNOWN') fail('KEYBOARD_RESET_INVALID');
  return Object.freeze({
    emptyErrorSummaryFocused: true,
    passSubmitted: true,
    resetActivated: true,
  });
}

export async function launchBrowser(browserExecutable, remotePort, profilePath) {
  const executable = realpathSync(browserExecutable);
  const child = spawn(
    executable,
    [
      '--headless=new',
      '--disable-background-networking',
      '--disable-component-update',
      '--disable-default-apps',
      '--disable-domain-reliability',
      '--disable-features=MediaRouter,OptimizationHints,Translate',
      '--disable-sync',
      '--metrics-recording-only',
      '--no-first-run',
      '--no-sandbox',
      `--remote-debugging-address=${LOOPBACK}`,
      `--remote-debugging-port=${remotePort}`,
      `--user-data-dir=${profilePath}`,
      'about:blank',
    ],
    {
      env: {
        LANG: 'C.UTF-8',
        LC_ALL: 'C.UTF-8',
        PATH: '/usr/bin:/bin',
      },
      stdio: ['ignore', 'ignore', 'pipe'],
    },
  );
  let stderr = '';
  child.stderr.on('data', (chunk) => {
    if (stderr.length < 1024 * 1024) stderr += String(chunk);
  });
  return Object.freeze({ child, executable, stderr: () => stderr });
}

export async function reservePort() {
  const server = createServer();
  await new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, LOOPBACK, resolvePromise);
  });
  const address = server.address();
  if (address === null || typeof address === 'string') fail('PORT_RESERVATION_INVALID');
  await new Promise((resolvePromise) => server.close(resolvePromise));
  return address.port;
}

function writeEvidence(path, evidence) {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.tmp-${process.pid}`;
  const descriptor = openSync(temporary, 'wx', 0o600);
  try {
    writeFileSync(descriptor, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  } finally {
    closeSync(descriptor);
  }
  renameSync(temporary, path);
}

async function main() {
  if (realpathSync(process.cwd()) !== ROOT) fail('WORKSPACE_ROOT_REQUIRED');
  if (Number.parseInt(process.versions.node.split('.', 1)[0] ?? '', 10) !== REQUIRED_NODE_MAJOR) {
    fail('NODE_RUNTIME_MAJOR_INVALID');
  }
  const argumentsValue = parseArguments(process.argv.slice(2));
  const previewDigests = verifyPreview();
  const transfer = auditTransferBudgets();
  const axePath = require.resolve('axe-core/axe.min.js');
  const axePackage = JSON.parse(readFileSync(require.resolve('axe-core/package.json'), 'utf8'));
  if (axePackage.version !== '4.12.1') fail('AXE_VERSION_INVALID');
  const axeSource = readBounded(axePath).toString('utf8');
  const profilePath = mkdtempSync(join(tmpdir(), 'raos-v2-browser-'));
  const server = await startServer();
  const remotePort = await reservePort();
  const browser = await launchBrowser(argumentsValue.browserExecutable, remotePort, profilePath);
  let connection = null;
  try {
    const debuggerUrl = await waitForDebugger(remotePort);
    connection = new CdpConnection(debuggerUrl);
    await connection.open();
    const networkUrls = [];
    connection.on('Network.requestWillBeSent', (event) => networkUrls.push(event.request.url));
    await connection.call('Page.enable');
    await connection.call('Runtime.enable');
    await connection.call('Network.enable');
    await connection.call('Accessibility.enable');

    const routeResults = {};
    const accessibilityRouteResults = {};
    const keyboardRouteResults = {};
    const mediaRouteResults = {};
    for (const route of ROUTES) {
      const viewportAudits = {};
      for (const viewport of VIEWPORTS) {
        await setViewport(connection, viewport);
        await navigate(connection, `${server.origin}${route}`);
        const basics = await auditBasics(connection);
        if (
          basics.h1Count !== 1 ||
          basics.horizontalOverflow ||
          basics.lang !== 'ja' ||
          !basics.disclosureVisible ||
          basics.focusableCount < 2
        ) {
          fail('ROUTE_VIEWPORT_SEMANTICS_INVALID');
        }
        const axe = await runAxe(connection, axeSource);
        if (axe.violations.length !== 0 || axe.incomplete.length !== 0) {
          fail(`AXE_UNRESOLVED_${route}_${viewport.name}`);
        }
        viewportAudits[viewport.name] = Object.freeze({
          axeIncomplete: axe.incomplete,
          axeViolations: 0,
          horizontalOverflow: false,
        });
      }

      await setViewport(connection, MOBILE_AUDIT_VIEWPORT);
      await navigate(connection, `${server.origin}${route}`);
      const accessibilityAudit = await auditAccessibilityTree(connection, route);
      accessibilityRouteResults[route] = accessibilityAudit;
      const keyboardAudit = await auditKeyboard(connection, route);
      keyboardRouteResults[route] = keyboardAudit;
      await navigate(connection, `${server.origin}${route}`);
      const mediaAudit = await auditZoomAndMedia(connection);
      if (
        mediaAudit.zoom.horizontalOverflow ||
        !mediaAudit.media.forcedColors ||
        !mediaAudit.media.reducedMotion ||
        mediaAudit.media.borderStyle === 'none' ||
        mediaAudit.media.transitionSeconds > 0.01
      ) {
        fail('ROUTE_REFLOW_OR_MEDIA_CONTRACT_INVALID');
      }
      mediaRouteResults[route] = mediaAudit;
      const routePrivacy = await auditPrivacy(connection);
      if (
        routePrivacy.cookies !== '' ||
        routePrivacy.databases !== 0 ||
        routePrivacy.localStorage !== 0 ||
        routePrivacy.serviceWorkers !== 0 ||
        routePrivacy.sessionStorage !== 0
      ) {
        fail('BROWSER_PERSISTENCE_PROHIBITED');
      }
      routeResults[route] = Object.freeze({
        axeIncomplete: [],
        axeViolations: 0,
        accessibility: accessibilityAudit,
        h1Count: 1,
        keyboard: keyboardAudit,
        mobileOverflow: false,
        viewportAudits: Object.freeze(viewportAudits),
      });
    }

    const viewportResults = Object.fromEntries(
      VIEWPORTS.map((viewport) => [
        viewport.name,
        Object.freeze({ axeRuns: ROUTES.length, horizontalOverflow: false, routes: ROUTES.length }),
      ]),
    );

    const javascriptDisabled = await auditJavascriptDisabledFallback(
      connection,
      server.origin,
    );
    await setViewport(connection, MOBILE_AUDIT_VIEWPORT);
    await navigate(connection, `${server.origin}/tools/carry-on-size-checker/`);
    const checker = await auditChecker(connection);
    await navigate(connection, `${server.origin}/tools/carry-on-size-checker/`);
    const checkerKeyboard = await auditCheckerKeyboard(connection);
    const keyboard = Object.freeze({
      checkerInteraction: checkerKeyboard,
      focusRingPx: Math.min(
        ...Object.values(keyboardRouteResults).map((row) => row.focusRingPx),
      ),
      focusTraversalAllRoutes: true,
      routes: ROUTES.length,
      routeResults: Object.freeze(keyboardRouteResults),
      skipLink: true,
      skipLinkAllRoutes: true,
    });
    const media = Object.freeze({
      media: Object.freeze({
        borderStyle: 'solid',
        forcedColors: true,
        reducedMotion: true,
        routes: ROUTES.length,
        transitionSeconds: 0,
      }),
      routeResults: Object.freeze(mediaRouteResults),
      zoom: Object.freeze({ fontSize: '32px', horizontalOverflow: false, routes: ROUTES.length }),
    });
    const accessibility = Object.freeze({
      fullAxTreeAllRoutes: true,
      routeResults: Object.freeze(accessibilityRouteResults),
      routes: ROUTES.length,
      screenReaderSmokeAllRoutes: true,
      unnamedInteractiveCount: 0,
    });
    const reflow = Object.freeze({
      cssViewportWidthPx: 320,
      equivalentSourceWidthPx: 1280,
      equivalentZoomPercent: 400,
      horizontalOverflow: false,
      routes: ROUTES.length,
      viewportName: 'reflow-320-equivalent-400pct',
    });

    const outbound = networkUrls.filter((value) => {
      const parsed = new URL(value);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:'
        ? parsed.origin !== server.origin
        : false;
    });
    if (outbound.length !== 0) fail('OUTBOUND_PAGE_REQUEST_PROHIBITED');

    const versionOutput = await new Promise((resolvePromise, rejectPromise) => {
      const child = spawn(browser.executable, ['--version'], {
        env: { LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', PATH: '/usr/bin:/bin' },
        stdio: ['ignore', 'pipe', 'ignore'],
      });
      let output = '';
      child.stdout.on('data', (chunk) => {
        output += String(chunk);
      });
      child.once('error', rejectPromise);
      child.once('exit', (code) =>
        code === 0 ? resolvePromise(output.trim()) : rejectPromise(new Error('VERSION_FAILED')),
      );
    });
    const evidence = Object.freeze({
      accessibility,
      browser: Object.freeze({
        executableSha256: await sha256File(browser.executable),
        version: versionOutput,
      }),
      checker,
      classification: 'PASSED_LOCAL',
      commandContract: COMMAND_CONTRACT,
      exitStatus: 0,
      externalActions: 'NOT_EXECUTED',
      harnessBytes: lstatSync(SCRIPT_PATH).size,
      harnessPath: HARNESS_PATH,
      harnessSha256: await sha256File(SCRIPT_PATH),
      javascriptDisabled,
      keyboard,
      media,
      network: Object.freeze({ outboundRequests: 0, requestCount: networkUrls.length }),
      runtime: Object.freeze({
        executableSha256: await sha256File(realpathSync(process.execPath)),
        nodeMajor: REQUIRED_NODE_MAJOR,
        nodeVersion: process.versions.node,
      }),
      persistence: Object.freeze({
        cookies: 0,
        indexedDatabases: 0,
        localStorageEntries: 0,
        serviceWorkers: 0,
        sessionStorageEntries: 0,
      }),
      previewDigests,
      reflow,
      routes: routeResults,
      schema: 'RAOS_V2_LOCAL_BROWSER_EVIDENCE_V1',
      transfer,
      viewports: viewportResults,
    });
    if (argumentsValue.outputPath !== null) writeEvidence(argumentsValue.outputPath, evidence);
    process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
  } finally {
    if (connection !== null) connection.close();
    browser.child.kill('SIGTERM');
    await server.close();
    rmSync(profilePath, { force: true, recursive: true });
  }
}

const invokedPath =
  process.argv[1] === undefined ? null : realpathSync(resolve(process.argv[1]));
if (invokedPath === SCRIPT_PATH) {
  main().catch((error) => {
    const code =
      error instanceof BrowserValidationError ? error.code : 'BROWSER_VALIDATION_UNEXPECTED';
    process.stderr.write(`${code}\n`);
    process.exitCode = 1;
  });
}
