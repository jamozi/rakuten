import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

import {
  DECISION_SUPPORT_V2_PAGE_TEMPLATES,
  DECISION_SUPPORT_V2_RESULT_STATES,
  DECISION_SUPPORT_V2_ROUTES,
} from '../../packages/web-ui/src/decision-support-v2/contracts.ts';
import { evaluateCarryOnDecisionV2 } from '../../packages/web-ui/src/decision-support-v2/checker.ts';
import { renderDecisionSupportPageV2 } from '../../packages/web-ui/src/decision-support-v2/renderer.ts';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = join(SCRIPT_DIR, '..', '..');
const UI_ROOT = join(ROOT, 'packages', 'web-ui', 'src', 'decision-support-v2');
const PREVIEW_ROOT = join(ROOT, 'changes', 'raos-v2', 'phase-2', 'preview');
const EXPECTED_NODE_VERSION = '24.18.1';

function fail(code, details = '') {
  throw new Error(details.length === 0 ? code : `${code}: ${details}`);
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function decodeHtml(value) {
  return value
    .replace(/<[^>]*>/gu, '')
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'")
    .replace(/\s+/gu, ' ')
    .trim();
}

function matchOne(html, pattern, code) {
  const match = pattern.exec(html);
  if (match === null || match[1] === undefined) fail(code);
  return match[1];
}

function allMatches(html, pattern, mapper = (match) => match[1]) {
  return [...html.matchAll(pattern)].map(mapper);
}

function semanticDocument(html, disclosure) {
  const breadcrumbBlock = /<nav class="breadcrumbs reading"[^>]*>([\s\S]*?)<\/nav>/u.exec(html)?.[1] ?? '';
  const structuredData = allMatches(
    html,
    /<script type="application\/ld\+json">([\s\S]*?)<\/script>/gu,
  ).flatMap((payload) => {
    const parsed = JSON.parse(payload);
    return parsed['@graph'].map((entry) => entry['@type']);
  });
  const headings = allMatches(
    html,
    /<h([1-6])(?:\s[^>]*)?>([\s\S]*?)<\/h\1>/gu,
    (match) => ({ level: Number(match[1]), text: decodeHtml(match[2]) }),
  );
  return Object.freeze({
    articleMetadataCount: (html.match(/class="article-meta"/gu) ?? []).length,
    blockedCtaCount: (html.match(/class="affiliate-cta is-blocked"/gu) ?? []).length,
    breadcrumbLabels: allMatches(breadcrumbBlock, /<li(?:\s[^>]*)?>([\s\S]*?)<\/li>/gu).map(
      decodeHtml,
    ),
    canonical: matchOne(html, /<link rel="canonical" href="([^"]+)">/u, 'CANONICAL_MISSING'),
    checkerCount: (html.match(/id="carry-on-checker"/gu) ?? []).length,
    contentSections: allMatches(
      html,
      /<section class="reading content-section" aria-labelledby="([^"]+)"><h2 id="([^"]+)">([\s\S]*?)<\/h2>/gu,
      (match) => ({ id: match[1], labelledBy: match[2], title: decodeHtml(match[3]) }),
    ),
    disclosureExact: html.includes(disclosure),
    formControlNames: allMatches(
      html,
      /<(?:input|select)[^>]*\sname="([^"]+)"[^>]*>/gu,
    ),
    headings,
    h1Count: headings.filter((heading) => heading.level === 1).length,
    jsonLdTypes: structuredData,
    mainCount: (html.match(/<main(?:\s[^>]*)?>/gu) ?? []).length,
    productIds: allMatches(
      html,
      /<article class="product-card" aria-labelledby="product-([A-Z0-9-]+)">/gu,
    ),
    robots: matchOne(html, /<meta name="robots" content="([^"]+)">/u, 'ROBOTS_MISSING'),
    route: matchOne(html, /<body[^>]*data-route="([^"]+)"/u, 'BODY_ROUTE_MISSING'),
    template: matchOne(html, /<body[^>]*data-template="([A-Z]+)"/u, 'BODY_TEMPLATE_MISSING'),
    title: decodeHtml(matchOne(html, /<title>([\s\S]*?)<\/title>/u, 'TITLE_MISSING')),
  });
}

