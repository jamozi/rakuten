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
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

import {
  CdpConnection,
  ROOT,
  evaluate,
  launchBrowser,
  navigate,
  reservePort,
  setViewport,
  waitForDebugger,
} from './browser-validation.mjs';

const require = createRequire(import.meta.url);
const SCRIPT_PATH = realpathSync(fileURLToPath(import.meta.url));
const SCRIPT_RELATIVE = 'tests/raos_v2/phase3-local-validation.mjs';
const SUPPORT_HARNESS_PATH = join(ROOT, 'tests/raos_v2/browser-validation.mjs');
const SUPPORT_HARNESS_RELATIVE = 'tests/raos_v2/browser-validation.mjs';
const PREVIEW_RELATIVE = 'changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html';
const PREVIEW_PATH = join(ROOT, PREVIEW_RELATIVE);
const TARGET_ROUTE = '/carry-on-suitcase-comparison/';
const TARGET_CLASSIFICATION = 'LOCAL_WORDPRESS_ASSEMBLY_SIMULATION';
const PACKAGE_MARKER = 'RAOS_V2_A05_POST_CONTENT_V1';
const CONTENT_ENVELOPE = 'RAOS_V2_A05_ENVELOPE_V1';
const OFFICIAL_SOURCE_URLS = Object.freeze([
  'https://store.ace.jp/shop/g/g01471-02',
  'https://store.ace.jp/shop/g/g05721-04',
  'https://store.ace.jp/shop/g/g06316-01/',
]);
const COMMAND_CONTRACT = 'NODE24_LOCAL_CDP_AXE_PHASE3_WORDPRESS_ASSEMBLY_SANITIZED_RECEIPT_V1';
const RECEIPT_SCHEMA = 'RAOS_V2_PHASE3_LOCAL_BROWSER_EVIDENCE_V1';
const REQUIRED_NODE_MAJOR = 24;
const REQUIRED_AXE_VERSION = '4.12.1';
const LOOPBACK = '127.0.0.1';
const MAX_PREVIEW_BYTES = 2 * 1024 * 1024;
const OUTPUT_ROOT = join(ROOT, 'output/playwright');
const VIEWPORTS = Object.freeze([
  Object.freeze({ equivalentZoomPercent: 400, height: 800, name: 'reflow-320', width: 320 }),
  Object.freeze({ height: 844, name: 'mobile-390', width: 390 }),
  Object.freeze({ height: 1024, name: 'tablet-768', width: 768 }),
  Object.freeze({ height: 900, name: 'desktop-1440', width: 1440 }),
]);
const MOBILE_VIEWPORT = VIEWPORTS.find((viewport) => viewport.width === 390);
if (MOBILE_VIEWPORT === undefined) throw new Error('PHASE3_MOBILE_VIEWPORT_MISSING');

class Phase3LocalValidationError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
    this.name = 'Phase3LocalValidationError';
  }
}

function fail(code) {
  throw new Phase3LocalValidationError(code);
}

const SAFE_SYSTEM_ERROR_CODES = new Set([
  'EACCES',
  'EADDRINUSE',
  'EEXIST',
  'EIO',
  'EMFILE',
  'ENFILE',
  'ENOENT',
  'ENOSPC',
  'ENOTDIR',
  'EPERM',
  'EROFS',
]);

function classifiedErrorCode(error) {
  if (error instanceof Phase3LocalValidationError) return error.code;
  const candidate =
    error !== null && typeof error === 'object' && typeof error.code === 'string' ? error.code : '';
  if (error?.name === 'BrowserValidationError' && /^[A-Z0-9_]+$/u.test(candidate)) {
    return `PHASE3_SUPPORT_${candidate}`;
  }
  if (SAFE_SYSTEM_ERROR_CODES.has(candidate)) return `PHASE3_RUNTIME_${candidate}`;
  return 'PHASE3_LOCAL_VALIDATION_UNEXPECTED';
}

