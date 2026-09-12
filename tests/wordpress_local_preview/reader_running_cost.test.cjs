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
