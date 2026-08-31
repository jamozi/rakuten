(() => {
  'use strict';

  const gateId = 'google_gtagjs-js';
  const analyticsCookiePattern = /^_ga(?:_|$)/;
  let activated = false;
  let activeLoader = null;
  let activeMeasurementId = null;
  let revocationReloadRequested = false;

  function consentIsGranted() {
    if (
      typeof window.getCkyConsent !== 'function' ||
      typeof window.wp_has_consent !== 'function'
    ) {
      return false;
    }
    const cookieYes = window.getCkyConsent();
    return Boolean(
      cookieYes &&
        cookieYes.isUserActionCompleted === true &&
        cookieYes.categories &&
        cookieYes.categories.analytics === true &&
        window.wp_has_consent('statistics') === true &&
        window._googlesitekitConsents &&
        window._googlesitekitConsents.analytics_storage === 'granted'
    );
  }

  function cookieDomains() {
    const hostname = String(window.location.hostname || '').toLowerCase();
    const labels = hostname.split('.').filter(Boolean);
    const domains = [''];
    if (labels.length >= 2) {
      domains.push(hostname, `.${hostname}`);
      for (let index = 1; index < labels.length - 1; index += 1) {
        domains.push(`.${labels.slice(index).join('.')}`);
      }
    }
    return [...new Set(domains)];
  }

  function clearAnalyticsCookies() {
    const names = String(document.cookie || '')
      .split(';')
      .map((entry) => entry.split('=', 1)[0].trim())
      .filter((name) => analyticsCookiePattern.test(name));
    for (const name of new Set(names)) {
      for (const domain of cookieDomains()) {
        const domainAttribute = domain ? `; Domain=${domain}` : '';
        document.cookie =
          `${name}=; Path=/; Max-Age=0; ` +
          `Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax${domainAttribute}`;
      }
    }
  }

  function readGateConfiguration() {
    const gate = document.getElementById(gateId);
    if (
      !gate ||
      gate.tagName !== 'SCRIPT' ||
      gate.type !== 'application/json' ||
      gate.getAttribute('data-raos-consent-gate') !== 'statistics'
    ) {
      return null;
    }
    const measurementId = gate.getAttribute('data-raos-measurement-id') || '';
    const source = gate.getAttribute('data-raos-source') || '';
    if (!/^G-[A-Z0-9]{6,20}$/.test(measurementId)) {
      return null;
    }
    let parsed;
    try {
      parsed = new URL(source);
    } catch (_error) {
      return null;
    }
    if (
      parsed.protocol !== 'https:' ||
      parsed.hostname !== 'www.googletagmanager.com' ||
      parsed.port !== '' ||
      parsed.username !== '' ||
      parsed.password !== '' ||
      parsed.pathname !== '/gtag/js' ||
      parsed.hash !== '' ||
      parsed.search !== `?id=${measurementId}`
    ) {
      return null;
    }
    return { gate, measurementId, source: parsed.href };
  }

  function activate() {
    if (activated) {
      return true;
    }
    if (!consentIsGranted()) {
      return false;
    }
    const configuration = readGateConfiguration();
    if (!configuration) {
      return false;
    }
    if (typeof window.gtag !== 'undefined') {
      window[`ga-disable-${configuration.measurementId}`] = true;
      return false;
    }
    // Never execute commands queued by an unowned script before consent.
    window.dataLayer = [];
    const ownedGtag = function () {
      window.dataLayer.push(arguments);
    };
    Object.defineProperty(ownedGtag, 'raosConsentGate', {
      value: true,
      writable: false,
    });
    window.gtag = ownedGtag;
    window.gtag('consent', 'update', {
      ad_personalization: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      analytics_storage: 'granted',
    });
    window.gtag('js', new Date());
    window.gtag('config', configuration.measurementId, {
      allow_ad_personalization_signals: false,
      allow_google_signals: false,
      cookie_expires: 63072000,
      cookie_update: true,
      send_page_view: true,
    });
    const loader = document.createElement('script');
    loader.id = gateId;
    loader.async = true;
    loader.dataset.cookieyes = 'cookieyes-analytics';
    loader.dataset.raosConsentActivated = 'statistics';
    loader.src = configuration.source;
    activated = true;
    activeLoader = loader;
    activeMeasurementId = configuration.measurementId;
    configuration.gate.replaceWith(loader);
    return true;
  }

  function deactivate() {
    if (!activated || revocationReloadRequested) {
      return false;
    }
    if (activeMeasurementId) {
      window[`ga-disable-${activeMeasurementId}`] = true;
    }
    if (
      typeof window.gtag === 'function' &&
      window.gtag.raosConsentGate === true
    ) {
      window.gtag('consent', 'update', {
        ad_personalization: 'denied',
        ad_storage: 'denied',
        ad_user_data: 'denied',
        analytics_storage: 'denied',
      });
    }
    if (activeLoader && typeof activeLoader.remove === 'function') {
      activeLoader.remove();
    }
    revocationReloadRequested = true;
    return true;
  }

  function synchronizeConsent() {
    if (consentIsGranted()) {
      if (activate()) {
        return;
      }
    }
    const shouldReload = deactivate();
    clearAnalyticsCookies();
    if (
      shouldReload &&
      typeof window.location.reload === 'function'
    ) {
      window.location.reload();
    }
  }

  for (const eventName of [
    'wp_consent_type_defined',
    'wp_listen_for_consent_change',
    'cookieyes_consent_update',
  ]) {
    document.addEventListener(eventName, synchronizeConsent);
  }
  if (document.readyState === 'complete') {
    synchronizeConsent();
  } else {
    window.addEventListener('load', synchronizeConsent, { once: true });
  }
})();
