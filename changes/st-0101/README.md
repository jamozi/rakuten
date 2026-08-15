# ST-0101 ChatGPT Pro browser workflow revision

This operational revision implements the approved
`design-handoff.pro-browser.v1.yaml` boundary and the approved
`design-handoff.raos-ask-pro.v1.yaml` and
`design-handoff.edge-browser.v1.yaml` and
`design-handoff.interactive-auth-wait.v1.yaml` and
`design-handoff.wslg-visible-browser.v1.yaml` and
`design-handoff.initial-ui-settle.v1.yaml` and
`design-handoff.current-pro-ui.v1.yaml` and
`design-handoff.current-response-ui.v1.yaml` and
`design-handoff.response-wait-until-complete.v1.yaml` and
`design-handoff.answer-now-generating.v1.yaml` and
`design-handoff.resilient-pro-review.v1.yaml` and
`design-handoff.summary-verified-pro-answer.v1.yaml` and
`design-handoff.role-scoped-summary-correction.v1.yaml` and
`design-handoff.advanced-button-priority.v1.yaml` and
`design-handoff.semantic-summary-evidence.v1.yaml` and
`design-handoff.closed-selector-diagnostics.v1.yaml` and
`design-handoff.typed-composer-mcp-diagnostics.v1.yaml` and
`design-handoff.hybrid-summary-priority.v1.yaml` addenda. It does not
change the immutable canonical package and it does not make automatically
captured or manually imported model output authoritative.

## Components

- `chatgpt-pro-known-ui.v1.json` is the closed, reviewable UI-state contract.
- `scripts/chatgpt_pro_workflow.py` prepares an owner-private prompt secret and
  validates fixture observations before writing a hash-chained run record and
  an `UNAPPROVED_PROPOSAL`.
- `scripts/chatgpt_pro_orchestrator.py` owns explicit runtime install, setup,
  doctor, ask, resume, no-browser response import, and read-only status
  behavior. It injects the prompt-secret path only into its MCP child, persists
  wait/reconnect state, and records importance-aware fallback, review, and
  convergence decisions.
- `scripts/chatgpt_pro_python.sh` validates the physical repository and the
  existing managed Python 3.14.6 environment, including its reviewed uv 0.12.1
  provenance, before isolated execution. The Pro convenience commands do not
  resolve or run an ambient `uv`.
- `scripts/chatgpt_pro_mcp_runtime/package.json` and its exact npm-11.16.0 lock
  are the only package-install inputs for the owner-private MCP runtime.
- `scripts/chatgpt_pro_mcp_runtime/expected-runtime-inventory.v1.json` anchors
  the exact Linux installed tree; the standalone verifier requires both the
  runtime manifest and a fresh scan to match every committed mode, size, and
  file hash.
- `scripts/chatgpt_pro_mcp.sh` executes exact `@playwright/mcp@0.0.78` only from
  the verified `.secrets/chatgpt-pro-mcp-runtime`, never from a shared `npx`
  cache. It retains the closed Edge/Chrome mapping, passes both the mapped
  Playwright channel and validated fixed executable through `--browser` and
  `--executable-path`, uses a selected dedicated profile and a secret-name
  prompt, independently requires the fixed visible WSLg display, and exposes
  no storage, tab, upload, unsafe-code, or session-save capability.
- `.codex/config.toml` documents only navigate, snapshot, click, type, wait, and
  close through that pinned wrapper. The general MCP entry remains disabled;
  the orchestrator starts its private child directly.
- `/home/minami/.codex/skills/raos-ask-pro/` is the RAOS-only explicitly
  invocable optional-advice Skill. It explores locally first, runs setup itself
  when necessary, and preserves Canonical authority. Complexity, security,
  migration, or policy work does not invoke it implicitly, and its availability
  never blocks repository-local development.

The two legacy label profiles reflect OpenAI's 2026 ChatGPT documentation for
the web model picker and its `Pro Standard` / `Pro Extended` choices. The
strict advanced profile records the separately approved current observed UI.
The UI is not a stable API: any different option set or ambiguous selector is
a mandatory stop, not a reason to guess. Source references:

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

## Owner-private MCP runtime

Runtime hydration is a separate, explicit online maintenance action:

```bash
make pro-runtime-install \
  PRO_NODE=/home/minami/.nvm/versions/node/v24.18.1/bin/node \
  PRO_NPM_CLI=/home/minami/.nvm/versions/node/v24.18.1/lib/node_modules/npm/bin/npm-cli.js
```

The installer accepts only exact Node 24.18.1, npm 11.16.0, the committed
package manifest and exact lock, and `@playwright/mcp@0.0.78`. It installs with
lifecycle scripts disabled into owner-private
`.secrets/chatgpt-pro-mcp-runtime`, records a complete integrity/mode
inventory, and atomically publishes the staged tree while replacing an
owner-scoped drifted runtime entry without following it. A shared
`~/.npm/_npx` tree, including a cached 0.0.79 package, is neither an install
source nor an execution source. An interrupted private stage is recovered or
refused within the install command; it must not be removed manually.

The committed expected inventory is the trust anchor for the complete Linux
runtime, not the mutable installed manifest by itself. Both that manifest and a
fresh no-symlink runtime scan must equal all 217 expected entries before the
private CLI can launch. Do not hand-edit the lock or inventory or regenerate
them with an ambient toolchain, shared cache, different platform, or different
MCP version.

`pro-doctor`, `pro-ask`, `pro-resume`, status, and response import never install
or update packages. They verify the private runtime before any live MCP launch.
Doctor reports a missing runtime as `PRO_RUNTIME_MISSING` with next action
`pro-runtime-install`. Runtime integrity, source, mode, symlink, or exact-
toolchain failure reports status `PRO_RUNTIME_DRIFTED`, preserves the exact
reason `PRO_RUNTIME_DRIFTED`, `PRO_RUNTIME_MODE`,
`PRO_RUNTIME_SOURCE_INVALID`, `PRO_RUNTIME_SYMLINK`, or
`PRO_RUNTIME_TOOLCHAIN_INVALID`, and also directs `pro-runtime-install`.
Transport failures remain distinct:
`PRO_UNAVAILABLE` preserves the launch or disconnect reason, including
`MCP_START_FAILED`, and directs `pro-doctor`. `LOGIN_REQUIRED` directs
`pro-setup`; `STOPPED` directs `STOP`; and `READY` directs `pro-ask`.

## Self-contained setup and ask flow

