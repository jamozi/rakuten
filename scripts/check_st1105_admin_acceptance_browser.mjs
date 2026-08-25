import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
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
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  createPublicationReviewWorkspaceV2,
  renderPublicationReviewWorkspaceHtmlV2,
} from '../packages/web-ui/src/publication-review-workspace-v2.ts';

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const ROOT = realpathSync(resolve(dirname(SCRIPT_PATH), '..'));
const CONTRACT_PATH = join(ROOT, 'changes/st-1105/contracts/admin-visual-browser-evidence.v2.json');
const ACCEPTANCE_PATH = join(
  ROOT,
  'changes/st-1105/generated/admin-visual-accessibility-recorded.v2.json',
);
const BASELINE_PATH = join(ROOT, 'changes/st-1105/baselines/admin-visual.synthetic.v2.json');
const EVIDENCE_PATH = join(ROOT, 'changes/st-1105/evidence/local-browser-automated.v2.json');
const LOOPBACK_HOST = '127.0.0.1';
const MAX_INPUT_BYTES = 8 * 1024 * 1024;
const MAX_PROCESS_OUTPUT_BYTES = 4 * 1024 * 1024;
const BROWSER_TIMEOUT_MS = 20_000;
const PAGE_TIMEOUT_MS = 15_000;

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
  let nodeModules = null;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--record' || argument === '--check') {
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
    if (argument === '--node-modules') {
      if (nodeModules !== null || index + 1 >= argv.length) {
        fail('ARGUMENT_NODE_MODULES_INVALID');
      }
      nodeModules = argv[index + 1];
      index += 1;
      continue;
    }
    fail('ARGUMENT_UNKNOWN');
  }
  if (mode === null) fail('ARGUMENT_MODE_REQUIRED');
  if (browserExecutable === null || !isAbsolute(browserExecutable)) {
    fail('ARGUMENT_BROWSER_REQUIRED');
  }
  if (nodeModules === null || !isAbsolute(nodeModules)) {
    fail('ARGUMENT_NODE_MODULES_REQUIRED');
  }
  return Object.freeze({ browserExecutable, mode, nodeModules });
}

function readBounded(path) {
  let info;
  try {
    info = lstatSync(path);
  } catch {
    fail('SOURCE_UNAVAILABLE');
  }
  if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || info.size > MAX_INPUT_BYTES) {
    fail('SOURCE_FILE_INVALID');
  }
  return readFileSync(path);
}

function parseJsonObject(bytes, failureCode) {
  let value;
  try {
    value = JSON.parse(bytes.toString('utf8'));
  } catch {
    fail(failureCode);
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail(failureCode);
  return value;
}

function mapping(value, code) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail(code);
  return value;
}

function array(value, code) {
  if (!Array.isArray(value)) fail(code);
  return value;
}

function string(value, code) {
  if (typeof value !== 'string' || value.length === 0 || value !== value.trim()) fail(code);
  return value;
}

