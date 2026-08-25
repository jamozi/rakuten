#!/usr/bin/env node

import assert from 'node:assert/strict';
import { readFile, realpath, rm, mkdtemp } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const appDirectory = path.join(root, 'apps/web');
const routes = [
  ['/editorial-policy', '編集方針'],
  ['/affiliate-disclosure', '広告・Affiliate開示'],
  ['/privacy', 'Privacy Policy'],
  ['/about', '運営者・問い合わせ'],
];
const require = createRequire(import.meta.url);

function fail(code) {
  throw new Error(code);
}

function waitForLine(stream, pattern, timeoutMs) {
  return new Promise((resolvePromise, rejectPromise) => {
    let buffered = '';
    const timeout = setTimeout(() => {
      cleanup();
      rejectPromise(new Error('ST1001_CHROME_START_TIMEOUT'));
    }, timeoutMs);
    const onData = (chunk) => {
      buffered += chunk.toString('utf8');
      const match = buffered.match(pattern);
      if (match !== null) {
        cleanup();
        resolvePromise(match[1]);
      }
    };
    const cleanup = () => {
      clearTimeout(timeout);
      stream.off('data', onData);
    };
    stream.on('data', onData);
  });
}

class CdpConnection {
  constructor(url) {
    this.nextId = 1;
    this.pending = new Map();
    this.eventWaiters = new Map();
    this.socket = new WebSocket(url);
  }

