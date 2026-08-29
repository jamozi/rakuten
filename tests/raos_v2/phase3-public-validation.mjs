import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import {
  closeSync,
  createReadStream,
  existsSync,
  lstatSync,
  linkSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

import {
  CdpConnection,
  ROOT,
  evaluate,
  navigate,
  reservePort,
  setViewport,
  waitForDebugger,
} from './browser-validation.mjs';

const require = createRequire(import.meta.url);
const SCRIPT_PATH = realpathSync(fileURLToPath(import.meta.url));
const SCRIPT_RELATIVE = 'tests/raos_v2/phase3-public-validation.mjs';
const SUPPORT_HARNESS_PATH = join(ROOT, 'tests/raos_v2/browser-validation.mjs');
const SUPPORT_HARNESS_RELATIVE = 'tests/raos_v2/browser-validation.mjs';
const TARGET_ORIGIN = 'https://kurashinoshirube.com';
const TARGET_ROUTE = '/carry-on-suitcase-comparison/';
const TARGET_URL = `${TARGET_ORIGIN}${TARGET_ROUTE}`;
const PACKAGE_MARKER = 'RAOS_V2_A05_POST_CONTENT_V1';
const CONTENT_ENVELOPE = 'RAOS_V2_A05_ENVELOPE_V1';
const RAW_RECEIPT_SCHEMA = 'RAOS_V2_PHASE3_PUBLIC_BROWSER_RAW_RECEIPT_V1';
const COMMAND_CONTRACT = 'NODE24_PUBLIC_READ_ONLY_CDP_AXE_PHASE3_SANITIZED_RAW_RECEIPT_V1';
const REQUIRED_NODE_MAJOR = 24;
const REQUIRED_AXE_VERSION = '4.12.1';
const OUTPUT_ROOT = join(ROOT, 'output/playwright');
const MAX_DOCUMENT_BYTES = 4 * 1024 * 1024;
const MAX_SCREENSHOT_HEIGHT = 30_000;
const MAX_NETWORK_REQUESTS = 80;
const BROWSER_STOP_TIMEOUT_MS = 5000;
const BROWSER_GRACEFUL_STOP_MS = 250;
const BROWSER_SUPERVISOR_EXIT_TIMEOUT_MS =
  BROWSER_GRACEFUL_STOP_MS + BROWSER_STOP_TIMEOUT_MS + 1000;
const INTERNAL_BROWSER_SUPERVISOR = '--internal-browser-supervisor';
const VIEWPORTS = Object.freeze([
  Object.freeze({ height: 844, name: 'mobile-390', width: 390 }),
  Object.freeze({ height: 1024, name: 'tablet-768', width: 768 }),
  Object.freeze({ height: 900, name: 'desktop-1440', width: 1440 }),
]);
const AFFILIATE_URL_PATTERN = /(?:rakuten|r10\.to|hb\.afl)/iu;

class Phase3PublicValidationError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
    this.name = 'Phase3PublicValidationError';
  }
}

function fail(code) {
  throw new Phase3PublicValidationError(code);
}

const SAFE_SYSTEM_ERROR_CODES = new Set([
  'EACCES',
  'EEXIST',
  'EIO',
  'EMFILE',
  'ENFILE',
  'ENOENT',
  'ENOSPC',
  'ENOTDIR',
  'EPERM',
  'EROFS',
]);

function classifiedErrorCode(error) {
  if (error instanceof Phase3PublicValidationError) return error.code;
  const candidate =
    error !== null && typeof error === 'object' && typeof error.code === 'string' ? error.code : '';
  if (error?.name === 'BrowserValidationError' && /^[A-Z0-9_]+$/u.test(candidate)) {
    return `PHASE3_PUBLIC_SUPPORT_${candidate}`;
  }
  if (SAFE_SYSTEM_ERROR_CODES.has(candidate)) return `PHASE3_PUBLIC_RUNTIME_${candidate}`;
  return 'PHASE3_PUBLIC_VALIDATION_UNEXPECTED';
}

function sha256Bytes(value) {
  return createHash('sha256').update(value).digest('hex');
}

const BROWSER_STATE_MUTATION_RESPONSE_HEADERS = new Set([
  'accept-ch',
  'activate-storage-access',
  'attribution-reporting-register-source',
  'attribution-reporting-register-trigger',
  'clear-site-data',
  'nel',
  'observe-browsing-topics',
  'report-to',
  'reporting-endpoints',
  'sec-private-state-token',
  'set-cookie',
  'set-login',
]);

export function browserStateMutationHeaderNames(headers) {
  if (headers === null || typeof headers !== 'object' || Array.isArray(headers)) return [];
  return Object.keys(headers)
    .map((name) => name.toLowerCase())
    .filter((name) => BROWSER_STATE_MUTATION_RESPONSE_HEADERS.has(name))
    .sort();
}

async function sha256File(path) {
  const hash = createHash('sha256');
  await new Promise((resolvePromise, rejectPromise) => {
    const stream = createReadStream(path);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.once('error', rejectPromise);
    stream.once('end', resolvePromise);
  });
  return hash.digest('hex');
}

function parseArguments(argv) {
  let browserExecutable = null;
  let output = null;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = argv[index + 1] ?? null;
    if (argument === '--browser-executable' && browserExecutable === null && value !== null) {
      browserExecutable = value;
      index += 1;
      continue;
    }
    if (argument === '--output' && output === null && value !== null) {
      output = value;
      index += 1;
      continue;
    }
    fail('PHASE3_PUBLIC_ARGUMENT_INVALID');
  }
  if (browserExecutable === null || !isAbsolute(browserExecutable)) {
    fail('PHASE3_PUBLIC_BROWSER_EXECUTABLE_ABSOLUTE_REQUIRED');
  }
  if (output === null) fail('PHASE3_PUBLIC_OUTPUT_REQUIRED');
  const outputPath = resolve(ROOT, output);
  const fromOutputRoot = relative(OUTPUT_ROOT, outputPath);
  if (
    fromOutputRoot === '' ||
    fromOutputRoot === '..' ||
    fromOutputRoot.startsWith(`..${sep}`) ||
    isAbsolute(fromOutputRoot) ||
    !outputPath.endsWith('.json')
  ) {
    fail('PHASE3_PUBLIC_OUTPUT_PATH_INVALID');
  }
  const capturesDirectory = join(dirname(outputPath), `${basename(outputPath, '.json')}-captures`);
  return Object.freeze({ browserExecutable, capturesDirectory, outputPath });
}

function ensureSafeOutputDirectory(path) {
  const fromRoot = relative(ROOT, path);
  const parts = fromRoot.split(sep);
  if (
    isAbsolute(fromRoot) ||
    parts.length < 2 ||
    parts[0] !== 'output' ||
    parts[1] !== 'playwright' ||
    parts.includes('..')
  ) {
    fail('PHASE3_PUBLIC_OUTPUT_DIRECTORY_INVALID');
  }
  let current = ROOT;
  for (const part of parts) {
    current = join(current, part);
    if (!existsSync(current)) {
      mkdirSync(current, { mode: 0o700 });
      continue;
    }
    const information = lstatSync(current);
    if (!information.isDirectory() || information.isSymbolicLink()) {
      fail('PHASE3_PUBLIC_OUTPUT_DIRECTORY_INVALID');
    }
  }
  const outputRoot = realpathSync(OUTPUT_ROOT);
  const outputDirectory = realpathSync(path);
  const fromOutputRoot = relative(outputRoot, outputDirectory);
  if (
    fromOutputRoot === '..' ||
    fromOutputRoot.startsWith(`..${sep}`) ||
    isAbsolute(fromOutputRoot)
  ) {
    fail('PHASE3_PUBLIC_OUTPUT_DIRECTORY_INVALID');
  }
}

