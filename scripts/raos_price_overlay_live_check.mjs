// Contract §8 (changes/reader-purchase-support-v1/price-refresh-contract.md): the local
// price-overlay live check for every Node entry point that can reach the live site (the
// editor MCP launcher and the anonymous browser probes).
//
// It runs the deployment operator's local-only `price-overlay-live-check` command and accepts
// only its exact negative answer. A non-zero exit, a missing interpreter, a timeout, a
// different answer or an extra key all refuse (fail closed). As a CLI it exits 0 when nothing
// may be live and 69 with the refusal code on stderr otherwise.

import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import process from 'node:process';

export const REPOSITORY_ROOT = fileURLToPath(new URL('..', import.meta.url)).replace(/\/+$/, '');
const STATE_INVALID = 'WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID';
const RESULT_CODE = /^[A-Z0-9_]{3,96}$/;
const MAX_OUTPUT_BYTES = 4096;
const TIMEOUT_MS = 120_000;

export function priceOverlayRefusal(root = REPOSITORY_ROOT) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    let child;
    try {
      child = spawn(
        `${root}/.venv/bin/python`,
        ['-B', `${root}/scripts/raos_wordpress_deployment_operator.py`, 'price-overlay-live-check'],
        {
          cwd: root,
          env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', TZ: 'UTC' },
          stdio: ['pipe', 'pipe', 'pipe'],
        },
      );
    } catch {
      finish(STATE_INVALID);
      return;
    }
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      finish(STATE_INVALID);
    }, TIMEOUT_MS);
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
      if (stdout.length > MAX_OUTPUT_BYTES) {
        child.kill('SIGKILL');
        finish(STATE_INVALID);
      }
    });
    child.stderr.on('data', (chunk) => {
      stderr = (stderr + chunk).slice(0, MAX_OUTPUT_BYTES);
    });
    child.once('error', () => {
      clearTimeout(timer);
      finish(STATE_INVALID);
    });
    child.once('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const line = stderr.trim();
        finish(RESULT_CODE.test(line) ? line : STATE_INVALID);
        return;
      }
      let parsed;
      try {
        parsed = JSON.parse(stdout);
      } catch {
        finish(STATE_INVALID);
        return;
      }
      if (
        parsed === null ||
        typeof parsed !== 'object' ||
        Array.isArray(parsed) ||
        Object.keys(parsed).length !== 1 ||
        parsed.price_overlay_live !== false
      ) {
        finish(STATE_INVALID);
        return;
      }
      finish(null);
    });
    child.stdin.on('error', () => {});
    child.stdin.end('{}');
  });
}

export async function refuseWhilePriceOverlayLive(root = REPOSITORY_ROOT) {
  const code = await priceOverlayRefusal(root);
  if (code !== null) {
    process.stderr.write(code + '\n');
    process.exit(69);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await refuseWhilePriceOverlayLive();
}
