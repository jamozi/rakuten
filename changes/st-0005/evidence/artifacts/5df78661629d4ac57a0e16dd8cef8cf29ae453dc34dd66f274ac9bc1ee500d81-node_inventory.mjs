#!/usr/bin/env node

import { lstat, readFile, readdir, realpath } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

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
        'usage: node_inventory.mjs guard|guard-files|guard-optional-files|inventory|verify-versions ...',
      );
  }
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