function prepareOutput(argumentsValue) {
  ensureSafeOutputDirectory(dirname(argumentsValue.outputPath));
  if (existsSync(argumentsValue.outputPath) || existsSync(argumentsValue.capturesDirectory)) {
    fail('PHASE3_PUBLIC_OUTPUT_ALREADY_EXISTS');
  }
  return mkdtempSync(join(dirname(argumentsValue.outputPath), '.raos-v2-public-browser-'));
}

function writeExclusive(path, value) {
  const descriptor = openSync(path, 'wx', 0o600);
  try {
    writeFileSync(descriptor, value);
  } finally {
    closeSync(descriptor);
  }
}

export function commitEvidence(argumentsValue, temporaryCapturesDirectory, receipt) {
  const temporaryReceipt = `${argumentsValue.outputPath}.tmp-${process.pid}`;
  let capturesDirectoryCreated = false;
  let receiptCommitted = false;
  try {
    writeExclusive(temporaryReceipt, `${JSON.stringify(receipt, null, 2)}\n`);
    mkdirSync(argumentsValue.capturesDirectory, { mode: 0o700 });
    capturesDirectoryCreated = true;
    for (const entry of readdirSync(temporaryCapturesDirectory, { withFileTypes: true })) {
      if (!entry.isFile() || entry.isSymbolicLink() || basename(entry.name) !== entry.name) {
        fail('PHASE3_PUBLIC_CAPTURE_SET_INVALID');
      }
      renameSync(
        join(temporaryCapturesDirectory, entry.name),
        join(argumentsValue.capturesDirectory, entry.name),
      );
    }
    linkSync(temporaryReceipt, argumentsValue.outputPath);
    receiptCommitted = true;
  } catch (error) {
    if (
      !receiptCommitted &&
      capturesDirectoryCreated &&
      existsSync(argumentsValue.capturesDirectory)
    ) {
      rmSync(argumentsValue.capturesDirectory, { force: true, recursive: true });
    }
    if (error?.code === 'EEXIST') fail('PHASE3_PUBLIC_OUTPUT_ALREADY_EXISTS');
    throw error;
  } finally {
    if (existsSync(temporaryReceipt)) rmSync(temporaryReceipt, { force: true });
    if (existsSync(temporaryCapturesDirectory)) {
      rmSync(temporaryCapturesDirectory, { force: true, recursive: true });
    }
  }
}

function loadAxeRuntime() {
  let axePath;
  let packagePath;
  try {
    axePath = require.resolve('axe-core/axe.min.js');
    packagePath = require.resolve('axe-core/package.json');
  } catch {
    fail('PHASE3_PUBLIC_AXE_DEPENDENCY_UNAVAILABLE');
  }
  try {
    const axePackage = JSON.parse(readFileSync(packagePath, 'utf8'));
    if (axePackage.version !== REQUIRED_AXE_VERSION) {
      fail('PHASE3_PUBLIC_AXE_VERSION_INVALID');
    }
    const source = readFileSync(axePath, 'utf8');
    if (source.length === 0) fail('PHASE3_PUBLIC_AXE_DEPENDENCY_INVALID');
    return source;
  } catch (error) {
    if (error instanceof Phase3PublicValidationError) throw error;
    fail('PHASE3_PUBLIC_AXE_DEPENDENCY_INVALID');
  }
}

function browserVersion(executable) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(executable, ['--version'], {
      env: { LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', PATH: '/usr/bin:/bin' },
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    let value = '';
    child.stdout.on('data', (chunk) => {
      if (value.length < 1024) value += String(chunk);
    });
    child.once('error', () => {
      rejectPromise(new Phase3PublicValidationError('PHASE3_PUBLIC_BROWSER_VERSION_UNAVAILABLE'));
    });
    child.once('exit', (code) => {
      if (code === 0 && value.trim().length > 0) resolvePromise(value.trim());
      else {
        rejectPromise(new Phase3PublicValidationError('PHASE3_PUBLIC_BROWSER_VERSION_UNAVAILABLE'));
      }
    });
  });
}

function chromiumArguments(remotePort, profilePath) {
  return [
    '--headless=new',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--disable-domain-reliability',
    '--disable-features=MediaRouter,OptimizationHints,Translate',
    '--disable-sync',
    '--metrics-recording-only',
    '--no-first-run',
    '--remote-debugging-address=127.0.0.1',
    `--remote-debugging-port=${remotePort}`,
    `--user-data-dir=${profilePath}`,
    'about:blank',
  ];
}

async function superviseBrowser(argv) {
  if (process.platform !== 'linux') fail('PHASE3_PUBLIC_BROWSER_PROCESS_GROUP_UNSUPPORTED');
  if (argv.length !== 3) fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_ARGUMENT_INVALID');
  const [browserExecutable, remotePortText, profilePath] = argv;
  if (!/^[1-9][0-9]{0,4}$/u.test(remotePortText) || Number(remotePortText) > 65535) {
    fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_PORT_INVALID');
  }
  if (!isAbsolute(profilePath)) fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_PROFILE_INVALID');
  const executable = realpathSync(browserExecutable);
  const child = spawn(
    executable,
    chromiumArguments(Number(remotePortText), profilePath),
    {
      env: {
        LANG: 'C.UTF-8',
        LC_ALL: 'C.UTF-8',
        PATH: '/usr/bin:/bin',
      },
      stdio: ['ignore', 'ignore', 'pipe'],
    },
  );
  child.stderr.pipe(process.stderr);
  child.once('error', () => {
    process.stderr.write('PHASE3_PUBLIC_BROWSER_CHILD_LAUNCH_FAILED\n');
  });

  // The supervisor deliberately stays alive even if Chromium's root exits.
  // This keeps ownership of the detached process group continuous until the
  // parent harness freezes and terminates the whole group.
  process.on('SIGTERM', () => {});
  let stopping = false;
  process.on('SIGUSR1', () => {
    if (stopping) return;
    stopping = true;
    void shutdownSupervisedBrowserGroup().catch(() => emergencyKillOwnedBrowserGroup());
  });
  const parentPid = process.ppid;
  setInterval(() => {
    if (process.ppid === parentPid) return;
    emergencyKillOwnedBrowserGroup();
  }, 250);
  await new Promise(() => {});
}

function emergencyKillOwnedBrowserGroup() {
  try {
    process.kill(-process.pid, 'SIGKILL');
  } catch {
    process.exit(1);
  }
}

function linuxProcessGroupMembers(groupId) {
  const members = [];
  for (const entry of readdirSync('/proc')) {
    if (!/^[1-9][0-9]*$/u.test(entry)) continue;
    let stat;
    try {
      stat = readFileSync(`/proc/${entry}/stat`, 'utf8');
    } catch (error) {
      if (error?.code === 'ENOENT') continue;
      fail('PHASE3_PUBLIC_BROWSER_PROCESS_GROUP_INSPECTION_FAILED');
    }
    const commandEnd = stat.lastIndexOf(') ');
    if (commandEnd < 0) fail('PHASE3_PUBLIC_BROWSER_PROCESS_STAT_INVALID');
    const fields = stat.slice(commandEnd + 2).trim().split(/\s+/u);
    if (fields.length < 3) fail('PHASE3_PUBLIC_BROWSER_PROCESS_STAT_INVALID');
    // A zombie has already exited and cannot retain or recreate the profile.
    // Waiting for an overloaded parent runtime to reap it can otherwise consume
    // the supervisor's entire bounded shutdown window.
    if (fields[0] !== 'Z' && Number(fields[2]) === groupId) members.push(Number(entry));
  }
  return members.sort((left, right) => left - right);
}

