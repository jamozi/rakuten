const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const context = { module: { exports: {} } };
vm.runInNewContext(readFileSync('changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/local-running-cost.js', 'utf8'), context);
const { calculate, parseInput } = context.module.exports;
const profile = { energyWh: 230, waterLitres: 2.5 };
const input = { electricity: '30.7', water: '262', detergent: '2.1', runs: '30' };

test('known quantities use Wh/kWh and L/m3, rounding only at display', () => {
  const result = calculate(profile, input);
  assert.equal(result.complete, true);
  assert.ok(Math.abs(result.fees.electricity - 7.061) < 1e-9);
  assert.equal(result.fees.water, .655);
  assert.ok(Math.abs(result.perCycle - 9.816) < 1e-9);
  assert.ok(Math.abs(result.monthly - 294.48) < 1e-8);
});
test('blank is missing while explicit zero remains a valid rate/count', () => {
  assert.equal(parseInput('').value, null);
  assert.equal(parseInput('0').value, 0);
  const empty = calculate(profile, { electricity: '', water: '', detergent: '', runs: '' });
  assert.equal(empty.perCycle, null);
  assert.equal(empty.monthly, null);
  const zero = calculate(profile, { electricity: '0', water: '0', detergent: '0', runs: '0' });
  assert.equal(zero.perCycle, 0);
  assert.equal(zero.monthly, 0);
  assert.equal(zero.complete, true);
});
test('unknown quantities only permit a labelled partial sum, never rated watts', () => {
  const result = calculate({ energyWh: null, waterLitres: 3.2, ratedW: 900, minutes: 120 }, input);
  assert.equal(result.complete, false);
  assert.equal(result.fees.electricity, null);
  assert.ok(result.missing.includes('electricity'));
  assert.ok(Math.abs(result.perCycle - 2.9384) < 1e-9);
  const tank = calculate({ energyWh: null, waterLitres: null, tankLitres: 6 }, input);
  assert.equal(tank.fees.water, null);
  assert.equal(tank.perCycle, 2.1);
});
test('negative, malformed and non-finite numbers cannot yield a plausible total', () => {
  for (const bad of ['-1', 'NaN', 'Infinity', '1e309', '1,2', 'abc', '0x20']) {
    const result = calculate(profile, { ...input, electricity: bad });
    assert.ok(result.errors.electricity, bad);
    assert.equal(result.fees.electricity, null);
    assert.equal(result.complete, false);
  }
  assert.ok(parseInput('2.5', true).error);
  for (const fractional of ['1.0', '1.0000000000000001', '0.99999999999999999']) {
    const result = calculate(profile, { ...input, runs: fractional });
    assert.ok(result.errors.runs);
    assert.equal(result.monthly, null);
  }
  assert.ok(parseInput('9007199254740992', true).error);
  assert.equal(parseInput(' ３０．７ ').value, 30.7);
});
test('missing or invalid monthly count leaves the per-cycle subtotal usable', () => {
  for (const runs of ['', '2.5', '-1']) {
    const result = calculate(profile, { ...input, runs });
    assert.equal(result.monthly, null);
    assert.ok(result.perCycle > 0);
  }
});
test('documented input bounds reject digit errors without replacing them with zero', () => {
  for (const [key, maximum] of Object.entries({ electricity: 1000, water: 10000, detergent: 1000, runs: 1000 })) {
    assert.equal(calculate(profile, { ...input, [key]: String(maximum) }).errors[key], undefined);
    for (const value of [String(maximum + 1), '999999999999']) {
      const result = calculate(profile, { ...input, [key]: value });
      assert.match(result.errors[key], /桁と単位/);
      if (key === 'runs') {
        assert.equal(result.monthly, null);
        assert.ok(result.perCycle > 0);
      } else {
        assert.equal(result.fees[key], null);
        assert.equal(result.complete, false);
        assert.ok(result.missing.includes(key));
      }
    }
  }
});
test('exponent notation and excessive decimal precision receive distinct correction messages', () => {
  for (const key of ['electricity', 'water', 'detergent']) {
    assert.equal(calculate(profile, { ...input, [key]: '３０．７１２３' }).errors[key], undefined);
    assert.match(calculate(profile, { ...input, [key]: '30.71234' }).errors[key], /小数第4位/);
    assert.match(calculate(profile, { ...input, [key]: '1e2' }).errors[key], /指数表記/);
    assert.equal(calculate(profile, { ...input, [key]: '0.00001' }).fees[key], null);
  }
});
test('overflow is reported, never rendered as Infinity or a complete sum', () => {
  const result = calculate({ energyWh: 230, waterLitres: 1e308 }, { ...input, water: '10000' });
  assert.ok(Object.keys(result.errors).length > 0);
  assert.equal(result.complete, false);
});

