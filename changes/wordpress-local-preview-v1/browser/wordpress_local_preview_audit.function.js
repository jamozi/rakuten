async (page) => {
  const origin = 'http://127.0.0.1:8888';
  const artifactDirectory = '/home/minami/rakuten/output/playwright/local-preview';
  const surfaces = [
    { name: 'home', path: '/' },
    {
      name: 'article',
      path: '/local-preview-carry-on-suitcase-comparison/',
    },
  ];
  const widths = [360, 390, 768, 1440];
  const runtimeErrors = [];
  const externalRequests = [];

  page.on('console', (message) => {
    if (message.type() === 'error') runtimeErrors.push(`console:${message.text()}`);
  });
  page.on('pageerror', (error) => runtimeErrors.push(`page:${error.name}`));
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith(`${origin}/`) && !url.startsWith('data:') && !url.startsWith('blob:')) {
      externalRequests.push(url);
    }
  });

  const results = [];
  for (const surface of surfaces) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      const response = await page.goto(`${origin}${surface.path}`, {
        waitUntil: 'networkidle',
      });
      if (!response || !response.ok()) {
        throw new Error(`RAOS_WORDPRESS_LOCAL_PREVIEW_HTTP_FAILED_${surface.name}`);
      }
      const audit = await page.evaluate(() => {
        const ids = [...document.querySelectorAll('[id]')]
          .map((element) => element.id)
          .filter(Boolean);
        const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
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
        const banner = document.querySelector('.raos-local-preview-banner');
        return {
          bannerText: banner?.textContent?.trim() || '',
          brokenAriaReferences,
          clientWidth: document.documentElement.clientWidth,
          duplicateIds,
          h1Count: document.querySelectorAll('h1').length,
          lang: document.documentElement.lang,
          mainCount: document.querySelectorAll('main').length,
          missingAlt: document.querySelectorAll('img:not([alt])').length,
          scrollWidth: document.documentElement.scrollWidth,
          title: document.title,
          unlabeledControls,
        };
      });
      if (
        audit.title.trim() === '' ||
        !audit.lang.toLowerCase().startsWith('ja') ||
        audit.bannerText !== 'LOCAL WORDPRESS PREVIEW — 本番表示ではありません' ||
        audit.h1Count !== 1 ||
        audit.mainCount !== 1 ||
        audit.missingAlt !== 0 ||
        audit.unlabeledControls !== 0 ||
        audit.duplicateIds.length !== 0 ||
        audit.brokenAriaReferences !== 0 ||
        audit.scrollWidth > audit.clientWidth
      ) {
        throw new Error(`RAOS_WORDPRESS_LOCAL_PREVIEW_AUDIT_FAILED_${surface.name}_${width}`);
      }
      const screenshot = `${artifactDirectory}/local-preview-${surface.name}-${width}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({ ...audit, screenshot, surface: surface.name, width });
    }
  }
  if (runtimeErrors.length !== 0) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_RUNTIME_ERROR');
  }
  if (externalRequests.length !== 0) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_EXTERNAL_REQUEST');
  }
  return results;
}
