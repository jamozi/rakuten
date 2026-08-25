#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile, realpath, rm, mkdtemp } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const appDirectory = path.join(root, 'apps/web');
const articlePath = '/articles/synthetic-recorded-policy-seo';
const require = createRequire(import.meta.url);

function fail(code) {
  throw new Error(code);
}

function waitForLine(stream, pattern, timeoutMs) {
  return new Promise((resolvePromise, rejectPromise) => {
    let buffered = '';
    const timeout = setTimeout(() => {
      cleanup();
      rejectPromise(new Error('ST1002_CHROME_START_TIMEOUT'));
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
      const timeout = setTimeout(() => rejectPromise(new Error('ST1002_CDP_OPEN_TIMEOUT')), 10_000);
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
          rejectPromise(new Error('ST1002_CDP_OPEN_FAILED'));
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
          if (message.error === undefined) pending.resolve(message.result);
          else pending.reject(new Error('ST1002_CDP_COMMAND_FAILED'));
        }
      } else if (typeof message.method === 'string') {
        const waiters = this.eventWaiters.get(message.method) ?? [];
        this.eventWaiters.delete(message.method);
        for (const waiter of waiters) waiter(message.params);
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
    fail('ST1002_BROWSER_EVALUATION_FAILED');
  }
  return result.result.value;
}

async function navigate(connection, url) {
  const loaded = connection.waitFor('Page.loadEventFired');
  await connection.send('Page.navigate', { url });
  await Promise.race([
    loaded,
    new Promise((_, rejectPromise) =>
      setTimeout(() => rejectPromise(new Error('ST1002_PAGE_LOAD_TIMEOUT')), 15_000),
    ),
  ]);
}

async function main() {
  if (process.argv.length !== 2) return 2;
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
  if (address === null || typeof address === 'string') fail('ST1002_LOOPBACK_BIND_FAILED');
  const baseUrl = `http://127.0.0.1:${address.port}`;
  let chrome;
  let profile;
  let connection;
  try {
    const response = await fetch(
      `${baseUrl}${articlePath}?untrusted=%3Cscript%3Ecanary%3C%2Fscript%3E`,
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
    assert.match(response.headers.get('content-security-policy') ?? '', /connect-src 'none'/);
    assert.match(response.headers.get('x-robots-tag') ?? '', /^noindex, nofollow/);
    assert.match(response.headers.get('cache-control') ?? '', /no-store/);
    assert.equal(response.headers.has('x-powered-by'), false);
    assert.equal(response.headers.has('set-cookie'), false);
    const html = await response.text();
    assert.match(html, /<html lang="ja">/);
    assert.equal((html.match(/<h1\b/g) ?? []).length, 1);
    assert.match(html, /ST-0805 recorded policy draft/);
    for (const landmark of ['header', 'nav', 'main', 'article', 'aside', 'section', 'footer']) {
      assert.match(html, new RegExp(`<${landmark}\\b`));
    }
    assert.match(html, /href="#public-article-main"/);
    assert.match(html, /name="robots" content="noindex, nofollow/);
    assert.doesNotMatch(html, /rel="canonical"|property="og:|name="twitter:/i);
    assert.doesNotMatch(
      html,
      /018f3e90|publication_snapshot|publicationId|articleId|sourcePacket|rawPrompt|finance/i,
    );
    assert.doesNotMatch(html, /product-card|affiliate-cta|application\/ld\+json/i);
    const visibleMarkup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
    assert.doesNotMatch(visibleMarkup, /canary|%3Cscript%3Ecanary/i);

    for (const pathValue of [
      '/articles/not-recorded',
      '/articles/Synthetic-recorded-policy-seo',
      '/articles/%3Cscript%3Eunknown%3C%2Fscript%3E',
    ]) {
      const missing = await fetch(`${baseUrl}${pathValue}`, { redirect: 'manual' });
      assert.equal(missing.status, 404);
      assert.equal(missing.headers.has('set-cookie'), false);
      assert.match(missing.headers.get('x-robots-tag') ?? '', /^noindex, nofollow/);
      const missingHtml = await missing.text();
      assert.doesNotMatch(
        missingHtml.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ''),
        /not-recorded|unknown/i,
      );
    }

    profile = await mkdtemp(path.join(tmpdir(), 'raos-st1002-chrome-'));
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
      `${debugOrigin}/json/new?${encodeURIComponent(`${baseUrl}${articlePath}`)}`,
      {
        method: 'PUT',
      },
    ).then((value) => value.json());
    connection = new CdpConnection(target.webSocketDebuggerUrl);
    await connection.open();
    const requested = [];
    connection.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (message.method === 'Network.requestWillBeSent')
        requested.push(message.params.request.url);
    });
    await connection.send('Page.enable');
    await connection.send('Runtime.enable');
    await connection.send('Network.enable');
    for (const width of [320, 360, 768, 1440]) {
      await connection.send('Emulation.setDeviceMetricsOverride', {
        width,
        height: 900,
        deviceScaleFactor: 1,
        mobile: false,
      });
      await navigate(connection, `${baseUrl}${articlePath}`);
      const summary = JSON.parse(
        await evaluate(
          connection,
          `JSON.stringify({
            lang: document.documentElement.lang,
            h1: [...document.querySelectorAll('h1')].map((node) => node.textContent),
            main: document.querySelectorAll('main').length,
            article: document.querySelectorAll('main article').length,
            breadcrumb: document.querySelectorAll('nav[aria-label="現在位置"]').length,
            skip: document.querySelector('a[href="#public-article-main"]')?.textContent,
            overflow: document.documentElement.scrollWidth > window.innerWidth,
            preview: document.body.innerText.includes('記録済み合成Fixtureのローカル表示'),
            disclosure: document.body.innerText.includes('この記事にはアフィリエイト広告が含まれます。')
          })`,
        ),
      );
      assert.deepEqual(summary, {
        lang: 'ja',
        h1: ['ST-0805 recorded policy draft'],
        main: 1,
        article: 1,
        breadcrumb: 1,
        skip: '本文へ移動',
        overflow: false,
        preview: true,
        disclosure: true,
      });
    }
    assert.ok(requested.every((url) => url.startsWith(baseUrl) || url === 'about:blank'));

    await navigate(connection, `${baseUrl}${articlePath}`);
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
    const focus = JSON.parse(
      await evaluate(
        connection,
        `JSON.stringify({
          text: document.activeElement?.textContent,
          outlineStyle: getComputedStyle(document.activeElement).outlineStyle,
          outlineWidth: getComputedStyle(document.activeElement).outlineWidth
        })`,
      ),
    );
    assert.equal(focus.text, '本文へ移動');
    assert.equal(focus.outlineStyle, 'solid');
    assert.notEqual(focus.outlineWidth, '0px');

    const axePackage = JSON.parse(await readFile(require.resolve('axe-core/package.json'), 'utf8'));
    assert.equal(axePackage.version, '4.12.1');
    const axeSource = await readFile(require.resolve('axe-core/axe.min.js'), 'utf8');
    await evaluate(connection, `${axeSource}\ntrue`);
    const axe = JSON.parse(
      await evaluate(
        connection,
        `(async () => {
          const result = await axe.run(document, {
            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] }
          });
          return JSON.stringify({
            violations: result.violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.length })),
            incomplete: result.incomplete.map(({ id, nodes }) => ({ id, nodes: nodes.length }))
          });
        })()`,
      ),
    );
    assert.deepEqual(axe.violations, []);
    assert.deepEqual(axe.incomplete, []);
    process.stdout.write(
      `${JSON.stringify({
        status: 'PASS',
        exactRoutes: 1,
        viewports: [320, 360, 768, 1440],
        keyboardFocusChecked: true,
        axeViolations: 0,
        axeIncomplete: 0,
        formalTst021: 'NOT_EXECUTED',
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
        setTimeout(resolvePromise, 3_000);
      });
    }
    if (profile !== undefined) await rm(profile, { recursive: true, force: true });
    await new Promise((resolvePromise) => server.close(resolvePromise));
  }
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : 'ST1002_BROWSER_FAILED'}\n`);
    process.exitCode = 1;
  });
