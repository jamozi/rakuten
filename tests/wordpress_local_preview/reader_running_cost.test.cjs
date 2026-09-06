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
test('overflow is reported, never rendered as Infinity or a complete sum', () => {
  const result = calculate({ energyWh: 1e308, waterLitres: 2.5 }, { ...input, electricity: '999999999' });
  assert.ok(Object.keys(result.errors).length > 0);
  assert.equal(result.complete, false);
});