The Skill runs `make pro-doctor`. When setup is missing or doctor returns
`LOGIN_REQUIRED`, it tells the user which dedicated browser window will open
and runs interactive `make pro-setup` itself. The user completes only ChatGPT
login in that window; the Skill then runs a fresh doctor and requires `READY`
before ask. A `STOPPED` doctor outcome remains `STOP` and never proceeds. Bare
setup uses `PRO_BROWSER=auto`: it selects the fixed Linux Edge
executable `/opt/microsoft/msedge/msedge` when available and checks the fixed
Linux Chrome executable `/opt/google/chrome/chrome` only when Edge is
unavailable before launch. `PRO_BROWSER=edge` and `PRO_BROWSER=chrome` are
explicit fail-closed selections and never fall back. The prior exact
`/opt/google/chrome/google-chrome` setup input remains a closed compatibility
alias that normalizes to the package Chrome binary; arbitrary paths, symlinks,
channels, profile paths, and browser names are refused.

Edge uses `.secrets/chatgpt-pro-edge-profile`; Chrome retains the previously
approved `.secrets/chatgpt-pro-profile`. Both are repository-scoped,
owner-mode-`0700`, ChatGPT-only directories. The workflow never reads, copies,
attaches, or modifies a Windows, personal, default, or other existing browser
profile. Setup persists the selected browser and profile; doctor and ask load
that setup state, while resume loads the browser hash-bound into its run state,
so a resumable run cannot switch browsers. The Skill runs setup rather than
asking the user to run a command, and it never reads, types, requests, or
records credentials. No Codex restart or per-run environment export is
required.

Every live `pro-doctor`, `pro-ask`, and `pro-resume` MCP child is headed and
visible through the single fixed WSLg X11 boundary. Before subprocess creation,
the orchestrator requires the parent `DISPLAY` to be exactly `:0` and requires
fixed `/tmp/.X11-unix/X0` to exist as a real Unix socket, not a symlink or
regular file. It reconstructs the minimal child environment and adds only
`DISPLAY=:0`; it does not inherit Wayland, XDG runtime, D-Bus, PulseAudio, or
other ambient desktop-session values. The wrapper independently rejects a
missing, empty, or non-`:0` display. There is no CLI or Make display input,
alternate display, fallback, or headed/headless option, and the pinned MCP uses
its reviewed default headed mode without `--headless`.

Doctor and ask always capture an immediate snapshot after initial navigation.
They validate the exact origin and all stop states before considering a retry.
Only when that snapshot is on the exact ChatGPT origin, is stop-free, and lacks
a unique required initial known UI may the same transport perform exactly one
fixed five-second wait followed by exactly one new snapshot. There is no click
or type before this retry. The second snapshot receives the complete unchanged
origin, stop-state, and unique-selector validation; persistent unknown UI or
ambiguity stops unsent. This settle applies only to the initial
post-navigation landing and never after a click, model or effort action, type,
or send. It is not an authentication wait and neither consumes nor replenishes
the separate `pro-ask` manual-authentication budget. Its duration and count are
fixed in code, with no CLI, Make, environment, browser-fallback, or retry
configuration.

Microsoft or Edge account login and browser synchronization are neither needed
nor authorized. Authenticate only ChatGPT manually in the visible dedicated
browser window. For `pro-ask`, keep that window open throughout the bounded
manual-authentication interval; **do not close that window**.

Explicit setup examples are:

```bash
make pro-setup PRO_BROWSER=edge
make pro-setup PRO_BROWSER=chrome
```

The Skill writes its request to an owner-mode-`0600` file beneath
`.secrets/chatgpt-pro-requests/` and runs:

```bash
make pro-ask \
  PRO_REQUEST_FILE=/home/minami/rakuten/.secrets/chatgpt-pro-requests/request.txt \
  PRO_IMPORTANCE=ordinary
```

`pro-ask` defaults `PRO_INTERACTIVE_AUTH_WAIT_SECONDS=900` and accepts only
integer values from 0 through 900. The value is parsed and rejected before any
browser child is launched. When the exact ChatGPT origin shows login, CAPTCHA,
reauthentication, or account selection, the same MCP child, transport,
selected browser process, and dedicated profile remain open for that bounded
manual-authentication interval. The user completes the visible action manually
in that window; **do not close that window**. Automation performs only the
already-approved initial navigation, exact-origin snapshots, and bounded waits
until the known authenticated UI appears. It performs no click, type, model or
effort selection, or send while authentication is unresolved. A value of zero
preserves the prior immediate fail-closed behavior.

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

The automation re-checks the exact origin before every page classification and
response observation and visibly verifies the model and effort state before
submission. An authentication timeout stops unsent. Login, reauthentication,
and account selection are trusted only through approved authentication
controls; rate limit and CAPTCHA are trusted only through approved page-level
alert/status/dialog structure or the existing compound Cloudflare challenge.
Matching words inside a bounded assistant response, user message, sidebar,
citation, or other untrusted region do not create a stop state by themselves.
An origin mismatch or structurally recognized stop still stops immediately.
Persistent initial selector drift or unknown UI after the sole initial settle
also stops without entering or extending the authentication wait. For the
strict advanced pre-submission transitions described below, only bounded
observation may continue while their exact expected structure is incomplete.
`pro-doctor` remains read-only and never enters the manual-authentication wait;
its sole allowed wait is the fixed initial settle.
No post-launch state may trigger a cross-browser fallback; fallback exists only
during `auto` setup when Edge is unavailable before launch. The workflow types
the literal secret name `RAOS_CHATGPT_PROMPT`; the MCP substitutes the protected
prompt. It may not use CDP, remote debugging, a browser extension, an existing
browser process, or a personal/default/Windows profile, and it may not inspect
unrelated tabs, cookies, storage, credentials, or browser-profile contents.

For the strict advanced profile, the authenticated landing must contain one
exact top-level `button Pro` and one approved unique composer. Opening that
control may expose a compact view, which expands only through one exact
`menuitem Show advanced options`. Every clicked control is resolved by its
exact raw role and label, must be enabled with exactly one valid ref, and must
not collide with another control required in that snapshot. A malformed,
disabled, duplicate, multiple-ref, or ref-colliding clicked control fails
closed.

In the expanded view, the visibly selected `Model GPT-5.6 Sol` and `Effort Pro`
labels are non-clicked semantic evidence. The resolver first excludes
navigation, sidebar, user, response, citation, and other untrusted regions,
then normalizes only horizontal whitespace within the two labels. Action and
presentation leaf records use the closed `button`, `description`, `heading`,
`link`, `menuitem`, `text`, or `statictext` role boundary. Within it, present
or absent refs and duplicate descendants with the same normalized target value
are equivalent evidence. A `menu`, `listbox`, `dialog`, or generic container
may be named, unnamed, differently named, ref-bearing, ref-free, or absent;
its identity never supplies or competes with evidence. Radio/option child
inventory is equally inert. Missing, wrong-case, edge-padded, renamed, near,
or competing trusted Model or Effort values fail before typing. The exact
target pair is classified before any expand control and makes every valid,
invalid, malformed, duplicate, ref-free, disabled, or inert expand shape
irrelevant; automation neither resolves nor clicks it. The sole safety check on
an ignored exact raw expand candidate rejects `ADVANCED_PRO_BUTTON_INVALID` if
its valid ref-token set contains the used closing Pro ref, because that Pro
action target is no longer collision-safe. Any nonempty partial or
conflicting semantic set also refuses before expansion. Only when both semantic
sets are empty may one exact enabled, ref-bearing expand control define the
compact one-click path; an exact invalid candidate is
`ADVANCED_EXPAND_CONTROL_INVALID`, and no exact candidate is
`ADVANCED_MENU_UNRECOGNIZED`. Automation does not open, enumerate, compare, or
click either child model-option or effort-option menu, and evidence-node refs
never become click targets. New advanced workflow transcripts therefore use an empty ref mapping
for the model and effort evidence states. The validator accepts the predecessor
one-ref shape only when reading an existing transcript and emits no action for
it. The workflow closes the verified expanded surface only through the freshly
resolved unique top-level `button Pro` and requires a closed, stop-free exact-
origin landing with the approved composer before typing.

