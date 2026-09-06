# Current RAOS system

この文書は実装への地図です。仕様の適用範囲は[docs map](../README.md)、現行の編集・利益
contractは[Editorial V3](../../changes/editorial-portfolio-v3/README.md)を参照します。
実装・local testの存在と、live接続・公開・事業成果は別の状態です。

## Data flow and ownership

```text
provider / official evidence
  → bounded adapters → application use cases → domain + versioned contracts
  → editorial review → approved immutable publication snapshot
  → public projection → public API / Web / tracked WordPress materialization

confirmed rewards → private finance / reconciliation → portfolio economics
                                      (not editorial ranking input)
```

| Boundary | Implementation | Verification / source |
| --- | --- | --- |
| Business rules / use cases | `python/raos/domain/`, `python/raos/application/` | 領域tests、versioned contracts |
| External interfaces | `python/raos/ports/`, `python/raos/adapters/` | 接続先・auth・idempotencyのnegative tests |
| Delivery | `apps/`, `python/raos/api/`, `python/raos/workers/` | public/admin分離、authn/authz |
| Snapshot / public read | [snapshot](../../python/raos/domain/publishing/publication_snapshot_v2.py), [projection](../../python/raos/domain/publishing/public_projection_v2.py) | `tests/st0902_v2/`, `tests/st0905/`, `tests/st1001/` |
| Identity / evidence | `domain/catalog`, `domain/evidence`, `domain/decision_support_v2` | `tests/raos_v2/`, `tests/editorial_portfolio_v3/` |
| Reader UI / WordPress | `packages/web-ui/`, `changes/wordpress-local-preview-v1/` | `tests/wordpress_local_preview/`, `tests/wordpress_seo_audit_v1/` |
| Publication bridge | `packages/wordpress-mcp-bridge/`, `changes/wordpress-mcp-v1/` | `tests/wordpress_mcp_v1/`、[runbook](../runbooks/wordpress-verified-incremental.md) |
| ASP ingestion | `tools/affiliate_ingestion/` | `tests/test_affiliate_ingestion.py`、[guide](../affiliate-network-ingestion.md) |
| Generated artifacts | `scripts/raos_build_core.py` registry | `changes/build/manifest.v2.json`、owner drift tests |

`domain`は純粋なルール、`application`はuse case、`ports`は契約、`adapters`は外部実装を所有します。
公開側へ新しい情報を出す場合はsnapshotとprojectionの閉じた契約を検討し、内部repositoryを
rendererへ接続しません。Evidence locator・raw AI・Financeの内部値は公開payloadに出しません。
既存source_note等で解決できる場合は、公開契約を不用意に増やしません。

## Invariants and executable constraints

| Invariant | Executable constraint |
| --- | --- |
| Authentication / authorization | `tests/st0401/test_authentication.py`, `tests/st0403/test_authorization.py`, `tests/st0404/test_security.py` |
| Public/internal isolation, hostile input | `tests/st0905/test_runtime_hostile_v2.py`, `tests/st1001/public-shell-boundaries.test.ts` |
| Disclosure and affiliate CTA behavior | `tests/st1004_v2/disclosure-affiliate-negative.test.ts` |
| Snapshot approval / idempotency | `tests/st0901_pr3/test_authorization_idempotency.py`, `tests/st0902_v2/test_domain.py` |
| Confirmed versus estimated economics | `tests/st1305_v2/test_reconciliation_negative.py`, `tests/editorial_portfolio_v3/test_economics_cli.py` |
| Identity, freshness, comparison scope, zero-weight finance factors | `tests/editorial_portfolio_v3/test_contract.py`, `tests/raos_v2/test_decision_engine.py` |
| WordPress expiry / separate approval / recovery / default-off | `tests/wordpress_mcp_v1/`, `tests/wordpress_local_preview/` |
| AI truthfulness / no invented experience | [product eval](../../python/raos/application/ai/evaluation_harness.py), `tests/st0707_runtime/test_harness.py` |

不変条件を変える場合は入力から公開・集計までの隣接影響を確認します。
通常のlocal実装に追加承認台帳は不要です。外部適用は既存の実行境界に従います。

## Current product contracts

Editorial V3はV2の履歴を変更せずに採用された後継です。
`changes/editorial-portfolio-v3/editorial-portfolio.v3.json`がstrategyとselection policy、
`editorial-identities.v1.json`が記事分類と比較範囲、`market-candidate-audit.v1.json`が候補・除外根拠、
`generated/navigation.v3.json`がホーム・関連記事の唯一の機械可読元です。
ownerは`scripts/build_editorial_portfolio_v3.py`です。

確定貢献利益の式、欠損時のUNAVAILABLE、新規記事を増やす条件はstrategyを参照します。
公開用情報とowner-private economicsを分離し、未帰属報酬を記事へ推測配賦しません。
記事単位の一般的出典を、型番・variant別の安全性や保証確認の完了へ昇格させません。

v2 decision supportのルールは`changes/raos-v2/`と`domain/decision_support_v2`が所有します。
旧v2の単一wedgeを現行portfolio全体の範囲として解釈しません。
実装状況と外部未実行項目は[status v2](../../changes/status/README.md)から確認します。

