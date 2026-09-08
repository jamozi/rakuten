# RAOS documentation map

## Which source applies

`canonical/` は2026-07-30にimportしたv1.0の不変baselineです。
import時の未実装statusと旧Codex手順は当時の記録です。現在の実装状況はstatus v2、
開発workflowは[developer guide](../README.md)、agentの入口は[AGENTS](../AGENTS.md)が所有します。

製品・安全の不変条件はbaselineを維持します。明示的に採用された後継は宣言された対象機能に
だけ適用し、更新日時やversion番号だけで全仕様を上書きしません。
[v2 clarifications](../changes/raos-v2/clarifications.v1.yaml)はv2の適用範囲を定めます。
現行の記事・商品選定と利益指標はEditorial V3、v2 decision support等は各contractが正本です。
矛盾があれば対象・根拠・実装との差を記録し、不明な実値はUNKNOWNにします。

## Task map

一律の必読順はありません。作業に対応する入口と、その判断に必要な参照先を選びます。

| 必要な情報 | 最初に読む場所 | 実装・検証への接続 |
| --- | --- | --- |
| Mission・現行利益指標・商品選定 | [Editorial V3](../changes/editorial-portfolio-v3/README.md) | `editorial-portfolio.v3.json`、`tests/editorial_portfolio_v3/` |
| 全体構造・公開/内部境界 | [current system](architecture/current-system.md) | domain/application/ports/adaptersと不変条件の検証先 |
| v1のProduct/Security原則 | [integration design](canonical/01_integration/RAOS_07_integration_design_v1.0.md) | 同package内の領域設計・security controls |
| v2の採用・意思決定支援 | [v2](../changes/raos-v2/product-spec.v2.yaml) | product-spec.v2.yaml、decision_support_v2、`tests/raos_v2/` |
| 記事・Evidence・日本語・SEO/CRO | [editorial review Skill](../.agents/skills/raos-editorial-review/SKILL.md) | 現行portfolio、source locators、local表示検査 |
| WordPressの日常作成・公開 | [簡易公開](../changes/wordpress-direct-publish-v1/README.md) | [workflow Skill](../.agents/skills/raos-wordpress-workflow/SKILL.md)、既存Make入口。旧候補だけ[互換runbook](runbooks/wordpress-verified-incremental.md) |
| ASP追加・取得・送信先制限 | [affiliate ingestion](affiliate-network-ingestion.md) | `tools/affiliate_ingestion/`、`tests/test_affiliate_ingestion.py` |
| 実装status・外部未実行項目 | [status v2](../changes/status/README.md) | `status.v2.yaml`、GitHubの現行Issue/PR |
| 開発・CI・生成元 | [developer guide](../README.md) | `raos_build.py`、`manifest.v2.json`、Final Integration |
| Codex計測・回帰評価 | [eval entrypoint](../tests/evals/README.md) | `scripts/codex_harness.py`、製品evalとagent evalを区別 |
| 原設計の決定・未決事項 | [canonical decisions](canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml) | [open decisions](canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml)、後継の適用範囲も確認 |
| 過去の目的・議論 | [original purpose](upstream/key_documents/RAOS_01_requirements_purpose_success_v0.1.md) | 当時の数値目標を現在の実測値として使わない |

## Imported evidence and history

原設計の入口は[v1 master](canonical/00_master/RAOS_MASTER_README_v1.0.md)です。
内部の旧Codex手順・backlog・test catalogは当時のbaselineとして参照します。

`upstream/` は6つのv0.1原設計package等、[manifest.json](manifest.json)はimport元と
repository path・size・SHA-256の対応を所有します。修正は後継contract等として採用し、
`canonical/`、`upstream/`、`zip/` を直接更新しません。

```sh
.venv/bin/python scripts/import_raos_design.py verify
```

検証はarchive、path mapping、symlink、size、package checksumを確認します。
`execplans/`、worklog、status/evidence v1は履歴です。古いACTIVE表記から開発手順を復元せず、
現在の依頼・status v2・関連Issueを使います。