The initial picker is resolved before any click. `combobox Pro` plus an
approved advanced composer is not an alternate advanced control and refuses in
phase `landing` with no click, type, intent, or Send. This intentionally retires
only the predecessor legacy shape that is structurally indistinguishable from
that wrong-role advanced landing. Independently distinguishable legacy combined
and split profiles remain supported, including their already-approved picker
and post-selection state machines.

Opening the Pro menu, expanding advanced options, closing the verified menu,
and typing the secret-name placeholder each use a bounded observation-only
settle on the same transport. The workflow takes an immediate snapshot and,
only while the expected structure is incomplete, performs at most twelve
additional fixed five-second wait/snapshot observations. Every observation
validates the exact origin and approved structural stops first. A stop or
origin mismatch ends observation immediately; no settle repeats navigate,
click, type, or Send.

Once the exact advanced landing and its picker click are proven, every stop-
free exact-origin post-click menu observation is classified by the advanced
validator before any legacy selector. Its only diagnostic reasons are
`ADVANCED_PRO_BUTTON_INVALID`, `ADVANCED_EXPAND_CONTROL_INVALID`,
`ADVANCED_MENU_STATE_MIXED`, `ADVANCED_MENU_UNRECOGNIZED`,
`ADVANCED_MODEL_EVIDENCE_MISSING`, `ADVANCED_MODEL_EVIDENCE_CONFLICT`,
`ADVANCED_EFFORT_EVIDENCE_MISSING`, and
`ADVANCED_EFFORT_EVIDENCE_CONFLICT`. After the Pro control, any semantic set is
classified before expansion: model missing then conflict, followed by effort
missing then conflict. Only when both sets are empty does the classifier resolve
an exact expand candidate or return the unrecognized code. Exact-origin and
structural-stop checks precede all eight. `ADVANCED_MENU_STATE_MIXED` remains
valid only for verification and status of predecessor hash-bound records; the
current classifier does not emit it for an exact target pair plus any expand
shape.

The code is stored only for an unsent advanced-menu fallback, with the existing
`pro_menu` or `advanced_summary` phase and `submission_attempted: false`.
Hash-bound state and the final event must contain the same exact allowlisted
value before read-only status returns it. Unknown, suffixed, mismatched, or
dynamic values fail state validation; no raw label, role, ref, count, value,
hash, snapshot, sidebar, account, profile, prompt, response, or unrelated URL
is diagnostic data. These codes authorize no action or import. A fully valid
compact menu that remains after the one expand click still ends with generic
`SELECTOR_AMBIGUITY` in `advanced_summary`, and a fully valid expanded menu that
remains after the one close click remains generic in `closed_landing`.
Closed-landing composer/button, typed-composer, Send, independently
distinguishable legacy, and other unclassified failures retain their existing
generic reason.

At the actual `StdioMcpTransport.call("browser_type", ...)` boundary, the
separately approved typed-composer MCP handoff adds only three closed diagnostic
reasons: `MCP_TYPE_REF_STALE`, `MCP_TYPE_ELEMENT_NOT_EDITABLE`, and
`MCP_TYPE_FILL_TIMEOUT`. Classification activates only for an MCP result whose
`isError` value is exactly `true`, whose content is exactly one text block, and
whose non-empty strict UTF-8 text is at most the existing 1 MiB limit. A stale
ref matches only the complete pinned error sentence with one syntactically
valid accessibility ref. The non-editable and fixed 5000 ms `locator.fill`
timeout signatures accept only their complete pinned sentence followed by end
of text or the exact pinned Playwright `Call log:` continuation. Matching is
byte-exact: there is no substring, case-folded, padded, whitespace-normalized,
fuzzy, or version-inferred fallback.

Zero or multiple signature matches, malformed or extra result structure,
empty, invalid-UTF-8, multi-block, non-text, oversized, near, concatenated, and
non-`browser_type` error results retain generic `MCP_CALL_FAILED`. Raw MCP text,
the captured accessibility ref, call-log material, prompt, and secret material
never enter an exception, CLI result, log, hash, state, event, or status. Only
the source-defined closed code may be hash-bound, and validators accept it only
with phase `typed_composer` and `submission_attempted: false`; predecessor
generic `MCP_CALL_FAILED` records remain valid and expose no new state/status
reason field. Each of these three typed-composer codes projects
`next_action: STOP` and matching event `fallback_scope: STOP` for both ordinary
and gated importance. Ordinary importance retains status
`PRO_UNAVAILABLE_FALLBACK` and exit code `0`; gated importance retains
`BLOCKED_PRO_REQUIRED` and exit code `4`. This does not change the existing
advanced diagnostic convention: an ordinary advanced diagnostic still projects
`CONTINUE_CANONICAL_LOCAL_ONLY`. A classification adds no browser call,
snapshot, wait, retry, type replay, intent, Send lookup, Send click, response
capture, or proposal. It is diagnostic evidence only and requires a separately
approved exact follow-on handoff before any correction or new live run.

That final pre-type landing does not require a visible send button. Automation
types only `RAOS_CHATGPT_PROMPT` with `submit: false` and uses the bounded
typed-composer settle before requiring one exact `button Send prompt`. Only
after that reference is known does it durably record
`SUBMISSION_INTENT_RECORDED`, immediately followed by the exact send click. A
missing or ambiguous control, wrong role, origin change, recognized stop, or
transport disconnect before that boundary returns unavailable with
`submission_attempted: false` and no send click. The legacy profiles retain
their existing state machines except for the explicitly retired initial
`combobox Pro` plus approved-composer collision.