function integer(value, code) {
  if (!Number.isSafeInteger(value)) fail(code);
  return value;
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

function resolveOwnedPath(relativePath) {
  if (
    typeof relativePath !== 'string' ||
    relativePath.length === 0 ||
    relativePath.includes('\0') ||
    isAbsolute(relativePath)
  ) {
    fail('SOURCE_PATH_INVALID');
  }
  const path = resolve(ROOT, relativePath);
  const fromRoot = relative(ROOT, path);
  if (fromRoot === '..' || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    fail('SOURCE_PATH_INVALID');
  }
  return path;
}

function loadInputs() {
  if (realpathSync(process.cwd()) !== ROOT) fail('WORKSPACE_ROOT_INVALID');
  if (process.versions.node !== '24.18.1') fail('NODE_VERSION_DRIFT');
  const contract = parseJsonObject(readBounded(CONTRACT_PATH), 'CONTRACT_INVALID');
  const acceptance = parseJsonObject(readBounded(ACCEPTANCE_PATH), 'ACCEPTANCE_INVALID');
  if (
    contract.schema_version !== 2 ||
    contract.story_id !== 'ST-1105' ||
    contract.classification !==
      'LOCAL_BROWSER_AUTOMATED_ADMIN_ACCESSIBILITY_VISUAL_EVIDENCE_NON_FORMAL_V2' ||
    acceptance.schema_version !== 2 ||
    acceptance.story_id !== 'ST-1105' ||
    acceptance.screen_count !== 44
  ) {
    fail('CONTRACT_IDENTITY_INVALID');
  }
  const screenOrder = array(acceptance.screen_order, 'SCREEN_ORDER_INVALID');
  const screens = array(acceptance.screens, 'SCREENS_INVALID');
  if (
    screenOrder.length !== 44 ||
    new Set(screenOrder).size !== 44 ||
    screens.length !== 44 ||
    screens.some(
      (screen, index) => mapping(screen, 'SCREEN_INVALID').screen_id !== screenOrder[index],
    )
  ) {
    fail('SCREEN_SCOPE_INVALID');
  }
  return { acceptance, contract };
}

async function validateToolchain(args, contract) {
  const browser = mapping(mapping(contract.runtime, 'RUNTIME_INVALID').browser, 'BROWSER_INVALID');
  const axe = mapping(contract.runtime.axe, 'AXE_INVALID');
  const browserInfo = lstatSync(args.browserExecutable);
  if (
    !browserInfo.isFile() ||
    browserInfo.isSymbolicLink() ||
    (browserInfo.mode & 0o111) === 0 ||
    (await sha256File(args.browserExecutable)) !== browser.executable_sha256
  ) {
    fail('BROWSER_EXECUTABLE_INVALID');
  }
  const axePath = resolve(
    args.nodeModules,
    string(axe.script_path_from_node_modules, 'AXE_INVALID'),
  );
  const fromModules = relative(args.nodeModules, axePath);
  if (fromModules === '..' || fromModules.startsWith(`..${sep}`) || isAbsolute(fromModules)) {
    fail('AXE_PATH_INVALID');
  }
  const axeBytes = readBounded(axePath);
  if (sha256Bytes(axeBytes) !== axe.script_sha256) fail('AXE_HASH_DRIFT');
  return axeBytes.toString('utf8');
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function syntheticHtml(screen, fixture) {
  const template = mapping(fixture.template, 'FIXTURE_TEMPLATE_INVALID');
  const workflows = array(screen.workflow_ids, 'SCREEN_WORKFLOWS_INVALID');
  const workflowLinks = workflows.length
    ? workflows
        .map(
          (workflowId) =>
            `<li><a id="workflow-${escapeHtml(workflowId)}" href="#workflow-summary">${escapeHtml(workflowId)}</a></li>`,
        )
        .join('')
    : '<li><a id="workflow-none" href="#workflow-summary">関連 workflow 未割当</a></li>';
  const rows = array(template.table_rows, 'FIXTURE_ROWS_INVALID')
    .map(
      (row) =>
        `<tr><th scope="row">${escapeHtml(row[0])}</th><td>${escapeHtml(
          row[1],
        )}</td><td>${escapeHtml(row[2])}</td></tr>`,
    )
    .join('');
  return `<!doctype html>
<html lang="ja-JP">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'none'; base-uri 'none'; object-src 'none'">
  <title>${escapeHtml(screen.screen_id)} ${escapeHtml(screen.name)} — ST-1105 local fixture</title>
  <style>
    :root{color-scheme:light;font:100%/1.55 Arial,sans-serif;--ink:#17202a;--soft:#f4f7fa;--line:#65798c;--accent:#005fcc;--danger:#8b1e16}*{box-sizing:border-box}html{background:#e7edf3;color:var(--ink)}body{margin:0;min-width:0}a{color:#004b9b}a:focus-visible,button:focus-visible,input:focus-visible,[tabindex]:focus-visible{outline:3px solid #005fcc;outline-offset:3px}.skip{position:absolute;top:-8rem;left:1rem;background:#17202a;color:#fff;padding:.8rem 1rem;z-index:20}.skip:focus{top:1rem}.shell{max-width:76rem;min-height:100vh;margin:auto;background:#fff}.top,main,footer{padding:clamp(1rem,3vw,2rem)}.top{border-bottom:2px solid var(--line)}h1{font-size:clamp(1.65rem,5vw,2.65rem);line-height:1.15;overflow-wrap:anywhere}code{overflow-wrap:anywhere;word-break:break-word}.status{border-left:.45rem solid var(--danger);background:#fff1ef;padding:.75rem;font-weight:700}.workflow-list{display:flex;flex-wrap:wrap;gap:.5rem 1rem;padding-left:1.25rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,19rem),1fr));gap:1rem}.panel{min-width:0;border:1px solid var(--line);padding:1rem;background:var(--soft)}label{display:block;font-weight:700}input,button{font:inherit;min-height:44px;padding:.6rem .8rem}input{max-width:100%;width:24rem}.instruction,.error{display:block;margin:.35rem 0}.error{color:var(--danger);font-weight:700}.table-scroll{max-width:100%;overflow-x:auto;border:1px solid var(--line)}table{border-collapse:collapse;min-width:36rem;width:100%}caption{text-align:left;font-weight:700;padding:.75rem}th,td{border:1px solid var(--line);padding:.6rem;text-align:left}dialog{max-width:min(32rem,calc(100% - 2rem));border:3px solid var(--ink);padding:1.25rem}dialog::backdrop{background:rgba(0,0,0,.55)}.actions{display:flex;flex-wrap:wrap;gap:.75rem}footer{border-top:1px solid var(--line)}@media(max-width:30rem){.top,main,footer{padding:1rem}table{min-width:34rem}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
  </style>
</head>
<body>
  <a id="skip-link" class="skip" href="#main">${escapeHtml(template.skip_link_text)}</a>
  <div class="shell">
    <header class="top">
      <p>ST-1105 · recorded synthetic · local only</p>
      <h1 id="page-title">${escapeHtml(screen.name)} <small>(${escapeHtml(screen.screen_id)})</small></h1>
      <p>${escapeHtml(screen.purpose)}</p>
      <p id="status" role="status" data-status-code="DISABLED" data-color-only="false" class="status"><span aria-hidden="true">⛔</span> ${escapeHtml(template.status_text)}</p>
      <nav aria-label="関連する critical workflow"><ul class="workflow-list">${workflowLinks}</ul></nav>
    </header>
    <main id="main" tabindex="-1" aria-labelledby="page-title">
      <section id="workflow-summary" aria-labelledby="workflow-heading">
        <h2 id="workflow-heading">Acceptance pattern</h2>
        <div class="grid">
          <form class="panel" action="javascript:void(0)" novalidate>
            <label for="filter">${escapeHtml(template.filter_label)} <span aria-hidden="true">*</span></label>
            <span id="filter-help" class="instruction">${escapeHtml(template.filter_instruction)}</span>
            <input id="filter" name="filter" required aria-required="true" aria-describedby="filter-help filter-error">
            <span id="filter-error" class="error">未入力の場合も外部送信されません。</span>
          </form>
          <section class="panel" aria-labelledby="boundary-title">
            <h2 id="boundary-title">Authority boundary</h2>
            <p>Catalog route: <code>${escapeHtml(screen.catalog_route)}</code></p>
            <p>Route registered: false · authentication: false · authorization: false.</p>
            <button id="dialog-open" type="button">${escapeHtml(template.dialog_open_label)}</button>
          </section>
        </div>
      </section>
      <section aria-labelledby="table-title">
        <h2 id="table-title">Semantic table pattern</h2>
        <div class="table-scroll" id="table-scroll" role="region" tabindex="0" aria-label="合成 table の横スクロール領域">
          <table>
            <caption>${escapeHtml(template.table_caption)}</caption>
            <thead><tr>${array(template.table_columns, 'FIXTURE_COLUMNS_INVALID')
              .map((column) => `<th scope="col">${escapeHtml(column)}</th>`)
              .join('')}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
    </main>
    <footer><a id="boundary-link" href="#status">安全境界へ戻る</a></footer>
  </div>
  <dialog id="review-dialog" aria-labelledby="dialog-title" aria-describedby="dialog-description">
    <h2 id="dialog-title">${escapeHtml(template.dialog_title)}</h2>
    <p id="dialog-description">${escapeHtml(template.dialog_description)}</p>
    <p id="disabled-reason">${escapeHtml(template.dialog_disabled_reason)}</p>
    <div class="actions">
      <button id="dialog-next" type="button">確認を続ける</button>
      <button id="dialog-close" type="button">${escapeHtml(template.dialog_cancel_label)}</button>
      <button id="dialog-disabled" type="button" disabled aria-describedby="disabled-reason">${escapeHtml(template.dialog_disabled_action_label)}</button>
    </div>
  </dialog>
  <script>
    (() => {
      const dialog = document.getElementById('review-dialog');
      const opener = document.getElementById('dialog-open');
      const next = document.getElementById('dialog-next');
      const close = document.getElementById('dialog-close');
      const closeDialog = () => { if (dialog.open) dialog.close(); opener.focus(); };
      opener.addEventListener('click', () => { dialog.showModal(); next.focus(); });
      next.addEventListener('click', () => close.focus());
      close.addEventListener('click', closeDialog);
      dialog.addEventListener('cancel', (event) => { event.preventDefault(); closeDialog(); });
      dialog.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        if (!event.shiftKey && document.activeElement === close) { event.preventDefault(); next.focus(); }
        if (event.shiftKey && document.activeElement === next) { event.preventDefault(); close.focus(); }
      });
    })();
  </script>
</body>
</html>`;
}

function dependencyHtml(screenId) {
  return renderPublicationReviewWorkspaceHtmlV2(createPublicationReviewWorkspaceV2({ screenId }));
}

async function startServer(acceptance) {
  const fixture = mapping(acceptance.fixture, 'FIXTURE_INVALID');
  const byId = new Map(
    array(acceptance.screens, 'SCREENS_INVALID').map((screen) => [screen.screen_id, screen]),
  );
  const server = createServer((request, response) => {
    try {
      if (request.method !== 'GET' || typeof request.url !== 'string') fail('HTTP_REQUEST_INVALID');
      const url = new URL(request.url, `http://${LOOPBACK_HOST}`);
      const syntheticMatch = url.pathname.match(/^\/_st1105\/synthetic\/([A-Z]+-[0-9]{3})$/u);
      const dependencyMatch = url.pathname.match(/^\/_st1105\/dependency\/([A-Z]+-[0-9]{3})$/u);
      let html = null;
      if (syntheticMatch !== null) {
        const screen = byId.get(syntheticMatch[1]);
        if (screen !== undefined) html = syntheticHtml(screen, fixture);
      } else if (dependencyMatch !== null) {
        html = dependencyHtml(dependencyMatch[1]);
      } else if (url.pathname === '/_st1105/ready') {
        html = '<!doctype html><html lang="en"><title>ready</title><body>ready</body></html>';
      }
      if (html === null) {
        response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
        response.end('not found');
        return;
      }
      response.writeHead(200, {
        'cache-control': 'no-store',
        'content-security-policy':
          "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
        'content-type': 'text/html; charset=utf-8',
        'x-content-type-options': 'nosniff',
      });
      response.end(html);
    } catch {
      response.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' });
      response.end('invalid');
    }
  });
  await new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, LOOPBACK_HOST, resolvePromise);
  });
  const address = server.address();
  if (address === null || typeof address === 'string') fail('LOOPBACK_PORT_INVALID');
  return { origin: `http://${LOOPBACK_HOST}:${String(address.port)}`, server };
}

