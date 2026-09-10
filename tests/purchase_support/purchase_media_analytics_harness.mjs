import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const base = 'changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/';
const script = fs.readFileSync(base + 'assets/purchase-analytics.js', 'utf8');
const binding = { article_id: 'article-1', product_id: 'PRD-EXAMPLE', seller_id: 'rakuten-public-shop', offer_id: 'image-PRD-EXAMPLE-300', cta_id: 'purchase-image-PRD-EXAMPLE-300', placement: 'product_card', snapshot_id: 'ps-example', href: 'https://seller.example/image?opaque=do-not-send' };
function fixture() {
  const calls = [], listeners = {};
  const root = { getAttribute: key => ({ 'data-raos-article-id': binding.article_id, 'data-raos-snapshot-id': binding.snapshot_id })[key] };
  const wrapper = { getAttribute: key => binding[key.replace('data-raos-', '').replaceAll('-', '_')], closest: () => root };
  const anchor = { href: binding.href, closest: () => wrapper };
  const config = { profile: 'purchase-support-v1', enabled: true, debug_mode: false, bindings: [{ ...binding }] };
  const window = { getCkyConsent: () => ({ isUserActionCompleted: true, categories: { analytics: true } }), wp_has_consent: () => true, _googlesitekitConsents: { analytics_storage: 'granted' }, localStorage: { getItem: () => null }, gtag: (...args) => calls.push(args) };
  window.gtag.raosConsentGate = true;
  const document = { getElementById: id => id === 'raos-purchase-ga4-config' ? { type: 'application/json', textContent: JSON.stringify(config) } : { getAttribute: () => 'G-ABC12345' }, addEventListener: (type, fn) => (listeners[type] ??= []).push(fn) };
  const context = vm.createContext({ window, document });
  vm.runInContext(script, context);
  const click = () => listeners.click[0]({ type: 'click', button: 0, isTrusted: true, target: { closest: () => anchor } });
  return { calls, listeners, anchor, wrapper, config, click, context };
}
let f = fixture(); f.click();
assert.equal(f.calls.length, 1);
assert.equal(Object.keys(f.calls[0][2]).length, 9);
assert.equal(JSON.stringify(f.calls).includes('opaque'), false);
assert.equal(JSON.stringify(f.calls).includes('https'), false);
assert.equal(f.calls[0][2].offer_id, binding.offer_id);
vm.runInContext(script, f.context); assert.equal(f.listeners.click.length, 1);
for (const alter of [f => f.anchor.href += '&drift=1', f => f.wrapper.getAttribute = () => 'wrong', f => f.config.bindings[0].href += '&drift=1', f => f.config.bindings[0].extra = 'invalid', f => f.anchor.closest = () => null]) {
  f = fixture(); alter(f); f.click(); assert.equal(f.calls.length, 0);
}
console.log('Media wrapper bindings, exact href, payload privacy, and single collector PASS');
