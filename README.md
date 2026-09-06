# RAOS / 暮らしのしるべ

日本の読者へ商品比較・購入支援を提供する、編集・Evidence・公開・収益運営のmonorepoです。
読者の信頼と有用性を維持し、持続的な確定貢献利益の改善を支えます。
現在の製品contractは[Editorial V3](changes/editorial-portfolio-v3/README.md)、
構造は[current architecture](docs/architecture/current-system.md)、目的別の仕様は[docs map](docs/README.md)から参照できます。

## Quick Start

Python 3.14.6、uv 0.12.x、Node 24.18.1、npm 11.16.0を使います。
初回は次の`make setup`でlockどおりに依存を準備します。
[scoped CLIと必須runtimeの手順](docs/architecture/current-system.md#codex-context-and-capability-boundaries)を参照してください。ローカルWordPressは
[preview guide](changes/wordpress-local-preview-v1/README.md)に従って起動します。
ASPは[接続guide](docs/affiliate-network-ingestion.md)を参照してください。
各社の実接続・登録情報の受領は未完了で、初期設定は無効です。

## 開発コマンド

通常の確認は `make fast` だけです。変更箇所の静的検査、関連テスト、生成物のdriftを
同じ差分計画から実行します。修正後は失敗した検査を先に確認してから影響範囲を確認します。

```bash
make setup       # 初回・依存変更時
make generate    # 生成入力を変更した場合
make fast        # 日常の確認
```

`make check` は同じ選択による静的検査のみ、`make final` は任意の全体診断です。
local全件検査は実装完了条件ではなく、`check → fast → final` の連続実行は不要です。
Pythonの通常の型検査はmypyに集約し、Pyrightは定期・手動の全件検査で実行します。

```bash
.venv/bin/python scripts/raos_build.py --base origin/main plan --json
.venv/bin/python scripts/raos_build.py --base origin/main plan --critical --json
make fast BASE=origin/main
```

計画には変更ファイル、選択した検査と理由、全件へ戻す理由を出力します。generatorの依存に加え、
通常コードのimport利用側、設定・fixtureの対応、追加・削除・renameされたtestを選択します。
未知のコード・設定、依存lock、共通検査基盤の変更は全件検査へ戻します。
生成入力ではない文書のみの変更は文書・参照整合性を確認します。

通常PRは影響範囲と重要な回帰・secret検査を実行します。Draftでは重い検査を省き、
`Final Integration` は未検証として不合格に保ちます。Ready化後のCIで、選択された検査の
成功を集約し、未選択と失敗・cancel・必要な検査の未実行を区別します。自動mergeには
現在のPR head SHAで実行された `Final Integration` の成功が必要です。古い実行結果や
skipはmergeの根拠になりません。

毎日03:00 JSTと手動CIでは、全generator、Python・Node・PHP、契約、DB／Storage、secret検査を
実行します。`live`、`external`、`raos_owner_private` は実行対象外です。環境依存のskipは
pytestの結果に表示し、未実行を成功した実環境検証とは扱いません。定期CIの失敗は修正対象です。
CIには検査ごとの所要時間と遅いテストを出力します。通常PRの中央値10分以内は改善目標であり、
新しい停止条件ではありません。

## WordPress公開準備

`make wordpress-production-request` は読み取り専用の計画を表示します。
対象選択、local preview、再開、独立レビュー、承認と反映の手順は
[公開runbook](docs/runbooks/wordpress-verified-incremental.md)が所有します。

## Generator ownership

`scripts/raos_build_core.py` の `BuildSpec` registryがgenerator owner、関連Story IDs、semantic input、output、owner依存、test pathを管理します。active inventoryは `changes/build/manifest.v2.json` です。

入力の扱いは次のとおりです。

- `docs/canonical/**`、dependency lock、container image digest、runtime data integrity、release provenanceはchecksumで保護します。
- 通常のtracked sourceはURIとsemantic identity/versionで追跡し、mutable byte digestを承認条件にしません。
- predecessor outputはowner ID/versionで参照し、生成順はowner graphで保証します。

仕様の適用範囲と履歴の扱いは[docs map](docs/README.md)を参照してください。

## Test layout

pytestは `--import-mode=importlib` で全suiteをcollectionします。通常のtestはxdistで実行し、共有状態を使うtestは `serial` markerで実行します。
全件CIのPython・Nodeテストは独立した20ジョブへ分割します。Pythonはテストケース単位で
重複なく振り分け、`serial` は各ジョブ内で直列実行します。通常PRもPythonテストファイル25個ごとに
1ジョブを目安に分割します。リポジトリ変数 `RAOS_CI_TEST_SHARDS` で上限を1〜256に変更できます。
標準の同時実行枠に合わせた既定値は20です。枠を超える分割は起動待ちと環境準備を増やします。
通常のPHPテストはPHP 8.3、Phase 3のPHP 7.4互換性検査は専用ジョブで実行します。
DB／Storageは専用partitionに分け、localな全testがどれか1つのpartitionに入るようにします。
ファイル名による自動分類は廃止し、既存の共有状態testは明示的なmodule一覧で移行管理します。suite helperは各packageの `support.py` からrelative importします。

## Contribution and operations

小さな修正は対象test、機能変更は関連contractと利用側を確認してから`make fast`を実行します。
Story IDは要求・依存・statusの追跡に使い、commit・PRの境界にはしません。
通常の開発と外部適用の権限は[AGENTS](AGENTS.md)を参照してください。
ローカル結果はstaging・Production検証を表しません。
RAOSのCodex標準入口は、実際のWSL checkoutで使うscoped CLIです。
起動・inventory・必要runtimeの確認は上記の手順、計測・評価は
[cold-start evaluation](docs/architecture/current-system.md#cold-start-evaluation)を参照してください。

## Repository map

6社のASP向けに既定で無効なデータ取得CLIを用意しています。
[利用方法と審査後の残課題](docs/affiliate-network-ingestion.md)を参照してください。
登録情報の受領、各社の接続仕様・利用権限の確認、初回接続は未完了です。

| Path | Responsibility |
| --- | --- |
| `apps/` | Web/API/worker delivery boundaries |
| `python/raos/` | Domain, application, ports, adapters, delivery code |
| `packages/` | Shared web UI and generated web contracts |
| `contracts/`, `schemas/`, `policies/` | Versioned product contracts |
| `migrations/` | Migration definitions and fixtures; applying migrations is external/irreversible gated work |
| `infra/` | Provider-neutral infrastructure and deployment definitions; no apply is performed locally |
| `scripts/` | Shared generators, validators, importers, and verification tools |
| `tests/` | Parallel, serial, contract, data/storage, security, and external suites |
| `changes/` | Active generated outputs, status v2, and archived Story evidence |
| `docs/` | Canonical baseline, architecture, runbooks, and archived work records |

過去のstatus/evidence v1、ExecPlan、worklog、debt logは履歴として残ります。現行の変更概要、関連Story IDs、検証結果、external/live未実行事項は最終integration PRに一度だけ記録します。
