import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const sourcePath = process.argv[2];
if (!sourcePath) {
  throw new Error('consent gate source path is required');
}
const source = fs.readFileSync(sourcePath, 'utf8');

class Events {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }

  dispatch(name) {
    for (const callback of this.listeners.get(name) || []) {
      callback({ type: name });
    }
  }
}

class Element {
  constructor(document, tagName) {
    this.document = document;
    this.tagName = tagName.toUpperCase();
    this.type = '';
    this.id = '';
    this.async = false;
    this.src = '';
    this.dataset = {};
    this.attributes = new Map();
  }

  getAttribute(name) {
    if (name === 'id') return this.id || null;
    if (name === 'type') return this.type || null;
    return this.attributes.get(name) || null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  replaceWith(replacement) {
    this.document.elements.delete(this.id);
    this.document.elements.set(replacement.id, replacement);
    this.document.replacements.push(replacement);
  }

  remove() {
    this.document.elements.delete(this.id);
    this.document.removals.push(this);
  }
}

class Document extends Events {
  constructor(configuration) {
    super();
    this.readyState = 'complete';
    this.elements = new Map();
    this.replacements = [];
    this.removals = [];
    this.cookies = new Map([
      ['_ga', 'identifier'],
      ['_ga_CONTAINER', 'session'],
      ['functional', 'kept'],
    ]);
    const gate = new Element(this, 'script');
    gate.id = 'google_gtagjs-js';
    gate.type = configuration.type || 'application/json';
    gate.setAttribute(
      'data-raos-consent-gate',
      configuration.gate || 'statistics'
    );
    gate.setAttribute(
      'data-raos-measurement-id',
      configuration.measurementId || 'G-ABCDEF12'
    );
    gate.setAttribute(
      'data-raos-source',
      configuration.source ||
        'https://www.googletagmanager.com/gtag/js?id=G-ABCDEF12'
    );
    this.elements.set(gate.id, gate);
  }

  get cookie() {
    return [...this.cookies].map(([name, value]) => `${name}=${value}`).join('; ');
  }

  set cookie(value) {
    const [pair] = String(value).split(';', 1);
    const separator = pair.indexOf('=');
    const name = pair.slice(0, separator).trim();
    const cookieValue = pair.slice(separator + 1);
    if (/Max-Age=0|Expires=Thu, 01 Jan 1970/i.test(String(value))) {
      this.cookies.delete(name);
    } else {
      this.cookies.set(name, cookieValue);
    }
  }