For the strict advanced profile only, a completed response requires the exact
raw role `heading`, exact case- and punctuation-sensitive label `ChatGPT said:`,
and one valid structural `[ref=eN]`. Zero or more complete existing-grammar
non-ref accessibility attributes may surround that sole ref. Their names,
order, and non-whitespace values are ignored after structural validation and
contribute no response bytes, refs, stability material, stop evidence,
selectors, actions, persistence, or authority. Any reserved bracketed or
unbracketed `ref` attempt anywhere after the label—including inside another
attribute's name or value—remains invalid unless it is the sole exact lower-
case ref token. Exact-origin and stop checks run first, a generating marker
prevents completion, every parsed ref must be distinct, and any competing
response `article` recognized by the legacy selector is an ambiguity. An
empty/loading snapshot with no assistant marker remains pending. Once any
response-like assistant marker exists, a missing, duplicate, wrong-role,
wrong-case, wrong-punctuation, malformed/residual, ref-colliding, or competing
anchor stops without another input or send action. The selected heading must
be followed immediately by one distinct, same-indent, unlabeled
`generic [ref=...]:` response-body root. Extraction remains inside that root
and stops before the first non-empty same- or shallower-indent line.

Within that bounded subtree, exact lower-case `text:` and `statictext:` payloads
may occur below an approved semantic paragraph, list, list item, quote,
heading, or code node, or through only the body root and generic presentation
containers. Each payload is exactly one JSON string literal. Direct and
generic-only fragments form one deterministic body-root paragraph. Decoded
fragments within one semantic block are concatenated in snapshot order without
an invented separator; distinct semantic blocks are joined with deterministic
newlines. To preserve the approved predecessor bytes, an enclosing semantic
list owns its nested list-item fragments; a standalone list item is a semantic
block only when no enclosing list exists.

One exact `group "Response actions":` is allowed in either of two positions,
but there is still only one total group. It may be strictly nested before any
response content when later valid non-whitespace sibling content exists inside
the same exact body, or it may occur after content inside the body or at the
first same- or shallower-indent boundary. The complete exact action subtree is
opaque to response bytes, refs, assistant and generating markers, stability,
stop evidence, selectors, and actions. Action-looking descendants inside that
subtree do not count as another group. Complete button, link, citation, URL-
metadata, and approved structural-container chrome remains opaque even when
ref-free; unknown boundary chrome containing independently visible response
material is a boundary conflict. A same/shallow pre-content group, no later
content after a pre-content group, a second visible group, content after a
post-content group, malformed/ref-bearing/attributed/near action forms,
malformed payload or scalar syntax, duplicate or malformed required anchors,
outer heading/body ref collisions, boundary escape, empty output, excessive
size, and sensitive content refuse before persistence.

An exact `PRO_ADVICE_V1` JSON object retains its existing structured validation
and convergence behavior. A single lower-case `json` code fence with only
surrounding whitespace is also accepted when the decoded fence body is an exact
valid `PRO_ADVICE_V1`. The structured response fingerprint is computed from
canonical JSON, while the raw captured-response hash and raw proposal body are
retained. Multiple fences, prose-wrapped JSON, and malformed purported
`PRO_ADVICE_V1` are refused rather than reclassified as text review.

Any other stable, non-empty, non-sensitive Markdown or plain text is captured
as `PRO_REVIEW_TEXT_V1` with status `REVIEW_CAPTURED` and authority
`UNAPPROVED_REVIEW`. It remains a hash-bound `UNAPPROVED_PROPOSAL`; merely
naming `DESIGN_HANDOFF_V1` cannot promote it to an approved handoff. Ordinary
reversible work returns
`RECONCILE_CANONICAL_LOCAL`; gated design, policy, safety, security, migration,
irreversible, or external-cost work returns `HUMAN_APPROVAL_REQUIRED`. Legacy
profiles retain their predecessor article selector and parser. These are
tool-local classifications retained for compatibility; the root `AGENTS.md`
standing development authorization determines whether repository work
continues.

After the one approved send click, ask keeps that MCP transport, the selected
dedicated browser, and the same window open while the response is absent,
generating, or changing. It takes an immediate snapshot, then repeats exactly
`browser_wait_for {"time": 5}` followed by `browser_snapshot` with no response
duration or retry limit. Response latency never creates an ordinary `WAITING`
result and never closes the window. The separate interactive-authentication
budget remains bounded to at most 900 seconds and is not a response timeout.
There is no response-timeout, response-duration, or retry-count input in the
CLI, Make, environment, or UI contract.

An empty/loading snapshot or a known generating marker remains pending. For the
strict `gpt-5.6-sol-pro-advanced-v1` profile only, the exact accessible element
`button "Answer now"` is an additional generating marker. It must have the
exact lower-case role, case-sensitive label, spacing, punctuation, and ordinary
ref-only element shape. It is observation-only: automation never clicks it.
Wrong roles, case, punctuation, label whitespace, prefixes, suffixes,
attributes, duplicated tokens, text/statictext payloads, and every legacy
profile do not qualify. Multiple exact matching controls fail closed as
response-selector ambiguity. Existing predecessor generating markers remain
unchanged.

While the exact advanced marker exists, the stability sequence resets and the
strict parser is not called, including when `heading "ChatGPT said:"` and a
temporarily empty body root are already present. Once it disappears, a
response-like candidate is normalized only from the bounded assistant-response
subtree used by the strict parser. Volatile accessibility refs are replaced by
in-memory aliases, all outside content is excluded, and the result is hashed
only in memory. The candidate must have the same digest in three consecutive
snapshots at the fixed five-second interval, spanning at least ten seconds.
Any semantic change resets the sequence. Only a stable candidate reaches the
selected advanced or legacy parser. Polling snapshots, response subtrees,
volatile refs, outside content and URLs, and stability digests are never
written to a run artifact or log.

While a response remains pending, the existing hash-bound state/event
publication records one sanitized `RESPONSE_WAIT_PROGRESS` event after each
complete 60 seconds of fixed polling. Its explicit payload contains only
`elapsed_seconds`, `poll_count`, and the closed phase value
`response_absent`, `response_generating`, or `candidate_stabilizing`; the
ordinary state publication adds only its existing `state_sha256`. Progress
does not create `WAITING`, close the browser, change the five-second cadence,
or impose a timeout, and it never contains a prompt, response, snapshot,
subtree, accessibility ref, URL, or digest.

A stable valid structured advice or text review is finalized and its
hash-bound state/event pair is made durable before browser cleanup. A stable
invalid, sensitive, unidentifiable, or ambiguous response enters the sanitized
importance-aware unavailable boundary without creating a proposal, and that
terminal state/event pair is also durable before cleanup. Ordinary unavailability
returns exit 0 with `PRO_UNAVAILABLE_FALLBACK` and
`CONTINUE_CANONICAL_LOCAL_ONLY`; gated unavailability returns exit 4 with
`BLOCKED_PRO_REQUIRED` and `STOP`. Structurally trusted login,
reauthentication, CAPTCHA, account-ambiguity, and page-level rate-limit states,
plus origin drift, keep their fail-closed outcomes. Contract, security, state,
and non-response invariant failures remain hard exit-2 refusals.

