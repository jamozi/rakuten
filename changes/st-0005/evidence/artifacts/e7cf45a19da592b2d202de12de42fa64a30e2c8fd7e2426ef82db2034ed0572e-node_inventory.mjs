#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { constants as fsConstants } from 'node:fs';
import { access, lstat, readFile, readdir, realpath } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const LOCK_MANIFEST_FIELDS = [
  'name',
  'version',
  'license',
  'workspaces',
  'dependencies',
  'devDependencies',
  'optionalDependencies',
  'peerDependencies',
  'peerDependenciesMeta',
  'engines',
];

const UNSUPPORTED_LOCK_MANIFEST_FIELDS = [
  'bundleDependencies',
  'bundledDependencies',
  'acceptDependencies',
  'funding',
  'os',
  'cpu',
  'libc',
  'bin',
  'deprecated',
];

const EXPECTED_LOCK_TOP_LEVEL_KEYS = ['name', 'version', 'lockfileVersion', 'requires', 'packages'];

const EXPECTED_LOCK_MANIFEST_KEYS = ['', 'apps/web', 'packages/web-contracts', 'packages/web-ui'];

function fail(message) {
  process.stderr.write(`error: ${message}\n`);
  process.exitCode = 1;
}

async function statOrNull(target) {
  try {
    return await lstat(target);
  } catch (error) {
    if (error && typeof error === 'object' && error.code === 'ENOENT') {
      return null;
    }
    throw error;
  }
}

async function guardDirectories(targets) {
  let valid = true;
  for (const target of targets) {
    if (!path.isAbsolute(target)) {
      fail(`guard path must be absolute: ${target}`);
      valid = false;
      continue;
    }
    const stat = await statOrNull(target);
    if (stat === null) {
      continue;
    }
    if (stat.isSymbolicLink()) {
      fail(`guarded directory must not be a symbolic link: ${target}`);
      valid = false;
    } else if (!stat.isDirectory()) {
      fail(`guarded path is not a directory: ${target}`);
      valid = false;
    }
  }
  if (!valid) {
    process.exitCode = 1;
  }
}

async function guardFiles(targets, { allowMissing }) {
  let valid = true;
  for (const target of targets) {
    if (!path.isAbsolute(target)) {
      fail(`guard path must be absolute: ${target}`);
      valid = false;
      continue;
    }
    const stat = await statOrNull(target);
    if (stat === null && allowMissing) {
      continue;
    }
    if (stat === null) {
      fail(`required file does not exist: ${target}`);
      valid = false;
    } else if (stat.isSymbolicLink()) {
      fail(`guarded file must not be a symbolic link: ${target}`);
      valid = false;
    } else if (!stat.isFile()) {
      fail(`guarded path is not a regular file: ${target}`);
      valid = false;
    }
  }
  if (!valid) {
    process.exitCode = 1;
  }
}

function isJsonObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function canonicalizeJson(value) {
  if (Array.isArray(value)) {
    return value.map((item) => canonicalizeJson(item));
  }
  if (isJsonObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalizeJson(value[key])]),
    );
  }
  return value;
}

function jsonValuesEqual(left, right) {
  return JSON.stringify(canonicalizeJson(left)) === JSON.stringify(canonicalizeJson(right));
}

function rejectLockManifest(message) {
  throw new Error(message);
}

function manifestHasInstallScript(manifest, source) {
  if (!Object.hasOwn(manifest, 'scripts')) {
    return false;
  }
  if (!isJsonObject(manifest.scripts)) {
    rejectLockManifest(`package scripts must be an object: ${source}:scripts`);
  }
  let hasInstallScript = false;
  for (const script of ['preinstall', 'install', 'postinstall']) {
    if (!Object.hasOwn(manifest.scripts, script)) {
      continue;
    }
    const value = manifest.scripts[script];
    if (typeof value !== 'string' || value.length === 0) {
      rejectLockManifest(
        `package lifecycle script must be a non-empty string: ${source}:scripts.${script}`,
      );
    }
    hasInstallScript = true;
  }
  return hasInstallScript;
}

async function requirePhysicalRegularFile(target, label) {
  if (!path.isAbsolute(target) || path.resolve(target) !== target) {
    rejectLockManifest(`lock manifest path must be absolute and normalized: ${label}`);
  }
  const stat = await statOrNull(target);
  if (stat === null || !stat.isFile() || stat.isSymbolicLink()) {
    rejectLockManifest(`lock manifest path must be a regular non-symlink file: ${label}`);
  }
  const physical = await realpath(target);
  if (physical !== target) {
    rejectLockManifest(`lock manifest path must not traverse a symbolic link: ${label}`);
  }
  return physical;
}