function pageModel(page, packageInput) {
  const products = page.products.map((productId) => {
    const product = packageInput.products[productId];
    if (product === undefined) fail('PAGE_PRODUCT_UNKNOWN', productId);
    return {
      productId: product.product_id,
      name: product.name,
      modelNumber: product.model_number,
      facts: product.facts,
      fit: product.fit,
      nonFit: product.non_fit,
      tradeoff: product.tradeoff,
      unknown: product.unknown,
      source: {
        publisher: product.source.publisher,
        checkedAt: product.source.checked_at,
        status: product.source.status,
        link: {
          href: product.source.href,
          label: product.source.label,
          external: true,
        },
      },
      ctaState: product.cta_state,
    };
  });
  return {
    route: page.route,
    template: page.template,
    title: page.title,
    description: page.description,
    eyebrow: page.eyebrow,
    summary: page.summary,
    robots: packageInput.preview_robots,
    canonical: `${packageInput.target_origin}${page.route}`,
    breadcrumbs: page.breadcrumbs,
    sections: page.sections,
    products,
    comparisonAxes: page.comparison_axes,
    ...(page.author_name === undefined ? {} : { authorName: page.author_name }),
    ...(page.date_published === undefined ? {} : { datePublished: page.date_published }),
    ...(page.date_modified === undefined ? {} : { dateModified: page.date_modified }),
  };
}

function generatedPreviewPath(route) {
  return route === '/'
    ? join(PREVIEW_ROOT, 'index.html')
    : join(PREVIEW_ROOT, route.slice(1), 'index.html');
}

function toTsRule(rule, index) {
  return Object.freeze({
    ruleId: `UI-RULE-${String(index + 1).padStart(2, '0')}`,
    carrierId: rule.carrier,
    journeyScope: rule.journeyScope,
    dimensionsCm: rule.maxDimensions,
    maxDimensionSumCm: rule.maxSum,
    dimensionOrientation: rule.orientation,
    maxCombinedWeightKg: rule.maxWeight,
    maxItemCount: rule.maxItems,
    maxCarryOnCount: rule.maxCarryOnCount,
    maxPersonalItemCount: rule.maxPersonalItemCount,
    requiresPersonalItemUnderseat: rule.requiresPersonalItemUnderseat,
    sourceId: rule.sourceId,
    checkedAt: rule.checkedAt,
    sourceNextReviewAt: rule.nextReviewAt,
    effectiveFrom: rule.effectiveFrom,
    effectiveUntil: rule.effectiveUntil,
    freshness: rule.status === 'HARD_STALE' ? 'HARD_STALE' : rule.status === 'DUE' ? 'DUE' : 'FRESH',
    applicability: Object.freeze({
      aircraftClass: rule.aircraft,
      fareOrOption: rule.fareOrOption,
    }),
    blocked: rule.status === 'BLOCKED',
  });
}

function browserBag(raw) {
  return Object.freeze({
    dimensions: raw.dimensions,
    weight: raw.weight,
    carryOnCount: raw.carry_on_count,
    personalItemCount: raw.personal_item_count,
    bagState: raw.bag_state,
    appendagesIncluded: raw.appendages_included,
    personalItemUnderseatConfirmed: raw.personal_item_underseat_confirmed,
  });
}

function tsBag(raw) {
  return Object.freeze({
    dimensionsCm: raw.dimensions,
    combinedWeightKg: raw.weight,
    carryOnCount: raw.carry_on_count,
    personalItemCount: raw.personal_item_count,
    state: raw.bag_state,
    appendagesIncluded: raw.appendages_included,
    personalItemUnderseatConfirmed: raw.personal_item_underseat_confirmed,
  });
}

function browserSegment(raw) {
  return Object.freeze({
    carrier: raw.carrier,
    journeyScope: raw.journey_scope,
    aircraft: raw.aircraft ?? '',
    fareOrOption: raw.fare_or_option ?? '',
    departureAtJst: raw.departure_local,
    label: raw.segment_id,
  });
}

function tsSegment(raw) {
  return Object.freeze({
    segmentId: raw.segment_id,
    carrierId: raw.carrier,
    journeyScope: raw.journey_scope,
    aircraftClass: raw.aircraft,
    fareOrOption: raw.fare_or_option,
    departureAtJst: raw.departure_jst,
  });
}

