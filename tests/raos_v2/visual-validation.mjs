import { createHash } from 'node:crypto';
import {
  closeSync,
  createReadStream,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  writeFileSync,
} from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { ROOT, ROUTES, verifyPreview } from './browser-validation.mjs';

const SCRIPT_PATH = realpathSync(fileURLToPath(import.meta.url));
const REQUIRED_NODE_MAJOR = 24;
const OUTPUT_ROOT = join(ROOT, 'output/playwright');
const VISUAL_VIEWPORTS = Object.freeze([
  Object.freeze({ minimumHeight: 844, name: 'mobile-390', width: 390 }),
  Object.freeze({ minimumHeight: 1024, name: 'tablet-768', width: 768 }),
  Object.freeze({ minimumHeight: 900, name: 'desktop-1440', width: 1440 }),
]);
const ROUTE_CLASSIFICATION = Object.freeze({
  '/': 'PUBLIC_CANDIDATE',
  '/carry-on/': 'PUBLIC_CANDIDATE',
  '/tools/carry-on-size-checker/': 'PUBLIC_CANDIDATE',
  '/guides/carry-on-baggage-rules/': 'PUBLIC_CANDIDATE',
  '/guides/low-cost-carrier-7kg-packing/': 'PLANNED_LOCKED',
  '/carry-on-suitcase-comparison/': 'PUBLIC_CANDIDATE',
  '/guides/carry-on-bag-measurement/': 'PLANNED_LOCKED',
  '/policy/how-we-compare-carry-on-products/': 'PUBLIC_CANDIDATE',
  '/differences/ace-cresta-vs-difference-vs-maxpass4/': 'FIXTURE_ONLY',
});
const ROUTE_SLUG = Object.freeze({
  '/': 'home',
  '/carry-on/': 'carry-on',
  '/tools/carry-on-size-checker/': 'carry-on-size-checker',
  '/guides/carry-on-baggage-rules/': 'carry-on-baggage-rules',
  '/guides/low-cost-carrier-7kg-packing/': 'low-cost-carrier-7kg-packing',
  '/carry-on-suitcase-comparison/': 'carry-on-suitcase-comparison',
  '/guides/carry-on-bag-measurement/': 'carry-on-bag-measurement',
  '/policy/how-we-compare-carry-on-products/': 'how-we-compare-carry-on-products',
  '/differences/ace-cresta-vs-difference-vs-maxpass4/':
    'ace-cresta-vs-difference-vs-maxpass4',
});

class VisualValidationError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
    this.name = 'VisualValidationError';
  }
}

function fail(code) {
  throw new VisualValidationError(code);
}

function outputPath(raw, expectedSuffix) {
  if (raw === null) fail('VISUAL_OUTPUT_REQUIRED');
  const path = resolve(ROOT, raw);
  const fromRoot = relative(OUTPUT_ROOT, path);
  if (
    fromRoot === '' ||
    fromRoot === '..' ||
    fromRoot.startsWith(`..${sep}`) ||
    isAbsolute(fromRoot) ||
    !path.endsWith(expectedSuffix)
  ) {
    fail('VISUAL_OUTPUT_PATH_INVALID');
  }
  return path;
}

function parseArguments(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (
      value === undefined ||
      !['--captures-directory', '--cli-executable', '--receipt'].includes(key) ||
      values.has(key)
    ) {
      fail('VISUAL_ARGUMENT_INVALID');
    }
    values.set(key, value);
  }
  const cliExecutable = values.get('--cli-executable') ?? null;
  if (cliExecutable === null || !isAbsolute(cliExecutable)) {
    fail('VISUAL_CLI_EXECUTABLE_ABSOLUTE_REQUIRED');
  }
  return Object.freeze({
    capturesDirectory: outputPath(values.get('--captures-directory') ?? null, 'cli-captures'),
    cliExecutable: realpathSync(cliExecutable),
    receipt: outputPath(values.get('--receipt') ?? null, '.json'),
  });
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

function writeAtomic(path, value) {
  mkdirSync(dirname(path), { mode: 0o700, recursive: true });
  const temporary = `${path}.tmp-${process.pid}`;
  const descriptor = openSync(temporary, 'wx', 0o600);
  try {
    writeFileSync(descriptor, value, 'utf8');
  } finally {
    closeSync(descriptor);
  }
  renameSync(temporary, path);
}

function routeSlug(route) {
  const slug = ROUTE_SLUG[route];
  if (slug === undefined || !/^[a-z0-9-]+$/u.test(slug)) fail('VISUAL_ROUTE_SLUG_INVALID');
  return slug;
}

