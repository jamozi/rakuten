#!/usr/bin/env node

import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const appDirectory = path.join(root, 'apps/web');
const articlePath = '/articles/synthetic-recorded-policy-seo';

function anchorHrefs(html) {
  return [...html.matchAll(/<a\b[^>]*\shref="([^"]+)"[^>]*>/giu)].map((match) => match[1]);
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
  try {
    const address = server.address();
    assert.ok(address !== null && typeof address !== 'string');
    const baseUrl = `http://127.0.0.1:${address.port}`;
    const response = await fetch(`${baseUrl}${articlePath}`, { redirect: 'manual' });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-security-policy') ?? '', /script-src 'none'/u);
    assert.match(response.headers.get('content-security-policy') ?? '', /connect-src 'none'/u);
    assert.match(response.headers.get('x-robots-tag') ?? '', /^noindex, nofollow/u);
    assert.equal(response.headers.has('set-cookie'), false);
    const html = await response.text();
    assert.match(html, /この記事にはアフィリエイト広告が含まれます。/u);
    assert.match(
      html,
      /確認済みのリンクを利用できないため、楽天市場へのボタンは表示していません。/u,
    );
    assert.equal((html.match(/<h1\b/gu) ?? []).length, 1);
    assert.doesNotMatch(html, /楽天市場で写真・価格・在庫を見る/u);
    assert.doesNotMatch(html, /sponsored|example\.invalid|https?:\/\//iu);
    const hrefs = anchorHrefs(html);
    assert.ok(hrefs.length > 0);
    assert.ok(hrefs.every((href) => href.startsWith('/') || href.startsWith('#')));

    for (const unknownPath of [
      '/articles/not-recorded',
      '/articles/%2F%2Fevil.invalid',
      '/articles/synthetic-recorded-policy-seo%3FreturnUrl%3D%2F%2Fevil.invalid',
    ]) {
      const missing = await fetch(`${baseUrl}${unknownPath}`, { redirect: 'manual' });
      assert.equal(missing.status, 404);
      const missingHtml = await missing.text();
      assert.doesNotMatch(
        missingHtml.replace(/<script\b[^>]*>[\s\S]*?<\/script>/giu, ''),
        /evil\.invalid|returnUrl|not-recorded/iu,
      );
    }
    process.stdout.write(
      `${JSON.stringify({
        status: 'PASS',
        exactSlug: true,
        disclosureVisible: true,
        unavailableNoticeVisible: true,
        affiliateCtaAbsent: true,
        arbitraryOutboundAnchorCount: 0,
        noindex: true,
        cspClosed: true,
        formalTst020: 'NOT_EXECUTED',
        formalTst022: 'NOT_EXECUTED',
        formalTst026: 'NOT_EXECUTED',
      })}\n`,
    );
    return 0;
  } finally {
    await new Promise((resolvePromise) => server.close(resolvePromise));
  }
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : 'ST1004_BROWSER_FAILED'}\n`);
    process.exitCode = 1;
  });
