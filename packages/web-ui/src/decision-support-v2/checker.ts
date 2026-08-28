import type { DecisionSupportV2ResultState } from './contracts.ts';

export interface CarryOnBagInputV2 {
  readonly dimensionsCm: readonly [string, string, string];
  readonly combinedWeightKg: string;
  readonly carryOnCount: string;
  readonly personalItemCount: string;
  readonly state: 'NORMAL' | 'EXPANDED';
  readonly appendagesIncluded: true;
  readonly personalItemUnderseatConfirmed: boolean;
}

export interface CarryOnSegmentInputV2 {
  readonly segmentId: string;
  readonly carrierId: string;
  readonly journeyScope: 'DOMESTIC' | 'INTERNATIONAL' | 'UNKNOWN';
  readonly aircraftClass: string | null;
  readonly fareOrOption: string | null;
  readonly departureAtJst: string;
}

export interface AirlineRuleV2 {
  readonly ruleId: string;
  readonly carrierId: string;
  readonly journeyScope: 'DOMESTIC' | 'ALL';
  readonly dimensionsCm: readonly [string, string, string];
  readonly maxDimensionSumCm: string | null;
  readonly dimensionOrientation: 'ORDERED' | 'PERMUTABLE';
  readonly maxCombinedWeightKg: string;
  readonly maxItemCount: number;
  readonly maxCarryOnCount: number;
  readonly maxPersonalItemCount: number;
  readonly requiresPersonalItemUnderseat: boolean;
  readonly sourceId: string;
  readonly checkedAt: string;
  readonly sourceNextReviewAt: string;
  readonly effectiveFrom: string;
  readonly effectiveUntil: string | null;
  readonly freshness: 'FRESH' | 'DUE' | 'HARD_STALE';
  readonly applicability: Readonly<{
    aircraftClass: string | null;
    fareOrOption: string | null;
  }>;
  readonly blocked: boolean;
}

export interface SegmentDecisionV2 {
  readonly segmentId: string;
  readonly carrierId: string;
  readonly state: DecisionSupportV2ResultState;
  readonly reasons: readonly string[];
  readonly sourceIds: readonly string[];
  readonly checkedAt: string | null;
}

export interface DecisionSupportResultV2 {
  readonly state: DecisionSupportV2ResultState;
  readonly reasons: readonly string[];
  readonly segments: readonly SegmentDecisionV2[];
}

interface ExactDecimal {
  readonly coefficient: bigint;
  readonly scale: number;
}

const DECIMAL = /^(?:0|[1-9][0-9]*)(?:\.([0-9]+))?$/u;

function parseDecimal(value: string): ExactDecimal | null {
  const match = DECIMAL.exec(value.trim());
  if (match === null) return null;
  const fraction = match[1] ?? '';
  const digits = value.trim().replace('.', '');
  return Object.freeze({ coefficient: BigInt(digits), scale: fraction.length });
}

function compareDecimal(left: ExactDecimal, right: ExactDecimal): number {
  const scale = Math.max(left.scale, right.scale);
  const leftValue = left.coefficient * 10n ** BigInt(scale - left.scale);
  const rightValue = right.coefficient * 10n ** BigInt(scale - right.scale);
  return leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0;
}

function permutations(
  values: readonly [ExactDecimal, ExactDecimal, ExactDecimal],
): readonly (readonly [ExactDecimal, ExactDecimal, ExactDecimal])[] {
  const [first, second, third] = values;
  return Object.freeze([
    [first, second, third],
    [first, third, second],
    [second, first, third],
    [second, third, first],
    [third, first, second],
    [third, second, first],
  ]);
}

function dimensionsFit(
  input: readonly [ExactDecimal, ExactDecimal, ExactDecimal],
  maximum: readonly [ExactDecimal, ExactDecimal, ExactDecimal],
  orientation: AirlineRuleV2['dimensionOrientation'],
): boolean {
  const candidates = orientation === 'PERMUTABLE' ? permutations(input) : [input];
  return candidates.some((candidate) =>
    candidate.every((value, index) => compareDecimal(value, maximum[index]!) <= 0),
  );
}