An explicit operator interrupt in the response-observation loop records
resumable `WAITING`, the latest checked exact-origin `/c/...` conversation
binding, and `resubmit_allowed: false` before the browser closes. This guarantee
begins only after the polling loop has observed that binding. An interrupt or
disconnect while Send is in flight or before the first bound conversation is
observable records the predecessor `SUBMISSION_AMBIGUOUS`/no-resubmit boundary
without claiming a conversation URL; live resume refuses that unbound run
before creating a transport. A post-binding transport loss retains `WAITING`
and never triggers an automatic submission.

Resume inspects only a bound conversation: one navigate and an immediate
snapshot followed by the same unbounded fixed five-second snapshot loop, then
close after a durable outcome or an observation-loop interrupt. It updates the
binding only from a newly checked exact-origin `/c/...` URL and never types,
clicks Send, or resubmits. A resume-created terminal event/result records
`resubmitted: false`; its pending transcript is retained on failure and removed
only after successful predecessor WAITING finalization.

`pro-resume` also has one response-only terminal-recovery path. It is eligible
only when the verified LIVE state and hash chain bind one exact `/c/...` URL,
browser, prompt hash, exactly one `SUBMISSION_INTENT_RECORDED` for
`GPT-5.6 Sol` with effort `Pro`, and a final `PRO_UNAVAILABLE` reason exactly
`RESPONSE_NOT_IDENTIFIABLE` or `RESPONSE_SELECTOR_AMBIGUITY`. The final parser
terminal may be followed only by verified `RESPONSE_WAIT_PROGRESS` events for
that unchanged state. A missing, duplicate, malformed, or mismatching intent,
wrong reason, intervening event, state/hash/binding drift, non-LIVE run, or
unsafe proposal refuses before browser launch.

Terminal recovery uses only navigate to that exact bound URL, snapshot, the
existing fixed five-second wait/snapshot loop, and close. It neither reads nor
modifies any pending transcript and creates no type, click, Send, submission
intent, or resubmission evidence. Its 60-second progress events carry the
unchanged terminal state hash and never rewrite the state. On success it
atomically creates the owner-only existing proposal format, then appends
`BOUND_RESPONSE_RECOVERED` as the sole commit point with provenance
`AUTOMATED_BOUND_CONVERSATION_RECOVERY`, the source terminal event hash, the
proposal hash, and `resubmitted: false`; the terminal state remains byte-for-
byte unchanged. Read-only status projects the effective captured advice/review,
authority, and next action only from that fully verified event plus proposal.
An exact orphan proposal left before the commit event is status-invisible and
may be committed on retry only after exact schema, bytes, hash, source,
provenance, owner, and mode verification; a mismatch refuses without overwrite.
A fully verified committed recovery is idempotent and opens no browser.

Only an uncaught strict advanced-response parser refusal from that exact
eligible terminal-recovery path may add `diagnostic_code` to the CLI refusal.
Its existing generic `reason_code` remains `RESPONSE_SELECTOR_AMBIGUITY` or
`RESPONSE_NOT_IDENTIFIABLE`. The closed diagnostic values are exactly:

- `ADVANCED_RESPONSE_GENERATING_MARKER_DUPLICATION`
- `ADVANCED_RESPONSE_MARKER_CONFLICT`
- `ADVANCED_RESPONSE_STRUCTURAL_REF_COLLISION`
- `ADVANCED_RESPONSE_HEADING_INVALID`
- `ADVANCED_RESPONSE_BODY_ROOT_ABSENT`
- `ADVANCED_RESPONSE_BODY_ROOT_INVALID`
- `ADVANCED_RESPONSE_BOUNDARY_CONFLICT`
- `ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID`
- `ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID`

The code is selected from source literals only; no label, role, ref, URL,
count, line, response fragment, snapshot, hash, or exception text enters it.
An invalid attached value is omitted while the generic reason remains
unchanged. The diagnostic creates no proposal or failure event and changes no
state. It is never stored or projected by normal ask, ordinary `WAITING`
resume, legacy response parsing, status, state, events, proposals, manual
import, or unrelated terminal resume. A recovery progress publication remains
the only permitted durable side effect before a later retry.

Only when the generic reason is exactly `RESPONSE_SELECTOR_AMBIGUITY` and the
parent recovery diagnostic is exactly `ADVANCED_RESPONSE_HEADING_INVALID` may
the CLI add `diagnostic_detail_code`. Its closed values are exactly:

- `ADVANCED_RESPONSE_HEADING_ROLE_INVALID`
- `ADVANCED_RESPONSE_HEADING_LABEL_CASE_INVALID`
- `ADVANCED_RESPONSE_HEADING_LABEL_PUNCTUATION_INVALID`
- `ADVANCED_RESPONSE_HEADING_LABEL_EDGE_WHITESPACE_INVALID`
- `ADVANCED_RESPONSE_HEADING_LABEL_OTHER_INVALID`
- `ADVANCED_RESPONSE_HEADING_REF_MISSING`
- `ADVANCED_RESPONSE_HEADING_REF_INVALID`
- `ADVANCED_RESPONSE_HEADING_EXTRA_ATTRIBUTES`
- `ADVANCED_RESPONSE_HEADING_LINE_SHAPE_INVALID`

The diagnostic-only precedence is raw role; ASCII space/tab edge whitespace;
pure case; a changed, missing, or repeated terminal ASCII `: . ! ?` run;
other label; no structural ref attempt; malformed, invalid, or multiple ref
attempts; the predecessor extra-attribute compatibility category; then residual
line shape. Complete non-ref heading attributes are now valid, so
`ADVANCED_RESPONSE_HEADING_EXTRA_ATTRIBUTES` remains allowlisted only for
predecessor validator compatibility and is not emitted for accepted forms. A
second distinct trusted response-marker line wins as
`ADVANCED_RESPONSE_MARKER_CONFLICT`, even if it shares a ref, and receives no
heading detail. The same physical wrong-role marker is classified once rather
than counted twice. This detail never changes response acceptance, contains no
observed role/label/ref/attribute/count/line data, and grants no authority.
Missing, invalid, padded, suffixed, case-varied, wrong-parent, or wrong-reason
details are omitted while preserving the generic reason and valid parent
diagnostic. Like its parent, the field is recovery-only and non-persistent: it
never enters normal ask, ordinary `WAITING` resume, legacy parsing, manual
import, status, state, events, proposals, or unrelated terminal resume.

When the generic reason is exactly `RESPONSE_NOT_IDENTIFIABLE` and the parent
recovery diagnostic is exactly
`ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID`, the same CLI-only field has this
separate closed action set:

- `ADVANCED_RESPONSE_ACTION_ROLE_INVALID`
- `ADVANCED_RESPONSE_ACTION_LABEL_INVALID`
- `ADVANCED_RESPONSE_ACTION_REF_PRESENT`
- `ADVANCED_RESPONSE_ACTION_EXTRA_ATTRIBUTES`
- `ADVANCED_RESPONSE_ACTION_LINE_SHAPE_INVALID`
- `ADVANCED_RESPONSE_ACTION_PRE_CONTENT`
- `ADVANCED_RESPONSE_ACTION_DUPLICATE`
- `ADVANCED_RESPONSE_ACTION_CONTENT_AFTER`
- `ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID`

