#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { constants as fsConstants } from 'node:fs';
import { access, lstat, mkdir, readFile } from 'node:fs/promises';
import process from 'node:process';

import { priceOverlayRefusal } from './raos_price_overlay_live_check.mjs';

const root = '/home/minami/rakuten';
const secretDirectory = `${root}/.secrets/wordpress-mcp`;
const editorCredential = `${secretDirectory}/editor-application-password.v1.json`;
const operatorCredential = `${secretDirectory}/operator-application-password.v1.json`;
const proxyState = `${secretDirectory}/proxy-state`;
const proxy = `${root}/node_modules/@automattic/mcp-wordpress-remote/dist/proxy.js`;
const proxyPackage = `${root}/node_modules/@automattic/mcp-wordpress-remote/package.json`;
const node = '/home/minami/.nvm/versions/node/v24.18.1/bin/node';
const endpoint = 'https://kurashinoshirube.com/wp-json/raos-codex-mcp/v1/editor';
const maximumLineBytes = 64 * 1024 * 1024;

function refuse() {
  process.stderr.write('WORDPRESS_EDITOR_MCP_LAUNCH_REFUSED\n');
  process.exit(69);
}

// Contract §8: this server reads and writes live published content, so no message may reach
// the proxy, and no proxy answer may reach the client, while Rakuten price overlay values may
// be published. The proxy is long lived, so the check runs at startup and again for every
// message in both directions; only the exact negative answer passes (fail closed).
async function priceOverlayCode() {
  return priceOverlayRefusal(root);
}

async function secureJson(path, expectedPurpose) {
  const parent = await lstat(secretDirectory).catch(refuse);
  const metadata = await lstat(path).catch(refuse);
  if (
    parent.isSymbolicLink() ||
    !parent.isDirectory() ||
    (parent.mode & 0o777) !== 0o700 ||
    metadata.isSymbolicLink() ||
    !metadata.isFile() ||
    metadata.nlink !== 1 ||
    (metadata.mode & 0o777) !== 0o600 ||
    (process.geteuid !== undefined &&
      (parent.uid !== process.geteuid() || metadata.uid !== process.geteuid())) ||
    metadata.size < 1 ||
    metadata.size > 16 * 1024
  ) {
    refuse();
  }
  let parsed;
  try {
    parsed = JSON.parse(await readFile(path, 'utf8'));
  } catch {
    refuse();
  }
  if (
    parsed === null ||
    Array.isArray(parsed) ||
    typeof parsed !== 'object' ||
    Object.keys(parsed).sort().join(',') !==
      'application_password,origin,purpose,schema,username' ||
    parsed.schema !== 'RAOS_WORDPRESS_APPLICATION_PASSWORD_V1' ||
    parsed.origin !== 'https://kurashinoshirube.com' ||
    parsed.purpose !== expectedPurpose ||
    typeof parsed.username !== 'string' ||
    parsed.username.length < 1 ||
    typeof parsed.application_password !== 'string' ||
    parsed.application_password.length < 20
  ) {
    refuse();
  }
  return parsed;
}

if (process.cwd() !== root || process.version !== 'v24.18.1') refuse();
const startupRefusal = await priceOverlayCode();
if (startupRefusal !== null) {
  process.stderr.write(startupRefusal + '\n');
  process.exit(69);
}
await access(proxy, fsConstants.R_OK).catch(refuse);
let proxyMetadata;
try {
  proxyMetadata = JSON.parse(await readFile(proxyPackage, 'utf8'));
} catch {
  refuse();
}
if (proxyMetadata?.version !== '0.4.0') refuse();
const editor = await secureJson(editorCredential, 'editor_mcp');
try {
  await access(operatorCredential, fsConstants.F_OK);
  const operator = await secureJson(operatorCredential, 'deployment_operator');
  if (operator.application_password === editor.application_password) refuse();
} catch (error) {
  if (error?.code !== 'ENOENT') refuse();
}
await mkdir(proxyState, { recursive: true, mode: 0o700 }).catch(refuse);
const stateMetadata = await lstat(proxyState).catch(refuse);
if (
  stateMetadata.isSymbolicLink() ||
  !stateMetadata.isDirectory() ||
  (stateMetadata.mode & 0o777) !== 0o700 ||
  (process.geteuid !== undefined && stateMetadata.uid !== process.geteuid())
) {
  refuse();
}

const child = spawn(node, [proxy], {
  cwd: root,
  env: {
    PATH: '/usr/bin:/bin',
    LANG: 'C.UTF-8',
    LC_ALL: 'C.UTF-8',
    TZ: 'UTC',
    NODE_ENV: 'production',
    LOG_LEVEL: '0',
    LOG_TO_STDERR: 'true',
    OAUTH_ENABLED: 'false',
    USE_SYSTEM_PROXY: 'false',
    WP_API_URL: endpoint,
    WP_API_USERNAME: editor.username,
    WP_API_PASSWORD: editor.application_password,
    WP_MCP_CONFIG_DIR: proxyState,
  },
  stdio: ['pipe', 'pipe', 'pipe'],
});

function messageId(line) {
  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
  const id = parsed.id;
  if (typeof id !== 'string' && typeof id !== 'number') return null;
  return id;
}

function errorMessage(id, code) {
  return JSON.stringify({ jsonrpc: '2.0', id, error: { code: -32001, message: code } }) + '\n';
}

// One message at a time per direction, in order: the check for message N finishes before
// message N is forwarded and before message N+1 is checked.
function pump(source, handle) {
  let buffer = '';
  let chain = Promise.resolve();
  let ended = false;
  const queue = (line) => {
    chain = chain.then(() => handle(line));
  };
  source.setEncoding('utf8');
  source.on('data', (chunk) => {
    buffer += chunk;
    if (buffer.length > maximumLineBytes) refuse();
    let index;
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index);
      buffer = buffer.slice(index + 1);
      if (line.trim() !== '') queue(line);
    }
  });
  const finish = () => {
    if (ended) return;
    ended = true;
    if (buffer.trim() !== '') queue(buffer);
    buffer = '';
  };
  source.once('end', finish);
  source.once('close', finish);
  return {
    drained: () =>
      new Promise((resolve) => {
        finish();
        chain.then(resolve, resolve);
      }),
  };
}

const inbound = pump(process.stdin, async (line) => {
  const code = await priceOverlayCode();
  if (code === null) {
    child.stdin.write(line + '\n');
    return;
  }
  const id = messageId(line);
  if (id !== null) process.stdout.write(errorMessage(id, code));
});

const outbound = pump(child.stdout, async (line) => {
  const code = await priceOverlayCode();
  if (code === null) {
    process.stdout.write(line + '\n');
    return;
  }
  const id = messageId(line);
  if (id !== null) process.stdout.write(errorMessage(id, code));
});

process.stdin.once('end', () => {
  inbound.drained().then(() => child.stdin.end());
});
child.stdin.on('error', () => {});

child.stderr.resume();
child.once('error', refuse);
child.once('exit', (code, signal) => {
  outbound.drained().then(() => {
    if (signal) {
      process.removeAllListeners(signal);
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 69);
  });
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
