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
    const budgetMount = find('[data-ps-purpose-options]');
    if (budgetMount) {
      const options = optionsFrom(budgetMount, 'data-ps-purpose-options');
      if (options) {
        addSelect(budgetMount, '優先する条件', { 'data-ps-purpose': '' }, [{ id: '', label: 'すべての条件' }, ...options]);
        const label = create('label', '購入予算の上限（円）');
        label.append(create('input', '', { 'data-ps-budget': '', type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '例：50000' }));
        budgetMount.append(label, create('p', '予算は未入力です。', { 'data-ps-budget-result': '', role: 'status', 'aria-live': 'polite' }));
      }
    }
    const pairMount = find('[data-ps-pair-options]');
    if (pairMount) {
      const options = optionsFrom(pairMount, 'data-ps-pair-options');
      if (options && options.length === 4) {
        addSelect(pairMount, '候補A', { 'data-ps-pair': 'a' }, options);
        addSelect(pairMount, '候補B', { 'data-ps-pair': 'b' }, options);
        const label = create('label', '');
        label.append(create('input', '', { type: 'checkbox', 'data-ps-differences': '' }), page.createTextNode('同じ公表値の行を隠す'));
        pairMount.append(label, create('button', '4候補に戻す', { type: 'button', 'data-ps-pair-reset': '' }),
          create('p', '', { 'data-ps-pair-result': '', role: 'status', 'aria-live': 'polite' }));
      }
    }
    const sellers = all('[data-ps-offer]').map(node => ({ node, offer: readOffer(node), product: node.closest('[data-ps-product]').dataset.psProduct }));
    const cards = all('.ps-product[data-ps-product]');
    const budget = find('[data-ps-budget]'), purpose = find('[data-ps-purpose]'), budgetResult = find('[data-ps-budget-result]');
    const refreshBudget = now => {
      if (!budget || !purpose) return;
      const parsed = numberInput(budget.value);
      budget.setAttribute('aria-invalid', String(parsed.invalid));
      let visible = 0, unknown = 0;
      for (const card of cards) {
        const cases = (card.dataset.psUseCases || '').split(/\s+/).filter(Boolean);
        const purposeMatch = !purpose.value || !cases.length || cases.includes(purpose.value);
        const state = budgetState(sellers.filter(s => s.product === card.dataset.psProduct).map(s => s.offer), parsed.value, now);
        const hidden = !purposeMatch || state === 'OVER_BUDGET';
        card.hidden = hidden;
        if (!hidden) { visible++; if (state === 'UNKNOWN') unknown++; }
        const status = card.querySelector('[data-ps-product-budget]');
        if (status) status.textContent = parsed.invalid ? '予算未判定：入力を確認してください。' : parsed.value === null ? '' :
          state === 'WITHIN_BUDGET' ? '確認範囲の購入総額が予算内の販売条件があります。配送先・必要品の適用を再確認してください。' :
          state === 'OVER_BUDGET' ? '確認した購入総額は予算を超えています。' : '予算未判定：総額・型番・販売状態・鮮度の確認が必要です。不明費用は0円ではありません。';
      }
      budgetResult.textContent = parsed.invalid ? '予算は0以上の数値で入力してください。予算による絞り込みは解除しています。' :
        `${visible}候補を表示。${parsed.value === null ? '予算は未入力です。' : `うち${unknown}候補は予算未判定として残しています。`}性能の評価順は変えていません。仕様表と販売条件は全候補を確認できます。`;
    };
    if (budget && purpose) {
      budget.addEventListener('input', () => refreshBudget(Date.now()));
      purpose.addEventListener('change', () => refreshBudget(Date.now()));
      find('.ps-budget-controls').hidden = false;
    }
    const a = find('[data-ps-pair="a"]'), b = find('[data-ps-pair="b"]'), diff = find('[data-ps-differences]');
    if (a && b && diff) {
      const table = find('.ps-comparison'), result = find('[data-ps-pair-result]');
      let paired = false;
      const update = () => {
        const duplicate = paired && a.value === b.value;
        const selected = paired && !duplicate ? [a.value, b.value] : [];
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
      find('[data-ps-pair-reset]').addEventListener('click', () => { paired = false; diff.checked = false; update(); });
      if (b.options.length > 1) b.selectedIndex = 1;
      update();
      find('.ps-pair-controls').hidden = false;
    }
    all('[data-ps-installation]').forEach((container, index) => {
      let required;
      try { required = JSON.parse(container.dataset.psInstallation); } catch (_) { return; }
      if (!required || typeof required !== 'object' || Array.isArray(required)) return;
      const controls = container.querySelector('.ps-installation-controls');
      const fieldset = create('fieldset', '');
      fieldset.append(create('legend', '置き場所の寸法をmmで照合する'));
      fieldset.append(create('p', '置く予定の位置で、本体用の空間・開扉時の空間・本体から各方向に残る余白を別々に測ります。開扉時は本体を含む必要寸法です。入力は保存・送信しません。'));
      const inputs = {}, statuses = {};
      for (const [key, label] of installationFields) {
        const id = `ps-install-${index}-${key}`, helpId = `${id}-help`;
        const group = create('div', '', { class: 'ps-installation-field' });
        inputs[key] = create('input', '', { id, type: 'text', inputmode: 'decimal', autocomplete: 'off', 'aria-describedby': helpId });
        statuses[key] = create('p', '', { id: helpId });
        group.append(create('label', `${label}（mm）`, { for: id }), inputs[key], statuses[key]);
        fieldset.append(group);
      }
      const result = create('p', '', { role: 'status', 'aria-live': 'polite', class: 'ps-installation-result' });
      const update = () => {
        const check = checkInstallation(required, Object.fromEntries(Object.entries(inputs).map(([key, node]) => [key, node.value])));
        for (const f of check.fields) {
          inputs[f.key].setAttribute('aria-invalid', String(f.invalid));
          statuses[f.key].textContent = `${money(required[f.key]) ? `照合基準：${required[f.key]}mm。` : '照合基準：未確認。'}${f.invalid ? '0以上の数値で入力してください。' : f.state === 'MISMATCH' ? '条件不一致：入力寸法が不足しています。' : f.state === 'CONFIRMED' ? '確認済み：この数値条件を満たします。' : '未確認：照合基準と測定値の両方が必要です。'}`;
        }
        result.textContent = `${check.state === 'MISMATCH' ? '条件不一致：不足する寸法があります。' : check.state === 'CONFIRMED' ? '確認済み：9項目の寸法条件と入力値の照合を満たしました。' : '未確認：照合できていない寸法が残っています。'}`;
      };
      fieldset.addEventListener('input', update);
      const reset = create('button', '測定値をクリア', { type: 'button' });
      reset.addEventListener('click', () => { for (const input of Object.values(inputs)) input.value = ''; update(); });
      controls.append(fieldset, reset, result);
      update();
      controls.hidden = false;
    });
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
      refreshBudget(now);
      return deadlines;
    });
    root.dataset.psMounted = '1';
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = { numberInput, offerCost, budgetState, sameKnownValues, checkInstallation, watchClock, mount };
  if (typeof document !== 'undefined' && typeof window !== 'undefined') document.querySelectorAll('.ps-article').forEach(root => mount(root, document, window));
})();
