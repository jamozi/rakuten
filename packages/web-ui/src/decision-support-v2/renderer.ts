import type { DecisionSupportV2PageTemplate, DecisionSupportV2ResultState } from './contracts.ts';

export interface DecisionSupportV2Link {
  readonly href: string;
  readonly label: string;
  readonly external?: boolean;
}

export interface DecisionSupportV2SourceChip {
  readonly publisher: string;
  readonly checkedAt: string;
  readonly status: 'FRESH' | 'DUE' | 'HARD_STALE';
  readonly link: DecisionSupportV2Link;
}

export interface DecisionSupportV2Product {
  readonly productId: string;
  readonly name: string;
  readonly modelNumber: string;
  readonly facts: readonly string[];
  readonly fit: string;
  readonly nonFit: string;
  readonly tradeoff: string;
  readonly unknown: string;
  readonly source: DecisionSupportV2SourceChip;
  readonly ctaState: 'IDENTITY_BLOCKED' | 'UNAVAILABLE';
}

export interface DecisionSupportV2ComparisonAxis {
  readonly label: string;
  readonly values: Readonly<Record<string, string>>;
}

export interface DecisionSupportV2PageModel {
  readonly route: string;
  readonly template: DecisionSupportV2PageTemplate;
  readonly title: string;
  readonly description: string;
  readonly eyebrow: string;
  readonly summary: string;
  readonly robots: 'index,follow' | 'noindex,nofollow';
  readonly canonical: string;
  readonly breadcrumbs: readonly DecisionSupportV2Link[];
  readonly sections: readonly Readonly<{
    id: string;
    title: string;
    paragraphs: readonly string[];
    links: readonly DecisionSupportV2Link[];
  }>[];
  readonly products: readonly DecisionSupportV2Product[];
  readonly comparisonAxes: readonly DecisionSupportV2ComparisonAxis[];
  readonly authorName?: string;
  readonly datePublished?: string;
  readonly dateModified?: string;
}

const DISCLOSURE =
  '広告リンクを設置する場合があります。現在、確認済みでない商品リンクは表示しません。報酬は商品の選定・掲載順に影響しません。実機試験を行っていない比較では、公式情報と編集判断を分けて表示します。';

const SAFE_INTERNAL_HREFS = new Set([
  '/',
  '/carry-on/',
  '/tools/carry-on-size-checker/',
  '/guides/carry-on-baggage-rules/',
  '/guides/low-cost-carrier-7kg-packing/',
  '/carry-on-suitcase-comparison/',
  '/guides/carry-on-bag-measurement/',
  '/policy/how-we-compare-carry-on-products/',
  '/policy/how-we-compare-carry-on-products/#corrections',
  '/differences/ace-cresta-vs-difference-vs-maxpass4/',
  '/privacy-policy/',
]);

const SAFE_EXTERNAL_HOSTS = new Set([
  'www.ana.co.jp',
  'www.jal.co.jp',
  'www.flypeach.com',
  'www.jetstar.com',
  'store.ace.jp',
]);