async function stopServer(server) {
  await new Promise((resolvePromise, rejectPromise) => {
    server.close((error) => (error ? rejectPromise(error) : resolvePromise()));
  });
}

function captureOutput(child) {
  let stderr = '';
  let overflow = false;
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => {
    if (stderr.length + chunk.length > MAX_PROCESS_OUTPUT_BYTES) overflow = true;
    else stderr += chunk;
  });
  return {
    get stderr() {
      return stderr;
    },
    get overflow() {
      return overflow;
    },
  };
}

async function waitForDevTools(child, output) {
  const deadline = Date.now() + BROWSER_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || output.overflow) fail('BROWSER_START_FAILED');
    const match = output.stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/u);
    if (match !== null) return match[1];
    await sleep(25);
  }
  fail('BROWSER_START_TIMEOUT');
}

async function stopChild(child) {
  if (child.exitCode !== null) return;
  child.kill('SIGTERM');
  const deadline = Date.now() + 3_000;
  while (child.exitCode === null && Date.now() < deadline) await sleep(25);
  if (child.exitCode === null) child.kill('SIGKILL');
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
      if ((await evaluate(connection, 'document.readyState')) === 'complete') {
        await sleep(50);
        return;
      }
    } catch (error) {
      if (!(error instanceof ClosedFailure) || error.code !== 'CDP_COMMAND_FAILED') throw error;
    }
    await sleep(25);
  }
  fail('PAGE_READY_TIMEOUT');
}