async function main() {
  if (process.versions.node !== EXPECTED_NODE_VERSION) {
    fail('UI_PARITY_NODE_VERSION_INVALID', process.versions.node);
  }
  const packageInput = JSON.parse(
    await readFile(join(UI_ROOT, 'preview', 'pages.v2.json'), 'utf8'),
  );
  const casesInput = JSON.parse(
    await readFile(join(UI_ROOT, 'preview', 'checker-parity-cases.v2.json'), 'utf8'),
  );
  assert.equal(casesInput.schema, 'RAOS_V2_CHECKER_PARITY_CASES_V1');

  const pages = new Map(packageInput.pages.map((page) => [page.route, page]));
  assert.equal(pages.size, packageInput.pages.length, 'PREVIEW_ROUTE_DUPLICATE');
  assert.deepEqual(
    new Set(packageInput.pages.map((page) => page.template)),
    new Set(DECISION_SUPPORT_V2_PAGE_TEMPLATES),
  );
  assert.equal(DECISION_SUPPORT_V2_ROUTES.length, pages.size, 'ROUTE_COUNT_DRIFT');

  const routeParity = [];
  for (const routeContract of DECISION_SUPPORT_V2_ROUTES) {
    const page = pages.get(routeContract.route);
    if (page === undefined) fail('ROUTE_INPUT_MISSING', routeContract.route);
    assert.deepEqual(
      {
        articleId: page.article_id,
        intendedIndexCandidate: page.intended_index_candidate,
        previewRobots: packageInput.preview_robots,
        publicCandidate: page.public_candidate,
        publicationState: page.publication_state,
        route: page.route,
        template: page.template,
      },
      routeContract,
      `ROUTE_CONTRACT_DRIFT:${routeContract.route}`,
    );
    assert.equal(
      page.show_checker,
      page.template === 'HOME' || page.template === 'TOOL',
      `CHECKER_TEMPLATE_DRIFT:${page.route}`,
    );
    const tsHtml = renderDecisionSupportPageV2(pageModel(page, packageInput));
    const previewHtml = await readFile(generatedPreviewPath(page.route), 'utf8');
    const tsSemantic = semanticDocument(tsHtml, packageInput.disclosure);
    const previewSemantic = semanticDocument(previewHtml, packageInput.disclosure);
    assert.deepEqual(previewSemantic, tsSemantic, `RENDER_SEMANTIC_DRIFT:${page.route}`);
    routeParity.push(
      Object.freeze({
        route: page.route,
        semanticSha256: sha256(`${canonical(previewSemantic)}\n`),
      }),
    );
  }

  const checkerSource = await readFile(join(UI_ROOT, 'preview', 'checker.js'), 'utf8');
  const context = vm.createContext({ __RAOS_V2_TEST_MODE__: true });
  vm.runInContext(checkerSource, context, { filename: 'preview/checker.js' });
  const browserContract = context.__RAOS_V2_CHECKER_CONTRACT__;
  if (browserContract === undefined) fail('BROWSER_CHECKER_TEST_CONTRACT_MISSING');
  assert.deepEqual([...browserContract.resultStates], [...DECISION_SUPPORT_V2_RESULT_STATES]);
  const tsRules = [...browserContract.rules].map(toTsRule);
  const caseParity = [];
  for (const testCase of casesInput.cases) {
    const browserResult = browserContract.evaluate(
      browserBag(testCase.bag),
      testCase.segments.map(browserSegment),
    );
    const tsResult = evaluateCarryOnDecisionV2(
      tsBag(testCase.bag),
      testCase.segments.map(tsSegment),
      tsRules,
    );
    const browserSegments = [...browserResult.segments];
    const tsSegments = tsResult.segments.map((segment) => segment.state);
    assert.equal(browserResult.state, testCase.expected, `BROWSER_CASE_FAILED:${testCase.id}`);
    assert.equal(tsResult.state, testCase.expected, `TS_CASE_FAILED:${testCase.id}`);
    assert.deepEqual(browserSegments, tsSegments, `CHECKER_SEGMENT_DRIFT:${testCase.id}`);
    caseParity.push(
      Object.freeze({
        id: testCase.id,
        segmentStates: browserSegments,
        state: browserResult.state,
      }),
    );
  }

  process.stdout.write(
    `${JSON.stringify({
      schema: 'RAOS_V2_UI_PARITY_RESULT_V1',
      classification: 'PASSED_LOCAL',
      nodeVersion: process.versions.node,
      routeCount: routeParity.length,
      caseCount: caseParity.length,
      routeParity,
      caseParity,
      externalActions: 'NOT_EXECUTED',
    })}\n`,
  );
}

await main();
