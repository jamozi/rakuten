async (page) => {
  const origin = 'https://kurashinoshirube.com';
  const surfaces = [
    { name: 'home', path: '/' },
    { article: true, name: 'carryclassic', path: '/carry-on-suitcase-comparison/' },
    { article: true, name: 'powerguide', path: '/portable-power-station-guide/' },
    { article: true, name: 'ankermodels', path: '/anker-solix-c300-c800-c1000-differences/' },
    { article: true, name: 'smalldishwasher', path: '/countertop-dishwasher-for-small-households/' },
    { article: true, name: 'compactrobot', path: '/compact-robot-vacuum-shortlist/' },
    { article: true, name: 'under100', path: '/carry-on-suitcase-under-100-seats/' },
    { article: true, name: 'under3kg', path: '/lightweight-carry-on-suitcase-under-3kg/' },
    { article: true, name: 'frontstop', path: '/front-open-carry-on-suitcase-with-stopper/' },
    { article: true, name: 'roomba', path: '/roomba-mini-vs-switchbot-k11-pro/' },
    { article: true, name: 'dishwasher', path: '/solota-vs-rakua-mini-plus/' },
    { name: 'about', path: '/about-ad-policy/' },
    { name: 'comparisonpolicy', path: '/comparison-policy/' },
    { name: 'privacy', path: '/privacy-policy/' },
  ];
  const widths = [360, 390, 768, 1440];
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
        throw new Error(`WORDPRESS_PUBLIC_UI_HTTP_FAILED_${surface.name}_${width}`);
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
        return {
          brokenAriaReferences,
          clientWidth: document.documentElement.clientWidth,
          contextualLinks: document.querySelectorAll(
            '[data-raos-link-placement="article_body"][data-raos-to-article-id]',
          ).length,
          ctas: document.querySelectorAll('.raos-cta[data-raos-placement]').length,
          duplicateIds,
          editorialRoots: document.querySelectorAll('.raos-editorial-v2').length,
          h1Count: document.querySelectorAll('h1').length,
          lang: document.documentElement.lang,
          mainCount: document.querySelectorAll('main').length,
          missingAlt: document.querySelectorAll('img:not([alt])').length,
          relatedLinks: document.querySelectorAll(
            '[data-raos-link-placement="related_navigation"][data-raos-to-article-id]',
          ).length,
          scrollWidth: document.documentElement.scrollWidth,
          title: document.title,
          unlabeledControls,
        };
      });
      const articleFailed = surface.article && (
        audit.editorialRoots !== 1 ||
        audit.ctas < 1 ||
        audit.contextualLinks < 1 ||
        audit.contextualLinks > 2 ||
        audit.relatedLinks < 2
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
        articleFailed
      ) {
        throw new Error(`WORDPRESS_PUBLIC_UI_AUDIT_FAILED_${surface.name}_${width}`);
      }
      const screenshot = `${process.cwd()}/output/playwright/wordpress-${surface.name}-${width}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({ ...audit, screenshot, surface: surface.name, width });
    }
  }
  if (runtimeErrors.length !== 0) {
    throw new Error('WORDPRESS_PUBLIC_UI_RUNTIME_ERROR');
  }
  if (results.length !== 56) {
    throw new Error('WORDPRESS_PUBLIC_UI_SCREEN_COUNT_INVALID');
  }
  return results;
}