  createElement(tagName) {
    return new Element(this, tagName);
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }
}

function runScenario({
  configuration = {},
  providers = {},
  existingGtag = false,
  existingDataLayer = [],
}) {
  const document = new Document(configuration);
  const windowEvents = new Events();
  let reloadCount = 0;
  const state = {
    cookieYes: providers.cookieYes ?? false,
    wpConsent: providers.wpConsent ?? false,
    siteKit: providers.siteKit ?? false,
  };
  const window = {
    addEventListener: windowEvents.addEventListener.bind(windowEvents),
    dataLayer: existingDataLayer,
    getCkyConsent:
      providers.cookieYes === undefined
        ? undefined
        : () => ({
            categories: { analytics: state.cookieYes },
            isUserActionCompleted: true,
          }),
    location: {
      hostname: 'preview.example.test',
      reload() {
        reloadCount += 1;
      },
    },
    wp_has_consent:
      providers.wpConsent === undefined
        ? undefined
        : (category) => category === 'statistics' && state.wpConsent,
    _googlesitekitConsents:
      providers.siteKit === undefined
        ? undefined
        : {
            analytics_storage: state.siteKit ? 'granted' : 'denied',
          },
  };
  if (existingGtag) {
    window.gtag = () => {};
  }
  const context = vm.createContext({
    Array,
    Date,
    Object,
    Set,
    URL,
    document,
    window,
  });
  vm.runInContext(source, context, { filename: sourcePath });
  return {
    document,
    reloadCount: () => reloadCount,
    revoke() {
      state.cookieYes = false;
      state.wpConsent = false;
      state.siteKit = false;
      if (window._googlesitekitConsents) {
        window._googlesitekitConsents.analytics_storage = 'denied';
      }
      document.cookies.set('_ga', 'new-identifier');
      document.cookies.set('_ga_CONTAINER', 'new-session');
      document.dispatch('cookieyes_consent_update');
    },
    window,
  };
}

for (const providers of [
  {},
  { cookieYes: true },
  { cookieYes: true, wpConsent: true },
  { cookieYes: false, wpConsent: false, siteKit: false },
  { cookieYes: true, wpConsent: true, siteKit: false },
]) {
  const scenario = runScenario({ providers });
  assert.equal(scenario.document.replacements.length, 0);
  assert.equal(scenario.document.cookies.has('_ga'), false);
  assert.equal(scenario.document.cookies.has('_ga_CONTAINER'), false);
  assert.equal(scenario.document.cookies.get('functional'), 'kept');
  assert.equal(scenario.reloadCount(), 0);
}

const granted = runScenario({
  providers: { cookieYes: true, wpConsent: true, siteKit: true },
});
assert.equal(granted.document.replacements.length, 1);
const loader = granted.document.replacements[0];
assert.equal(loader.tagName, 'SCRIPT');
assert.equal(loader.id, 'google_gtagjs-js');
assert.equal(
  loader.src,
  'https://www.googletagmanager.com/gtag/js?id=G-ABCDEF12'
);
assert.equal(loader.dataset.cookieyes, 'cookieyes-analytics');
assert.equal(loader.dataset.raosConsentActivated, 'statistics');
assert.equal(granted.window.dataLayer.length, 3);
assert.deepEqual(
  JSON.parse(JSON.stringify(Array.from(granted.window.dataLayer[0]))),
  [
    'consent',
    'update',
    {
      ad_personalization: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      analytics_storage: 'granted',
    },
  ]
);
granted.document.dispatch('wp_listen_for_consent_change');
assert.equal(granted.document.replacements.length, 1);

granted.revoke();
assert.equal(granted.reloadCount(), 1);
assert.equal(granted.window['ga-disable-G-ABCDEF12'], true);
assert.equal(granted.document.removals.length, 1);
assert.equal(granted.window.dataLayer.length, 4);
assert.deepEqual(
  JSON.parse(JSON.stringify(Array.from(granted.window.dataLayer[3]))),
  [
    'consent',
    'update',
    {
      ad_personalization: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      analytics_storage: 'denied',
    },
  ]
);
assert.equal(granted.document.cookies.has('_ga'), false);
assert.equal(granted.document.cookies.has('_ga_CONTAINER'), false);
assert.equal(granted.document.cookies.get('functional'), 'kept');
granted.document.dispatch('cookieyes_consent_update');
assert.equal(granted.reloadCount(), 1);
assert.equal(granted.document.replacements.length, 1);

for (const configuration of [
  { source: 'http://www.googletagmanager.com/gtag/js?id=G-ABCDEF12' },
  { source: 'https://evil.example/gtag/js?id=G-ABCDEF12' },
  {
    source:
      'https://www.googletagmanager.com/gtag/js?id=G-ABCDEF12&debug=1',
  },
  { source: 'https://user@www.googletagmanager.com/gtag/js?id=G-ABCDEF12' },
  { measurementId: 'GT-ABCDEF12' },
  { type: 'text/javascript' },
]) {
  const scenario = runScenario({
    configuration,
    providers: { cookieYes: true, wpConsent: true, siteKit: true },
  });
  assert.equal(scenario.document.replacements.length, 0);
  assert.equal(scenario.window.dataLayer.length, 0);
}

const preexisting = runScenario({
  existingGtag: true,
  providers: { cookieYes: true, wpConsent: true, siteKit: true },
});
assert.equal(preexisting.document.replacements.length, 0);
assert.equal(preexisting.window.dataLayer.length, 0);
assert.equal(preexisting.window['ga-disable-G-ABCDEF12'], true);
assert.equal(preexisting.document.cookies.has('_ga'), false);
assert.equal(preexisting.document.cookies.has('_ga_CONTAINER'), false);

const unownedQueue = runScenario({
  existingDataLayer: [['event', 'unreviewed-command']],
  providers: { cookieYes: true, wpConsent: true, siteKit: true },
});
assert.equal(unownedQueue.document.replacements.length, 1);
assert.equal(unownedQueue.window.dataLayer.length, 3);
assert.equal(
  unownedQueue.window.dataLayer.some(
    (entry) => Array.isArray(entry) && entry.includes('unreviewed-command')
  ),
  false
);

process.stdout.write('ANALYTICS_CONSENT_GATE_HARNESS_OK\n');
