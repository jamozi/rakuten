/* Local preview only. No storage, networking, telemetry or household defaults. */
(() => {
  'use strict';

  // Calculator input bounds, not claims about current utility tariffs.
  const inputLimits = { electricity: 1000, water: 10000, detergent: 1000, runs: 1000 };
  const inputRange = key => key === 'runs'
    ? 'この計算では0〜1,000回の整数を入力できます。'
    : `この計算では0〜${inputLimits[key].toLocaleString('ja-JP')}円、小数第4位まで入力できます。`;
  const parseInput = (raw, integer = false) => {
    if (typeof raw !== 'string') return { value: null, error: '数値を入力してください。' };
    const text = raw.normalize('NFKC').trim();
    if (text === '') return { value: null, error: null };
    if (/^\d*(?:\.\d*)?[eE][+-]?\d+$/.test(text)) {
      return { value: null, error: '指数表記は使わず、通常の数値で入力してください。' };
    }
    const value = Number(text);
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) || !Number.isFinite(value) || value < 0) {
      return { value: null, error: '0以上の数値を入力してください（例：30.7）。' };
    }
    if (integer && (!/^\d+$/.test(text) || !Number.isSafeInteger(value))) {
      return { value: null, error: '運転回数は0以上の整数で入力してください。' };
    }
    return { value, error: null };
  };

  const calculate = (profile, inputs) => {
    const errors = {};
    const parsed = {};
    const fees = { electricity: null, water: null, detergent: null };
    for (const key of ['electricity', 'water', 'detergent', 'runs']) {
      parsed[key] = parseInput(inputs[key], key === 'runs');
      if (!parsed[key].error && parsed[key].value !== null) {
        const text = inputs[key].normalize('NFKC').trim();
        if (parsed[key].value > inputLimits[key]) {
          parsed[key] = { value: null, error: `${inputRange(key)}桁と単位を確認してください。` };
        } else if (key !== 'runs' && (text.split('.')[1] || '').length > 4) {
          parsed[key] = { value: null, error: '小数第4位までに丸めて入力してください。自動では丸めません。' };
        }
      }
      if (parsed[key].error) errors[key] = parsed[key].error;
    }
    const known = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
    if (known(profile.energyWh) && parsed.electricity.value !== null) {
      fees.electricity = profile.energyWh / 1000 * parsed.electricity.value;
    }
    if (known(profile.waterLitres) && parsed.water.value !== null) {
      fees.water = profile.waterLitres / 1000 * parsed.water.value;
    }
    fees.detergent = parsed.detergent.value;
    for (const key of Object.keys(fees)) {
      if (fees[key] !== null && !Number.isFinite(fees[key])) {
        fees[key] = null;
        errors[key] = '値が大きすぎて計算できません。入力を確認してください。';
      }
    }
    const missing = Object.keys(fees).filter(key => fees[key] === null);
    const available = Object.values(fees).filter(value => value !== null);
    let perCycle = available.length ? available.reduce((a, b) => a + b, 0) : null;
    if (perCycle !== null && !Number.isFinite(perCycle)) {
      perCycle = null;
      errors.total = '値が大きすぎて合計を計算できません。';
    }
    let monthly = perCycle !== null && parsed.runs.value !== null ? perCycle * parsed.runs.value : null;
    if (monthly !== null && !Number.isFinite(monthly)) {
      monthly = null;
      errors.runs = '値が大きすぎて月の概算を計算できません。';
    }
    return { fees, missing, errors, perCycle, monthly, complete: missing.length === 0 && !errors.total };
  };

  // Exact identifiers only; a color variant may select its explicitly shared profile.
  const profileForModel = (profiles, model) => profiles.find(p =>
    p.model === model || p.model.split(' / ').includes(model));
  const bindModelSelection = (profiles, page, browser, choose) => {
    const fromHash = () => {
      let id;
      try { id = decodeURIComponent(browser.location.hash.slice(1)); } catch (_) { return; }
      const profile = profiles.find(p => p.anchor === id);
      if (profile) choose(profile);
    };
    page.addEventListener('click', event => {
      const link = event.target.closest ? event.target.closest('[data-ps-cost-model]') : null;
      if (!link) return;
      const profile = profileForModel(profiles, link.getAttribute('data-ps-cost-model'));
      if (profile) choose(profile);
    });
    browser.addEventListener('hashchange', fromHash);
    fromHash();
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = { parseInput, calculate, profileForModel, bindModelSelection };
  if (typeof document === 'undefined') return;

  const mount = document.querySelector('[data-raos-cost-calculator="v1"]');
  if (!mount || mount.dataset.raosCostMounted) return;
  const quantity = (row, name) => row.hasAttribute(name) ? parseInput(row.getAttribute(name)).value : null;
  const profiles = [...mount.querySelectorAll('[data-raos-cost-profile]')].map(row => ({
    id: row.dataset.raosCostProfile,
    model: row.dataset.raosCostModel,
    course: row.dataset.raosCostCourse,
    anchor: row.dataset.raosCostAnchor,
    energyWh: quantity(row, 'data-raos-energy-wh'),
    waterLitres: quantity(row, 'data-raos-water-litres'),
  }));
  const defaultId = mount.dataset.raosDefaultProfile;
  if (!profiles.length || !profiles.some(p => p.id === defaultId) || new Set(profiles.map(p => p.id)).size !== profiles.length) return;
  const element = (tag, text, attributes = {}) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  };
  const form = element('form', '', { class: 'raos-cost-form', novalidate: '', 'aria-label': '自宅の単価による従量費の概算' });
  const fields = element('fieldset');
  fields.append(element('legend', '使う条件と、自宅の単価を入力'));
  const select = element('select', '', { id: 'raos-cost-profile', 'aria-describedby': 'raos-cost-selected-condition' });
  for (const profile of profiles) {
    const option = element('option', `${profile.model} — ${profile.course}`, { value: profile.id });
    option.defaultSelected = profile.id === defaultId;
    select.append(option);
  }
  const selectLabel = element('label', '型番・コース', { for: select.id });
  const selectedCondition = element('p', '', { id: 'raos-cost-selected-condition', class: 'raos-cost-help' });
  fields.append(selectLabel, select, selectedCondition);
  const definitions = [
    ['electricity', '電気単価（円/kWh）', '契約先の料金表で適用される従量単価を確認します。調整額などを含める範囲をそろえ、不明なら空欄にします。基本料金は入れません。', 'decimal'],
    ['water', '上下水道の合計従量単価（円/m³）', '自治体の料金表で、自宅に適用される上水道と下水道の従量単価を合計します。基本料金は除き、段階制などで単価が決まらなければ空欄にします。', 'decimal'],
    ['detergent', '洗剤代（円/回）', '使う機種・洗剤に合う一回分の量を確認し、購入価格÷内容量×一回分の量で求めます。投入量が不明なら空欄にします。', 'decimal'],
    ['runs', '月の運転回数（回）', '計算したい一か月の運転回数を整数で入力します。自動で毎日使う前提にはしません。', 'numeric'],
  ];
  const controls = {};
  const errors = {};
  for (const [key, label, help, inputmode] of definitions) {
    const id = `raos-cost-${key}`;
    const group = element('div', '', { class: 'raos-cost-field' });
    controls[key] = element('input', '', { id, type: 'text', inputmode, autocomplete: 'off', 'aria-describedby': `${id}-help ${id}-error` });
    errors[key] = element('p', '', { id: `${id}-error`, class: 'raos-cost-error', hidden: '' });
    group.append(element('label', label, { for: id }), controls[key],
      element('p', `${help}${inputRange(key)}`, { id: `${id}-help`, class: 'raos-cost-help' }), errors[key]);
    fields.append(group);
  }
  const actions = element('div', '', { class: 'raos-cost-actions' });
  actions.append(element('button', '従量費の概算を計算', { type: 'submit' }), element('button', '入力をクリア', { type: 'reset' }));
  const output = element('div', '', { class: 'raos-cost-result', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
  const amount = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 2 });
  const feeNames = { electricity: '電気代', water: '上下水道代', detergent: '洗剤代' };
  const selected = () => profiles.find(p => p.id === select.value);
  const condition = () => {
    const p = selected();
    selectedCondition.textContent = `${p.model}／${p.course}。消費電力量：${p.energyWh === null ? '未確認' : p.energyWh + 'Wh/回'}。使用水量：${p.waterLitres === null ? '未確認' : p.waterLitres + 'L/回'}。別コースへ同じ値は使いません。`;
  };
  const clearError = key => {
    controls[key].removeAttribute('aria-invalid');
    errors[key].textContent = '';
    errors[key].hidden = true;
  };
  const idle = () => { output.textContent = '単価と運転回数は未入力です。分かる項目を入力して計算してください。'; };
  form.addEventListener('submit', event => {
    event.preventDefault();
    const result = calculate(selected(), Object.fromEntries(Object.entries(controls).map(([key, node]) => [key, node.value])));
    for (const key of Object.keys(controls)) {
      clearError(key);
      if (result.errors[key]) {
        controls[key].setAttribute('aria-invalid', 'true');
        errors[key].textContent = result.errors[key];
        errors[key].hidden = false;
      }
    }
    output.replaceChildren();
    output.append(element('p', result.complete ? '入力した3費目の従量費の概算' : '確認できた費目の小計（未計算の費目を含みません）'));
    const list = element('ul');
    for (const [key, value] of Object.entries(result.fees)) {
      const reason = result.errors[key] ? '入力を確認してください' :
        (key === 'electricity' && selected().energyWh === null) || (key === 'water' && selected().waterLitres === null)
          ? 'この条件の公表値が未確認' : '単価が未入力';
      list.append(element('li', `${feeNames[key]}：${value === null ? '未計算（' + reason + '）' : amount.format(value) + '円/回'}`));
    }
    output.append(list);
    output.append(element('p', result.perCycle === null ? '一回分：計算できる費目がありません。' : `一回分${result.complete ? '' : 'の小計'}：${amount.format(result.perCycle)}円`));
    output.append(element('p', result.monthly === null ? '月の概算：未計算。運転回数と計算できる費目を確認してください。' :
      `${parseInput(controls.runs.value, true).value}回分${result.complete ? '' : 'の小計'}：${amount.format(result.monthly)}円/月`));
    if (result.errors.total) output.append(element('p', result.errors.total));
    output.append(element('p', '基本料金などを含む請求額や、手洗いとの差額ではありません。表示は小数第2位までに丸めています。'));
    const firstError = Object.keys(controls).find(key => result.errors[key]);
    if (firstError) controls[firstError].focus();
  });
  form.addEventListener('input', event => {
    const key = Object.keys(controls).find(k => controls[k] === event.target);
    if (key) clearError(key);
    output.textContent = '入力を変更しました。「従量費の概算を計算」で結果を更新してください。';
  });
  select.addEventListener('change', condition);
  form.addEventListener('reset', event => {
    event.preventDefault();
    for (const key of Object.keys(controls)) { controls[key].value = ''; clearError(key); }
    select.value = defaultId;
    condition();
    idle();
  });
  form.append(fields, element('p', '未確認・未入力の費目がある場合は、分かる費目だけの小計です。未確認は0円ではありません。含む費目が違う金額は比較できません。'), actions, element('p', '入力はこの画面内だけで使い、保存・送信しません。'), output);
  mount.prepend(form);
  mount.querySelector('.raos-cost-no-script').hidden = true;
  mount.dataset.raosCostMounted = '1';
  condition();
  idle();
  if (typeof window !== 'undefined') bindModelSelection(profiles, document, window, profile => {
    select.value = profile.id;
    condition();
    output.textContent = '機種を選択しました。単価を確認し、「従量費の概算を計算」で結果を更新してください。';
  });
})();
