import type { ReactNode } from 'react';

import {
  PUBLIC_POLICY_PAGES,
  getPublicPolicyPage,
  type PublicPolicyRoute,
  type PublicPolicyScreenId,
} from './public-policy';

const STATUS_LABELS = {
  CANONICAL_PRINCIPLE: '編集原則',
  SAFE_DEFAULT: '安全な初期状態',
  OWNER_DECISION_REQUIRED: '決定待ち',
  LEGAL_REVIEW_REQUIRED: '法務確認待ち',
} as const;

function ShellLink({
  children,
  href,
}: {
  readonly children: ReactNode;
  readonly href: PublicPolicyRoute;
}) {
  return <a href={href}>{children}</a>;
}

function PublicHeader({ current }: { readonly current: PublicPolicyScreenId }) {
  return (
    <header className="public-header" id="public-shell-header">
      <div className="public-header__inner">
        <div className="public-identity">
          <span className="public-identity__mark" aria-hidden="true">
            基
          </span>
          <span>
            <span className="public-identity__name">公開情報</span>
            <span className="public-identity__note">根拠と判断の方針</span>
          </span>
        </div>
        <nav className="primary-nav" aria-label="主要な方針ページ">
          <ul>
            {PUBLIC_POLICY_PAGES.map((page) => (
              <li key={page.screenId}>
                <ShellLink href={page.route}>
                  <span aria-current={page.screenId === current ? 'page' : undefined}>
                    {page.title}
                  </span>
                </ShellLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}

function Breadcrumb({ current }: { readonly current: PublicPolicyScreenId }) {
  const page = getPublicPolicyPage(current);
  return (
    <nav className="breadcrumb" aria-label="現在位置">
      <ol>
        <li>
          <span aria-current="page">{page.title}</span>
        </li>
      </ol>
    </nav>
  );
}

function PublicFooter() {
  return (
    <footer className="public-footer" id="public-shell-footer">
      <div className="public-footer__inner">
        <div>
          <p className="public-footer__heading">公開情報</p>
          <p>サイト名・運営者・問い合わせ先は承認待ちです。</p>
        </div>
        <nav aria-label="方針と運営情報">
          <ul>
            {PUBLIC_POLICY_PAGES.map((page) => (
              <li key={page.screenId}>
                <ShellLink href={page.route}>{page.title}</ShellLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}

export function PublicPolicyPage({ screenId }: { readonly screenId: PublicPolicyScreenId }) {
  const page = getPublicPolicyPage(screenId);
  return (
    <div className="site-frame">
      <a className="skip-link" href="#public-shell-main">
        本文へ移動
      </a>
      <PublicHeader current={screenId} />
      <main className="policy-main" id="public-shell-main" tabIndex={-1}>
        <Breadcrumb current={screenId} />
        <article className="policy-article" aria-labelledby="public-shell-heading">
          <header className="policy-hero">
            <p className="policy-hero__eyebrow">POLICY / LOCAL PREVIEW</p>
            <h1 id="public-shell-heading">{page.title}</h1>
            <p className="policy-hero__lead">{page.lead}</p>
          </header>

          <aside className="preview-notice" aria-labelledby="preview-notice-heading">
            <span className="preview-notice__icon" aria-hidden="true">
              i
            </span>
            <div>
              <h2 id="preview-notice-heading">公開前のローカル実装</h2>
              <p>
                サイト名、ドメイン、運営者、Privacy・同意、法務文言は未確定です。この表示は外部公開に使用できません。
              </p>
            </div>
          </aside>

          <div className="policy-sections">
            {page.sections.map((section) => (
              <section className="policy-card" key={section.id}>
                <p className={`status-label status-label--${section.state.toLowerCase()}`}>
                  <span aria-hidden="true" />
                  {STATUS_LABELS[section.state]}
                </p>
                <h2>{section.heading}</h2>
                <p>{section.body}</p>
              </section>
            ))}
          </div>
        </article>
      </main>
      <PublicFooter />
    </div>
  );
}
