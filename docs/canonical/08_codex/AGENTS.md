# AGENTS.md — RAOS implementation rules

## Mission
Implement one approved RAOS backlog story at a time. Preserve compliance, factual provenance, human approval, and public/internal data isolation before automation or speed.

## Read order
1. `00_master/RAOS_MASTER_README_v1.0.md`
2. `01_integration/RAOS_07_integration_design_v1.0.md`
3. `01_integration/RAOS_07_canonical_decisions_v1.0.yaml`
4. `01_integration/RAOS_07_open_decisions_v1.0.yaml`
5. The selected story in `07_backlog/RAOS_13_story_backlog_v1.0.yaml`
6. The story's `design_refs`, contracts, test suites, and security controls

## Non-negotiable rules
- Do not implement more than the selected story and its explicitly approved prerequisites.
- Do not silently resolve an open decision. Use the documented safe default or stop at the interface boundary.
- Do not claim a story is validated without runtime evidence from its required test suites.
- Do not apply `PROPOSAL_ONLY` SQL/YAML directly. Convert it into versioned migrations/contracts with tests.
- Do not let AI, workers, or generated code approve, publish, clear blockers, disable safeguards, or access production secrets.
- Do not collect, store, transform, summarize, or fixture Rakuten review bodies.
- Do not fabricate first-hand experience or infer missing product facts.
- Do not expose editorial, evidence, AI raw artifacts, analytics internals, or finance through the public API/read model.
- Do not use affiliate rate, EPC, RPM, or profit as recommendation input.
- Do not route affiliate clicks through RAOS as a required redirect.
- Do not put secrets, raw prompts, source packets, personal data, or production report rows in logs or commits.
- Never make a production write or infrastructure apply without explicit human approval and a release story.

## Before changing code
Post a short preflight in the PR or work log:
1. Story ID and objective
2. Files/contracts read
3. Ambiguities or open decisions
4. Planned files and migrations
5. Tests to add/run
6. Out of scope

## Implementation discipline
- Prefer domain ports and adapters; keep provider SDK types out of domain modules.
- Keep commands transactional and publish outbox events in the same database transaction.
- Assume at-least-once delivery; consumers must be idempotent.
- Use strict schemas and reject unknown fields at trust boundaries.
- Preserve immutable artifacts, approvals, provider facts, and publication snapshots.
- Use RFC 9457 Problem Details and existing error codes.
- Use ETag/If-Match for mutable resource concurrency and Idempotency-Key for commands.
- Keep public rendering deterministic from a publication manifest.
- Make dangerous behavior impossible by type/schema/authorization where practical, not only by prompt text.

## Database changes
- Use the repository migration framework.
- Follow Expand–Migrate–Contract.
- Add zero-to-latest and previous-to-latest integration tests.
- Test roles, grants, constraints, triggers, indexes, and rollback/forward recovery.
- Never edit a migration that may have been applied; add a new migration.

## External providers
- Consult current official primary documentation at implementation time.
- Add sanitized recorded fixtures for success and failure states.
- Keep live tests bounded, credential-separated, and staging-only.
- Persist provider version/config/request metadata without secrets.
- Mark live validation `NOT_EXECUTED` until it actually runs.

## UI
- Use semantic HTML first and WCAG 2.2 AA as the target.
- Preserve keyboard, focus, error recovery, and screen-reader behavior.
- Critical actions need step-up, reason, impact preview, idempotency, and audit.
- Finance information must not appear in recommendation review surfaces.

## Tests and status
- Run the story's required suites plus affected contract/static suites.
- Add negative and failure tests, not only happy paths.
- Update status only to the highest level supported by evidence.
- Record unexecuted live, browser, security, load, or recovery tests explicitly.
- `ST-0005`でStatus workflowが導入されるまでは集約Registryを手編集せず、PRに提案状態を記録する。導入後はValidator/Generatorを使用し、未解決行を削除しない。

## Pull requests
- One story per PR unless an approved ExecPlan says otherwise.
- Include requirement/design/control/test IDs.
- Include generated file source and command.
- Include migration/contract compatibility notes.
- Include security/privacy/accessibility impact.
- Include evidence and remaining unexecuted work.

## Stop conditions
Stop and request human review when:
- requirements or canonical decisions conflict;
- a blocking open decision has no safe interface-only path;
- a change would weaken human approval, disclosure, evidence, public isolation, or kill switches;
- provider terms or API behavior cannot be verified from an official source;
- production credentials or writes would be required;
- a zero-tolerance test fails.