  async open() {
    await new Promise((resolvePromise, rejectPromise) => {
      const timeout = setTimeout(() => rejectPromise(new Error('ST1001_CDP_OPEN_TIMEOUT')), 10_000);
      this.socket.addEventListener(
        'open',
        () => {
          clearTimeout(timeout);
          resolvePromise();
        },
        { once: true },
      );
      this.socket.addEventListener(
        'error',
        () => {
          clearTimeout(timeout);
          rejectPromise(new Error('ST1001_CDP_OPEN_FAILED'));
        },
        { once: true },
      );
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (typeof message.id === 'number') {
        const pending = this.pending.get(message.id);
        if (pending !== undefined) {
          this.pending.delete(message.id);
          if (message.error === undefined) {
            pending.resolve(message.result);
          } else {
            pending.reject(new Error('ST1001_CDP_COMMAND_FAILED'));
          }
        }
        return;
      }
      if (typeof message.method === 'string') {
        const waiters = this.eventWaiters.get(message.method) ?? [];
        this.eventWaiters.delete(message.method);
        for (const waiter of waiters) {
          waiter(message.params);
        }
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolvePromise, rejectPromise) => {
      this.pending.set(id, { resolve: resolvePromise, reject: rejectPromise });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  waitFor(method) {
    return new Promise((resolvePromise) => {
      const waiters = this.eventWaiters.get(method) ?? [];
      waiters.push(resolvePromise);
      this.eventWaiters.set(method, waiters);
    });
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(connection, expression) {
  const result = await connection.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    allowUnsafeEvalBlockedByCSP: true,
  });
  if (result.exceptionDetails !== undefined || result.result?.value === undefined) {
    fail('ST1001_BROWSER_EVALUATION_FAILED');
  }
  return result.result.value;
}

async function navigate(connection, url) {
  const loaded = connection.waitFor('Page.loadEventFired');
  await connection.send('Page.navigate', { url });
  await Promise.race([
    loaded,
    new Promise((_, rejectPromise) =>
      setTimeout(() => rejectPromise(new Error('ST1001_PAGE_LOAD_TIMEOUT')), 15_000),
    ),
  ]);
}

async function main() {
  if (process.argv.length !== 2) {
    return 2;
  }
  process.env.NEXT_TELEMETRY_DISABLED = '1';
  process.env.NODE_ENV = 'production';
  const next = (await import('next')).default;
  const application = next({ dev: false, dir: appDirectory, hostname: '127.0.0.1' });
  await application.prepare();
  const handler = application.getRequestHandler();
  const server = createServer((request, response) => handler(request, response));
  await new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, '127.0.0.1', resolvePromise);
  });
  const address = server.address();
  if (address === null || typeof address === 'string') {
    fail('ST1001_LOOPBACK_BIND_FAILED');
  }
  const baseUrl = `http://127.0.0.1:${address.port}`;
  let chrome;
  let profile;
  let connection;
  try {
    for (const [route, heading] of routes) {
      const response = await fetch(
        `${baseUrl}${route}?untrusted=%3Cscript%3Ecanary%3C%2Fscript%3E`,
        {
          redirect: 'manual',
        },
      );
      assert.equal(response.status, 200);
      assert.match(response.headers.get('content-type') ?? '', /^text\/html/);
      assert.equal(response.headers.get('x-frame-options'), 'DENY');
      assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
      assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
      assert.equal(response.headers.get('cross-origin-opener-policy'), 'same-origin');
      assert.match(response.headers.get('content-security-policy') ?? '', /script-src 'none'/);
      assert.match(response.headers.get('x-robots-tag') ?? '', /^noindex, nofollow/);
      assert.match(response.headers.get('cache-control') ?? '', /no-store/);
      assert.equal(response.headers.has('x-powered-by'), false);
      assert.equal(response.headers.has('set-cookie'), false);
      const html = await response.text();
      assert.match(html, /<html lang="ja">/);
      assert.equal((html.match(/<h1\b/g) ?? []).length, 1);
      assert.match(html, new RegExp(`<h1[^>]*>${heading}<\\/h1>`));
      for (const landmark of ['header', 'nav', 'main', 'article', 'aside', 'footer']) {
        assert.match(html, new RegExp(`<${landmark}\\b`));
      }
      assert.match(html, /href="#public-shell-main"/);
      assert.match(html, /name="robots" content="noindex, nofollow/);
      assert.doesNotMatch(html, /<script>canary/i);
      assert.doesNotMatch(html, /docs\/canonical|sourceRef|sourcePacket|rawPrompt/i);
      const visibleMarkup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
      assert.doesNotMatch(visibleMarkup, /canary|%3Cscript%3Ecanary/i);
      assert.doesNotMatch(visibleMarkup, /https?:\/\/(?!127\.0\.0\.1)/i);
    }

    const unknownRoute = await fetch(`${baseUrl}/not-a-public-policy-route`, {
      redirect: 'manual',
    });
    assert.equal(unknownRoute.status, 404);
    assert.equal(unknownRoute.headers.has('x-robots-tag'), false);
    assert.equal(unknownRoute.headers.has('content-security-policy'), false);

    profile = await mkdtemp(path.join(tmpdir(), 'raos-st1001-chrome-'));
    const chromePath = await realpath('/usr/bin/google-chrome');
    chrome = spawn(
      chromePath,
      [
        '--headless=new',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-networking',
        '--disable-component-update',
        '--disable-domain-reliability',
        '--disable-sync',
        '--metrics-recording-only',
        '--safebrowsing-disable-auto-update',
        '--remote-debugging-address=127.0.0.1',
        '--remote-debugging-port=0',
        `--user-data-dir=${profile}`,
        'about:blank',
      ],
      { stdio: ['ignore', 'ignore', 'pipe'] },
    );
    const browserSocket = await waitForLine(
      chrome.stderr,
      /(ws:\/\/127\.0\.0\.1:\d+\/devtools\/browser\/[a-z0-9-]+)/i,
      15_000,
    );
    const debugOrigin = browserSocket
      .replace(/^ws:/, 'http:')
      .replace(/\/devtools\/browser\/.+$/, '');
    const target = await fetch(
      `${debugOrigin}/json/new?${encodeURIComponent(`${baseUrl}/editorial-policy`)}`,
      { method: 'PUT' },
    ).then((response) => response.json());
    connection = new CdpConnection(target.webSocketDebuggerUrl);
    await connection.open();
    const requested = [];
    connection.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (message.method === 'Network.requestWillBeSent') {
        requested.push(message.params.request.url);
      }
    });
    await connection.send('Page.enable');
    await connection.send('Runtime.enable');
    await connection.send('Network.enable');
    await connection.send('Emulation.setDeviceMetricsOverride', {
      width: 320,
      height: 800,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await navigate(connection, `${baseUrl}/editorial-policy`);
    const summary = JSON.parse(
      await evaluate(
        connection,
        `JSON.stringify({
          lang: document.documentElement.lang,
          h1: [...document.querySelectorAll('h1')].map((node) => node.textContent),
          main: document.querySelectorAll('main').length,
          header: document.querySelectorAll('header.public-header').length,
          footer: document.querySelectorAll('footer.public-footer').length,
          skip: document.querySelector('.skip-link')?.getAttribute('href'),
          current: document.querySelector('[aria-current="page"]')?.textContent,
          overflow: document.documentElement.scrollWidth > window.innerWidth,
          preview: document.body.innerText.includes('公開前のローカル実装')
        })`,
      ),
    );
    assert.deepEqual(summary, {
      lang: 'ja',
      h1: ['編集方針'],
      main: 1,
      header: 1,
      footer: 1,
      skip: '#public-shell-main',
      current: '編集方針',
      overflow: false,
      preview: true,
    });
    assert.ok(requested.every((url) => url.startsWith(baseUrl) || url === 'about:blank'));

    await connection.send('Input.dispatchKeyEvent', {
      type: 'keyDown',
      key: 'Tab',
      code: 'Tab',
      windowsVirtualKeyCode: 9,
    });
    await connection.send('Input.dispatchKeyEvent', {
      type: 'keyUp',
      key: 'Tab',
      code: 'Tab',
      windowsVirtualKeyCode: 9,
    });
    const focusSummary = JSON.parse(
      await evaluate(
        connection,
        `JSON.stringify({
          className: document.activeElement?.className,
          outlineStyle: getComputedStyle(document.activeElement).outlineStyle,
          outlineWidth: getComputedStyle(document.activeElement).outlineWidth
        })`,
      ),
    );
    assert.equal(focusSummary.className, 'skip-link');
    assert.equal(focusSummary.outlineStyle, 'solid');
    assert.notEqual(focusSummary.outlineWidth, '0px');

    const axePath = require.resolve('axe-core/axe.min.js');
    const axePackage = JSON.parse(await readFile(require.resolve('axe-core/package.json'), 'utf8'));
    assert.equal(axePackage.version, '4.12.1');
    const axeSource = await readFile(axePath, 'utf8');
    await evaluate(connection, `${axeSource}\ntrue`);
    const axeSummary = JSON.parse(
      await evaluate(
        connection,
        `(async () => {
          const result = await axe.run(document, {
            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] }
          });
          return JSON.stringify({
            violations: result.violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.length })),
            incomplete: result.incomplete.map(({ id, nodes }) => ({
              id,
              nodes: nodes.map(({ html, failureSummary }) => ({ html, failureSummary }))
            }))
          });
        })()`,
      ),
    );
    assert.deepEqual(axeSummary.violations, []);
    assert.deepEqual(axeSummary.incomplete, []);
    process.stdout.write(
      `${JSON.stringify({
        status: 'PASS',
        routes: routes.length,
        viewportCssPixels: 320,
        keyboardFocusChecked: true,
        axeViolations: 0,
        axeIncomplete: 0,
        formalTst022: 'NOT_EXECUTED',
        formalTst023: 'NOT_EXECUTED',
      })}\n`,
    );
    return 0;
  } finally {
    connection?.close();
    if (chrome !== undefined) {
      chrome.kill('SIGTERM');
      await new Promise((resolvePromise) => {
        chrome.once('exit', resolvePromise);
        setTimeout(resolvePromise, 2_000);
      });
      if (chrome.exitCode === null) {
        chrome.kill('SIGKILL');
      }
    }
    if (profile !== undefined) {
      await rm(profile, { recursive: true, force: true });
    }
    await new Promise((resolvePromise) => server.close(resolvePromise));
    await application.close();
  }
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch(() => {
    process.stderr.write('ST-1001 local browser check failed\n');
    process.exitCode = 1;
  });