Action classification is diagnostic-only and follows the current first-failing
line. On one trusted Response-actions-like physical line, raw role precedes the
exact case-, punctuation-, and edge-sensitive label; any reserved structural
ref attempt precedes removable complete existing-grammar non-ref attributes in
their structural position before the terminal colon; residual syntax follows.
Only after that local syntax is exact may the lifecycle state apply. A valid
pre-content group is provisional: later valid content succeeds, a later
encountered defect keeps its existing category, and `PRE_CONTENT` applies only
at a clean end with no valid content. Duplicate and content-after failures stay
decisive; the classifier never scans beyond a decisive failure, and untrusted
candidates retain only the generic parent refusal.
`ADVANCED_RESPONSE_ACTION_PLACEMENT_INVALID` remains reserved for closed-
validator compatibility and is not emitted by the current parser.

Complete attributes after the colon, malformed or unclosed attributes, and
other residual text remain line-shape invalid. A missing, unknown, padded,
suffixed, case-varied, wrong-parent, or wrong-reason value is omitted without
changing the generic reason or parent diagnostic. The detail contains no raw
role, label, ref, attribute, count, indentation, line, snapshot, URL, response,
or exception data; changes no action-boundary acceptance; and never enters
normal ask, ordinary `WAITING` resume, legacy parsing, manual import, status,
state, events, proposals, unrelated terminal resume, or committed recovery.

Only the exact recovery conjunction `RESPONSE_NOT_IDENTIFIABLE` /
`ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID` /
`ADVANCED_RESPONSE_ACTION_PRE_CONTENT` may additionally carry one CLI-only
`diagnostic_context_code` from this exact closed set:

- `ADVANCED_RESPONSE_PRECONTENT_SAME_INDENT_BOUNDARY`
- `ADVANCED_RESPONSE_PRECONTENT_SHALLOW_BOUNDARY`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_CONTENT`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_ONLY_OPAQUE`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_EMPTY`

Placement wins first: a group at the body indent is same-indent and a shallower
group is shallow. For a strictly nested group that already reached the existing
`PRE_CONTENT` refusal, classification examines only the already bounded group
subtree and owned later siblings up to the existing body boundary. Invalid
response-bearing scalar or semantic material wins over valid content. Content
requires all response-bearing material to use valid exact JSON-string payloads
and at least one decoded fragment to be non-whitespace and UTF-8 encodable.
Empty or whitespace-only valid payloads are empty, or opaque-only when complete
approved chrome is also present. A structurally valid generic or semantic
response container without an exact payload remains invalid even if its only
descendants are opaque. Complete opaque chrome without any response-bearing
container, scalar, or payload is opaque-only; an otherwise clean group is
empty.

This context is sanitized diagnosis, not response content or authority. It
contributes no bytes and changes no parser acceptance, action opacity, body
boundary, ref, stop, stability, proposal, or recovery rule. Missing, unknown,
padded, suffixed, case-varied, or wrong-conjunction context is omitted while
the existing valid generic reason, parent, and detail remain. Context never
enters normal ask, ordinary `WAITING`, legacy/manual paths, status, state,
events, proposals, unrelated terminal resume, or committed recovery.

Only when the exact existing fields are `RESPONSE_NOT_IDENTIFIABLE` /
`ADVANCED_RESPONSE_ACTION_BOUNDARY_INVALID` /
`ADVANCED_RESPONSE_ACTION_PRE_CONTENT` /
`ADVANCED_RESPONSE_PRECONTENT_NESTED_DESCENDANT_INVALID` may recovery add one
CLI-only, non-persistent `diagnostic_context_detail_code` from this exact set:

- `ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_SHAPE_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_VALUE_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_CONTEXT_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_WITH_CONTENT`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_UNSATISFIED_EMPTY`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_MATERIAL_UNSUPPORTED`

Classification reads only the already bounded material used by the predecessor
nested-invalid context classifier. An already-invalid text/statictext-like
candidate with bad exact role/line/payload shape is scalar-shape invalid; a
shaped payload that is not one JSON string or is not UTF-8 encodable is
scalar-value invalid. A generic/semantic container failing its exact element
grammar is container-shape invalid, while any other visible nonblank material
outside approved opaque/untrusted regions is unsupported. Explicit defects
globally precede deferred unsatisfied-container detection and the first physical
explicit defect wins. Only when no explicit defect exists does the first
unsatisfied container select with-content when another valid non-whitespace,
UTF-8-encodable fragment exists, otherwise empty.

`ADVANCED_RESPONSE_PRECONTENT_NESTED_SCALAR_CONTEXT_INVALID` remains closed
validator-compatibility vocabulary and is not reachable on the current proven
production parser path. Complete bare `text:` or `statictext:` structural-
container forms, including trailing whitespace, preserve the predecessor
opaque-only context and emit no fifth field. Missing, unknown, padded, suffixed,
case-varied, or wrong-conjunction values omit only the fifth field. This detail
contains no raw UI data, grants no authority, changes no parser acceptance,
response byte, opacity, body, ref, stop, stability, action, proposal, or
recovery rule, and never enters normal ask, ordinary `WAITING`, legacy/manual
paths, status, state, events, proposals, unrelated terminal resume, or committed
recovery.

Only when the five existing fields end in
`ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_SHAPE_INVALID` may recovery add
one CLI-only, non-persistent `diagnostic_context_shape_code` from this exact
set:

- `ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_LINE_SHAPE_INVALID`

This sixth classifier reads only the first physical generic/semantic container
line already selected by the predecessor as container-shape invalid. Within
that selected population, ref-like text inside a valid JSON-quoted label is
label material. Outside the label, any reserved malformed bracketed or
unbracketed ref attempt is ref-invalid; with no ref attempt, one otherwise
complete ref-free existing-grammar container record is ref-missing; every
remaining selected shape is line-shape invalid. A line that the predecessor
already treats as a valid-ref unsatisfied container—including a valid ref found
only by that predecessor or a recognized valid ref plus an extra malformed or
duplicate attempt—keeps its existing fifth field and receives no sixth field.

Missing, unknown, padded, suffixed, case-varied, or wrong-conjunction shape is
omitted while the first five valid fields remain. The shape contains no raw or
dynamic UI data, grants no authority, changes no acceptance, bytes, opacity,
body, ref, stop, stability, action, proposal, or recovery rule, and never enters
normal ask, ordinary `WAITING`, legacy/manual paths, status, state, events,
proposals, unrelated terminal resume, or committed recovery.

One later recovery-only acceptance path is available only when the full six-
field chain ends in
`ADVANCED_RESPONSE_PRECONTENT_NESTED_CONTAINER_REF_MISSING`. The parser then
reuses the already-selected strictly nested exact action-group bounds and
validates only that group's descendants. Complete ref-free generic or existing
semantic presentation wrappers are accepted; a complete wrapper may instead
carry one sole exact lower-case structural ref that is unique within the
embedded response and collision-free against every trusted non-action ref.
Optional valid JSON labels and complete non-ref attributes are structural only.
Each exact lower-case `text:` or `statictext:` payload is one UTF-8-encodable
JSON string under body/generic/semantic ancestry. Every admitted wrapper must
own at least one valid scalar, at least one fragment overall must be non-
whitespace, and reconstruction retains the ordinary paragraph/list/list-item/
quote/heading/code block bytes. A direct scalar is eligible only alongside the
independent ref-free wrapper that supplies the required six-field entry.

The action root and all exact button/link/citation/URL/unknown/untrusted/nested-
action chrome stay fully opaque to bytes, refs, stops, response/generating
markers, selectors, and actions. Recovery stability alone adds the fully
validated presentation/scalar lines to its in-memory candidate, canonicalizes
admitted refs, and still requires three identical observations over at least
ten seconds before the existing size, sensitivity, advice/review, proposal,
provenance, and event gates. Any malformed ref or scalar, unsatisfied wrapper,
outside-group response material, boundary escape, duplicate group, or collision
fallback-validation failure keeps the predecessor refusal and writes no
proposal or recovery event. A fully reconstructed response that fails the
post-stability size or sensitivity policy keeps that existing policy refusal
and likewise writes no proposal or recovery event. This capability defaults off
and is enabled only
by terminal bound-response recovery; normal ask, ordinary `WAITING`, legacy,
manual import, status, unrelated terminal resume, and committed recovery remain
unchanged. Recovery still uses only navigate/snapshot/fixed-wait/close, never
resubmits, writes the owner-only proposal first, and appends the verified
`BOUND_RESPONSE_RECOVERED` event last.

When, and only when, that exact recovery-only fallback is attempted and still
fails, the refusal CLI may add one `diagnostic_fallback_code` beside the full
six-field chain. The exact closed values are:

- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_SCALAR_INVALID`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_MATERIAL_UNSUPPORTED`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_REF_COLLISION`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_WITH_CONTENT`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_WRAPPER_UNSATISFIED_EMPTY`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_CONTENT_EMPTY`

The extractor reports the first physical explicit wrapper, selected-scalar, or
unsupported-material defect. If that scan is clean, duplicate admitted refs or
a collision with a trusted outside ref wins; the first unsatisfied wrapper then
selects with-content or empty, and an otherwise valid reconstruction with no
non-whitespace bytes selects content-empty. Complete bare `Text:` and
`StaticText:` container forms retain predecessor unknown-container opacity and
cannot be reclassified merely to emit a code. Complete approved button, link,
citation, URL, unknown-chrome, untrusted, and action subtrees are ref-inert for
the fallback collision set and cannot veto acceptance. Heading/body and trusted
non-action presentation/structural refs still collide; malformed would-be
opaque records are not granted the complete-subtree exclusion.

This seventh value contains no raw label, ref, scalar, count, subtree, response,
or other dynamic UI material. Missing, padded, suffixed, case-varied, unknown,
or wrong-conjunction values omit only the seventh while preserving all six
valid existing fields. Successful fallback attaches no diagnostic. The value
never enters state, events, proposals, status, normal ask, ordinary `WAITING`,
legacy/manual paths, unrelated terminal resume, or committed recovery, and it
changes no bytes, stability, stop, marker, action, proposal-first/event-last,
no-resubmission, or authority contract.

Before the ref-free extractor is attempted, the exact same six-field
`...CONTAINER_REF_MISSING` chain may instead add one recovery-only, CLI-only
`diagnostic_fallback_entry_code`. Its exact closed values are:

- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_WHITESPACE_SCALAR`
- `ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER`

