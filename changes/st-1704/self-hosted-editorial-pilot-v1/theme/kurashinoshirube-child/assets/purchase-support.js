/* Bounded reader controls: ephemeral input only; no storage, requests or telemetry. */
(() => {
  'use strict';
  const COST_FIELDS = ['price_yen', 'shipping_yen', 'required_items_yen'];
  const DAY = 24 * 60 * 60 * 1000;
  const money = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1000000000;
  const numberInput = value => {
    const text = typeof value === 'string' ? value.normalize('NFKC').trim() : '';
    if (!text) return { value: null, invalid: false };
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) || !money(Number(text))) return { value: null, invalid: true };
    return { value: Number(text), invalid: false };
  };
  const time = value => typeof value === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? Date.parse(value) : NaN;
  const offerCost = (offer, now) => {
    const amounts = COST_FIELDS.map(key => offer[key]);
    const known = amounts.filter(money);
    const result = { state: 'INCOMPLETE', total: null, subtotal: known.length ? known.reduce((a, b) => a + b, 0) : null };
    const checked = time(offer.checked_at), deadline = time(offer.valid_until);
    if (!Number.isFinite(checked) || !Number.isFinite(deadline) || !Number.isFinite(now) || checked > now) return { ...result, state: 'UNKNOWN' };
    if (deadline <= checked || now >= Math.min(deadline, checked + DAY)) return { ...result, state: 'EXPIRED' };
    if (offer.identity_verified !== true || offer.state !== 'AVAILABLE' || offer.condition !== 'new') return { ...result, state: 'UNKNOWN' };
    if (offer.total_scope_complete !== true || !amounts.every(money)) return result;
    return { state: 'CURRENT', total: result.subtotal, subtotal: result.subtotal };
  };
  const budgetState = (offers, budget, now) => {
    if (!money(budget)) return 'UNKNOWN';
    const costs = offers.map(o => offerCost(o, now));
    if (costs.some(c => c.total !== null && c.total <= budget)) return 'WITHIN_BUDGET';
    if (!costs.length || costs.some(c => c.total === null)) return 'UNKNOWN';
    return 'OVER_BUDGET';
  };
  const sameKnownValues = values => values.length > 1 && values.every(v =>
    typeof v === 'string' && v.trim() && !/未確認|不明|UNKNOWN|UNAVAILABLE|確認中|未検証|未実施|未計測/i.test(v)) &&
    values.every(v => v.replace(/\s+/g, ' ').trim() === values[0].replace(/\s+/g, ' ').trim());
  const installationFields = [
    ['width_mm', '本体を置く幅'], ['depth_mm', '本体を置く奥行'], ['height_mm', '本体を置く高さ'],
    ['door_depth_mm', '扉を開けたときの奥行'], ['door_height_mm', '扉を開けたときの高さ'],
    ['above_mm', '本体の上に残せる余白'], ['left_mm', '本体の左に残せる余白'],
    ['right_mm', '本体の右に残せる余白'], ['rear_mm', '本体の後ろに残せる余白'],
  ];
  const checkInstallation = (requirements, measurements) => {
    const fields = installationFields.map(([key]) => {
      const required = requirements[key], measured = numberInput(measurements[key]);
      if (!money(required) || measured.value === null) return { key, state: 'UNKNOWN', invalid: measured.invalid };
      return { key, state: measured.value < required ? 'MISMATCH' : 'CONFIRMED', invalid: false };
    });
    return { fields, state: fields.some(f => f.state === 'MISMATCH') ? 'MISMATCH' : fields.some(f => f.state === 'UNKNOWN') ? 'UNKNOWN' : 'CONFIRMED' };
  };
  // Numeric matching only: a site-side reference that is missing or invalid is a
  // configuration state, never the reader's missing input, and no key outside the
  // nine published fields is accepted on either side.
  const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const validReference = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 10000;
  const parseMeasurement = raw => {
    if (typeof raw !== 'string') return { value: null, state: 'INVALID' };
    const text = raw.normalize('NFKC').trim();
    if (!text) return { value: null, state: 'MISSING' };
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text)) return { value: null, state: 'INVALID' };
    const value = Number(text);
    if (!Number.isFinite(value) || value < 0 || value > 1000000000) return { value: null, state: 'INVALID' };
    return { value, state: 'VALID' };
  };
  const assessInstallation = (requirements, measurements) => {
    if (!isRecord(requirements)) throw new TypeError('REFERENCE_OBJECT_REQUIRED');
    if (!isRecord(measurements)) throw new TypeError('MEASUREMENTS_OBJECT_REQUIRED');
    const allowed = new Set(installationFields.map(([key]) => key));
    if (Object.keys(requirements).some(key => !allowed.has(key))) throw new TypeError('UNKNOWN_REFERENCE_KEY');
    if (Object.keys(measurements).some(key => !allowed.has(key))) throw new TypeError('UNKNOWN_MEASUREMENT_KEY');
    const counts = { known: 0, matched: 0, mismatched: 0, missing: 0, invalid: 0, reference_unknown: 0, reference_invalid: 0 };
    const fields = installationFields.map(([key, label]) => {
      const required = requirements[key];
      if (required === undefined || required === null) {
        counts.reference_unknown++;
        return { key, label, required_mm: null, input_required: false, reference_state: 'UNKNOWN', input_state: 'NOT_REQUESTED', match_state: 'NOT_EVALUATED', shortfall_mm: null };
      }
      if (!validReference(required)) {
        counts.reference_invalid++;
        return { key, label, required_mm: null, input_required: false, reference_state: 'INVALID', input_state: 'NOT_REQUESTED', match_state: 'NOT_EVALUATED', shortfall_mm: null };
      }
      counts.known++;
      const parsed = parseMeasurement(Object.hasOwn(measurements, key) ? measurements[key] : '');
      const row = { key, label, required_mm: required, input_required: true, reference_state: 'KNOWN', input_state: parsed.state, match_state: 'NOT_EVALUATED', shortfall_mm: null };
      if (parsed.state === 'MISSING') counts.missing++;
      else if (parsed.state === 'INVALID') counts.invalid++;
      else if (parsed.value < required) {
        row.match_state = 'MISMATCH'; row.shortfall_mm = Number((required - parsed.value).toFixed(6)); counts.mismatched++;
      } else { row.match_state = 'MATCH'; counts.matched++; }
      return row;
    });
    const state = counts.reference_invalid ? 'REFERENCE_INVALID' : counts.invalid ? 'INPUT_INVALID' :
      counts.mismatched ? 'MISMATCH' : !counts.known ? 'NO_REFERENCE' :
      counts.missing ? 'INPUT_MISSING' : counts.reference_unknown ? 'PARTIAL' : 'NUMERIC_MATCH';
    return { fields, counts, state };
  };
  const installationSummary = assessment => {
    const c = assessment.counts;
    const parts = [`数値一致 ${c.matched}項目`, `不足 ${c.mismatched}項目`, `未入力 ${c.missing}項目`];
    if (c.invalid) parts.push(`入力形式の確認 ${c.invalid}項目`);
    if (c.reference_unknown) parts.push(`サイト側の基準未確認 ${c.reference_unknown}項目`);
    if (c.reference_invalid) parts.push(`基準データの不備 ${c.reference_invalid}項目`);
    return parts.join('／') + '。これは寸法の数値照合です。安全な設置・使用を保証しません。台の強度・水平、給排水、電源・アース、熱源、扉の動作経路は別に確認してください。';
  };
  // Re-evaluate from the current clock, including after suspended/background tabs resume.
  const watchClock = (browser, page, refresh) => {
    let timer;
    const run = () => {
      if (timer !== undefined) browser.clearTimeout(timer);
      const now = Date.now();
      const deadlines = refresh(now) || [];
      const future = deadlines.filter(t => Number.isFinite(t) && t > now);
      const delay = Math.max(1, Math.min(60000, future.length ? Math.min(...future) - now : 60000));
      timer = browser.setTimeout(run, delay);
    };
    browser.addEventListener('pageshow', run);
    browser.addEventListener('focus', run);
    page.addEventListener('visibilitychange', run);
    run();
  };
  const readOffer = node => {
    const d = node.dataset;
    const offer = { checked_at: d.psCheckedAt, valid_until: d.psValidUntil, identity_verified: d.psIdentity === 'true',
      state: d.psState, total_scope_complete: d.psComplete === 'true', condition: d.psCondition };
    for (const [key, attr] of [['price_yen', 'data-ps-price-yen'], ['shipping_yen', 'data-ps-shipping-yen'], ['required_items_yen', 'data-ps-required-items-yen']]) {
      offer[key] = node.hasAttribute(attr) ? numberInput(node.getAttribute(attr)).value : null;
    }
    return offer;
  };
  const mount = (root, page, browser) => {
    if (root.dataset.psMounted) return;
    const find = s => root.querySelector(s), all = s => [...root.querySelectorAll(s)];
    const create = (tag, text, attributes = {}) => {
      const node = page.createElement(tag);
      node.textContent = text;
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
      return node;
    };
    // CMS content carries only inert, escaped configuration; controls are created here.
    const optionsFrom = (node, name) => {
      try {
        const options = JSON.parse(node.getAttribute(name));
        if (!Array.isArray(options) || !options.length || options.length > 16 ||
            options.some(o => !o || typeof o.id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(o.id) ||
              typeof o.label !== 'string' || !o.label.trim() || o.label.length > 200) ||
            new Set(options.map(o => o.id)).size !== options.length) return null;
        return options;
      } catch (_) { return null; }
    };
    const addSelect = (container, label, attributes, options) => {
      const wrapper = create('label', label), select = create('select', '', attributes);
      for (const option of options) select.append(create('option', option.label, { value: option.id }));
      wrapper.append(select); container.append(wrapper);
    };
    // Each enhancement is independent: a missing part disables only that control and
    // never removes the static candidates, notes or links already in the document.
    const guarded = fn => { try { fn(); } catch (_) { /* static content stays usable */ } };
    const purposeMode = root.dataset.psPurposeMode || 'advisory';
    const budgetMode = root.dataset.psBudgetMode || 'advisory';
    guarded(() => {
      const budgetMount = find('[data-ps-purpose-options]');
      if (!budgetMount) return;
      const options = purposeMode === 'links' ? null : optionsFrom(budgetMount, 'data-ps-purpose-options');
      if (purposeMode !== 'links' && !options) return;
      if (options) addSelect(budgetMount, '優先する条件', { 'data-ps-purpose': '' }, [{ id: '', label: 'すべての条件' }, ...options]);
      if (budgetMode !== 'off') {
        const label = create('label', '購入予算の上限（円）');
        label.append(create('input', '', { 'data-ps-budget': '', type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '例：50000' }));
        budgetMount.append(label);
      }
      if (options || budgetMode !== 'off') budgetMount.append(create('p', '予算は未入力です。', { 'data-ps-budget-result': '', role: 'status', 'aria-live': 'polite' }));
    });
    const sellers = [];
    for (const node of all('[data-ps-offer]')) {
      const owner = node.closest('[data-ps-product]');
      if (owner) sellers.push({ node, offer: readOffer(node), product: owner.dataset.psProduct });
    }
    const cards = all('.ps-product');
    const budget = find('[data-ps-budget]'), purpose = find('[data-ps-purpose]'), budgetResult = find('[data-ps-budget-result]');
    // Advisory only: purpose and budget annotate cards and never hide a published candidate.
    const refreshBudget = now => {
      const parsed = budget ? numberInput(budget.value) : { value: null, invalid: false };
      if (budget) budget.setAttribute('aria-invalid', String(parsed.invalid));
      const purposeValue = purpose ? purpose.value : '';
      let matched = 0, unknown = 0, over = 0;
      for (const card of cards) {
        card.hidden = false;
        const cases = (card.dataset.psUseCases || '').split(/\s+/).filter(Boolean);
        const purposeMatch = Boolean(purposeValue) && cases.includes(purposeValue);
        card.dataset.psPriorityMatch = String(purposeMatch);
        if (purposeMatch) matched++;
        const state = budget ? budgetState(sellers.filter(s => s.product === card.dataset.psProduct).map(s => s.offer), parsed.value, now) : 'UNKNOWN';
        if (budget && parsed.value !== null && !parsed.invalid) { if (state === 'UNKNOWN') unknown++; if (state === 'OVER_BUDGET') over++; }
        const status = card.querySelector('[data-ps-product-budget]');
        if (status) status.textContent = !budget ? '' : parsed.invalid ? '予算未判定：入力を確認してください。' : parsed.value === null ? '' :
          state === 'WITHIN_BUDGET' ? '確認範囲の購入総額が予算内の販売条件があります。配送先・必要品の適用を再確認してください。' :
          state === 'OVER_BUDGET' ? '確認した購入総額は予算を超えています。候補は表示したままです。' : '予算未判定：総額・型番・販売状態・鮮度の確認が必要です。不明費用は0円ではありません。';
      }
      if (budgetResult) budgetResult.textContent = budget && parsed.invalid ? '予算は0以上の数値で入力してください。予算による判定は保留しています。' :
        `${cards.length}候補を表示。${purpose && purposeValue ? `優先する条件に合う候補は${matched}件です。` : ''}${budget ? parsed.value === null ? '予算は未入力です。' : `予算超過${over}件、予算未判定${unknown}件を含め、候補は隠していません。` : ''}性能の評価順は変えていません。仕様表と販売条件は全候補を確認できます。`;
    };
    guarded(() => {
      if (budget) budget.addEventListener('input', () => refreshBudget(Date.now()));
      if (purpose) purpose.addEventListener('change', () => refreshBudget(Date.now()));
      const budgetControls = find('.ps-budget-controls');
      if (budgetControls && (budget || purpose)) budgetControls.hidden = false;
    });
    guarded(() => {
      const pairMount = find('[data-ps-pair-options]');
      if (!pairMount) return;
      const options = optionsFrom(pairMount, 'data-ps-pair-options');
      if (!options || options.length !== 4) return;
      addSelect(pairMount, '候補A', { 'data-ps-pair': 'a' }, options);
      addSelect(pairMount, '候補B', { 'data-ps-pair': 'b' }, options);
      const label = create('label', '');
      label.append(create('input', '', { type: 'checkbox', 'data-ps-differences': '' }), page.createTextNode('同じ公表値の行を隠す'));
      pairMount.append(label, create('button', '4候補に戻す', { type: 'button', 'data-ps-pair-reset': '' }),
        create('p', '', { 'data-ps-pair-result': '', role: 'status', 'aria-live': 'polite' }));
    });
    guarded(() => {
      const pairControls = find('.ps-pair-controls');
      if (!pairControls) return;
      const a = find('[data-ps-pair="a"]'), b = find('[data-ps-pair="b"]'), diff = find('[data-ps-differences]');
      const table = find('.ps-comparison'), result = find('[data-ps-pair-result]'), reset = find('[data-ps-pair-reset]');
      const columns = table ? [...table.querySelectorAll('thead [data-ps-product]')].map(n => n.dataset.psProduct) : [];
      const validSelect = node => node && node.tagName === 'SELECT' && node.options.length === columns.length &&
        new Set([...node.options].map(o => o.value)).size === columns.length && [...node.options].every(o => columns.includes(o.value));
      // Every part is checked before any listener: with a missing part the operation stays
      // hidden and the full table remains readable; in-page links do not depend on it.
      if (!(a && b && diff && table && result && reset && columns.length >= 2 && new Set(columns).size === columns.length && validSelect(a) && validSelect(b))) {
        pairControls.hidden = true;
        return;
      }
      let paired = false;
      const update = () => {
        const duplicate = paired && a.value === b.value;
        const selected = paired && !duplicate ? [a.value, b.value] : [];
        // Only the main table columns change; cards, notes and detail tables keep all candidates.
        for (const cell of table.querySelectorAll('[data-ps-product]')) cell.hidden = selected.length > 0 && !selected.includes(cell.dataset.psProduct);
        let hiddenRows = 0;
        for (const row of table.querySelectorAll('tbody tr')) {
          const cells = [...row.querySelectorAll('td[data-ps-product]')].filter(c => !c.hidden);
          const values = cells.map(c => c.textContent);
          const unconfirmed = cells.some(c => c.dataset.psFactState && c.dataset.psFactState !== 'KNOWN');
          row.hidden = !row.hasAttribute('data-ps-keep-row') && diff.checked && !duplicate && !unconfirmed && sameKnownValues(values);
          if (row.hidden) hiddenRows++;
        }
        result.textContent = duplicate ? '同じ商品が選ばれています。別の商品を選んでください。比較表は4候補を表示しています。' :
          `${selected.length ? '選んだ2候補' : '4候補'}を表示。${hiddenRows}行を非表示にしました。未確認を含む行は残しています。`;
      };
      a.addEventListener('change', () => { paired = true; update(); });
      b.addEventListener('change', () => { paired = true; update(); });
      diff.addEventListener('change', update);
      reset.addEventListener('click', () => { paired = false; diff.checked = false; a.selectedIndex = 0; if (b.options.length > 1) b.selectedIndex = 1; update(); });
      if (b.options.length > 1) b.selectedIndex = 1;
      update();
      pairControls.hidden = false;
    });
    all('[data-ps-installation]').forEach((container, index) => guarded(() => {
      const controls = container.querySelector('.ps-installation-controls');
      if (!controls) return;
      let required;
      try { required = JSON.parse(container.dataset.psInstallation); } catch (_) { return; }
      if (!isRecord(required)) return;
      // An unknown reference key is a configuration error: no inputs, static notes stay.
      const initial = assessInstallation(required, {});
      const fieldset = create('fieldset', '');
      fieldset.append(create('legend', '置き場所の寸法をmmで照合する'));
      fieldset.append(create('p', '置く予定の位置で、本体用の空間・開扉時の空間・本体から各方向に残る余白を別々に測ります。開扉時は本体を含む必要寸法です。基準が未確認の項目には入力欄を作りません。入力は保存・送信しません。'));
      const inputs = {}, statuses = {};
      for (const f of initial.fields) {
        const id = `ps-install-${index}-${f.key}`, helpId = `${id}-help`;
        const group = create('div', '', { class: 'ps-installation-field' });
        statuses[f.key] = create('p', '', { id: helpId });
        if (f.input_required) {
          inputs[f.key] = create('input', '', { id, type: 'text', inputmode: 'decimal', autocomplete: 'off', 'aria-describedby': helpId });
          group.append(create('label', `${f.label}（mm）`, { for: id }), inputs[f.key], statuses[f.key]);
        } else {
          statuses[f.key].textContent = f.reference_state === 'INVALID' ? '基準データの不備があるため、この項目は照合できません。型番の公式資料で確認してください。' :
            'サイト側の基準が未確認のため、この項目は照合できません。利用者の未入力ではありません。型番の公式資料で確認してください。';
          group.append(create('p', f.label, { class: 'ps-installation-label' }), statuses[f.key]);
        }
        fieldset.append(group);
      }
      const result = create('p', '', { role: 'status', 'aria-live': 'polite', class: 'ps-installation-result' });
      const update = () => {
        let check;
        try {
          check = assessInstallation(required, Object.fromEntries(Object.entries(inputs).map(([key, node]) => [key, node.value])));
        } catch (_) {
          result.textContent = '設定不備のため数値照合を停止しました。上の静的な条件と注意をご確認ください。';
          return;
        }
        for (const f of check.fields) {
          if (!inputs[f.key]) continue;
          inputs[f.key].setAttribute('aria-invalid', String(f.input_state === 'INVALID'));
          statuses[f.key].textContent = `照合基準：${f.required_mm}mm。${f.input_state === 'INVALID' ? '0以上の数値で入力してください。' :
            f.match_state === 'MISMATCH' ? `不足：${f.shortfall_mm}mm。` : f.match_state === 'MATCH' ? '数値一致。' : '未入力。'}`;
        }
        result.textContent = installationSummary(check);
      };
      fieldset.addEventListener('input', update);
      const reset = create('button', '測定値をクリア', { type: 'button' });
      reset.addEventListener('click', () => { for (const input of Object.values(inputs)) input.value = ''; update(); });
      const staged = page.createDocumentFragment();
      staged.append(fieldset, reset, result);
      update();
      controls.append(staged);
      controls.hidden = false;
    }));
    const formatter = new Intl.NumberFormat('ja-JP');
    watchClock(browser, page, now => {
      const deadlines = [];
      for (const { node, offer } of sellers) {
        const cost = offerCost(offer, now), status = node.querySelector('.ps-price-status');
        const expiry = Math.min(time(offer.valid_until), time(offer.checked_at) + DAY);
        if (node.dataset && 'psPriceState' in node.dataset) {
          node.dataset.psPriceState = !money(offer.price_yen) || !Number.isFinite(expiry) || time(offer.checked_at) > now ? 'UNKNOWN'
            : now >= expiry ? 'EXPIRED' : 'CURRENT';
        }
        deadlines.push(expiry);
        if (status) status.textContent = cost.state === 'CURRENT' ? `確認した費目の購入総額：${formatter.format(cost.total)}円。表示期限：${new Date(expiry).toLocaleString('ja-JP')}。販売先で現在条件を再確認してください。` :
          `${cost.state === 'EXPIRED' ? '販売条件の表示期限切れ。' : '購入総額は未確認。'}${cost.subtotal === null ? '' : `確認時の費目の小計：${formatter.format(cost.subtotal)}円。`}現在の購入総額や予算内とは判断できません。販売先で再確認してください。`;
      }
      guarded(() => refreshBudget(now));
      return deadlines;
    });
    root.dataset.psMounted = '1';
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = { numberInput, offerCost, budgetState, sameKnownValues, checkInstallation, parseMeasurement, assessInstallation, installationSummary, watchClock, mount };
  if (typeof document !== 'undefined' && typeof window !== 'undefined') document.querySelectorAll('.ps-article').forEach(root => mount(root, document, window));
})();