function parseArguments(argv) {
  let browserExecutable = null;
  let output = null;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = argv[index + 1] ?? null;
    if (argument === '--browser-executable' && browserExecutable === null && value !== null) {
      browserExecutable = value;
      index += 1;
      continue;
    }
    if (argument === '--output' && output === null && value !== null) {
      output = value;
      index += 1;
      continue;
    }
    fail('PHASE3_ARGUMENT_INVALID');
  }
  if (browserExecutable === null || !isAbsolute(browserExecutable)) {
    fail('PHASE3_BROWSER_EXECUTABLE_ABSOLUTE_REQUIRED');
  }
  if (output === null) fail('PHASE3_OUTPUT_REQUIRED');
  const outputPath = resolve(ROOT, output);
  const fromOutputRoot = relative(OUTPUT_ROOT, outputPath);
  if (
    fromOutputRoot === '' ||
    fromOutputRoot === '..' ||
    fromOutputRoot.startsWith(`..${sep}`) ||
    isAbsolute(fromOutputRoot) ||
    !outputPath.endsWith('.json')
  ) {
    fail('PHASE3_OUTPUT_PATH_INVALID');
  }
  const capturesDirectory = join(dirname(outputPath), `${basename(outputPath, '.json')}-captures`);
  return Object.freeze({ browserExecutable, capturesDirectory, outputPath });
}

function readPreview() {
  if (!existsSync(PREVIEW_PATH)) fail('PHASE3_ASSEMBLED_PREVIEW_MISSING');
  let information;
  let payload;
  try {
    information = lstatSync(PREVIEW_PATH);
    payload = readFileSync(PREVIEW_PATH);
  } catch {
    fail('PHASE3_ASSEMBLED_PREVIEW_UNREADABLE');
  }
  if (
    !information.isFile() ||
    information.isSymbolicLink() ||
    information.size <= 0 ||
    information.size > MAX_PREVIEW_BYTES
  ) {
    fail('PHASE3_ASSEMBLED_PREVIEW_INVALID');
  }
  return Object.freeze({ bytes: information.size, payload });
}