async function pressKey(connection, key, code, modifiers = 0) {
  const virtualKeys = { ' ': 32, Enter: 13, Escape: 27, Tab: 9 };
  await connection.call('Input.dispatchKeyEvent', {
    code,
    key,
    modifiers,
    type: 'keyDown',
    windowsVirtualKeyCode: virtualKeys[key],
  });
  await connection.call('Input.dispatchKeyEvent', {
    code,
    key,
    modifiers,
    type: 'keyUp',
    windowsVirtualKeyCode: virtualKeys[key],
  });
}

async function navigate(connection, state, origin, path, viewport) {
  state.consoleErrors = 0;
  state.pageErrors = 0;
  state.documentStatus = null;
  state.currentUrl = `${origin}${path}`;
  await connection.call('Emulation.setDeviceMetricsOverride', {
    deviceScaleFactor: 1,
    height: viewport.height,
    mobile: false,
    screenHeight: viewport.height,
    screenWidth: viewport.width,
    width: viewport.width,
  });
  const result = await connection.call('Page.navigate', { url: state.currentUrl });
  if (result.errorText !== undefined) fail('PAGE_NAVIGATION_FAILED');
  await waitForDocument(connection);
  if (state.documentStatus !== 200) fail('PAGE_STATUS_INVALID');
  if (state.consoleErrors !== 0 || state.pageErrors !== 0) fail('PAGE_RUNTIME_ERROR');
  if (state.unexpectedRequests !== 0) fail('UNEXPECTED_OUTBOUND_REQUEST');
}

