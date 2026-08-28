import vm from 'node:vm';
import { createServer } from 'node:http';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { isAbsolute, join } from 'node:path';

import {
  CdpConnection,
  evaluate,
  navigate,
  reservePort,
  waitForDebugger,
} from './browser-validation.mjs';
import {
  browserStateMutationHeaderNames,
  launchSandboxedBrowser,
  stopBrowserProcess,
  storageAuditBootstrapSource,
} from './phase3-public-validation.mjs';

class Document {
  addEventListener() {}
}
Object.defineProperty(Document.prototype, 'cookie', {
  configurable: true,
  get() {
    return '';
  },
  set(_value) {},
});
class Storage {
  setItem() {}
  removeItem() {}
  clear() {}
}
class CookieStore {
  set() {
    return Promise.resolve();
  }
  delete() {
    return Promise.resolve();
  }
}
class IDBFactory {
  open() {}
  deleteDatabase() {}
}
class ServiceWorkerContainer {
  register() {
    return Promise.resolve();
  }
}
class CacheStorage {
  open() {
    return Promise.resolve();
  }
  delete() {
    return Promise.resolve();
  }
  keys() {
    return Promise.resolve([]);
  }
}
class StorageManager {
  getDirectory() {
    return Promise.resolve({});
  }
}
class StorageBucketManager {
  open() {
    return Promise.resolve({});
  }
  delete() {
    return Promise.resolve();
  }
  keys() {
    return Promise.resolve([]);
  }
}
class SharedStorage {
  set() {
    return Promise.resolve();
  }
  append() {
    return Promise.resolve();
  }
  delete() {
    return Promise.resolve();
  }
  clear() {
    return Promise.resolve();
  }
  createWorklet() {
    return Promise.resolve({});
  }
  run() {
    return Promise.resolve();
  }
  selectURL() {
    return Promise.resolve('urn:uuid:00000000-0000-0000-0000-000000000000');
  }
}
class SharedStorageWorklet {
  addModule() {
    return Promise.resolve();
  }
  run() {
    return Promise.resolve();
  }
  selectURL() {
    return Promise.resolve('urn:uuid:00000000-0000-0000-0000-000000000000');
  }
}
class Navigator {
  sendBeacon() {
    return true;
  }
  joinAdInterestGroup() {
    return Promise.resolve();
  }
  leaveAdInterestGroup() {
    return Promise.resolve();
  }
  clearOriginJoinedAdInterestGroups() {
    return Promise.resolve();
  }
  updateAdInterestGroups() {
    return Promise.resolve();
  }
}
class HTMLFormElement {
  submit() {}
  requestSubmit() {}
}
class UnblockedConstructor {}

const document = new Document();
const cookieStore = new CookieStore();
const localStorage = new Storage();
const sessionStorage = new Storage();
const indexedDB = new IDBFactory();
const serviceWorker = new ServiceWorkerContainer();
serviceWorker.getRegistrations = () => Promise.resolve([]);
const caches = new CacheStorage();
const storage = new StorageManager();
const storageBuckets = new StorageBucketManager();
const sharedStorage = new SharedStorage();
sharedStorage.worklet = new SharedStorageWorklet();
const navigator = new Navigator();
navigator.serviceWorker = serviceWorker;
navigator.storage = storage;
navigator.storageBuckets = storageBuckets;

const context = vm.createContext({
  CacheStorage,
  CookieStore,
  DOMException,
  Document,
  EventSource: UnblockedConstructor,
  HTMLFormElement,
  IDBFactory,
  Navigator,
  RTCPeerConnection: UnblockedConstructor,
  ServiceWorkerContainer,
  SharedStorage,
  SharedStorageWorklet,
  SharedWorker: UnblockedConstructor,
  Storage,
  StorageBucketManager,
  StorageManager,
  WebSocket: UnblockedConstructor,
  WebSocketStream: UnblockedConstructor,
  WebTransport: UnblockedConstructor,
  Worker: UnblockedConstructor,
  caches,
  cookieStore,
  document,
  indexedDB,
  localStorage,
  navigator,
  open() {},
  sessionStorage,
  sharedStorage,
  webkitRTCPeerConnection: UnblockedConstructor,
});

