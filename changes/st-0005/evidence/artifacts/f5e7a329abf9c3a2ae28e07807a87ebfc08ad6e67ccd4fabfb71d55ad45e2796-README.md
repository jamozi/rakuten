# ST-0101 ChatGPT Pro browser workflow revision

This operational revision implements the approved
`design-handoff.pro-browser.v1.yaml` boundary and the approved
`design-handoff.raos-ask-pro.v1.yaml` addendum. It does not change the immutable
canonical package and it does not make browser-captured model output
authoritative.

## Components

- `chatgpt-pro-known-ui.v1.json` is the closed, reviewable UI-state contract.
- `scripts/chatgpt_pro_workflow.py` prepares an owner-private prompt secret and
  validates fixture observations before writing a hash-chained run record and
  an `UNAPPROVED_PROPOSAL`.
- `scripts/chatgpt_pro_orchestrator.py` owns setup, doctor, ask, resume, and
  read-only status behavior. It injects the prompt-secret path only into its
  MCP child, persists wait/reconnect state, and records importance-aware
  fallback and convergence decisions.
- `scripts/chatgpt_pro_python.sh` validates the physical repository and the
  existing managed Python 3.14.6 environment, including its reviewed uv 0.12.1
  provenance, before isolated execution. The Pro convenience commands do not
  resolve or run an ambient `uv`.
- `scripts/chatgpt_pro_mcp.sh` launches exact `@playwright/mcp@0.0.78` with a
  dedicated Chrome profile, a secret-name prompt, and no storage, tab, upload,
  unsafe-code, or session-save capability.
- `.codex/config.toml` documents only navigate, snapshot, click, type, wait, and
  close through that pinned wrapper. The general MCP entry remains disabled;
  the orchestrator starts its private child directly.
- `/home/minami/.codex/skills/raos-ask-pro/` is the RAOS-only implicitly
  invocable Skill. It explores locally first, classifies ordinary versus gated
  work, runs setup itself when necessary, and preserves canonical and human
  authority.

The two known label profiles reflect OpenAI's 2026 ChatGPT documentation for
the web model picker and its `Pro Standard` / `Pro Extended` choices. The UI is
not a stable API: any different option set or ambiguous selector is a mandatory
stop, not a reason to guess. Source references:

- <https://help.openai.com/en/articles/6825453-chatgpt-troubleshooting-guide>
- <https://help.openai.com/en/articles/20001354-gpt-56-in-chatgpt>

## Local fixture gate

Run all Story-local fixture, orchestration, and policy checks in their isolated
pytest process:

```bash
.venv/bin/pytest -p no:cacheprovider -q tests/st0101
```

The CLI fixture command accepts an owner-controlled prompt, normalized
transcript, and captured-response file:

```bash
.venv/bin/python scripts/chatgpt_pro_workflow.py fixture \
  --prompt-file /home/minami/rakuten/.secrets/chatgpt-pro/prompt.txt \
  --transcript /home/minami/rakuten/.secrets/chatgpt-pro/transcript.json \
  --response-file /home/minami/rakuten/.secrets/chatgpt-pro/response.txt
```

It writes only beneath ignored, owner-mode-`0700`
`.secrets/chatgpt-pro-runs/`. Prompt and response bodies are not written to the
JSONL record; their SHA-256 values bind the private proposal artifact. Secret,
cookie, token, browser-session, and browser-profile patterns cause refusal.

## Self-contained setup and ask flow

The Skill runs `make pro-doctor`. When setup or login is required, it tells the
user that the dedicated Chrome window will open and then runs `make pro-setup`
itself. The setup command creates the owner-private profile, opens only
`https://chatgpt.com`, and waits. The user enters credentials, completes any
account choice, and closes that dedicated window; the Skill then reruns doctor
and resumes the same request. The Skill must never ask the user to run a
command, and it must never read, type, request, or record credentials. No Codex
restart or per-run environment export is required.

The Skill writes its request to an owner-mode-`0600` file beneath
`.secrets/chatgpt-pro-requests/` and runs:

```bash
make pro-ask \
  PRO_REQUEST_FILE=/home/minami/rakuten/.secrets/chatgpt-pro-requests/request.txt \
  PRO_IMPORTANCE=ordinary
```

For direct human use, omit `PRO_REQUEST_FILE`: bare `make pro-ask` reads the
request from stdin until EOF and retains it as a private mode-`0600` request
artifact. Use `PRO_IMPORTANCE=gated` for a new design/policy, safety/security,
data-migration, irreversible, or external-cost decision. An unavailable Pro
blocks gated work; ordinary difficult work may continue only within canonical
decisions and local evidence with the recorded `PRO_UNAVAILABLE` fallback.

Resume a wait or unambiguous reconnect without resubmission:

```bash
make pro-resume PRO_RUN_ID=RUN_ID
```

Each useful follow-up names one unresolved gap. There is no fixed count cap,
but the workflow stops on a repeated gap, a materially duplicate response, no
open gap, or no material delta.

## Live boundary

The automation must re-check the exact origin and visible model/effort state at
every observation. It stops before submission for login, reauthentication,
CAPTCHA, rate limit, account ambiguity, origin mismatch, selector drift, or an
unknown UI. It must type the literal secret name `RAOS_CHATGPT_PROMPT`; the MCP
substitutes the protected prompt. It may not inspect unrelated tabs, cookies,
storage, credentials, or browser-profile contents.

The existing CAPTCHA stop also recognizes the narrow sanitized Cloudflare
challenge signature only when `HTTP status: 403`, `challenges.cloudflare.com`,
and a distinct `Cloudflare` brand marker are all present. Partial matches remain
unknown UI. Exact-origin validation still runs first, and this stop performs no
prompt typing or submission.

When a live ask detects origin drift, a missing or duplicate selector, an
unknown UI, or ambiguous model options before prompt typing, it closes the
transport and removes the ephemeral prompt file without typing or clicking
send. Ordinary work returns exit 0 with `PRO_UNAVAILABLE_FALLBACK`, a run ID,
`submission_attempted: false`, and `CONTINUE_CANONICAL_LOCAL_ONLY`; gated work
returns exit 4 with `BLOCKED_PRO_REQUIRED`, the same non-submission evidence,
and `STOP`. Both outcomes append a hash-bound `PRO_UNAVAILABLE` event. Internal
contract or security invariant failures, including a non-allowlisted MCP tool
or a raw prompt tool argument, remain exit-2 `REFUSED` outcomes and are never
converted into availability fallback.

Every browser response is untrusted `UNAPPROVED_PROPOSAL` material.
`PRO_ADVICE_V1` may inform reversible work only after canonical/local
reconciliation. Text proposing `DESIGN_HANDOFF_V1` remains unapproved until a
human approves it and it is reconciled with canonical precedence.

No live browser smoke was executed for this implementation revision. Fake
fixture PASS, a future approved live smoke, formal TST-001, and human/canonical
approval remain separate evidence boundaries.