function validateBasics(value, findingsAllowed = false) {
  const basics = mapping(value, 'PAGE_BASICS_INVALID');
  if (
    typeof basics.title !== 'string' ||
    basics.title.trim().length === 0 ||
    basics.h1Count !== 1 ||
    basics.mainCount !== 1 ||
    typeof basics.language !== 'string' ||
    !basics.language.toLowerCase().startsWith('ja') ||
    !Number.isSafeInteger(basics.documentClientWidth) ||
    !Number.isSafeInteger(basics.documentScrollWidth) ||
    (!findingsAllowed && basics.documentScrollWidth - basics.documentClientWidth > 1)
  ) {
    fail('PAGE_SEMANTICS_INVALID');
  }
  return {
    document_overflow_css_px: basics.documentScrollWidth - basics.documentClientWidth,
    h1_count: basics.h1Count,
    language: basics.language,
    main_count: basics.mainCount,
    title: basics.title,
  };
}

async function basics(connection, findingsAllowed = false) {
  return validateBasics(
    await evaluate(
      connection,
      `({documentClientWidth:document.documentElement.clientWidth,documentScrollWidth:document.documentElement.scrollWidth,h1Count:document.querySelectorAll('h1').length,language:document.documentElement.lang,mainCount:document.querySelectorAll('main').length,title:document.title})`,
    ),
    findingsAllowed,
  );
}

async function runAxe(connection, source, tags, findingsAllowed = false) {
  await connection.call('Runtime.evaluate', { expression: source });
  const result = mapping(
    await evaluate(
      connection,
      `axe.run(document,{runOnly:{type:'tag',values:${JSON.stringify(tags)}}}).then(result=>({incomplete:result.incomplete.map(item=>({id:item.id,node_count:item.nodes.length})).sort((a,b)=>a.id.localeCompare(b.id)),passes:result.passes.length,violations:result.violations.map(item=>({id:item.id,impact:item.impact,node_count:item.nodes.length})).sort((a,b)=>a.id.localeCompare(b.id))}))`,
    ),
    'AXE_RESULT_INVALID',
  );
  const violationCount = array(result.violations, 'AXE_RESULT_INVALID').length;
  const incompleteCount = array(result.incomplete, 'AXE_RESULT_INVALID').length;
  if (!findingsAllowed && violationCount !== 0) fail('AXE_VIOLATION_PRESENT');
  if (!findingsAllowed && incompleteCount !== 0) fail('AXE_INCOMPLETE_PRESENT');
  return {
    incomplete: result.incomplete,
    pass_rule_count: integer(result.passes, 'AXE_RESULT_INVALID'),
    violations: result.violations,
  };
}

async function checkSkipLink(connection) {
  await evaluate(
    connection,
    `document.body.setAttribute('tabindex','-1');document.body.focus();true`,
  );
  await pressKey(connection, 'Tab', 'Tab');
  const first = mapping(
    await evaluate(
      connection,
      `(()=>{const a=document.activeElement;const s=getComputedStyle(a);const b=a.getBoundingClientRect();return{id:a.id,href:a.getAttribute('href'),visible:b.width>0&&b.height>0&&b.bottom>=0&&b.top<=innerHeight,outline:s.outlineStyle!=='none'&&s.outlineWidth!=='0px'}})()`,
    ),
    'SKIP_LINK_INVALID',
  );
  if (first.href === null || !/^#[A-Za-z][A-Za-z0-9_-]*$/u.test(first.href)) {
    fail('SKIP_LINK_INVALID');
  }
  if (first.visible !== true || first.outline !== true) fail('FOCUS_INDICATOR_INVALID');
  await pressKey(connection, 'Enter', 'Enter');
  await sleep(25);
  const targetReached = await evaluate(
    connection,
    `(()=>{const target=document.querySelector(${JSON.stringify(first.href)});return target!==null&&(document.activeElement===target||location.hash===${JSON.stringify(first.href)})})()`,
  );
  if (targetReached !== true) fail('SKIP_LINK_TARGET_INVALID');
  return { first_focus_id: first.id, focus_indicator_visible: true, target_reached: true };
}