The scalar code wins when the already bounded parser has accumulated any empty
or whitespace-only scalar block outside the selected action group. Only when
there is no such block may an independently visible outside generic or semantic
wrapper select the wrapper code. The presentation wrapper record enclosing the
selected group is excluded from that wrapper predicate, but an empty or
whitespace-only scalar sibling beneath the enclosing wrapper remains an
ordinary scalar block and selects the scalar code. Complete approved opaque,
untrusted, and action subtrees remain inert.

These entry suppressors do not invoke the extractor. Entry and attempted-
fallback diagnostics are mutually exclusive: a successful fallback emits
neither, and an attempted fallback failure emits only the existing
`diagnostic_fallback_code`. Missing, padded, suffixed, case-varied, unknown, or
wrong-conjunction entry values omit only the entry field while preserving the
six valid predecessors. The field contains no raw or dynamic UI material and
never enters state, events, proposals, status, normal ask, ordinary `WAITING`,
legacy/manual paths, unrelated terminal resume, or committed recovery. It
changes no acceptance, response bytes, stability, ref, stop, action,
proposal-first/event-last, no-resubmission, or authority contract.

One recovery-only exception is narrower than the outside-wrapper entry
diagnostic. At the exact same six-field `...CONTAINER_REF_MISSING` conjunction,
with fallback enabled and no accumulated scalar block, the existing extractor
may proceed when every independently visible outside generic or supported
semantic presentation tree is structurally complete and truly silent. Every
visible wrapper must use the predecessor-recognized grammar with exactly one
valid structural ref and no additional valid, duplicate, malformed,
wrong-case, spaced, unclosed, unbracketed, or residual ref-like token. A truly
ref-free predecessor-unrecognized wrapper keeps the bounded-content refusal.
The legacy `ELEMENT_PATTERN` case that backtracks valid-looking ref text from a
quoted label already reaches the exact-six entry; it remains non-silent with
that same refusal and is not reclassified. A structural-valid-first compound-
ref or otherwise non-silent wrapper likewise keeps the exact-six
`ADVANCED_RESPONSE_PRECONTENT_REF_FREE_ENTRY_OUTSIDE_PRESENTATION_WRAPPER`
refusal and does not invoke the extractor.

A silent tree owns no outside `text` or `statictext` scalar and may contain only
further silent wrappers or complete approved opaque, URL-metadata,
unknown-chrome, or untrusted subtrees. Independently visible exact, near, or
malformed action groups still produce predecessor duplicate/action-syntax
refusal; action-looking material remains inert only inside the selected action
subtree or existing approved inert chrome. Every silent-wrapper ref stays in
the trusted fallback collision multiset. On success, only validated lines from
the selected action subtree contribute response bytes. Recovery stability
preserves the heading, body, and selected group's enclosing presentation chain,
removes only independently outside silent-wrapper root records, and adds the
validated selected-subtree indexes. The
predicate and collisions are revalidated for every observation and final
completion. Scalar blocks retain priority, predicate failure retains the entry
diagnostic, extractor failure exposes only the existing fallback diagnostic,
and success exposes neither. Normal ask, ordinary `WAITING`, legacy/manual,
status/state/event/proposal, unrelated terminal, action, and no-resubmission
contracts are unchanged.

