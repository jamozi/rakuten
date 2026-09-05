(() => {
  const validateSeoHead = ({
    audit,
    expectedOpenGraphImageUrl,
    expectedUrl,
    forbiddenJsonLdTypes,
    localNoindexHeaderValid,
    openGraphImageResponseValid,
    requiredJsonLdTypes,
  }) => {
    const missingJsonLdTypes = requiredJsonLdTypes.filter(
      (type) => !audit.jsonLdTypes.includes(type),
    );
    const presentForbiddenJsonLdTypes = forbiddenJsonLdTypes.filter((type) =>
      audit.jsonLdTypes.includes(type),
    );
    const invalidJsonLdTypes = audit.jsonLdTypes.filter(
      (type) => typeof type !== 'string' || !/^[A-Za-z][A-Za-z0-9]*$/.test(type),
    );
    const openGraphFieldsValid = Object.values(audit.openGraph).every(
      (values) => values.length === 1 && values[0] !== '',
    );
    const openGraphImageValid =
      audit.openGraph.image.length === 1 &&
      audit.openGraph.image[0] === expectedOpenGraphImageUrl &&
      openGraphImageResponseValid;
    const metaRobotsDirectives = audit.metaRobots.flatMap((value) =>
      value
        .split(',')
        .map((directive) => directive.trim().toLowerCase())
        .filter(Boolean),
    );
    const localNoindexMetaValid =
      audit.metaRobots.length === 1 &&
      metaRobotsDirectives.includes('noindex') &&
      metaRobotsDirectives.includes('nofollow') &&
      !metaRobotsDirectives.includes('index') &&
      !metaRobotsDirectives.includes('follow');
    const failed =
      audit.currentUrl !== expectedUrl ||
      audit.canonicalLinks.length !== 1 ||
      audit.canonicalLinks[0]?.rawHref !== audit.currentUrl ||
      audit.canonicalLinks[0]?.resolvedHref !== audit.currentUrl ||
      audit.titleCount !== 1 ||
      audit.title.trim() === '' ||
      audit.metaDescriptions.length !== 1 ||
      audit.metaDescriptions[0] === '' ||
      !openGraphFieldsValid ||
      audit.openGraph.title[0] !== audit.title ||
      audit.openGraph.description[0] !== audit.metaDescriptions[0] ||
      audit.openGraph.url[0] !== audit.currentUrl ||
      !openGraphImageValid ||
      audit.jsonLdScriptCount !== 1 ||
      audit.jsonLdParseFailed ||
      invalidJsonLdTypes.length !== 0 ||
      missingJsonLdTypes.length !== 0 ||
      presentForbiddenJsonLdTypes.length !== 0 ||
      !localNoindexHeaderValid ||
      !localNoindexMetaValid;
    return {
      failed,
      invalidJsonLdTypes,
      localNoindexMetaValid,
      metaRobotsDirectives,
      missingJsonLdTypes,
      openGraphFieldsValid,
      openGraphImageValid,
      presentForbiddenJsonLdTypes,
    };
  };

  const exactSet = (actual, expected) => Array.isArray(actual) && Array.isArray(expected) &&
    actual.length === expected.length && new Set(actual).size === actual.length &&
    [...actual].sort().every((value, index) => value === [...expected].sort()[index]);
  const exactKeys = (value, keys) => value !== null && typeof value === 'object' &&
    !Array.isArray(value) && exactSet(Object.keys(value), keys);
  const exactMultiset = (actual, expected) => Array.isArray(actual) && Array.isArray(expected) &&
    actual.length === expected.length && [...actual].sort().every(
      (value, index) => value === [...expected].sort()[index]);
  const ctaTuple = (row) => JSON.stringify([row.cta_id, row.product_id, row.placement]);
  const validateIncrementalScope = ({ publicationProfile, linkMode, incrementalScope, articleIds }) => {
    if (publicationProfile === 'legacy-full') {
      if (incrementalScope !== null || !['standard-api', 'measured-admin'].includes(linkMode)) {
        throw new Error('RAOS_WORDPRESS_INCREMENTAL_SCOPE_INVALID');
      }
      return null;
    }
    const scope = incrementalScope;
    const identifier = (value) => typeof value === 'string' && value.length > 0 &&
      value.length <= 180 && /^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$/.test(value);
    if (publicationProfile !== 'verified-incremental' || linkMode !== 'standard-api' ||
      !exactKeys(scope, ['schema', 'publication_profile', 'link_mode', 'selected_article_ids',
        'articles', 'preparation_binding_sha256']) ||
      scope.schema !== 'RAOS_WORDPRESS_INCREMENTAL_BROWSER_SCOPE_V1' ||
      scope.publication_profile !== publicationProfile || scope.link_mode !== linkMode ||
      !/^[a-f0-9]{64}$/.test(scope.preparation_binding_sha256 || '') ||
      scope.preparation_binding_sha256 === '0'.repeat(64) ||
      !Array.isArray(scope.selected_article_ids) || scope.selected_article_ids.length === 0 ||
      !exactSet(scope.selected_article_ids, [...new Set(scope.selected_article_ids)]) ||
      scope.selected_article_ids.some((id) => !articleIds.includes(id)) ||
      !Array.isArray(scope.articles) ||
      !exactSet(scope.articles.map((row) => row?.article_id), articleIds)) {
      throw new Error('RAOS_WORDPRESS_INCREMENTAL_SCOPE_INVALID');
    }
    for (const row of scope.articles) {
      const selected = scope.selected_article_ids.includes(row.article_id);
      if (!exactKeys(row, ['article_id', 'editorial_product_ids', 'expected_cta_ids',
        'expected_ctas', 'expected_image_product_ids', 'expected_article_facts',
        'expected_disclosure_policy_link_count', 'display_projection']) ||
        !exactKeys(row.display_projection, ['state', 'contract_sha256', 'input_sha256',
          'output_sha256', 'profile', 'removed_decoration_count', 'removed_neutral_media_count']) ||
        ['contract_sha256', 'input_sha256', 'output_sha256'].some((key) =>
          !/^[a-f0-9]{64}$/.test(row.display_projection[key] || '')) ||
        (row.display_projection.state === 'NOT_APPLICABLE'
          ? row.display_projection.profile !== null ||
            row.display_projection.input_sha256 !== row.display_projection.output_sha256 ||
            row.display_projection.removed_decoration_count !== 0 ||
            row.display_projection.removed_neutral_media_count !== 0
          : row.display_projection.state !== 'APPLIED' ||
            !['production', 'local-fixture', 'local-stored'].includes(row.display_projection.profile) ||
            row.display_projection.input_sha256 === row.display_projection.output_sha256 ||
            row.display_projection.removed_decoration_count !== 8 ||
            row.display_projection.removed_neutral_media_count !== ({
              'st1704-portable-power-station-guide': 2,
              'st1704-anker-solix-c300-c800-c1000-differences': 4,
            })[row.article_id]) ||
        !exactKeys(row.expected_article_facts, ['content_role_labels', 'primary_query_intents']) ||
        Object.values(row.expected_article_facts).some((values) =>
          !Array.isArray(values) || values.length > 8 || (selected && values.length !== 1) ||
          values.some((value) => typeof value !== 'string' || !value.trim() || value.length > 2000)) ||
        !Number.isInteger(row.expected_disclosure_policy_link_count) ||
        row.expected_disclosure_policy_link_count < 0 || row.expected_disclosure_policy_link_count > 20 ||
        (selected && row.expected_disclosure_policy_link_count !== 1) ||
        !Array.isArray(row.editorial_product_ids) ||
        !Array.isArray(row.expected_cta_ids) || !Array.isArray(row.expected_ctas) ||
        !Array.isArray(row.expected_image_product_ids) ||
        [row.editorial_product_ids, row.expected_cta_ids,
          ...(selected ? [row.expected_image_product_ids] : [])]
          .some((values) => values.some((value) => !identifier(value)) ||
            !exactSet(values, [...new Set(values)])) ||
        row.expected_image_product_ids.some((id) => !identifier(id)) ||
        row.expected_image_product_ids.some((id) => !row.editorial_product_ids.includes(id)) ||
        row.expected_ctas.some((cta) =>
          !exactKeys(cta, ['cta_id', 'product_id', 'placement']) ||
          !(identifier(cta.cta_id) || (!selected && cta.cta_id === null)) ||
          !row.editorial_product_ids.includes(cta.product_id) ||
          !['product_card', 'final_summary'].includes(cta.placement)) ||
        !exactSet(row.expected_ctas.map(ctaTuple), [...new Set(row.expected_ctas.map(ctaTuple))]) ||
        !exactSet(row.expected_cta_ids, row.expected_ctas.map((cta) => cta.cta_id)
          .filter((id) => id !== null))) {
        throw new Error('RAOS_WORDPRESS_INCREMENTAL_SCOPE_INVALID');
      }
    }
    return scope;
  };

  const validateIncrementalArticle = ({ scope, articleId, audit }) => {
    if (scope === null) return { failed: false, selected: false, commerceStatus: 'LEGACY_PROFILE' };
    const expected = scope.articles.find((row) => row.article_id === articleId);
    if (!expected) return { failed: true, selected: false, commerceStatus: 'SCOPE_MISSING' };
    const selected = scope.selected_article_ids.includes(articleId);
    const ctas = audit.commerceCtas;
    const images = audit.commerceImages;
    const invalid = !exactSet(audit.productIds, expected.editorial_product_ids) ||
      !exactSet(ctas.map(ctaTuple), expected.expected_ctas.map(ctaTuple)) ||
      !exactMultiset(images.map((row) => row.product_id), expected.expected_image_product_ids) ||
      !exactMultiset(audit.articleFacts?.contentRoleLabels,
        expected.expected_article_facts.content_role_labels) ||
      !exactMultiset(audit.articleFacts?.primaryQueryIntents,
        expected.expected_article_facts.primary_query_intents) ||
      audit.disclosure?.policyLinkCount !== expected.expected_disclosure_policy_link_count;
    const unverified = selected && (
      audit.commercePlaceholderCount !== 0 ||
      ctas.some((row) => row.article_id !== articleId || !row.affiliate_host_valid ||
        row.has_measured_identifier || !exactSet(row.rel_tokens, ['sponsored', 'nofollow'])) ||
      images.some((row) => row.state !== 'verified' || !row.alt_valid ||
        !row.dimensions_valid || !row.lazy)
    );
    return {
      failed: invalid || unverified,
      selected,
      commerceStatus: !selected ? 'UNCHANGED_NOT_REVERIFIED' :
        expected.expected_ctas.length === 0 ? 'NOT_INCLUDED' : 'EXPECTED_VERIFIED_SET_PRESENT',
    };
  };

  // Native lazy images in the inactive legacy table/card view are not requested.
  // Observe their actual DOM state; do not change loading, visibility, or page content.
  const inspectImageLoading = () => [...document.images].map((image) => {
    const rect = image.getBoundingClientRect();
    const view = image.closest('.raos-comparison__table-view, .raos-comparison__cards');
    const cardWrapper = view?.parentElement;
    const comparison = view?.matches('.raos-comparison__cards') &&
      cardWrapper?.matches('.comparison-cards')
      ? cardWrapper.parentElement : view?.parentElement;
    const table = comparison?.querySelector(':scope > .raos-comparison__table-view');
    const cards = comparison?.querySelector(
      ':scope > .comparison-cards > .raos-comparison__cards',
    );
    const counterpart = view === table ? cards : view === cards ? table : null;
    let hiddenAncestor = false;
    for (let ancestor = image.parentElement; ancestor; ancestor = ancestor.parentElement) {
      if (getComputedStyle(ancestor).display === 'none') hiddenAncestor = true;
    }
    return {
      complete: image.complete,
      naturalWidth: image.naturalWidth,
      loading: image.loading,
      legacyResponsiveImage: image.matches('img.raos-comparison__product-image') &&
        comparison?.matches('.raos-comparison') === true &&
        view !== null && counterpart != null && getComputedStyle(view).display === 'none' &&
        counterpart.checkVisibility() === true &&
        counterpart.getBoundingClientRect().width > 0 &&
        counterpart.getBoundingClientRect().height > 0,
      hasProductImageId: image.hasAttribute('data-raos-product-image-id'),
      verifiedProductImage: image.closest(
        '.product-profile, .raos-product-card, [data-raos-product-image-id],'
        + '[data-raos-product-image-state="verified"]',
      ) !== null,
      hiddenAncestor,
      zeroRect: rect.width === 0 && rect.height === 0,
      invisible: image.checkVisibility() === false,
      source: image.currentSrc || image.src,
    };
  });
  const classifyImageLoading = ({ publicationProfile, commerceStatus, images }) => {
    let unloadedImages = 0;
    const hiddenLegacyLazySources = [];
    for (const image of images) {
      const deferred = publicationProfile === 'verified-incremental' &&
        commerceStatus === 'UNCHANGED_NOT_REVERIFIED' &&
        image.legacyResponsiveImage === true && image.hasProductImageId === false &&
        image.verifiedProductImage === false && image.hiddenAncestor === true &&
        image.zeroRect === true && image.invisible === true &&
        image.loading === 'lazy' && image.complete === false && image.naturalWidth === 0;
      if (deferred) hiddenLegacyLazySources.push(image.source);
      else if (!image.complete || image.naturalWidth === 0) unloadedImages += 1;
    }
    return { unloadedImages, hiddenLegacyLazySources };
  };
  const inspectHiddenLegacyImageResources = async ({ page, origin, sources }) => {
    let failures = 0;
    for (const source of new Set(sources)) {
      let resource = null;
      try {
        // Never turn a DOM URL into an arbitrary or external HTTP request.
        const target = new URL(source);
        if (target.origin !== origin || target.username || target.password || target.search ||
          target.hash || !/^\/wp-content\/themes\/[A-Za-z0-9_-]+\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+\.(?:webp|png|jpe?g|gif|svg)$/.test(target.pathname)) {
          failures += 1;
          continue;
        }
        resource = await page.request.get(source, { maxRedirects: 0, timeout: 5000 });
        const type = (resource.headers()['content-type'] || '').split(';', 1)[0].trim();
        if (resource.status() !== 200 || resource.url() !== source ||
          !/^image\/(?:webp|png|jpeg|gif|svg\+xml)$/.test(type)) {
          failures += 1;
          continue;
        }
        const bytes = (await resource.body()).length;
        if (bytes === 0 || bytes > 2 * 1024 * 1024) failures += 1;
      } catch (error) {
        failures += 1;
      } finally {
        if (resource !== null) await resource.dispose();
      }
    }
    return failures;
  };

  const factory = ({ artifactDirectory, axeSource, inventory, origin,
    publicationProfile = 'legacy-full', linkMode = 'measured-admin', incrementalScope = null,
  }) => async (page) => {
  const publicPath = (value) =>
    typeof value === 'string' && /^\/(?:[a-z0-9]+(?:-[a-z0-9]+)*\/)?$/.test(value);
  const localPath = (value, kind) => {
    if (kind === 'search') {
      return typeof value === 'string' &&
        /^\/\?s=(?:[A-Za-z0-9.-]|%[0-9A-F]{2})*(?:&paged=[2-9][0-9]*)?$/.test(value);
    }
    return typeof value === 'string' &&
      /^\/(?:[a-z0-9]+(?:-[a-z0-9]+)*\/)*(?:[0-9]{4}\/[0-9]{2}\/)?$/.test(value);
  };
  const rawSurfaces = inventory?.surfaces;
  const publicSurfaces = rawSurfaces;
  const localSurfaces = inventory?.local_surfaces;
  const routeCoverage = inventory?.route_coverage;
  const archiveCoverage = routeCoverage?.archive_types;
  const robotsProfile = routeCoverage?.robots_profile;
  const rawClusters = inventory?.clusters;
  const widths = inventory?.viewports;
  const requiredWidths = [360, 390, 768, 1440];
  const articleRows = Array.isArray(publicSurfaces)
    ? publicSurfaces.filter((surface) => surface.kind === 'article')
    : [];
  const policyRows = Array.isArray(publicSurfaces)
    ? publicSurfaces.filter((surface) => surface.kind === 'policy')
    : [];
  const homeRows = Array.isArray(publicSurfaces)
    ? publicSurfaces.filter((surface) => surface.kind === 'home')
    : [];
  const comparisonPolicyRows = policyRows.filter(
    (surface) => surface.surface_id === 'policy-comparison-policy',
  );
  const comparisonPolicyPath = comparisonPolicyRows[0]?.local_path;
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
    ['lifecycle_status_route', '型番・販売表示の確認案内'],
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
  const localSurfaceIds = new Set(
    Array.isArray(localSurfaces) ? localSurfaces.map((surface) => surface.surface_id) : [],
  );
  const localSurfaceById = new Map(
    Array.isArray(localSurfaces)
      ? localSurfaces.map((surface) => [surface.surface_id, surface])
      : [],
  );
  const routeClassCounts = new Map();
  if (Array.isArray(localSurfaces)) {
    for (const surface of localSurfaces) {
      routeClassCounts.set(
        surface.route_class,
        (routeClassCounts.get(surface.route_class) || 0) + 1,
      );
    }
  }
  const localArchiveRows = Array.isArray(localSurfaces)
    ? localSurfaces.filter((surface) => surface.kind === 'archive')
    : [];
  const applicableArchiveSurfaceIds = Array.isArray(archiveCoverage)
    ? archiveCoverage.filter((row) => row.status === 'APPLICABLE')
      .flatMap((row) => row.surface_ids || [])
    : [];
  const localByRouteClass = new Map(
    Array.isArray(localSurfaces)
      ? localSurfaces.map((surface) => [surface.route_class, surface])
      : [],
  );
  if (
    typeof artifactDirectory !== 'string' || !artifactDirectory.startsWith('/') ||
    typeof axeSource !== 'string' || axeSource.length < 100000 ||
    typeof origin !== 'string' || !/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(origin) ||
    inventory?.schema !== 'RAOS_WORDPRESS_AUDIT_INVENTORY_V3' ||
    inventory?.version !== '3.0.0' ||
    inventory?.target_origin !== 'https://kurashinoshirube.com' ||
    !Array.isArray(publicSurfaces) || publicSurfaces.length !== 14 ||
    !Array.isArray(localSurfaces) || localSurfaces.length !== 12 ||
    homeRows.length !== 1 || articleRows.length !== 10 || policyRows.length !== 3 ||
    comparisonPolicyRows.length !== 1 || !publicPath(comparisonPolicyPath) ||
    !Array.isArray(rawClusters) || rawClusters.length !== 3 ||
    !Array.isArray(widths) || widths.length !== requiredWidths.length ||
    widths.some((width, index) => width !== requiredWidths[index]) ||
    new Set(rawSurfaces.map((surface) => surface.local_path)).size !== 14 ||
    new Set(rawSurfaces.map((surface) => surface.production_path)).size !== 14 ||
    new Set([...publicSurfaces, ...localSurfaces].map((row) => row.surface_id)).size !== 26 ||
    routeClassCounts.size !== 10 ||
    routeClassCounts.get('ARCHIVE_CATEGORY') !== 3 ||
    [...routeClassCounts].some(([routeClass, count]) =>
      routeClass !== 'ARCHIVE_CATEGORY' && count !== 1) ||
    !Array.isArray(archiveCoverage) || archiveCoverage.length !== 5 ||
    new Set(archiveCoverage.map((row) => row.archive_type)).size !== 5 ||
    archiveCoverage.map((row) => row.archive_type).sort().join('|') !==
      'author|category|date|post_type|tag' ||
    archiveCoverage.some((row) =>
      !['APPLICABLE', 'NOT_APPLICABLE'].includes(row.status) ||
      !Array.isArray(row.surface_ids) || new Set(row.surface_ids).size !== row.surface_ids.length ||
      (row.status === 'APPLICABLE'
        ? row.surface_ids.length < 1 || row.reason !== null || row.reason_code !== null ||
          row.surface_ids.some((surfaceId) =>
            !localSurfaceIds.has(surfaceId) ||
            localSurfaceById.get(surfaceId)?.archive_type !== row.archive_type)
        : row.surface_ids.length !== 0 ||
          typeof row.reason !== 'string' || row.reason.trim() !== row.reason ||
          row.reason.length < 20 || row.reason.length > 180 ||
          !/^[A-Z0-9]+(?:_[A-Z0-9]+)+$/.test(row.reason_code || '')),
    ) ||
    applicableArchiveSurfaceIds.length !== localArchiveRows.length ||
    new Set(applicableArchiveSurfaceIds).size !== localArchiveRows.length ||
    localArchiveRows.some((surface) => !applicableArchiveSurfaceIds.includes(surface.surface_id)) ||
    robotsProfile?.local_profile_id !== 'LOCAL_PREVIEW' ||
    robotsProfile?.local_observed_policy !==
      'FORCED_ALL_NOINDEX_NOFOLLOW_NOARCHIVE_NOSNIPPET' ||
    robotsProfile?.production_expected_search_archive !== 'noindex, follow' ||
    robotsProfile?.production_expected_not_found !== 'noindex, nofollow' ||
    robotsProfile?.production_robots_evidence !== false ||
    localByRouteClass.get('SEARCH_EMPTY_QUERY')?.local_path !== '/?s=' ||
    localByRouteClass.get('SEARCH_EMPTY_QUERY')?.expected_state !== 'EMPTY_QUERY' ||
    localByRouteClass.get('SEARCH_EMPTY_QUERY')?.expected_search_query !== '' ||
    localByRouteClass.get('SEARCH_WHITESPACE_QUERY')?.local_path !== '/?s=%20%20%20' ||
    localByRouteClass.get('SEARCH_WHITESPACE_QUERY')?.expected_state !== 'WHITESPACE_QUERY' ||
    localByRouteClass.get('SEARCH_WHITESPACE_QUERY')?.expected_search_query !== '' ||
    localByRouteClass.get('SEARCH_HOSTILE_QUERY')?.local_path !==
      '/?s=%3Cscript%3Ealert%281%29%3C%2Fscript%3E' ||
    localByRouteClass.get('SEARCH_HOSTILE_QUERY')?.expected_state !==
      'HOSTILE_QUERY_ESCAPED' ||
    localByRouteClass.get('SEARCH_HOSTILE_QUERY')?.expected_search_query !==
      '<script>alert(1)</script>' ||
    localByRouteClass.get('SEARCH_PAGED_RESULTS')?.local_path !==
      '/?s=%E6%AF%94%E8%BC%83&paged=2' ||
    localByRouteClass.get('SEARCH_PAGED_RESULTS')?.expected_state !== 'PAGED_RESULTS' ||
    localByRouteClass.get('SEARCH_PAGED_RESULTS')?.expected_search_query !== '比較' ||
    localByRouteClass.get('SEARCH_PAGED_RESULTS')?.expected_page_number !== 2 ||
    publicSurfaces.some(
      (surface) =>
        !['home', 'article', 'policy'].includes(surface.kind) ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(surface.surface_id || '') ||
        !publicPath(surface.local_path) || !publicPath(surface.production_path),
    ) ||
    localSurfaces.some(
      (surface) =>
        !['search', 'archive', 'not_found'].includes(surface.kind) ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(surface.surface_id || '') ||
        !localPath(surface.local_path, surface.kind) ||
        surface.expected_canonical !== 'ABSENT' ||
        ![200, 404].includes(surface.expected_http_status) ||
        !['EMPTY_QUERY', 'WHITESPACE_QUERY', 'RESULTS_PRESENT', 'NO_RESULTS',
          'HOSTILE_QUERY_ESCAPED', 'PAGED_RESULTS', 'EXCERPT_LIST', 'NOT_FOUND'].includes(
          surface.expected_state,
        ) ||
        !/^[A-Z]+(?:_[A-Z]+)*$/.test(surface.route_class || '') ||
        !Array.isArray(surface.expected_ui_text) || surface.expected_ui_text.length < 2 ||
        surface.expected_ui_text.length > 4 ||
        surface.expected_ui_text.some((value) =>
          typeof value !== 'string' || value.trim() !== value ||
          value.length < 2 || value.length > 100) ||
        (surface.kind === 'search' && (
          typeof surface.expected_search_query !== 'string' ||
          ![null, 2].includes(surface.expected_page_number) ||
          surface.expected_http_status !== 200 ||
          !surface.route_class.startsWith('SEARCH_')
        )) ||
        (surface.kind === 'archive' && (
          !['category', 'date', 'author'].includes(surface.archive_type) ||
          surface.expected_state !== 'EXCERPT_LIST' ||
          surface.expected_http_status !== 200 ||
          surface.route_class !== `ARCHIVE_${surface.archive_type.toUpperCase()}`
        )) ||
        (surface.kind === 'not_found' && (
          surface.expected_state !== 'NOT_FOUND' || surface.expected_http_status !== 404 ||
          surface.route_class !== 'NOT_FOUND'
        )),
    ) ||
    articleIds.size !== 10 ||
    lifecycleStatusRouteRows.length !== 1 ||
    lifecycleStatusRouteRows[0]?.article_id !== lifecycleStatusRouteArticleId ||
    articleById.get(lifecycleStatusRouteArticleId)?.content_role !==
      'lifecycle_status_route' ||
    articleRows.some(
      (surface) =>
        !articleIds.has(surface.contextual_article_id) ||
        surface.contextual_article_id === surface.article_id ||
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
        !/^cluster-[a-z0-9-]+$/.test(cluster.anchor || '') ||
        !Array.isArray(cluster.article_ids) || cluster.article_ids.length < 2 ||
        new Set(cluster.article_ids).size !== cluster.article_ids.length ||
        cluster.article_ids.some((articleId) => !articleIds.has(articleId)),
    ) ||
    memberships.length !== 10 || new Set(memberships).size !== 10
  ) {
    throw new Error('RAOS_WORDPRESS_AUDIT_INVENTORY_INVALID');
  }
  const checkedIncrementalScope = validateIncrementalScope({
    publicationProfile, linkMode, incrementalScope, articleIds: [...articleIds],
  });

  const surfaces = [...publicSurfaces, ...localSurfaces].map((surface) => ({
    ...surface,
    article: surface.kind === 'article',
    expectedStatus: surface.expected_http_status || 200,
    name: surface.surface_id,
    path: surface.local_path,
    publicCore: ['home', 'article', 'policy'].includes(surface.kind),
  }));
  const requiredJsonLdTypesByKind = {
    home: ['Organization', 'WebSite'],
    article: ['Article', 'BreadcrumbList', 'Organization', 'WebSite'],
    policy: ['BreadcrumbList', 'Organization', 'WebSite'],
  };
  const forbiddenJsonLdTypes = ['Product', 'Offer', 'Review', 'FAQPage'];
  const extractJsonLdTypes = (documents) => {
    const types = [];
    const stack = [...documents];
    while (stack.length > 0) {
      const value = stack.pop();
      if (value === null || typeof value !== 'object') continue;
      if (Array.isArray(value)) {
        stack.push(...value);
        continue;
      }
      const rawTypes = Array.isArray(value['@type']) ? value['@type'] : [value['@type']];
      for (const value of rawTypes) {
        if (typeof value !== 'string') continue;
        const normalized = value.trim();
        if (normalized !== '') types.push(normalized);
      }
      stack.push(...Object.values(value));
    }
    return types;
  };
  const expectedPathByArticleId = Object.fromEntries(
    articleRows.map((surface) => [surface.article_id, surface.local_path]),
  );
  const parseLocalUrl = (value) => {
    if (
      typeof value !== 'string' ||
      (value !== origin && !value.startsWith(`${origin}/`))
    ) return null;
    const suffix = value.slice(origin.length) || '/';
    const hashAt = suffix.indexOf('#');
    const beforeHash = hashAt === -1 ? suffix : suffix.slice(0, hashAt);
    const hash = hashAt === -1 ? '' : suffix.slice(hashAt);
    const queryAt = beforeHash.indexOf('?');
    return {
      hash,
      origin,
      pathname: queryAt === -1 ? beforeHash : beforeHash.slice(0, queryAt),
      search: queryAt === -1 ? '' : beforeHash.slice(queryAt),
    };
  };
  const runtimeErrors = [];
  const resourceErrors = [];
  const forbiddenRequests = [];
  const requestCounts = new Map();
  const allowedRequestMethods = new Set(['GET', 'HEAD']);
  const allowedRequestResourceTypes = new Set([
    'document', 'font', 'image', 'script', 'stylesheet',
  ]);
  let externalRequestCount = 0;
  let measurementRequestCount = 0;
  let expectedNotFoundConsoleMessages = 0;
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const messageText = message.text();
    if (
      expectedNotFoundConsoleMessages > 0 &&
      messageText === 'Failed to load resource: the server responded with a status of 404 (Not Found)'
    ) {
      expectedNotFoundConsoleMessages -= 1;
      return;
    }
    runtimeErrors.push('console-error');
  });
  page.on('pageerror', (error) => runtimeErrors.push(`page:${error.name}`));
  page.on('response', (response) => {
    if (response.status() >= 400 && response.request().resourceType() !== 'document') {
      resourceErrors.push({
        resourceType: response.request().resourceType(),
        status: response.status(),
      });
    }
  });
  page.on('request', (request) => {
    const url = request.url();
    const method = request.method().toUpperCase();
    const resourceType = request.resourceType();
    const scope = url === origin || url.startsWith(`${origin}/`)
      ? 'local'
      : url.startsWith('data:')
        ? 'data'
        : url.startsWith('blob:')
          ? 'blob'
          : 'external';
    const signature = `${method}|${resourceType}|${scope}`;
    requestCounts.set(signature, (requestCounts.get(signature) || 0) + 1);
    if (url === `${origin}/wp-json/raos/v1/events`) measurementRequestCount += 1;
    if (scope === 'external') externalRequestCount += 1;
    if (
      !allowedRequestMethods.has(method) ||
      !allowedRequestResourceTypes.has(resourceType)
    ) {
      forbiddenRequests.push({ method, resourceType, scope });
    }
  });

  const graphFailure = (audit, surface, expectedUrl) => {
    const forbidden = new Set(['AggregateRating', 'FAQPage', 'Offer', 'Product', 'Review']);
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
          typeof type === 'string' && forbidden.has(type.replace(/^.*[/#:]/, '')))) return true;
        stack.push(...Object.values(value));
      }
      return false;
    };
    if (audit.jsonLd.some((document) => containsForbiddenType(document))) {
      return 'FORBIDDEN_TYPE';
    }
    if (!surface.publicCore) return null;
    if (audit.jsonLd.length !== 1) return 'COUNT';
    const document = audit.jsonLd[0];
    if (!document || document['@context'] !== 'https://schema.org' || !Array.isArray(document['@graph'])) {
      return 'DOCUMENT';
    }
    const graph = document['@graph'];
    const ids = graph.map((node) => node?.['@id']).filter(Boolean);
    if (new Set(ids).size !== ids.length || ids.some((id) => !id.startsWith(`${origin}/`))) {
      return 'IDENTITY';
    }
    const byType = (type) => graph.filter((node) => node?.['@type'] === type);
    const organization = byType('Organization')[0];
    const website = byType('WebSite')[0];
    if (
      byType('Organization').length !== 1 || byType('WebSite').length !== 1 ||
      organization['@id'] !== `${origin}/#organization` ||
      organization.name !== '暮らしのしるべ編集者' || organization.url !== `${origin}/` ||
      website['@id'] !== `${origin}/#website` || website.url !== `${origin}/` ||
      website.name !== '暮らしのしるべ' || website.inLanguage !== 'ja-JP' ||
      website.publisher?.['@id'] !== organization['@id']
    ) return 'PUBLISHER';
    if (surface.kind === 'home') return graph.length === 2 ? null : 'HOME_GRAPH';
    const breadcrumb = byType('BreadcrumbList')[0];
    const items = breadcrumb?.itemListElement;
    if (
      byType('BreadcrumbList').length !== 1 ||
      breadcrumb['@id'] !== `${expectedUrl}#breadcrumb` ||
      !Array.isArray(items) || items.length !== 2 ||
      items[0]?.position !== 1 || items[0]?.item !== `${origin}/` ||
      items[1]?.position !== 2 || items[1]?.item !== expectedUrl ||
      items[1]?.name !== audit.head.title
    ) return 'BREADCRUMB';
    if (surface.kind === 'article') {
      const article = byType('Article')[0];
      if (
        graph.length !== 4 || byType('Article').length !== 1 ||
        article['@id'] !== `${expectedUrl}#article` ||
        article.headline !== audit.head.title || article.description !== audit.head.description[0] ||
        article.mainEntityOfPage !== expectedUrl || article.inLanguage !== 'ja-JP' ||
        article.author?.['@id'] !== organization['@id'] ||
        article.publisher?.['@id'] !== organization['@id'] ||
        !Array.isArray(article.image) || article.image[0] !== audit.head.ogImage[0] ||
        typeof article.articleSection !== 'string' || article.articleSection.length === 0 ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(article.datePublished || '') ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(article.dateModified || '') ||
        article.dateModified < article.datePublished
      ) return 'ARTICLE';
      return null;
    }
    const pageType = surface.name === 'policy-about-ad-policy' ? 'AboutPage' : 'WebPage';
    const node = byType(pageType)[0];
    if (
      graph.length !== 4 || byType(pageType).length !== 1 ||
      node['@id'] !== `${expectedUrl}#webpage` || node.url !== expectedUrl ||
      node.name !== audit.head.title || node.description !== audit.head.description[0] ||
      node.inLanguage !== 'ja-JP' || node.isPartOf?.['@id'] !== website['@id'] ||
      node.breadcrumb?.['@id'] !== breadcrumb['@id']
    ) return 'PAGE';
    return null;
  };

  const results = [];
  for (const surface of surfaces) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      expectedNotFoundConsoleMessages = surface.expectedStatus === 404 ? 1 : 0;
      const expectedUrl = `${origin}${surface.path}`;
      const response = await page.goto(expectedUrl, { waitUntil: 'networkidle' });
      if (
        !response || response.status() !== surface.expectedStatus ||
        (surface.publicCore && response.status() !== 200) ||
        response.url() !== expectedUrl
      ) {
        throw new Error(`RAOS_WORDPRESS_LOCAL_PREVIEW_HTTP_FAILED_${surface.name}`);
      }
      await page.evaluate(async () => {
        for (const image of document.images) {
          if (!image.complete) {
            image.scrollIntoView({ block: 'center', inline: 'nearest' });
            await Promise.race([
              new Promise((resolve) => {
                image.addEventListener('load', resolve, { once: true });
                image.addEventListener('error', resolve, { once: true });
              }),
              new Promise((resolve) => setTimeout(resolve, 3000)),
            ]);
          }
        }
        scrollTo(0, 0);
      });
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
          throw new Error(`RAOS_WORDPRESS_HOME_REAL_SCROLL_FAILED_${width}`);
        }
      }
      if (surface.article) {
        await page.locator('.raos-disclosure')
          .scrollIntoViewIfNeeded();
        await page.evaluate(
          () => new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
      }
      await page.addScriptTag({ content: axeSource });
      const responseHeaders = await response.allHeaders();
      const normalizedPermissionsPolicy = (responseHeaders['permissions-policy'] || '')
        .split(',').map((value) => value.trim()).join(', ');
      const expectedPermissionsPolicy = [
        'accelerometer=()', 'autoplay=()', 'camera=()', 'geolocation=()', 'gyroscope=()',
        'magnetometer=()', 'microphone=()', 'payment=()', 'usb=()',
      ].join(', ');
      const responseRobotsTokens = new Set(
        (responseHeaders['x-robots-tag'] || '').toLowerCase().split(',')
          .map((value) => value.trim()).filter(Boolean),
      );
      const securityHeaderFailure = [
        /^text\/html;\s*charset=UTF-8$/i.test(responseHeaders['content-type'] || '')
          ? null : 'content-type-charset',
        responseHeaders['x-content-type-options'] === 'nosniff' ? null : 'nosniff',
        responseHeaders['referrer-policy'] === 'no-referrer' ? null : 'referrer-policy',
        normalizedPermissionsPolicy === expectedPermissionsPolicy ? null : 'permissions-policy',
        responseHeaders['x-frame-options'] === 'DENY' ? null : 'frame-protection',
      ].filter(Boolean);
      const audit = await page.evaluate(async ({
        comparisonPolicyPath, expectedPageNumber, expectedSearchQuery,
      }) => {
        const visible = (element) => {
          if (!(element instanceof HTMLElement)) return false;
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' &&
            rect.width > 0 && rect.height > 0;
        };
        const boxes = (selector) => [...document.querySelectorAll(selector)].map((element) => {
          const rect = element.getBoundingClientRect();
          return { bottom: rect.bottom, height: rect.height, left: rect.left,
            right: rect.right, top: rect.top, width: rect.width };
        });
        const values = (selector, attribute = 'content') =>
          [...document.querySelectorAll(selector)].map((element) =>
            (element.getAttribute(attribute) || '').trim());
        const visibleFactValues = (label) => [...document.querySelectorAll('dt')]
          .filter((term) => term.textContent?.trim() === label)
          .flatMap((term) => {
            const value = term.nextElementSibling;
            return value instanceof HTMLElement && value.tagName === 'DD' && visible(value)
              ? [value.textContent?.trim() || ''] : [];
          });
        const ids = [...document.querySelectorAll('[id]')].map((node) => node.id).filter(Boolean);
        const ariaAttributes = ['aria-activedescendant', 'aria-controls', 'aria-describedby',
          'aria-details', 'aria-labelledby', 'aria-owns'];
        const ariaSelector = ariaAttributes.map((name) => `[${name}]`).join(',');
        const brokenAriaReferences = [...document.querySelectorAll(ariaSelector)].filter((node) =>
          ariaAttributes.flatMap((name) => (node.getAttribute(name) || '').split(/\s+/).filter(Boolean))
            .some((id) => !document.getElementById(id))).length;
        const controls = [...document.querySelectorAll(
          'input:not([type="hidden"]),select,textarea,button',
        )];
        const productProfiles = [...document.querySelectorAll('.product-profile')];
        const productIds = productProfiles.map((profile) =>
          (profile.getAttribute('data-raos-product-id') || '').trim());
        const commerceCtas = [...document.querySelectorAll('a[href]')].filter((anchor) =>
          anchor.matches('.raos-cta,[data-raos-placement]') ||
          (() => { try { return new URL(anchor.href).hostname === 'hb.afl.rakuten.co.jp'; }
            catch { return false; } })()).map((anchor) => ({
          cta_id: anchor.getAttribute('data-raos-cta-id'),
          article_id: anchor.getAttribute('data-raos-article-id'),
          product_id: anchor.getAttribute('data-raos-product-id') ||
            anchor.closest('[data-raos-product-id]')?.getAttribute('data-raos-product-id') || null,
          placement: anchor.getAttribute('data-raos-placement'),
          affiliate_host_valid: (() => { try { const url = new URL(anchor.href);
            return url.protocol === 'https:' && url.hostname === 'hb.afl.rakuten.co.jp';
          } catch { return false; } })(),
          rel_tokens: [...anchor.relList],
          has_measured_identifier: anchor.hasAttribute('data-raos-provider-measurement-id') ||
            anchor.hasAttribute('data-raos-provider-slot-id'),
        }));
        const commerceImages = [...document.querySelectorAll(
          '.product-profile img,.raos-product-card img,img[data-raos-product-image-id]',
        )].map((image) => ({
          product_id: image.getAttribute('data-raos-product-image-id') ||
            image.closest('[data-raos-product-id]')?.getAttribute('data-raos-product-id') || null,
          state: image.getAttribute('data-raos-product-image-state'),
          alt_valid: Boolean(image.getAttribute('alt')?.trim()),
          dimensions_valid: image.width > 0 && image.height > 0,
          lazy: image.loading === 'lazy',
        }));
        const commercePlaceholderCount = document.querySelectorAll(
          '[data-raos-product-image-state="neutral"],[data-raos-product-image-state="unverified"],'
          + '.raos-product-image-placeholder,.raos-product-card__media:empty,'
          + '[data-raos-purchase-action][aria-disabled="true"]',
        ).length;
        let sessionKeys = 0;
        try {
          for (let index = 0; index < sessionStorage.length; index += 1) {
            if ((sessionStorage.key(index) || '').startsWith('raos_measurement_v1:')) sessionKeys += 1;
          }
        } catch (error) {
          sessionKeys = -1;
        }
        let documentCookieCount = -1;
        let localStorageKeyCount = -1;
        let sessionStorageKeyCount = -1;
        let indexedDbDatabaseCount = -1;
        let cacheStorageCount = -1;
        let serviceWorkerRegistrationCount = -1;
        try {
          const cookieText = document.cookie.trim();
          documentCookieCount = cookieText === '' ? 0 : cookieText.split(';').length;
          localStorageKeyCount = localStorage.length;
          sessionStorageKeyCount = sessionStorage.length;
          indexedDbDatabaseCount = typeof indexedDB?.databases === 'function'
            ? (await indexedDB.databases()).length : -1;
          cacheStorageCount = typeof caches?.keys === 'function'
            ? (await caches.keys()).length : -1;
          serviceWorkerRegistrationCount =
            typeof navigator.serviceWorker?.getRegistrations === 'function'
              ? (await navigator.serviceWorker.getRegistrations()).length : -1;
        } catch (error) {
          // All APIs are available in the pinned Chromium runtime. A denied or
          // unreadable state fails closed instead of being treated as empty.
        }
        const jsonLd = [];
        let jsonLdParseFailures = 0;
        for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
          try { jsonLd.push(JSON.parse(script.textContent || '')); }
          catch (error) { jsonLdParseFailures += 1; }
        }
        const axeResult = await window.axe.run(document, {
          resultTypes: ['violations'],
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
        });
        const footerGrid = document.querySelector('.raos-footer__grid');
        const footerStyle = footerGrid ? getComputedStyle(footerGrid) : null;
        const h1 = document.querySelector('h1');
        const h1Range = h1 ? document.createRange() : null;
        if (h1Range) h1Range.selectNodeContents(h1);
        const lineTops = h1Range ? [...h1Range.getClientRects()].map((rect) => Math.round(rect.top)) : [];
        const disclosure = document.querySelector('.raos-disclosure');
        const disclosureRect = disclosure instanceof HTMLElement
          ? disclosure.getBoundingClientRect() : null;
        const disclosureStyle = disclosure instanceof HTMLElement
          ? getComputedStyle(disclosure) : null;
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
          const isLocalHttp = target.protocol === 'http:' && target.origin === location.origin;
          const isHttps = target.protocol === 'https:';
          const isExpectedMail = target.href === 'mailto:contact@kurashinoshirube.com';
          if (!isLocalHttp && !isHttps && !isExpectedMail) {
            anchorSecurity.unsafeSchemeCount += 1;
          }
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
        const paginationAnchors = [...document.querySelectorAll(
          '.wp-block-query-pagination a[href]',
        )];
        const pageNumber = (url) => {
          const pathnameMatch = url.pathname.match(/\/page\/([1-9][0-9]*)\/?$/);
          if (pathnameMatch) return Number(pathnameMatch[1]);
          for (const [name, value] of url.searchParams.entries()) {
            if ((name === 'paged' || /(?:^|-)page$/.test(name)) && /^[1-9][0-9]*$/.test(value)) {
              return Number(value);
            }
          }
          return 1;
        };
        const pagination = {
          count: paginationAnchors.length,
          differentPageCount: expectedPageNumber === null ? 0 : paginationAnchors.filter(
            (anchor) => pageNumber(new URL(anchor.href)) !== expectedPageNumber,
          ).length,
          originMismatchCount: paginationAnchors.filter(
            (anchor) => new URL(anchor.href).origin !== location.origin,
          ).length,
          queryMismatchCount: expectedSearchQuery === null ? 0 : paginationAnchors.filter(
            (anchor) => (new URL(anchor.href).searchParams.get('s') || '').trim() !==
              expectedSearchQuery,
          ).length,
        };
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
          axeViolations: axeResult.violations.map((row) => ({ id: row.id, impact: row.impact,
            nodes: row.nodes.length })),
          bannerText: document.querySelector('.raos-local-preview-banner')?.textContent?.trim() || '',
          brokenAriaReferences,
          characterSet: document.characterSet,
          clientWidth: document.documentElement.clientWidth,
          consentElementCount: document.querySelectorAll(
            '.cky-consent-container,.cky-banner-element,[data-cookieyes]',
          ).length,
          comparisonFocusability,
          cookieSettingsCount: document.querySelectorAll('.raos-cookie-settings').length,
          ctaBoxes: boxes('.raos-cta[data-raos-placement]'),
          commerceCtas,
          commerceImages,
          commercePlaceholderCount,
          productIds,
          productProfileCount: productProfiles.length,
          duplicateIds: [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))],
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
            opacityVisible: disclosureStyle !== null && disclosureAncestorsVisible &&
              disclosureEffectiveOpacity > 0 && visible(disclosure),
            nonaffiliatePhraseCount: [
              '購入リンクなし',
              '商品カードとアフィリエイトリンクは掲載していません',
              '購入先を案内しないことは、商品の性能が劣るという意味ではありません',
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
          editorialBodyClass: document.body.classList.contains('raos-editorial-v2-page'),
          editorialRootCount: document.querySelectorAll('.raos-editorial-v2').length,
          emptyStateCount: document.querySelectorAll('.raos-listing-empty').length,
          footerBackground: getComputedStyle(document.querySelector('.raos-footer')).backgroundColor,
          footerBoxes: boxes('.raos-footer__grid,.raos-footer__bottom'),
          footerColumnCount: footerStyle?.gridTemplateColumns === 'none' ? 0 :
            (footerStyle?.gridTemplateColumns || '').split(/\s+/).filter(Boolean).length,
          footerDisplay: footerStyle?.display || '',
          footerLinkBoxes: boxes('.raos-footer a'),
          fullPostContentCount: document.querySelectorAll('.wp-block-post-content').length,
          h1Count: document.querySelectorAll('h1').length,
          h1LineCount: new Set(lineTops).size,
          homeClusters: [...document.querySelectorAll('.raos-cluster-nav .raos-cluster')]
            .map((cluster) => ({
              anchor: cluster.id,
              links: [...cluster.querySelectorAll('a[href]')].map((anchor) => ({
                href: anchor.href,
                pathname: new URL(anchor.href).pathname,
              })),
            })),
          head: {
            canonical: values('link[rel="canonical"]', 'href'),
            canonicalResolved: [...document.querySelectorAll('link[rel="canonical"][href]')]
              .map((link) => link.href),
            description: values('meta[name="description"]'),
            ogDescription: values('meta[property="og:description"]'),
            ogImage: values('meta[property="og:image"]'),
            ogLocale: values('meta[property="og:locale"]'),
            ogSiteName: values('meta[property="og:site_name"]'),
            ogTitle: values('meta[property="og:title"]'),
            ogType: values('meta[property="og:type"]'),
            ogUrl: values('meta[property="og:url"]'),
            robots: values('meta[name="robots"]'),
            title: document.title.trim(),
            titleCount: document.querySelectorAll('head > title').length,
            twitterCard: values('meta[name="twitter:card"]'),
            twitterDescription: values('meta[name="twitter:description"]'),
            twitterImage: values('meta[name="twitter:image"]'),
            twitterTitle: values('meta[name="twitter:title"]'),
          },
          imageLoadingInvalid: [...document.querySelectorAll('.raos-product-card img')]
            .filter((image) => image.loading !== 'lazy' || !image.width || !image.height).length,
          heroNotice: (() => {
            const notices = [...document.querySelectorAll('.raos-article-hero-image__notice')];
            return {
              count: notices.length,
              text: notices.map((notice) => notice.textContent?.trim() || '').join('|'),
              visible: notices.length === 1 && visible(notices[0]),
            };
          })(),
          hostileExecutableCount: [...document.scripts].filter((script) =>
            (script.textContent || '').includes('alert(1)') ||
            (script.getAttribute('src') || '').includes('alert(1)')).length +
            [...document.querySelectorAll('*')].filter((element) =>
              [...element.attributes].some((attribute) =>
                /^on/i.test(attribute.name) && attribute.value.includes('alert(1)'))).length,
          jsonLd,
          jsonLdParseFailures,
          lang: document.documentElement.lang,
          listingBodyClass: document.body.classList.contains('raos-listing-page'),
          listingCardCount: document.querySelectorAll('.raos-listing-card').length,
          mainCount: document.querySelectorAll('main').length,
          measurementConfigDefined: typeof window.RAOS_MEASUREMENT_CONFIG_V1 !== 'undefined',
          measurementScriptCount: document.querySelectorAll(
            'script#kurashinoshirube-measurement-v1-js,script[src*="/assets/measurement.js"]',
          ).length,
          measurementSessionKeyCount: sessionKeys,
          storageState: {
            cacheStorageCount,
            documentCookieCount,
            indexedDbDatabaseCount,
            localStorageKeyCount,
            serviceWorkerRegistrationCount,
            sessionStorageKeyCount,
          },
          missingAlt: document.querySelectorAll('img:not([alt])').length,
          notFoundBodyClass: document.body.classList.contains('raos-not-found-page'),
          pagination,
          policyBodyClass: document.body.classList.contains('raos-policy-v3-page'),
          reducedMotion: {
            animatedElementCount,
            htmlScrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
            mediaMatches: matchMedia('(prefers-reduced-motion: reduce)').matches,
            smoothScrollElementCount,
          },
          scrollWidth: document.documentElement.scrollWidth,
          searchInputMatch: expectedSearchQuery === null ||
            [...document.querySelectorAll('input[type="search"]')]
              .some((input) => input.value.trim() === expectedSearchQuery),
          toc: {
            backCount: document.querySelectorAll('.raos-back-to-toc[href="#raos-article-toc"]').length,
            count: document.querySelectorAll('#raos-article-toc.raos-article-toc').length,
            detailsOpen: document.querySelector('.raos-article-toc details')?.open === true,
            firstTarget: document.querySelector('.raos-article-toc a[href^="#"]')?.hash || '',
            listVisible: visible(document.querySelector('.raos-article-toc ol')),
            summaryVisible: visible(document.querySelector('.raos-article-toc summary')),
            titleText: document.querySelector('.raos-article-toc__title')?.textContent?.trim() || '',
            titleVisible: visible(document.querySelector('.raos-article-toc__title')),
          },
          unlabeledControls: controls.filter((element) => element.tagName !== 'BUTTON' &&
            !element.labels?.length && !element.getAttribute('aria-label') &&
            !element.getAttribute('aria-labelledby')).length,
        };
      }, {
        comparisonPolicyPath,
        expectedPageNumber: surface.expected_page_number ?? null,
        expectedSearchQuery: surface.kind === 'search' ? surface.expected_search_query : null,
      });

      const imageLoading = classifyImageLoading({
        publicationProfile,
        commerceStatus: surface.article && checkedIncrementalScope?.articles.some(
          (row) => row.article_id === surface.article_id,
        ) && !checkedIncrementalScope.selected_article_ids.includes(surface.article_id)
          ? 'UNCHANGED_NOT_REVERIFIED' : 'STRICT',
        images: await page.evaluate(inspectImageLoading),
      });
      audit.unloadedImages = imageLoading.unloadedImages;
      audit.hiddenLegacyLazyImageCount = imageLoading.hiddenLegacyLazySources.length;
      audit.hiddenLegacyImageResourceFailures = await inspectHiddenLegacyImageResources({
        page, origin, sources: imageLoading.hiddenLegacyLazySources,
      });

      const browserCookieCount = (await page.context().cookies([expectedUrl])).length;
      const comparisonFocusabilityFailure = audit.comparisonFocusability.some((row) =>
        !row.accessibleName || (row.shouldBeFocusable
          ? row.tabindex !== '0' || row.availableState !== 'available'
          : row.tabindex !== null || row.availableState !== null));
      const head = audit.head;
      const expectedOpenGraphImageUrl = head.ogImage.length === 1
        ? head.ogImage[0] : '';
      let openGraphImageResponse = null;
      let openGraphImageResponseBodyBytes = 0;
      let openGraphImageResponseContentType = '';
      let openGraphImageResponseStatus = 0;
      let openGraphImageResponseUrl = '';
      try {
        if (
          /^http:\/\/127\.0\.0\.1:[0-9]{4,5}\/wp-content\/themes\//
            .test(expectedOpenGraphImageUrl) &&
          expectedOpenGraphImageUrl.endsWith('.webp')
        ) {
          openGraphImageResponse = await page.request.get(expectedOpenGraphImageUrl, {
            maxRedirects: 0,
            timeout: 5000,
          });
          openGraphImageResponseStatus = openGraphImageResponse.status();
          openGraphImageResponseUrl = openGraphImageResponse.url();
          openGraphImageResponseContentType = (
            openGraphImageResponse.headers()['content-type'] || ''
          ).split(';', 1)[0].trim().toLowerCase();
          if (openGraphImageResponseStatus === 200) {
            openGraphImageResponseBodyBytes = (await openGraphImageResponse.body()).length;
          }
        }
      } catch (error) {
        openGraphImageResponseBodyBytes = 0;
      } finally {
        if (openGraphImageResponse !== null) {
          await openGraphImageResponse.dispose();
        }
      }
      const openGraphImageResponseValid =
        openGraphImageResponse !== null &&
        openGraphImageResponseStatus === 200 &&
        openGraphImageResponseUrl === expectedOpenGraphImageUrl &&
        openGraphImageResponseContentType === 'image/webp' &&
        openGraphImageResponseBodyBytes > 0 &&
        openGraphImageResponseBodyBytes <= 2 * 1024 * 1024;
      const localNoindexHeaderValid =
        responseRobotsTokens.has('noindex') &&
        responseRobotsTokens.has('nofollow') &&
        !responseRobotsTokens.has('index') &&
        !responseRobotsTokens.has('follow');
      const seoHeadAudit = surface.publicCore
        ? validateSeoHead({
          audit: {
            canonicalLinks: head.canonical.map((rawHref, index) => ({
              rawHref,
              resolvedHref: head.canonicalResolved[index] || '',
            })),
            currentUrl: page.url(),
            jsonLdParseFailed: audit.jsonLdParseFailures !== 0,
            jsonLdScriptCount: audit.jsonLd.length + audit.jsonLdParseFailures,
            jsonLdTypes: extractJsonLdTypes(audit.jsonLd),
            metaDescriptions: head.description,
            metaRobots: head.robots,
            openGraph: {
              description: head.ogDescription,
              image: head.ogImage,
              title: head.ogTitle,
              url: head.ogUrl,
            },
            title: head.title,
            titleCount: head.titleCount,
          },
          expectedOpenGraphImageUrl,
          expectedUrl,
          forbiddenJsonLdTypes,
          localNoindexHeaderValid,
          openGraphImageResponseValid,
          requiredJsonLdTypes: requiredJsonLdTypesByKind[surface.kind],
        })
        : { failed: false };
      const seoHeadAuditFailed = seoHeadAudit.failed;
      const headFailure = surface.publicCore
        ? head.titleCount !== 1 || !head.title ||
          head.canonical.length !== 1 || head.canonical[0] !== expectedUrl ||
          head.description.length !== 1 || head.description[0].length < 30 ||
          head.ogTitle.length !== 1 || head.ogTitle[0] !== head.title ||
          head.ogDescription.length !== 1 || head.ogDescription[0] !== head.description[0] ||
          head.ogUrl.length !== 1 || head.ogUrl[0] !== expectedUrl ||
          head.ogImage.length !== 1 || !head.ogImage[0].startsWith(`${origin}/`) ||
          head.ogType.length !== 1 || head.ogType[0] !== (surface.article ? 'article' : 'website') ||
          head.ogLocale.length !== 1 || head.ogLocale[0] !== 'ja_JP' ||
          head.ogSiteName.length !== 1 || head.ogSiteName[0] !== '暮らしのしるべ' ||
          head.twitterCard.length !== 1 || head.twitterCard[0] !== 'summary_large_image' ||
          head.twitterTitle.length !== 1 || head.twitterTitle[0] !== head.title ||
          head.twitterDescription.length !== 1 || head.twitterDescription[0] !== head.description[0] ||
          head.twitterImage.length !== 1 || head.twitterImage[0] !== head.ogImage[0]
        : head.titleCount !== 1 || !head.title || surface.expected_canonical !== 'ABSENT' ||
          head.canonical.length !== 0;
      const metaRobotsTokens = head.robots.length === 1
        ? new Set(head.robots[0].toLowerCase().split(',')
          .map((value) => value.trim()).filter(Boolean))
        : new Set();
      const requiredLocalRobots = ['noindex', 'nofollow', 'noarchive', 'nosnippet'];
      const robotsFailure = head.robots.length !== 1 ||
        robotsProfile.production_robots_evidence !== false ||
        requiredLocalRobots.some((value) => !metaRobotsTokens.has(value)) ||
        requiredLocalRobots.some((value) => !responseRobotsTokens.has(value)) ||
        metaRobotsTokens.has('index') || metaRobotsTokens.has('follow') ||
        responseRobotsTokens.has('index') || responseRobotsTokens.has('follow');
      const semanticGraphFailure = graphFailure(audit, surface, expectedUrl);

      const missingUiText = surface.publicCore ? [] : await page.evaluate(
        (markers) => markers.filter((marker) => !document.body.innerText.includes(marker)),
        surface.expected_ui_text,
      );
      let routeFailure = null;
      if (!surface.publicCore) {
        routeFailure = await page.evaluate((route) => {
          const current = new URL(route.currentUrl);
          const requested = new URL(route.requestedUrl);
          if (current.origin !== route.origin) return 'ORIGIN';
          if (route.kind !== 'search' && (
            current.pathname !== requested.pathname || current.search !== requested.search
          )) return 'ROUTE_CHANGED';
          if (route.kind !== 'search') return null;
          if (!current.searchParams.has('s')) return 'SEARCH_QUERY_MISSING';
          if (
            route.expectedPageNumber === null &&
            current.pathname !== requested.pathname
          ) return 'SEARCH_ROUTE_CHANGED';
          const query = (current.searchParams.get('s') || '').trim();
          if (query !== route.expectedSearchQuery) return 'SEARCH_QUERY_NOT_PRESERVED';
          if (!route.searchInputMatch) return 'SEARCH_INPUT_NOT_PRESERVED';
          if (
            route.routeClass === 'SEARCH_HOSTILE_QUERY' &&
            route.hostileExecutableCount !== 0
          ) return 'HOSTILE_QUERY_EXECUTABLE';
          if (route.expectedPageNumber === null) return null;
          const pageNumber = (url) => {
            const pathnameMatch = url.pathname.match(/\/page\/([1-9][0-9]*)\/?$/);
            if (pathnameMatch) return Number(pathnameMatch[1]);
            for (const [name, value] of url.searchParams.entries()) {
              if ((name === 'paged' || /(?:^|-)page$/.test(name)) && /^[1-9][0-9]*$/.test(value)) {
                return Number(value);
              }
            }
            return 1;
          };
          if (pageNumber(current) !== route.expectedPageNumber) {
            return 'SEARCH_PAGE_NOT_PRESERVED';
          }
          if (route.pagination.count < 1) return 'PAGINATION_MISSING';
          if (
            route.pagination.originMismatchCount !== 0 ||
            route.pagination.queryMismatchCount !== 0
          ) {
            return 'PAGINATION_QUERY_NOT_PRESERVED';
          }
          return route.pagination.differentPageCount > 0
            ? null : 'PAGINATION_CONTINUITY_MISSING';
        }, {
          currentUrl: page.url(),
          expectedPageNumber: surface.expected_page_number,
          expectedSearchQuery: surface.expected_search_query,
          hostileExecutableCount: audit.hostileExecutableCount,
          kind: surface.kind,
          origin,
          pagination: audit.pagination,
          requestedUrl: `${origin}${surface.path}`,
          routeClass: surface.route_class,
          searchInputMatch: audit.searchInputMatch,
        });
      }

      let disclosureKeyboardFailure = null;
      if (
        surface.article && width === 390 &&
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

      let skipLinkFailure = null;
      if (width === 390) {
        skipLinkFailure = await (async () => {
          const skipLink = page.locator('#wp-skip-link');
          if (await skipLink.count() !== 1) return 'LINK_MISSING';
          const targetHash = await skipLink.getAttribute('href');
          if (!targetHash || !targetHash.startsWith('#') || targetHash.length < 2) {
            return 'TARGET_INVALID';
          }
          const targetId = decodeURIComponent(targetHash.slice(1));
          const targetState = await page.evaluate((id) => {
            const target = document.getElementById(id);
            return target
              ? { tabIndex: target.getAttribute('tabindex'), tagName: target.tagName }
              : null;
          }, targetId);
          if (!targetState || targetState.tagName !== 'MAIN' || targetState.tabIndex !== '-1') {
            return 'TARGET_NOT_FOCUSABLE';
          }
          await page.evaluate(() => scrollTo(0, 0));
          await skipLink.focus();
          await page.keyboard.press('Enter');
          await page.evaluate(
            () => new Promise((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          return await page.evaluate(
            ({ hash, id }) => location.hash === hash && document.activeElement?.id === id
              ? null
              : 'FOCUS_NOT_MOVED',
            { hash: targetHash, id: targetId },
          );
        })();
      }

      let navigationFailure = null;
      if (surface.article && width === 390) {
        navigationFailure = await (async () => {
          await page.locator('.raos-article-toc details').evaluate((details) => {
            details.open = true;
          });
          const tocLink = page.locator('.raos-article-toc a[href^="#"]').first();
          if (await tocLink.count() !== 1) return 'TOC_LINK_MISSING';
          const targetHash = await tocLink.getAttribute('href');
          if (!targetHash || !/^#[a-z][a-z0-9-]{1,80}$/.test(targetHash)) {
            return 'TOC_TARGET_INVALID';
          }
          const targetId = targetHash.slice(1);
          await tocLink.focus();
          await page.keyboard.press('Enter');
          await page.evaluate(
            () => new Promise((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          const targetReached = await page.evaluate(
            ({ id, hash }) => location.hash === hash && document.activeElement?.id === id,
            { hash: targetHash, id: targetId },
          );
          if (!targetReached) return 'TOC_FOCUS';
          const back = page.locator('[id="' + targetId + '"]').locator(
            'xpath=ancestor::section[1]//a[' +
              'contains(concat(" ", normalize-space(@class), " "), " raos-back-to-toc ")][1]',
          );
          if (await back.count() !== 1) return 'BACK_LINK_MISSING';
          await back.focus();
          await page.keyboard.press('Enter');
          await page.evaluate(
            () => new Promise((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(resolve))),
          );
          return await page.evaluate(() =>
            location.hash === '#raos-article-toc' &&
              document.activeElement?.id === 'raos-article-toc'
              ? null
              : 'BACK_FOCUS');
        })();
      }

      let desktopTocPositionFailure = null;
      if (surface.article && width === 1440) {
        desktopTocPositionFailure = await (async () => {
          const tocLink = page.locator('.raos-article-toc a[href^="#"]').first();
          if (await tocLink.count() !== 1) return 'TOC_LINK_MISSING';
          const targetHash = await tocLink.getAttribute('href');
          if (!targetHash || !/^#[a-z][a-z0-9-]{1,80}$/.test(targetHash)) {
            return 'TOC_TARGET_INVALID';
          }
          const targetId = targetHash.slice(1);
          const isUnobscured = () => page.evaluate((id) => {
            const toc = document.querySelector('.raos-article-toc');
            const main = document.querySelector('.raos-editorial-v2__main');
            const target = document.getElementById(id);
            if (
              !(toc instanceof HTMLElement) || !(main instanceof HTMLElement) ||
              !(target instanceof HTMLElement)
            ) {
              return false;
            }
            const tocRect = toc.getBoundingClientRect();
            const mainRect = main.getBoundingClientRect();
            const targetRect = target.getBoundingClientRect();
            const stickyTop = Number.parseFloat(getComputedStyle(toc).top);
            const sampleX = Math.min(
              window.innerWidth - 1,
              Math.max(0, targetRect.left + Math.min(targetRect.width / 2, 24)),
            );
            const sampleY = Math.min(
              window.innerHeight - 1,
              Math.max(0, targetRect.top + Math.min(targetRect.height / 2, 12)),
            );
            const topmost = document.elementFromPoint(sampleX, sampleY);
            return tocRect.left >= mainRect.right + 12 &&
              targetRect.left >= mainRect.left - 1 && targetRect.right <= mainRect.right + 1 &&
              targetRect.top >= (Number.isFinite(stickyTop) ? stickyTop : 0) - 1 &&
              targetRect.top < window.innerHeight &&
              topmost !== null && !toc.contains(topmost);
          }, targetId);
          await tocLink.focus();
          await page.keyboard.press('Enter');
          await page.waitForTimeout(500);
          if (!await isUnobscured()) return 'CLICK_TARGET_OBSCURED';
          // Force a document navigation before testing an initial hash. A same-document
          // page.goto() correctly returns null in Playwright and would be a false failure.
          await page.goto('about:blank');
          const directResponse = await page.goto(`${expectedUrl}${targetHash}`, {
            waitUntil: 'networkidle',
          });
          if (!directResponse || directResponse.status() !== 200) {
            return 'DIRECT_HASH_HTTP';
          }
          await page.waitForTimeout(500);
          if (!await isUnobscured()) return 'DIRECT_HASH_TARGET_OBSCURED';
          await page.evaluate(async () => {
            for (const image of document.images) {
              if (!image.complete) {
                image.scrollIntoView({ block: 'center', inline: 'nearest' });
                await Promise.race([
                  new Promise((resolve) => {
                    image.addEventListener('load', resolve, { once: true });
                    image.addEventListener('error', resolve, { once: true });
                  }),
                  new Promise((resolve) => setTimeout(resolve, 3000)),
                ]);
              }
            }
            scrollTo(0, 0);
          });
          return null;
        })();
      }

      let internalLinkFailure = false;
      if (surface.article && width === 390) {
        const links = await page.evaluate(() => [...document.querySelectorAll(
          'a[data-raos-link-placement="article_body"],'
            + 'a[data-raos-link-placement="related_navigation"],'
            + 'a[data-raos-link-placement="cluster_home"]',
        )].map((anchor) => ({
          clusterAnchor: anchor.getAttribute('data-raos-cluster-anchor'),
          href: anchor.href,
          placement: anchor.getAttribute('data-raos-link-placement'),
          target: anchor.getAttribute('data-raos-to-article-id'),
        })));
        const expected = [
          ['article_body', surface.contextual_article_id, ''],
          ...surface.related_article_ids.map((id) => ['related_navigation', id, '']),
          ['cluster_home', null, surface.cluster_anchor],
        ].map((row) => row.join('|')).sort();
        internalLinkFailure =
          new Set(links.map((link) => link.href)).size !== links.length ||
          links.map(
            (link) => `${link.placement}|${link.target || ''}|${link.clusterAnchor || ''}`,
          ).sort().join('\n') !== expected.join('\n');
        for (const link of links) {
          const target = parseLocalUrl(link.href);
          if (target === null) {
            internalLinkFailure = true;
            continue;
          }
          if (link.placement === 'cluster_home') {
            if (
              target.origin !== origin || target.pathname !== '/' || target.search ||
              target.hash !== `#${surface.cluster_anchor}` ||
              link.clusterAnchor !== surface.cluster_anchor || link.target !== null
            ) internalLinkFailure = true;
            continue;
          }
          if (target.origin !== origin || target.pathname !== expectedPathByArticleId[link.target] ||
            target.search || target.hash) internalLinkFailure = true;
          const readback = await page.request.get(link.href, { maxRedirects: 0 });
          if (readback.status() !== 200 || readback.url() !== link.href) internalLinkFailure = true;
        }
      }

      let homeLinkFailure = false;
      if (surface.kind === 'home' && width === 390) {
        const expectedClusters = rawClusters.map((cluster) => ({
          anchor: cluster.anchor,
          paths: cluster.article_ids.map((articleId) => expectedPathByArticleId[articleId]),
        }));
        homeLinkFailure = audit.homeClusters.length !== expectedClusters.length ||
          audit.homeClusters.some((cluster, index) => {
            const expected = expectedClusters[index];
            return !expected || cluster.anchor !== expected.anchor ||
              cluster.links.length !== expected.paths.length ||
              cluster.links.some((link, linkIndex) =>
                link.pathname !== expected.paths[linkIndex] ||
                parseLocalUrl(link.href) === null);
          });
      }

      let localLinkFailure = false;
      if (width === 390) {
        const localLinks = await page.evaluate((localOrigin) => {
          const unique = new Map();
          for (const anchor of document.querySelectorAll('a[href]')) {
            let target;
            try {
              target = new URL(anchor.href);
            } catch (error) {
              continue;
            }
            if (target.origin === localOrigin) unique.set(target.href, {
              hash: target.hash,
              href: target.href,
              pathname: target.pathname,
              search: target.search,
            });
          }
          return [...unique.values()];
        }, origin);
        const current = parseLocalUrl(page.url());
        if (current === null) localLinkFailure = true;
        for (const link of localLinks) {
          if (current && link.hash && link.pathname === current.pathname &&
            link.search === current.search) {
            const targetExists = await page.evaluate(
              (id) => document.getElementById(id) !== null,
              decodeURIComponent(link.hash.slice(1)),
            );
            if (!targetExists) localLinkFailure = true;
            continue;
          }
          const readback = await page.request.get(link.href, { maxRedirects: 0 });
          const final = parseLocalUrl(readback.url());
          if (
            readback.status() !== 200 ||
            final === null ||
            final.pathname !== link.pathname ||
            final.search !== link.search
          ) localLinkFailure = true;
        }
      }

      let zoomFailure = null;
      let zoomScreenshot = null;

      const expectsEmptyListing = [
        'EMPTY_QUERY', 'WHITESPACE_QUERY', 'NO_RESULTS', 'HOSTILE_QUERY_ESCAPED',
      ].includes(surface.expected_state);
      const listingFailure = ['search', 'archive'].includes(surface.kind) && (
        !audit.listingBodyClass || audit.fullPostContentCount !== 0 ||
        (expectsEmptyListing
          ? audit.emptyStateCount !== 1 || audit.listingCardCount !== 0
          : audit.emptyStateCount !== 0 || audit.listingCardCount < 1)
      );
      const notFoundFailure = surface.kind === 'not_found' &&
        (!audit.notFoundBodyClass || !head.title.includes('ページが見つかりません'));
      const tocFailure = surface.article && (
        audit.toc.count !== 1 || audit.toc.backCount < 1 || !audit.toc.firstTarget ||
        audit.toc.titleText !== 'この記事の目次' ||
        (width > 768
          ? !audit.toc.detailsOpen || !audit.toc.listVisible || audit.toc.summaryVisible ||
            !audit.toc.titleVisible
          : audit.toc.detailsOpen || audit.toc.listVisible || !audit.toc.summaryVisible ||
            audit.toc.titleVisible)
      );
      const boxInvalid = (box) => !Object.values(box).every(Number.isFinite) ||
        box.width <= 0 || box.height <= 0 || box.left < -0.5 ||
        box.right > audit.clientWidth + 0.5;
      const expectedColumns = width === 1440 ? 3 : width === 768 ? 2 : 1;
      const isLifecycleStatusRoute = surface.article &&
        surface.article_id === lifecycleStatusRouteArticleId;
      const incrementalArticle = surface.article ? validateIncrementalArticle({
        scope: checkedIncrementalScope, articleId: surface.article_id, audit,
      }) : { failed: false, selected: false, commerceStatus: 'NOT_AN_ARTICLE' };
      const incrementalExpected = checkedIncrementalScope?.articles.find(
        (row) => row.article_id === surface.article_id);
      const isPreservedArticle = Boolean(incrementalExpected && !incrementalArticle.selected);
      const requiresAffiliateCta = surface.article &&
        (incrementalExpected ? incrementalExpected.expected_ctas.length > 0 : !isLifecycleStatusRoute);
      const zeroProducts = audit.productIds.length === 0;
      const zeroCtas = audit.ctaBoxes.length === 0;
      const lifecycleProductCtaInvariantFailure = surface.article && (
        (surface.content_role === 'lifecycle_status_route') !== isLifecycleStatusRoute ||
        (incrementalExpected ? incrementalArticle.failed :
          zeroProducts !== isLifecycleStatusRoute || zeroCtas !== isLifecycleStatusRoute) ||
        audit.productProfileCount !== audit.productIds.length ||
        audit.productIds.some((productId) => productId === '') ||
        new Set(audit.productIds).size !== audit.productIds.length
      );
      const disclosureSemanticsFailure = surface.article && (
        audit.disclosure.count !== 1 ||
        !audit.disclosure.opacityVisible || !audit.disclosure.inViewport ||
        !audit.disclosure.unobscured || audit.disclosure.policyLinkCount !==
          (isPreservedArticle ? incrementalExpected.expected_disclosure_policy_link_count : 1) ||
        (isLifecycleStatusRoute
          ? audit.disclosure.ariaLabel !== '購入リンクについて' ||
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
      const articleFactsFailure = surface.article
        ? isPreservedArticle
          ? !exactMultiset(audit.articleFacts.contentRoleLabels,
              incrementalExpected.expected_article_facts.content_role_labels) ||
            !exactMultiset(audit.articleFacts.primaryQueryIntents,
              incrementalExpected.expected_article_facts.primary_query_intents)
          : audit.articleFacts.contentRoleLabels.length !== 1 ||
            audit.articleFacts.contentRoleLabels[0] !== surface.content_role_label ||
            audit.articleFacts.primaryQueryIntents.length !== 1 ||
            audit.articleFacts.primaryQueryIntents[0] !== surface.primary_query_intent
        : audit.articleFacts.contentRoleLabels.length !== 0 ||
          audit.articleFacts.primaryQueryIntents.length !== 0;
      const generalFailure =
        browserCookieCount !== 0 ||
        audit.lang !== 'ja' || audit.characterSet !== 'UTF-8' ||
        audit.bannerText !== 'LOCAL WORDPRESS PREVIEW — 本番表示ではありません' ||
        audit.h1Count !== 1 || audit.mainCount !== 1 || audit.scrollWidth > audit.clientWidth ||
        audit.h1LineCount > (width <= 390 ? 6 : 4) ||
        audit.missingAlt !== 0 || audit.unloadedImages !== 0 || audit.unlabeledControls !== 0 ||
        audit.hiddenLegacyImageResourceFailures !== 0 ||
        comparisonFocusabilityFailure ||
        audit.duplicateIds.length !== 0 || audit.brokenAriaReferences !== 0 ||
        audit.consentElementCount !== 0 || audit.cookieSettingsCount !== 0 ||
        audit.measurementConfigDefined || audit.measurementScriptCount !== 0 ||
        audit.measurementSessionKeyCount !== 0 || audit.jsonLdParseFailures !== 0 ||
        Object.values(audit.anchorSecurity).some((count) => count !== 0) ||
        !audit.reducedMotion.mediaMatches ||
        audit.reducedMotion.htmlScrollBehavior !== 'auto' ||
        audit.reducedMotion.animatedElementCount !== 0 ||
        audit.reducedMotion.smoothScrollElementCount !== 0 ||
        Object.values(audit.storageState).some((count) => count !== 0) ||
        audit.axeViolations.length !== 0 || audit.footerBackground !== 'rgb(23, 36, 63)' ||
        audit.footerDisplay !== 'grid' || audit.footerColumnCount !== expectedColumns ||
        audit.footerBoxes.length !== 2 || audit.footerBoxes.some(boxInvalid) ||
        audit.footerLinkBoxes.length === 0 || audit.footerLinkBoxes.some(
          (box) => boxInvalid(box) || box.height < 44,
        ) ||
        articleFactsFailure ||
        (surface.article && (
          audit.editorialRootCount !== 1 ||
          audit.heroNotice.count !== 1 || !audit.heroNotice.visible ||
          audit.heroNotice.text !== '比較イメージ／商品写真ではありません' ||
          (requiresAffiliateCta
            ? audit.ctaBoxes.length === 0 ||
              audit.ctaBoxes.some((box) => boxInvalid(box) || box.height < 44) ||
              !audit.disclosure.beforeFirstCtaDom ||
              !audit.disclosure.beforeFirstCtaVisual
            : audit.ctaBoxes.length !== 0 || audit.disclosure.beforeFirstCtaDom ||
              audit.disclosure.beforeFirstCtaVisual) ||
          audit.imageLoadingInvalid !== 0 || disclosureSemanticsFailure
        )) ||
        (!surface.article && audit.disclosure.count !== 0) ||
        surface.article !== audit.editorialBodyClass ||
        (surface.kind === 'policy') !== audit.policyBodyClass;

      if (
        generalFailure || headFailure || seoHeadAuditFailed || robotsFailure || semanticGraphFailure ||
        securityHeaderFailure.length !== 0 || disclosureKeyboardFailure || focusFlowFailure ||
        navigationFailure || desktopTocPositionFailure || internalLinkFailure ||
        homeLinkFailure || localLinkFailure || listingFailure || missingUiText.length !== 0 ||
        lifecycleProductCtaInvariantFailure || notFoundFailure || routeFailure ||
        skipLinkFailure || tocFailure
      ) {
        throw new Error(
          `RAOS_WORDPRESS_LOCAL_PREVIEW_AUDIT_FAILED_${surface.name}_${width}:` +
          JSON.stringify({ audit, browserCookieCount, desktopTocPositionFailure,
            articleFactsFailure, disclosureSemanticsFailure,
            disclosureKeyboardFailure, focusFlowFailure, generalFailure, headFailure,
            homeLinkFailure, internalLinkFailure, listingFailure, localLinkFailure,
            missingUiText, navigationFailure, notFoundFailure, robotsFailure, routeFailure,
            semanticGraphFailure, seoHeadAudit, incrementalArticle,
            securityHeaderFailure, skipLinkFailure, tocFailure }),
        );
      }
      // Interaction checks intentionally mutate focus, hash, disclosure and TOC state.
      // Capture evidence from a fresh document so baseline screenshots never inherit it.
      await page.goto('about:blank');
      expectedNotFoundConsoleMessages = surface.expectedStatus === 404 ? 1 : 0;
      const baselineResponse = await page.goto(expectedUrl, { waitUntil: 'networkidle' });
      if (!baselineResponse || baselineResponse.status() !== surface.expectedStatus) {
        throw new Error(`RAOS_WORDPRESS_LOCAL_PREVIEW_BASELINE_HTTP_FAILED_${surface.name}`);
      }
      const cleanBaselineState = await page.evaluate(async ({ article, desktop, home }) => {
        const afterPaint = () => new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)));
        for (const image of document.images) {
          if (!image.complete) {
            image.scrollIntoView({ block: 'center', inline: 'nearest' });
            await Promise.race([
              new Promise((resolve) => {
                image.addEventListener('load', resolve, { once: true });
                image.addEventListener('error', resolve, { once: true });
              }),
              new Promise((resolve) => setTimeout(resolve, 3000)),
            ]);
          }
        }
        if (home) {
          for (const section of document.querySelectorAll('.raos-home-v2 > *')) {
            section.scrollIntoView({ behavior: 'auto', block: 'start' });
            await afterPaint();
          }
        }
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
        scrollTo({ behavior: 'auto', left: 0, top: 0 });
        await afterPaint();
        const details = document.querySelector('.raos-article-toc details');
        return {
          activeElementIsBody: document.activeElement === document.body,
          captureStyleCount: document.querySelectorAll(
            '#raos-audit-capture-only-content-visibility',
          ).length,
          hash: location.hash,
          navigationOpenCount: document.querySelectorAll(
            '.wp-block-navigation__responsive-container.is-menu-open',
          ).length,
          rootInlineFontSize: document.documentElement.style.fontSize,
          scrollY,
          searchExpandedCount: document.querySelectorAll(
            '.raos-site-header .raos-header-search:not(.wp-block-search__searchfield-hidden)',
          ).length,
          tocOpen: details instanceof HTMLDetailsElement ? details.open : null,
          tocStateExpected: article ? details instanceof HTMLDetailsElement && details.open === desktop
            : details === null,
        };
      }, { article: surface.article, desktop: width >= 1025, home: surface.kind === 'home' });
      if (
        !cleanBaselineState.activeElementIsBody || cleanBaselineState.captureStyleCount !== 0 ||
        cleanBaselineState.hash !== '' || cleanBaselineState.navigationOpenCount !== 0 ||
        cleanBaselineState.rootInlineFontSize !== '' || cleanBaselineState.scrollY !== 0 ||
        cleanBaselineState.searchExpandedCount !== 0 || !cleanBaselineState.tocStateExpected
      ) {
        throw new Error(
          `RAOS_WORDPRESS_LOCAL_PREVIEW_BASELINE_STATE_FAILED_${surface.name}_${width}:` +
          JSON.stringify(cleanBaselineState),
        );
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
          throw new Error(`RAOS_WORDPRESS_HOME_CAPTURE_MODE_FAILED_${width}`);
        }
      }
      const screenshot = `${artifactDirectory}/local-preview-${surface.name}-${width}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      if (width === 390) {
        await page.evaluate(() => {
          document.documentElement.style.setProperty('font-size', '200%', 'important');
        });
        await page.evaluate(
          () => new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        const zoomAudit = await page.evaluate(() => {
          const isVisible = (element) => {
            if (!(element instanceof HTMLElement)) return false;
            if (element.matches('.screen-reader-text:not(:focus)')) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0;
          };
          const clientWidth = document.documentElement.clientWidth;
          const interactiveOutOfBounds = [...document.querySelectorAll(
            'a[href],button,input:not([type="hidden"]),select,textarea,summary',
          )].filter((element) => {
            if (!isVisible(element)) return false;
            const rect = element.getBoundingClientRect();
            return rect.left < -0.5 || rect.right > clientWidth + 0.5;
          }).length;
          const clippedTextCount = [...document.querySelectorAll(
            'h1,h2,h3,p,li,dt,dd,label,summary,button',
          )].filter((element) => {
            if (!isVisible(element)) return false;
            const style = getComputedStyle(element);
            const clipsX = ['clip', 'hidden'].includes(style.overflowX) &&
              element.scrollWidth > element.clientWidth + 1;
            const clipsY = ['clip', 'hidden'].includes(style.overflowY) &&
              element.scrollHeight > element.clientHeight + 1;
            return clipsX || clipsY;
          }).length;
          const wordmark = document.querySelector('.raos-site-header .raos-wordmark a');
          const wordmarkRange = wordmark ? document.createRange() : null;
          if (wordmarkRange) wordmarkRange.selectNodeContents(wordmark);
          const wordmarkLineCount = wordmarkRange
            ? new Set([...wordmarkRange.getClientRects()].map((rect) => Math.round(rect.top))).size
            : 0;
          return {
            clientWidth,
            clippedTextCount,
            h1Count: document.querySelectorAll('h1').length,
            interactiveOutOfBounds,
            mainCount: document.querySelectorAll('main').length,
            rootFontSizePx: Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
            scrollWidth: document.documentElement.scrollWidth,
            wordmarkLineCount,
          };
        });
        if (
          !Number.isFinite(zoomAudit.rootFontSizePx) || zoomAudit.rootFontSizePx < 31.5 ||
          zoomAudit.h1Count !== 1 || zoomAudit.mainCount !== 1 ||
          zoomAudit.scrollWidth > zoomAudit.clientWidth ||
          zoomAudit.interactiveOutOfBounds !== 0 || zoomAudit.clippedTextCount !== 0 ||
          (surface.kind === 'home' && (
            zoomAudit.wordmarkLineCount < 1 || zoomAudit.wordmarkLineCount > 2
          ))
        ) {
          zoomFailure = zoomAudit;
        }
        zoomScreenshot = `${artifactDirectory}/local-preview-${surface.name}-zoom200.png`;
        await page.screenshot({ path: zoomScreenshot, fullPage: true });
        await page.evaluate(() => {
          document.documentElement.style.removeProperty('font-size');
        });
        if (zoomFailure) {
          throw new Error(
            `RAOS_WORDPRESS_LOCAL_PREVIEW_ZOOM_FAILED_${surface.name}:` +
            JSON.stringify(zoomFailure),
          );
        }
      }
      results.push({
        auditResultSchema: 'RAOS_WORDPRESS_LOCAL_BROWSER_RESULT_V1',
        localPath: surface.local_path,
        productionPath: surface.production_path || null,
        mandatoryCounts: {
          actionableAxeViolations: audit.axeViolations.length,
          brokenImages: audit.unloadedImages,
          missingAlt: audit.missingAlt,
          unlabeledControls: audit.unlabeledControls,
          brokenAriaReferences: audit.brokenAriaReferences,
          horizontalOverflow: Math.max(0, audit.scrollWidth - audit.clientWidth),
          browserCookies: browserCookieCount,
          unhandledRuntimeErrors: runtimeErrors.length,
          failedResources: resourceErrors.length,
        },
        canonicalPolicy: surface.publicCore ? 'EXACT_LOCAL_PUBLIC_CORE' : surface.expected_canonical,
        captureOnlyEvidenceMode,
        imageLoadingEvidence: {
          hiddenLegacyLazyNotRequested: audit.hiddenLegacyLazyImageCount,
          hiddenLegacyImageResourceFailures: audit.hiddenLegacyImageResourceFailures,
        },
        httpStatus: response.status(),
        profileSemantics: {
          publicationProfile,
          linkMode,
          incrementalCommerceStatus: incrementalArticle.commerceStatus,
          legacyMediaDisplayProjection: incrementalExpected?.display_projection || null,
          preparationBindingSha256: checkedIncrementalScope?.preparation_binding_sha256 || null,
          localProfileId: robotsProfile.local_profile_id,
          localObservedPolicy: robotsProfile.local_observed_policy,
          productionRobotsEvidence: robotsProfile.production_robots_evidence,
        },
        screenshot,
        routeClass: surface.route_class || 'PUBLIC_CORE',
        realScrollEvidence,
        surface: surface.name,
        width,
        zoomScreenshot,
      });
    }
  }
  if (runtimeErrors.length !== 0 || resourceErrors.length !== 0) {
    throw new Error(
      `RAOS_WORDPRESS_LOCAL_PREVIEW_RUNTIME_ERROR:${JSON.stringify({resourceErrors, runtimeErrors})}`,
    );
  }
  const requestSummary = [...requestCounts.entries()].sort(([left], [right]) =>
    left.localeCompare(right)).map(([signature, count]) => ({ count, signature }));
  if (externalRequestCount !== 0) {
    throw new Error(`RAOS_WORDPRESS_LOCAL_PREVIEW_EXTERNAL_REQUEST:${externalRequestCount}`);
  }
  if (forbiddenRequests.length !== 0) {
    throw new Error(
      `RAOS_WORDPRESS_LOCAL_PREVIEW_REQUEST_METHOD_OR_TYPE_FAILED:${JSON.stringify({
        forbiddenRequests, requestSummary,
      })}`,
    );
  }
  if (measurementRequestCount !== 0) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_MEASUREMENT_DEFAULT_OFF_FAILED');
  }
  if (results.length !== surfaces.length * widths.length) {
    throw new Error('RAOS_WORDPRESS_LOCAL_PREVIEW_SCREEN_COUNT_INVALID');
  }
  return results;
  };

  factory.validateSeoHead = validateSeoHead;
  factory.validateIncrementalScope = validateIncrementalScope;
  factory.validateIncrementalArticle = validateIncrementalArticle;
  factory.inspectImageLoading = inspectImageLoading;
  factory.classifyImageLoading = classifyImageLoading;
  factory.inspectHiddenLegacyImageResources = inspectHiddenLegacyImageResources;
  return factory;
})()
