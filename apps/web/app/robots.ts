import type { MetadataRoute } from 'next';

import { createLocalRobotsRuntimePolicy } from '../src/local-seo-runtime.ts';

export default function robots(): MetadataRoute.Robots {
  return createLocalRobotsRuntimePolicy();
}
