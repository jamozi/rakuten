import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const shell = readFileSync(resolve(root, 'apps/web/src/public-shell.tsx'), 'utf8');
const layout = readFileSync(resolve(root, 'apps/web/app/layout.tsx'), 'utf8');
const css = readFileSync(resolve(root, 'apps/web/app/globals.css'), 'utf8');

describe('ST-1001 V2 accessibility implementation contract', () => {
  it('uses Japanese document language, one page heading, skip target, and labelled landmarks', () => {
    assert.match(layout, /<html lang="ja">/);
    assert.equal((shell.match(/<h1\b/g) ?? []).length, 1);
    assert.match(shell, /href="#public-shell-main"/);
    assert.match(shell, /id="public-shell-main"/);
    assert.match(shell, /aria-label="主要な方針ページ"/);
    assert.match(shell, /aria-label="現在位置"/);
    assert.match(shell, /aria-label="方針と運営情報"/);
    assert.match(shell, /aria-labelledby="public-shell-heading"/);
    assert.match(shell, /aria-labelledby="preview-notice-heading"/);
  });

  it('preserves visible focus, text status, target size, reflow, and reduced-motion rules', () => {
    assert.match(css, /:focus-visible/);
    assert.match(css, /outline:\s*0\.2rem solid var\(--focus\)/);
    assert.match(css, /min-height:\s*2\.75rem/);
    assert.match(css, /@media \(max-width: 24rem\)/);
    assert.match(css, /overflow-wrap:\s*anywhere/);
    assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
    assert.doesNotMatch(css, /animation(?:-name)?:|transition:/);
    assert.match(shell, /STATUS_LABELS\[section\.state\]/);
    assert.match(shell, /aria-hidden="true"/);
  });

  it('does not introduce images, forms, dialogs, tables, motion, or auto-updating regions', () => {
    assert.doesNotMatch(shell, /<img\b|<form\b|<dialog\b|<table\b|aria-live|role="alert"/);
    assert.doesNotMatch(shell, /onClick=|onSubmit=|onKeyDown=|setTimeout|setInterval/);
  });
});