function pngDimensions(path) {
  const header = readFileSync(path).subarray(0, 24);
  if (
    header.length !== 24 ||
    !header.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
    header.subarray(12, 16).toString('ascii') !== 'IHDR'
  ) {
    fail('VISUAL_PNG_HEADER_INVALID');
  }
  return Object.freeze({ height: header.readUInt32BE(20), width: header.readUInt32BE(16) });
}

async function main() {
  if (realpathSync(process.cwd()) !== ROOT) fail('VISUAL_WORKSPACE_ROOT_REQUIRED');
  if (Number.parseInt(process.versions.node.split('.', 1)[0] ?? '', 10) !== REQUIRED_NODE_MAJOR) {
    fail('VISUAL_NODE_RUNTIME_MAJOR_INVALID');
  }
  const argumentsValue = parseArguments(process.argv.slice(2));
  const previewDigests = verifyPreview();
  if (Object.keys(ROUTE_CLASSIFICATION).length !== ROUTES.length) {
    fail('VISUAL_ROUTE_CLASSIFICATION_INCOMPLETE');
  }
  const expectedFiles = new Set(
    ROUTES.flatMap((route) =>
      VISUAL_VIEWPORTS.map((viewport) => `${routeSlug(route)}__${viewport.width}.png`),
    ),
  );
  const actualFiles = new Set(
    readdirSync(argumentsValue.capturesDirectory).filter((name) => name.endsWith('.png')),
  );
  if (
    expectedFiles.size !== actualFiles.size ||
    [...expectedFiles].some((name) => !actualFiles.has(name))
  ) {
    fail('VISUAL_CAPTURE_SET_INVALID');
  }
  const captures = [];
  for (const route of ROUTES) {
    for (const viewport of VISUAL_VIEWPORTS) {
      const filename = `${routeSlug(route)}__${viewport.width}.png`;
      const path = join(argumentsValue.capturesDirectory, filename);
      const info = lstatSync(path);
      if (!info.isFile() || info.isSymbolicLink() || info.size < 1024) {
        fail('VISUAL_CAPTURE_FILE_INVALID');
      }
      const dimensions = pngDimensions(path);
      if (dimensions.width !== viewport.width || dimensions.height < viewport.minimumHeight) {
        fail('VISUAL_CAPTURE_DIMENSIONS_INVALID');
      }
      captures.push(
        Object.freeze({
          bytes: info.size,
          classification: ROUTE_CLASSIFICATION[route],
          criticalFindings: null,
          height: dimensions.height,
          majorFindings: null,
          previewSha256: previewDigests[route],
          reviewStatus: 'PENDING_SEPARATE_MANUAL_REVIEW',
          route,
          screenshot: relative(ROOT, path),
          screenshotSha256: await sha256File(path),
          viewport: viewport.name,
          width: dimensions.width,
        }),
      );
    }
  }
  const receipt = Object.freeze({
    captureCount: captures.length,
    captureTool: Object.freeze({
      executableSha256: await sha256File(argumentsValue.cliExecutable),
      name: 'PLAYWRIGHT_CLI_CACHED_OFFLINE_NODE24',
    }),
    captures: Object.freeze(captures),
    classification: 'PENDING_LOCAL_VISUAL_REVIEW',
    commandContract: 'PLAYWRIGHT_CLI_FULL_PAGE_CAPTURE_HASH_BINDING_V1',
    criticalFindings: null,
    externalActions: 'NOT_EXECUTED',
    harnessBytes: lstatSync(SCRIPT_PATH).size,
    harnessPath: relative(ROOT, SCRIPT_PATH),
    harnessSha256: await sha256File(SCRIPT_PATH),
    majorFindings: null,
    reviewBoundary: 'MANUAL_REVIEW_REQUIRED_SEPARATE_RECORD',
    routes: ROUTES.length,
    runtime: Object.freeze({ nodeMajor: REQUIRED_NODE_MAJOR, nodeVersion: process.versions.node }),
    schema: 'RAOS_V2_LOCAL_VISUAL_CAPTURE_RECEIPT_V1',
    viewports: VISUAL_VIEWPORTS.map((viewport) => viewport.name),
  });
  writeAtomic(argumentsValue.receipt, `${JSON.stringify(receipt, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
}

main().catch((error) => {
  const code =
    error instanceof VisualValidationError ? error.code : 'VISUAL_VALIDATION_UNEXPECTED';
  process.stderr.write(`${code}\n`);
  process.exitCode = 1;
});