async function shutdownSupervisedBrowserGroup() {
  const groupId = process.pid;
  try {
    process.kill(-groupId, 'SIGTERM');
  } catch (error) {
    if (error?.code !== 'ESRCH') emergencyKillOwnedBrowserGroup();
  }
  await delay(BROWSER_GRACEFUL_STOP_MS);
  const deadline = Date.now() + BROWSER_STOP_TIMEOUT_MS;
  let stableEmptyObservations = 0;
  while (Date.now() < deadline) {
    const members = linuxProcessGroupMembers(groupId).filter((pid) => pid !== groupId);
    if (members.length === 0) {
      stableEmptyObservations += 1;
      if (stableEmptyObservations >= 2) process.exit(0);
      await delay(50);
      continue;
    }
    stableEmptyObservations = 0;
    for (const pid of members) {
      try {
        process.kill(pid, 'SIGKILL');
      } catch (error) {
        if (error?.code !== 'ESRCH') emergencyKillOwnedBrowserGroup();
      }
    }
    await delay(20);
  }
  emergencyKillOwnedBrowserGroup();
}

export async function launchSandboxedBrowser(browserExecutable, remotePort, profilePath) {
  if (process.platform !== 'linux') fail('PHASE3_PUBLIC_BROWSER_PROCESS_GROUP_UNSUPPORTED');
  const executable = realpathSync(browserExecutable);
  const child = spawn(
    realpathSync(process.execPath),
    [SCRIPT_PATH, INTERNAL_BROWSER_SUPERVISOR, executable, String(remotePort), profilePath],
    {
      detached: true,
      env: {
        LANG: 'C.UTF-8',
        LC_ALL: 'C.UTF-8',
        PATH: '/usr/bin:/bin',
      },
      stdio: ['ignore', 'ignore', 'pipe'],
    },
  );
  let stderr = '';
  child.stderr.on('data', (chunk) => {
    if (stderr.length < 1024 * 1024) stderr += String(chunk);
  });
  return Object.freeze({ child, executable, ownsProcessGroup: true, stderr: () => stderr });
}

