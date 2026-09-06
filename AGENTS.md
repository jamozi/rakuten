# RAOS — Codex entrypoint

## Mission

読者に信頼できる商品比較・購入支援を提供し、品質制約を守って持続的な確定貢献利益を改善する。
技術・記事数・SEO・CRO・自動化はこの目的の手段である。
優先順: 製品目的 → 正確性・安全性 → 全体の設計品質 → 判断品質 → context効率 → 速度。

## Non-negotiables

- 商品同定、一次情報、鮮度、比較範囲、自然な日本語、広告表示を維持する。
  料率・価格・楽天取扱有無を商品選定の加点要素にしない。未確認値はUNKNOWN/UNAVAILABLE。
- 編集判断と財務を分離する。推計収益を確定報酬へ置換せず、計測欠損をゼロ・成功にしない。
- 公開側は承認済みsnapshotのpublic projectionを読む。内部Evidence・Finance・raw AIへ直結しない。
  auth/authz、public/internal分離、CTA、disclosure、publication、kill switchの既存testを維持する。
- `docs/canonical/`、`docs/upstream/`、`zip/` はimmutable baseline。採用済み後継は対象機能だけに適用する。
  baselineの旧Story/PR分割・preflight・human-review手順は現行開発workflowへ適用しない。
- Generated outputはowner generatorから更新する。通常sourceのbyte hashを開発承認条件にしない。
  runtime integrity、生成物、release provenanceのhashは維持する。
- Secret、credential、personal/production data、raw prompt、禁止provider materialを読出し・記録・公開しない。
- 他者の変更を保持し、無関係なdirty pathを編集・stage・削除しない。

## Canonical source map

必要な行の入口から読み、リンク先の全履歴を一括投入しない。

| 判断対象 | 正本への入口 |
| --- | --- |
| 仕様の適用範囲・後継・履歴 | [docs map](docs/README.md) |
| 現行の編集・商品選定・利益指標 | [Editorial V3](changes/editorial-portfolio-v3/README.md) |
| 構造・data flow・不変条件とtest | [current architecture](docs/architecture/current-system.md) |
| v1の製品・安全制約 | [integration baseline](docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md) |
| 実装状況・未実行事項 | [status v2](changes/status/README.md) |
| 開発・CI・generator ownership | [developer guide](README.md) |
| WordPressの段階・再開条件 | [publication runbook](docs/runbooks/wordpress-verified-incremental.md) |

## Repository map

- `python/raos/`: domain → application → ports / adapters。`apps/`: delivery。
- `packages/`: UI・web contracts・bounded WordPress bridge。
- `contracts/`, `schemas/`, `policies/`: versioned contracts。`migrations/`, `infra/`:適用前の定義。
- `scripts/`: generator / deterministic validation。`tests/`: behavior / boundary検証。
- `changes/`:採用済み後継と生成物・status。ownerは`changes/build/manifest.v2.json`。

## Task routing

- S: 明確な局所修正は対象と関連testだけ。M: subsystem、contract、利用側まで。
- L: data flow・外部interface変更は関連設計と隣接system。XL: business・security・publication・
  主要architecture判断はMission、architecture、適用する決定まで確認する。
- L/XLと曖昧なMではObjective Checksumを内部確認する:
  要求 / 上位目的 / 成功指標 / 影響域 / 隣接影響 / 正本 / 不可逆作用 / 非対象。
- 不具合は症状・根因・違反不変条件・隣接影響を確認し、最小の完全なsystem変更で解決する。
- 記事・比較レビュー → `$raos-editorial-review`。WordPress編集・表示・公開準備 → `$raos-wordpress-workflow`。
- code・architecture → local file / `rg`。Issue・PR・CI → GitHub app、未対応操作は`gh`。
  Git → local git。現在のAPI仕様 → official docs/web。反復手順 → Skill、機械処理 → script。
- 正本やIssueに必要情報があれば再探索せず、参照済み内容を再読するのは変更・不足がある時だけ。
  Memoryは探索補助であり、仕様・承認の正本ではない。

## Validation and development

- 通常は`make fast`。初回・依存変更は`make setup`、生成入力変更は`make generate`。
  差分選択は`.venv/bin/python scripts/raos_build.py --base <ref> plan --json`。
- `make check`は静的検査、`make final`は任意診断。連続実行やlocal全件合格を一律条件にしない。
- 失敗した検査から修正・再実行し、変更がなければ同じ検査を繰り返さない。
  通常testは並列、共有stateは`serial`、DB/Storageは専用partition。未実行をPASSと呼ばない。
- design、code、refactor、security、migration code、fixture、docs、および通常GitHub開発操作は継続承認済み。
  edit/test/generate/stage/commit/push/PR作成更新/branch protection更新/required CI合格後のmergeに再確認は不要。
- Story IDは追跡情報。実装slice/branch/PR境界ではない。integration PRは1本にまとめる。
  個別ExecPlan/worklog/debt logは必須ではない。Proは明示依頼時だけの任意助言。

## External effects and escalation

- GitHub開発操作以外のlive write、credential入力・開示、規約同意、支出、公開、staging、
  deployment/release/Production、live policy/kill-switch変更には対象操作の承認が必要。
- data削除、不可逆migration適用・変換、force push、default branch/history破壊は停止して確認する。
  localなport・rollback・simulation・draft artifactは継続する。不明な実値は作らずdefault-offで実装する。
- WordPressは先に非本番データとlocal previewで確認する。対応能力があれば`wordpressEditor` /
  `wordpressDeployment`を先に実呼出しする。状態を設定・過去結果から推定しない。
- MCP不能時はlistとread-only statusで診断し、代替理由を記録する。MCP優先は権限を広げない。
  未検証候補は送付・提案・反映しない。独立2巡、Required CI、wp-admin別人承認、期限・対象hash、
  precondition、idempotency、kill switch、用途別default-offを維持する。自己承認・汎用CMS迂回は禁止。
- test failure、設計不足、hash drift、Pro不在、live evidence未実行は修正または正確な報告の対象。
  解消不能な仕様矛盾は根拠とUNKNOWNを示し、安全な独立作業を進める。