function decimalSum(values: readonly ExactDecimal[]): ExactDecimal {
  const scale = Math.max(...values.map((value) => value.scale));
  return Object.freeze({
    coefficient: values.reduce(
      (total, value) => total + value.coefficient * 10n ** BigInt(scale - value.scale),
      0n,
    ),
    scale,
  });
}

function parseJstInstant(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$/u.test(value)) return null;
  const instant = Date.parse(value);
  return Number.isFinite(instant) ? instant : null;
}

function selectRule(
  segment: CarryOnSegmentInputV2,
  rules: readonly AirlineRuleV2[],
): AirlineRuleV2 | null | 'AMBIGUOUS' | 'APPLICABILITY_UNKNOWN' | 'SCOPE_NO_MATCH' {
  const carrierRules = rules.filter((rule) => rule.carrierId === segment.carrierId);
  if (carrierRules.length === 0) return null;
  const departureInstant = parseJstInstant(segment.departureAtJst);
  if (departureInstant === null) {
    return 'APPLICABILITY_UNKNOWN';
  }
  if (segment.journeyScope === 'UNKNOWN') return 'APPLICABILITY_UNKNOWN';
  const scopeRules = carrierRules.filter(
    (rule) => rule.journeyScope === 'ALL' || rule.journeyScope === segment.journeyScope,
  );
  if (scopeRules.length === 0) return 'SCOPE_NO_MATCH';
  const effectiveRules = scopeRules.filter((rule) => {
    const effectiveFrom = parseJstInstant(rule.effectiveFrom);
    const effectiveUntil =
      rule.effectiveUntil === null ? null : parseJstInstant(rule.effectiveUntil);
    return (
      effectiveFrom !== null &&
      effectiveFrom <= departureInstant &&
      (rule.effectiveUntil === null ||
        (effectiveUntil !== null && departureInstant < effectiveUntil))
    );
  });
  if (effectiveRules.length === 0) return 'APPLICABILITY_UNKNOWN';
  const requiresAircraft = effectiveRules.some((rule) => rule.applicability.aircraftClass !== null);
  const requiresFare = effectiveRules.some((rule) => rule.applicability.fareOrOption !== null);
  if (
    (requiresAircraft && segment.aircraftClass === null) ||
    (requiresFare && segment.fareOrOption === null)
  ) {
    return 'APPLICABILITY_UNKNOWN';
  }
  const matchingCandidates = effectiveRules.filter((rule) => {
    if (rule.carrierId !== segment.carrierId) return false;
    if (
      rule.applicability.aircraftClass !== null &&
      rule.applicability.aircraftClass !== segment.aircraftClass
    ) {
      return false;
    }
    return (
      rule.applicability.fareOrOption === null ||
      rule.applicability.fareOrOption === segment.fareOrOption
    );
  });
  if (matchingCandidates.length === 0) return 'APPLICABILITY_UNKNOWN';
  const specificity = (rule: AirlineRuleV2): number =>
    Number(rule.applicability.aircraftClass !== null) +
    Number(rule.applicability.fareOrOption !== null);
  const maximumSpecificity = Math.max(...matchingCandidates.map(specificity));
  const candidates = matchingCandidates.filter((rule) => specificity(rule) === maximumSpecificity);
  if (candidates.length > 1) return 'AMBIGUOUS';
  return candidates[0]!;
}

