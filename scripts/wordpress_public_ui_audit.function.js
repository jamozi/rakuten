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
  const comparisonPolicyRows = policyRows.filter(
    (surface) => surface.surface_id === 'policy-comparison-policy',
  );
  const comparisonPolicyPath = comparisonPolicyRows[0]?.production_path;
  const articleIds = new Set(articleRows.map((surface) => surface.article_id));
  const articleById = new Map(articleRows.map((surface) => [surface.article_id, surface]));
  const lifecycleStatusRouteArticleId = 'solota-vs-rakua-mini-plus';
  const lifecycleStatusRouteRows = articleRows.filter(
    (surface) => surface.content_role === 'lifecycle_status_route',
  );
  const roleLabelByRole = new Map([
    ['brand_family_comparison', 'ブランド内比較'],
    ['category_guide', '選び方'],
    ['constraint_shortlist', '条件別比較'],
    ['feature_shortlist', '機能別比較'],
    ['head_to_head_comparison', '2製品比較'],
    ['head_to_head_with_reference', '2製品比較＋参考機種'],
    ['lifecycle_status_route', '以前の比較対象の販売状態確認＋現行比較への案内'],
    ['model_family_comparison', 'ブランド内比較'],
  ]);
  const intentGroupByArticleId = new Map(
    articleRows.map((surface) => [surface.article_id, surface.intent_group_id]),
  );
  const memberships = Array.isArray(rawClusters)
    ? rawClusters.flatMap((cluster) => cluster.article_ids || [])
    : [];
  const clusterById = new Map(
    Array.isArray(rawClusters)
      ? rawClusters.map((cluster) => [cluster.cluster_id, cluster])
      : [],
  );
  if (
    typeof artifactDirectory !== 'string' || !artifactDirectory.startsWith('/') ||
    inventory?.schema !== 'RAOS_WORDPRESS_AUDIT_INVENTORY_V3' ||
    inventory?.version !== '3.0.0' ||
    origin !== 'https://kurashinoshirube.com' ||
    !Array.isArray(rawSurfaces) || rawSurfaces.length !== 14 ||
    homeRows.length !== 1 || articleRows.length !== 10 || policyRows.length !== 3 ||
    comparisonPolicyRows.length !== 1 || !cleanPath(comparisonPolicyPath) ||
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
    lifecycleStatusRouteRows.length !== 1 ||
    lifecycleStatusRouteRows[0]?.article_id !== lifecycleStatusRouteArticleId ||
    articleById.get(lifecycleStatusRouteArticleId)?.content_role !== 'lifecycle_status_route' ||
    articleRows.some(
      (surface) =>
        typeof surface.article_id !== 'string' ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(surface.article_id) ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(surface.intent_group_id || '') ||
        roleLabelByRole.get(surface.content_role) !== surface.content_role_label ||
        typeof surface.primary_query_intent !== 'string' ||
        surface.primary_query_intent.trim() !== surface.primary_query_intent ||
        surface.primary_query_intent.length < 1 || surface.primary_query_intent.length > 180 ||
        articleRows.some((other) =>
          other !== surface &&
          other.intent_group_id === surface.intent_group_id &&
          other.primary_query_intent === surface.primary_query_intent) ||
        typeof surface.comparison_scope !== 'string' ||
        surface.comparison_scope.trim() !== surface.comparison_scope ||
        surface.comparison_scope.length < 1 || surface.comparison_scope.length > 120 ||
        (surface.broader_article_id !== null && (
          !articleIds.has(surface.broader_article_id) ||
          surface.broader_article_id === surface.article_id ||
          articleById.get(surface.broader_article_id)?.intent_group_id !== surface.intent_group_id ||
          !['category_guide', 'constraint_shortlist'].includes(
            articleById.get(surface.broader_article_id)?.content_role,
          )
        )) ||
        !articleIds.has(surface.contextual_article_id) ||
        surface.contextual_article_id === surface.article_id ||
        intentGroupByArticleId.get(surface.contextual_article_id) !== surface.intent_group_id ||
        !/^cluster-[a-z0-9-]+$/.test(surface.cluster_anchor || '') ||
        clusterById.get(surface.cluster_id)?.anchor !== surface.cluster_anchor ||
        !clusterById.get(surface.cluster_id)?.article_ids?.includes(surface.article_id) ||
        !Array.isArray(surface.related_article_ids) ||
        surface.related_article_ids.length > 1 ||
        new Set(surface.related_article_ids).size !== surface.related_article_ids.length ||
        surface.related_article_ids.some(
          (articleId) =>
            articleId === surface.article_id ||
            articleId === surface.contextual_article_id ||
            !articleIds.has(articleId) ||
            intentGroupByArticleId.get(articleId) !== surface.intent_group_id,
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
    if (message.type() === 'error') runtimeErrors.push('console-error');
  });
  page.on('pageerror', (error) => runtimeErrors.push(`page:${error.name}`));

  const results = [];
  for (const surface of surfaces) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const expectedUrl = `${origin}${surface.path}`;
      const response = await page.goto(expectedUrl, { waitUntil: 'networkidle' });
      if (!response || response.status() !== 200 || response.url() !== expectedUrl) {
        throw new Error(`WORDPRESS_PUBLIC_UI_HTTP_FAILED_${surface.surface_id}_${width}`);
      }
      let realScrollEvidence = null;
      if (surface.kind === 'home') {
        realScrollEvidence = await page.evaluate(async () => {
          const afterPaint = () => new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve)));
          const sections = [...document.querySelectorAll('.raos-home-v2 > *')]
            .filter((element) => element instanceof HTMLElement);
          const checkpoints = [];
          for (const section of sections) {
            section.scrollIntoView({ behavior: 'auto', block: 'start' });
            await afterPaint();
            const rect = section.getBoundingClientRect();
            checkpoints.push({
              intersectsViewport: rect.bottom > 0 && rect.top < innerHeight,
              scrollY,
            });
          }
          scrollTo({ behavior: 'auto', left: 0, top: document.documentElement.scrollHeight });
          await afterPaint();
          const maximumScrollY = Math.max(
            0,
            document.documentElement.scrollHeight - innerHeight,
          );
          const reachedBottom = Math.abs(scrollY - maximumScrollY) <= 2;
          const maximumObservedScrollY = Math.max(0, ...checkpoints.map((row) => row.scrollY));
          scrollTo({ behavior: 'auto', left: 0, top: 0 });
          await afterPaint();
          return {
            allSectionsIntersected: checkpoints.every((row) => row.intersectsViewport),
            maximumObservedScrollY,
            reachedBottom,
            returnedToTop: scrollY === 0,
            sectionCount: sections.length,
          };
        });
        if (
          realScrollEvidence.sectionCount < 4 ||
          !realScrollEvidence.allSectionsIntersected ||
          realScrollEvidence.maximumObservedScrollY <= 0 ||
          !realScrollEvidence.reachedBottom ||
          !realScrollEvidence.returnedToTop
        ) {
          throw new Error(`WORDPRESS_PUBLIC_UI_HOME_REAL_SCROLL_FAILED_${width}`);
        }
      }
      if (surface.kind === 'article') {
        await page.locator('.raos-disclosure')
          .scrollIntoViewIfNeeded();
        await page.evaluate(
          () => new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
      }
      const audit = await page.evaluate((comparisonPolicyPath) => {
        const visible = (element) => {
          if (!(element instanceof HTMLElement)) return false;
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' &&
            Number.parseFloat(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
        };
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
            clusterAnchor: anchor.getAttribute('data-raos-cluster-anchor'),
            hash: target.hash,
            href: target.href,
            origin: target.origin,
            pathname: target.pathname,
            placement: anchor.getAttribute('data-raos-link-placement'),
            search: target.search,
            targetArticleId: anchor.getAttribute('data-raos-to-article-id'),
          };
        };
        const visibleFactValues = (label) => [...document.querySelectorAll('dt')]
          .filter((term) => term.textContent?.trim() === label)
          .flatMap((term) => {
            const value = term.nextElementSibling;
            if (!(value instanceof HTMLElement) || value.tagName !== 'DD') return [];
            const style = getComputedStyle(value);
            const rect = value.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0
              ? [value.textContent?.trim() || ''] : [];
          });
        const productProfiles = [...document.querySelectorAll('.product-profile')];
        const productIds = productProfiles.map((profile) =>
          (profile.getAttribute('data-raos-product-id') || '').trim());
        const disclosure = document.querySelector('.raos-disclosure');
        const disclosureRect = disclosure instanceof HTMLElement
          ? disclosure.getBoundingClientRect() : null;
        let disclosureEffectiveOpacity = 1;
        let disclosureAncestorsVisible = disclosure instanceof HTMLElement;
        for (let element = disclosure; element instanceof HTMLElement; element = element.parentElement) {
          const style = getComputedStyle(element);
          const opacity = Number.parseFloat(style.opacity);
          disclosureEffectiveOpacity *= Number.isFinite(opacity) ? opacity : 0;
          if (
            style.display === 'none' || style.visibility === 'hidden' ||
            style.visibility === 'collapse' || style.clipPath !== 'none' ||
            (style.clip !== 'auto' && style.clip !== 'rect(auto, auto, auto, auto)')
          ) disclosureAncestorsVisible = false;
        }
        const disclosureSampleX = disclosureRect === null ? -1 :
          Math.min(innerWidth - 1, Math.max(0, disclosureRect.left + disclosureRect.width / 2));
        const disclosureSampleY = disclosureRect === null ? -1 :
          Math.min(innerHeight - 1, Math.max(0, disclosureRect.top + disclosureRect.height / 2));
        const disclosureTopmost = disclosureRect === null ? null :
          document.elementFromPoint(disclosureSampleX, disclosureSampleY);
        const disclosureDetails = disclosure?.querySelectorAll('details') || [];
        const disclosureSummary = disclosure?.querySelector('details > summary') || null;
        const disclosureText = disclosure?.textContent || '';
        const disclosurePolicyLinks = disclosure
          ? [...disclosure.querySelectorAll('a[href]')].filter((anchor) => {
              try {
                const target = new URL(anchor.getAttribute('href') || '', location.href);
                return target.origin === location.origin &&
                  target.pathname === comparisonPolicyPath && !target.search && !target.hash;
              } catch (error) {
                return false;
              }
            })
          : [];
        const firstCta = document.querySelector('.raos-cta[data-raos-placement]');
        const firstCtaRect = firstCta instanceof HTMLElement
          ? firstCta.getBoundingClientRect() : null;
        const anchorSecurity = {
          affiliateRelInvalid: 0,
          blankRelInvalid: 0,
          malformedHrefCount: 0,
          unsafeSchemeCount: 0,
        };
        for (const anchor of document.querySelectorAll('a[href]')) {
          const rawHref = (anchor.getAttribute('href') || '').trim();
          if (!rawHref) {
            anchorSecurity.malformedHrefCount += 1;
            continue;
          }
          let target;
          try {
            target = new URL(rawHref, location.href);
          } catch (error) {
            anchorSecurity.malformedHrefCount += 1;
            continue;
          }
          const isHttps = target.protocol === 'https:';
          const isExpectedMail = target.href === 'mailto:contact@kurashinoshirube.com';
          if (!isHttps && !isExpectedMail) anchorSecurity.unsafeSchemeCount += 1;
          const rel = new Set((anchor.getAttribute('rel') || '').toLowerCase()
            .split(/\s+/).filter(Boolean));
          if (
            target.protocol === 'https:' && target.hostname === 'hb.afl.rakuten.co.jp' &&
            (!rel.has('sponsored') || !rel.has('nofollow'))
          ) anchorSecurity.affiliateRelInvalid += 1;
          if (
            (anchor.getAttribute('target') || '').toLowerCase() === '_blank' &&
            (!rel.has('noopener') || !rel.has('noreferrer'))
          ) anchorSecurity.blankRelInvalid += 1;
        }
        const forbiddenTypes = new Set([
          'AggregateRating', 'FAQPage', 'Offer', 'Product', 'Review',
        ]);
        const containsForbiddenType = (root) => {
          const stack = [root];
          const seen = new Set();
          while (stack.length > 0) {
            const value = stack.pop();
            if (value === null || typeof value !== 'object' || seen.has(value)) continue;
            seen.add(value);
            if (Array.isArray(value)) {
              stack.push(...value);
              continue;
            }
            const types = Array.isArray(value['@type']) ? value['@type'] : [value['@type']];
            if (types.some((type) =>
              typeof type === 'string' &&
              forbiddenTypes.has(type.replace(/^.*[/#:]/, '')))) return true;
            stack.push(...Object.values(value));
          }
          return false;
        };
        let jsonLdParseFailures = 0;
        let forbiddenJsonLdTypeCount = 0;
        for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
          try {
            if (containsForbiddenType(JSON.parse(script.textContent || ''))) {
              forbiddenJsonLdTypeCount += 1;
            }
          } catch (error) {
            jsonLdParseFailures += 1;
          }
        }
        const parseTimeMs = (value) => {
          const trimmed = value.trim();
          const amount = Number.parseFloat(trimmed);
          if (!Number.isFinite(amount)) return Number.POSITIVE_INFINITY;
          return trimmed.endsWith('ms') ? amount : trimmed.endsWith('s') ? amount * 1000
            : Number.POSITIVE_INFINITY;
        };
        let animatedElementCount = 0;
        let smoothScrollElementCount = 0;
        for (const element of document.querySelectorAll('*')) {
          const style = getComputedStyle(element);
          const animationMs = style.animationDuration.split(',')
            .map(parseTimeMs).reduce((maximum, value) => Math.max(maximum, value), 0);
          const transitionMs = style.transitionDuration.split(',')
            .map(parseTimeMs).reduce((maximum, value) => Math.max(maximum, value), 0);
          if (animationMs > 0.011 || transitionMs > 0.011) animatedElementCount += 1;
          if (style.scrollBehavior === 'smooth') smoothScrollElementCount += 1;
        }
        const comparisonFocusability = [
          ...document.querySelectorAll('.comparison-table-wrap[role="region"]'),
        ].map((region) => {
          const style = getComputedStyle(region);
          const labelledByName = (region.getAttribute('aria-labelledby') || '')
            .split(/\s+/).filter(Boolean)
            .map((id) => document.getElementById(id)?.textContent?.trim() || '')
            .filter(Boolean).join(' ');
          const accessibleName =
            region.getAttribute('aria-label')?.trim() || labelledByName;
          const shouldBeFocusable = visible(region) &&
            region.scrollWidth > region.clientWidth + 1 &&
            ['auto', 'scroll'].includes(style.overflowX);
          return {
            accessibleName,
            availableState: region.dataset.raosHorizontalScroll || null,
            shouldBeFocusable,
            tabindex: region.getAttribute('tabindex'),
          };
        });
        return {
          anchorSecurity,
          articleFacts: {
            contentRoleLabels: visibleFactValues('記事分類'),
            primaryQueryIntents: visibleFactValues('この記事で答えること'),
          },
          brokenAriaReferences,
          clientWidth: document.documentElement.clientWidth,
          comparisonFocusability,
          ctas: document.querySelectorAll('.raos-cta[data-raos-placement]').length,
          duplicateIds,
          disclosure: {
            ariaLabel: disclosure?.getAttribute('aria-label') || '',
            beforeFirstCtaDom: disclosure instanceof HTMLElement && firstCta instanceof HTMLElement &&
              Boolean(disclosure.compareDocumentPosition(firstCta) & Node.DOCUMENT_POSITION_FOLLOWING),
            beforeFirstCtaVisual: disclosureRect !== null && firstCtaRect !== null &&
              disclosureRect.top + scrollY < firstCtaRect.top + scrollY,
            count: document.querySelectorAll('.raos-disclosure').length,
            detailsCount: disclosureDetails.length,
            detailsValid: disclosureDetails.length === 1 &&
              disclosureDetails[0].querySelectorAll(':scope > summary').length === 1 &&
              disclosureDetails[0].firstElementChild === disclosureSummary &&
              Boolean(disclosureSummary?.textContent?.trim()),
            inViewport: disclosureRect !== null && disclosureRect.top >= 0 &&
              disclosureRect.left >= 0 && disclosureRect.bottom <= innerHeight &&
              disclosureRect.right <= innerWidth,
            opacityVisible: disclosureAncestorsVisible &&
              disclosureEffectiveOpacity > 0 && visible(disclosure),
            nonaffiliatePhraseCount: [
              'この記事には購入リンクがありません',
              '以前の比較対象の販売状態を確認する案内記事',
              '商品カードとアフィリエイトリンクは掲載していません',
            ].filter((phrase) => disclosureText.includes(phrase)).length,
            policyLinkCount: disclosurePolicyLinks.length,
            standardPhraseCount: [
              '広告を含みます',
              '選定・掲載順には使いません',
              '実機を使用したレビューではありません',
            ].filter((phrase) => disclosureText.includes(phrase)).length,
            strongText: disclosure?.querySelector(':scope > strong')?.textContent?.trim() || '',
            summaryVisible: visible(disclosureSummary),
            unobscured: disclosure instanceof HTMLElement && disclosureTopmost !== null &&
              (disclosureTopmost === disclosure || disclosure.contains(disclosureTopmost)),
          },
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
              + 'a[data-raos-link-placement="related_navigation"],'
              + 'a[data-raos-link-placement="cluster_home"]',
          )].map(linkRecord),
          lang: document.documentElement.lang,
          mainCount: document.querySelectorAll('main').length,
          missingAlt: document.querySelectorAll('img:not([alt])').length,
          productIds,
          productProfileCount: productProfiles.length,
          jsonLdParseFailures,
          forbiddenJsonLdTypeCount,
          reducedMotion: {
            animatedElementCount,
            htmlScrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
            mediaMatches: matchMedia('(prefers-reduced-motion: reduce)').matches,
            smoothScrollElementCount,
          },
          scrollWidth: document.documentElement.scrollWidth,
          title: document.title,
          unlabeledControls,
        };
      }, comparisonPolicyPath);
      const comparisonFocusabilityFailure = audit.comparisonFocusability.some((row) =>
        !row.accessibleName || (row.shouldBeFocusable
          ? row.tabindex !== '0' || row.availableState !== 'available'
          : row.tabindex !== null || row.availableState !== null));

      let disclosureKeyboardFailure = null;
      if (
        surface.kind === 'article' && width === 390 &&
        surface.article_id !== lifecycleStatusRouteArticleId
      ) {
        disclosureKeyboardFailure = await (async () => {
          const details = page.locator(
            '.raos-disclosure[aria-label="広告表示"] details',
          );
          const summary = details.locator(':scope > summary');
          if (await details.count() !== 1 || await summary.count() !== 1) {
            return 'DISCLOSURE_CONTROL_MISSING';
          }
          await details.evaluate((element) => { element.open = false; });
          await summary.focus();
          await page.keyboard.press('Enter');
          if (!await details.evaluate((element) => element.open)) return 'ENTER_DID_NOT_OPEN';
          await page.keyboard.press('Enter');
          if (await details.evaluate((element) => element.open)) return 'ENTER_DID_NOT_CLOSE';
          await page.keyboard.press('Space');
          if (!await details.evaluate((element) => element.open)) return 'SPACE_DID_NOT_OPEN';
          await page.keyboard.press('Space');
          if (await details.evaluate((element) => element.open)) return 'SPACE_DID_NOT_CLOSE';
          return await summary.evaluate((element) =>
            document.activeElement === element ? null : 'SUMMARY_FOCUS_LOST');
        })();
      }

      let focusFlowFailure = null;
      if (width === 390 || width === 1440) {
        focusFlowFailure = await (async () => {
          await page.evaluate(() => {
            if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
            scrollTo(0, 0);
          });
          const captureFocusedControl = () => page.evaluate(() => {
            const active = document.activeElement;
            if (!(active instanceof HTMLElement) || active === document.body) return null;
            const style = getComputedStyle(active);
            const rect = active.getBoundingClientRect();
            const sampleX = Math.min(innerWidth - 1, Math.max(0, rect.left + rect.width / 2));
            const sampleY = Math.min(innerHeight - 1, Math.max(0, rect.top + rect.height / 2));
            const topmost = document.elementFromPoint(sampleX, sampleY);
            const focusables = [...document.querySelectorAll(
              'a[href],button,input:not([type="hidden"]),select,textarea,summary,[tabindex]',
            )].filter((element) =>
              element instanceof HTMLElement && element.tabIndex >= 0 &&
              !element.hasAttribute('disabled'));
            const indicatorVisible =
              (style.outlineStyle !== 'none' && Number.parseFloat(style.outlineWidth) > 0) ||
              style.boxShadow !== 'none';
            return {
              focusVisible: active.matches(':focus-visible') && indicatorVisible,
              index: focusables.indexOf(active),
              unobscured: rect.width > 0 && rect.height > 0 && rect.bottom > 0 &&
                rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth &&
                topmost !== null &&
                (topmost === active || active.contains(topmost) || topmost.contains(active)),
            };
          });
          const forward = [];
          for (let index = 0; index < 3; index += 1) {
            await page.keyboard.press('Tab');
            forward.push(await captureFocusedControl());
          }
          const backward = [];
          for (let index = 0; index < 2; index += 1) {
            await page.keyboard.press('Shift+Tab');
            backward.push(await captureFocusedControl());
          }
          const states = [...forward, ...backward];
          if (states.some((state) =>
            state === null || state.index < 0 || !state.focusVisible || !state.unobscured)) {
            return 'FOCUS_STATE_INVALID';
          }
          if (
            new Set(forward.map((state) => state.index)).size !== forward.length ||
            backward[0].index !== forward[1].index || backward[1].index !== forward[0].index
          ) return 'TAB_ORDER_NOT_REVERSIBLE';
          return null;
        })();
      }

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
          {
            clusterAnchor: surface.cluster_anchor,
            placement: 'cluster_home',
            targetArticleId: null,
          },
        ];
        const signature = (link) =>
          `${link.placement}|${link.targetArticleId}|${link.clusterAnchor || ''}`;
        if (
          audit.internalLinks.length !== expectedInternalLinks.length ||
          new Set(audit.internalLinks.map((link) => link.href)).size !==
            audit.internalLinks.length ||
          audit.internalLinks.map(signature).sort().join('\n') !==
            expectedInternalLinks.map(signature).sort().join('\n')
        ) {
          internalLinkReadbackFailed = true;
        }
        for (const link of audit.internalLinks) {
          if (link.placement === 'cluster_home') {
            if (
              link.origin !== origin || link.pathname !== '/' || link.search !== '' ||
              link.hash !== `#${surface.cluster_anchor}` ||
              link.clusterAnchor !== surface.cluster_anchor ||
              link.targetArticleId !== null
            ) {
              internalLinkReadbackFailed = true;
            }
            continue;
          }
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

      const isLifecycleStatusRoute = surface.kind === 'article' &&
        surface.article_id === lifecycleStatusRouteArticleId;
      const requiresAffiliateCta = surface.kind === 'article' && !isLifecycleStatusRoute;
      const zeroProducts = audit.productIds.length === 0;
      const zeroCtas = audit.ctas === 0;
      const lifecycleProductCtaInvariantFailure = surface.kind === 'article' && (
        (surface.content_role === 'lifecycle_status_route') !== isLifecycleStatusRoute ||
        zeroProducts !== isLifecycleStatusRoute ||
        zeroCtas !== isLifecycleStatusRoute ||
        audit.productProfileCount !== audit.productIds.length ||
        audit.productIds.some((productId) => productId === '') ||
        new Set(audit.productIds).size !== audit.productIds.length
      );
      const disclosureSemanticsFailure = surface.kind === 'article' && (
        audit.disclosure.count !== 1 ||
        !audit.disclosure.opacityVisible || !audit.disclosure.inViewport ||
        !audit.disclosure.unobscured || audit.disclosure.policyLinkCount !== 1 ||
        (isLifecycleStatusRoute
          ? audit.disclosure.ariaLabel !== '収益化の対象外' ||
            audit.disclosure.strongText !== '購入リンクなし' ||
            audit.disclosure.detailsCount !== 0 || audit.disclosure.detailsValid ||
            audit.disclosure.summaryVisible ||
            audit.disclosure.standardPhraseCount !== 0 ||
            audit.disclosure.nonaffiliatePhraseCount !== 3
          : audit.disclosure.ariaLabel !== '広告表示' ||
            audit.disclosure.strongText !== '広告・アフィリエイト開示' ||
            audit.disclosure.detailsCount !== 1 || !audit.disclosure.detailsValid ||
            !audit.disclosure.summaryVisible ||
            audit.disclosure.standardPhraseCount !== 3 ||
            audit.disclosure.nonaffiliatePhraseCount !== 0)
      );
      const articleFailed = surface.kind === 'article' && (
        audit.editorialRoots !== 1 ||
        (requiresAffiliateCta
          ? audit.ctas < 1 || !audit.disclosure.beforeFirstCtaDom ||
            !audit.disclosure.beforeFirstCtaVisual
          : audit.ctas !== 0 || audit.disclosure.beforeFirstCtaDom ||
            audit.disclosure.beforeFirstCtaVisual) ||
        disclosureSemanticsFailure ||
        audit.articleFacts.contentRoleLabels.length !== 1 ||
        audit.articleFacts.contentRoleLabels[0] !== surface.content_role_label ||
        audit.articleFacts.primaryQueryIntents.length !== 1 ||
        audit.articleFacts.primaryQueryIntents[0] !== surface.primary_query_intent ||
        audit.internalLinks.filter((link) => link.placement === 'article_body').length !== 1 ||
        audit.internalLinks.filter(
          (link) => link.placement === 'related_navigation',
        ).length !== surface.related_article_ids.length ||
        audit.internalLinks.filter((link) => link.placement === 'cluster_home').length !== 1
      ) || surface.kind !== 'article' && (
        audit.disclosure.count !== 0 ||
        audit.articleFacts.contentRoleLabels.length !== 0 ||
        audit.articleFacts.primaryQueryIntents.length !== 0
      );
      if (
        audit.title.trim() === '' ||
        !audit.lang.toLowerCase().startsWith('ja') ||
        audit.h1Count !== 1 ||
        audit.mainCount !== 1 ||
        audit.missingAlt !== 0 ||
        audit.unlabeledControls !== 0 ||
        comparisonFocusabilityFailure ||
        audit.duplicateIds.length !== 0 ||
        audit.brokenAriaReferences !== 0 ||
        audit.scrollWidth > audit.clientWidth ||
        Object.values(audit.anchorSecurity).some((count) => count !== 0) ||
        audit.jsonLdParseFailures !== 0 || audit.forbiddenJsonLdTypeCount !== 0 ||
        !audit.reducedMotion.mediaMatches ||
        audit.reducedMotion.htmlScrollBehavior !== 'auto' ||
        audit.reducedMotion.animatedElementCount !== 0 ||
        audit.reducedMotion.smoothScrollElementCount !== 0 ||
        articleFailed ||
        lifecycleProductCtaInvariantFailure ||
        disclosureKeyboardFailure || focusFlowFailure ||
        internalLinkReadbackFailed ||
        homepageReadbackFailed
      ) {
        throw new Error(`WORDPRESS_PUBLIC_UI_AUDIT_FAILED_${surface.surface_id}_${width}`);
      }
      let captureOnlyEvidenceMode = null;
      if (surface.kind === 'home') {
        captureOnlyEvidenceMode = await page.evaluate(() => {
          document.documentElement.dataset.raosAuditCapture =
            'expanded-after-real-scroll';
          const style = document.createElement('style');
          style.id = 'raos-audit-capture-only-content-visibility';
          style.dataset.raosAuditCaptureOnly = 'true';
          style.textContent = [
            '/* Capture-only: interaction and paint were already verified by real scrolling. */',
            'html[data-raos-audit-capture="expanded-after-real-scroll"]',
            ' .raos-home-v2 > :not(.raos-home-hero) {',
            ' content-visibility: visible !important; }',
          ].join('');
          document.head.append(style);
          return style.sheet !== null &&
            document.querySelectorAll('.raos-home-v2 > :not(.raos-home-hero)').length > 0
            ? 'CAPTURE_ONLY_CONTENT_VISIBILITY_EXPANDED_AFTER_REAL_SCROLL'
            : null;
        });
        await page.evaluate(
          () => new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        if (captureOnlyEvidenceMode === null) {
          throw new Error(`WORDPRESS_PUBLIC_UI_HOME_CAPTURE_MODE_FAILED_${width}`);
        }
      }
      const screenshot = `${artifactDirectory}/wordpress-${surface.surface_id}-${width}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({
        ...audit,
        captureOnlyEvidenceMode,
        homepageReadbackFailed,
        internalLinkReadbackFailed,
        realScrollEvidence,
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
