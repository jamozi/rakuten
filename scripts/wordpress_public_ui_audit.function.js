({ artifactDirectory, inventory }) => async (page) => {
  const origin = inventory?.target_origin;
  const cleanPath = (value) =>
    typeof value === 'string' && /^\/(?:[a-z0-9]+(?:-[a-z0-9]+)*\/)?$/.test(value);
  const rawSurfaces = inventory?.surfaces;
  const rawClusters = inventory?.clusters;
  const widths = inventory?.viewports;
  const articleRows = Array.isArray(rawSurfaces)
    ? rawSurfaces.filter((surface) => surface.kind === 'article')
    : [];
  const policyRows = Array.isArray(rawSurfaces)
    ? rawSurfaces.filter((surface) => surface.kind === 'policy')
    : [];
  const homeRows = Array.isArray(rawSurfaces)
    ? rawSurfaces.filter((surface) => surface.kind === 'home')
    : [];
  const articleIds = new Set(articleRows.map((surface) => surface.article_id));
  const memberships = Array.isArray(rawClusters)
    ? rawClusters.flatMap((cluster) => cluster.article_ids || [])
    : [];
  if (
    typeof artifactDirectory !== 'string' || !artifactDirectory.startsWith('/') ||
    inventory?.schema !== 'RAOS_WORDPRESS_AUDIT_INVENTORY_V3' ||
    inventory?.version !== '3.0.0' ||
    origin !== 'https://kurashinoshirube.com' ||
    !Array.isArray(rawSurfaces) || rawSurfaces.length !== 14 ||
    homeRows.length !== 1 || articleRows.length !== 10 || policyRows.length !== 3 ||
    !Array.isArray(rawClusters) || rawClusters.length !== 3 ||
    !Array.isArray(widths) || widths.length !== 4 ||
    new Set(widths).size !== widths.length ||
    widths.some((width) => !Number.isInteger(width) || width < 320 || width > 1920) ||
    new Set(rawSurfaces.map((surface) => surface.surface_id)).size !== 14 ||
    rawSurfaces.some(
      (surface) =>
        !['home', 'article', 'policy'].includes(surface.kind) ||
        typeof surface.surface_id !== 'string' ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(surface.surface_id) ||
        !cleanPath(surface.local_path) || !cleanPath(surface.production_path),
    ) ||
    articleIds.size !== 10 ||
    articleRows.some(
      (surface) =>
        typeof surface.article_id !== 'string' ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(surface.article_id) ||
        !articleIds.has(surface.contextual_article_id) ||
        !Array.isArray(surface.related_article_ids) ||
        surface.related_article_ids.length < 2 ||
        new Set(surface.related_article_ids).size !== surface.related_article_ids.length ||
        !surface.related_article_ids.includes(surface.contextual_article_id) ||
        surface.related_article_ids.some(
          (articleId) => articleId === surface.article_id || !articleIds.has(articleId),
        ),
    ) ||
    rawClusters.some(
      (cluster) =>
        typeof cluster.anchor !== 'string' || !/^cluster-[a-z0-9-]+$/.test(cluster.anchor) ||
        !Array.isArray(cluster.article_ids) || cluster.article_ids.length < 2 ||
        new Set(cluster.article_ids).size !== cluster.article_ids.length ||
        cluster.article_ids.some((articleId) => !articleIds.has(articleId)),
    ) ||
    memberships.length !== 10 || new Set(memberships).size !== 10 ||
    memberships.some((articleId) => !articleIds.has(articleId))
  ) {
    throw new Error('WORDPRESS_PUBLIC_UI_INVENTORY_INVALID');
  }
  const surfaces = rawSurfaces.map((surface) => ({
    ...surface,
    path: surface.production_path,
  }));
  const expectedPathByArticleId = Object.fromEntries(
    articleRows.map((surface) => [surface.article_id, surface.production_path]),
  );
  const runtimeErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') runtimeErrors.push(`console:${message.text()}`);
  });
  page.on('pageerror', (error) => runtimeErrors.push(`page:${error.name}`));

  const results = [];
  for (const surface of surfaces) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      const expectedUrl = `${origin}${surface.path}`;
      const response = await page.goto(expectedUrl, { waitUntil: 'networkidle' });
      if (!response || response.status() !== 200 || response.url() !== expectedUrl) {
        throw new Error(`WORDPRESS_PUBLIC_UI_HTTP_FAILED_${surface.surface_id}_${width}`);
      }
      const audit = await page.evaluate(() => {
        const ids = [...document.querySelectorAll('[id]')].map((element) => element.id);
        const duplicateIds = [...new Set(
          ids.filter((id, index) => id && ids.indexOf(id) !== index),
        )];
        const controls = [
          ...document.querySelectorAll('input:not([type=hidden]),select,textarea,button'),
        ];
        const unlabeledControls = controls.filter(
          (element) =>
            element.tagName !== 'BUTTON' &&
            !element.labels?.length &&
            !element.getAttribute('aria-label') &&
            !element.getAttribute('aria-labelledby'),
        ).length;
        const brokenAriaReferences = [
          ...document.querySelectorAll('[aria-labelledby],[aria-describedby]'),
        ].filter((element) => {
          const references = [
            ...(element.getAttribute('aria-labelledby') || '').split(/\s+/),
            ...(element.getAttribute('aria-describedby') || '').split(/\s+/),
          ].filter(Boolean);
          return references.some((id) => !document.getElementById(id));
        }).length;
        const linkRecord = (anchor) => {
          const target = new URL(anchor.href);
          return {
            hash: target.hash,
            href: target.href,
            origin: target.origin,
            pathname: target.pathname,
            placement: anchor.getAttribute('data-raos-link-placement'),
            search: target.search,
            targetArticleId: anchor.getAttribute('data-raos-to-article-id'),
          };
        };
        return {
          brokenAriaReferences,
          clientWidth: document.documentElement.clientWidth,
          ctas: document.querySelectorAll('.raos-cta[data-raos-placement]').length,
          duplicateIds,
          editorialRoots: document.querySelectorAll('.raos-editorial-v2').length,
          h1Count: document.querySelectorAll('h1').length,
          homeClusters: [
            ...document.querySelectorAll('.raos-cluster-nav .raos-cluster'),
          ].map((cluster) => ({
            anchor: cluster.id,
            links: [...cluster.querySelectorAll('ul a[href]')].map(linkRecord),
          })),
          internalLinks: [...document.querySelectorAll(
            'a[data-raos-link-placement="article_body"],'
              + 'a[data-raos-link-placement="related_navigation"]',
          )].map(linkRecord),
          lang: document.documentElement.lang,
          mainCount: document.querySelectorAll('main').length,
          missingAlt: document.querySelectorAll('img:not([alt])').length,
          scrollWidth: document.documentElement.scrollWidth,
          title: document.title,
          unlabeledControls,
        };
      });

      let internalLinkReadbackFailed = false;
      if (surface.kind === 'article') {
        const expectedInternalLinks = [
          {
            placement: 'article_body',
            targetArticleId: surface.contextual_article_id,
          },
          ...surface.related_article_ids.map((targetArticleId) => ({
            placement: 'related_navigation',
            targetArticleId,
          })),
        ];
        const signature = (link) => `${link.placement}|${link.targetArticleId}`;
        if (
          audit.internalLinks.length !== expectedInternalLinks.length ||
          audit.internalLinks.map(signature).sort().join('\n') !==
            expectedInternalLinks.map(signature).sort().join('\n')
        ) {
          internalLinkReadbackFailed = true;
        }
        for (const link of audit.internalLinks) {
          const expectedPath = expectedPathByArticleId[link.targetArticleId];
          if (
            !expectedPath || link.origin !== origin ||
            link.pathname !== expectedPath || link.search !== '' || link.hash !== '' ||
            !['article_body', 'related_navigation'].includes(link.placement)
          ) {
            internalLinkReadbackFailed = true;
            continue;
          }
          if (width === 390) {
            const linkResponse = await page.request.get(link.href, { maxRedirects: 0 });
            if (linkResponse.status() !== 200 || linkResponse.url() !== link.href) {
              internalLinkReadbackFailed = true;
            }
          }
        }
      } else if (audit.internalLinks.length !== 0) {
        internalLinkReadbackFailed = true;
      }

      let homepageReadbackFailed = false;
      if (surface.kind === 'home') {
        const expectedClusters = rawClusters.map((cluster) => ({
          anchor: cluster.anchor,
          paths: cluster.article_ids.map(
            (articleId) => expectedPathByArticleId[articleId],
          ),
        }));
        if (
          audit.homeClusters.length !== expectedClusters.length ||
          audit.homeClusters.some((cluster, index) => {
            const expected = expectedClusters[index];
            return !expected || cluster.anchor !== expected.anchor ||
              cluster.links.length !== expected.paths.length ||
              cluster.links.some(
                (link, linkIndex) =>
                  link.origin !== origin ||
                  link.pathname !== expected.paths[linkIndex] ||
                  link.search !== '' || link.hash !== '',
              );
          })
        ) {
          homepageReadbackFailed = true;
        }
        if (width === 390) {
          for (const cluster of audit.homeClusters) {
            for (const link of cluster.links) {
              const linkResponse = await page.request.get(link.href, { maxRedirects: 0 });
              if (linkResponse.status() !== 200 || linkResponse.url() !== link.href) {
                homepageReadbackFailed = true;
              }
            }
          }
        }
      } else if (audit.homeClusters.length !== 0) {
        homepageReadbackFailed = true;
      }

      const articleFailed = surface.kind === 'article' && (
        audit.editorialRoots !== 1 ||
        audit.ctas < 1 ||
        audit.internalLinks.filter((link) => link.placement === 'article_body').length !== 1 ||
        audit.internalLinks.filter(
          (link) => link.placement === 'related_navigation',
        ).length !== surface.related_article_ids.length
      );
      if (
        audit.title.trim() === '' ||
        !audit.lang.toLowerCase().startsWith('ja') ||
        audit.h1Count !== 1 ||
        audit.mainCount !== 1 ||
        audit.missingAlt !== 0 ||
        audit.unlabeledControls !== 0 ||
        audit.duplicateIds.length !== 0 ||
        audit.brokenAriaReferences !== 0 ||
        audit.scrollWidth > audit.clientWidth ||
        articleFailed ||
        internalLinkReadbackFailed ||
        homepageReadbackFailed
      ) {
        throw new Error(`WORDPRESS_PUBLIC_UI_AUDIT_FAILED_${surface.surface_id}_${width}`);
      }
      const screenshot = `${artifactDirectory}/wordpress-${surface.surface_id}-${width}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({
        ...audit,
        homepageReadbackFailed,
        internalLinkReadbackFailed,
        screenshot,
        surface: surface.surface_id,
        width,
      });
    }
  }
  if (runtimeErrors.length !== 0) {
    throw new Error('WORDPRESS_PUBLIC_UI_RUNTIME_ERROR');
  }
  if (results.length !== surfaces.length * widths.length) {
    throw new Error('WORDPRESS_PUBLIC_UI_SCREEN_COUNT_INVALID');
  }
  return results;
}