async function readJsonObject(target, source) {
  let parsed;
  try {
    parsed = JSON.parse(await readFile(target, 'utf8'));
  } catch {
    rejectLockManifest(`invalid JSON object: ${source}`);
  }
  if (!isJsonObject(parsed)) {
    rejectLockManifest(`invalid JSON object: ${source}`);
  }
  return parsed;
}

function isCanonicalNodeModulesLocation(location) {
  if (typeof location !== 'string' || location.includes('\\')) {
    return false;
  }
  const segments = location.split('/');
  if (segments.some((segment) => segment === '' || segment === '.' || segment === '..')) {
    return false;
  }

  let index = 0;
  while (index < segments.length) {
    if (segments[index] !== 'node_modules') {
      return false;
    }
    index += 1;
    if (index >= segments.length) {
      return false;
    }

    if (segments[index].startsWith('@')) {
      if (segments[index].length === 1) {
        return false;
      }
      index += 1;
      if (index >= segments.length) {
        return false;
      }
    }

    const packageName = segments[index];
    if (packageName === 'node_modules' || packageName.startsWith('@')) {
      return false;
    }
    index += 1;
  }
  return true;
}

function verifyLockRepositoryStructure(lock) {
  if (lock.lockfileVersion !== 3 || !isJsonObject(lock.packages)) {
    rejectLockManifest('invalid package-lock v3 packages contract: package-lock.json');
  }
  if (lock.requires !== true) {
    rejectLockManifest('package-lock.json requires must be true: package-lock.json');
  }
  const observedTopLevelKeys = Object.keys(lock).sort();
  const expectedTopLevelKeys = [...EXPECTED_LOCK_TOP_LEVEL_KEYS].sort();
  if (!jsonValuesEqual(observedTopLevelKeys, expectedTopLevelKeys)) {
    rejectLockManifest(
      'package-lock.json top-level keys do not match the fixed v3 contract: package-lock.json',
    );
  }
  for (const [packageKey, packageEntry] of Object.entries(lock.packages)) {
    if (typeof packageKey !== 'string' || !isJsonObject(packageEntry)) {
      rejectLockManifest(
        'package-lock.json package entries must have string keys and object values',
      );
    }
    if (
      !EXPECTED_LOCK_MANIFEST_KEYS.includes(packageKey) &&
      !isCanonicalNodeModulesLocation(packageKey)
    ) {
      rejectLockManifest('package-lock.json contains a noncanonical package location');
    }
  }
}

