/**
 * Maximum-safe ST-1005 runtime policy for the recorded local preview.
 *
 * The runtime intentionally has no site origin and no indexable route. It
 * cannot synthesize a canonical URL or sitemap entry while OD-002 and a
 * current approved publication are unavailable.
 */

export const LOCAL_SEO_RUNTIME_CLASSIFICATION =
  'ST1005_LOCAL_PREVIEW_FAIL_CLOSED_RUNTIME_V2' as const;

export const LOCAL_SEO_RUNTIME_POLICY = Object.freeze({
  classification: LOCAL_SEO_RUNTIME_CLASSIFICATION,
  activation: 'LOCAL_DEV_CI_ONLY',
  originAuthority: 'UNAVAILABLE_UNRESOLVED_OD_002',
  currentPublication: 'UNAVAILABLE',
  exactArticlePath: '/articles/synthetic-recorded-policy-seo',
  articleIndexState: 'NOINDEX_NOFOLLOW',
  canonicalUrl: null,
  canonicalActivated: false,
  robotsMode: 'DISALLOW_ALL',
  sitemapMode: 'EMPTY_NO_ELIGIBLE_ENTRIES',
  sitemapEligibility: Object.freeze({
    published: false,
    http200: false,
    indexable: false,
    selfCanonical: false,
    notPaused: false,
    currentPublicationSnapshot: false,
  }),
  draftPreviewFacetIndexState: 'NOINDEX_NOFOLLOW',
  publicationAuthorized: false,
  releaseAuthorized: false,
  productionAuthorized: false,
  formalEvidence: false,
} as const);

export interface LocalRobotsRuntimePolicy {
  readonly rules: {
    readonly userAgent: '*';
    readonly disallow: '/';
  };
}

export function createLocalRobotsRuntimePolicy(): LocalRobotsRuntimePolicy {
  return {
    rules: {
      userAgent: '*',
      disallow: '/',
    },
  };
}

export function createLocalSitemapRuntimeEntries(): [] {
  return [];
}