async function checkTabReachability(connection) {
  const count = await evaluate(
    connection,
    `(()=>{const q='a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';const items=[...document.querySelectorAll(q)].filter(e=>{const s=getComputedStyle(e);const b=e.getBoundingClientRect();return s.visibility!=='hidden'&&s.display!=='none'&&b.width>0&&b.height>0});items.forEach((e,i)=>e.dataset.st1105Focus=String(i));return items.length})()`,
  );
  if (!Number.isSafeInteger(count) || count < 2 || count > 80) fail('FOCUSABLE_INVENTORY_INVALID');
  await evaluate(
    connection,
    `document.body.setAttribute('tabindex','-1');document.body.focus();true`,
  );
  const observed = new Set();
  for (let index = 0; index < count + 2; index += 1) {
    await pressKey(connection, 'Tab', 'Tab');
    const value = await evaluate(connection, 'document.activeElement?.dataset?.st1105Focus??null');
    if (value !== null) observed.add(value);
  }
  if (observed.size !== count) fail('FOCUSABLE_NOT_TAB_REACHABLE');
  return { enabled_focusable_count: count, tab_reached_count: observed.size };
}

async function checkSyntheticSemantics(connection) {
  const result = mapping(
    await evaluate(
      connection,
      `(()=>{const status=document.querySelector('[role="status"]');const input=document.getElementById('filter');const table=document.querySelector('table');return{statusText:status?.textContent?.trim()??'',statusCode:status?.dataset?.statusCode??null,colorOnly:status?.dataset?.colorOnly??null,labelled:input?.labels?.length===1,describedBy:input?.getAttribute('aria-describedby')==='filter-help filter-error',caption:table?.querySelectorAll(':scope>caption').length===1,columnScopes:[...table.querySelectorAll('thead th')].every(th=>th.getAttribute('scope')==='col'),rowScopes:[...table.querySelectorAll('tbody th')].every(th=>th.getAttribute('scope')==='row')}})()`,
    ),
    'SYNTHETIC_SEMANTICS_INVALID',
  );
  if (
    result.statusText.length === 0 ||
    result.statusCode !== 'DISABLED' ||
    result.colorOnly !== 'false' ||
    result.labelled !== true ||
    result.describedBy !== true ||
    result.caption !== true ||
    result.columnScopes !== true ||
    result.rowScopes !== true
  ) {
    fail('SYNTHETIC_SEMANTICS_INVALID');
  }
  return {
    form_associations: true,
    status_not_color_only: true,
    table_semantics: true,
  };
}

async function checkDialog(connection) {
  await evaluate(connection, `document.getElementById('dialog-open').focus();true`);
  await pressKey(connection, ' ', 'Space');
  await sleep(25);
  const initialDialogState = await evaluate(
    connection,
    `({active:document.activeElement?.id,open:document.getElementById('review-dialog').open})`,
  );
  if (initialDialogState.active !== 'dialog-next') {
    fail('DIALOG_INITIAL_FOCUS_INVALID');
  }
  await pressKey(connection, 'Tab', 'Tab');
  if ((await evaluate(connection, `document.activeElement?.id`)) !== 'dialog-close') {
    fail('DIALOG_FOCUS_ORDER_INVALID');
  }
  await pressKey(connection, 'Tab', 'Tab');
  if ((await evaluate(connection, `document.activeElement?.id`)) !== 'dialog-next') {
    fail('DIALOG_FORWARD_TRAP_INVALID');
  }
  await pressKey(connection, 'Tab', 'Tab', 8);
  if ((await evaluate(connection, `document.activeElement?.id`)) !== 'dialog-close') {
    fail('DIALOG_REVERSE_TRAP_INVALID');
  }
  await pressKey(connection, 'Escape', 'Escape');
  await sleep(25);
  const closed = await evaluate(
    connection,
    `!document.getElementById('review-dialog').open&&document.activeElement?.id==='dialog-open'`,
  );
  if (closed !== true) fail('DIALOG_ESCAPE_RETURN_INVALID');
  return { escape_closes: true, focus_trapped: true, focus_returned: true };
}