async function verifyLockManifests(lockPath, manifestPaths) {
  if (manifestPaths.length !== EXPECTED_LOCK_MANIFEST_KEYS.length) {
    rejectLockManifest('verify-lock-manifests requires exactly four package manifests');
  }

  const physicalLock = await requirePhysicalRegularFile(lockPath, 'package-lock.json');
  if (path.basename(physicalLock) !== 'package-lock.json') {
    rejectLockManifest('lock manifest filename must be package-lock.json');
  }
  const repositoryRoot = path.dirname(physicalLock);
  const manifests = new Map();

  for (const manifestPath of manifestPaths) {
    const argumentLabel = path.isAbsolute(manifestPath)
      ? 'package manifest'
      : 'relative package manifest';
    const physicalManifest = await requirePhysicalRegularFile(manifestPath, argumentLabel);
    if (!isWithin(physicalManifest, repositoryRoot)) {
      rejectLockManifest('package manifest escapes package-lock.json root');
    }
    if (path.basename(physicalManifest) !== 'package.json') {
      rejectLockManifest('package manifest filename must be package.json');
    }
    const relativeManifest = path
      .relative(repositoryRoot, physicalManifest)
      .split(path.sep)
      .join('/');
    const lockKey = path.posix.dirname(relativeManifest);
    const normalizedKey = lockKey === '.' ? '' : lockKey;
    if (manifests.has(normalizedKey)) {
      rejectLockManifest(`duplicate package manifest key: ${normalizedKey || '.'}`);
    }
    manifests.set(normalizedKey, {
      path: physicalManifest,
      source: relativeManifest,
    });
  }

  const observedKeys = [...manifests.keys()].sort();
  const expectedKeys = [...EXPECTED_LOCK_MANIFEST_KEYS].sort();
  if (!jsonValuesEqual(observedKeys, expectedKeys)) {
    rejectLockManifest('package manifest set does not match the fixed workspace allowlist');
  }

  const lock = await readJsonObject(physicalLock, 'package-lock.json');
  verifyLockRepositoryStructure(lock);

  const rootManifestSource = manifests.get('');
  const rootManifest = await readJsonObject(rootManifestSource.path, rootManifestSource.source);
  for (const field of ['name', 'version']) {
    if (typeof lock[field] !== 'string' || lock[field] !== rootManifest[field]) {
      rejectLockManifest(
        `package-lock.json top-level identity does not match root package manifest: ${field}`,
      );
    }
  }

  const manifestNames = new Set();
  for (const lockKey of EXPECTED_LOCK_MANIFEST_KEYS) {
    const manifestSource = manifests.get(lockKey);
    const manifest =
      lockKey === ''
        ? rootManifest
        : await readJsonObject(manifestSource.path, manifestSource.source);
    if (typeof manifest.name !== 'string' || manifestNames.has(manifest.name)) {
      rejectLockManifest(`duplicate or invalid package manifest name: ${manifestSource.source}`);
    }
    manifestNames.add(manifest.name);

    const locked = lock.packages[lockKey];
    if (!isJsonObject(locked)) {
      rejectLockManifest(`package-lock.json entry is missing or invalid: ${manifestSource.source}`);
    }
    for (const field of UNSUPPORTED_LOCK_MANIFEST_FIELDS) {
      if (Object.hasOwn(manifest, field)) {
        rejectLockManifest(
          `unsupported package manifest lock metadata: ${manifestSource.source}:${field}`,
        );
      }
      if (Object.hasOwn(locked, field)) {
        rejectLockManifest(`unsupported package-lock metadata: ${manifestSource.source}:${field}`);
      }
    }
    if (Object.hasOwn(manifest, 'hasInstallScript')) {
      rejectLockManifest(
        `unsupported package manifest lock metadata: ${manifestSource.source}:hasInstallScript`,
      );
    }
    for (const field of LOCK_MANIFEST_FIELDS) {
      const manifestHasField = Object.hasOwn(manifest, field);
      const lockHasField = Object.hasOwn(locked, field);
      if (
        manifestHasField !== lockHasField ||
        (manifestHasField && !jsonValuesEqual(manifest[field], locked[field]))
      ) {
        rejectLockManifest(
          `package manifest metadata does not match package-lock.json: ${manifestSource.source}:${field}`,
        );
      }
    }
    const expectedHasInstallScript = manifestHasInstallScript(manifest, manifestSource.source);
    const lockHasInstallScript = Object.hasOwn(locked, 'hasInstallScript');
    if (
      expectedHasInstallScript !== lockHasInstallScript ||
      (lockHasInstallScript && locked.hasInstallScript !== true)
    ) {
      rejectLockManifest(
        `package manifest metadata does not match package-lock.json: ${manifestSource.source}:hasInstallScript`,
      );
    }
  }
}

async function requirePhysicalDirectory(target, label) {
  if (!path.isAbsolute(target) || path.resolve(target) !== target) {
    throw new Error(`Python runtime path must be absolute and normalized: ${label}`);
  }
  const stat = await statOrNull(target);
  if (stat === null || !stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`Python runtime path must be a real directory: ${label}`);
  }
  if ((await realpath(target)) !== target) {
    throw new Error(`Python runtime path must not traverse a symbolic link: ${label}`);
  }
}

async function requirePhysicalPythonTarget(target) {
  const parsed = path.parse(target);
  const parts = target.slice(parsed.root.length).split(path.sep).filter(Boolean);
  let current = parsed.root;
  for (const [index, part] of parts.entries()) {
    current = path.join(current, part);
    const stat = await statOrNull(current);
    const isTarget = index === parts.length - 1;
    if (isTarget) {
      if (stat === null || !stat.isFile() || stat.isSymbolicLink()) {
        throw new Error('Python runtime resolved target must be a regular file: .venv/bin/python');
      }
    } else if (stat === null || !stat.isDirectory() || stat.isSymbolicLink()) {
      throw new Error(
        'Python runtime resolved target ancestors must be real directories: .venv/bin/python',
      );
    }
  }
  if (parts.length === 0 || (await realpath(target)) !== target) {
    throw new Error('Python runtime resolved target must be physical: .venv/bin/python');
  }
}