The multi-step predecessor proposal finalizer is not transactional and is not
changed by this response-wait handoff. A `KeyboardInterrupt` raised inside that
finalizer is therefore a hard fail-closed residual: it is never relabeled as
resumable `WAITING`, and automatic resume or resubmission is not authorized.
The current structural stop classifier is phase- and region-scoped; generic
whole-snapshot phrase matching must not be restored, and the approved
authentication/page-level structural stops must not be weakened.

Manual response import is the exceptional no-browser path for one answer that
is already displayed in the conversation belonging to one eligible run. A
human places the displayed response in an owner-mode-`0600` regular file below
`.secrets/chatgpt-pro-responses/`, then invokes:

```bash
make pro-import-response \
  PRO_RUN_ID=RUN_ID \
  PRO_RESPONSE_FILE=/home/minami/rakuten/.secrets/chatgpt-pro-responses/response.txt
```

The importer accepts only a bound, once-submitted `WAITING` run or a
post-submission response-only terminal refusal whose recorded reason is exactly
`ADVICE_INVALID`, `RESPONSE_NOT_IDENTIFIABLE`,
`RESPONSE_SELECTOR_AMBIGUITY`, or the predecessor conservative
`STOP_RATE_LIMIT` residual, and only when no proposal exists. It
applies the same size, sensitivity, response classification, persistence, and
hash controls, appends `MANUAL_RESPONSE_IMPORTED`, and records provenance
`HUMAN_COPIED_DISPLAYED_RESPONSE`. It rejects pre-submission or unbound runs,
`SUBMISSION_AMBIGUOUS`, authentication/CAPTCHA/account failures, a repeated
import, an existing proposal, unsafe path or mode, sensitive content, and
oversized content. It never creates a transport, starts a browser, types,
clicks, resumes, resubmits, or creates submission evidence. Manual provenance
is lower assurance than automatic capture and does not increase authority.
For either eligible parser-terminal reason, a verified progress-only recovery
tail does not revoke manual import: the importer resolves the same original
terminal anchor and keeps its distinct human-copy provenance.

Resume and status perform no pre-lock state or event-record read. They validate
the run ID and the existing exact run-directory path, owner UID, mode `0700`,
and no-symlink ancestry without creating the run directory. Resume then takes
the exclusive per-run lock without directory creation; status takes the shared
lock. Only under that lock does either operation load and verify the state,
event hash chain, and state hash. A concurrent loser or status reader therefore
waits through the event-append/state-replace publication window, observes the
winner's terminal state, and does not open a second transport or append
`WAIT_CONTINUES`. Missing runs remain `RUN_NOT_FOUND`; unsafe directory modes
and symlinks fail closed.

The existing CAPTCHA stop also recognizes the narrow sanitized Cloudflare
challenge signature only when `HTTP status: 403`, `challenges.cloudflare.com`,
and a distinct `Cloudflare` brand marker are all present. Partial matches remain
unknown UI. Exact-origin validation still runs first, and this stop performs no
prompt typing or submission.

When a live ask detects origin drift, a missing or duplicate selector, unknown
UI, or unresolved exact summary before prompt typing, it closes the transport
and removes the ephemeral prompt file without typing or clicking send. Ordinary
work returns exit 0 with `PRO_UNAVAILABLE_FALLBACK`, a run ID,
`submission_attempted: false`, and `CONTINUE_CANONICAL_LOCAL_ONLY`; gated work
returns exit 4 with `BLOCKED_PRO_REQUIRED`, the same non-submission evidence,
and `STOP`. Both outcomes append a hash-bound `PRO_UNAVAILABLE` event. For a
pre-submission refusal, state, event, output, and status may add only one closed
phase identifier: `landing`, `pro_menu`, `advanced_summary`, `closed_landing`,
`typed_composer`, or `send_control`. They never persist or print snapshots,
arbitrary labels, refs, menu contents, prompts, responses, account data, or
profile data for diagnosis. Internal contract or security invariant failures,
including a non-allowlisted MCP tool or a raw prompt tool argument, remain
exit-2 `REFUSED` outcomes and are never converted into availability fallback.

Every automatically captured or manually imported response is untrusted,
hash-bound `UNAPPROVED_PROPOSAL` material. Exact or sole-json-fenced
`PRO_ADVICE_V1` keeps structured convergence behavior and may inform reversible
work only after canonical/local reconciliation. `PRO_REVIEW_TEXT_V1` never
carries design authority: ordinary work must reconcile it with canonical and
local evidence. A gated run's `HUMAN_APPROVAL_REQUIRED` stops only that browser
workflow and does not create a repository-development gate. Text proposing
`DESIGN_HANDOFF_V1` remains advisory until it is reconciled with Canonical
precedence. No captured artifact resolves an Open Decision or authorizes an
external operation by itself; repository-local authority comes from the root
`AGENTS.md` standing development authorization.

No Edge or Chrome process, live browser navigation, login, or submission was
executed for the Edge-first implementation revision. Fake fixture PASS, the
previous bounded doctor observation, a future approved selected-browser smoke,
formal TST-001, and human/canonical approval remain separate evidence
boundaries.

No live browser action was executed while implementing the interactive
authentication wait. Its same-transport behavior, no-input interval, timeout,
bounds, and immediate stops are verified only with inert scripted transports;
live authentication, Pro submission, formal TST-001, and production readiness
remain separate evidence boundaries.

## Hosted Unit hybrid boundary

The owner-approved `ST0101_HOSTED_UNIT_HYBRID_BOUNDARY_V1` slice separates
portable ST-0101 behavior coverage from irreducible owner-private policy
checks. The tracked contract is
`changes/st-0101/hosted-unit-hybrid-boundary.v1.yaml`. It binds the exact
sixteen portable node IDs, exact seven `raos_owner_private` node IDs, hosted
selector `not raos_owner_private`, and local target `pro-owner-private-test`.

Hosted `ci-unit` applies that selector only to `tests/st0101`. The sixteen
reconciled cases replace repository, wrapper, runtime, stdin, or process
dependencies only inside the test process; the production physical-root,
wrapper, runtime, WSLg, browser, origin, credential, and approval guards are
unchanged. The existing nine network-sandbox skips remain separate and are
still owned by `ci-network-assert`.

At physical `/home/minami/rakuten`, run the irreducible boundary with:

```bash
make pro-owner-private-test
```

The target fails unless the physical root, exact owner-private Skill and agents
metadata, protected launcher/runtime source bytes, and installed private MCP
runtime are present and verified. It runs the non-private boundary validator
first, then requires exactly seven passing private cases with no skip, xfail,
or xpass. It performs no browser navigation, input, submission, provider call,
installation, publication, release, or Production action.

Local collection and fixture results are not hosted CI or formal TST-001
evidence. A clean hosted Unit rerun at the exact pushed head remains required
before merge review; browser/provider, staging, publication, release, and
Production remain separately unexecuted and gated.
