import type { PublicArticleViewModelV2 } from '../../../packages/web-ui/src/public-article-renderer.ts';

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

export function PublicArticlePage({ model }: { readonly model: PublicArticleViewModelV2 }) {
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
            <div className={styles['lead']}>
              {model.article.lead.map((paragraph, index) => (
                <p key={`lead-${String(index)}`}>{paragraph}</p>
              ))}
            </div>
          </header>

          <aside className={styles['disclosure']} aria-labelledby="article-disclosure-heading">
            <p className={styles['disclosureMark']} aria-hidden="true">
              広告
            </p>
            <div>
              <h2 id="article-disclosure-heading">広告について</h2>
              <p>{model.article.disclosureText}</p>
            </div>
          </aside>

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