vm.runInContext(storageAuditBootstrapSource(), context, {
  filename: 'phase3-public-bootstrap-adversarial.js',
});

for (const expression of [
  "Object.defineProperty(globalThis, 'WebSocketStream', { value: class Bypass {} })",
  "Object.defineProperty(CacheStorage.prototype, 'open', { value() { return Promise.resolve(); } })",
  "Object.defineProperty(CookieStore.prototype, 'set', { value() { return Promise.resolve(); } })",
  "Object.defineProperty(StorageManager.prototype, 'getDirectory', { value() { return Promise.resolve({}); } })",
  "Object.defineProperty(StorageBucketManager.prototype, 'open', { value() { return Promise.resolve({}); } })",
  "Object.defineProperty(SharedStorage.prototype, 'set', { value() { return Promise.resolve(); } })",
  "Object.defineProperty(SharedStorageWorklet.prototype, 'addModule', { value() { return Promise.resolve(); } })",
  "Object.defineProperty(Navigator.prototype, 'joinAdInterestGroup', { value() { return Promise.resolve(); } })",
]) {
  try {
    vm.runInContext(expression, context);
    throw new Error('AUDIT_GUARD_REDEFINITION_NOT_BLOCKED');
  } catch (error) {
    if (!(error instanceof TypeError) && error?.name !== 'TypeError') throw error;
  }
}
if (!vm.runInContext('Object.isFrozen(globalThis.__RAOS_V2_PUBLIC_AUDIT__)', context)) {
  throw new Error('AUDIT_SNAPSHOT_MUTABLE');
}

function expectSecurityError(operation, code) {
  try {
    operation();
  } catch (error) {
    if (error?.name === 'SecurityError') return;
    throw new Error(code);
  }
  throw new Error(code);
}

expectSecurityError(
  () => vm.runInContext("new WebSocketStream('wss://attacker.invalid')", context),
  'WEBSOCKET_STREAM_NOT_BLOCKED',
);

const cacheResult = vm.runInContext("caches.open('adversarial')", context);
const cookieStoreResult = vm.runInContext("cookieStore.set('raos', 'persisted')", context);
const opfsResult = vm.runInContext('navigator.storage.getDirectory()', context);
const bucketResult = vm.runInContext("navigator.storageBuckets.open('adversarial')", context);
const sharedStorageResult = vm.runInContext("sharedStorage.set('key', 'value')", context);
const sharedStorageWorkletResult = vm.runInContext(
  "sharedStorage.worklet.addModule('/adversarial-worklet.js')",
  context,
);
const protectedAudienceResults = [
  vm.runInContext(
    "navigator.joinAdInterestGroup({ owner: 'https://example.invalid', name: 'raos' }, 60)",
    context,
  ),
  vm.runInContext(
    "navigator.leaveAdInterestGroup({ owner: 'https://example.invalid', name: 'raos' })",
    context,
  ),
  vm.runInContext(
    "navigator.clearOriginJoinedAdInterestGroups('https://example.invalid')",
    context,
  ),
  vm.runInContext('navigator.updateAdInterestGroups()', context),
];
for (const [promise, code] of [
  [cacheResult, 'CACHE_STORAGE_NOT_BLOCKED'],
  [cookieStoreResult, 'COOKIE_STORE_NOT_BLOCKED'],
  [opfsResult, 'OPFS_NOT_BLOCKED'],
  [bucketResult, 'STORAGE_BUCKET_NOT_BLOCKED'],
  [sharedStorageResult, 'SHARED_STORAGE_NOT_BLOCKED'],
  [sharedStorageWorkletResult, 'SHARED_STORAGE_WORKLET_NOT_BLOCKED'],
  ...protectedAudienceResults.map((promise) => [promise, 'PROTECTED_AUDIENCE_NOT_BLOCKED']),
]) {
  try {
    await promise;
    throw new Error(code);
  } catch (error) {
    if (error?.name !== 'SecurityError') throw error;
  }
}