## Codex context and capability boundaries

AGENTSは常時の目的・不変条件と地図、READMEは人間の開発案内、Skillは反復workflowを所有します。
S/M/L/XLとObjective ChecksumはAGENTSの探索方針を使い、各Skillへ複製しません。
RAOSのscoped CLI起動・inventory・必要runtimeの手順はこの節を正本とします。

Project設定は`.codex/config.toml`、workflowは`.agents/skills/`です。
Global preference・Plugin install state・個人Memoryをrepositoryへコピーしません。
GSDのdisable対象は現在ホストで発見したSKILL.md pathです。Codex 0.153.4には
[project Skill filterの制約](https://github.com/openai/codex/issues/20210)があり、
通常の起動ではこの設定をSkill一覧へ反映しません。RAOSでは実際のWSL checkoutから
既存の`scripts/codex_harness.py run --`を使うscoped CLIを標準入口とします。
この入口がprojectのSkill設定だけをsession overrideへ渡します。新しいlauncherは追加せず、
Global GSDの設定・インストール状態と権限設定を維持します。

以下のcheckout、Codex home、実行ファイルの絶対pathはこのホストの例です。別ホストでは
実際のWSL checkoutと実行可能なWSL版Codexに置き換えます。`RAOS_CODEX_BIN`は明示した
実行ファイルを選択し、未指定時だけPATH上の`codex`を使います。この例の実行ファイルは
`--version`で`codex-cli 0.153.4`を確認しています。`CODEX_HOME`と`RAOS_CODEX_BIN`は
起動processの環境として渡し、Global設定やshell profileへ保存しません。

WSL shellでは、subshell内だけに環境を設定して起動します。

```sh
(
  cd /home/minami/.codex/worktrees/0449/rakuten || exit 1
  export CODEX_HOME=/mnt/c/Users/naoki/.codex
  export RAOS_CODEX_BIN=/mnt/c/Users/naoki/.codex/bin/wsl/b53f5e5f7452dd19/codex
  test -x "$RAOS_CODEX_BIN" || exit 1
  .venv/bin/python scripts/codex_harness.py run --
)
```

Windows PowerShellからも、Windows側の見かけのworktree pathではなく、
`--cd`に実在するWSL checkoutを指定します。

```powershell
wsl -d Ubuntu-22.04 --cd /home/minami/.codex/worktrees/0449/rakuten --exec env `
  CODEX_HOME=/mnt/c/Users/naoki/.codex `
  RAOS_CODEX_BIN=/mnt/c/Users/naoki/.codex/bin/wsl/b53f5e5f7452dd19/codex `
  .venv/bin/python scripts/codex_harness.py run --
```

native DesktopでGSDを非表示にすることは、このscoped CLIの合意済み範囲に含めません。
Desktopの制約を受け入れた上でCLIを使い、Global GSDは変更しません。
既存会話への遡及適用も前提にしません。別ホストや上流更新時には、同じprocess環境で
`inventory --runtime`の実ロードpathと通常起動・scoped起動の差を確認してproject設定を合わせます。
Instruction/Skillカタログ上限を削って情報を隠す方法は使いません。

外部能力はGitHub appの必要toolと2つのbounded WordPress MCPに限定します。
MCPの保存済みcheckout起動先は資格情報を扱う既存境界であり、worktreeへ自動変更しません。
設定されたtool、実際に公開されたtool、optional能力、接続不能は別々に診断します。
live状態はMCP statusで確認し、過去の監査結果から推測しません。

inventoryと構造検査は、上記subshell内で`run --`の代わりに次の既存コマンドを実行します。
Windowsからは同じ`wsl ... --exec env ...`の末尾を置き換えます。

```sh
.venv/bin/python scripts/codex_harness.py inventory --host --runtime --output /tmp/raos-harness.json
.venv/bin/python scripts/codex_harness.py check
```

WordPress statusの実呼出しはopt-inです。`--wordpress-status`には`--runtime`が必要です。

```sh
.venv/bin/python scripts/codex_harness.py inventory --host --runtime --wordpress-status --output /tmp/raos-harness-status.json
```

このoptionは設定済みstdio bridgeを使い、`wordpressEditor`の`raos-codex-site-status`と
`wordpressDeployment`の`deployment-status`だけを固定の読み取り専用呼出しとして実行します。
通常のruntime inventoryと同じcontrollerでhost・config・auth・repositoryを読み取り専用に保ち、
書込みstateを使い捨て領域へ分離します。bridgeの保存済み起動先は維持し、
結果の`startup_checkout`・`startup_commit`でどのcheckoutを使ったか確認します。

設定上の許可、`tools/list`に公開されたcatalog、`tools/call`の実行結果は別々の証拠です。
`runtime_wordpress_status`で必須statusの実呼出し結果と`configured_but_unavailable`を確認します。
optionalなaggregate・operation-status等はcatalogにない場合も区別して記録し、
2つのstatus呼出しのPASSをoptional能力の存在・動作確認へ広げません。
その時点のtool数・Skill数・commit・status結果はinventory出力で扱います。

Host inventoryはSkill metadata・Plugin cache manifest・設定の非秘密項目だけを扱います。
runtime inventoryのcontrollerはhost・config・auth・対象repositoryを読み取り専用で参照し、
cache・state等の書込みは使い捨て領域へ分離します。認証値をコピー・表示しません。
`config/read`には対象repositoryの`cwd`を明示し、そのcheckoutのproject設定を解決します。
このinventory用の書込み隔離を、通常の対話用`run --`にも適用されるものとは扱いません。
Plugin cacheの存在はinstall/on状態や利用頻度の証拠ではありません。
`runtime_skills`は通常起動、`scoped_cli_skills`は標準入口の実ロード結果です。
上流でproject Skill filterに対応した際も両結果を比較して互換経路を外します。

必要なlocal validationはexact PostgreSQL 18.4とPHP 8.3を使います。
取得先・digest・runtime探索は共有toolchainの`scripts/raos_test_runtime.py`が所有し、
ここへ複製しません。`make setup`で依存とPostgreSQLを準備し、PostgreSQLだけを準備し直す場合は
`.venv/bin/python scripts/verify_dev_toolchain.py --test-runtime-only`を使います。
選択された必須DB testでruntime不在・version不一致をskipによる成功にしません。
`RAOS_PG_BIN`・`RAOS_PG_LIB`・`LD_LIBRARY_PATH`はpytestの子processにも引き継ぎます。

```sh
.venv/bin/python -m pytest -q tests/test_runtime
.venv/bin/python -m pytest -q \
  tests/editorial_measurement_v1/test_contract.py \
  tests/st1704_publication_operator/test_draft_writer_read_projection_behavior.py \
  tests/st1704_publication_operator/test_draft_writer_role_behavior.py \
  tests/st1704_publication_operator/test_terminal_reconciliation_behavior.py \
  tests/wordpress_mcp_v1/test_batch_status_bindings.py
```

前者はPG18.4のsocket-only smokeとruntime境界、後者はPHP8.3のrate・retention・
read projection・role・terminal reconciliation・batch statusの動作を確認します。
local PHP CLIがない場合は共有toolchainの既存`scripts/test-runtime-bin/php`が固定imageの
PHP CLIを使います。固定imageは事前配置が必要で、自動pullはしません。
実行はnetworkなし・読み取り専用・capability削除とsource／synthetic fixture mountに
限定します。WordPress serverは起動しません。`make fast`と直接のpytestはこの探索を共有します。
PHP7.4互換性の専用CIは維持します。`live`・`external`・`raos_owner_private`と
旧workflow proseに対する意図的skipはこの必須runtime検証と区別します。

## Cold-start evaluation

```sh
.venv/bin/python scripts/codex_harness.py eval --ref <before-commit> --model <configured-model> --reasoning <configured-effort> --output /tmp/raos-before.json
.venv/bin/python scripts/codex_harness.py eval --ref <after-commit> --model <same-model> --reasoning <same-effort> --output /tmp/raos-after.json
.venv/bin/python scripts/codex_harness.py compare /tmp/raos-before.json /tmp/raos-after.json
```

上の標準入口と同じprocess-scoped環境で実行します。
各ケースは3回、新規checkoutと会話で実行します。Before/Afterとも`run`と同じSkill設定解決を
使います。評価はlocal sourceとrecorded WordPressだけに限定し、shellのネットワーク・home・
保存済みcheckoutへのアクセスを遮断します。既存Codex認証はcontrollerだけが利用します。
controllerにも読み取り専用のホストmountを適用し、Home・PID・`/tmp`・cacheを分離します。
既存認証ファイルは読み取り専用mountで参照し、値のコピー・表示はしません。
`--ignore-user-config`は書込み隔離にはならないため使いません。無効な継承MCP transportの
補完はBefore/After共通のoffline fixtureです。隔離できないホストでは実評価を実行しません。
採点コードと問題注入は評価対象へ渡しません。生の推論・prompt・event列は保存しません。
差分、syntheticな設計/レビュー結果、参照path、操作名、検査と利用量を保存します。

採点の8項目は動作に基づくproxyです。日本語の自然さ、設計理由、Objective Checksumの
妥当性は保存された成果物もレビューします。case別中央値の維持、受入達成、境界違反ゼロを
確認し、timeout・起動不能・採点不能はPASSに換算しません。製品AI出力のevalと混同しません。

評価Cは新規rendererと公開投影のdomain・隔離testに検査範囲を限定します。通常開発の
未対応入力・共通基盤に対する全件選択は維持し、実リポジトリの`make fast`で別途検証します。
採点環境だけが失敗した場合は、commitと保存差分を復元して同じ入力で再採点できます。
`eval --regrade /tmp/raos-before.json --output /tmp/raos-before-regraded.json`はモデルを再実行せず、
元の採点結果も保存します。task/fixtureが異なる結果や未固定worktreeは再採点できません。
再採点が通っても、元のモデル実行がtimeoutなら受入成功にはなりません。