function delay(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

function signalOwnedBrowserProcessGroup(browser, signal) {
  const pid = browser.child.pid;
  if (!Number.isSafeInteger(pid) || pid <= 0) fail('PHASE3_PUBLIC_BROWSER_PID_INVALID');
  if (!browser.ownsProcessGroup) fail('PHASE3_PUBLIC_BROWSER_PROCESS_GROUP_UNSUPPORTED');
  if (browser.child.exitCode !== null || browser.child.signalCode !== null) {
    fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_EXITED');
  }
  try {
    process.kill(-pid, signal);
  } catch (error) {
    if (error?.code === 'ESRCH') fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_EXITED');
    fail('PHASE3_PUBLIC_BROWSER_GROUP_SIGNAL_FAILED');
  }
}

function waitForBrowserSupervisorExit(browser) {
  return new Promise((resolvePromise) => {
    const timeout = setTimeout(() => {
      browser.child.removeListener('exit', onExit);
      resolvePromise(false);
    }, BROWSER_SUPERVISOR_EXIT_TIMEOUT_MS);
    function onExit() {
      clearTimeout(timeout);
      resolvePromise(true);
    }
    browser.child.once('exit', onExit);
  });
}

export async function stopBrowserProcess(browser) {
  const hasExited = () => browser.child.exitCode !== null || browser.child.signalCode !== null;
  if (hasExited()) fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_EXITED');
  const exited = waitForBrowserSupervisorExit(browser);

  // The supervisor retains process-group ownership while it terminates and
  // observes every other group member. Exit code zero is the receipt that the
  // ephemeral profile can be removed without a surviving writer.
  if (!browser.child.kill('SIGUSR1')) fail('PHASE3_PUBLIC_BROWSER_SUPERVISOR_EXITED');
  if (!(await exited)) {
    signalOwnedBrowserProcessGroup(browser, 'SIGKILL');
    await waitForBrowserSupervisorExit(browser);
    fail('PHASE3_PUBLIC_BROWSER_STOP_TIMEOUT');
  }
  if (!hasExited() || browser.child.exitCode !== 0) {
    fail('PHASE3_PUBLIC_BROWSER_GROUP_SHUTDOWN_FAILED');
  }
}

function pngDimensions(payload) {
  if (
    payload.length < 24 ||
    !payload.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
    payload.subarray(12, 16).toString('ascii') !== 'IHDR'
  ) {
    fail('PHASE3_PUBLIC_SCREENSHOT_PNG_INVALID');
  }
  return Object.freeze({ height: payload.readUInt32BE(20), width: payload.readUInt32BE(16) });
}

async function waitForStableLayout(connection, viewport) {
  const result = await evaluate(
    connection,
    `new Promise((resolvePromise) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolvePromise({
        height: document.documentElement.scrollHeight,
        width: window.innerWidth,
      })));
    })`,
  );
  if (result.width !== viewport.width || result.height < viewport.height) {
    fail(`PHASE3_PUBLIC_CSS_VIEWPORT_INVALID_${viewport.width}`);
  }
}

export function storageAuditBootstrapSource() {
  return `(() => {
    const state = {
      affiliateNavigationAttempts: 0,
      beaconAttempts: 0,
      cacheStorageMutationAttempts: 0,
      cookieMutationAttempts: 0,
      cookieStoreMutationAttempts: 0,
      formSubmissionAttempts: 0,
      indexedDbMutationAttempts: 0,
      instrumentationFailures: 0,
      localStorageMutationAttempts: 0,
      nonHttpChannelAttempts: 0,
      opfsMutationAttempts: 0,
      popupAttempts: 0,
      protectedAudienceMutationAttempts: 0,
      serviceWorkerRegistrationAttempts: 0,
      sessionStorageMutationAttempts: 0,
      sharedStorageMutationAttempts: 0,
      storageBucketMutationAttempts: 0,
      streamingChannelAttempts: 0,
      workerConstructionAttempts: 0,
    };
    Object.defineProperty(globalThis, '__RAOS_V2_PUBLIC_AUDIT__', {
      configurable: false,
      enumerable: false,
      get() { return Object.freeze({ ...state }); },
    });
    const instrument = (operation) => {
      try { operation(); } catch { state.instrumentationFailures += 1; }
    };
    instrument(() => {
      const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
      if (descriptor?.get === undefined || descriptor?.set === undefined) return;
      Object.defineProperty(Document.prototype, 'cookie', {
        configurable: false,
        enumerable: descriptor.enumerable,
        get() { return descriptor.get.call(this); },
        set() { state.cookieMutationAttempts += 1; },
      });
    });
    instrument(() => {
      const store = globalThis.cookieStore;
      if (store === undefined) return;
      const prototype = globalThis.CookieStore?.prototype ?? Object.getPrototypeOf(store);
      for (const name of ['set', 'delete']) {
        if (typeof prototype[name] !== 'function') continue;
        Object.defineProperty(prototype, name, {
          configurable: false,
          value() {
            state.cookieStoreMutationAttempts += 1;
            return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      for (const name of ['setItem', 'removeItem', 'clear']) {
        const original = Storage.prototype[name];
        Object.defineProperty(Storage.prototype, name, {
          configurable: false,
          value(...args) {
            if (this === globalThis.localStorage) state.localStorageMutationAttempts += 1;
            else if (this === globalThis.sessionStorage) state.sessionStorageMutationAttempts += 1;
            return undefined;
          },
          writable: false,
        });
        void original;
      }
    });
    instrument(() => {
      if (globalThis.IDBFactory === undefined) return;
      for (const name of ['open', 'deleteDatabase']) {
        Object.defineProperty(IDBFactory.prototype, name, {
          configurable: false,
          value() {
            state.indexedDbMutationAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      if (globalThis.ServiceWorkerContainer === undefined) return;
      Object.defineProperty(ServiceWorkerContainer.prototype, 'register', {
        configurable: false,
        value() {
          state.serviceWorkerRegistrationAttempts += 1;
          return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
        },
        writable: false,
      });
    });
    instrument(() => {
      if (globalThis.CacheStorage === undefined) return;
      for (const name of ['open', 'delete']) {
        Object.defineProperty(CacheStorage.prototype, name, {
          configurable: false,
          value() {
            state.cacheStorageMutationAttempts += 1;
            return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      if (globalThis.StorageManager === undefined ||
          typeof StorageManager.prototype.getDirectory !== 'function') return;
      Object.defineProperty(StorageManager.prototype, 'getDirectory', {
        configurable: false,
        value() {
          state.opfsMutationAttempts += 1;
          return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
        },
        writable: false,
      });
    });
    instrument(() => {
      const manager = navigator.storageBuckets;
      if (manager === undefined) return;
      const prototype = globalThis.StorageBucketManager?.prototype ?? Object.getPrototypeOf(manager);
      for (const name of ['open', 'delete']) {
        if (typeof prototype[name] !== 'function') continue;
        Object.defineProperty(prototype, name, {
          configurable: false,
          value() {
            state.storageBucketMutationAttempts += 1;
            return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      const storage = globalThis.sharedStorage;
      if (storage === undefined) return;
      const prototype = Object.getPrototypeOf(storage);
      for (const name of ['set', 'append', 'delete', 'clear']) {
        if (typeof prototype[name] !== 'function') continue;
        Object.defineProperty(prototype, name, {
          configurable: false,
          value() {
            state.sharedStorageMutationAttempts += 1;
            return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      const storage = globalThis.sharedStorage;
      if (storage === undefined) return;
      const surfaces = [
        [Object.getPrototypeOf(storage), ['createWorklet', 'run', 'selectURL']],
      ];
      const worklet = storage.worklet;
      if (worklet !== undefined && worklet !== null) {
        surfaces.push([Object.getPrototypeOf(worklet), ['addModule', 'run', 'selectURL']]);
      }
      for (const [prototype, names] of surfaces) {
        for (const name of names) {
          if (typeof prototype?.[name] !== 'function') continue;
          Object.defineProperty(prototype, name, {
            configurable: false,
            value() {
              state.sharedStorageMutationAttempts += 1;
              return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
            },
            writable: false,
          });
        }
      }
    });
    instrument(() => {
      const prototype = Object.getPrototypeOf(navigator);
      for (const name of [
        'joinAdInterestGroup',
        'leaveAdInterestGroup',
        'clearOriginJoinedAdInterestGroups',
        'updateAdInterestGroups',
      ]) {
        if (typeof navigator[name] !== 'function') continue;
        Object.defineProperty(prototype, name, {
          configurable: false,
          value() {
            state.protectedAudienceMutationAttempts += 1;
            return Promise.reject(new DOMException('Blocked by public read-only audit', 'SecurityError'));
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      if (typeof navigator.sendBeacon !== 'function') return;
      Object.defineProperty(Navigator.prototype, 'sendBeacon', {
        configurable: false,
        value() { state.beaconAttempts += 1; return false; },
        writable: false,
      });
    });
    instrument(() => {
      Object.defineProperty(globalThis, 'open', {
        configurable: false,
        value(...args) {
          state.popupAttempts += 1;
          void args;
          return null;
        },
        writable: false,
      });
    });
    instrument(() => {
      for (const name of ['submit', 'requestSubmit']) {
        Object.defineProperty(HTMLFormElement.prototype, name, {
          configurable: false,
          value() {
            state.formSubmissionAttempts += 1;
            return undefined;
          },
          writable: false,
        });
      }
    });
    instrument(() => {
      for (const name of ['Worker', 'SharedWorker']) {
        if (globalThis[name] === undefined) continue;
        Object.defineProperty(globalThis, name, { configurable: false, writable: false, value: class BlockedWorker {
          constructor() {
            state.workerConstructionAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          }
        }});
      }
    });
    instrument(() => {
      if (globalThis.WebSocket !== undefined) {
        Object.defineProperty(globalThis, 'WebSocket', { configurable: false, writable: false, value: class BlockedWebSocket {
          constructor() {
            state.streamingChannelAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          }
        }});
      }
      if (globalThis.WebSocketStream !== undefined) {
        Object.defineProperty(globalThis, 'WebSocketStream', { configurable: false, writable: false, value: class BlockedWebSocketStream {
          constructor() {
            state.streamingChannelAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          }
        }});
      }
      if (globalThis.EventSource !== undefined) {
        Object.defineProperty(globalThis, 'EventSource', { configurable: false, writable: false, value: class BlockedEventSource {
          constructor() {
            state.streamingChannelAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          }
        }});
      }
      if (globalThis.WebTransport !== undefined) {
        Object.defineProperty(globalThis, 'WebTransport', { configurable: false, writable: false, value: class BlockedWebTransport {
          constructor() {
            state.nonHttpChannelAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          }
        }});
      }
      for (const name of ['RTCPeerConnection', 'webkitRTCPeerConnection']) {
        if (globalThis[name] === undefined) continue;
        Object.defineProperty(globalThis, name, { configurable: false, writable: false, value: class BlockedPeerConnection {
          constructor() {
            state.nonHttpChannelAttempts += 1;
            throw new DOMException('Blocked by public read-only audit', 'SecurityError');
          }
        }});
      }
    });
    document.addEventListener('submit', (event) => {
      state.formSubmissionAttempts += 1;
      event.preventDefault();
      event.stopImmediatePropagation();
    }, true);
    document.addEventListener('click', (event) => {
      const anchor = event.target?.closest?.('a[href]');
      const href = anchor?.getAttribute?.('href') ?? '';
      if (/(?:rakuten|r10\\.to|hb\\.afl)/iu.test(href)) {
        state.affiliateNavigationAttempts += 1;
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
  })();`;
}

async function runAxe(connection, axeSource) {
  await evaluate(connection, `${axeSource}\ntrue`);
  return evaluate(
    connection,
    `axe.run(document, {
      runOnly: {
        type: 'tag',
        values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']
      }
    }).then((result) => ({
      incompleteCount: result.incomplete.length,
      criticalCount: result.violations.filter((entry) => entry.impact === 'critical').length,
      seriousCount: result.violations.filter((entry) => entry.impact === 'serious').length,
      violationCount: result.violations.length,
    }))`,
  );
}

async function auditPage(connection, viewport) {
  const result = await evaluate(
    connection,
    `(async () => {
      const visible = (node) => {
        if (node === null || node.getClientRects().length === 0) return false;
        const style = getComputedStyle(node);
        const box = node.getBoundingClientRect();
        return style.display !== 'none'
          && style.visibility !== 'hidden'
          && Number.parseFloat(style.opacity || '1') > 0
          && box.width > 0
          && box.height > 0;
      };
      const markers = [...document.querySelectorAll(
        '[data-raos-v2-package-marker="${PACKAGE_MARKER}"]'
      )];
      const marker = markers.length === 1 ? markers[0] : null;
      const envelopes = [...document.querySelectorAll(
        '[data-raos-v2-post-content-envelope="${CONTENT_ENVELOPE}"]'
      )];
      const disclosure = marker?.querySelector('.raos-v2-decision-support__disclosure') ?? null;
      const ctas = marker === null ? [] : [...marker.querySelectorAll('[data-raos-v2-cta-state]')];
      const blockedCtas = ctas.filter((node) => node.dataset.raosV2CtaState === 'BLOCKED');
      const visibleBlockedCtas = blockedCtas.filter(visible);
      const affiliateAnchors = [...document.querySelectorAll('a[href]')].filter((anchor) => {
        const href = anchor.getAttribute('href') ?? '';
        const rel = (anchor.getAttribute('rel') ?? '').split(/\\s+/u);
        return /(?:rakuten|r10\\.to|hb\\.afl)/iu.test(href) || rel.includes('sponsored');
      });
      const blockedButtons = blockedCtas.filter((node) => {
        const button = node.querySelector('button');
        return button !== null && button.disabled && button.getAttribute('aria-disabled') === 'true' && visible(button);
      });
      const encoder = new TextEncoder();
      const semanticPayload = marker === null
        ? new Uint8Array()
        : encoder.encode(new XMLSerializer().serializeToString(marker));
      const semanticDigest = await crypto.subtle.digest('SHA-256', semanticPayload);
      const markerSemanticSha256 = [...new Uint8Array(semanticDigest)]
        .map((value) => value.toString(16).padStart(2, '0'))
        .join('');
      return {
        affiliateAnchorCount: affiliateAnchors.length,
        blockedButtonCount: blockedButtons.length,
        blockedCtaCount: blockedCtas.length,
        ctaStateCount: ctas.length,
        disclosureComputedVisible: visible(disclosure),
        documentHorizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
        envelopeCount: envelopes.length,
        envelopeContainsMarker: envelopes.length === 1 && marker !== null && marker.parentElement === envelopes[0],
        lang: document.documentElement.lang,
        markerCount: markers.length,
        markerSemanticSha256,
        visibleBlockedCtaCount: visibleBlockedCtas.length,
        viewportWidth: window.innerWidth,
      };
    })()`,
  );
  if (result.markerCount !== 1) fail('PHASE3_PUBLIC_V2_MARKER_MISSING_OR_AMBIGUOUS');
  if (
    result.affiliateAnchorCount !== 0 ||
    result.blockedButtonCount !== 3 ||
    result.blockedCtaCount !== 3 ||
    result.ctaStateCount !== 3 ||
    !result.disclosureComputedVisible ||
    result.documentHorizontalOverflow ||
    result.envelopeCount !== 1 ||
    !result.envelopeContainsMarker ||
    result.lang !== 'ja' ||
    result.visibleBlockedCtaCount !== 3 ||
    result.viewportWidth !== viewport.width
  ) {
    fail(`PHASE3_PUBLIC_VIEWPORT_CONTRACT_INVALID_${viewport.width}`);
  }
  return result;
}

function dispatchTab(connection) {
  return connection
    .call('Input.dispatchKeyEvent', {
      code: 'Tab',
      key: 'Tab',
      type: 'keyDown',
      windowsVirtualKeyCode: 9,
    })
    .then(() =>
      connection.call('Input.dispatchKeyEvent', {
        code: 'Tab',
        key: 'Tab',
        type: 'keyUp',
        windowsVirtualKeyCode: 9,
      }),
    );
}

async function auditKeyboard(connection, viewport) {
  await evaluate(connection, 'document.activeElement?.blur(); window.scrollTo(0, 0); true');
  const focusableCount = await evaluate(
    connection,
    `(() => {
      const selector = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
      return [...document.querySelectorAll(selector)].filter((node) => {
        const style = getComputedStyle(node);
        return node.getClientRects().length > 0
          && style.display !== 'none'
          && style.visibility !== 'hidden'
          && Number.parseFloat(style.opacity || '1') > 0;
      }).length;
    })()`,
  );
  if (focusableCount < 1 || focusableCount > 300) {
    fail(`PHASE3_PUBLIC_KEYBOARD_FOCUSABLE_SET_INVALID_${viewport.width}`);
  }
  const visited = new Set();
  const maximumSteps = focusableCount * 2 + 4;
  for (let step = 0; step < maximumSteps && visited.size < focusableCount; step += 1) {
    await dispatchTab(connection);
    const focused = await evaluate(
      connection,
      `(() => {
        const selector = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
        const visible = [...document.querySelectorAll(selector)].filter((node) => {
          const style = getComputedStyle(node);
          return node.getClientRects().length > 0
            && style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number.parseFloat(style.opacity || '1') > 0;
        });
        const node = document.activeElement;
        const style = getComputedStyle(node);
        const outlineWidth = Number.parseFloat(style.outlineWidth) || 0;
        return {
          browserBoundary: node === document.body || node === document.documentElement,
          focusIndicatorVisible: (style.outlineStyle !== 'none' && outlineWidth > 0)
            || (style.boxShadow !== 'none' && style.boxShadow.length > 0),
          index: visible.indexOf(node),
        };
      })()`,
    );
    if (focused.index < 0) {
      if (focused.browserBoundary) continue;
      fail(`PHASE3_PUBLIC_KEYBOARD_PATH_INVALID_${viewport.width}`);
    }
    if (!visited.has(focused.index)) {
      if (!focused.focusIndicatorVisible) {
        fail(`PHASE3_PUBLIC_KEYBOARD_FOCUS_NOT_VISIBLE_${viewport.width}`);
      }
      visited.add(focused.index);
    }
  }
  if (visited.size !== focusableCount) {
    fail(`PHASE3_PUBLIC_KEYBOARD_TRAVERSAL_INCOMPLETE_${viewport.width}`);
  }
  return Object.freeze({ focusableCount, keyboardOnlyPassed: true });
}

async function auditZoom200Percent(connection, viewport) {
  const result = await evaluate(
    connection,
    `new Promise((resolvePromise) => {
      const root = document.documentElement;
      const originalValue = root.style.getPropertyValue('font-size');
      const originalPriority = root.style.getPropertyPriority('font-size');
      const initialPx = Number.parseFloat(getComputedStyle(root).fontSize);
      root.style.setProperty('font-size', '200%', 'important');
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const zoomedPx = Number.parseFloat(getComputedStyle(root).fontSize);
        const horizontalOverflow = root.scrollWidth > window.innerWidth + 1;
        if (originalValue === '') root.style.removeProperty('font-size');
        else root.style.setProperty('font-size', originalValue, originalPriority);
        resolvePromise({ horizontalOverflow, initialPx, zoomedPx });
      }));
    })`,
  );
  if (
    !Number.isFinite(result.initialPx) ||
    !Number.isFinite(result.zoomedPx) ||
    result.zoomedPx < result.initialPx * 1.9 ||
    result.horizontalOverflow
  ) {
    fail(`PHASE3_PUBLIC_ZOOM_200_PERCENT_INVALID_${viewport.width}`);
  }
  return Object.freeze({ horizontalOverflow: false, zoom200PercentPassed: true });
}

async function auditPersistence(connection) {
  const result = await evaluate(
    connection,
    `Promise.all([
      navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then((items) => items.length) : 0,
      indexedDB.databases ? indexedDB.databases().then((items) => items.length) : 0,
      globalThis.caches ? caches.keys().then((items) => items.length) : 0,
      typeof navigator.storageBuckets?.keys === 'function'
        ? navigator.storageBuckets.keys().then((items) => items.length)
        : 0,
    ]).then(([serviceWorkers, databases, cacheNames, storageBucketNames]) => ({
      attempts: globalThis.__RAOS_V2_PUBLIC_AUDIT__,
      cacheNames,
      cookies: document.cookie,
      databases,
      localStorage: localStorage.length,
      serviceWorkers,
      sessionStorage: sessionStorage.length,
      storageBucketNames,
    }))`,
  );
  const attempts = result.attempts ?? {};
  const attemptCount = Object.values(attempts).reduce(
    (sum, value) => sum + (Number.isInteger(value) ? value : 0),
    0,
  );
  if (
    attemptCount !== 0 ||
    result.cacheNames !== 0 ||
    result.cookies !== '' ||
    result.databases !== 0 ||
    result.localStorage !== 0 ||
    result.serviceWorkers !== 0 ||
    result.sessionStorage !== 0 ||
    result.storageBucketNames !== 0
  ) {
    fail('PHASE3_PUBLIC_BROWSER_PERSISTENCE_CHANGED');
  }
  return Object.freeze({
    cookieCount: 0,
    cacheStorageEntryCount: 0,
    indexedDatabaseCount: 0,
    localStorageEntryCount: 0,
    mutationAttemptCount: 0,
    domStorageMutationEventCount: 0,
    serviceWorkerRegistrationCount: 0,
    sessionStorageEntryCount: 0,
    storageBucketEntryCount: 0,
  });
}

async function captureFullPage(connection, viewport, temporaryCapturesDirectory) {
  const metrics = await connection.call('Page.getLayoutMetrics');
  const content = metrics.cssContentSize;
  const height = Math.ceil(content?.height ?? 0);
  if (height < viewport.height || height > MAX_SCREENSHOT_HEIGHT) {
    fail(`PHASE3_PUBLIC_SCREENSHOT_HEIGHT_INVALID_${viewport.width}`);
  }
  const captured = await connection.call('Page.captureScreenshot', {
    captureBeyondViewport: true,
    clip: { height, scale: 1, width: viewport.width, x: 0, y: 0 },
    format: 'png',
    fromSurface: true,
  });
  if (typeof captured.data !== 'string') fail('PHASE3_PUBLIC_SCREENSHOT_DATA_INVALID');
  const payload = Buffer.from(captured.data, 'base64');
  const dimensions = pngDimensions(payload);
  if (dimensions.width !== viewport.width || dimensions.height !== height) {
    fail(`PHASE3_PUBLIC_SCREENSHOT_DIMENSIONS_INVALID_${viewport.width}`);
  }
  const filename = `carry-on-suitcase-comparison__${viewport.width}.png`;
  const path = join(temporaryCapturesDirectory, filename);
  writeExclusive(path, payload);
  return Object.freeze({
    screenshotBytes: payload.length,
    screenshotHeight: height,
    screenshotSha256: sha256Bytes(payload),
    screenshotWidth: viewport.width,
  });
}

function sanitizedResourceManifest(networkRows) {
  return networkRows
    .map((row) => [
      row.method,
      row.resourceType,
      row.status ?? null,
      row.urlSha256,
      row.fromDiskCache ?? false,
      row.isAffiliate,
      row.isCrossOrigin,
      row.completed,
      row.failed,
    ])
    .sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
}

async function settleInterceptions(tasks) {
  let consumed = 0;
  while (consumed < tasks.length) {
    const pending = tasks.slice(consumed);
    consumed = tasks.length;
    await Promise.all(pending);
  }
}

async function main() {
  if (realpathSync(process.cwd()) !== ROOT) fail('PHASE3_PUBLIC_WORKSPACE_ROOT_REQUIRED');
  if (Number.parseInt(process.versions.node.split('.', 1)[0] ?? '', 10) !== REQUIRED_NODE_MAJOR) {
    fail('PHASE3_PUBLIC_NODE_RUNTIME_MAJOR_INVALID');
  }
  const argumentsValue = parseArguments(process.argv.slice(2));
  const axeSource = loadAxeRuntime();
  const temporaryCapturesDirectory = prepareOutput(argumentsValue);
  let profilePath = null;
  let browser = null;
  let connection = null;
  let evidenceCommitted = false;
  try {
    profilePath = mkdtempSync(join(tmpdir(), 'raos-v2-phase3-public-browser-'));
    const remotePort = await reservePort();
    browser = await launchSandboxedBrowser(
      argumentsValue.browserExecutable,
      remotePort,
      profilePath,
    );
    connection = new CdpConnection(await waitForDebugger(remotePort));
    await connection.open();
    const networkRows = [];
    const rowsByRequestId = new Map();
    const interceptionTasks = [];
    const interceptionFailures = [];
    const popupAttempts = [];
    const unexpectedAttachedTargets = [];
    const nonHttpTransportEvents = [];
    const domStorageMutationEvents = [];
    const responseBrowserStateMutationEvents = [];
    let interceptedRequestCount = 0;
    let documentResponseRequestId = null;
    let documentResponseStatus = null;
    let documentResponseUrlSha256 = null;

    connection.on('Network.requestWillBeSent', (event) => {
      responseBrowserStateMutationEvents.push(
        ...browserStateMutationHeaderNames(event.redirectResponse?.headers),
      );
      const requestUrl = event.request?.url ?? '';
      let parsed;
      try {
        parsed = new URL(requestUrl);
      } catch {
        return;
      }
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return;
      const row = {
        completed: false,
        failed: false,
        fromDiskCache: false,
        isAffiliate: AFFILIATE_URL_PATTERN.test(requestUrl),
        isCrossOrigin: parsed.origin !== TARGET_ORIGIN,
        method: event.request?.method ?? 'UNKNOWN',
        resourceType: event.type ?? 'UNKNOWN',
        status: null,
        urlSha256: sha256Bytes(requestUrl),
      };
      networkRows.push(row);
      rowsByRequestId.set(event.requestId, row);
    });
    connection.on('Network.responseReceived', (event) => {
      responseBrowserStateMutationEvents.push(
        ...browserStateMutationHeaderNames(event.response?.headers),
      );
      const row = rowsByRequestId.get(event.requestId);
      if (row !== undefined) {
        row.status = event.response?.status ?? null;
        row.fromDiskCache = event.response?.fromDiskCache === true;
      }
      if (event.type === 'Document') {
        documentResponseRequestId = event.requestId;
        documentResponseStatus = event.response?.status ?? null;
        documentResponseUrlSha256 = sha256Bytes(event.response?.url ?? '');
      }
    });
    connection.on('Network.loadingFinished', (event) => {
      const row = rowsByRequestId.get(event.requestId);
      if (row !== undefined) row.completed = true;
    });
    connection.on('Network.loadingFailed', (event) => {
      const row = rowsByRequestId.get(event.requestId);
      if (row !== undefined) {
        row.completed = true;
        row.failed = true;
      }
    });
    connection.on('Network.responseReceivedExtraInfo', (event) => {
      responseBrowserStateMutationEvents.push(...browserStateMutationHeaderNames(event.headers));
    });
    connection.on('Network.webSocketCreated', () => {
      nonHttpTransportEvents.push('WEBSOCKET');
    });
    connection.on('Network.webTransportCreated', () => {
      nonHttpTransportEvents.push('WEBTRANSPORT');
    });
    for (const eventName of [
      'DOMStorage.domStorageItemAdded',
      'DOMStorage.domStorageItemRemoved',
      'DOMStorage.domStorageItemUpdated',
      'DOMStorage.domStorageItemsCleared',
    ]) {
      connection.on(eventName, () => {
        domStorageMutationEvents.push(eventName);
      });
    }
    connection.on('Page.windowOpen', () => {
      popupAttempts.push('WINDOW_OPEN');
    });
    connection.on('Target.attachedToTarget', (event) => {
      unexpectedAttachedTargets.push(String(event.targetInfo?.type ?? 'UNKNOWN'));
    });
    connection.on('Fetch.requestPaused', (event) => {
      const task = (async () => {
        interceptedRequestCount += 1;
        const method = String(event.request?.method ?? 'UNKNOWN').toUpperCase();
        const url = event.request?.url ?? '';
        let origin = null;
        try {
          origin = new URL(url).origin;
        } catch {
          origin = null;
        }
        const isAffiliate = AFFILIATE_URL_PATTERN.test(url);
        const isWrite = method !== 'GET' && method !== 'HEAD';
        const isCrossOrigin = origin !== TARGET_ORIGIN;
        const isUnexpectedDocument = event.resourceType === 'Document' && url !== TARGET_URL;
        const exceedsRequestLimit = interceptedRequestCount > MAX_NETWORK_REQUESTS;
        if (
          isAffiliate ||
          isWrite ||
          isCrossOrigin ||
          isUnexpectedDocument ||
          exceedsRequestLimit
        ) {
          interceptionFailures.push(
            isAffiliate
              ? 'AFFILIATE'
              : isWrite
                ? 'WRITE'
                : isCrossOrigin
                  ? 'CROSS_ORIGIN'
                  : isUnexpectedDocument
                    ? 'UNEXPECTED_DOCUMENT'
                    : 'REQUEST_LIMIT',
          );
          await connection.call('Fetch.failRequest', {
            errorReason: 'BlockedByClient',
            requestId: event.requestId,
          });
          return;
        }
        await connection.call('Fetch.continueRequest', { requestId: event.requestId });
      })().catch(() => {
        interceptionFailures.push('INTERCEPTION_ERROR');
      });
      interceptionTasks.push(task);
    });

    await connection.call('Page.enable');
    await connection.call('Runtime.enable');
    await connection.call('Network.enable');
    await connection.call('DOMStorage.enable');
    await connection.call('Accessibility.enable');
    await connection.call('Target.setAutoAttach', {
      autoAttach: true,
      flatten: true,
      waitForDebuggerOnStart: true,
    });
    await connection.call('Fetch.enable', {
      patterns: [{ requestStage: 'Request', urlPattern: '*' }],
    });
    await connection.call('Page.addScriptToEvaluateOnNewDocument', {
      source: storageAuditBootstrapSource(),
    });

    await setViewport(connection, VIEWPORTS[0]);
    await navigate(connection, TARGET_URL);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
    await settleInterceptions(interceptionTasks);
    if (interceptionFailures.length !== 0) fail('PHASE3_PUBLIC_REQUEST_INTERCEPTION_FAILED');
    if (nonHttpTransportEvents.length !== 0) fail('PHASE3_PUBLIC_NON_HTTP_TRANSPORT_DETECTED');
    if ((await evaluate(connection, 'location.href')) !== TARGET_URL) {
      fail('PHASE3_PUBLIC_FINAL_URL_INVALID');
    }
    const documentRows = networkRows.filter((row) => row.resourceType === 'Document');
    if (
      documentRows.length !== 1 ||
      documentRows[0].method !== 'GET' ||
      documentResponseRequestId === null ||
      documentResponseStatus !== 200 ||
      documentResponseUrlSha256 !== sha256Bytes(TARGET_URL)
    ) {
      fail('PHASE3_PUBLIC_DOCUMENT_RESPONSE_INVALID');
    }
    const documentResponse = await connection.call('Network.getResponseBody', {
      requestId: documentResponseRequestId,
    });
    if (typeof documentResponse.body !== 'string') {
      fail('PHASE3_PUBLIC_DOCUMENT_BODY_INVALID');
    }
    const documentBody = Buffer.from(
      documentResponse.body,
      documentResponse.base64Encoded === true ? 'base64' : 'utf8',
    );
    if (documentBody.length <= 0 || documentBody.length > MAX_DOCUMENT_BYTES) {
      fail('PHASE3_PUBLIC_DOCUMENT_BODY_SIZE_INVALID');
    }

    const viewportResults = [];
    for (const viewport of VIEWPORTS) {
      await setViewport(connection, viewport);
      await waitForStableLayout(connection, viewport);
      const page = await auditPage(connection, viewport);
      const axe = await runAxe(connection, axeSource);
      if (
        axe.incompleteCount !== 0 ||
        axe.violationCount !== 0 ||
        axe.criticalCount !== 0 ||
        axe.seriousCount !== 0
      ) {
        fail(`PHASE3_PUBLIC_AXE_WCAG22AA_INVALID_${viewport.width}`);
      }
      const keyboard = await auditKeyboard(connection, viewport);
      const zoom = await auditZoom200Percent(connection, viewport);
      await waitForStableLayout(connection, viewport);
      const capture = await captureFullPage(connection, viewport, temporaryCapturesDirectory);
      viewportResults.push(
        Object.freeze({
          axeCriticalCount: 0,
          axeIncompleteCount: 0,
          axeSeriousCount: 0,
          axeViolationCount: 0,
          blockedCtaCount: page.blockedCtaCount,
          ctaStateCount: page.ctaStateCount,
          disclosureComputedVisible: page.disclosureComputedVisible,
          height: viewport.height,
          horizontalOverflow: false,
          keyboardOnlyPassed: keyboard.keyboardOnlyPassed,
          markerSemanticSha256: page.markerSemanticSha256,
          screenshotBytes: capture.screenshotBytes,
          screenshotHeight: capture.screenshotHeight,
          screenshotPath: join(
            relative(ROOT, argumentsValue.capturesDirectory),
            `carry-on-suitcase-comparison__${viewport.width}.png`,
          ),
          screenshotSha256: capture.screenshotSha256,
          visibleBlockedCtaCount: page.visibleBlockedCtaCount,
          width: viewport.width,
          zoom200PercentPassed: zoom.zoom200PercentPassed,
        }),
      );
    }

    await settleInterceptions(interceptionTasks);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
    await settleInterceptions(interceptionTasks);
    if (interceptionFailures.length !== 0) fail('PHASE3_PUBLIC_REQUEST_INTERCEPTION_FAILED');
    if (nonHttpTransportEvents.length !== 0) fail('PHASE3_PUBLIC_NON_HTTP_TRANSPORT_DETECTED');
    if (networkRows.length > MAX_NETWORK_REQUESTS) fail('PHASE3_PUBLIC_REQUEST_LIMIT_EXCEEDED');
    if (domStorageMutationEvents.length !== 0) {
      fail('PHASE3_PUBLIC_DOM_STORAGE_MUTATION_DETECTED');
    }
    if (responseBrowserStateMutationEvents.length !== 0) {
      fail('PHASE3_PUBLIC_RESPONSE_STATE_MUTATION_DETECTED');
    }
    const finalDocumentRows = networkRows.filter((row) => row.resourceType === 'Document');
    if (
      finalDocumentRows.length !== 1 ||
      finalDocumentRows[0].method !== 'GET' ||
      finalDocumentRows[0].failed ||
      !finalDocumentRows[0].completed
    ) {
      fail('PHASE3_PUBLIC_FINAL_DOCUMENT_SCOPE_INVALID');
    }
    await connection.call('Emulation.setVirtualTimePolicy', { policy: 'pause' });
    const persistence = await auditPersistence(connection);
    const cookies = await connection.call('Network.getAllCookies');
    if (Array.isArray(cookies.cookies) && cookies.cookies.length !== 0) {
      fail('PHASE3_PUBLIC_BROWSER_COOKIE_STORE_CHANGED');
    }
    await connection.call('Runtime.terminateExecution');
    await connection.call('Page.stopLoading');
    await settleInterceptions(interceptionTasks);
    const terminalTarget = await connection.call('Target.getTargetInfo');
    const terminalTargetId = terminalTarget.targetInfo?.targetId;
    if (typeof terminalTargetId !== 'string' || terminalTargetId === '') {
      fail('PHASE3_PUBLIC_TERMINAL_TARGET_INVALID');
    }
    const terminalNetworkCount = networkRows.length;
    const closeResult = await connection.call('Target.closeTarget', {
      targetId: terminalTargetId,
    });
    if (closeResult.success !== true) fail('PHASE3_PUBLIC_TERMINAL_CLOSE_FAILED');
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    await settleInterceptions(interceptionTasks);
    if (
      interceptionFailures.length !== 0 ||
      nonHttpTransportEvents.length !== 0 ||
      networkRows.length !== terminalNetworkCount
    ) {
      fail('PHASE3_PUBLIC_TERMINAL_BOUNDARY_DRIFT');
    }
    const writeRequestCount = networkRows.filter(
      (row) => row.method !== 'GET' && row.method !== 'HEAD',
    ).length;
    const affiliateRequestCount = networkRows.filter((row) => row.isAffiliate).length;
    const unexpectedCrossOriginRequestCount = networkRows.filter((row) => row.isCrossOrigin).length;
    const resourceFailureCount = networkRows.filter(
      (row) =>
        row.resourceType !== 'Document' &&
        (row.failed || !row.completed || typeof row.status !== 'number' || row.status >= 400),
    ).length;
    if (
      writeRequestCount !== 0 ||
      affiliateRequestCount !== 0 ||
      unexpectedCrossOriginRequestCount !== 0 ||
      resourceFailureCount !== 0 ||
      popupAttempts.length !== 0 ||
      unexpectedAttachedTargets.length !== 0
    ) {
      fail('PHASE3_PUBLIC_NETWORK_READ_ONLY_CONTRACT_INVALID');
    }
    const resourceManifest = sanitizedResourceManifest(networkRows);
    const executable = realpathSync(browser.executable);
    const harnessSha256 = await sha256File(SCRIPT_PATH);
    const executableSha256 = await sha256File(executable);
    const commandSha256 = sha256Bytes(
      JSON.stringify([
        process.execPath,
        SCRIPT_RELATIVE,
        '--browser-executable',
        executableSha256,
        '--output',
        relative(ROOT, argumentsValue.outputPath),
      ]),
    );
    const receipt = Object.freeze({
      acceptanceAuthority: false,
      bindings: Object.freeze({
        decodedPublicBodyBytes: documentBody.length,
        decodedPublicBodySha256: sha256Bytes(documentBody),
        publicHttpStatus: 200,
        targetUrlSha256: sha256Bytes(TARGET_URL),
      }),
      browser: Object.freeze({
        axeVersion: REQUIRED_AXE_VERSION,
        commandSha256,
        engine: 'CHROMIUM',
        executableSha256,
        version: await browserVersion(executable),
      }),
      classification: 'OWNER_HELD_RAW_PUBLIC_BROWSER_EVIDENCE',
      criticalIssueCount: 0,
      evidenceClass: 'PUBLIC_READ_ONLY_BROWSER_RAW',
      harness: Object.freeze({
        bytes: lstatSync(SCRIPT_PATH).size,
        path: SCRIPT_RELATIVE,
        sha256: harnessSha256,
      }),
      independentRecalculationStatus: 'PENDING',
      network: Object.freeze({
        affiliateRequestCount: 0,
        formSubmissionCount: 0,
        navigationRequestCount: finalDocumentRows.length,
        nonHttpTransportCount: 0,
        requestCount: networkRows.length,
        requestLimit: MAX_NETWORK_REQUESTS,
        resourceFailureCount: 0,
        resourceManifest,
        resourceManifestSha256: sha256Bytes(JSON.stringify(resourceManifest)),
        serviceWorkerRegistrationCount: 0,
        storageMutationCount: 0,
        unexpectedAttachedTargetCount: 0,
        unexpectedCrossOriginRequestCount: 0,
        writeRequestCount: 0,
      }),
      observedAt: new Date().toISOString(),
      phaseExitEligible: false,
      rawCaptureLocation: 'OWNER_CONTROLLED_OUTPUT_PLAYWRIGHT_NOT_GIT',
      runtime: Object.freeze({
        executableSha256: await sha256File(realpathSync(process.execPath)),
        nodeMajor: REQUIRED_NODE_MAJOR,
        nodeVersion: process.versions.node,
      }),
      schema: RAW_RECEIPT_SCHEMA,
      summary: Object.freeze({
        axeWcag22aaPassed: true,
        computedVisibilityPassed: true,
        keyboardPassed: true,
        markerGatePassed: true,
        persistenceUnchanged: true,
        resourceAndNetworkGatePassed: true,
        zoom200PercentPassed: true,
      }),
      supportHarness: Object.freeze({
        bytes: lstatSync(SUPPORT_HARNESS_PATH).size,
        path: SUPPORT_HARNESS_RELATIVE,
        sha256: await sha256File(SUPPORT_HARNESS_PATH),
      }),
      target: Object.freeze({ origin: TARGET_ORIGIN, route: TARGET_ROUTE }),
      verificationStatus: 'RECORDED_PUBLIC_READ_ONLY',
      version: '1.0.0',
      viewports: Object.freeze(viewportResults),
      persistence,
    });
    connection.close();
    connection = null;
    await stopBrowserProcess(browser);
    browser = null;
    rmSync(profilePath, { force: true, recursive: true });
    profilePath = null;
    commitEvidence(argumentsValue, temporaryCapturesDirectory, receipt);
    evidenceCommitted = true;
    process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
  } finally {
    if (connection !== null) connection.close();
    if (browser !== null) await stopBrowserProcess(browser);
    if (profilePath !== null) rmSync(profilePath, { force: true, recursive: true });
    if (!evidenceCommitted && existsSync(temporaryCapturesDirectory)) {
      rmSync(temporaryCapturesDirectory, { force: true, recursive: true });
    }
  }
}

const invokedPath = process.argv[1] === undefined ? null : realpathSync(resolve(process.argv[1]));
if (invokedPath === SCRIPT_PATH) {
  const operation =
    process.argv[2] === INTERNAL_BROWSER_SUPERVISOR
      ? superviseBrowser(process.argv.slice(3))
      : main();
  operation.catch((error) => {
    process.stderr.write(`${classifiedErrorCode(error)}\n`);
    process.exitCode = 1;
  });
}