const ARTICLE_TEMPLATES = new Set<DecisionSupportV2PageTemplate>([
  'GUIDE',
  'COMPARISON',
  'DIFFERENCE',
  'POLICY',
]);
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u;

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderLink(link: DecisionSupportV2Link, className = ''): string {
  const external = link.external === true;
  if (external) {
    const match = /^https:\/\/([^/?#@]+)(\/[^?#]*)?$/u.exec(link.href);
    if (match === null || !SAFE_EXTERNAL_HOSTS.has(match[1]!)) {
      throw new TypeError('DECISION_SUPPORT_V2_EXTERNAL_HREF_INVALID');
    }
  } else if (!SAFE_INTERNAL_HREFS.has(link.href)) {
    throw new TypeError('DECISION_SUPPORT_V2_INTERNAL_HREF_INVALID');
  }
  const rel = external ? ' rel="noopener noreferrer"' : '';
  const target = external ? ' target="_blank"' : '';
  const suffix = external ? '<span class="visually-hidden">（外部サイト）</span>' : '';
  return `<a${className.length > 0 ? ` class="${escapeHtml(className)}"` : ''} href="${escapeHtml(link.href)}"${rel}${target}>${escapeHtml(link.label)}${suffix}</a>`;
}

function renderBreadcrumbs(links: readonly DecisionSupportV2Link[]): string {
  const items = links
    .map((link, index) => {
      const current = index === links.length - 1;
      return `<li${current ? ' aria-current="page"' : ''}>${
        current ? escapeHtml(link.label) : renderLink(link)
      }</li>`;
    })
    .join('');
  return `<nav class="breadcrumbs reading" aria-label="パンくず"><ol>${items}</ol></nav>`;
}

function renderSourceChip(source: DecisionSupportV2SourceChip): string {
  const stale = source.status === 'HARD_STALE';
  return `<p class="source-chip" data-freshness="${source.status}"><span>${escapeHtml(
    source.publisher,
  )}・確認 ${escapeHtml(source.checkedAt)}</span>${stale ? '<strong>再確認期限超過</strong>' : ''}${renderLink(
    source.link,
  )}</p>`;
}

function renderComparisonTable(
  products: readonly DecisionSupportV2Product[],
  axes: readonly DecisionSupportV2ComparisonAxis[],
): string {
  if (products.length === 0 || axes.length === 0) return '';
  const headers = products
    .map((product) => `<th scope="col">${escapeHtml(product.name)}</th>`)
    .join('');
  const rows = axes
    .map(
      (axis) =>
        `<tr><th scope="row">${escapeHtml(axis.label)}</th>${products
          .map((product) => `<td>${escapeHtml(axis.values[product.productId] ?? '未確認')}</td>`)
          .join('')}</tr>`,
    )
    .join('');
  const mobile = axes
    .map(
      (axis) =>
        `<article class="matrix-mobile-card"><h3>${escapeHtml(axis.label)}</h3><dl>${products
          .map(
            (product) =>
              `<div><dt>${escapeHtml(product.name)}</dt><dd>${escapeHtml(
                axis.values[product.productId] ?? '未確認',
              )}</dd></div>`,
          )
          .join('')}</dl></article>`,
    )
    .join('');
  return `<section class="wide comparison-matrix" aria-labelledby="comparison-matrix-title"><h2 id="comparison-matrix-title">仕様を同じ軸で比較</h2><div class="table-scroll" role="region" aria-label="3モデル比較表" tabindex="0"><table><caption>ACE 3モデルの公式仕様と未確認事項</caption><thead><tr><th scope="col">比較軸</th>${headers}</tr></thead><tbody>${rows}</tbody></table></div><div class="matrix-mobile">${mobile}</div></section>`;
}

function renderProductCard(product: DecisionSupportV2Product): string {
  const facts = product.facts.map((fact) => `<li>${escapeHtml(fact)}</li>`).join('');
  return `<article class="product-card" aria-labelledby="product-${escapeHtml(
    product.productId,
  )}"><p class="meta">メーカー型番 ${escapeHtml(product.modelNumber)}</p><h3 id="product-${escapeHtml(
    product.productId,
  )}">${escapeHtml(product.name)}</h3><div class="product-placeholder" role="img" aria-label="商品画像は使用していません">商品画像なし</div><h4>公式仕様</h4><ul>${facts}</ul><dl class="judgement-list"><div><dt>向く条件</dt><dd>${escapeHtml(
    product.fit,
  )}</dd></div><div><dt>向かない条件</dt><dd>${escapeHtml(
    product.nonFit,
  )}</dd></div><div><dt>トレードオフ</dt><dd>${escapeHtml(
    product.tradeoff,
  )}</dd></div><div><dt>未確認</dt><dd>${escapeHtml(
    product.unknown,
  )}</dd></div></dl>${renderSourceChip(product.source)}<div class="affiliate-cta is-blocked" role="group" aria-label="楽天リンク利用不可"><strong>楽天CTA：確認待ち</strong><p>型番・世代・販売単位を一意に結び付けられるまでリンクを表示しません。</p><button type="button" disabled>現在情報を確認できません</button></div></article>`;
}

function renderSections(model: DecisionSupportV2PageModel): string {
  return model.sections
    .map((section) => {
      const paragraphs = section.paragraphs
        .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
        .join('');
      const links = section.links.map((link) => `<li>${renderLink(link)}</li>`).join('');
      return `<section class="reading content-section" aria-labelledby="${escapeHtml(
        section.id,
      )}"><h2 id="${escapeHtml(section.id)}">${escapeHtml(
        section.title,
      )}</h2>${paragraphs}${links.length > 0 ? `<ul class="link-list">${links}</ul>` : ''}</section>`;
    })
    .join('');
}

function renderTool(): string {
  const carriers = `<option value="">選択してください</option><option value="ANA">ANA</option><option value="JAL">JAL</option><option value="PEACH">Peach</option><option value="JETSTAR_JAPAN">Jetstar Japan（GK運航便）</option>`;
  const aircraft = `<option value="">わからない</option><option value="LARGE">100席以上</option><option value="SMALL">100席未満</option>`;
  const journeyScopes = `<option value="">選択してください</option><option value="DOMESTIC">国内線</option><option value="INTERNATIONAL">国際線</option><option value="UNKNOWN">わからない・確認中</option>`;
  const fares = `<option value="">わからない・確認中</option><option value="STANDARD_7KG">標準7kg条件</option><option value="UP_TO_14KG_OPTION">機内持込手荷物オプション（最大14kg）</option><option value="NOT_APPLICABLE">該当なし</option>`;
  return `<section class="wide tool-panel" aria-labelledby="checker-title"><div><p class="eyebrow">入力はこのブラウザ内だけで処理</p><h2 id="checker-title">機内持ち込み条件チェッカー</h2><p>航空会社を推測しません。全区間の路線区分・出発日時・機材・運賃と、付属部品を含む外寸、合計重量・個数を入力してください。</p></div><form id="carry-on-checker" novalidate><div id="form-errors" class="error-summary" tabindex="-1" hidden><h3>入力を確認してください</h3><ul></ul></div><fieldset><legend>搭乗区間1（必須）</legend><label for="carrier">航空会社<select id="carrier" name="carrier" required>${carriers}</select></label><label for="journey-scope">路線区分<select id="journey-scope" name="journey-scope" required>${journeyScopes}</select></label><label for="aircraft">便・機材条件<select id="aircraft" name="aircraft">${aircraft}</select></label><label for="fare-option">運賃・手荷物オプション<select id="fare-option" name="fare-option">${fares}</select></label><label for="departure-at-jst">出発日時（JST）<input id="departure-at-jst" name="departure-at-jst" type="datetime-local" required></label></fieldset><details><summary>乗り継ぎ区間を追加</summary><fieldset><legend>搭乗区間2（任意）</legend><label for="carrier-2">航空会社<select id="carrier-2" name="carrier-2">${carriers}</select></label><label for="journey-scope-2">路線区分<select id="journey-scope-2" name="journey-scope-2">${journeyScopes}</select></label><label for="aircraft-2">便・機材条件<select id="aircraft-2" name="aircraft-2">${aircraft}</select></label><label for="fare-option-2">運賃・手荷物オプション<select id="fare-option-2" name="fare-option-2">${fares}</select></label><label for="departure-at-jst-2">出発日時（JST）<input id="departure-at-jst-2" name="departure-at-jst-2" type="datetime-local"></label></fieldset></details><fieldset><legend>荷物（付属部品を含む）</legend><label for="bag-state">測定状態<select id="bag-state" name="bag-state" required><option value="">選択してください</option><option value="NORMAL">通常時</option><option value="EXPANDED">拡張時</option></select></label><div class="field-grid"><label for="height">高さ <span>cm</span><input id="height" name="height" inputmode="decimal" autocomplete="off" required></label><label for="width">幅 <span>cm</span><input id="width" name="width" inputmode="decimal" autocomplete="off" required></label><label for="depth">奥行 <span>cm</span><input id="depth" name="depth" inputmode="decimal" autocomplete="off" required></label></div><label for="weight">身の回り品を含む合計重量 <span>kg</span><input id="weight" name="weight" inputmode="decimal" autocomplete="off" required></label><div class="field-grid"><label for="carry-on-count">機内持ち込み手荷物の個数<input id="carry-on-count" name="carry-on-count" inputmode="numeric" autocomplete="off" value="1" required></label><label for="personal-item-count">身の回り品の個数<input id="personal-item-count" name="personal-item-count" inputmode="numeric" autocomplete="off" value="1" required></label></div><label class="check-label" for="appendages-included"><input id="appendages-included" name="appendages-included" type="checkbox" value="yes" required>キャスター・ハンドル・外ポケットを含む最大外寸です</label><label class="check-label" for="personal-item-underseat-confirmed"><input id="personal-item-underseat-confirmed" name="personal-item-underseat-confirmed" type="checkbox" value="yes">Jetstar Japanを利用する場合、身の回り品を前の座席の下に収納できることを確認しました</label></fieldset><button class="button primary" type="submit">結果を見る</button><button class="button secondary" type="reset">入力を消す</button><p class="privacy-note">入力値は送信・保存しません。判定後も航空会社の公式ページで最終確認してください。</p></form><div id="checker-result" class="result-panel" data-state="UNKNOWN" role="status" aria-live="polite" aria-atomic="true"><h3>まだ判定していません</h3><p>航空会社と荷物条件を入力してください。</p></div><noscript><p class="no-js-note">JavaScriptが無効なため自動判定は使えません。航空会社の公式リンクと入力項目を照らし合わせてください。</p></noscript></section>`;
}

interface ArticleMetadataV2 {
  readonly authorName: string;
  readonly datePublished: string;
  readonly dateModified: string;
}

function articleMetadata(model: DecisionSupportV2PageModel): ArticleMetadataV2 | null {
  const values = [model.authorName, model.datePublished, model.dateModified];
  if (values.every((value) => value === undefined)) return null;
  if (values.some((value) => value === undefined)) {
    throw new TypeError('DECISION_SUPPORT_V2_ARTICLE_METADATA_INCOMPLETE');
  }
  const authorName = model.authorName!;
  const datePublished = model.datePublished!;
  const dateModified = model.dateModified!;
  if (
    !ARTICLE_TEMPLATES.has(model.template) ||
    authorName.trim() !== authorName ||
    authorName.length === 0 ||
    !ISO_DATE.test(datePublished) ||
    !ISO_DATE.test(dateModified) ||
    dateModified < datePublished
  ) {
    throw new TypeError('DECISION_SUPPORT_V2_ARTICLE_METADATA_INVALID');
  }
  return Object.freeze({ authorName, dateModified, datePublished });
}

function renderArticleMetadata(model: DecisionSupportV2PageModel): string {
  const metadata = articleMetadata(model);
  if (metadata === null) return '';
  return `<p class="article-meta"><span>執筆者：${escapeHtml(
    metadata.authorName,
  )}</span><span>公開日：<time datetime="${metadata.datePublished}">${metadata.datePublished}</time></span><span>更新日：<time datetime="${metadata.dateModified}">${metadata.dateModified}</time></span></p>`;
}

function renderJsonLd(model: DecisionSupportV2PageModel): string {
  if (model.robots !== 'index,follow') return '';
  const graph: Record<string, unknown>[] = [{ '@type': 'Organization', name: '暮らしのしるべ' }];
  if (model.template === 'HOME') {
    graph.push({ '@type': 'WebSite', name: '暮らしのしるべ', url: model.canonical });
  } else {
    graph.push({
      '@type': 'BreadcrumbList',
      itemListElement: model.breadcrumbs.map((link, index) => ({
        '@type': 'ListItem',
        item: `https://kurashinoshirube.com${link.href}`,
        name: link.label,
        position: index + 1,
      })),
    });
    const metadata = articleMetadata(model);
    if (metadata !== null) {
      graph.push({
        '@type': 'Article',
        author: { '@type': 'Organization', name: metadata.authorName },
        dateModified: metadata.dateModified,
        datePublished: metadata.datePublished,
        headline: model.title,
        inLanguage: 'ja-JP',
        mainEntityOfPage: model.canonical,
      });
    }
  }
  return JSON.stringify({
    '@context': 'https://schema.org',
    '@graph': graph,
  }).replaceAll('<', '\\u003c');
}

export function renderDecisionSupportPageV2(model: DecisionSupportV2PageModel): string {
  if (
    !SAFE_INTERNAL_HREFS.has(model.route) ||
    model.canonical !== `https://kurashinoshirube.com${model.route}`
  ) {
    throw new TypeError('DECISION_SUPPORT_V2_ROUTE_BINDING_INVALID');
  }
  const cards = model.products.map(renderProductCard).join('');
  const comparison = renderComparisonTable(model.products, model.comparisonAxes);
  const tool = model.template === 'HOME' || model.template === 'TOOL' ? renderTool() : '';
  const jsonLd = renderJsonLd(model);
  const structuredData =
    jsonLd.length > 0 ? `<script type="application/ld+json">${jsonLd}</script>` : '';
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(
    model.title,
  )} | 暮らしのしるべ</title><meta name="description" content="${escapeHtml(
    model.description,
  )}"><meta name="robots" content="${model.robots}"><link rel="canonical" href="${escapeHtml(
    model.canonical,
  )}">${structuredData}</head><body data-template="${model.template}" data-route="${escapeHtml(
    model.route,
  )}"><a class="skip-link" href="#main">本文へ移動</a><header class="site-header"><nav class="shell" aria-label="主要ナビゲーション"><a class="wordmark" href="/">暮らしのしるべ</a><div class="nav-links"><a href="/carry-on/">機内持ち込み</a><a href="/tools/carry-on-size-checker/">条件チェッカー</a><a href="/carry-on-suitcase-comparison/">比較ガイド</a><a href="/policy/how-we-compare-carry-on-products/">比較方法</a></div></nav></header><aside class="disclosure-bar" aria-label="広告表示"><div class="shell"><strong>広告リンクに関する表示</strong><span>${escapeHtml(
    DISCLOSURE,
  )}</span><a href="/policy/how-we-compare-carry-on-products/">比較・広告方針</a></div></aside>${renderBreadcrumbs(
    model.breadcrumbs,
  )}<main id="main" tabindex="-1"><header class="decision-hero reading"><p class="eyebrow">${escapeHtml(
    model.eyebrow,
  )}</p><h1>${escapeHtml(model.title)}</h1><p class="lead">${escapeHtml(
    model.summary,
  )}</p>${renderArticleMetadata(model)}</header>${tool}${renderSections(model)}${comparison}${
    cards.length > 0
      ? `<section class="wide" aria-labelledby="product-cards-title"><h2 id="product-cards-title">条件ごとの候補</h2><div class="product-grid">${cards}</div><aside class="none-fit"><h3>3商品とも合わない条件</h3><p>航空会社の条件、拡張時の外寸、必要容量が一致しない場合は購入候補にしません。条件を見直すか、別の商品群を探してください。</p></aside></section>`
      : ''
  }<section class="reading trust-strip" aria-labelledby="trust-title"><h2 id="trust-title">根拠の読み方</h2><dl><div><dt>公式情報</dt><dd>発行主体と確認日を表示します。</dd></div><div><dt>編集判断</dt><dd>条件と理由を明記します。</dd></div><div><dt>未確認</dt><dd>推測せず、購入判断を止めます。</dd></div></dl></section><section class="reading change-log" aria-labelledby="change-log-title"><h2 id="change-log-title">確認・変更履歴</h2><p>ローカルプレビュー。公開・配信・WordPress書き込みは実行していません。</p><a href="/policy/how-we-compare-carry-on-products/#corrections">訂正方針を確認する</a></section></main><footer class="site-footer"><div class="shell"><p>暮らしのしるべ — 公式情報と編集判断を分ける購買支援</p><nav aria-label="方針"><a href="/policy/how-we-compare-carry-on-products/">比較方法</a><a href="/privacy-policy/">プライバシー</a></nav></div></footer></body></html>`;
}

export function resultStateCopyV2(state: DecisionSupportV2ResultState): string {
  const copy: Readonly<Record<DecisionSupportV2ResultState, string>> = Object.freeze({
    PASS: '入力した条件では記録済み規定内です。公式情報で最終確認してください。',
    FAIL: '入力した条件に、記録済み規定を超える項目があります。',
    UNKNOWN: '入力または適用条件が不足しているため確定できません。',
    STALE: '公式情報の再確認期限を過ぎているため確定できません。',
    BLOCKED: '根拠または商品同一性を確認できないため処理を停止しました。',
    NO_MATCH: '入力条件に一致する記録済みルールがありません。',
  });
  return copy[state];
}