test('model links and initial or changed hashes select only the bound exact profile', () => {
  const { profileForModel, bindModelSelection } = context.module.exports;
  const profiles = [
    { id: 'legacy', model: 'TK-MDW22W' },
    { id: 'color', model: 'TDWS25SBL / TDWS25SRD', anchor: 'product-dish-rakua-mini-color' },
    { id: 'tsp1', model: 'NP-TSP1-W', anchor: 'product-dish-np-tsp1' },
  ];
  assert.equal(profileForModel(profiles, 'TDWS25SBL').id, 'color');
  assert.equal(profileForModel(profiles, 'TDWS25SRD').id, 'color');
  assert.equal(profileForModel(profiles, 'TK-MDW22W').id, 'legacy');
  assert.equal(profileForModel(profiles, 'TK-MDW22B'), undefined);
  assert.equal(profileForModel(profiles, 'NP-TSP1'), undefined);
  const pageHandlers = {}, browserHandlers = {};
  const page = { addEventListener: (name, handler) => { pageHandlers[name] = handler; } };
  const browser = { location: { hash: '#product-dish-np-tsp1' }, addEventListener: (name, handler) => { browserHandlers[name] = handler; } };
  const chosen = [];
  bindModelSelection(profiles, page, browser, p => chosen.push(p.id));
  assert.deepEqual(chosen, ['tsp1']);
  browser.location.hash = '#product-dish-rakua-mini-color';
  browserHandlers.hashchange();
  assert.deepEqual(chosen, ['tsp1', 'color']);
  for (const hash of ['', '#unrelated', '#%E0%A4']) {
    browser.location.hash = hash;
    browserHandlers.hashchange();
  }
  assert.equal(chosen.length, 2);
  pageHandlers.click({ target: { closest: () => ({ getAttribute: () => 'TDWS25SRD' }) } });
  assert.equal(chosen.at(-1), 'color');
  pageHandlers.click({ target: { closest: () => ({ getAttribute: () => 'TK-MDW22B' }) } });
  assert.equal(chosen.length, 3);
});

test('new NP-TSP1 and color profiles preserve unknown energy and units', () => {
  const tsp = calculate({ energyWh: 670, waterLitres: 9 }, input);
  assert.ok(Math.abs(tsp.fees.electricity - 20.569) < 1e-9);
  assert.ok(Math.abs(tsp.fees.water - 2.358) < 1e-9);
  const color = calculate({ energyWh: null, waterLitres: 3.2 }, input);
  assert.equal(color.complete, false);
  assert.equal(color.fees.electricity, null);
});