function evaluateSegment(
  bag: CarryOnBagInputV2,
  segment: CarryOnSegmentInputV2,
  rules: readonly AirlineRuleV2[],
): SegmentDecisionV2 {
  if (bag.appendagesIncluded !== true || (bag.state !== 'NORMAL' && bag.state !== 'EXPANDED')) {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: segment.carrierId,
      state: 'UNKNOWN',
      reasons: Object.freeze([
        '通常時・拡張時と、キャスター・ハンドルを含む測定かを確認してください。',
      ]),
      sourceIds: Object.freeze([]),
      checkedAt: null,
    });
  }
  if (segment.carrierId.length === 0) {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: '',
      state: 'UNKNOWN',
      reasons: Object.freeze(['航空会社が選択されていません。']),
      sourceIds: Object.freeze([]),
      checkedAt: null,
    });
  }

  const rule = selectRule(segment, rules);
  if (
    rule === null ||
    rule === 'AMBIGUOUS' ||
    rule === 'APPLICABILITY_UNKNOWN' ||
    rule === 'SCOPE_NO_MATCH'
  ) {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: segment.carrierId,
      state: rule === null || rule === 'SCOPE_NO_MATCH' ? 'NO_MATCH' : 'UNKNOWN',
      reasons: Object.freeze([
        rule === null
          ? 'この航空会社に一致する記録済みルールがありません。'
          : rule === 'SCOPE_NO_MATCH'
            ? 'この路線区分に一致する記録済みルールがありません。'
            : '適用候補を一意に決められません。出発日時・便・機材・運賃を確認してください。',
      ]),
      sourceIds: Object.freeze([]),
      checkedAt: null,
    });
  }

  if (rule.blocked) {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: segment.carrierId,
      state: 'BLOCKED',
      reasons: Object.freeze(['ルールの根拠確認が完了していないため判定を停止しました。']),
      sourceIds: Object.freeze([rule.sourceId]),
      checkedAt: rule.checkedAt,
    });
  }

  const sourceNextReviewAt = parseJstInstant(rule.sourceNextReviewAt);
  const departureInstant = parseJstInstant(segment.departureAtJst);
  if (
    sourceNextReviewAt === null ||
    departureInstant === null ||
    departureInstant >= sourceNextReviewAt
  ) {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: segment.carrierId,
      state: sourceNextReviewAt === null ? 'UNKNOWN' : 'STALE',
      reasons: Object.freeze([
        sourceNextReviewAt === null
          ? '公式ルールの再確認期限を検証できません。'
          : '搭乗日時が公式ルールの再確認期限以後のため確定判定できません。',
      ]),
      sourceIds: Object.freeze([rule.sourceId]),
      checkedAt: rule.checkedAt,
    });
  }

  if (rule.freshness === 'HARD_STALE') {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: segment.carrierId,
      state: 'STALE',
      reasons: Object.freeze(['公式ルールの再確認期限を過ぎているため確定判定できません。']),
      sourceIds: Object.freeze([rule.sourceId]),
      checkedAt: rule.checkedAt,
    });
  }

  const dimensions = bag.dimensionsCm.map(parseDecimal);
  const maximumDimensions = rule.dimensionsCm.map(parseDecimal);
  const weight = parseDecimal(bag.combinedWeightKg);
  const maximumWeight = parseDecimal(rule.maxCombinedWeightKg);
  const carryOnCount = /^(?:0|[1-9][0-9]*)$/u.test(bag.carryOnCount)
    ? Number(bag.carryOnCount)
    : Number.NaN;
  const personalItemCount = /^(?:0|[1-9][0-9]*)$/u.test(bag.personalItemCount)
    ? Number(bag.personalItemCount)
    : Number.NaN;
  const itemCount = carryOnCount + personalItemCount;
  if (
    dimensions.some((value) => value === null) ||
    dimensions.some((value) => value !== null && value.coefficient <= 0n) ||
    maximumDimensions.some((value) => value === null) ||
    weight === null ||
    (weight !== null && weight.coefficient <= 0n) ||
    maximumWeight === null ||
    !Number.isSafeInteger(carryOnCount) ||
    !Number.isSafeInteger(personalItemCount) ||
    itemCount < 1
  ) {
    return Object.freeze({
      segmentId: segment.segmentId,
      carrierId: segment.carrierId,
      state: 'UNKNOWN',
      reasons: Object.freeze(['外寸・合計重量・個数を0より大きい数値で入力してください。']),
      sourceIds: Object.freeze([rule.sourceId]),
      checkedAt: rule.checkedAt,
    });
  }

  const reasons: string[] = [];
  const typedDimensions = dimensions as [ExactDecimal, ExactDecimal, ExactDecimal];
  const typedMaximum = maximumDimensions as [ExactDecimal, ExactDecimal, ExactDecimal];
  if (!dimensionsFit(typedDimensions, typedMaximum, rule.dimensionOrientation)) {
    reasons.push('キャスター・ハンドルを含む外寸が上限を超えています。');
  }
  if (rule.maxDimensionSumCm !== null) {
    const maximumSum = parseDecimal(rule.maxDimensionSumCm);
    if (maximumSum === null || compareDecimal(decimalSum(typedDimensions), maximumSum) > 0) {
      reasons.push('キャスター・ハンドルを含む3辺合計が上限を超えています。');
    }
  }
  if (compareDecimal(weight, maximumWeight) > 0) {
    reasons.push('身の回り品を含む合計重量が上限を超えています。');
  }
  if (itemCount > rule.maxItemCount) {
    reasons.push('身の回り品を含む個数が上限を超えています。');
  }
  if (carryOnCount > rule.maxCarryOnCount) {
    reasons.push('機内持ち込み手荷物の個数が上限を超えています。');
  }
  if (personalItemCount > rule.maxPersonalItemCount) {
    reasons.push('身の回り品の個数が上限を超えています。');
  }

  if (reasons.length === 0 && rule.requiresPersonalItemUnderseat && personalItemCount > 0) {
    if (!bag.personalItemUnderseatConfirmed) {
      return Object.freeze({
        segmentId: segment.segmentId,
        carrierId: segment.carrierId,
        state: 'UNKNOWN',
        reasons: Object.freeze(['身の回り品を前の座席の下に収納できるか確認してください。']),
        sourceIds: Object.freeze([rule.sourceId]),
        checkedAt: rule.checkedAt,
      });
    }
  }

  return Object.freeze({
    segmentId: segment.segmentId,
    carrierId: segment.carrierId,
    state: reasons.length === 0 ? 'PASS' : 'FAIL',
    reasons: Object.freeze(
      reasons.length === 0
        ? ['入力された外寸・合計重量・個数は記録済みルールの範囲内です。']
        : reasons,
    ),
    sourceIds: Object.freeze([rule.sourceId]),
    checkedAt: rule.checkedAt,
  });
}

const STATE_PRIORITY: Readonly<Record<DecisionSupportV2ResultState, number>> = Object.freeze({
  PASS: 0,
  NO_MATCH: 1,
  UNKNOWN: 2,
  STALE: 3,
  BLOCKED: 4,
  FAIL: 5,
});

export function evaluateCarryOnDecisionV2(
  bag: CarryOnBagInputV2,
  segments: readonly CarryOnSegmentInputV2[],
  rules: readonly AirlineRuleV2[],
): DecisionSupportResultV2 {
  if (segments.length === 0) {
    return Object.freeze({
      state: 'UNKNOWN',
      reasons: Object.freeze(['少なくとも1区間の航空会社を選択してください。']),
      segments: Object.freeze([]),
    });
  }

  const decisions = Object.freeze(segments.map((segment) => evaluateSegment(bag, segment, rules)));
  const state = decisions.reduce<DecisionSupportV2ResultState>(
    (current, decision) =>
      STATE_PRIORITY[decision.state] > STATE_PRIORITY[current] ? decision.state : current,
    'PASS',
  );
  return Object.freeze({
    state,
    reasons: Object.freeze(decisions.flatMap((decision) => decision.reasons)),
    segments: decisions,
  });
}
