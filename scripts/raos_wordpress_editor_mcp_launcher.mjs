#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { constants as fsConstants } from 'node:fs';
import { access, lstat, mkdir, readFile } from 'node:fs/promises';
import process from 'node:process';

const root = '/home/minami/rakuten';
const secretDirectory = `${root}/.secrets/wordpress-mcp`;
const editorCredential = `${secretDirectory}/editor-application-password.v1.json`;
const operatorCredential = `${secretDirectory}/operator-application-password.v1.json`;
const proxyState = `${secretDirectory}/proxy-state`;
const proxy = `${root}/node_modules/@automattic/mcp-wordpress-remote/dist/proxy.js`;
const proxyPackage = `${root}/node_modules/@automattic/mcp-wordpress-remote/package.json`;
const node = '/home/minami/.nvm/versions/node/v24.18.1/bin/node';
const endpoint = 'https://kurashinoshirube.com/wp-json/raos-codex-mcp/v1/editor';

function refuse() {
  process.stderr.write('WORDPRESS_EDITOR_MCP_LAUNCH_REFUSED\n');
  process.exit(69);
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
  stdio: ['inherit', 'inherit', 'pipe'],
});

child.stderr.resume();
child.once('error', refuse);
child.once('exit', (code, signal) => {
  if (signal) {
    process.removeAllListeners(signal);
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 69);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