async function screenshotDigest(connection) {
  const result = await connection.call('Page.captureScreenshot', {
    captureBeyondViewport: false,
    format: 'png',
    fromSurface: true,
  });
  if (typeof result.data !== 'string' || result.data.length === 0) fail('SCREENSHOT_INVALID');
  const bytes = Buffer.from(result.data, 'base64');
  if (bytes.length < 100 || !bytes.subarray(1, 4).equals(Buffer.from('PNG'))) {
    fail('SCREENSHOT_INVALID');
  }
  return { bytes: bytes.length, sha256: sha256Bytes(bytes) };
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

async function audit(connection, acceptance, contract, origin, axeSource) {
  const state = {
    consoleErrors: 0,
    currentUrl: null,
    documentStatus: null,
    pageErrors: 0,
    unexpectedRequests: 0,
  };
  connection.on('Network.requestWillBeSent', ({ request }) => {
    if (request && typeof request.url === 'string') {
      try {
        assertLoopbackRequest(request.url, origin);
      } catch {
        state.unexpectedRequests += 1;
      }
    }
  });
  connection.on('Network.responseReceived', ({ response, type }) => {
    if (
      type === 'Document' &&
      response &&
      response.url === state.currentUrl &&
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
  const viewports = array(contract.viewport_profiles, 'VIEWPORTS_INVALID');
  const reflow = mapping(
    viewports.find((item) => item.id === 'REFLOW_320'),
    'VIEWPORT_INVALID',
  );
  const desktop = mapping(
    viewports.find((item) => item.id === 'VISUAL_DESKTOP_1280'),
    'VIEWPORT_INVALID',
  );
  const tags = array(contract.runtime.axe.tags, 'AXE_TAGS_INVALID');
  const results = [];
  const titles = new Set();
  const baseline = [];
  for (const screen of acceptance.screens) {
    const screenId = screen.screen_id;
    const path = `/_st1105/synthetic/${screenId}`;
    await navigate(connection, state, origin, path, desktop);
    const desktopBasics = await basics(connection);
    const axe = await runAxe(connection, axeSource, tags);
    const screenshot = await screenshotDigest(connection);
    baseline.push({ screen_id: screenId, ...screenshot });
    await navigate(connection, state, origin, path, reflow);
    const reflowBasics = await basics(connection);
    const semantics = await checkSyntheticSemantics(connection);
    const keyboard = await checkTabReachability(connection);
    const skip = await checkSkipLink(connection);
    const dialog = screen.critical_action === true ? await checkDialog(connection) : null;
    if (titles.has(reflowBasics.title)) fail('PAGE_TITLE_DUPLICATE');
    titles.add(reflowBasics.title);
    results.push({
      axe,
      browser_surface: 'SYNTHETIC_ACCEPTANCE_FIXTURE_ONLY',
      critical_dialog: dialog,
      desktop: desktopBasics,
      keyboard,
      reflow_320: reflowBasics,
      screen_id: screenId,
      semantics,
      skip_link: skip,
    });
  }
  const dependencyResults = [];
  for (const screenId of contract.surfaces.dependency_renderer.screen_ids) {
    const path = `/_st1105/dependency/${screenId}`;
    await navigate(connection, state, origin, path, desktop);
    const axe = await runAxe(connection, axeSource, tags, true);
    await navigate(connection, state, origin, path, reflow);
    dependencyResults.push({
      axe,
      browser_surface: 'ST0906_DEPENDENCY_RENDERER_ROUTE_UNREGISTERED',
      keyboard: await checkTabReachability(connection),
      reflow_320: await basics(connection, true),
      screen_id: screenId,
      skip_link: await checkSkipLink(connection),
    });
  }
  return { baseline, dependencyResults, results };
}

async function launchBrowser(args, contract, acceptance, origin, axeSource) {
  const profile = mkdtempSync(join(tmpdir(), 'raos-st1105-browser-'));
  const child = spawn(
    args.browserExecutable,
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
      env: {
        LANG: 'C.UTF-8',
        LC_ALL: 'C.UTF-8',
        PATH: `${dirname(process.execPath)}:/usr/bin:/bin`,
      },
      stdio: ['ignore', 'ignore', 'pipe'],
    },
  );
  const output = captureOutput(child);
  let connection = null;
  try {
    const browserUrl = await waitForDevTools(child, output);
    const endpoint = new URL(browserUrl);
    if (![LOOPBACK_HOST, 'localhost'].includes(endpoint.hostname)) {
      fail('BROWSER_DEBUG_ORIGIN_INVALID');
    }
    const browserConnection = new CdpConnection(browserUrl);
    await browserConnection.open();
    const version = await browserConnection.call('Browser.getVersion');
    if (version.product !== `Chrome/${contract.runtime.browser.version}`) {
      fail('BROWSER_VERSION_DRIFT');
    }
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
    connection = new CdpConnection(string(target.webSocketDebuggerUrl, 'BROWSER_TARGET_INVALID'));
    await connection.open();
    return await audit(connection, acceptance, contract, origin, axeSource);
  } finally {
    connection?.close();
    await stopChild(child);
    const prefix = `${tmpdir()}${sep}raos-st1105-browser-`;
    if (!profile.startsWith(prefix)) fail('BROWSER_PROFILE_INVALID');
    rmSync(profile, { force: true, recursive: true });
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
  return Buffer.from(`${JSON.stringify(sortJson(value), null, 2)}\n`, 'utf8');
}

async function sourceArtifacts(contract) {
  const values = [];
  for (const relativePath of array(contract.inputs, 'CONTRACT_INPUTS_INVALID')) {
    const path = resolveOwnedPath(relativePath);
    const bytes = readBounded(path);
    values.push({ bytes: bytes.length, path: relativePath, sha256: sha256Bytes(bytes) });
  }
  return values;
}

function writeAtomic(path, bytes) {
  mkdirSync(dirname(path), { mode: 0o755, recursive: true });
  if (existsSync(path) && lstatSync(path).isSymbolicLink()) fail('OUTPUT_PATH_INVALID');
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

function compareOrWrite(mode, path, bytes, missingCode, driftCode) {
  if (mode === 'record') {
    writeAtomic(path, bytes);
    return;
  }
  if (!existsSync(path)) fail(missingCode);
  if (!readBounded(path).equals(bytes)) fail(driftCode);
}

async function execute(argv) {
  const args = parseArguments(argv);
  const { acceptance, contract } = loadInputs();
  const axeSource = await validateToolchain(args, contract);
  const artifacts = await sourceArtifacts(contract);
  const server = await startServer(acceptance);
  try {
    const observed = await launchBrowser(args, contract, acceptance, server.origin, axeSource);
    const baseline = {
      algorithm: contract.visual_baseline.algorithm,
      approved: false,
      browser: contract.runtime.browser,
      classification: 'LOCAL_SYNTHETIC_VISUAL_BASELINE_DIGESTS_NON_FORMAL_V2',
      formal_TST_025: 'NOT_EXECUTED',
      profile: contract.visual_baseline.profile,
      schema_version: 2,
      screenshots: observed.baseline,
      story_id: 'ST-1105',
      tolerance: contract.visual_baseline.tolerance,
    };
    const baselineBytes = encodeJson(baseline);
    compareOrWrite(
      args.mode,
      BASELINE_PATH,
      baselineBytes,
      'BASELINE_MISSING',
      'VISUAL_BASELINE_DRIFT',
    );
    const dependencyFindingsPresent = observed.dependencyResults.some(
      (screen) =>
        screen.axe.incomplete.length !== 0 ||
        screen.axe.violations.length !== 0 ||
        screen.reflow_320.document_overflow_css_px > 1,
    );
    const evidence = {
      authority: contract.authority,
      classification: contract.classification,
      dependency_renderer: {
        result: dependencyFindingsPresent
          ? 'LOCAL_AUTOMATED_REVIEW_REQUIRED_DEPENDENCY_RENDERER_ONLY'
          : 'LOCAL_AUTOMATED_PASS_DEPENDENCY_RENDERER_ONLY',
        screens: observed.dependencyResults,
      },
      formal_boundary: contract.formal_boundary,
      local_zoom_check: contract.zoom_proxy,
      runtime: {
        axe: contract.runtime.axe,
        browser: contract.runtime.browser,
        environment: 'LOCAL_ENV_DEV_NON_FORMAL',
        network: 'LOOPBACK_ONLY',
        node: contract.runtime.node,
      },
      schema_version: 2,
      source_artifacts: artifacts,
      source_bundle_sha256: sha256Bytes(encodeJson(artifacts)),
      story_id: 'ST-1105',
      synthetic_fixture: {
        result: 'LOCAL_AUTOMATED_PASS_SYNTHETIC_FIXTURE_ONLY',
        screen_count: observed.results.length,
        screens: observed.results,
      },
      visual_baseline: {
        approved: false,
        formal_TST_025: 'NOT_EXECUTED',
        path: relative(ROOT, BASELINE_PATH),
        sha256: sha256Bytes(baselineBytes),
      },
      wcag_conformance: 'NOT_CLAIMED',
    };
    const evidenceBytes = encodeJson(evidence);
    compareOrWrite(args.mode, EVIDENCE_PATH, evidenceBytes, 'EVIDENCE_MISSING', 'EVIDENCE_DRIFT');
    return args.mode === 'record'
      ? 'ST1105_LOCAL_BROWSER_BASELINE_AND_EVIDENCE_RECORDED'
      : 'ST1105_LOCAL_BROWSER_BASELINE_AND_EVIDENCE_CHECKED';
  } finally {
    await stopServer(server.server);
  }
}

export { ClosedFailure, encodeJson, parseArguments, sortJson, syntheticHtml };

if (process.argv[1] !== undefined && realpathSync(process.argv[1]) === realpathSync(SCRIPT_PATH)) {
  try {
    process.stdout.write(`${await execute(process.argv.slice(2))}\n`);
  } catch (error) {
    const code = error instanceof ClosedFailure ? error.code : 'ST1105_BROWSER_RUN_FAILED';
    process.stderr.write(`${code}\n`);
    process.exitCode = 1;
  }
}
