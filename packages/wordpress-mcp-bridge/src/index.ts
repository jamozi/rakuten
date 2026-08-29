import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const repositoryRoot = fileURLToPath(new URL('../../..', import.meta.url));
const operator = `${repositoryRoot}/scripts/raos_wordpress_deployment_operator.py`;
const python = `${repositoryRoot}/.venv/bin/python`;
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const releaseProposalIds = z
  .array(sha256)
  .min(1)
  .max(20)
  .refine((values) => new Set(values).size === values.length, {
    message: 'proposal_ids must be unique',
  });
const resultCode = /^[A-Z0-9_]{3,96}$/;

function assertPinnedRuntimePackage(relativePath: string, version: string) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(`${repositoryRoot}/${relativePath}`, 'utf8'));
  } catch {
    throw new Error('WORDPRESS_MCP_RUNTIME_PACKAGE_INVALID');
  }
  if (
    parsed === null ||
    Array.isArray(parsed) ||
    typeof parsed !== 'object' ||
    !('version' in parsed) ||
    parsed.version !== version
  ) {
    throw new Error('WORDPRESS_MCP_RUNTIME_PACKAGE_INVALID');
  }
}

assertPinnedRuntimePackage('node_modules/@modelcontextprotocol/sdk/package.json', '1.30.0');
assertPinnedRuntimePackage('node_modules/zod/package.json', '4.4.3');

type OperatorCommand =
  | 'deployment-status'
  | 'publication-batch-status'
  | 'release-wait-and-apply'
  | 'theme-propose-release'
  | 'plugin-propose-change'
  | 'plugin-apply-change'
  | 'operation-recover';

type OperatorResult = Record<string, unknown>;

class OperatorError extends Error {
  public readonly resultCode: string;

  public constructor(resultCode: string) {
    super(resultCode);
    this.resultCode = resultCode;
  }
}

function runOperator(
  command: OperatorCommand,
  input: Record<string, unknown>,
): Promise<OperatorResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [operator, command], {
      cwd: repositoryRoot,
      env: {
        PATH: '/usr/bin:/bin',
        LANG: 'C.UTF-8',
        LC_ALL: 'C.UTF-8',
        TZ: 'UTC',
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let settled = false;

    const timeoutMs = command === 'release-wait-and-apply' ? 17 * 60_000 : 90_000;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        child.kill('SIGKILL');
        reject(new OperatorError('WORDPRESS_MCP_OPERATOR_TIMEOUT'));
      }
    }, timeoutMs);

    child.stdout.on('data', (chunk: Buffer) => {
      stdoutBytes += chunk.length;
      if (stdoutBytes <= 4 * 1024 * 1024) stdout.push(chunk);
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderrBytes += chunk.length;
      if (stderrBytes <= 4096) stderr.push(chunk);
    });
    child.once('error', () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(new OperatorError('WORDPRESS_MCP_OPERATOR_UNAVAILABLE'));
    });
    child.once('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (stdoutBytes > 4 * 1024 * 1024 || stderrBytes > 4096) {
        reject(new OperatorError('WORDPRESS_MCP_OPERATOR_OUTPUT_INVALID'));
        return;
      }
      if (code !== 0) {
        const candidate = Buffer.concat(stderr).toString('ascii').trim();
        reject(
          new OperatorError(
            resultCode.test(candidate) ? candidate : 'WORDPRESS_MCP_OPERATOR_REFUSED',
          ),
        );
        return;
      }
      try {
        const value: unknown = JSON.parse(Buffer.concat(stdout).toString('utf8'));
        if (value === null || Array.isArray(value) || typeof value !== 'object') {
          throw new Error('invalid');
        }
        resolve(value as OperatorResult);
      } catch {
        reject(new OperatorError('WORDPRESS_MCP_OPERATOR_RESPONSE_INVALID'));
      }
    });
    child.stdin.end(JSON.stringify(input));
  });
}

function toolResult(value: OperatorResult) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(value) }],
    structuredContent: value,
  };
}

function toolError(error: unknown) {
  const code = error instanceof OperatorError ? error.resultCode : 'WORDPRESS_MCP_OPERATOR_FAILED';
  return {
    content: [{ type: 'text' as const, text: JSON.stringify({ code }) }],
    structuredContent: { code },
    isError: true,
  };
}