async function verifyPythonRuntime(venvRoot, binDirectory, pythonPath, expectedVersion) {
  if (
    path.basename(venvRoot) !== '.venv' ||
    binDirectory !== path.join(venvRoot, 'bin') ||
    pythonPath !== path.join(binDirectory, 'python')
  ) {
    throw new Error('Python runtime paths must identify the fixed .venv/bin/python hierarchy');
  }
  if (!/^\d+\.\d+\.\d+$/u.test(expectedVersion)) {
    throw new Error('required Python runtime version must be an exact semantic version');
  }

  await requirePhysicalDirectory(venvRoot, '.venv');
  await requirePhysicalDirectory(binDirectory, '.venv/bin');

  const pythonStat = await statOrNull(pythonPath);
  if (pythonStat === null || (!pythonStat.isFile() && !pythonStat.isSymbolicLink())) {
    throw new Error(
      'Python runtime path must be a regular file or resolved symbolic link: .venv/bin/python',
    );
  }
  let physicalPython;
  try {
    physicalPython = await realpath(pythonPath);
  } catch {
    throw new Error('Python runtime leaf must resolve: .venv/bin/python');
  }
  await requirePhysicalPythonTarget(physicalPython);
  try {
    await access(physicalPython, fsConstants.X_OK);
  } catch {
    throw new Error('Python runtime resolved target must be executable: .venv/bin/python');
  }

  const probe = [
    'import json, platform, sys',
    'print(json.dumps({"implementation": platform.python_implementation(),',
    '                  "prefix": sys.prefix,',
    '                  "version": ".".join(str(part) for part in sys.version_info[:3])},',
    '                 sort_keys=True, separators=(",", ":")))',
  ].join('\n');

  let stdout;
  let stderr;
  try {
    ({ stdout, stderr } = await execFileAsync(pythonPath, ['-I', '-c', probe], {
      encoding: 'utf8',
      env: { LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', TZ: 'UTC' },
      maxBuffer: 16 * 1024,
      timeout: 10_000,
    }));
  } catch {
    throw new Error('cannot execute required Python runtime: .venv/bin/python');
  }

  let identity;
  try {
    identity = JSON.parse(stdout.trim());
  } catch {
    throw new Error('required Python runtime returned an invalid identity');
  }
  if (
    stderr !== '' ||
    !isJsonObject(identity) ||
    Object.keys(identity).sort().join(',') !== 'implementation,prefix,version' ||
    identity.implementation !== 'CPython' ||
    identity.version !== expectedVersion ||
    identity.prefix !== venvRoot
  ) {
    throw new Error(
      'required Python runtime identity does not match .venv and exact CPython version',
    );
  }
}

async function readManifest(packageDirectory) {
  const manifestPath = path.join(packageDirectory, 'package.json');
  let parsed;
  try {
    parsed = JSON.parse(await readFile(manifestPath, 'utf8'));
  } catch (error) {
    throw new Error(`cannot read package manifest ${manifestPath}: ${String(error)}`);
  }
  if (
    parsed === null ||
    typeof parsed !== 'object' ||
    Array.isArray(parsed) ||
    typeof parsed.name !== 'string' ||
    typeof parsed.version !== 'string'
  ) {
    throw new Error(`invalid package identity in ${manifestPath}`);
  }
  return { name: parsed.name, version: parsed.version };
}

function isWithin(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..');
}

async function inventory(nodeModulesPath) {
  if (!path.isAbsolute(nodeModulesPath)) {
    throw new Error(`inventory path must be absolute: ${nodeModulesPath}`);
  }
  const rootStat = await statOrNull(nodeModulesPath);
  if (rootStat === null || !rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error(`node_modules must be a real directory: ${nodeModulesPath}`);
  }

  const repositoryRoot = path.dirname(nodeModulesPath);
  const rows = [];

  async function visitModules(modulesDirectory, logicalPrefix = '') {
    const entries = await readdir(modulesDirectory, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name === '.bin' || entry.name === '.package-lock.json') {
        continue;
      }
      const entryPath = path.join(modulesDirectory, entry.name);
      if (entry.name.startsWith('@')) {
        const scopeStat = await lstat(entryPath);
        if (!scopeStat.isDirectory() || scopeStat.isSymbolicLink()) {
          throw new Error(`package scope must be a real directory: ${entryPath}`);
        }
        await visitModules(entryPath, `${logicalPrefix}${entry.name}/`);
        continue;
      }

      const logicalPath = `${logicalPrefix}${entry.name}`;
      const entryStat = await lstat(entryPath);
      let workspace = false;
      if (entryStat.isSymbolicLink()) {
        if (
          logicalPath !== '@raos/web' &&
          logicalPath !== '@raos/web-contracts' &&
          logicalPath !== '@raos/web-ui'
        ) {
          throw new Error(`unexpected symbolic-link package: ${entryPath}`);
        }
        const resolved = await realpath(entryPath);
        if (!isWithin(resolved, repositoryRoot)) {
          throw new Error(`workspace link escapes repository: ${entryPath}`);
        }
        workspace = true;
      } else if (!entryStat.isDirectory()) {
        throw new Error(`unexpected node_modules entry: ${entryPath}`);
      }

      const identity = await readManifest(entryPath);
      if (identity.name !== logicalPath.split('/node_modules/').at(-1)) {
        throw new Error(
          `package path/name mismatch at ${entryPath}: expected ${logicalPath}, found ${identity.name}`,
        );
      }
      rows.push({ path: logicalPath, ...identity, workspace });

      if (!workspace) {
        const nested = path.join(entryPath, 'node_modules');
        const nestedStat = await statOrNull(nested);
        if (nestedStat !== null) {
          if (!nestedStat.isDirectory() || nestedStat.isSymbolicLink()) {
            throw new Error(`nested node_modules must be a real directory: ${nested}`);
          }
          await visitModules(nested, `${logicalPath}/node_modules/`);
        }
      }
    }
  }

  await visitModules(nodeModulesPath);
  rows.sort((left, right) => left.path.localeCompare(right.path, 'en'));
  for (const row of rows) {
    process.stdout.write(
      `${row.path}\t${row.name}\t${row.version}\t${row.workspace ? 'workspace' : 'package'}\n`,
    );
  }
}

