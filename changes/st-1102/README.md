# ST-1102 Article Workspace local implementation

Status: `LOCAL_IMPLEMENTATION_COMPLETE` (recorded synthetic V2 only)

ST-1102 now has an additive, deterministic Article Workspace V2 model for its
declared dependency boundary. It projects the exact recorded/synthetic ST-0806
Content AST proposal into AST, typed AI diff, Claim/Evidence, Comparison, and
partial SEO panes. It also provides effect-free evaluators for strong ETag
preconditions and unsaved-change navigation decisions.

The historical V1 metadata implementation remains byte-identical. V2 does not
replace it, register a route, render a browser view, load editorial data, adopt
the proposal, save an article, navigate, publish, or call a provider.

## Dependency and data boundary

- ST-0806 is bound by exact hashes and loaded through its production recorded
  fixture adapter. The owner generator recomputes the typed AST diff and Claim
  coverage; it does not trust copied summary values.
- ST-1101 remains a disabled headless UI foundation. Catalog roles are display
  metadata and do not establish authentication or authorization.
- The declared dependencies contain no resolved ST-0807 SEO metadata. The SEO
  pane therefore exposes the AST title and SEO reference while canonical,
  robots, and JSON-LD values remain `UNAVAILABLE_DEPENDENCY`.
- Fixture content is synthetic, minimized, DEV/CI-only, and ineligible for
  Production. Raw prompts, raw source/review bodies, Claim text, raw HTML,
  arbitrary URLs, credentials, personal data, and finance/affiliate economics
  are excluded.

## Concurrency and unsaved decisions

`evaluateArticleWorkspaceEtagV2` implements only a pure decision:

- missing `If-Match` -> `PRECONDITION_REQUIRED` / 428;
- stale `If-Match` -> `PRECONDITION_FAILED` / 412 with conflict resolution
  required and no overwrite;
- exact match -> `MATCHED_NO_COMMAND`, never save authority.

`evaluateArticleWorkspaceUnsavedV2` compares exact AST SHA-256 values. A dirty
model returns `BLOCK_UNSAVED_CHANGES` and the dialog focus target; a clean model
returns `ALLOW_CLEAN`. Neither path performs or intercepts navigation, saves,
or discards.

## Owned generation

Owner source:

- `contracts/article-workspace.v2.yaml`
- `../../scripts/build_st1102_article_workspace_v2.py`

Generated outputs (never edit manually):

- `article-workspace-recorded.v2.json`
- `../../packages/web-ui/src/article-workspace-recorded.v2.ts`
- `runtime-manifest.v2.yaml`

Generation and no-write verification use the repository's pinned Python
toolchain:

```text
uv run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads python scripts/build_st1102_article_workspace_v2.py
uv run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads python scripts/build_st1102_article_workspace_v2.py --check
```

The manifest binds all owner sources, exact canonical/dependency inputs, locked
toolchain files, the hardened atomic writer, and generated artifact bytes.

## Accessibility candidate

The headless model records stable unique semantic IDs, one H1, landmark/focus
order, keyboard tab-model keys, text+code+icon status cues, non-color-only
state, and table caption/header/row-header requirements. These are local model
checks only; there is no DOM, browser, keyboard, zoom, or screen-reader claim.

## Authority and completion boundary

All authentication, authorization, route, rendering, mutation, navigation
effect, dispatch, persistence, network, provider, approval, publication,
release, and Production authority fields are false. Canonical Story/registry
state is unchanged.

The exact local check inventory and counts are recorded in
`LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml` and
`../../docs/worklogs/ST-1102.md`. Formal TST-022/TST-024, hosted CI, browser,
live, staging, release, publication, and Production remain `NOT_EXECUTED`.

## Historical V1 compatibility

`packages/web-ui/src/article-workspace.ts` remains the original disabled,
metadata-only V1 candidate. Its SHA-256 is fixed as
`01d2f680ddfb5a64fa9d84db1c10e1ae9cd3de490520e67f135f3be63260db89`.
Existing V1 tests remain part of the affected ST-1102 suite.
