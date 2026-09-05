import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const sourcePath = process.argv[2];
assert.ok(sourcePath, 'measurement client path is required');
const source = fs.readFileSync(sourcePath, 'utf8');

class FakeElement {
  constructor(attributes = {}, kind = 'generic') {
    this.attributes = attributes;
    this.kind = kind;
    this.listeners = new Map();
    this.scrollLeft = 0;
  }

  addEventListener(name, callback) {
    const listeners = this.listeners.get(name) || [];
    listeners.push(callback);
    this.listeners.set(name, listeners);
  }

  dispatch(name) {
    for (const callback of this.listeners.get(name) || []) {
      callback({ target: this });
    }
  }

  closest(selector) {
    return selector === 'a' && this.kind === 'cta' ? this : null;
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name]
      : null;
  }

  matches(selector) {
    return this.kind === 'cta' && selector.startsWith('.raos-cta.rakuten-cta');
  }
}

class FakeBlob {
  constructor(parts, options) {
    this.parts = parts;
    this.type = options.type;
  }
}

function createRuntime(initialConsent, delivery = {}, configOverride = {}) {
  let granted = initialConsent;
  let randomCounter = 1;
  const fetchEvents = [];
  const fetchEndpoints = [];
  const beaconEvents = [];
  const beaconEndpoints = [];
  const ga4Events = [];
  const documentListeners = new Map();
  const storage = new Map();
  const observers = [];
  const cta = new FakeElement({
    'data-raos-product-id': 'PRD-TEST-001',
    'data-raos-placement': 'product_card'
  }, 'cta');
  const card = new FakeElement({
    'data-raos-product-id': 'PRD-TEST-001'
  }, 'card');
  const comparison = new FakeElement({}, 'comparison');
  const disclosure = new FakeElement({}, 'disclosure');

  class FakeIntersectionObserver {
    constructor(callback, options) {
      this.callback = callback;
      this.options = options;
      this.targets = [];
      this.disconnected = false;
      observers.push(this);
    }

    observe(target) {
      this.targets.push(target);
    }

    unobserve(target) {
      this.targets = this.targets.filter((candidate) => candidate !== target);
    }

    disconnect() {
      this.disconnected = true;
      this.targets = [];
    }

    trigger(target, ratio) {
      this.callback([{
        target,
        isIntersecting: ratio > 0,
        intersectionRatio: ratio
      }]);
    }
  }

  const document = {
    readyState: 'complete',
    referrer: '',
    addEventListener(name, callback) {
      const listeners = documentListeners.get(name) || [];
      listeners.push(callback);
      documentListeners.set(name, listeners);
    },
    dispatch(name, event = {}) {
      for (const callback of documentListeners.get(name) || []) {
        callback(event);
      }
    },
    querySelectorAll(selector) {
      if (selector.startsWith('a.raos-cta.rakuten-cta')) {
        return [cta];
      }
      if (selector.startsWith('.raos-product-card')) {
        return [card];
      }
      if (selector === '.raos-comparison') {
        return [comparison];
      }
      if (selector === '.disclosure') {
        return [disclosure];
      }
      return [];
    }
  };
  const sessionStorage = {
    get length() {
      return storage.size;
    },
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    key(index) {
      return Array.from(storage.keys())[index] ?? null;
    },
    removeItem(key) {
      storage.delete(key);
    },
    setItem(key, value) {
      storage.set(key, String(value));
    }
  };
  const measurementConfig = {
      schema: 'RAOSMeasurementClientConfigV1',
      enabled: true,
      endpoint: 'https://kurashinoshirube.com/wp-json/raos/v1/events',
      disclosureVersion: 'privacy-2026-08-30',
      article: {
        articleCode: 'a01',
        articleId: 'article-001',
        categoryId: 'mobility',
        ctaBindings: [{
          cta_id: 'icta_a01_p01_card',
          offer_id: 'off-a01-p01',
          placement: 'product_card',
          product_id: 'PRD-TEST-001'
        }],
        relatedArticleIds: ['article-002'],
        snapshotId: 'snp-a01-0123456789ab'
      }
  };
  Object.assign(measurementConfig, configOverride);
  const window = {
    RAOS_MEASUREMENT_CONFIG_V1: measurementConfig,
    _googlesitekitConsents: {
      analytics_storage: granted ? 'granted' : 'denied'
    },
    crypto: {
      getRandomValues(bytes) {
        for (let index = 0; index < bytes.length; index += 1) {
          bytes[index] = (randomCounter + index) & 255;
        }
        randomCounter += 17;
        return bytes;
      }
    },
    fetch(endpoint, options) {
      if (delivery.fetchThrows === true) {
        throw new Error('simulated collection failure');
      }
      fetchEndpoints.push(endpoint);
      fetchEvents.push(JSON.parse(options.body));
      return Promise.resolve({ ok: true });
    },
    getCkyConsent() {
      return {
        isUserActionCompleted: granted,
        categories: { analytics: granted }
      };
    },
    gtag(...arguments_) {
      ga4Events.push(arguments_);
    },
    location: {
      href: 'https://kurashinoshirube.com/example/',
      origin: 'https://kurashinoshirube.com'
    },
    navigator: {
      sendBeacon(endpoint, blob) {
        if (delivery.beaconThrows === true) {
          throw new Error('simulated beacon failure');
        }
        assert.equal(blob.type, 'application/json');
        beaconEndpoints.push(endpoint);
        beaconEvents.push(JSON.parse(blob.parts.join('')));
        return true;
      }
    },
    sessionStorage,
    wp_has_consent(category) {
      return category === 'statistics' && granted;
    }
  };
  window.window = window;
  window.document = document;
  window.IntersectionObserver = FakeIntersectionObserver;

  const context = vm.createContext({
    Array,
    Blob: FakeBlob,
    Date,
    Element: FakeElement,
    IntersectionObserver: FakeIntersectionObserver,
    JSON,
    Map,
    Promise,
    Set,
    URL,
    Uint8Array,
    document,
    window
  });

  return {
    beaconEndpoints,
    beaconEvents,
    card,
    comparison,
    context,
    cta,
    disclosure,
    document,
    events() {
      return fetchEvents.concat(beaconEvents);
    },
    fetchEvents,
    fetchEndpoints,
    ga4Events,
    observers,
    run() {
      vm.runInContext(source, context, { filename: sourcePath });
    },
    setConsent(next) {
      granted = next;
      window._googlesitekitConsents.analytics_storage = next ? 'granted' : 'denied';
      document.dispatch('cookieyes_consent_update');
    },
    storage
  };
}

