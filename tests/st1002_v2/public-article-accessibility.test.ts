import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const page = readFileSync(resolve(root, 'apps/web/src/public-article-page.tsx'), 'utf8');
const css = readFileSync(resolve(root, 'apps/web/app/articles/[slug]/article.module.css'), 'utf8');

describe('ST-1002 V2 accessibility implementation contract', () => {
  it('provides skip navigation, landmarks, labelled breadcrumb/article/status regions and one H1', () => {
    assert.equal((page.match(/<h1\b/g) ?? []).length, 1);
    assert.match(page, /href="#public-article-main"/);
    assert.match(page, /id="public-article-main"/);
    assert.match(page, /aria-label="現在位置"/);
    assert.match(page, /aria-label="方針と運営情報"/);
    assert.match(page, /aria-label="公開方針ページ"/);
    assert.match(page, /aria-labelledby="public-article-heading"/);
    assert.match(page, /aria-labelledby="article-disclosure-heading"/);
    assert.match(page, /aria-labelledby="article-preview-heading"/);
    assert.match(page, /aria-labelledby="article-freshness-heading"/);
  });

  it('preserves visible focus, target size, 320px reflow and reduced-motion safety', () => {
    assert.match(css, /:focus-visible/);
    assert.match(css, /outline:\s*0\.2rem solid #0b63ce/);
    assert.match(css, /min-height:\s*2\.75rem/);
    assert.match(css, /@media \(max-width: 24rem\)/);
    assert.match(css, /grid-template-columns:\s*1fr/);
    assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
    assert.doesNotMatch(css, /animation(?:-name)?:|transition:/);
  });

  it('uses text cues instead of color-only state and introduces no interactive widgets', () => {
    assert.match(page, /section\.kind === 'WARNING' \? '注意' : '判断材料'/);
    assert.match(page, /model\.article\.freshnessText/);
    assert.match(page, /model\.article\.previewLabel/);
    assert.doesNotMatch(page, /onClick=|onSubmit=|onKeyDown=|aria-live|role="alert"/);
    assert.doesNotMatch(page, /<button\b|<input\b|<dialog\b|tabIndex=\{0\}/);
  });
});
