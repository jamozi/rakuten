# RAOS Codex handoff checklist

## Files to give Codex
Give Codex this entire package, not selected excerpts.

## First action
Use `CODEX_KICKOFF.md`. The first implementation story is `ST-0001` only.

## Human inputs required before the vertical pilot
- initial category
- site name/domain/operator disclosure
- reviewer and labor cost
- category product identity rules
- category freshness SLA
- legal review boundary
- cloud/AI budget

## Inputs required before live integrations
- dedicated Rakuten/OpenAI/Google/AWS credentials
- anonymized real Rakuten result report sample
- OIDC provider
- privacy/consent decision
- notification channel
- production region/data residency
- retention approval

## Do not accept these completion claims without evidence
- “DB is done” without PostgreSQL 18 migration/role/constraint tests
- “API is done” without runtime contract/authz/idempotency tests
- “AI is done” without locked evaluation and live bounded provider evidence
- “UI is accessible” without manual keyboard/screen-reader evidence
- “Analytics works” without reconciliation and real provider import evidence
- “Production ready” without security, restore, rollback, alert, and GATE-0 evidence