const state = vm.runInContext('globalThis.__RAOS_V2_PUBLIC_AUDIT__', context);
if (
  state.instrumentationFailures !== 0 ||
  state.streamingChannelAttempts !== 1 ||
  state.cacheStorageMutationAttempts !== 1 ||
  state.cookieStoreMutationAttempts !== 1 ||
  state.opfsMutationAttempts !== 1 ||
  state.storageBucketMutationAttempts !== 1 ||
  state.sharedStorageMutationAttempts !== 2 ||
  state.protectedAudienceMutationAttempts !== 4
) {
  throw new Error('ADVERSARIAL_COUNTER_CONTRACT_INVALID');
}

function startAdversarialServer() {
  const body = `<!doctype html><html><head><meta charset="utf-8"><title>adversarial</title></head><body><script>
    const attempt = async (operation) => {
      try { await operation(); return 'FULFILLED'; }
      catch (error) { return error?.name ?? 'UNKNOWN'; }
    };
    globalThis.__RAOS_V2_REAL_PROBE__ = (async () => {
      localStorage.raos = 'persisted';
      delete localStorage.raos;
      sessionStorage.raos = 'persisted';
      delete sessionStorage.raos;
      const storageBucket = navigator.storageBuckets === undefined
        ? 'UNAVAILABLE'
        : await attempt(() => navigator.storageBuckets.open('raos-adversarial'));
      const cookieStoreResult = globalThis.cookieStore === undefined
        ? 'UNAVAILABLE'
        : await attempt(() => cookieStore.set('raos', 'persisted'));
      const sharedStorageResult = globalThis.sharedStorage === undefined
        ? 'UNAVAILABLE'
        : await attempt(() => sharedStorage.set('raos', 'persisted'));
      const protectedAudienceResult = typeof navigator.joinAdInterestGroup !== 'function'
        ? 'UNAVAILABLE'
        : await attempt(() => navigator.joinAdInterestGroup({
            owner: location.origin,
            name: 'raos-adversarial',
            biddingLogicURL: location.origin + '/bid.js',
          }, 60));
      await fetch('/set', { credentials: 'include' });
      await fetch('/delete', { credentials: 'include' });
      await fetch('/state', { credentials: 'omit' });
      return {
        audit: globalThis.__RAOS_V2_PUBLIC_AUDIT__,
        cookieStoreResult,
        localStorageLength: localStorage.length,
        sessionStorageLength: sessionStorage.length,
        sharedStorageResult,
        storageBucket,
        protectedAudienceResult,
      };
    })();
  </script></body></html>`;
  const server = createServer((request, response) => {
    if (request.method !== 'GET' || !['/', '/set', '/delete', '/state'].includes(request.url)) {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('not found');
      return;
    }
    if (request.url === '/set') {
      response.writeHead(204, {
        'Cache-Control': 'no-store',
        'Set-Cookie': 'raos=ephemeral; Path=/; SameSite=Strict',
      });
      response.end();
      return;
    }
    if (request.url === '/delete') {
      response.writeHead(204, {
        'Cache-Control': 'no-store',
        'Set-Cookie': 'raos=; Max-Age=0; Path=/; SameSite=Strict',
      });
      response.end();
      return;
    }
    if (request.url === '/state') {
      response.writeHead(204, {
        'Attribution-Reporting-Register-Source': '{"source_event_id":"1"}',
        'Attribution-Reporting-Register-Trigger': '{"trigger_data":"1"}',
        'Clear-Site-Data': '"storage"',
        'Observe-Browsing-Topics': '?1',
      });
      response.end();
      return;
    }
    response.writeHead(200, {
      'Cache-Control': 'no-store',
      'Content-Length': String(Buffer.byteLength(body)),
      'Content-Security-Policy':
        "default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'",
      'Content-Type': 'text/html; charset=utf-8',
    });
    response.end(body);
  });
  return new Promise((resolvePromise, rejectPromise) => {
    server.once('error', rejectPromise);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (address === null || typeof address === 'string') {
        rejectPromise(new Error('ADVERSARIAL_SERVER_ADDRESS_INVALID'));
        return;
      }
      resolvePromise({
        close: () => new Promise((resolveClose) => server.close(resolveClose)),
        url: `http://127.0.0.1:${address.port}/`,
      });
    });
  });
}

