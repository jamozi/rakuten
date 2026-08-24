import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

const component = readFileSync('apps/web/src/recorded-comparison-components.tsx', 'utf8');
const styles = readFileSync('apps/web/src/recorded-comparison-components.module.css', 'utf8');

describe('ST-1003 V2 recorded public components', () => {
  it('uses native comparison headers and a labelled scroll region', () => {
    assert.match(component, /<caption>/u);
    assert.match(component, /scope="col"/u);
    assert.match(component, /scope="row"/u);
    assert.match(component, /role="region"/u);
    assert.match(component, /tabIndex=\{0\}/u);
    assert.match(styles, /overflow-x:\s*auto/u);
    assert.match(styles, /:focus-visible/u);
  });

  it('keeps Unknown and all three trade-off fields visible as text', () => {
    assert.match(component, /不明（一次情報未確認）/u);
    assert.match(component, />利点</u);
    assert.match(component, />制約</u);
    assert.match(component, />当てはまる条件</u);
    assert.doesNotMatch(component, /unknown[^\n]*(?:0|''|"")/iu);
  });

  it('contains no CTA or image markup, finance value, tracking, or client effect', () => {
    assert.match(component, /CTA、価格、在庫、画像、実商品情報は含みません/u);
    assert.doesNotMatch(
      component,
      /<a\b|<img\b|href=|楽天市場|commissionRate|EPC|RPM|profit|use client|useEffect|fetch|sendBeacon/iu,
    );
    assert.doesNotMatch(component, /dangerouslySetInnerHTML/iu);
  });

  it('provides a mobile single-column card layout without changing table semantics', () => {
    assert.match(styles, /@media\s*\(max-width:\s*36rem\)/u);
    assert.match(styles, /grid-template-columns:\s*1fr/u);
    assert.match(styles, /min-width:\s*42rem/u);
  });
});
