# RAOS monorepo

RAOS の実装、生成、検証を1つの統合workflowで管理するmonorepoです。Story IDは要求・依存・statusの追跡に使い、実装・commit・PRの境界には使いません。

## 開発コマンド

```bash
make setup
make generate
make check
make fast
make final
```

- `make setup` はPython/Nodeのlock済み依存をローカルcacheを使って同期し、toolchainとlockの整合性を確認します。
- `make generate` は変更された入力から影響ownerを求め、依存graph順に生成します。
- `make check` は生成drift、lint、type、静的検査を実行します。
- `make fast` はmerge-baseとの差分からaffected generatorとfocused testを選びます。必要なら `BASE=<ref>` を指定できます。
- `make final` は全generator check、全local test、contract、DB、Storage、secret scanを集約します。`live`、`external`、`raos_owner_private` testはlocal finalでは実行せず、結果に未実行として表示します。

通常loopではStory固有Make target、absolute tool path、常時offline/no-cache、実行ごとのexact tool再検証を使いません。tool versionとdependency lockは `setup` と `final` の境界で検証します。

## Generator ownership

`scripts/raos_build_core.py` の `BuildSpec` registryがgenerator owner、関連Story IDs、semantic input、output、owner依存、test pathを管理します。active inventoryは `changes/build/manifest.v2.json` です。

入力の扱いは次のとおりです。

- `docs/canonical/**`、dependency lock、container image digest、runtime data integrity、release provenanceはchecksumで保護します。
- 通常のtracked sourceはURIとsemantic identity/versionで追跡し、mutable byte digestを承認条件にしません。
- predecessor outputはowner ID/versionで参照し、生成順はowner graphで保証します。

`docs/canonical/**` は不変baselineです。product requirementは正本として利用しますが、baseline内の旧Story/PR/preflight/human-review手順は現在の開発workflowには適用しません。

## Test layout

pytestは `--import-mode=importlib` で全suiteをcollectionします。parallel-safe testはxdist、DB・Storage・global filesystem testは `serial` markerで実行します。suite helperは各packageの `support.py` からrelative importします。

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
