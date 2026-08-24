import type { MetadataRoute } from 'next';

import { createLocalSitemapRuntimeEntries } from '../src/local-seo-runtime.ts';

export default function sitemap(): MetadataRoute.Sitemap {
  return createLocalSitemapRuntimeEntries();
}
