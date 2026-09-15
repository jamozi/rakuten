# Codex harness operations

Codex設定・スキルの運用とハーネス評価を変更・検証する時に読む。
製品の構造は [current architecture](../architecture/current-system.md) が所有する。

## Codex context and capability boundaries

AGENTSは常時の目的・不変条件と地図、READMEは人間の開発案内、Skillは反復workflowを所有します。
S/M/L/XLとObjective ChecksumはAGENTSの探索方針を使い、各Skillへ複製しません。
RAOSのscoped CLI起動・inventory・必要runtimeの手順はこの節を正本とします。

Project設定は`.codex/config.toml`、workflowは`.agents/skills/`です。
Global preference・Plugin install state・個人Memoryをrepositoryへコピーしません。
GSD・Superpowersの通常時無効化はユーザー設定が所有します。Windows/WSLそれぞれの有効な
Codex homeへ `[[skills.config]]` の `path` / `enabled=false` を設定し、配布元のスキルは編集しません。
使う時は該当スキルの設定を `enabled=true` に戻して再起動します。プラグイン更新後はパスの失効を確認します。
個人設定をこのrepositoryへ複製しません。

既存のscoped CLIは、ユーザー設定と任意のproject Skill selectorをsession overrideへ渡す互換経路です。
同じselectorではprojectを優先し、権限や承認設定は変更しません。通常起動とscoped起動の実ロード結果を
比較して判断します。現在の版や実行pathは `codex --version` / `command -v codex` で確認します。
`RAOS_CODEX_BIN` は明示した実行ファイルを選び、未指定時はPATH上のCodexを使います。

```sh
.venv/bin/python scripts/codex_harness.py run --
```

Codex homeは現在のprocessの `CODEX_HOME`、未指定時はユーザーhomeの `.codex` です。
WindowsとWSLのCodex homeを取り違えないでください。設定変更は新しい起動で確認し、
既存会話への遡及適用やCLIでの結果をDesktopの確認済み証拠として扱いません。
Instruction/Skillカタログ上限を削って情報を隠す方法は使いません。

外部能力はGitHub appの必要toolと2つのbounded WordPress MCPに限定します。
MCPの保存済みcheckout起動先は資格情報を扱う既存境界であり、worktreeへ自動変更しません。
設定されたtool、実際に公開されたtool、optional能力、接続不能は別々に診断します。
live状態はMCP statusで確認し、過去の監査結果から推測しません。

inventoryと構造検査は、同じprocess環境で`run --`の代わりに次の既存コマンドを実行します。
Windowsからは対象checkoutのあるWSL上で実行します。

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
.venv/bin/python scripts/codex_harness.py eval --ref <before-commit> --model <configured-model> --reasoning <configured-effort> --context /private/before-context.json --output /tmp/raos-before.json
.venv/bin/python scripts/codex_harness.py eval --ref <after-commit> --model <same-model> --reasoning <same-effort> --context /private/after-context.json --output /tmp/raos-after.json
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

### Global context and efficiency evidence

`eval --context` は、非公開のJSONで共通指示とSkillの選択設定だけを固定します。
全config、認証値、MCP定義、環境変数は受け付けません。入力形式は次のとおりです。

```json
{
  "version": 1,
  "global_agents": {"name": "AGENTS.md", "content": "固定する共通指示"},
  "skills_config": [{"path": "/path/to/skill/SKILL.md", "enabled": false}]
}
```

実際のglobal overrideが非空なら `name` は `AGENTS.override.md` とし、その内容を使います。
空の `skills_config` は意図的な空設定であり、実行中の個人設定を継承しません。
共通指示は使い捨てcontroller homeへ渡し、報告には内容ではなく入力の識別hashだけを残します。
評価には同一CLI版・model・reasoning・task/fixture・採点基準・時間制限を使います。
モデルに渡す共通設定はこの入力で固定し、評価中は参照元Skillのインストール・内容を変更しません。
plugins/apps/memoryは隔離評価で無効なため、その削減効果やDesktop全体の費用を実測したことにはなりません。

既存A–Eを各3回実行し、`compare` の `quality_status` と `efficiency` を別々に確認します。
トップレベルの `status` は従来どおり品質判定です。採用には `efficiency.adoption_status=PASS` が必要です。
input + outputのcase別中央値を等重みで平均し、品質低下・境界違反なく減少した時だけ採用可能とします。
cached inputはinputの内数です。欠損・不正な値や旧計測方式は `UNAVAILABLE` とし、0へ変換しません。
read量・tool数・時間と個別caseの悪化も併記します。tool数は観測できたshell実行とMCP呼出の合計で、
編集eventやprovider内部の呼出数は含みません。3回の結果を一般的な性能保証にはしません。

`--case F --case G --repetitions 1` はRAOSのsource/指示を含まない独立プロジェクトで、
小規模Python修正と日本語の利用案内を確認する補助検証です。A–Eの効率比較に混ぜません。
`inventory --host --runtime` は、指示の探索順・容量の推定、スキル設定と実ロードの差を報告します。
`NOT_DISCOVERED` はselector失効・非対応scope・plugin不在を調べる入口であり、削減成功ではありません。

設計根拠: [OpenAIの指示設計ガイド](https://learn.chatgpt.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)、
[AGENTS.mdの探索規則](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、
[Skillの段階的読み込みと無効化](https://learn.chatgpt.com/docs/build-skills)（2026-09-15確認）。
