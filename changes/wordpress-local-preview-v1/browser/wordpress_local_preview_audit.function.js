({ artifactDirectory, inventory }) => async (page) => {
  const origin = 'http://127.0.0.1:8888';
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
    inventory?.target_origin !== 'https://kurashinoshirube.com' ||
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
    throw new Error('RAOS_WORDPRESS_AUDIT_INVENTORY_INVALID');
  }
  const surfaces = rawSurfaces.map((surface) => ({
    ...surface,
    article: surface.kind === 'article',
    articleId: surface.article_id,
    name: surface.surface_id,
    path: surface.local_path,
  }));
  const articleSurfaces = surfaces.filter((surface) => surface.article);
  const expectedPathByArticleId = Object.fromEntries(
    articleSurfaces.map((surface) => [surface.articleId, surface.path]),
  );
  const runtimeErrors = [];
  const externalRequests = [];
  const measurementRequests = [];

  page.on('console', (message) => {
    if (message.type() === 'error') runtimeErrors.push(`console:${message.text()}`);
  });
  page.on('pageerror', (error) => runtimeErrors.push(`page:${error.name}`));
  page.on('request', (request) => {
    const url = request.url();
    if (url === `${origin}/wp-json/raos/v1/events`) {
      measurementRequests.push(url);
    }
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
      if (surface.article) {
        await page.evaluate(() => {
          if (!document.body.classList.contains('single-post')) {
            throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_SINGLE_POST_CLASS_MISSING');
          }
          const base = document.createElement('style');
          base.dataset.raosCookieyesAuditBase = '1';
          base.textContent = `
            [data-raos-cookieyes-audit] {
              bottom: 20px;
              box-sizing: border-box;
              left: 20px;
              position: fixed;
              width: 440px;
              z-index: 999999;
            }
            [data-raos-cookieyes-audit] .cky-consent-bar {
              background: #fff;
              border: 1px solid #d8d8d8;
              border-radius: 6px;
              box-shadow: 0 3px 18px rgb(0 0 0 / 18%);
              box-sizing: border-box;
              padding: 24px;
            }
            [data-raos-cookieyes-audit] .cky-title {
              display: block;
              font-size: 18px;
              font-weight: 700;
              line-height: 1.35;
              margin: 0 0 12px;
            }
            [data-raos-cookieyes-audit] .cky-notice-des {
              font-size: 14px;
              line-height: 1.5;
              margin: 0 0 16px;
            }
            [data-raos-cookieyes-audit] .cky-notice-des p { margin: 0; }
            [data-raos-cookieyes-audit] .cky-notice-btn-wrapper {
              display: flex;
              flex-direction: column;
              gap: 8px;
            }
            [data-raos-cookieyes-audit] .cky-btn {
              background: #fff;
              border: 1px solid #24365f;
              box-sizing: border-box;
              color: #17243f;
              cursor: pointer;
              min-height: 40px;
              width: 100%;
            }
          `;
          document.head.append(base);
          const container = document.createElement('div');
          container.className = 'cky-consent-container cky-box-bottom-left';
          container.dataset.raosCookieyesAudit = '1';
          container.setAttribute('role', 'dialog');
          container.setAttribute('aria-label', 'Cookieの同意');
          container.innerHTML = `
            <div class="cky-consent-bar">
              <div class="cky-notice">
                <p class="cky-title">Cookieを使用しています</p>
                <div class="cky-notice-des"><p>当サイトでは、閲覧体験の改善、利用状況の分析、関連する情報のご案内のためCookieを使用します。設定はいつでも変更できます。</p></div>
                <div class="cky-notice-btn-wrapper">
                  <button type="button" class="cky-btn cky-btn-customize">設定</button>
                  <button type="button" class="cky-btn cky-btn-reject">拒否</button>
                  <button type="button" class="cky-btn cky-btn-accept">同意</button>
                </div>
              </div>
            </div>
          `;
          document.body.append(container);
        });
      }
      await page.evaluate(async () => {
        await Promise.all(
          [...document.images].map(
            (image) =>
              new Promise((resolve) => {
                image.loading = 'eager';
                if (image.complete) {
                  resolve();
                  return;
                }
                image.addEventListener('load', resolve, { once: true });
                image.addEventListener('error', resolve, { once: true });
              }),
          ),
        );
      });
      const audit = await page.evaluate(() => {
        const boundingBoxes = (selector) =>
          [...document.querySelectorAll(selector)].map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              bottom: rect.bottom,
              height: rect.height,
              left: rect.left,
              right: rect.right,
              top: rect.top,
              width: rect.width,
            };
          });
        const clientWidth = document.documentElement.clientWidth;
        const invalidBoundingBoxCount = (boxes) =>
          boxes.filter(
            (box) =>
              !Object.values(box).every(Number.isFinite) ||
              box.width <= 0 ||
              box.height <= 0 ||
              box.left < -0.5 ||
              box.right > clientWidth + 0.5,
          ).length;
        const visibleCount = (selector) =>
          [...document.querySelectorAll(selector)].filter((element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return (
              style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 0 &&
              rect.height > 0
            );
          }).length;
        const overlaps = (first, second) =>
          first.left < second.right &&
          first.right > second.left &&
          first.top < second.bottom &&
          first.bottom > second.top;
        const textLineMetrics = (element) => {
          if (!element) return { lastLineCharacters: 0, lineCount: 0 };
          const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
          const lines = [];
          while (walker.nextNode()) {
            const node = walker.currentNode;
            for (let index = 0; index < node.data.length; index += 1) {
              const character = node.data[index];
              if (/\s/u.test(character)) continue;
              const range = document.createRange();
              range.setStart(node, index);
              range.setEnd(node, index + 1);
              const rect = range.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) continue;
              let line = lines.find((candidate) => Math.abs(candidate.top - rect.top) < 1);
              if (!line) {
                line = { characters: 0, top: rect.top };
                lines.push(line);
              }
              line.characters += 1;
            }
          }
          lines.sort((left, right) => left.top - right.top);
          return {
            lastLineCharacters: lines.at(-1)?.characters || 0,
            lineCount: lines.length,
          };
        };
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
        const ariaReferenceAttributes = [
          'aria-activedescendant',
          'aria-controls',
          'aria-describedby',
          'aria-details',
          'aria-labelledby',
          'aria-owns',
        ];
        const brokenAriaReferences = [
          ...document.querySelectorAll(
            ariaReferenceAttributes.map((name) => `[${name}]`).join(','),
          ),
        ].filter((element) => {
          const references = ariaReferenceAttributes.flatMap((name) =>
            (element.getAttribute(name) || '').split(/\s+/).filter(Boolean),
          );
          return references.some((id) => !document.getElementById(id));
        }).length;
        const banner = document.querySelector('.raos-local-preview-banner');
        const cookieSettingsBounds = boundingBoxes('.raos-cookie-settings');
        const ctaBounds = boundingBoxes('.raos-cta[data-raos-placement]');
        const h1Bounds = boundingBoxes('h1');
        const h1LineMetrics = textLineMetrics(document.querySelector('h1'));
        const cookieConsentBounds = boundingBoxes(
          '.cky-consent-container.cky-box-bottom-left[data-raos-cookieyes-audit]',
        );
        const cookieButtonBounds = boundingBoxes(
          '[data-raos-cookieyes-audit] .cky-notice-btn-wrapper .cky-btn',
        );
        const cookieButtonOrder = [
          ...document.querySelectorAll(
            '[data-raos-cookieyes-audit] .cky-notice-btn-wrapper .cky-btn',
          ),
        ].map((button) => button.textContent.trim());
        const cookieConsent = cookieConsentBounds[0];
        let measurementSessionKeyCount = 0;
        try {
          for (let index = 0; index < window.sessionStorage.length; index += 1) {
            const key = window.sessionStorage.key(index);
            if (typeof key === 'string' && key.startsWith('raos_measurement_v1:')) {
              measurementSessionKeyCount += 1;
            }
          }
        } catch (error) {
          measurementSessionKeyCount = -1;
        }
        return {
          bannerText: banner?.textContent?.trim() || '',
          brokenAriaReferences,
          clientWidth,
          comparisonSectionCount: document.querySelectorAll('.comparison-section').length,
          comparisonCardsVisible: visibleCount(
            '.comparison-cards, .raos-comparison__cards',
          ),
          comparisonTablesVisible: visibleCount(
            '.comparison-table-wrap table',
          ),
          cookieButtonBounds,
          cookieButtonOrder,
          cookieConsentBounds,
          cookieOverlapsCta:
            cookieConsent
              ? ctaBounds.filter((bounds) => overlaps(cookieConsent, bounds)).length
              : 0,
          cookieOverlapsH1:
            cookieConsent && h1Bounds[0] ? overlaps(cookieConsent, h1Bounds[0]) : false,
          cookieSettingsBounds,
          ctaBounds,
          decisionListCount: document.querySelectorAll('.decision-list').length,
          duplicateIds,
          editorialRootCount: document.querySelectorAll('.raos-editorial-v2').length,
          h1Bounds,
          h1Count: document.querySelectorAll('h1').length,
          h1LastLineCharacters: h1LineMetrics.lastLineCharacters,
          h1LineCount: h1LineMetrics.lineCount,
          homeClusters: [
            ...document.querySelectorAll('.raos-cluster-nav .raos-cluster'),
          ].map((cluster) => ({
            anchor: cluster.id,
            links: [...cluster.querySelectorAll('ul a[href]')].map((anchor) => {
              const target = new URL(anchor.href);
              return {
                hash: target.hash,
                href: target.href,
                origin: target.origin,
                pathname: target.pathname,
                search: target.search,
              };
            }),
          })),
          contextualLinkCount: document.querySelectorAll(
            'a[data-raos-link-placement="article_body"][data-raos-to-article-id]',
          ).length,
          relatedLinkCount: document.querySelectorAll(
            'a[data-raos-link-placement="related_navigation"][data-raos-to-article-id]',
          ).length,
          invalidCookieButtonBounds: invalidBoundingBoxCount(cookieButtonBounds),
          invalidCookieConsentBounds: invalidBoundingBoxCount(cookieConsentBounds),
          invalidCookieSettingsBounds: invalidBoundingBoxCount(cookieSettingsBounds),
          invalidCtaBounds: invalidBoundingBoxCount(ctaBounds),
          invalidH1Bounds: invalidBoundingBoxCount(h1Bounds),
          lang: document.documentElement.lang,
          mainCount: document.querySelectorAll('main').length,
          measurementConfigDefined:
            typeof window.RAOS_MEASUREMENT_CONFIG_V1 !== 'undefined',
          measurementScriptCount: document.querySelectorAll(
            'script#kurashinoshirube-measurement-v1-js,script[src*="/assets/measurement.js"]',
          ).length,
          measurementSessionKeyCount,
          missingAlt: document.querySelectorAll('img:not([alt])').length,
          unloadedImages: [...document.images].filter(
            (image) => !image.complete || image.naturalWidth === 0,
          ).length,
          purchaseCautionCount: document.querySelectorAll('.purchase-caution').length,
          scrollWidth: document.documentElement.scrollWidth,
          sourcesSectionCount: document.querySelectorAll('.sources-section').length,
          title: document.title,
          unlabeledControls,
        };
      });
      const internalLinks = surface.article
        ? await page.evaluate(() =>
            [...document.querySelectorAll(
              'a[data-raos-link-placement="article_body"],'
                + 'a[data-raos-link-placement="related_navigation"]',
            )].map((anchor) => {
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
            }),
          )
        : [];
      let internalLinkReadbackFailed = false;
      const expectedInternalLinks = surface.article
        ? [
            {
              placement: 'article_body',
              targetArticleId: surface.contextual_article_id,
            },
            ...surface.related_article_ids.map((targetArticleId) => ({
              placement: 'related_navigation',
              targetArticleId,
            })),
          ]
        : [];
      const signature = (link) => `${link.placement}|${link.targetArticleId}`;
      if (
        internalLinks.length !== expectedInternalLinks.length ||
        internalLinks.map(signature).sort().join('\n') !==
          expectedInternalLinks.map(signature).sort().join('\n')
      ) {
        internalLinkReadbackFailed = true;
      }
      for (const link of internalLinks) {
        const expectedPath = expectedPathByArticleId[link.targetArticleId];
        if (
          !expectedPath ||
          link.origin !== origin ||
          link.pathname !== expectedPath ||
          link.search !== '' ||
          link.hash !== '' ||
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
                  link.search !== '' ||
                  link.hash !== '',
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
      }

      let keyboardAudit = {
        ctaReached: !surface.article,
        escapedConsentDialog: true,
        focusVisibleFailures: 0,
        contextualReached: !surface.article,
        relatedReached: !surface.article,
        distinctTargets: 0,
      };
      if (width === 390) {
        await page.evaluate(() => {
          if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
          window.scrollTo(0, 0);
        });
        const focusableCount = await page.evaluate(() =>
          [...document.querySelectorAll(
            'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
          )].filter((element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0;
          }).length,
        );
        const visited = new Set();
        let consentWasReached = false;
        let escapedConsentDialog = false;
        let focusVisibleFailures = 0;
        let ctaReached = false;
        let contextualReached = false;
        let relatedReached = false;
        for (let index = 0; index < Math.min(focusableCount + 2, 500); index += 1) {
          await page.keyboard.press('Tab');
          const focus = await page.evaluate(() => {
            const element = document.activeElement;
            if (!(element instanceof HTMLElement) || element === document.body) return null;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return {
              cta: element.matches('.raos-cta'),
              contextual: element.matches('[data-raos-link-placement="article_body"]'),
              inConsent: element.closest('[data-raos-cookieyes-audit]') !== null,
              related: element.matches('[data-raos-link-placement="related_navigation"]'),
              signature: [element.tagName, element.id, element.className, element.getAttribute('href')].join('|'),
              visible: rect.width > 0 && rect.height > 0 &&
                ((style.outlineStyle !== 'none' && style.outlineWidth !== '0px') ||
                  style.boxShadow !== 'none'),
            };
          });
          if (!focus) continue;
          visited.add(focus.signature);
          ctaReached ||= focus.cta;
          contextualReached ||= focus.contextual;
          relatedReached ||= focus.related;
          if (focus.inConsent) consentWasReached = true;
          if (consentWasReached && !focus.inConsent) escapedConsentDialog = true;
          if (!focus.visible) focusVisibleFailures += 1;
        }
        keyboardAudit = {
          ctaReached,
          escapedConsentDialog: !consentWasReached || escapedConsentDialog,
          focusVisibleFailures,
          contextualReached,
          relatedReached,
          distinctTargets: visited.size,
        };
        await page.evaluate(() => {
          if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
          window.scrollTo(0, 0);
        });
      }
      const articleAuditFailed =
        surface.article &&
        (audit.editorialRootCount !== 1 ||
          audit.decisionListCount === 0 ||
          audit.comparisonSectionCount === 0 ||
          audit.purchaseCautionCount === 0 ||
          audit.sourcesSectionCount === 0 ||
          audit.ctaBounds.length === 0 ||
          audit.invalidCtaBounds !== 0 ||
          audit.contextualLinkCount !== 1 ||
          audit.relatedLinkCount !== surface.related_article_ids.length ||
          audit.cookieConsentBounds.length !== 1 ||
          audit.invalidCookieConsentBounds !== 0 ||
          audit.cookieButtonBounds.length !== 3 ||
          audit.invalidCookieButtonBounds !== 0 ||
          audit.cookieButtonOrder.join('|') !== '設定|拒否|同意' ||
          audit.cookieButtonBounds.some((bounds) => bounds.height < 44) ||
          audit.cookieOverlapsH1 ||
          audit.cookieOverlapsCta !== 0 ||
          audit.h1LastLineCharacters === 1 ||
          (width <= 768 &&
            (audit.comparisonCardsVisible === 0 ||
              audit.comparisonTablesVisible !== 0)) ||
          (width === 1440 &&
            (audit.comparisonCardsVisible !== 0 ||
              audit.comparisonTablesVisible === 0)) ||
          ((width === 360 || width === 390) &&
            (audit.h1LineCount > 6 ||
              audit.cookieConsentBounds[0].height < 160 ||
              audit.cookieConsentBounds[0].height > 230 ||
              audit.cookieButtonBounds.some(
                (bounds) =>
                  Math.abs(bounds.top - audit.cookieButtonBounds[0].top) > 1,
              ))) ||
          (width === 1440 &&
            (audit.h1LineCount > 4 ||
              Math.abs(audit.cookieConsentBounds[0].width - 320) > 1)));
      const keyboardAuditFailed =
        width === 390 &&
        (keyboardAudit.distinctTargets < 3 ||
          keyboardAudit.focusVisibleFailures !== 0 ||
          !keyboardAudit.escapedConsentDialog ||
          (surface.article &&
            (!keyboardAudit.ctaReached ||
              !keyboardAudit.contextualReached ||
              !keyboardAudit.relatedReached)));
      if (
        audit.title.trim() === '' ||
        !audit.lang.toLowerCase().startsWith('ja') ||
        audit.bannerText !== 'LOCAL WORDPRESS PREVIEW — 本番表示ではありません' ||
        audit.h1Count !== 1 ||
        audit.h1Bounds.length !== 1 ||
        audit.invalidH1Bounds !== 0 ||
        audit.mainCount !== 1 ||
        audit.measurementConfigDefined ||
        audit.measurementScriptCount !== 0 ||
        audit.measurementSessionKeyCount !== 0 ||
        audit.cookieSettingsBounds.length !== 1 ||
        audit.invalidCookieSettingsBounds !== 0 ||
        audit.missingAlt !== 0 ||
        audit.unloadedImages !== 0 ||
        audit.unlabeledControls !== 0 ||
        audit.duplicateIds.length !== 0 ||
        audit.brokenAriaReferences !== 0 ||
        audit.scrollWidth > audit.clientWidth ||
        articleAuditFailed ||
        homepageReadbackFailed ||
        internalLinkReadbackFailed ||
        keyboardAuditFailed
      ) {
        throw new Error(`RAOS_WORDPRESS_LOCAL_PREVIEW_AUDIT_FAILED_${surface.name}_${width}`);
      }
      const screenshot = `${artifactDirectory}/local-preview-${surface.name}-${width}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({
        ...audit,
        homepageReadbackFailed,
        internalLinkReadbackFailed,
        keyboardAudit,
        screenshot,
        surface: surface.name,
        width,
      });
    }
  }
  if (runtimeErrors.length !== 0) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_RUNTIME_ERROR');
  }
  if (externalRequests.length !== 0) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_EXTERNAL_REQUEST');
  }
  if (measurementRequests.length !== 0) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_MEASUREMENT_DEFAULT_OFF_FAILED');
  }
  if (results.length !== surfaces.length * widths.length) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_SCREEN_COUNT_INVALID');
  }
  return results;
}