async function runRealChromiumAdversarialContract(browserExecutable) {
  const server = await startAdversarialServer();
  const profilePath = mkdtempSync(join(tmpdir(), 'raos-v2-phase3-adversarial-'));
  let browser = null;
  let connection = null;
  try {
    const remotePort = await reservePort();
    browser = await launchSandboxedBrowser(browserExecutable, remotePort, profilePath);
    connection = new CdpConnection(await waitForDebugger(remotePort));
    await connection.open();
    const domStorageEvents = [];
    const responseStateMutationHeaders = [];
    for (const eventName of [
      'DOMStorage.domStorageItemAdded',
      'DOMStorage.domStorageItemRemoved',
      'DOMStorage.domStorageItemUpdated',
      'DOMStorage.domStorageItemsCleared',
    ]) {
      connection.on(eventName, () => domStorageEvents.push(eventName));
    }
    await connection.call('Page.enable');
    await connection.call('Runtime.enable');
    connection.on('Network.responseReceivedExtraInfo', (event) => {
      responseStateMutationHeaders.push(...browserStateMutationHeaderNames(event.headers));
    });
    await connection.call('Network.enable');
    await connection.call('DOMStorage.enable');
    await connection.call('Page.addScriptToEvaluateOnNewDocument', {
      source: storageAuditBootstrapSource(),
    });
    await navigate(connection, server.url);
    const result = await evaluate(connection, 'globalThis.__RAOS_V2_REAL_PROBE__');
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    const cookies = await connection.call('Network.getAllCookies');
    if (
      result.storageBucket !== 'SecurityError' ||
      result.cookieStoreResult !== 'SecurityError' ||
      (result.sharedStorageResult !== 'SecurityError' &&
        result.sharedStorageResult !== 'UNAVAILABLE') ||
      result.audit.storageBucketMutationAttempts !== 1 ||
      result.audit.cookieStoreMutationAttempts !== 1 ||
      (result.sharedStorageResult === 'SecurityError' &&
        result.audit.sharedStorageMutationAttempts !== 1) ||
      (result.protectedAudienceResult === 'SecurityError' &&
        result.audit.protectedAudienceMutationAttempts !== 1) ||
      (result.protectedAudienceResult === 'UNAVAILABLE' &&
        result.audit.protectedAudienceMutationAttempts !== 0) ||
      result.localStorageLength !== 0 ||
      result.sessionStorageLength !== 0 ||
      !domStorageEvents.includes('DOMStorage.domStorageItemAdded') ||
      !domStorageEvents.includes('DOMStorage.domStorageItemRemoved') ||
      ![
        'attribution-reporting-register-source',
        'attribution-reporting-register-trigger',
        'clear-site-data',
        'observe-browsing-topics',
        'set-cookie',
      ].every((name) => responseStateMutationHeaders.includes(name)) ||
      !Array.isArray(cookies.cookies) ||
      cookies.cookies.length !== 0
    ) {
      throw new Error('REAL_CHROMIUM_PERSISTENCE_GUARD_INVALID');
    }
  } finally {
    if (connection !== null) connection.close();
    if (browser !== null) await stopBrowserProcess(browser);
    rmSync(profilePath, {
      force: true,
      maxRetries: 20,
      recursive: true,
      retryDelay: 50,
    });
    await server.close();
  }
}

const browserArguments = process.argv.slice(2);
if (browserArguments.length !== 0) {
  if (
    browserArguments.length !== 2 ||
    browserArguments[0] !== '--browser-executable' ||
    !isAbsolute(browserArguments[1])
  ) {
    throw new Error('ADVERSARIAL_BROWSER_ARGUMENT_INVALID');
  }
  await runRealChromiumAdversarialContract(browserArguments[1]);
}

process.stdout.write('RAOS_V2_PHASE3_PUBLIC_ADVERSARIAL_RUNTIME_PASSED\n');
