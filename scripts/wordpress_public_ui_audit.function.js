async (page) => {
  const runtimeErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') runtimeErrors.push(`console:${message.text()}`);
  });
  page.on('pageerror', (error) => runtimeErrors.push(`page:${error.name}`));
  await page.reload({ waitUntil: 'networkidle' });

  const results = [];
  for (const width of [360, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(150);
    const audit = await page.evaluate(() => {
      const ids = [...document.querySelectorAll('[id]')].map((element) => element.id);
      const duplicateIds = [...new Set(ids.filter((id, index) => id && ids.indexOf(id) !== index))];
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
        title: document.title,
        lang: document.documentElement.lang,
        h1Count: document.querySelectorAll('h1').length,
        mainCount: document.querySelectorAll('main').length,
        missingAlt: document.querySelectorAll('img:not([alt])').length,
        unlabeledControls,
        duplicateIds,
        brokenAriaReferences,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      };
    });
    if (
      audit.title.trim() === '' ||
      !audit.lang.toLowerCase().startsWith('ja') ||
      audit.h1Count !== 1 ||
      audit.mainCount !== 1 ||
      audit.missingAlt !== 0 ||
      audit.unlabeledControls !== 0 ||
      audit.duplicateIds.length !== 0 ||
      audit.brokenAriaReferences !== 0 ||
      audit.scrollWidth > audit.clientWidth
    ) {
      throw new Error(`WORDPRESS_PUBLIC_UI_AUDIT_FAILED_${width}`);
    }
    const screenshot = `/home/minami/rakuten/output/playwright/wordpress-home-${width}.png`;
    await page.screenshot({ path: screenshot, fullPage: true });
    results.push({ ...audit, screenshot, width });
  }
  if (runtimeErrors.length !== 0) {
    throw new Error('WORDPRESS_PUBLIC_UI_RUNTIME_ERROR');
  }
  return results;
}