const server = new McpServer(
  { name: 'raos-wordpress-bridge', version: '1.1.0' },
  {
    instructions:
      'Bounded deployment bridge for kurashinoshirube.com. It cannot approve, publish without a separate wp-admin approval, run commands, PHP, or SQL, delete content, uninstall plugins, accept URLs, or accept caller-selected package paths. Apply calls require an unexpired hash-bound proposal, If-Match, idempotency, the global kill switch, and a proposal-bound single-use approval lease.',
  },
);

server.registerTool(
  'deployment-status',
  {
    title: 'Read WordPress deployment status',
    description:
      'Read the fixed production deployment status, including the active child-theme tree SHA-256. It does not create, approve, or apply anything.',
    inputSchema: z.strictObject({}),
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async () => {
    try {
      return toolResult(await runOperator('deployment-status', {}));
    } catch (error) {
      return toolError(error);
    }
  },
);

server.registerTool(
  'publication-batch-status',
  {
    title: 'Read an exact publication batch status',
    description:
      'Read the server-derived state and precondition barrier for one exact registered publication batch. It never claims or applies a member.',
    inputSchema: z.strictObject({
      batch_token: sha256,
      batch_manifest_sha256: sha256,
      proposal_ids: releaseProposalIds,
    }),
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ batch_token, batch_manifest_sha256, proposal_ids }) => {
    try {
      return toolResult(
        await runOperator('publication-batch-status', {
          batch_token,
          batch_manifest_sha256,
          proposal_ids,
        }),
      );
    } catch (error) {
      return toolError(error);
    }
  },
);

server.registerTool(
  'release-wait-and-apply',
  {
    title: 'Wait for approval and apply one release set',
    description:
      'Wait up to the fixed approval window for one server-registered exact content/theme batch, then apply only that approved batch. At most one theme is accepted and it is always converged before content. Plugin proposals and terminal failure states are refused.',
    inputSchema: z.strictObject({
      batch_token: sha256,
      batch_manifest_sha256: sha256,
      proposal_ids: releaseProposalIds,
    }),
    annotations: {
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ batch_token, batch_manifest_sha256, proposal_ids }) => {
    try {
      return toolResult(
        await runOperator('release-wait-and-apply', {
          batch_token,
          batch_manifest_sha256,
          proposal_ids,
        }),
      );
    } catch (error) {
      return toolError(error);
    }
  },
);

server.registerTool(
  'theme-propose-release',
  {
    title: 'Propose tracked child-theme release',
    description:
      'Build and propose the committed kurashinoshirube-child tree. Caller paths and ZIP files are not accepted.',
    inputSchema: z.strictObject({ idempotency_key: sha256.optional() }),
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
    },
  },
  async (input) => {
    try {
      return toolResult(await runOperator('theme-propose-release', input));
    } catch (error) {
      return toolError(error);
    }
  },
);


server.registerTool(
  'plugin-propose-change',
  {
    title: 'Propose bounded plugin change',
    description:
      'Propose a fixed WordPress.org version or a registered repository artifact. URLs, paths, arbitrary ZIPs, uninstall, and deletion are not accepted.',
    inputSchema: z.strictObject({
      source: z.enum(['wordpress_org', 'repo_artifact']),
      slug: z
        .string()
        .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
        .max(100),
      version: z
        .string()
        .regex(/^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?$/)
        .max(64),
      activation_intent: z.enum(['preserve', 'activate', 'deactivate']),
      artifact_id: z
        .string()
        .regex(/^[a-z0-9][a-z0-9._-]{0,127}$/)
        .optional(),
    }),
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    },
  },
  async (input) => {
    try {
      return toolResult(await runOperator('plugin-propose-change', input));
    } catch (error) {
      return toolError(error);
    }
  },
);

server.registerTool(
  'plugin-apply-change',
  {
    title: 'Apply approved plugin change',
    description:
      'Apply one separately approved eligible plugin proposal with backup, readback, and rollback. Manual-review proposals remain blocked.',
    inputSchema: z.strictObject({ proposal_id: sha256 }),
    annotations: {
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ proposal_id }) => {
    try {
      return toolResult(await runOperator('plugin-apply-change', { proposal_id }));
    } catch (error) {
      return toolError(error);
    }
  },
);

server.registerTool(
  'operation-recover',
  {
    title: 'Recover one WordPress operation',
    description:
      'Reconcile an interrupted operation by its existing operation ID. It never creates a new mutation.',
    inputSchema: z.strictObject({ operation_id: sha256 }),
    annotations: {
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ operation_id }) => {
    try {
      return toolResult(await runOperator('operation-recover', { operation_id }));
    } catch (error) {
      return toolError(error);
    }
  },
);

await server.connect(new StdioServerTransport());
