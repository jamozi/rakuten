import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import {
  resolveRecordedPublicArticleV2,
  type PublicArticleViewModelV2,
} from '../../../../../packages/web-ui/src/public-article-renderer.ts';
import { PublicArticlePage } from '../../../src/public-article-page.tsx';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface ArticleRouteProps {
  readonly params: Promise<{ readonly slug: string }>;
}

function requireArticle(slug: unknown): PublicArticleViewModelV2 {
  return resolveRecordedPublicArticleV2(slug) ?? notFound();
}

export async function generateMetadata({ params }: ArticleRouteProps): Promise<Metadata> {
  const model = requireArticle((await params).slug);
  return {
    title: model.metadata.title,
    description: model.metadata.description,
    robots: {
      index: false,
      follow: false,
      noarchive: true,
      nosnippet: true,
      noimageindex: true,
      nocache: true,
      googleBot: {
        index: false,
        follow: false,
        noarchive: true,
        nosnippet: true,
        noimageindex: true,
      },
    },
  };
}

export default async function RecordedPublicArticleRoute({ params }: ArticleRouteProps) {
  const model = requireArticle((await params).slug);
  return <PublicArticlePage model={model} />;
}