// KS-025: every registry profile against the hand-calculation record, in rendered (anchored first) order.
const HAND_RECORD = 'tests/wordpress_local_preview/fixtures/running-cost-hand-calculations.v1.json';
const ASSET = 'changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/local-running-cost.js';
const renderedProfiles = () => {
  const registry = JSON.parse(readFileSync('changes/editorial-portfolio-v3/local-reader-guides.v1.json', 'utf8'));
  const config = registry.articles.find(a => a.article_id === 'dishwasher-running-cost').cost_calculator;
  const quantity = (p, ref, kind) => ref === null ? null : registry.facts
    .find(f => f.evidence_ref === ref && f.exact_model === p.exact_model).quantities
    .find(q => q.kind === kind && q.course === p.course);
  const ordered = [...config.profiles.filter(p => p.product_anchor), ...config.profiles.filter(p => !p.product_anchor)];
  return { total: config.profiles.length, rows: ordered.map(p => {
    const e = quantity(p, p.energy_ref, 'energy_per_cycle'), w = quantity(p, p.water_ref, 'water_per_cycle');
    return { id: p.profile_id, model: p.exact_model, anchor: p.product_anchor, energy: e ? e.value : null, water: w ? w.value : null,
      course: e?.course_label ?? w?.course_label ?? 'コース別の消費量は未確認' };
  }) };
};
class FakeElement {
  constructor(tag) { Object.assign(this, { tagName: tag.toUpperCase(), children: [], attrs: {}, listeners: {}, ownText: '', hidden: false, dataset: {}, stored: undefined }); }
  get id() { return this.attrs.id; }
  get value() {
    if (this.stored === undefined && this.tagName === 'SELECT') return [...this.walk()].find(o => o.tagName === 'OPTION' && o.defaultSelected)?.attrs.value;
    return this.stored ?? '';
  }
  set value(v) { this.stored = v; }
  set textContent(text) { this.ownText = String(text); this.children = []; }
  get textContent() { return this.ownText + this.children.map(c => c.textContent).join(''); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.ownText = ''; this.children = nodes; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  focus() {}
  *walk() { yield this; for (const child of this.children) yield* child.walk(); }
}
// Runs the asset's own mount and submit handler, so result wording comes from the production template.
const mountCalculator = (rows, defaultId) => {
  const mount = new FakeElement('div'), noScript = new FakeElement('p');
  mount.dataset.raosDefaultProfile = defaultId;
  const trs = rows.map(p => {
    const tr = new FakeElement('tr');
    Object.assign(tr.dataset, { raosCostProfile: p.id, raosCostModel: p.model, raosCostCourse: p.course, raosCostAnchor: p.anchor });
    if (p.energy !== null) tr.setAttribute('data-raos-energy-wh', String(p.energy));
    if (p.water !== null) tr.setAttribute('data-raos-water-litres', String(p.water));
    return tr;
  });
  mount.querySelectorAll = () => trs;
  mount.querySelector = selector => selector === '.raos-cost-no-script' ? noScript : null;
  const document = { querySelector: s => s === '[data-raos-cost-calculator="v1"]' ? mount : null, createElement: tag => new FakeElement(tag) };
  vm.runInNewContext(readFileSync(ASSET, 'utf8'), { document });
  const nodes = [...mount.children[0].walk()], byId = id => nodes.find(n => n.attrs.id === id);
  const output = nodes.find(n => n.attrs.class === 'raos-cost-result');
  assert.equal(noScript.hidden, true);
  return (profileId, values) => {
    byId('raos-cost-profile').value = profileId;
    for (const [key, value] of Object.entries(values)) byId('raos-cost-' + key).value = value;
    mount.children[0].listeners.submit({ preventDefault() {} });
    return output.children.flatMap(c => c.tagName === 'UL' ? c.children.map(li => li.textContent) : [c.textContent]);
  };
};

test('hand-calculation record covers every registry profile', () => {
  const record = JSON.parse(readFileSync(HAND_RECORD, 'utf8'));
  const { total, rows } = renderedProfiles();
  assert.equal(rows.length, total);
  assert.deepEqual(record.profiles.map(p => p.profile_id), rows.map(p => p.id));
  assert.deepEqual(record.inputs, input);
  const amount = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 2 });
  const submit = mountCalculator(rows, 'np-tmlk1-standard');
  for (const [i, row] of rows.entries()) {
    const rec = record.profiles[i], id = rec.profile_id;
    assert.deepEqual([rec.exact_model, rec.course_label, rec.energy_wh, rec.water_l, rec.scope],
      [row.model, row.course, row.energy, row.water, row.anchor ? '現行比較対象' : '参考（比較対象外）'], id);
    const result = calculate({ energyWh: rec.energy_wh, waterLitres: rec.water_l }, input);
    const actual = { ...result.fees, per_cycle: result.perCycle, monthly: result.monthly };
    const recorded = { ...rec.fees, per_cycle: rec.per_cycle, monthly: rec.monthly };
    for (const [key, value] of Object.entries(recorded)) {
      if (value === null) assert.equal(actual[key], null, id + ' ' + key);
      else assert.ok(Math.abs(actual[key] - Number(value)) < 1e-9, `${id} ${key} ${actual[key]} != ${value}`);
      assert.equal(actual[key] === null ? null : amount.format(actual[key]), rec.display[key], id + ' display ' + key);
    }
    assert.equal(result.complete, rec.complete, id);
    assert.deepEqual(submit(id, input), rec.result_lines, id);
  }
});
