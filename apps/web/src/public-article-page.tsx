import type { PublicArticleViewModelV2 } from '../../../packages/web-ui/src/public-article-renderer.ts';
import {
  PUBLIC_DISCLOSURE_COPY_V2,
  createPublicDisclosureAffiliateArticleViewV2,
  validatePublicAffiliateCtaSyntheticViewV2,
  validatePublicDisclosureAffiliateArticleViewV2,
  type PublicAffiliateCtaSyntheticViewV2,
  type PublicAffiliateCtaUnavailableViewV2,
  type PublicDisclosureAffiliateArticleViewV2,
} from '../../../packages/web-ui/src/disclosure-affiliate-cta.ts';

import { PUBLIC_POLICY_PAGES } from './public-policy.ts';

import styles from '../app/articles/[slug]/article.module.css';

function ArticleHeader() {
  return (
    <header className={styles['siteHeader']}>
      <div className={styles['siteHeaderInner']}>
        <div className={styles['identity']}>
          <span className={styles['identityMark']} aria-hidden="true">
            基
          </span>
          <span>
            <span className={styles['identityName']}>公開情報</span>
            <span className={styles['identityNote']}>根拠と判断の方針</span>
          </span>
        </div>
        <nav className={styles['primaryNav']} aria-label="方針と運営情報">
          <ul>
            {PUBLIC_POLICY_PAGES.map((page) => (
              <li key={page.screenId}>
                <a href={page.route}>{page.title}</a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}

function ArticleFooter() {
  return (
    <footer className={styles['siteFooter']}>
      <div className={styles['siteFooterInner']}>
        <div>
          <p className={styles['footerHeading']}>公開情報</p>
          <p>サイト名・運営者・問い合わせ先は承認待ちです。</p>
        </div>
        <nav aria-label="公開方針ページ">
          <ul>
            {PUBLIC_POLICY_PAGES.map((page) => (
              <li key={page.screenId}>
                <a href={page.route}>{page.title}</a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}

function ArticleSection({
  section,
}: {
  readonly section: PublicArticleViewModelV2['article']['sections'][number];
}) {
  const warning = section.kind === 'WARNING';
  return (
    <section
      className={`${styles['articleSection']} ${warning ? styles['warningSection'] : ''}`}
      aria-labelledby={`article-${section.blockKey}`}
    >
      <p className={styles['sectionLabel']}>{section.kind === 'WARNING' ? '注意' : '判断材料'}</p>
      <h2 id={`article-${section.blockKey}`}>{section.heading}</h2>
      {section.items.length === 1 ? (
        <p>{section.items[0]}</p>
      ) : (
        <ul>
          {section.items.map((item, index) => (
            <li key={`${section.blockKey}-${String(index)}`}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function DisclosureBanner({
  view,
}: {
  readonly view: PublicDisclosureAffiliateArticleViewV2;
}) {
  const safeBanner = validatePublicDisclosureAffiliateArticleViewV2(view).disclosure;
  return (
    <aside className={styles['disclosure']} aria-labelledby="article-disclosure-heading">
      <p className={styles['disclosureMark']} aria-hidden="true">
        {safeBanner.badge}
      </p>
      <div>
        <h2 id={safeBanner.headingId}>{safeBanner.heading}</h2>
        <p>{safeBanner.copy}</p>
      </div>
    </aside>
  );
}

function AffiliateCtaUnavailableNotice({
  cta,
}: {
  readonly cta: PublicAffiliateCtaUnavailableViewV2;
}) {
  return (
    <section className={styles['ctaUnavailable']} aria-labelledby={cta.notice.headingId}>
      <span className={styles['ctaUnavailableMark']} aria-hidden="true">
        未
      </span>
      <div>
        <h2 id={cta.notice.headingId}>{cta.notice.heading}</h2>
        <p>{cta.notice.text}</p>
      </div>
    </section>
  );
}

export function AffiliateCTA({ cta }: { readonly cta: PublicAffiliateCtaSyntheticViewV2 }) {
  const safeCta = validatePublicAffiliateCtaSyntheticViewV2(cta);
  return (
    <a className={styles['affiliateCta']} href={safeCta.href} rel={safeCta.rel}>
      <span>{safeCta.copy}</span>
      <span className={styles['affiliateCtaDestination']}>{safeCta.destinationText}</span>
    </a>
  );
}

function disclosureAffiliateView(
  model: PublicArticleViewModelV2,
): PublicDisclosureAffiliateArticleViewV2 {
  if (model.article.disclosureText !== PUBLIC_DISCLOSURE_COPY_V2) {
    throw new TypeError('PUBLIC_DISCLOSURE_V2_SOURCE_MISMATCH');
  }
  return createPublicDisclosureAffiliateArticleViewV2({
    schemaVersion: 2,
    screenId: model.screen.id,
    routePath: model.route.path,
    sourceProfile: 'EXACT_ST1002_RECORDED_PUBLIC_ARTICLE_V2',
    disclosureCopy: model.article.disclosureText,
    affiliateSource: {
      profile: 'ST0503_RECORDED_LOSSLESS_STRUCTURAL_V1',
      state: 'UNAVAILABLE_SOURCE',
      affiliateUrl: null,
    },
  });
}

export function PublicArticlePage({ model }: { readonly model: PublicArticleViewModelV2 }) {
  const disclosureAffiliate = disclosureAffiliateView(model);
  return (
    <div className={styles['siteFrame']}>
      <a className={styles['skipLink']} href="#public-article-main">
        {model.article.skipLink}
      </a>
      <ArticleHeader />
      <main className={styles['articleMain']} id="public-article-main" tabIndex={-1}>
        <nav className={styles['breadcrumb']} aria-label="現在位置">
          <ol>
            <li>{model.article.breadcrumbRoot}</li>
            <li>
              <span aria-current="page">{model.article.title}</span>
            </li>
          </ol>
        </nav>

        <article className={styles['article']} aria-labelledby="public-article-heading">
          <header className={styles['hero']}>
            <p className={styles['eyebrow']}>{model.article.eyebrow}</p>
            <p className={styles['previewPill']}>{model.article.previewLabel}</p>
            <h1 id="public-article-heading">{model.article.title}</h1>
            <DisclosureBanner view={disclosureAffiliate} />
            <div className={styles['lead']}>
              {model.article.lead.map((paragraph, index) => (
                <p key={`lead-${String(index)}`}>{paragraph}</p>
              ))}
            </div>
          </header>

          <div className={styles['statusGrid']}>
            <section aria-labelledby="article-preview-heading">
              <p className={styles['statusIcon']} aria-hidden="true">
                i
              </p>
              <div>
                <h2 id="article-preview-heading">{model.article.previewLabel}</h2>
                <p>{model.article.previewMessage}</p>
              </div>
            </section>
            <section aria-labelledby="article-freshness-heading">
              <p className={styles['statusIcon']} aria-hidden="true">
                ?
              </p>
              <div>
                <h2 id="article-freshness-heading">情報の状態</h2>
                <p>{model.article.freshnessText}</p>
              </div>
            </section>
          </div>

          <AffiliateCtaUnavailableNotice cta={disclosureAffiliate.affiliateCta} />

          <div className={styles['articleSections']}>
            {model.article.sections.map((section) => (
              <ArticleSection key={section.blockKey} section={section} />
            ))}
          </div>
        </article>
      </main>
      <ArticleFooter />
    </div>
  );
}
