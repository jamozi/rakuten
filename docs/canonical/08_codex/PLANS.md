# PLANS.md — RAOS ExecPlan format

Use an ExecPlan for L-size stories, migrations, cross-module contracts, provider integrations, security-sensitive work, and any PR expected to require more than one coherent implementation phase.

## Required sections

### 1. Story and outcome
- Story ID
- User/system outcome
- Explicit non-goals

### 2. Context read
- Canonical documents
- Contract/schema versions
- Existing implementation paths
- Open decisions and safe defaults

### 3. Invariants
List the RAOS invariants that must remain true, including human approval, provenance, idempotency, public isolation, finance/editorial separation, and no review-body use.

### 4. Proposed design
- Modules and ownership
- Data/transaction boundaries
- API/event/job changes
- Migration plan
- Failure and rollback behavior
- Security/privacy/accessibility impact

### 5. Milestones
Each milestone must leave the repository testable. Do not use vague percentages.

### 6. Test plan
Map test cases to suite IDs. Include negative, duplicate, stale, unauthorized, provider failure, and rollback cases when applicable.

### 7. Evidence plan
Specify which artifacts prove implementation, runtime validation, staging deployment, and release readiness. Do not pre-mark them PASS.

### 8. Risks and decisions
Record unresolved decisions, alternatives, and the chosen safe behavior.

### 9. Progress log
Update after each milestone with files changed, commands run, results, and deviations.

### 10. Completion note
Summarize what is implemented, what is validated, what remains unexecuted, and which status rows changed.
