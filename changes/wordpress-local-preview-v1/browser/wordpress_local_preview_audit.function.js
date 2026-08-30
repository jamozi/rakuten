async (page) => {
  const origin = 'http://127.0.0.1:8888';
  const artifactDirectory = '/home/minami/rakuten/output/playwright/local-preview';
  const surfaces = [
    { name: 'home', path: '/' },
    {
      article: true,
      name: 'carryclassic',
      path: '/local-preview-carry-on-suitcase-comparison/',
    },
    {
      article: true,
      name: 'powerguide',
      path: '/local-preview-portable-power-station-guide/',
    },
    {
      article: true,
      name: 'ankermodels',
      path: '/local-preview-anker-solix-c300-c800-c1000-differences/',
    },
    {
      article: true,
      name: 'smalldishwasher',
      path: '/local-preview-countertop-dishwasher-for-small-households/',
    },
    {
      article: true,
      name: 'compactrobot',
      path: '/local-preview-compact-robot-vacuum-shortlist/',
    },
    {
      article: true,
      name: 'under100',
      path: '/local-preview-carry-on-suitcase-under-100-seats/',
    },
    {
      article: true,
      name: 'under3kg',
      path: '/local-preview-lightweight-carry-on-suitcase-under-3kg/',
    },
    {
      article: true,
      name: 'frontstop',
      path: '/local-preview-front-open-carry-on-suitcase-with-stopper/',
    },
    {
      article: true,
      name: 'roomba',
      path: '/local-preview-roomba-mini-vs-switchbot-k11-pro/',
    },
    {
      article: true,
      name: 'dishwasher',
      path: '/local-preview-solota-vs-rakua-mini-plus/',
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
        const footer = document.querySelector('.raos-footer');
        const footerBottomBounds = boundingBoxes('.raos-footer__bottom');
        const footerGridBounds = boundingBoxes('.raos-footer__grid');
        const footerLinkBounds = boundingBoxes('.raos-footer a');
        const footerGrid = document.querySelector('.raos-footer__grid');
        const footerGridStyle = footerGrid ? getComputedStyle(footerGrid) : null;
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
          footerBackgroundColor: footer ? getComputedStyle(footer).backgroundColor : '',
          footerBottomBounds,
          footerGridColumnCount:
            footerGridStyle && footerGridStyle.gridTemplateColumns !== 'none'
              ? footerGridStyle.gridTemplateColumns.split(/\s+/).filter(Boolean).length
              : 0,
          footerGridDisplay: footerGridStyle
            ? footerGridStyle.display
            : '',
          footerGridBounds,
          footerLinkBounds,
          h1Bounds,
          h1Count: document.querySelectorAll('h1').length,
          h1LastLineCharacters: h1LineMetrics.lastLineCharacters,
          h1LineCount: h1LineMetrics.lineCount,
          invalidCookieButtonBounds: invalidBoundingBoxCount(cookieButtonBounds),
          invalidCookieConsentBounds: invalidBoundingBoxCount(cookieConsentBounds),
          invalidCookieSettingsBounds: invalidBoundingBoxCount(cookieSettingsBounds),
          invalidCtaBounds: invalidBoundingBoxCount(ctaBounds),
          invalidFooterBottomBounds: invalidBoundingBoxCount(footerBottomBounds),
          invalidFooterGridBounds: invalidBoundingBoxCount(footerGridBounds),
          invalidFooterLinkBounds: invalidBoundingBoxCount(footerLinkBounds),
          invalidH1Bounds: invalidBoundingBoxCount(h1Bounds),
          lang: document.documentElement.lang,
          mainCount: document.querySelectorAll('main').length,
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
      const articleAuditFailed =
        surface.article &&
        (audit.editorialRootCount !== 1 ||
          audit.decisionListCount === 0 ||
          audit.comparisonSectionCount === 0 ||
          audit.purchaseCautionCount === 0 ||
          audit.sourcesSectionCount === 0 ||
          audit.ctaBounds.length === 0 ||
          audit.invalidCtaBounds !== 0 ||
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
      if (
        audit.title.trim() === '' ||
        !audit.lang.toLowerCase().startsWith('ja') ||
        audit.bannerText !== 'LOCAL WORDPRESS PREVIEW — 本番表示ではありません' ||
        audit.h1Count !== 1 ||
        audit.h1Bounds.length !== 1 ||
        audit.invalidH1Bounds !== 0 ||
        audit.mainCount !== 1 ||
        audit.cookieSettingsBounds.length !== 1 ||
        audit.invalidCookieSettingsBounds !== 0 ||
        audit.footerBackgroundColor !== 'rgb(23, 36, 63)' ||
        audit.footerBottomBounds.length !== 1 ||
        audit.footerGridBounds.length !== 1 ||
        audit.footerGridDisplay !== 'grid' ||
        audit.invalidFooterBottomBounds !== 0 ||
        audit.invalidFooterGridBounds !== 0 ||
        audit.footerLinkBounds.length === 0 ||
        audit.invalidFooterLinkBounds !== 0 ||
        audit.footerLinkBounds.some((bounds) => bounds.height < 44) ||
        audit.footerGridColumnCount !==
          (width === 1440 ? 3 : width === 768 ? 2 : 1) ||
        [...audit.footerBottomBounds, ...audit.footerGridBounds].some(
          (bounds) => bounds.left < 16 || bounds.right > audit.clientWidth - 16,
        ) ||
        audit.missingAlt !== 0 ||
        audit.unloadedImages !== 0 ||
        audit.unlabeledControls !== 0 ||
        audit.duplicateIds.length !== 0 ||
        audit.brokenAriaReferences !== 0 ||
        audit.scrollWidth > audit.clientWidth ||
        articleAuditFailed
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
  if (results.length !== 44) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_SCREEN_COUNT_INVALID');
  }
  return results;
}
