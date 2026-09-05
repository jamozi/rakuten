(function () {
  'use strict';

  var config = window.RAOS_MEASUREMENT_CONFIG_V1;
  if (!config || config.enabled !== true || config.schema !== 'RAOSMeasurementClientConfigV1') {
    return;
  }
  var configKeys = ['article', 'disclosureVersion', 'enabled', 'endpoint', 'schema'];
  if (Object.keys(config).sort().join('|') !== configKeys.join('|') ||
      typeof config.endpoint !== 'string' ||
      typeof config.disclosureVersion !== 'string' ||
      !/^privacy-[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(config.disclosureVersion) ||
      typeof config.article !== 'object' || config.article === null) {
    return;
  }
  var endpoint;
  try {
    endpoint = new URL(config.endpoint);
  } catch (error) {
    return;
  }
  if (endpoint.protocol !== 'https:' ||
      endpoint.origin !== window.location.origin ||
      endpoint.pathname !== '/wp-json/raos/v1/events' ||
      endpoint.username !== '' || endpoint.password !== '' ||
      endpoint.search !== '' || endpoint.hash !== '' ||
      endpoint.href !== config.endpoint) {
    return;
  }
  var measurementEndpoint = endpoint.href;
  var article = config.article;
  var allowedKeys = [
    'articleCode',
    'articleId',
    'categoryId',
    'ctaBindings',
    'relatedArticleIds',
    'snapshotId'
  ];
  if (Object.keys(article).sort().join('|') !== allowedKeys.sort().join('|')) {
    return;
  }

  var storagePrefix = 'raos_measurement_v1:';
  var sessionKey = storagePrefix + 'session';
  var inMemoryOnce = new Set();
  var observers = [];
  var active = false;
  var interactionsInstalled = false;

  function consentGranted() {
    if (typeof window.getCkyConsent !== 'function' || typeof window.wp_has_consent !== 'function') {
      return false;
    }
    var cookieYes = window.getCkyConsent();
    return !!(
      cookieYes &&
      cookieYes.isUserActionCompleted === true &&
      cookieYes.categories &&
      cookieYes.categories.analytics === true &&
      window.wp_has_consent('statistics') === true &&
      window._googlesitekitConsents &&
      window._googlesitekitConsents.analytics_storage === 'granted'
    );
  }

  function uuid7() {
    if (!window.crypto || typeof window.crypto.getRandomValues !== 'function') {
      return null;
    }
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    var timestamp = Date.now();
    for (var index = 5; index >= 0; index -= 1) {
      bytes[index] = timestamp & 255;
      timestamp = Math.floor(timestamp / 256);
    }
    bytes[6] = (bytes[6] & 15) | 112;
    bytes[8] = (bytes[8] & 63) | 128;
    var hex = Array.from(bytes, function (value) {
      return value.toString(16).padStart(2, '0');
    }).join('');
    return [
      hex.slice(0, 8),
      hex.slice(8, 12),
      hex.slice(12, 16),
      hex.slice(16, 20),
      hex.slice(20)
    ].join('-');
  }

  function sessionId() {
    if (!consentGranted()) {
      return null;
    }
    try {
      var existing = window.sessionStorage.getItem(sessionKey);
      if (/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(existing || '')) {
        return existing;
      }
      var created = uuid7();
      if (created !== null) {
        window.sessionStorage.setItem(sessionKey, created);
      }
      return created;
    } catch (error) {
      return uuid7();
    }
  }

  function markOnce(key) {
    if (!consentGranted()) {
      return false;
    }
    var storageKey = storagePrefix + article.snapshotId + ':' + key;
    try {
      if (window.sessionStorage.getItem(storageKey) === '1') {
        return false;
      }
      window.sessionStorage.setItem(storageKey, '1');
      return true;
    } catch (error) {
      if (inMemoryOnce.has(storageKey)) {
        return false;
      }
      inMemoryOnce.add(storageKey);
      return true;
    }
  }

  function clearMeasurementSession() {
    active = false;
    observers.forEach(function (observer) {
      observer.disconnect();
    });
    observers = [];
    inMemoryOnce.clear();
    try {
      for (var index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
        var key = window.sessionStorage.key(index);
        if (typeof key === 'string' && key.indexOf(storagePrefix) === 0) {
          window.sessionStorage.removeItem(key);
        }
      }
    } catch (error) {
      // A denied storage API is equivalent to an already-cleared session.
    }
  }

  function classifyReferrer() {
    if (!document.referrer) {
      return 'direct';
    }
    try {
      var referrer = new URL(document.referrer);
      if (referrer.origin === window.location.origin) {
        return 'internal';
      }
      if (/(?:google|bing|yahoo|duckduckgo)\./i.test(referrer.hostname)) {
        return 'search';
      }
      if (/(?:x|twitter|facebook|instagram|threads|tiktok)\.com$/i.test(referrer.hostname)) {
        return 'social';
      }
    } catch (error) {
      return 'other';
    }
    return 'other';
  }

  function ga4(event) {
    if (!consentGranted() || typeof window.gtag !== 'function') {
      return;
    }
    var parameters = Object.assign({}, event.dimensions, {
      article_id: event.article_id,
      event_id: event.event_id,
      snapshot_id: event.snapshot_id
    });
    window.gtag('event', event.event_name, parameters);
  }

  function deliver(event) {
    var serialized;
    try {
      serialized = JSON.stringify(event);
    } catch (error) {
      return;
    }
    if (serialized.length > 4096 || !consentGranted()) {
      return;
    }
    if (event.event_name === 'affiliate_click' && event.dimensions.beacon_transport === 'sendBeacon') {
      try {
        var blob = new Blob([serialized], { type: 'application/json' });
        window.navigator.sendBeacon(measurementEndpoint, blob);
      } catch (error) {
        // Native outbound navigation remains independent of measurement.
      }
    } else {
      try {
        window.fetch(measurementEndpoint, {
          body: serialized,
          cache: 'no-store',
          credentials: 'omit',
          headers: { 'Content-Type': 'application/json' },
          keepalive: true,
          method: 'POST',
          mode: 'same-origin',
          redirect: 'error',
          referrerPolicy: 'no-referrer'
        }).catch(function () {});
      } catch (error) {
        // Collection failure is deliberately swallowed.
      }
    }
    ga4(event);
  }

  function emit(eventName, dimensions) {
    if (!consentGranted()) {
      return;
    }
    var eventId = uuid7();
    var anonymousSessionId = sessionId();
    if (eventId === null || anonymousSessionId === null) {
      return;
    }
    deliver({
      schema_version: '1.0',
      event_id: eventId,
      event_name: eventName,
      occurred_at: new Date().toISOString(),
      anonymous_session_id: anonymousSessionId,
      article_id: article.articleId,
      snapshot_id: article.snapshotId,
      dimensions: dimensions
    });
  }

  function bindingFor(element, forcedPlacement) {
    if (!element || typeof element.getAttribute !== 'function') {
      return null;
    }
    var productId = element.getAttribute('data-raos-product-id');
    var placement = forcedPlacement || element.getAttribute('data-raos-placement');
    if (!productId || !placement) {
      return null;
    }
    return article.ctaBindings.find(function (binding) {
      return binding.product_id === productId && binding.placement === placement;
    }) || null;
  }

  function ctaDimensions(binding) {
    return {
      product_id: binding.product_id,
      cta_id: binding.cta_id,
      offer_id: binding.offer_id,
      placement: binding.placement
    };
  }

  function observeOnce(elements, keyFor, callback) {
    if (!('IntersectionObserver' in window)) {
      return;
    }
    var observer = new window.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
          var key = keyFor(entry.target);
          if (key && markOnce(key)) {
            callback(entry.target);
          }
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: [0.5] });
    elements.forEach(function (element) {
      observer.observe(element);
    });
    observers.push(observer);
  }

  function installObservers() {
    var ctas = Array.from(document.querySelectorAll('a.raos-cta.rakuten-cta[data-raos-product-id][data-raos-placement]'))
      .filter(function (element) { return bindingFor(element, null) !== null; });
    observeOnce(
      ctas,
      function (element) {
        var binding = bindingFor(element, null);
        return binding ? 'cta-impression:' + binding.cta_id : null;
      },
      function (element) {
        var binding = bindingFor(element, null);
        if (binding) {
          emit('affiliate_cta_impression', Object.assign(ctaDimensions(binding), {
            visibility_threshold: 0.5
          }));
        }
      }
    );

    var productCards = Array.from(document.querySelectorAll('.raos-product-card[data-raos-product-id], .product-profile[data-raos-product-id]'))
      .filter(function (element) { return bindingFor(element, 'product_card') !== null; });
    observeOnce(
      productCards,
      function (element) {
        var binding = bindingFor(element, 'product_card');
        return binding ? 'product-card:' + binding.product_id : null;
      },
      function (element) {
        var binding = bindingFor(element, 'product_card');
        if (binding) {
          emit('product_card_view', ctaDimensions(binding));
          if (markOnce('qualified-decision')) {
            emit('qualified_decision_engagement', {
              component_type: 'product_card',
              engagement_kind: 'view_50_percent'
            });
          }
        }
      }
    );

    var comparisons = Array.from(document.querySelectorAll('.raos-comparison'));
    observeOnce(
      comparisons,
      function () { return 'comparison-view'; },
      function () {
        if (markOnce('qualified-decision')) {
          emit('qualified_decision_engagement', {
            component_type: 'comparison_table',
            engagement_kind: 'view_50_percent'
          });
        }
      }
    );

    var disclosures = Array.from(document.querySelectorAll('.disclosure'));
    observeOnce(
      disclosures,
      function () { return 'disclosure-view'; },
      function () {
        emit('disclosure_view', { disclosure_version: config.disclosureVersion });
      }
    );
  }

  function installInteractions() {
    if (interactionsInstalled) {
      return;
    }
    interactionsInstalled = true;
    document.addEventListener('click', function (event) {
      var target = event.target instanceof Element ? event.target.closest('a') : null;
      if (!target || !consentGranted()) {
        return;
      }
      if (target.matches('.raos-cta.rakuten-cta[data-raos-product-id][data-raos-placement]')) {
        var binding = bindingFor(target, null);
        if (binding) {
          var transport = typeof window.navigator.sendBeacon === 'function'
            ? 'sendBeacon'
            : 'fetch_keepalive';
          emit('affiliate_click', Object.assign(ctaDimensions(binding), {
            beacon_transport: transport,
            consent_state: 'GRANTED'
          }));
        }
      }
      var toArticleId = target.getAttribute('data-raos-to-article-id');
      var linkPlacement = target.getAttribute('data-raos-link-placement');
      if (article.relatedArticleIds.indexOf(toArticleId) !== -1 &&
          ['article_body', 'related_navigation'].indexOf(linkPlacement) !== -1) {
        emit('internal_link_click', {
          to_article_id: toArticleId,
          placement: linkPlacement
        });
      }
    }, { capture: true, passive: true });

    Array.from(document.querySelectorAll('.raos-comparison')).forEach(function (comparison) {
      comparison.addEventListener('focusin', function () {
        if (markOnce('comparison-focus')) {
          emit('comparison_interaction', {
            interaction: 'focus',
            axis_code: 'comparison_table'
          });
        }
      }, { passive: true });
      comparison.addEventListener('scroll', function () {
        if (comparison.scrollLeft > 16 && markOnce('comparison-horizontal-scroll')) {
          emit('comparison_interaction', {
            interaction: 'horizontal_scroll',
            axis_code: 'comparison_table'
          });
        }
      }, { passive: true });
    });
  }

  function activate() {
    if (!consentGranted() || active) {
      return;
    }
    active = true;
    if (markOnce('article-view')) {
      emit('article_view', {
        category_id: article.categoryId,
        referrer_class: classifyReferrer(),
        consent_state: 'GRANTED'
      });
    }
    installObservers();
    installInteractions();
  }

  function reconcileConsent() {
    if (consentGranted()) {
      activate();
    } else {
      clearMeasurementSession();
    }
  }

  document.addEventListener('wp_consent_type_defined', reconcileConsent);
  document.addEventListener('wp_listen_for_consent_change', reconcileConsent);
  document.addEventListener('cookieyes_consent_update', reconcileConsent);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', reconcileConsent, { once: true });
  } else {
    reconcileConsent();
  }
})();
