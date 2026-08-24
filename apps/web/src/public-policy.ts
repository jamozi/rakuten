import type { Metadata } from 'next';

import { PUBLIC_POLICY_CONTENT_SOURCE } from './public-policy-content.generated.ts';

export const PUBLIC_POLICY_SCREEN_IDS = Object.freeze([
  'PUB-004',
  'PUB-005',
  'PUB-006',
  'PUB-007',
] as const);

export type PublicPolicyScreenId = (typeof PUBLIC_POLICY_SCREEN_IDS)[number];
export type PublicPolicySectionState =
  'CANONICAL_PRINCIPLE' | 'SAFE_DEFAULT' | 'OWNER_DECISION_REQUIRED' | 'LEGAL_REVIEW_REQUIRED';

export interface PublicPolicySectionRecord {
  readonly id: string;
  readonly heading: string;
  readonly body: string;
  readonly state: PublicPolicySectionState;
  readonly sourceRef: string;
}

export interface PublicPolicyPageRecord {
  readonly screenId: PublicPolicyScreenId;
  readonly route: '/editorial-policy' | '/affiliate-disclosure' | '/privacy' | '/about';
  readonly title: '編集方針' | '広告・Affiliate開示' | 'Privacy Policy' | '運営者・問い合わせ';
  readonly purpose: string;
  readonly description: string;
  readonly lead: string;
  readonly sections: readonly PublicPolicySectionRecord[];
}

export interface PublicPolicyContentSource {
  readonly schemaVersion: 2;
  readonly storyId: 'ST-1001';
  readonly classification: 'LOCAL_ONLY_UNBRANDED_SSR_POLICY_PREVIEW_V2';
  readonly pages: readonly PublicPolicyPageRecord[];
  readonly runtimeBoundary: Readonly<Record<string, unknown>>;
  readonly identityBoundary: Readonly<Record<string, unknown>>;
  readonly privacyBoundary: Readonly<Record<string, unknown>>;
  readonly metadataPolicy: Readonly<Record<string, unknown>>;
  readonly shell: Readonly<Record<string, unknown>>;
  readonly securityHeaders: Readonly<Record<string, unknown>>;
  readonly authority: Readonly<Record<string, false | 'NOT_EXECUTED'>>;
}

export type PublicPolicyPage = PublicPolicyContentSource['pages'][number];
export type PublicPolicyRoute = PublicPolicyPage['route'];

export const PUBLIC_POLICY_ERROR_CODES = Object.freeze([
  'PUBLIC_POLICY_SCREEN_UNKNOWN',
  'PUBLIC_POLICY_CONTRACT_INVALID',
] as const);

export type PublicPolicyErrorCode = (typeof PUBLIC_POLICY_ERROR_CODES)[number];

export class PublicPolicyError extends TypeError {
  readonly code: PublicPolicyErrorCode;

  constructor(code: PublicPolicyErrorCode) {
    super(code);
    this.name = 'PublicPolicyError';
    this.code = code;
    Object.freeze(this);
  }
}

function freezeTree(value: unknown, visited = new WeakSet<object>()): void {
  if (typeof value !== 'object' || value === null || visited.has(value)) {
    return;
  }
  visited.add(value);
  for (const child of Object.values(value)) {
    freezeTree(child, visited);
  }
  Object.freeze(value);
}

function reject(code: PublicPolicyErrorCode): never {
  throw new PublicPolicyError(code);
}

function hasItems(value: readonly unknown[]): boolean {
  return value.length > 0;
}

function validateSource(): void {
  const pages = PUBLIC_POLICY_CONTENT_SOURCE.pages;
  if (
    pages.length !== PUBLIC_POLICY_SCREEN_IDS.length ||
    pages.some((page, index) => page.screenId !== PUBLIC_POLICY_SCREEN_IDS[index]) ||
    new Set(pages.map(({ route }) => route)).size !== pages.length ||
    pages.some(
      (page) =>
        !hasItems(page.sections) ||
        new Set(page.sections.map(({ id }) => id)).size !== page.sections.length,
    )
  ) {
    reject('PUBLIC_POLICY_CONTRACT_INVALID');
  }
  freezeTree(PUBLIC_POLICY_CONTENT_SOURCE);
}

validateSource();

export const PUBLIC_POLICY_PAGES = PUBLIC_POLICY_CONTENT_SOURCE.pages;
export const PUBLIC_POLICY_ROUTES = Object.freeze(
  PUBLIC_POLICY_PAGES.map(({ route }) => route),
) as readonly PublicPolicyRoute[];

export function getPublicPolicyPage(screenId: PublicPolicyScreenId): PublicPolicyPage {
  const page = PUBLIC_POLICY_PAGES.find((candidate) => candidate.screenId === screenId);
  return page ?? reject('PUBLIC_POLICY_SCREEN_UNKNOWN');
}

export function createPublicPolicyMetadata(screenId: PublicPolicyScreenId): Metadata {
  const page = getPublicPolicyPage(screenId);
  return {
    title: page.title,
    description: page.description,
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
