(() => {
  'use strict';
  if (window.raosPurchaseAnalyticsInstalled === true) return;
  window.raosPurchaseAnalyticsInstalled = true;
  const keys = ['article_id', 'product_id', 'seller_id', 'offer_id', 'cta_id', 'placement', 'snapshot_id'];
  const placements = ['top_summary', 'comparison_table', 'product_card', 'final_summary'];
  const seen = new WeakSet();
  function collect(event) {
    try {
      if ((event.type === 'click' && event.button !== 0) ||
          (event.type === 'auxclick' && event.button !== 1) || seen.has(event)) return;
      seen.add(event);
      const configNode = document.getElementById('raos-purchase-ga4-config');
      if (!configNode || configNode.type !== 'application/json') return;
      const config = JSON.parse(configNode.textContent);
      if (config.profile !== 'purchase-support-v1' || config.enabled !== true ||
          typeof config.debug_mode !== 'boolean' || !Array.isArray(config.bindings)) return;
      if (event.isTrusted !== true && config.debug_mode !== true) return;
      if (typeof window.gtag !== 'function' || window.gtag.raosConsentGate !== true ||
          typeof window.getCkyConsent !== 'function' || typeof window.wp_has_consent !== 'function') return;
      const consent = window.getCkyConsent();
      if (!consent || consent.isUserActionCompleted !== true || !consent.categories ||
          consent.categories.analytics !== true || window.wp_has_consent('statistics') !== true ||
          !window._googlesitekitConsents || window._googlesitekitConsents.analytics_storage !== 'granted') return;
      if (window.localStorage.getItem('raos_purchase_ga4_opt_out') === '1') return;
      const anchor = event.target && typeof event.target.closest === 'function'
        ? event.target.closest('a') : null;
      const wrapper = anchor && anchor.closest('[data-raos-cta-type="offer"]');
      const root = wrapper && wrapper.closest('[data-raos-purchase-support="v1"]');
      if (!root) return;
      const params = Object.fromEntries(keys.map(key => [key, wrapper.getAttribute(`data-raos-${key.replaceAll('_', '-')}`)]));
      if (!keys.every(key => typeof params[key] === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/.test(params[key])) ||
          !placements.includes(params.placement) ||
          root.getAttribute('data-raos-article-id') !== params.article_id ||
          root.getAttribute('data-raos-snapshot-id') !== params.snapshot_id) return;
      const binding = config.bindings.find(binding => binding && [8, 10].includes(Object.keys(binding).length) &&
          keys.every(key => binding[key] === params[key]) && binding.href === anchor.href);
      if (!binding) return;
      if (Object.keys(binding).length === 10) {
        if (!['affiliate_purchase', 'merchant_purchase'].includes(binding.link_purpose) ||
            !['true', 'false'].includes(binding.affiliate) ||
            (binding.link_purpose === 'affiliate_purchase') !== (binding.affiliate === 'true') ||
            wrapper.getAttribute('data-raos-link-purpose') !== binding.link_purpose ||
            wrapper.getAttribute('data-raos-affiliate') !== binding.affiliate) return;
        params.link_purpose = binding.link_purpose;
        params.affiliate = binding.affiliate === 'true';
      } else {
        // Previously approved eight-field purchase bindings retain their own snapshot.
        params.affiliate = /^https:\/\/hb\.afl\.rakuten\.co\.jp\//.test(binding.href);
        params.link_purpose = params.affiliate ? 'affiliate_purchase' : 'merchant_purchase';
      }
      const gate = document.getElementById('google_gtagjs-js');
      const measurementId = gate && gate.getAttribute('data-raos-measurement-id');
      if (!measurementId || !/^(?:G|GT)-[A-Z0-9]{6,20}$/.test(measurementId) || window[`ga-disable-${measurementId}`] === true) return;
      // gtag drops events addressed to a Google tag ID (GT-); the owned config is the only destination,
      // so route by send_to only for a GA4 measurement ID (G-).
      const routing = /^GT-/.test(measurementId) ? {} : {send_to: measurementId};
      window.gtag('event', 'offer_click', {...params, ...routing, debug_mode: config.debug_mode});
    } catch (_error) {
      // Consent/storage/provider failures never interrupt the shopper's navigation.
    }
  }
  document.addEventListener('click', collect);
  document.addEventListener('auxclick', collect);
})();