function loadAxeRuntime() {
  let axePath;
  let packagePath;
  try {
    axePath = require.resolve('axe-core/axe.min.js');
    packagePath = require.resolve('axe-core/package.json');
  } catch {
    fail('PHASE3_AXE_DEPENDENCY_UNAVAILABLE');
  }
  try {
    const axePackage = JSON.parse(readFileSync(packagePath, 'utf8'));
    if (axePackage.version !== REQUIRED_AXE_VERSION) fail('PHASE3_AXE_VERSION_INVALID');
    const source = readFileSync(axePath, 'utf8');
    if (source.length === 0) fail('PHASE3_AXE_DEPENDENCY_INVALID');
    return source;
  } catch (error) {
    if (error instanceof Phase3LocalValidationError) throw error;
    fail('PHASE3_AXE_DEPENDENCY_INVALID');
  }
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

function ensureSafeOutputDirectory(path) {
  const fromRoot = relative(ROOT, path);
  const parts = fromRoot.split(sep);
  if (
    isAbsolute(fromRoot) ||
    parts.length < 2 ||
    parts[0] !== 'output' ||
    parts[1] !== 'playwright' ||
    parts.includes('..')
  ) {
    fail('PHASE3_OUTPUT_DIRECTORY_INVALID');
  }
  let current = ROOT;
  for (const part of parts) {
    current = join(current, part);
    if (!existsSync(current)) {
      mkdirSync(current, { mode: 0o700 });
      continue;
    }
    const information = lstatSync(current);
    if (!information.isDirectory() || information.isSymbolicLink()) {
      fail('PHASE3_OUTPUT_DIRECTORY_INVALID');
    }
  }
  const outputRoot = realpathSync(OUTPUT_ROOT);
  const outputDirectory = realpathSync(path);
  const fromOutputRoot = relative(outputRoot, outputDirectory);
  if (
    fromOutputRoot === '..' ||
    fromOutputRoot.startsWith(`..${sep}`) ||
    isAbsolute(fromOutputRoot)
  ) {
    fail('PHASE3_OUTPUT_DIRECTORY_INVALID');
  }
}

function writeAtomic(path, value) {
  ensureSafeOutputDirectory(dirname(path));
  if (existsSync(path)) {
    const information = lstatSync(path);
    if (!information.isFile() || information.isSymbolicLink()) {
      fail('PHASE3_OUTPUT_FILE_INVALID');
    }
  }
  const temporary = `${path}.tmp-${process.pid}`;
  const descriptor = openSync(temporary, 'wx', 0o600);
  try {
    writeFileSync(descriptor, value);
  } finally {
    closeSync(descriptor);
  }
  renameSync(temporary, path);
}

function writeReceipt(path, value) {
  writeAtomic(path, `${JSON.stringify(value, null, 2)}\n`);
}

function pngDimensions(payload) {
  if (
    payload.length < 24 ||
    !payload.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
    payload.subarray(12, 16).toString('ascii') !== 'IHDR'
  ) {
    fail('PHASE3_SCREENSHOT_PNG_INVALID');
  }
  return Object.freeze({ height: payload.readUInt32BE(20), width: payload.readUInt32BE(16) });
}

function startPreviewServer(payload) {
  const requests = [];
  const server = createServer((request, response) => {
    try {
      const parsed = new URL(request.url ?? '/', `http://${LOOPBACK}`);
      requests.push(
        Object.freeze({ method: request.method ?? 'UNKNOWN', pathname: parsed.pathname }),
      );
      if (
        (request.method !== 'GET' && request.method !== 'HEAD') ||
        parsed.pathname !== TARGET_ROUTE ||
        parsed.search !== '' ||
        parsed.hash !== ''
      ) {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('not found');
        return;
      }
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Length': String(payload.length),
        'Content-Security-Policy':
          "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src 'none'; font-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
        'Content-Type': 'text/html; charset=utf-8',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
      });
      response.end(request.method === 'HEAD' ? undefined : payload);
    } catch {
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('closed failure');
    }
  });
  return new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, LOOPBACK, () => {
      const address = server.address();
      if (address === null || typeof address === 'string') {
        rejectPromise(new Phase3LocalValidationError('PHASE3_SERVER_ADDRESS_INVALID'));
        return;
      }
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

function dispatchKey(connection, code, key) {
  const codes = Object.freeze({ Enter: 13, Tab: 9 });
  const windowsVirtualKeyCode = codes[code] ?? 0;
  const text = code === 'Enter' ? '\r' : undefined;
  return connection
    .call('Input.dispatchKeyEvent', {
      code,
      key,
      text,
      type: 'keyDown',
      windowsVirtualKeyCode,
    })
    .then(() =>
      connection.call('Input.dispatchKeyEvent', {
        code,
        key,
        type: 'keyUp',
        windowsVirtualKeyCode,
      }),
    );
}

async function runAxe(connection, axeSource) {
  await evaluate(connection, `${axeSource}\ntrue`);
  return evaluate(
    connection,
    `axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] }
    }).then((result) => ({
      incomplete: result.incomplete
        .map((entry) => ({
          id: entry.id,
          targets: entry.nodes.flatMap((node) => node.target).slice(0, 3),
        }))
        .sort((left, right) => left.id.localeCompare(right.id)),
      violations: result.violations
        .map((entry) => ({
          id: entry.id,
          targets: entry.nodes.flatMap((node) => node.target).slice(0, 3),
        }))
        .sort((left, right) => left.id.localeCompare(right.id)),
    }))`,
  );
}

async function waitForStableLayout(connection, viewport) {
  const width = await evaluate(
    connection,
    `new Promise((resolvePromise) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolvePromise(window.innerWidth)));
    })`,
  );
  if (width !== viewport.width) fail(`PHASE3_CSS_VIEWPORT_INVALID_${viewport.width}`);
}

async function auditPage(connection, viewport) {
  const result = await evaluate(
    connection,
    `(() => {
      const visible = (node) => node !== null && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
      const wrapper = document.querySelector('.raos-v2-decision-support');
      const classification = document.querySelector('[data-raos-v2-classification="${TARGET_CLASSIFICATION}"]');
      const marker = document.querySelector('[data-raos-v2-package-marker="${PACKAGE_MARKER}"]');
      const envelopes = [...document.querySelectorAll('[data-raos-v2-post-content-envelope="${CONTENT_ENVELOPE}"]')];
      const envelope = envelopes.length === 1 ? envelopes[0] : null;
      const envelopeSubstantiveTextNodes = envelope === null
        ? []
        : [...envelope.childNodes].filter((node) => node.nodeType === Node.TEXT_NODE && (node.textContent ?? '').trim() !== '');
      const h1 = [...document.querySelectorAll('h1')];
      const entryTitles = [...document.querySelectorAll('h1.raos-v2-phase3-entry-title')];
      const ctas = [...document.querySelectorAll('[data-raos-v2-cta-state]')];
      const disabledButtons = [...document.querySelectorAll('[data-raos-v2-cta-state="BLOCKED"] button:disabled')];
      const resourceElements = [...document.querySelectorAll('img,script,iframe,object,embed,video,audio,source,link[rel~="stylesheet"],link[rel~="preload"],link[rel~="modulepreload"]')];
      const eventHandlers = [...document.querySelectorAll('*')].flatMap((node) =>
        [...node.attributes].filter((attribute) => attribute.name.toLowerCase().startsWith('on')),
      );
      const anchors = [...document.querySelectorAll('a[href]')];
      const affiliateAnchors = anchors.filter((anchor) => {
        const href = anchor.getAttribute('href') ?? '';
        const rel = (anchor.getAttribute('rel') ?? '').split(/\s+/u);
        return /rakuten|r10\.to|hb\.afl/iu.test(href) || rel.includes('sponsored');
      });
      const externalAnchors = anchors.filter((anchor) => {
        const href = anchor.getAttribute('href') ?? '';
        return !(href.startsWith('/') || href.startsWith('#'));
      });
      const externalAnchorHrefs = externalAnchors
        .map((anchor) => anchor.getAttribute('href') ?? '')
        .sort();
      const grid = document.querySelector('.raos-v2-decision-support__product-grid');
      const columns = grid === null ? [] : getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/u);
      const tableRegion = document.querySelector('.raos-v2-decision-support__table-scroll');
      const comparisonCards = [...document.querySelectorAll('.raos-v2-decision-support__comparison-card')];
      const minimumBlockedButtonHeight = disabledButtons.length === 0
        ? 0
        : Math.min(...disabledButtons.map((button) => button.getBoundingClientRect().height));
      return {
        affiliateAnchorCount: affiliateAnchors.length,
        blockedButtonCount: disabledButtons.length,
        blockedCtaCount: ctas.filter((cta) => cta.dataset.raosV2CtaState === 'BLOCKED').length,
        classificationCount: classification === null ? 0 : 1,
        disclosureVisible: visible(document.querySelector('.raos-v2-decision-support__disclosure')),
        documentHorizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
        entryTitleCount: entryTitles.length,
        envelopeCount: envelopes.length,
        envelopeOnlyContainsMarker: envelope !== null && envelope.children.length === 1 && envelope.firstElementChild === marker && envelopeSubstantiveTextNodes.length === 0,
        eventHandlerCount: eventHandlers.length,
        externalAnchorHrefs,
        gridColumnCount: columns.filter(Boolean).length,
        h1Count: h1.length,
        h1Visible: h1.length === 1 && visible(h1[0]),
        imageCount: document.images.length,
        inlineScriptCount: document.scripts.length,
        lang: document.documentElement.lang,
        mainCount: document.querySelectorAll('main#raos-v2-phase3-main[tabindex="-1"]').length,
        markerCount: marker === null ? 0 : 1,
        minimumBlockedButtonHeight,
        mobileComparisonCardCount: comparisonCards.filter(visible).length,
        resourceElementCount: resourceElements.length,
        resourceEntryCount: performance.getEntriesByType('resource').length,
        robots: document.querySelector('meta[name="robots"]')?.getAttribute('content') ?? '',
        skipLinkCount: document.querySelectorAll('a.raos-v2-phase3-skip[href="#raos-v2-phase3-main"]').length,
        tableContainedOverflow: tableRegion !== null && tableRegion.scrollWidth > tableRegion.clientWidth,
        tableVisible: visible(tableRegion),
        wrapperVisible: visible(wrapper),
      };
    })()`,
  );
  const expectedColumns = viewport.width >= 1440 ? 3 : 1;
  const mobileComparison = viewport.width <= 390;
  if (
    result.affiliateAnchorCount !== 0 ||
    result.blockedButtonCount !== 3 ||
    result.blockedCtaCount !== 3 ||
    result.classificationCount !== 1 ||
    !result.disclosureVisible ||
    result.documentHorizontalOverflow ||
    result.entryTitleCount !== 1 ||
    result.envelopeCount !== 1 ||
    !result.envelopeOnlyContainsMarker ||
    result.eventHandlerCount !== 0 ||
    JSON.stringify(result.externalAnchorHrefs) !== JSON.stringify(OFFICIAL_SOURCE_URLS) ||
    result.gridColumnCount !== expectedColumns ||
    result.h1Count !== 1 ||
    !result.h1Visible ||
    result.imageCount !== 0 ||
    result.inlineScriptCount !== 0 ||
    result.lang !== 'ja' ||
    result.mainCount !== 1 ||
    result.markerCount !== 1 ||
    result.minimumBlockedButtonHeight < 44 ||
    result.mobileComparisonCardCount !== (mobileComparison ? 4 : 0) ||
    result.resourceElementCount !== 0 ||
    result.resourceEntryCount !== 0 ||
    result.robots !== 'noindex,nofollow' ||
    result.skipLinkCount !== 1 ||
    result.tableVisible === mobileComparison ||
    !result.wrapperVisible
  ) {
    fail(`PHASE3_VIEWPORT_CONTRACT_INVALID_${viewport.width}`);
  }
  return Object.freeze({
    axeIncomplete: 0,
    axeViolations: 0,
    blockedCtas: 3,
    gridColumns: expectedColumns,
    height: viewport.height,
    horizontalOverflow: false,
    comparisonMode: mobileComparison ? 'CARDS' : 'TABLE',
    tableOverflowContained: mobileComparison ? null : result.tableContainedOverflow,
    width: viewport.width,
  });
}

async function captureFullPage(connection, viewport, capturesDirectory) {
  const metrics = await connection.call('Page.getLayoutMetrics');
  const content = metrics.cssContentSize;
  const height = Math.ceil(content?.height ?? 0);
  if (height < viewport.height || height > 20_000) {
    fail(`PHASE3_SCREENSHOT_HEIGHT_INVALID_${viewport.width}`);
  }
  const captured = await connection.call('Page.captureScreenshot', {
    captureBeyondViewport: true,
    clip: { height, scale: 1, width: viewport.width, x: 0, y: 0 },
    format: 'png',
    fromSurface: true,
  });
  if (typeof captured.data !== 'string') fail('PHASE3_SCREENSHOT_DATA_INVALID');
  const payload = Buffer.from(captured.data, 'base64');
  const dimensions = pngDimensions(payload);
  if (dimensions.width !== viewport.width || dimensions.height !== height) {
    fail(`PHASE3_SCREENSHOT_DIMENSIONS_INVALID_${viewport.width}`);
  }
  const path = join(capturesDirectory, `carry-on-suitcase-comparison__${viewport.width}.png`);
  writeAtomic(path, payload);
  return Object.freeze({
    bytes: payload.length,
    height,
    path: relative(ROOT, path),
    sha256: sha256Bytes(payload),
    width: viewport.width,
  });
}

async function auditAccessibilityTree(connection) {
  const tree = await connection.call('Accessibility.getFullAXTree');
  const nodes = Array.isArray(tree.nodes) ? tree.nodes.filter((node) => !node.ignored) : [];
  const value = (field) => (typeof field?.value === 'string' ? field.value : '');
  const interactiveRoles = new Set(['button', 'link']);
  let levelOneHeadings = 0;
  let unnamedInteractive = 0;
  const roles = {};
  const structuralRows = [];
  for (const node of nodes) {
    const role = value(node.role);
    const name = value(node.name).trim();
    const level = (node.properties ?? []).find((property) => property.name === 'level')?.value
      ?.value;
    roles[role] = (roles[role] ?? 0) + 1;
    if (role === 'heading' && level === 1) levelOneHeadings += 1;
    if (interactiveRoles.has(role) && name.length === 0) unnamedInteractive += 1;
    structuralRows.push([role, name, level ?? null]);
  }
  if (
    nodes.length < 20 ||
    roles.RootWebArea !== 1 ||
    (roles.banner ?? 0) < 1 ||
    (roles.main ?? 0) !== 1 ||
    (roles.contentinfo ?? 0) < 1 ||
    levelOneHeadings !== 1 ||
    unnamedInteractive !== 0
  ) {
    fail('PHASE3_ACCESSIBILITY_TREE_INVALID');
  }
  return Object.freeze({
    levelOneHeadings,
    nodeCount: nodes.length,
    screenReaderSmoke: true,
    structuralSha256: sha256Bytes(JSON.stringify(structuralRows)),
    unnamedInteractive,
  });
}

async function auditKeyboard(connection, url) {
  await navigate(connection, url);
  await evaluate(connection, 'document.activeElement?.blur(); window.scrollTo(0, 0); true');
  await dispatchKey(connection, 'Tab', 'Tab');
  const first = await evaluate(
    connection,
    `(() => {
      const node = document.activeElement;
      const style = getComputedStyle(node);
      return {
        isSkip: node?.matches?.('a.raos-v2-phase3-skip[href="#raos-v2-phase3-main"]') === true,
        outlineStyle: style.outlineStyle,
        outlineWidth: Number.parseFloat(style.outlineWidth) || 0,
      };
    })()`,
  );
  if (!first.isSkip || first.outlineStyle === 'none' || first.outlineWidth < 3) {
    fail('PHASE3_KEYBOARD_SKIP_LINK_INVALID');
  }
  await dispatchKey(connection, 'Enter', 'Enter');
  const mainFocused = await evaluate(
    connection,
    "location.hash === '#raos-v2-phase3-main' && document.activeElement?.id === 'raos-v2-phase3-main'",
  );
  if (!mainFocused) fail('PHASE3_KEYBOARD_SKIP_TARGET_INVALID');

  await navigate(connection, url);
  await evaluate(connection, 'document.activeElement?.blur(); window.scrollTo(0, 0); true');
  const descriptors = await evaluate(
    connection,
    `(() => {
      const selector = 'a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])';
      return [...document.querySelectorAll(selector)]
        .filter((node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden')
        .map((node) => [node.tagName, node.getAttribute('href') ?? '', node.id].join(':'));
    })()`,
  );
  if (descriptors.length < 3) fail('PHASE3_KEYBOARD_FOCUSABLE_SET_INVALID');
  const visited = new Set();
  let minimumOutline = Number.POSITIVE_INFINITY;
  const maximumSteps = descriptors.length * 2 + 4;
  for (let step = 0; step < maximumSteps && visited.size < descriptors.length; step += 1) {
    await dispatchKey(connection, 'Tab', 'Tab');
    const focus = await evaluate(
      connection,
      `(() => {
        const selector = 'a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])';
        const visible = [...document.querySelectorAll(selector)]
          .filter((node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden');
        const node = document.activeElement;
        const style = getComputedStyle(node);
        return {
          browserBoundary: node === document.body || node === document.documentElement,
          index: visible.indexOf(node),
          outlineStyle: style.outlineStyle,
          outlineWidth: Number.parseFloat(style.outlineWidth) || 0,
        };
      })()`,
    );
    if (focus.index < 0) {
      if (focus.browserBoundary) continue;
      fail('PHASE3_KEYBOARD_FOCUS_PATH_INVALID');
    }
    if (!visited.has(focus.index)) {
      if (focus.outlineStyle === 'none' || focus.outlineWidth < 3) {
        fail('PHASE3_KEYBOARD_FOCUS_NOT_VISIBLE');
      }
      minimumOutline = Math.min(minimumOutline, focus.outlineWidth);
      visited.add(focus.index);
    }
  }
  if (visited.size !== descriptors.length) fail('PHASE3_KEYBOARD_TRAVERSAL_INCOMPLETE');
  return Object.freeze({
    focusableCount: descriptors.length,
    focusRingMinimumPx: minimumOutline,
    focusTraversal: true,
    mainFocused: true,
    skipLinkFirst: true,
  });
}

async function auditZoomAndMedia(connection, url) {
  await navigate(connection, url);
  await evaluate(connection, "document.documentElement.style.fontSize = '200%'; true");
  const zoom = await evaluate(
    connection,
    `({
      fontSizePx: Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    })`,
  );
  await evaluate(connection, "document.documentElement.style.fontSize = ''; true");
  if (zoom.fontSizePx < 32 || zoom.horizontalOverflow) {
    fail('PHASE3_ZOOM_200_PERCENT_INVALID');
  }

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
      const target = document.querySelector('.raos-v2-decision-support__unknown');
      const targetStyle = getComputedStyle(target);
      const durations = [...document.querySelectorAll('.raos-v2-decision-support *')]
        .flatMap((node) => {
          const style = getComputedStyle(node);
          return [style.animationDuration, style.transitionDuration]
            .flatMap((value) => value.split(','))
            .map((value) => Number.parseFloat(value) || 0);
        });
      return {
        borderStyle: targetStyle.borderStyle,
        borderWidth: Number.parseFloat(targetStyle.borderWidth) || 0,
        forcedColors: matchMedia('(forced-colors: active)').matches,
        maximumMotionSeconds: Math.max(0, ...durations),
        reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
      };
    })()`,
  );
  await connection.call('Emulation.setEmulatedMedia', { features: [], media: '' });
  if (
    media.borderStyle === 'none' ||
    media.borderWidth < 1 ||
    !media.forcedColors ||
    media.maximumMotionSeconds > 0.01 ||
    !media.reducedMotion
  ) {
    fail('PHASE3_FORCED_COLORS_REDUCED_MOTION_INVALID');
  }
  return Object.freeze({
    forcedColors: true,
    maximumMotionSeconds: 0,
    reducedMotion: true,
    zoom200Percent: true,
  });
}

async function auditPersistence(connection) {
  const result = await evaluate(
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
  if (
    result.cookies !== '' ||
    result.databases !== 0 ||
    result.localStorage !== 0 ||
    result.serviceWorkers !== 0 ||
    result.sessionStorage !== 0
  ) {
    fail('PHASE3_BROWSER_PERSISTENCE_PROHIBITED');
  }
  return Object.freeze({
    cookies: 0,
    indexedDatabases: 0,
    localStorageEntries: 0,
    serviceWorkers: 0,
    sessionStorageEntries: 0,
  });
}

function browserVersion(executable) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(executable, ['--version'], {
      env: { LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', PATH: '/usr/bin:/bin' },
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    let value = '';
    child.stdout.on('data', (chunk) => {
      if (value.length < 1024) value += String(chunk);
    });
    child.once('error', () => {
      rejectPromise(new Phase3LocalValidationError('PHASE3_BROWSER_VERSION_UNAVAILABLE'));
    });
    child.once('exit', (code) => {
      if (code === 0 && value.trim().length > 0) resolvePromise(value.trim());
      else {
        rejectPromise(new Phase3LocalValidationError('PHASE3_BROWSER_VERSION_UNAVAILABLE'));
      }
    });
  });
}

async function stopBrowserProcess(browser) {
  const hasExited = () => browser.child.exitCode !== null || browser.child.signalCode !== null;
  if (hasExited()) return;
  let resolveExit;
  const exited = new Promise((resolvePromise) => {
    resolveExit = resolvePromise;
    browser.child.once('exit', resolvePromise);
  });
  browser.child.kill('SIGTERM');
  await Promise.race([exited, new Promise((resolvePromise) => setTimeout(resolvePromise, 2000))]);
  if (!hasExited()) {
    browser.child.kill('SIGKILL');
    await Promise.race([exited, new Promise((resolvePromise) => setTimeout(resolvePromise, 2000))]);
  }
  if (!hasExited()) {
    browser.child.removeListener('exit', resolveExit);
    fail('PHASE3_BROWSER_STOP_TIMEOUT');
  }
}

async function main() {
  if (realpathSync(process.cwd()) !== ROOT) fail('PHASE3_WORKSPACE_ROOT_REQUIRED');
  if (Number.parseInt(process.versions.node.split('.', 1)[0] ?? '', 10) !== REQUIRED_NODE_MAJOR) {
    fail('PHASE3_NODE_RUNTIME_MAJOR_INVALID');
  }
  const argumentsValue = parseArguments(process.argv.slice(2));
  const preview = readPreview();
  const axeSource = loadAxeRuntime();
  const profilePath = mkdtempSync(join(tmpdir(), 'raos-v2-phase3-browser-'));
  const server = await startPreviewServer(preview.payload);
  const remotePort = await reservePort();
  const browser = await launchBrowser(argumentsValue.browserExecutable, remotePort, profilePath);
  let connection = null;
  let browserStopped = false;
  let serverClosed = false;
  let profileRemoved = false;
  try {
    connection = new CdpConnection(await waitForDebugger(remotePort));
    await connection.open();
    const networkRequests = [];
    connection.on('Network.requestWillBeSent', (event) => {
      networkRequests.push(
        Object.freeze({ type: event.type ?? 'UNKNOWN', url: event.request?.url ?? '' }),
      );
    });
    await connection.call('Page.enable');
    await connection.call('Runtime.enable');
    await connection.call('Network.enable');
    await connection.call('Accessibility.enable');

    const url = `${server.origin}${TARGET_ROUTE}`;
    const viewportResults = {};
    for (const viewport of VIEWPORTS) {
      await setViewport(connection, viewport);
      await navigate(connection, url);
      await waitForStableLayout(connection, viewport);
      const page = await auditPage(connection, viewport);
      const axe = await runAxe(connection, axeSource);
      if (axe.violations.length !== 0 || axe.incomplete.length !== 0) {
        const identifiers = [
          ...axe.violations.map((entry) => entry.id),
          ...axe.incomplete.map((entry) => entry.id),
        ]
          .join('_')
          .replaceAll(/[^a-z0-9_-]+/giu, '_')
          .slice(0, 160);
        fail(`PHASE3_AXE_UNRESOLVED_${viewport.width}_${identifiers}`);
      }
      viewportResults[viewport.name] = page;
    }

    await setViewport(connection, MOBILE_VIEWPORT);
    await navigate(connection, url);
    const accessibility = await auditAccessibilityTree(connection);
    const keyboard = await auditKeyboard(connection, url);
    const media = await auditZoomAndMedia(connection, url);
    const persistence = await auditPersistence(connection);
    const visualCaptures = [];
    for (const viewport of VIEWPORTS.filter((item) => item.width !== 320)) {
      await setViewport(connection, viewport);
      await navigate(connection, url);
      await waitForStableLayout(connection, viewport);
      visualCaptures.push(
        await captureFullPage(connection, viewport, argumentsValue.capturesDirectory),
      );
    }

    const outboundRequests = networkRequests.filter((request) => {
      try {
        const parsed = new URL(request.url);
        return (
          (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
          parsed.origin !== server.origin
        );
      } catch {
        return true;
      }
    });
    const resourceRequests = networkRequests.filter(
      (request) => request.type !== 'Document' && request.url !== 'about:blank',
    );
    if (outboundRequests.length !== 0) fail('PHASE3_OUTBOUND_PAGE_REQUEST_PROHIBITED');
    if (resourceRequests.length !== 0) fail('PHASE3_PAGE_RESOURCE_REQUEST_PROHIBITED');
    if (
      server.requests.length === 0 ||
      server.requests.some(
        (request) => request.pathname !== TARGET_ROUTE || request.method !== 'GET',
      )
    ) {
      fail('PHASE3_SERVER_REQUEST_SCOPE_INVALID');
    }

    const executable = realpathSync(browser.executable);
    const receipt = Object.freeze({
      accessibility,
      assemblyClassification: TARGET_CLASSIFICATION,
      assertions: Object.freeze({
        affiliateUrls: 0,
        axeIncomplete: 0,
        axeRuns: VIEWPORTS.length,
        axeViolations: 0,
        blockedCtas: 3,
        externalResources: 0,
        h1Count: 1,
        horizontalOverflow: 0,
        images: 0,
        inlineScripts: 0,
        reflowEquivalentZoomPercent: 400,
        viewports: VIEWPORTS.map((viewport) => viewport.width),
      }),
      browser: Object.freeze({
        executableSha256: await sha256File(executable),
        version: await browserVersion(executable),
      }),
      classification: 'PASSED_LOCAL_ASSEMBLY_SIMULATION',
      commandContract: COMMAND_CONTRACT,
      externalActions: 'NOT_EXECUTED',
      harness: Object.freeze({
        bytes: lstatSync(SCRIPT_PATH).size,
        path: SCRIPT_RELATIVE,
        sha256: await sha256File(SCRIPT_PATH),
      }),
      keyboard,
      media,
      network: Object.freeze({ outboundRequests: 0, resourceRequests: 0 }),
      persistence,
      preview: Object.freeze({
        bytes: preview.bytes,
        path: PREVIEW_RELATIVE,
        sha256: sha256Bytes(preview.payload),
      }),
      publicEvidence: 'NOT_CLAIMED',
      runtime: Object.freeze({
        executableSha256: await sha256File(realpathSync(process.execPath)),
        nodeMajor: REQUIRED_NODE_MAJOR,
        nodeVersion: process.versions.node,
      }),
      schema: RECEIPT_SCHEMA,
      supportHarness: Object.freeze({
        bytes: lstatSync(SUPPORT_HARNESS_PATH).size,
        path: SUPPORT_HARNESS_RELATIVE,
        sha256: await sha256File(SUPPORT_HARNESS_PATH),
      }),
      targetRoute: TARGET_ROUTE,
      visualCaptures: Object.freeze(visualCaptures),
      visualReview: 'PENDING_SEPARATE_MANUAL_REVIEW',
      viewports: Object.freeze(viewportResults),
    });
    connection.close();
    connection = null;
    await stopBrowserProcess(browser);
    browserStopped = true;
    await server.close();
    serverClosed = true;
    rmSync(profilePath, { force: true, recursive: true });
    profileRemoved = true;
    writeReceipt(argumentsValue.outputPath, receipt);
    process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
  } finally {
    if (connection !== null) connection.close();
    if (!browserStopped) await stopBrowserProcess(browser);
    if (!serverClosed) await server.close();
    if (!profileRemoved) rmSync(profilePath, { force: true, recursive: true });
  }
}

const invokedPath = process.argv[1] === undefined ? null : realpathSync(resolve(process.argv[1]));
if (invokedPath === SCRIPT_PATH) {
  main().catch((error) => {
    process.stderr.write(`${classifiedErrorCode(error)}\n`);
    process.exitCode = 1;
  });
}
