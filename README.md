# RAOS monorepo

RAOS の実装、生成、検証を1つの統合workflowで管理するmonorepoです。Story IDは要求・依存・statusの追跡に使い、実装・commit・PRの境界には使いません。

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

通常PRは影響範囲と重要な回帰・secret検査を実行します。Draftでは重い検査を省き、ready時に
実行します。`Final Integration` は選択された検査の成功を集約し、未選択と失敗・cancel・
必要な検査の未実行を区別します。自動mergeはDraft以外のPRのみが対象です。

毎日03:00 JSTと手動CIでは、全generator、Python・Node・PHP、契約、DB／Storage、secret検査を
実行します。`live`、`external`、`raos_owner_private` は実行対象外です。環境依存のskipは
pytestの結果に表示し、未実行を成功した実環境検証とは扱いません。定期CIの失敗は修正対象です。
CIには検査ごとの所要時間と遅いテストを出力します。通常PRの中央値10分以内は改善目標であり、
新しい停止条件ではありません。

## Generator ownership

`scripts/raos_build_core.py` の `BuildSpec` registryがgenerator owner、関連Story IDs、semantic input、output、owner依存、test pathを管理します。active inventoryは `changes/build/manifest.v2.json` です。

入力の扱いは次のとおりです。

- `docs/canonical/**`、dependency lock、container image digest、runtime data integrity、release provenanceはchecksumで保護します。
- 通常のtracked sourceはURIとsemantic identity/versionで追跡し、mutable byte digestを承認条件にしません。
- predecessor outputはowner ID/versionで参照し、生成順はowner graphで保証します。

`docs/canonical/**` は不変baselineです。product requirementは正本として利用しますが、baseline内の旧Story/PR/preflight/human-review手順は現在の開発workflowには適用しません。

## Test layout

pytestは `--import-mode=importlib` で全suiteをcollectionします。通常のtestはxdistで実行し、共有状態を使うtestは `serial` markerで実行します。
DB／Storageは専用partitionに分け、localな全testがどれか1つのpartitionに入るようにします。
ファイル名による自動分類は廃止し、既存の共有状態testは明示的なmodule一覧で移行管理します。suite helperは各packageの `support.py` からrelative importします。

## 外部作用の境界

GitHub上の通常の開発操作を除くcredential入力、規約同意、支出、live provider変更、公開、staging、deployment、release、Production変更は自動実行しません。回復不能な削除、migration適用、Git history破壊も自動実行しません。ローカルのdesign、implementation、test、migration code、rollback logic、security hardeningはこの境界の内側で継続します。

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
