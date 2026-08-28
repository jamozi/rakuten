(() => {
  'use strict';

  const RESULT_STATES = Object.freeze(['PASS', 'FAIL', 'UNKNOWN', 'STALE', 'BLOCKED', 'NO_MATCH']);
  const STATE_PRIORITY = Object.freeze({
    PASS: 0,
    NO_MATCH: 1,
    UNKNOWN: 2,
    STALE: 3,
    BLOCKED: 4,
    FAIL: 5,
  });
  const RULES = Object.freeze([
    Object.freeze({
      carrier: 'ANA',
      journeyScope: 'DOMESTIC',
      aircraft: 'LARGE',
      fareOrOption: null,
      effectiveFrom: '2026-08-28T06:41:52+09:00',
      effectiveUntil: null,
      maxDimensions: Object.freeze(['55', '40', '25']),
      maxSum: '115',
      maxWeight: '10',
      maxItems: 2,
      maxCarryOnCount: 1,
      maxPersonalItemCount: 1,
      requiresPersonalItemUnderseat: false,
      orientation: 'PERMUTABLE',
      checkedAt: '2026-08-28T06:41:52+09:00',
      nextReviewAt: '2026-09-27T06:41:52+09:00',
      sourceId: 'SRC-V2-ANA-CARRY-ON',
      status: 'FRESH',
    }),
    Object.freeze({
      carrier: 'ANA',
      journeyScope: 'DOMESTIC',
      aircraft: 'SMALL',
      fareOrOption: null,
      effectiveFrom: '2026-08-28T06:41:52+09:00',
      effectiveUntil: null,
      maxDimensions: Object.freeze(['45', '35', '20']),
      maxSum: '100',
      maxWeight: '10',
      maxItems: 2,
      maxCarryOnCount: 1,
      maxPersonalItemCount: 1,
      requiresPersonalItemUnderseat: false,
      orientation: 'PERMUTABLE',
      checkedAt: '2026-08-28T06:41:52+09:00',
      nextReviewAt: '2026-09-27T06:41:52+09:00',
      sourceId: 'SRC-V2-ANA-CARRY-ON',
      status: 'FRESH',
    }),
    Object.freeze({
      carrier: 'JAL',
      journeyScope: 'DOMESTIC',
      aircraft: 'LARGE',
      fareOrOption: null,
      effectiveFrom: '2026-08-28T06:41:52+09:00',
      effectiveUntil: null,
      maxDimensions: Object.freeze(['55', '40', '25']),
      maxSum: '115',
      maxWeight: '10',
      maxItems: 2,
      maxCarryOnCount: 1,
      maxPersonalItemCount: 1,
      requiresPersonalItemUnderseat: false,
      orientation: 'PERMUTABLE',
      checkedAt: '2026-08-28T06:41:52+09:00',
      nextReviewAt: '2026-09-27T06:41:52+09:00',
      sourceId: 'SRC-V2-JAL-CARRY-ON',
      status: 'FRESH',
    }),
    Object.freeze({
      carrier: 'JAL',
      journeyScope: 'DOMESTIC',
      aircraft: 'SMALL',
      fareOrOption: null,
      effectiveFrom: '2026-08-28T06:41:52+09:00',
      effectiveUntil: null,
      maxDimensions: Object.freeze(['45', '35', '20']),
      maxSum: '100',
      maxWeight: '10',
      maxItems: 2,
      maxCarryOnCount: 1,
      maxPersonalItemCount: 1,
      requiresPersonalItemUnderseat: false,
      orientation: 'PERMUTABLE',
      checkedAt: '2026-08-28T06:41:52+09:00',
      nextReviewAt: '2026-09-27T06:41:52+09:00',
      sourceId: 'SRC-V2-JAL-CARRY-ON',
      status: 'FRESH',
    }),
    Object.freeze({
      carrier: 'PEACH',
      journeyScope: 'ALL',
      aircraft: null,
      fareOrOption: null,
      effectiveFrom: '2026-08-28T06:41:52+09:00',
      effectiveUntil: null,
      maxDimensions: Object.freeze(['115', '115', '115']),
      maxSum: '115',
      maxWeight: '7',
      maxItems: 2,
      maxCarryOnCount: 1,
      maxPersonalItemCount: 1,
      requiresPersonalItemUnderseat: false,
      orientation: 'PERMUTABLE',
      checkedAt: '2026-08-28T06:41:52+09:00',
      nextReviewAt: '2026-09-27T06:41:52+09:00',
      sourceId: 'SRC-V2-PEACH-CARRY-ON',
      status: 'FRESH',
    }),
    Object.freeze({
      carrier: 'JETSTAR_JAPAN',
      journeyScope: 'ALL',
      aircraft: null,
      fareOrOption: 'STANDARD_7KG',
      effectiveFrom: '2026-08-28T06:41:52+09:00',
      effectiveUntil: null,
      maxDimensions: Object.freeze(['56', '36', '23']),
      maxSum: null,
      maxWeight: '7',
      maxItems: 2,
      maxCarryOnCount: 1,
      maxPersonalItemCount: 1,
      requiresPersonalItemUnderseat: true,
      orientation: 'ORDERED',
      checkedAt: '2026-08-28T06:41:52+09:00',
      nextReviewAt: '2026-09-27T06:41:52+09:00',
      sourceId: 'SRC-V2-JETSTAR-CARRY-ON',
      status: 'FRESH',
    }),
  ]);
  const DECIMAL = /^(?:0|[1-9][0-9]*)(?:\.([0-9]+))?$/u;
  const JST_LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/u;
  const JST_OFFSET_MS = 9 * 60 * 60 * 1000;

  function parseDecimal(raw) {
    const value = String(raw).trim();
    const match = DECIMAL.exec(value);
    if (match === null) return null;
    const fraction = match[1] || '';
    return Object.freeze({
      coefficient: BigInt(value.replace('.', '')),
      scale: fraction.length,
    });
  }

  function align(value, scale) {
    return value.coefficient * 10n ** BigInt(scale - value.scale);
  }

  function compare(left, right) {
    const scale = Math.max(left.scale, right.scale);
    const leftAligned = align(left, scale);
    const rightAligned = align(right, scale);
    return leftAligned < rightAligned ? -1 : leftAligned > rightAligned ? 1 : 0;
  }

  function add(left, right) {
    const scale = Math.max(left.scale, right.scale);
    return Object.freeze({
      coefficient: align(left, scale) + align(right, scale),
      scale,
    });
  }

  function parseJstLocalInstant(raw) {
    const match = JST_LOCAL.exec(String(raw));
    if (match === null) return null;
    const parts = match.slice(1).map((value) => Number(value || '0'));
    const [year, month, day, hour, minute, second] = parts;
    const utc = Date.UTC(year, month - 1, day, hour - 9, minute, second);
    const local = new Date(utc + JST_OFFSET_MS);
    if (
      local.getUTCFullYear() !== year ||
      local.getUTCMonth() + 1 !== month ||
      local.getUTCDate() !== day ||
      local.getUTCHours() !== hour ||
      local.getUTCMinutes() !== minute ||
      local.getUTCSeconds() !== second
    ) {
      return null;
    }
    return utc;
  }

  function parseRuleInstant(raw) {
    const value = Date.parse(raw);
    return Number.isFinite(value) ? value : null;
  }

  function permutations(values) {
    return [
      [values[0], values[1], values[2]],
      [values[0], values[2], values[1]],
      [values[1], values[0], values[2]],
      [values[1], values[2], values[0]],
      [values[2], values[0], values[1]],
      [values[2], values[1], values[0]],
    ];
  }

  function evaluateRule(input, rule) {
    if (rule.status === 'BLOCKED') {
      return { state: 'BLOCKED', reasons: ['根拠確認が完了していないルールです。'], rule };
    }
    if (rule.status === 'HARD_STALE') {
      return { state: 'STALE', reasons: ['公式情報の再確認期限を過ぎています。'], rule };
    }
    const reasons = [];
    if (rule.maxDimensions !== null) {
      const maximums = rule.maxDimensions.map(parseDecimal);
      const candidates =
        rule.orientation === 'PERMUTABLE' ? permutations(input.dimensions) : [input.dimensions];
      const fits = candidates.some((candidate) =>
        candidate.every((value, index) => compare(value, maximums[index]) <= 0),
      );
      if (!fits) reasons.push('外寸の少なくとも1辺が上限を超えています。');
    }
    if (rule.maxSum !== null) {
      const sum = add(add(input.dimensions[0], input.dimensions[1]), input.dimensions[2]);
      if (compare(sum, parseDecimal(rule.maxSum)) > 0) {
        reasons.push('3辺の合計が上限を超えています。');
      }
    }
    if (compare(input.weight, parseDecimal(rule.maxWeight)) > 0) {
      reasons.push('身の回り品を含む合計重量が上限を超えています。');
    }
    if (input.items > rule.maxItems) {
      reasons.push('身の回り品を含む合計個数が上限を超えています。');
    }
    if (input.carryOnCount > rule.maxCarryOnCount) {
      reasons.push('機内持ち込み手荷物の個数が上限を超えています。');
    }
    if (input.personalItemCount > rule.maxPersonalItemCount) {
      reasons.push('身の回り品の個数が上限を超えています。');
    }
    if (
      reasons.length === 0 &&
      rule.requiresPersonalItemUnderseat &&
      input.personalItemCount > 0 &&
      !input.personalItemUnderseatConfirmed
    ) {
      return {
        state: 'UNKNOWN',
        reasons: ['身の回り品を前の座席の下に収納できるか確認してください。'],
        rule,
      };
    }
    return {
      state: reasons.length === 0 ? 'PASS' : 'FAIL',
      reasons:
        reasons.length === 0 ? ['外寸・合計重量・個数は記録済みルールの範囲内です。'] : reasons,
      rule,
    };
  }

  function evaluateSegment(input, segment) {
    const { carrier, journeyScope, aircraft, fareOrOption, departureAtJst } = segment;
    if (carrier === '') {
      return { state: 'UNKNOWN', reasons: ['航空会社が選択されていません。'], rules: [] };
    }
    const carrierRules = RULES.filter((rule) => rule.carrier === carrier);
    if (carrierRules.length === 0) {
      return { state: 'NO_MATCH', reasons: ['一致する記録済みルールがありません。'], rules: [] };
    }
    const departureInstant = parseJstLocalInstant(departureAtJst);
    if (departureInstant === null) {
      return {
        state: 'UNKNOWN',
        reasons: ['出発日時（JST）を入力してください。'],
        rules: carrierRules,
      };
    }
    if (!['DOMESTIC', 'INTERNATIONAL'].includes(journeyScope)) {
      return {
        state: 'UNKNOWN',
        reasons: ['国内線または国際線の区分を確認してください。'],
        rules: carrierRules,
      };
    }
    const scopeRules = carrierRules.filter(
      (rule) => rule.journeyScope === 'ALL' || rule.journeyScope === journeyScope,
    );
    if (scopeRules.length === 0) {
      return {
        state: 'NO_MATCH',
        reasons: ['この路線区分に一致する記録済みルールがありません。'],
        rules: carrierRules,
      };
    }
    const effectiveRules = scopeRules.filter((rule) => {
      const effectiveFrom = parseRuleInstant(rule.effectiveFrom);
      const effectiveUntil =
        rule.effectiveUntil === null ? null : parseRuleInstant(rule.effectiveUntil);
      return (
        effectiveFrom !== null &&
        effectiveFrom <= departureInstant &&
        (rule.effectiveUntil === null ||
          (effectiveUntil !== null && departureInstant < effectiveUntil))
      );
    });
    if (effectiveRules.length === 0) {
      return {
        state: 'UNKNOWN',
        reasons: ['出発日に適用できる記録済みルールがありません。'],
        rules: carrierRules,
      };
    }
    const staleRules = effectiveRules.filter((rule) => {
      const nextReviewAt = parseRuleInstant(rule.nextReviewAt);
      return nextReviewAt === null || departureInstant >= nextReviewAt;
    });
    if (staleRules.length > 0) {
      return {
        state: staleRules.some((rule) => parseRuleInstant(rule.nextReviewAt) === null)
          ? 'UNKNOWN'
          : 'STALE',
        reasons: [
          staleRules.some((rule) => parseRuleInstant(rule.nextReviewAt) === null)
            ? '公式情報の再確認期限を検証できません。'
            : '出発日時が公式情報の再確認期限以後です。航空会社の公式ページを再確認してください。',
        ],
        rules: staleRules,
      };
    }
    const aircraftRequired = effectiveRules.some((rule) => rule.aircraft !== null);
    const fareRequired = effectiveRules.some((rule) => rule.fareOrOption !== null);
    const applicabilityMissing =
      (aircraftRequired && aircraft === '') || (fareRequired && fareOrOption === '');
    const matchingRules = effectiveRules.filter(
      (rule) =>
        (aircraft === '' || rule.aircraft === null || rule.aircraft === aircraft) &&
        (rule.fareOrOption === null || rule.fareOrOption === fareOrOption),
    );
    if (matchingRules.length === 0) {
      return {
        state: 'UNKNOWN',
        reasons: ['機材または運賃・オプションの適用条件を確認できません。'],
        rules: effectiveRules,
      };
    }
    const specificity = (rule) =>
      Number(rule.aircraft !== null) + Number(rule.fareOrOption !== null);
    const maximumSpecificity = Math.max(...matchingRules.map(specificity));
    const exactRules = matchingRules.filter((rule) => specificity(rule) === maximumSpecificity);
    const results = exactRules.map((rule) => evaluateRule(input, rule));
    const allFail = results.every((result) => result.state === 'FAIL');
    const allPass = results.every((result) => result.state === 'PASS');
    if (!applicabilityMissing && (allFail || allPass || results.length === 1)) {
      const selected = results.reduce((current, result) =>
        STATE_PRIORITY[result.state] > STATE_PRIORITY[current.state] ? result : current,
      );
      return { state: selected.state, reasons: selected.reasons, rules: exactRules };
    }
    return {
      state: 'UNKNOWN',
      reasons: ['座席数・機材・運賃によって判定が変わります。搭乗便の条件を確認してください。'],
      rules: exactRules,
    };
  }

  function readInput(form) {
    const values = new FormData(form);
    const dimensionValues = ['height', 'width', 'depth'].map((name) =>
      parseDecimal(values.get(name)),
    );
    const weight = parseDecimal(values.get('weight'));
    const carryOnText = String(values.get('carry-on-count') || '').trim();
    const personalText = String(values.get('personal-item-count') || '').trim();
    const carryOnCount = /^(?:0|[1-9][0-9]*)$/u.test(carryOnText)
      ? Number(carryOnText)
      : Number.NaN;
    const personalItemCount = /^(?:0|[1-9][0-9]*)$/u.test(personalText)
      ? Number(personalText)
      : Number.NaN;
    const items = carryOnCount + personalItemCount;
    const invalid = [];
    if (dimensionValues.some((value) => value === null || value.coefficient <= 0n)) {
      invalid.push('外寸3項目を0より大きい数値で入力してください。');
    }
    if (weight === null || weight.coefficient <= 0n) {
      invalid.push('合計重量を0より大きい数値で入力してください。');
    }
    if (
      !Number.isSafeInteger(carryOnCount) ||
      carryOnCount < 0 ||
      !Number.isSafeInteger(personalItemCount) ||
      personalItemCount < 0 ||
      items < 1
    ) {
      invalid.push('機内持ち込み手荷物と身の回り品を、それぞれ0以上の整数で入力してください。');
    }
    const bagState = String(values.get('bag-state') || '');
    if (bagState !== 'NORMAL' && bagState !== 'EXPANDED') {
      invalid.push('通常時または拡張時を選択してください。');
    }
    if (values.get('appendages-included') !== 'yes') {
      invalid.push('キャスター・ハンドル・ポケットを含む外寸であることを確認してください。');
    }
    const carrier = String(values.get('carrier') || '');
    if (carrier === '') invalid.push('航空会社を選択してください。');
    return {
      invalid,
      input:
        invalid.length === 0
          ? {
              dimensions: dimensionValues,
              weight,
              items,
              carryOnCount,
              personalItemCount,
              bagState,
              appendagesIncluded: true,
              personalItemUnderseatConfirmed:
                values.get('personal-item-underseat-confirmed') === 'yes',
            }
          : null,
      segments: [
        {
          carrier,
          journeyScope: String(values.get('journey-scope') || ''),
          aircraft: String(values.get('aircraft') || ''),
          fareOrOption: String(values.get('fare-option') || ''),
          departureAtJst: String(values.get('departure-at-jst') || ''),
          label: '区間1',
        },
        {
          carrier: String(values.get('carrier-2') || ''),
          journeyScope: String(values.get('journey-scope-2') || ''),
          aircraft: String(values.get('aircraft-2') || ''),
          fareOrOption: String(values.get('fare-option-2') || ''),
          departureAtJst: String(values.get('departure-at-jst-2') || ''),
          label: '区間2',
          optional: true,
        },
      ],
    };
  }

  function evaluateDecision(input, segments) {
    const results = segments.map((segment) => evaluateSegment(input, segment));
    const state = results.reduce(
      (current, result) =>
        STATE_PRIORITY[result.state] > STATE_PRIORITY[current] ? result.state : current,
      'PASS',
    );
    return Object.freeze({
      results: Object.freeze(results),
      state,
      segments: Object.freeze(results.map((result) => result.state)),
    });
  }

  function evaluateContractCase(bag, segments) {
    const dimensions = bag.dimensions.map(parseDecimal);
    const weight = parseDecimal(bag.weight);
    const carryOnCount = /^(?:0|[1-9][0-9]*)$/u.test(String(bag.carryOnCount))
      ? Number(bag.carryOnCount)
      : Number.NaN;
    const personalItemCount = /^(?:0|[1-9][0-9]*)$/u.test(String(bag.personalItemCount))
      ? Number(bag.personalItemCount)
      : Number.NaN;
    const items = carryOnCount + personalItemCount;
    if (
      dimensions.length !== 3 ||
      dimensions.some((value) => value === null || value.coefficient <= 0n) ||
      weight === null ||
      weight.coefficient <= 0n ||
      !Number.isSafeInteger(carryOnCount) ||
      !Number.isSafeInteger(personalItemCount) ||
      carryOnCount < 0 ||
      personalItemCount < 0 ||
      items < 1 ||
      !['NORMAL', 'EXPANDED'].includes(bag.bagState) ||
      bag.appendagesIncluded !== true
    ) {
      return Object.freeze({
        state: 'UNKNOWN',
        segments: Object.freeze(segments.map(() => 'UNKNOWN')),
      });
    }
    return evaluateDecision(
      Object.freeze({
        appendagesIncluded: true,
        bagState: bag.bagState,
        carryOnCount,
        dimensions,
        items,
        personalItemCount,
        personalItemUnderseatConfirmed: bag.personalItemUnderseatConfirmed === true,
        weight,
      }),
      segments,
    );
  }

  function renderErrors(form, messages) {
    const summary = form.querySelector('#form-errors');
    const list = summary.querySelector('ul');
    list.replaceChildren(
      ...messages.map((message) => {
        const item = document.createElement('li');
        item.textContent = message;
        return item;
      }),
    );
    summary.hidden = messages.length === 0;
    if (messages.length > 0) summary.focus();
  }

  function renderResult(panel, state, reasons, rules) {
    if (!RESULT_STATES.includes(state)) throw new TypeError('RESULT_STATE_INVALID');
    const heading = document.createElement('h3');
    const stateLabels = {
      PASS: 'PASS：入力した条件では記録済み規定内',
      FAIL: 'FAIL：規定を超える項目があります',
      UNKNOWN: 'UNKNOWN：条件を確定できません',
      STALE: 'STALE：公式情報の再確認が必要です',
      BLOCKED: 'BLOCKED：根拠確認が完了していません',
      NO_MATCH: 'NO_MATCH：一致する記録済み条件がありません',
    };
    heading.textContent = stateLabels[state];
    const list = document.createElement('ul');
    list.replaceChildren(
      ...reasons.map((reason) => {
        const item = document.createElement('li');
        item.textContent = reason;
        return item;
      }),
    );
    const evidence = document.createElement('p');
    evidence.className = 'meta';
    const sourceIds = [...new Set(rules.map((rule) => rule.sourceId))];
    const checkedDates = [...new Set(rules.map((rule) => rule.checkedAt))];
    evidence.textContent =
      sourceIds.length === 0
        ? '根拠ルール：未確定'
        : `根拠 ${sourceIds.join(' / ')}・確認 ${checkedDates.join(' / ')}`;
    const finalCheck = document.createElement('p');
    finalCheck.textContent =
      state === 'PASS'
        ? '航空会社の公式ページで搭乗便の最新条件を最終確認してください。'
        : '購入より先に、不足条件または超過項目を確認してください。';
    panel.replaceChildren(heading, list, evidence, finalCheck);
    panel.dataset.state = state;
  }

  function initialize(form) {
    const panel = document.querySelector('#checker-result');
    if (!(panel instanceof HTMLElement)) return;
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const parsed = readInput(form);
      renderErrors(form, parsed.invalid);
      if (parsed.input === null) {
        renderResult(panel, 'UNKNOWN', parsed.invalid, []);
        return;
      }
      const activeSegments = parsed.segments.filter(
        (segment) => !segment.optional || segment.carrier !== '',
      );
      const decision = evaluateDecision(parsed.input, activeSegments);
      renderResult(
        panel,
        decision.state,
        decision.results.flatMap((result) => result.reasons),
        decision.results.flatMap((result) => result.rules),
      );
    });
    form.addEventListener('reset', () => {
      queueMicrotask(() => {
        renderErrors(form, []);
        renderResult(panel, 'UNKNOWN', ['航空会社と荷物条件を入力してください。'], []);
      });
    });
  }

  if (globalThis.__RAOS_V2_TEST_MODE__ === true) {
    Object.defineProperty(globalThis, '__RAOS_V2_CHECKER_CONTRACT__', {
      configurable: false,
      enumerable: false,
      value: Object.freeze({
        evaluate: evaluateContractCase,
        resultStates: RESULT_STATES,
        rules: RULES,
      }),
      writable: false,
    });
  }
  if (typeof document === 'undefined') return;

  for (const form of document.querySelectorAll('#carry-on-checker')) {
    if (form instanceof HTMLFormElement) initialize(form);
  }
})();