async function verifyVersions(nodeModulesPath, specifications) {
  if (!path.isAbsolute(nodeModulesPath)) {
    throw new Error(`node_modules path must be absolute: ${nodeModulesPath}`);
  }
  for (const specification of specifications) {
    const separator = specification.lastIndexOf('=');
    if (separator <= 0 || separator === specification.length - 1) {
      throw new Error(`invalid version specification: ${specification}`);
    }
    const name = specification.slice(0, separator);
    const expected = specification.slice(separator + 1);
    if (
      name.includes('\\') ||
      name.startsWith('/') ||
      name.includes('../') ||
      name.endsWith('/..') ||
      !/^(@[a-z0-9._-]+\/[a-z0-9._-]+|[a-z0-9._-]+)$/u.test(name)
    ) {
      throw new Error(`unsafe package name: ${name}`);
    }
    const manifest = await readManifest(path.join(nodeModulesPath, ...name.split('/')));
    if (manifest.name !== name || manifest.version !== expected) {
      throw new Error(
        `required ${name} version ==${expected}; found ${manifest.name}@${manifest.version}`,
      );
    }
    process.stdout.write(`${name} ${manifest.version}\n`);
  }
}

const [command, ...arguments_] = process.argv.slice(2);

try {
  switch (command) {
    case 'guard':
      if (arguments_.length === 0) {
        throw new Error('guard requires at least one directory');
      }
      await guardDirectories(arguments_);
      break;
    case 'guard-files':
      if (arguments_.length === 0) {
        throw new Error('guard-files requires at least one file');
      }
      await guardFiles(arguments_, { allowMissing: false });
      break;
    case 'guard-optional-files':
      if (arguments_.length === 0) {
        throw new Error('guard-optional-files requires at least one file');
      }
      await guardFiles(arguments_, { allowMissing: true });
      break;
    case 'verify-lock-manifests':
      if (arguments_.length !== 5) {
        throw new Error(
          'verify-lock-manifests requires package-lock.json and exactly four package manifests',
        );
      }
      await verifyLockManifests(arguments_[0], arguments_.slice(1));
      break;
    case 'verify-python-runtime':
      if (arguments_.length !== 4) {
        throw new Error(
          'verify-python-runtime requires .venv, .venv/bin, .venv/bin/python, and an exact version',
        );
      }
      await verifyPythonRuntime(...arguments_);
      break;
    case 'inventory':
      if (arguments_.length !== 1) {
        throw new Error('inventory requires exactly one node_modules directory');
      }
      await inventory(arguments_[0]);
      break;
    case 'verify-versions':
      if (arguments_.length < 2) {
        throw new Error('verify-versions requires node_modules and package=version entries');
      }
      await verifyVersions(arguments_[0], arguments_.slice(1));
      break;
    default:
      throw new Error(
        'usage: node_inventory.mjs guard|guard-files|guard-optional-files|verify-lock-manifests|verify-python-runtime|inventory|verify-versions ...',
      );
  }
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
