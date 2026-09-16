// Contract §8 (changes/reader-purchase-support-v1/price-refresh-contract.md): the local
// price-overlay live check for every Node entry point that can reach the live site (the
// editor MCP launcher and the anonymous browser probes).
//
// It runs the deployment operator's local-only `price-overlay-live-check` command and accepts
// only its exact negative answer. A non-zero exit, a missing interpreter, a timeout, a
// different answer or an extra key all refuse (fail closed). As a CLI it exits 0 when nothing
// may be live and 69 with the refusal code on stderr otherwise.

import { spawn } from 'node:child_process';
import { lstatSync, readFileSync, realpathSync } from 'node:fs';
import { isAbsolute, resolve, sep } from 'node:path';
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

// Contract §8: while a run is live, a rendering of a WordPress page (a screenshot, the saved
// HTML, a sha256 of either) outlives a purge that has already reported success unless the
// thing holding it is deleted with the run. Round 9 decided that from the destination's
// *name* (`<64 hex>`, `theme-<64 hex>`, `.staging-*`), but the §5 sweep deletes by content,
// not by name: `owner_direct_candidates_containing` removes a candidate directory only when a
// file inside it carries a price needle, and a full-page PNG holds the prices as pixels. An
// invented or needle-free directory of the right shape was accepted and never deleted.
//
// So the exemption is gone for every caller but one. The anonymous probes and audits call
// `refuseWhilePriceOverlayLive()` directly: while values are published they refuse wherever
// they were going to write, `output/` and `.secrets` alike. The one caller that has to keep
// working while a run is live is the publisher's own run-bound preview - `preview --candidate
// price-overlay:<run>:purge` is how the values come back down - and it writes into the
// candidate directory the run itself deletes. Its exemption is proved from the candidate's
// own binding, never from the directory's name:
//
//   * the destination resolves (through symlinks) into
//     `<OWNER_CHECKOUT>/.secrets/wordpress-mcp/owner-direct-v1/<64 hex>/` - the one base the
//     §5 sweep walks, in the one checkout it walks it in; and
//   * that directory's own `candidate.json` carries a `price_overlay` binding, which is what
//     makes the run delete the directory whole: `delete_local_injected_copies` removes the
//     injected candidate and its frozen preview theme by the id the approval record holds,
//     `_finish_purge` removes the purge candidate by its own id, and both directories carry
//     the injected bytes `owner_direct_candidates_containing` greps for as well.
//
// The verified path is what the function returns, and the caller writes into that value, so a
// destination cannot be proved safe and then swapped for another one.
export const OWNER_CHECKOUT = '/home/minami/rakuten';
export const OWNER_DIRECT_CANDIDATES = '.secrets/wordpress-mcp/owner-direct-v1';
const CANDIDATE_UNIT = /^[0-9a-f]{64}$/;
// raos_wordpress_price_overlay.BINDING_SCHEMA / MODE_PUBLISH / MODE_PURGE / rpr run ids.
const BINDING_SCHEMA = 'RAOS_OWNER_DIRECT_PRICE_OVERLAY_V1';
const BINDING_MODES = new Set(['PUBLISH', 'PURGE']);
const BINDING_RUN_ID = /^[a-z0-9][a-z0-9-]{7,63}$/;
const MAX_CANDIDATE_BYTES = 4 * 1024 * 1024;

/** The path with its deepest existing ancestor resolved, so a symlink cannot fake the prefix. */
function resolvedThroughSymlinks(destination) {
  const parts = resolve(destination).split(sep);
  for (let index = parts.length; index >= 1; index -= 1) {
    const ancestor = parts.slice(0, index).join(sep) || sep;
    try {
      return [realpathSync(ancestor), ...parts.slice(index)].join(sep);
    } catch {
      // Keep walking up; the root always resolves.
    }
  }
  return null;
}

/** `<owner checkout>/.secrets/wordpress-mcp/owner-direct-v1/`, or null when unresolvable. */
function candidateBase() {
  const base = resolvedThroughSymlinks(OWNER_CHECKOUT);
  if (base === null) return null;
  const posix = base.split(sep).join('/').replace(/\/+$/, '');
  return posix === '' ? null : `${posix}/${OWNER_DIRECT_CANDIDATES}/`;
}

/**
 * Whether `directory` is a candidate directory bound to a price-overlay run, read from its own
 * `candidate.json`. Nothing from the file is returned, printed or kept: only the binding's
 * shape decides, and any read or parse failure answers false (fail closed).
 */
function boundToAPriceOverlayRun(directory) {
  let bound;
  try {
    if (!lstatSync(directory).isDirectory()) return false;
    const file = `${directory}/candidate.json`;
    const info = lstatSync(file);
    if (!info.isFile() || info.size > MAX_CANDIDATE_BYTES) return false;
    const parsed = JSON.parse(readFileSync(file, 'utf8'));
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return false;
    bound = parsed.price_overlay;
  } catch {
    return false;
  }
  return (
    bound !== null &&
    typeof bound === 'object' &&
    !Array.isArray(bound) &&
    bound.schema === BINDING_SCHEMA &&
    BINDING_MODES.has(bound.mode) &&
    typeof bound.run_id === 'string' &&
    BINDING_RUN_ID.test(bound.run_id)
  );
}

/** The resolved destination when it is inside a run-bound candidate directory, else null. */
export function boundCandidateDestination(destination) {
  if (typeof destination !== 'string' || destination === '' || !isAbsolute(destination)) {
    return null;
  }
  const resolved = resolvedThroughSymlinks(destination);
  const base = candidateBase();
  if (resolved === null || base === null) return null;
  const posix = resolved.split(sep).join('/');
  // Anchored at the owner checkout, not a substring match: `..` is normalised away by
  // resolve() and a symlink in an existing ancestor is resolved before the compare, so a
  // worktree, a temporary directory or `<root>/output/.secrets/...` is never the swept base.
  if (!posix.startsWith(base)) return null;
  const unit = posix.slice(base.length).split('/')[0];
  if (!CANDIDATE_UNIT.test(unit)) return null;
  return boundToAPriceOverlayRun(`${base}${unit}`) ? resolved : null;
}

/**
 * Refuse a capture whose artifacts would outlive the purge, and answer with the path the
 * caller must write into. Fail closed: a destination that is missing, relative, unresolvable,
 * outside the swept candidate base or inside a directory whose candidate.json carries no
 * price-overlay binding runs the live check like any other capture.
 */
export async function refuseWhilePriceOverlayLiveUnlessBoundCandidate(
  destination,
  root = REPOSITORY_ROOT,
) {
  const bound = boundCandidateDestination(destination);
  if (bound === null) {
    await refuseWhilePriceOverlayLive(root);
  }
  return bound ?? resolve(destination);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await refuseWhilePriceOverlayLive();
}
