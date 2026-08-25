# ST-1802 blocked local GATE-1 decision

This Story implements the maximum safe local GATE-1 decision boundary. It reads
only fixed, hash-bound repository inputs and deterministically produces a blocked
decision pack plus a non-attesting recorded-synthetic evaluator output.

The exact ST-1801 dependency is not a 30–45 article portfolio. It is a plan with
30 synthetic placeholders whose creation, approval, and publication states are
all negative, while actual article count and observations are `UNAVAILABLE`.
Consequently, ST-1802 cannot pass GATE-1. The generated decision is always
`BLOCKED`, eligibility is `NOT_ELIGIBLE`, qualifying evidence is empty, and every
authority remains `NONE`.

## Mandatory-criteria model

The pack explicitly records the editorial, technical, security, recovery, and
governance criteria required by the authoritative GATE-1 sources. Each criterion
uses a closed status vocabulary:

- `PASS`, `FAIL`
- `UNAVAILABLE`, `NOT_EXECUTED`
- `BLOCKED`, `INELIGIBLE_NON_ATTESTING`

No local generated pack contains an actual `PASS`. Missing observations are not
converted to zero. Revenue, affiliate rate, EPC, RPM, reward, or profit are not
GATE-1 pass criteria and do not influence content or recommendation order.

## Recorded-synthetic evaluator

The evaluator exercises the numeric and boolean GATE-1 rules with exact integer
cross-multiplication and bounded decimal parsing. Missing values and zero
denominators yield `UNAVAILABLE`; malformed or inconsistent counts are rejected.
Its classification is fixed to `RECORDED_SYNTHETIC_ONLY_NON_ATTESTING`, and even a
synthetic `PASS` cannot satisfy an article, Story, TST-032, Gate, publication, or
release requirement.

## Deterministic owner generation

Run from the exact physical repository root with the synchronized pinned Python
environment. No install, environment-value read, subprocess, network, provider,
credential, browser, CMS, or external action is performed:

```bash
/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1802_gate1_decision.py

/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1802_gate1_decision.py --check
```

All three generated outputs are published under one directory lock and one
recoverable all-or-nothing transaction. The next normal build rolls back an
interrupted prepared transaction or completes committed cleanup. `--check` is
strictly read-only and rejects pending recovery. Inputs are captured
descriptor-relatively without following links, have a 2 MiB limit, and reject
duplicate JSON/YAML keys and YAML aliases.

## Evidence boundary

Local tests exercise implementation behavior only. Formal TST-020/TST-032,
actual 30–45 article execution, human review/approval, publication, live provider,
staging, release, deployment, and Production remain `NOT_EXECUTED`. Canonical and
Status Registry states remain unchanged.