const denied = createRuntime(false);
denied.run();
assert.deepEqual(denied.events(), []);
assert.deepEqual(denied.ga4Events, []);
assert.equal(denied.storage.size, 0);
assert.equal(denied.observers.length, 0);

for (const endpoint of [
  'http://kurashinoshirube.com/wp-json/raos/v1/events',
  'https://kurashinoshirube.com.evil.example/wp-json/raos/v1/events',
  'https://kurashinoshirube.com/wp-json/raos/v1/events?leak=1',
  'https://user:pass@kurashinoshirube.com/wp-json/raos/v1/events',
  'javascript:alert(1)'
]) {
  const invalidEndpoint = createRuntime(true, {}, { endpoint });
  invalidEndpoint.run();
  assert.deepEqual(invalidEndpoint.events(), []);
  assert.deepEqual(invalidEndpoint.ga4Events, []);
  assert.equal(invalidEndpoint.storage.size, 0);
  assert.equal(invalidEndpoint.observers.length, 0);
}

const delayedGrant = createRuntime(false);
delayedGrant.run();
delayedGrant.setConsent(true);
assert.equal(delayedGrant.events().filter((event) => event.event_name === 'article_view').length, 1);
assert.equal(delayedGrant.ga4Events.length, 1);
assert.ok(delayedGrant.storage.size > 0);

const runtime = createRuntime(true);
runtime.run();
assert.equal(runtime.events().filter((event) => event.event_name === 'article_view').length, 1);
assert.equal(runtime.ga4Events.length, 1);
assert.ok(runtime.storage.size > 0);

const ctaObserver = runtime.observers.find((observer) => observer.targets.includes(runtime.cta));
assert.ok(ctaObserver);
ctaObserver.trigger(runtime.cta, 0.49);
assert.equal(runtime.events().filter((event) => event.event_name === 'affiliate_cta_impression').length, 0);
ctaObserver.trigger(runtime.cta, 0.5);
ctaObserver.trigger(runtime.cta, 1);
assert.equal(runtime.events().filter((event) => event.event_name === 'affiliate_cta_impression').length, 1);

const cardObserver = runtime.observers.find((observer) => observer.targets.includes(runtime.card));
assert.ok(cardObserver);
cardObserver.trigger(runtime.card, 0.5);
assert.equal(runtime.events().filter((event) => event.event_name === 'product_card_view').length, 1);
assert.equal(runtime.events().filter((event) => event.event_name === 'qualified_decision_engagement').length, 1);

let defaultPrevented = false;
runtime.document.dispatch('click', {
  target: runtime.cta,
  preventDefault() {
    defaultPrevented = true;
  }
});
assert.equal(defaultPrevented, false);
assert.equal(runtime.events().filter((event) => event.event_name === 'affiliate_click').length, 1);
assert.equal(runtime.beaconEvents.length, 1);
assert.deepEqual(runtime.beaconEndpoints, [
  'https://kurashinoshirube.com/wp-json/raos/v1/events'
]);

const failedDelivery = createRuntime(true, {
  beaconThrows: true,
  fetchThrows: true
});
failedDelivery.run();
let failurePreventedNavigation = false;
failedDelivery.document.dispatch('click', {
  target: failedDelivery.cta,
  preventDefault() {
    failurePreventedNavigation = true;
  }
});
assert.equal(failurePreventedNavigation, false);

for (const event of runtime.events()) {
  assert.deepEqual(Object.keys(event).sort(), [
    'anonymous_session_id',
    'article_id',
    'dimensions',
    'event_id',
    'event_name',
    'occurred_at',
    'schema_version',
    'snapshot_id'
  ]);
  const serialized = JSON.stringify(event);
  assert.ok(!serialized.includes('https://'));
  assert.ok(!serialized.includes('?'));
  assert.ok(!serialized.includes('@'));
}

const beforeRevocation = runtime.events().length;
runtime.setConsent(false);
assert.equal(runtime.storage.size, 0);
assert.ok(runtime.observers.every((observer) => observer.disconnected));
runtime.document.dispatch('click', { target: runtime.cta });
assert.equal(runtime.events().length, beforeRevocation);

console.log('RAOS_MEASUREMENT_CLIENT_BEHAVIOR_OK');
