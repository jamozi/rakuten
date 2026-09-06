# RAOS Codex Harness audit — 2026-09-06

## 1. Executive Summary

- Global設定上書き事故は、合意された回収済み項目からの再構成で解消した。Desktop・通知・Memoryを保持し、一時trust19件だけを除去した。不明な元値は現在値または既定値を使い、完全な原状復元とは区別する。
- 評価とruntime inventoryを読み取り専用host mount・独立Home/cacheで隔離し、Global設定・認証への書込み拒否を検証した。CIでも隔離ツールの導入・起動確認を必須にした。
- AGENTSはMissionと不変条件から始まる83行のBootloaderへ変更。2,342→1,754 o200k tokens（25.1%減）。
- 現行V3・対象限定の後継設計・実装・検証先を目的別の地図へ接続した。immutable baselineと履歴は維持する。
- Skillは編集レビューとWordPress workflowの2件。詳細は既存contract/runbookが所有する。
- 専用CLIは有効95→30件、GSD0件。既存Sora/Speech無効化もWindows・WSL・隔離mount間で維持する。Global GSDやPlugin本体は変更していない。
- 不要App4件とAPI-key MCPをProjectで無効化。GitHub28＋WordPress15の実観測toolを選択し、WordPress承認境界と保存済みcheckout起動を維持した。
- PostgreSQLの既存19失敗を原因別に修正。権限を増やさず、並行保存・rollback・再upgrade・有効構造digest・履歴graphを検証した。
- 未実行PHP6件を8.3で実行し、PHP7.4互換CIも合格。履歴7skipには現行behavior7件を対応付けた。
- 拡張CIで判明したreaderの185型エラーを修正。記事10件と境界753件の結果は同一で、Pyrightは0件。
- 最終Before/After各15実行は比較PASS。品質中央値はA/B/C16点を維持、D/E14→16点。失敗・時間切れ・大きな出力の外れ値も履歴へ残した。
- 最終コードのローカル標準検証と拡張CIは合格。報告を含むRequired CI、merge SHA、ローカル同期の証拠は[統合PR #189](https://github.com/jamozi/rakuten/pull/189)へ集約する。

## 2. Project Objective Map

| 項目 | 復元した目的・制約 | 正本 / 実装 |
| --- | --- | --- |
| Mission | 読者の信頼できる購入判断を支え、品質制約のもとで持続的な確定貢献利益を改善する | [Editorial V3](../editorial-portfolio-v3/README.md) |
| Primary metric | `MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT_JPY`。確定報酬−変動外部費用−編集時間/60×承認済み時間単価 | [strategy contract](../editorial-portfolio-v3/editorial-portfolio.v3.json) |
| User value | 正確な商品同定、用途に合う比較、根拠・弱点・範囲が分かる自然な日本語、購入判断を助ける導線 | V3 identities / market-candidate audit、decision support |
| Product non-negotiables | 一次情報、鮮度、追跡可能な根拠、UNKNOWN/UNAVAILABLE、広告表示。料率・価格・楽天取扱有無を選定の加点要素にしない | V3 selection policy、`tests/editorial_portfolio_v3/`、`tests/raos_v2/` |
| Architecture | domain/application/ports/adapters。承認済みsnapshot→public projection。公開rendererから内部Evidence・Finance・raw AIへ直結しない | [current system](../../docs/architecture/current-system.md)、`tests/st0902_v2/`、`tests/st0905/` |
| Finance boundary | 推計を確定値にしない。欠損をゼロや成功にしない。編集判断へ財務情報を混入させない | reconciliation、economics CLI、V3 strategy |
| Operational boundary | local開発と通常GitHub操作は継続承認。live write・支出・公開・staging・deployment・release・Production・不可逆操作は対象操作の承認が必要 | [AGENTS](../../AGENTS.md)、[WordPress runbook](../../docs/runbooks/wordpress-verified-incremental.md) |
| WordPress | 非本番データとlocal previewが先。独立2巡、Required CI、wp-admin別人承認、期限、対象hash、precondition、idempotency、kill switch、default-off | `tests/wordpress_mcp_v1/`、`tests/wordpress_local_preview/` |
| Roadmap / actuals | 新規記事は実測データのgateを満たすまで増やさない。実装済みとlive検証済みを分ける | [status v2](../status/README.md)、[ASP初回接続 Issue #165](https://github.com/jamozi/rakuten/issues/165)、[readiness tracker #57](https://github.com/jamozi/rakuten/issues/57) |

実測利益・CVR・運営時間・現在のlive gate値は今回取得していないためUNKNOWN。技術の整備を事業成果と同一視しない。Issue #165と#57は監査時点でOPEN。旧ExecPlanのACTIVE表記は現在の作業権限・進捗の根拠にしない。

## 3. Current Harness Inventory

サイズの明細は[inventory.json](inventory.json)、比較・Skillごとの判断と資源数は[metrics.json](metrics.json)。数値はファイルの文字数・指定encodingでの計測であり、実際の課金context量ではない。

| Component | Current role | Always loaded | Size / cost | Used? | Problem | Decision |
| --- | --- | ---: | ---: | --- | --- | --- |
| root AGENTS | Mission、不変条件、案内、境界 | root作業時 | 83行 / 1,754 tokens | YES | 旧版は開発手順が先 | REWRITE |
| canonical nested AGENTS ×2 | import時のbaseline | NO、対象scope次第 | 各90行 / 1,056 tokens | 履歴 | 同一内容と旧workflow | KEEP immutable、常時案内しない |
| AGENTS.override | なし | NO | 0 | NO | なし | 追加しない |
| README | 人間向け導入・commands・CI | NO | 111行 / 1,970 tokens | YES | WordPress手順の重複 | REWRITE、runbook参照 |
| docs map / architecture | 適用範囲・実装・検証先 | NO | metrics参照 | YES | 旧必読順、初期placeholder | REWRITE |
| canonical / upstream / ZIP | 不変な原設計と由来 | NO | 必要な領域だけ取得 | YES | 現行statusと誤認しやすい | KEEP、適用範囲を明示 |
| execution plans | 当時の判断・履歴 | NO | 履歴本文は維持 | 条件付き | 古いACTIVE表記 | 2入口に履歴注記 |
| Project Skills | 反復workflow | metadataのみ | 2件、本文566 / 659 tokens | YES | 旧版0件 | CREATE 2 |
| GSD | 別の計画・実行framework | CLIの発見対象 | 65件、name+descriptionは1,217 tokens | 頻度UNKNOWN | RAOSの現行workflowと競合 | Project選択でDISABLE、Global削除なし |
| その他Global Skills | 共通文書・UI・security等 | metadata、本文は条件付き | 個別明細はmetrics | 頻度UNKNOWN | 一部Pluginと重複 | KEEP shared、RAOSへコピーしない |
| Plugins | 共通能力の配布 | host/feature依存 | cache 32 directory、install数ではない | 頻度UNKNOWN | 古いversionと複数配布元が混在 | Global本体を変更しない |
| MCP / Apps | 外部情報・操作 | discovery / policy依存 | Project選択はGitHub28＋WP最大17 | YES | 不要Appの明示有効設定が継承される | explicit false＋allowlist |
| rules | Globalの実行規則 | 条件付き | active homeに567 bytesの1ファイル | 頻度UNKNOWN | Project固有ではない | KEEP、Project rule追加なし |
| hooks | 明示Project hookなし | NO | 追加0 | NO | proseを強制停止hookへ移す必要なし | 追加しない |
| subagent | bounded implementation worker | 委任時 | 15→9行、245→131 tokens | DB・runtime実装と独立レビューに使用 | root規律の複製 | root参照へ縮約 |
| fallback / model instruction | 明示設定なし | NO | defaultの上限は変更しない | NO | README強制読込を追加すべきでない | 追加しない |
| Memory | 探索の補助 | 実ロード量UNKNOWN | 個人本文は取得しない | UNKNOWN | 正本・承認にしてはいけない | 設定変更なし |
| helper scripts / CI | generator、差分選択、決定的検証 | NO | 既存build registryを利用 | YES | Instructionsが検証選択から除外 | 既存plannerへ接続 |
| native eval CLI | inventory/check/eval/compare、scoped run | NO | 単一CLI＋fixture/grader | YES | controllerの書込み隔離不足 | evalとinventoryをmountで機械的に隔離 |

Active homeはWindows側 `/mnt/c/Users/naoki/.codex`。Linux側の旧config・親ディレクトリのAGENTSを、このセッションにロードされた情報とはみなしていない。Globalの当初AGENTSは0 bytes。Global再構成後に通常CLIと専用CLIを新規起動して再確認した。catalog全97件のうち通常経路の有効95件、専用CLIの有効30件（GSD0件、Project Skill2件、既存disable2件を維持）。AppはGitHubだけがenabled/callableで、実設定を`config/read`の明示cwd付き応答から確認した。

## 4. Redundancy / Conflict Matrix

| Information | Locations | Conflict | Canonical target | Action |
| --- | --- | --- | --- | --- |
| 最上位目的 | 原設計、V2、V3、旧AGENTS | AGENTSは速度・開発手順が先 | 現行V3 contract、AGENTSに短いchecksum | Missionと優先順位を先頭へ |
| 現行仕様 | v1 master、v2、V3、status | 日付・versionだけでは適用対象を決められない | docs map | 対象別の採用関係を明示 |
| Codex必読順 | docs README、importer、test | 旧workflowを機械的に必須化 | docs map | baselineへの到達性を検証し、順序固定を廃止 |
| WordPress手順 | AGENTS、README、runbook | 詳細を複数文書で保守 | 既存publication runbook | AGENTSは境界、READMEは入口、Skillはworkflow routing |
| 開発・CI | AGENTS、README | ジョブ数・実行手順を二重管理 | README / build planner | AGENTSは標準入口だけ |
| 現在のarchitecture | generated README、実装 | 現在もinertと読めるplaceholder | current-system＋実装 | 生成元から案内を更新 |
| contracts README | bootstrap generator、ST-0104 installer | 通常文書の旧byte hashを固定 | bootstrap owner | ownerから再現される内容を検証、package pinは維持 |
| Pro / Story / 停止条件 | root / worker / prose tests | 一字一句の一致を品質判定に使用 | root、構造・振舞いtests | workerの複製と文章固定assertを除去 |
| Apps継承 | Global個別true、Project `_default=false` | 個別trueはdefaultで消えない | Project explicit false | 継承を再現するnegative test |
| GSD無効化 | Project `skills.config`、Codex0.153.4 | 設定を保存しても実Skill一覧へ反映されない | Project config＋scoped CLI | session selectorへ昇格、Desktop効果を分ける |
| disabled MCP transport | 継承依存のnode_repl宣言 | 単独のProject読込でinvalid transport | Project config | `/usr/bin/false`の完全な無効宣言 |
| user config無視 | eval CLI flag、CLI trust保存 | 読込を無視してもGlobalへの書込みが起きる | controller | eval・inventoryとも読み取り専用mountとprivate Homeで保証 |
| runtime設定読取 | config/read、App catalog | cwdを省くとGlobal層だけを返す | Harness inventory | 明示cwdとnullable値を扱い、Project再公開の回帰検査 |
| Global Skill path | Windows設定、WSL、private Home | path不一致でdisableが失われる | 専用CLI/inventory | 既知Homeのaliasとmount先だけ変換、無関係なpath・同名Skillを維持 |
| 評価状態 | per-run結果、report状態、終了コード | 失敗や再採点が旧PASSを残す | Harness CLI | aggregate状態を再計算、INCOMPLETE/FAILを非ゼロ終了、grader/timebudget不一致を拒否 |
| DB構造digest | PostgreSQL内部catalog、downgrade | 削除済み列の内部情報が有効構造へ混入 | migration runner | dropped列を除外、有効列・制約・権限の検査を維持 |
| migration履歴とfixture | ST-0303/0306、future graph | 旧revisionと累積HEAD、後継fixtureが混在 | 対象revisionのgraph | 歴史と最新HEADを分け、後継revisionの履歴・排他を検査 |

## 5. Target Architecture

```text
repository/
  AGENTS.md                              # Always-on: 目的・不変条件・短い地図
  README.md                              # Human: 導入・commands・開発案内
  .codex/config.toml                     # Projectの能力制御、host固有の既存起動先
  .codex/agents/implementation-worker.toml # 委任時のownershipと出力契約
  .agents/skills/
    raos-editorial-review/SKILL.md        # 記事・商品比較のレビュー
    raos-wordpress-workflow/SKILL.md      # 既存WordPress段階へのrouting
  docs/README.md                         # 現行・後継・履歴の地図
  docs/architecture/current-system.md    # 実装・data flow・不変条件・検証先
  docs/runbooks/                         # 既存の専門手順
  workspace-layout.json                 # generated READMEの入力
  scripts/codex_harness.py               # 計測・検査・実評価・比較・CLI互換起動
  scripts/raos_test_runtime.py           # PostgreSQL/PHPの固定runtimeと子process環境
  scripts/test-runtime-bin/php          # 既存PHP入口の隔離fallback
  tests/evals/codex_harness/              # synthetic入力、独立grader、回帰tests
  changes/codex-harness-v1/               # この監査の報告と計測結果
```

Sは対象と関連test、Mはsubsystemと利用側、Lはdata flowと隣接領域、XLはMission・採用判断まで読む。L/XLと曖昧なMで、要求・上位目的・指標・影響域・隣接影響・正本・不可逆作用・非対象を確認する。局所不具合も症状・根因・違反不変条件・隣接影響から最小の完全な修正を選ぶ。

codeはlocal search、architectureはcanonical map、Issue/PR/CIはGitHub、Gitはlocal、現在のAPIは公式docs/web、反復手順はSkill、決定的作業はscript/testへ進む。正本へ到達後は探索を打ち切り、全履歴の読込を通常手順にしない。

## 6. Skills Architecture

| Skill | Trigger | Scope | Keep/Create/Merge/Delete | Reason |
| --- | --- | --- | --- | --- |
| raos-editorial-review | 記事・商品比較の品質レビュー | identity、evidence、比較範囲、日本語、読者の導線、selection policy | CREATE | 既存V3記事・候補監査で反復するまとまり |
| raos-wordpress-workflow | WordPress編集・表示確認・公開準備・再開 | 依頼された段階まで既存runbookを実行 | CREATE | preview・prepare・承認・通信断回復に繰返し現れるworkflow |
| GSD 65件 | GSD固有のphase/milestone等 | 別framework | DISABLE_IN_RAOS | 現行RAOSはStory/ExecPlan単位の強制workflowを採用しない |
| content-and-copy / security / browser / document系 | 共通の専門作業 | 複数project共通 | KEEP_SHARED | RAOSへ複製しない。今回のSkillと開始条件を区別する |
| Sora / Speech | ユーザーの既存disable | Global preference | KEEP_DISABLED | Global再変更なし。専用CLIで正確なpath選択を維持 |
| system creator / installer / docs等 | それぞれの明示的な作業 | Codex共通 | KEEP_SHARED | repo固有手順の所有元にはしない |
| Plugin由来Skills | connected appまたは共通専門能力が必要な時 | host依存 | KEEP_SHARED / Project appは必要時のみ | キャッシュだけから不要・利用頻度を断定しない |

2つのProject Skillは、非trigger、input、正本参照、procedure、validation、output、失敗・残条件を定義する。本文を知識百科事典にせず、既存contract/runbookへ進む。新しいtemplate/script bundleは追加していない。Global Skillごとの名前、サイズ、references/templates/scripts数、判断はmetricsに記録した。

## 7. Plugin / MCP Architecture

| Capability | Mechanism | Enabled | Scope | Reason |
| --- | --- | ---: | --- | --- |
| GitHub | hosted App | ProjectでYES | Issue/PR/review/CI読取、通常PR作成更新・ready・merge等28 tool | local Git、未対応のghと役割分担 |
| wordpressEditor | pinned launcher＋bounded MCP | YES | allowlist9、監査で観測8 | content/status/draft/proposal。別人承認を代替しない |
| wordpressDeployment | pinned Node bridge＋bounded operator | YES | allowlist8、監査で観測7 | bounded deployment/recovery、既存gateを維持 |
| WPWriter / WordPress.com | inherited Apps | NO | RAOS内だけ無効 | 汎用CMSへの迂回・能力重複を防ぐ |
| Figma / Outlook | inherited Apps | NO | RAOS内だけ無効 | 今回の反復workflowに不要、個別trueを明示override |
| API-key local confirmation | inherited MCP | NO | inert direct declaration | 常時必要なRAOS能力ではない |
| raw GitHub / fetch / filesystem / memory / sequential-thinking / Figma / Linear / Notion / node_repl | direct MCP | NO | 既存のdisabled宣言 | shell・official web・bounded能力との重複を避ける |
| Pro用Playwright | disabled direct MCP、既存orchestratorのchild | 常時NO | 明示された任意のPro作業 | pinned wrapperと用途を維持。Pro不在で開発を止めない |
| OpenAI docs | official web、必要時のdocs Skill | on-demand | 現行仕様確認 | 常時MCPを増やさない |
| その他shared Plugins | Global cache / install | Plugin本体は未変更 | Global config事故は第11章 | cache数をinstall数・不要数と混同しない |

32のcache directoryには、codex-app-tools、computer-use/unified-computer-use、sites、visualize、旧curated/remoteのCanva・Figma・GitHub・Hugging Face・Notion・Slack、codex-security、WPWriter、WordPress.com、Google Drive、deep-research、openai-developers、openai-templates、Outlook、plugin-management、Replit、local documents/PDF/presentations/spreadsheets/template-creatorが含まれる。同名の旧versionを削除・uninstallしていない。個別versionとSkill一覧はmetricsを参照する。利用頻度はUNKNOWN。

WordPress起動先は `/home/minami/rakuten` のまま。今回のworktreeとそのcheckoutのcode revisionは別物であり、設定だけでlive状態を推定しない。optionalなaggregate reportとoperation-statusの未公開をserver全体の障害と混同しない。両MCPの固定status実呼出しは成功した。応答本文や個人情報を保存せず、tool名・応答field名・起動checkoutのSHAをinventoryへ保存する。serverごとの正確なstartup時間はUNKNOWN。catalog取得時間・公開tool数・選択schema量は別の量として記録する。

仕様確認は導入済みCodex 0.153.4のhelp・app-server応答と、[公式config reference](https://learn.chatgpt.com/docs/config-file/config-reference)、[AGENTS](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Skills](https://learn.chatgpt.com/docs/build-skills)、[MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[rules](https://learn.chatgpt.com/docs/agent-configuration/rules)、[hooks](https://learn.chatgpt.com/docs/hooks)、[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[memories](https://learn.chatgpt.com/docs/customization/memories)、[app-server](https://learn.chatgpt.com/docs/app-server)による。
Project Skill filterには[OpenAI upstream issue #20210](https://github.com/openai/codex/issues/20210)と一致する制約があった。permissions profileの選択には実CLI/schemaが受け付ける`default_permissions`を使い、受け付けなかった`permissions.default`は採用していない。

## 8. Changes Implemented

| Files / owner | 実変更と理由 |
| --- | --- |
| AGENTS / README / docs README | Missionを先にし、人間向け手順・agent routing・正本の役割を分離 |
| current-system / architecture・runbook・eval README | 実装と不変条件の検証先へ案内 |
| .agents/skillsの2件 | 編集レビュー、WordPress段階の反復workflow |
| .codex/config.toml / implementation-worker | 明示App override、GitHub allowlist、GSD selectors、無効transport補完、root規律の参照 |
| workspace-layout / bootstrap_workspace | 生成READMEをownerから更新し、初期placeholderを歴史として説明 |
| import_raos_design / importer tests | 一律の旧必読順からbaseline入口の整合性検証へ。archive/path/symlink/checksum保護は維持 |
| ST-0104 installer / installer tests | 通常READMEの固定digestをownerの再現性検証へ変更。原契約packageのpinは維持 |
| raos_test_plan | root/nested/override Instructions、Skills、.codexを検証選択へ接続。共通基盤の全件fallbackは維持 |
| codex_harness / cases / fixtures / regressions | JSON計測、links/anchors、継承再公開negative tests、native新規評価、独立採点、timeout拒否、controllerのwrite isolation |
| 既存Pro・Story・ST-0104・開発規則tests | 文言一致のassertを除去。transport/allowlist/worker schema、公開・承認の振舞い検査と実commandの案内検査は維持 |
| 2つの旧ExecPlan入口 | 現行命令として扱わない履歴注記 |
| generated manifests | 変更した入力に対応するowner生成物を更新。承認済みlive候補は変更しない |
| google_live persistence / migration runner / PG tests | immutable snapshotのFOR SHAREを除去。worker権限を増やさず並行保存・競合・rollbackを保証。有効構造digestと歴史/最新/future graphを修正 |
| raos_test_runtime / verify_dev_toolchain / conftest / CI | 固定PostgreSQL 18.4の実行ファイルとlibraryを子processへ渡し、必要DB検査のruntime欠落を失敗にする。PHP 8.3と7.4 CIを維持 |
| readerの4 moduleと関連test | object-valued JSONの型・検証を明確化。型検査を抑制せず、出力・公開境界・既存挙動を維持 |
| runtime/phase3/history tests | PHP実行経路、上書き設定、隔離、現行workflowのzero-action・activation拒否を検証 |
| .gitattributes / evals artifacts | unified diffの空context行のspaceを保持するため、保存patchだけに既存のbyte保存方式を適用。製品sourceのwhitespace検査は維持 |

製品の公開API・データ契約・順位ロジックは変更していない。canonical/upstream/ZIPに差分はない。今回、記事・テーマ・pluginの本番送付、公開提案・適用、staging、deployment、releaseは実施していない。local generatorが出すProduction関連の検査表示は実Production evidenceではない。

## 9. Before / After

| Metric | Before | After | 解釈 |
| --- | ---: | ---: | --- |
| root AGENTS lines | 91 | 83 | 行数を合格条件にはしていない |
| root characters / bytes | 4,906 / 8,962 | 3,973 / 6,535 | 日本語を含むUTF-8 |
| root tokens | 2,342 | 1,754 | o200k_baseで25.1%減 |
| README tokens | 1,858 | 1,970 | 人間向け説明と導入を整備したため増加、常時投入ではない |
| docs map tokens | 815 | 1,110 | 現行・後継・実装の案内を追加、on-demand |
| worker tokens | 245 | 131 | root規律の複製を縮約 |
| Project Skills | 0 | 2 | workflowだけ追加 |
| Project Skill name+description | 0 | 161 tokens | 本文は条件付きで1,225 tokens |
| GSD name+description | 1,217 tokens / 65件 | scoped CLIでは無効化対象 | path表示・system instructionsを含む実投入量とは別 |
| 同一HomeのSkill実ロード | 通常経路で有効95件 | 専用CLIで有効30件 | catalog全97には既存disable2件を含む。GSD65件をProjectで無効化。初期監査93件とは測定条件を分ける |
| WordPress詳細の所有箇所 | AGENTS / README / runbook | runbook | 他は短い境界・入口へ。逐語的な重複率とは別 |
| 新規nested AGENTS / hooks / plugins | 0 | 0 | 探索・運用面を増やさない |
| 外部能力 | セッション開始時320能力が発見可能 | runtime policy選択43 tool、catalogのAppsは484 tool | 集合が異なるため320→43の削減率にはしない。選択schemaは10,472 o200k tokens、常時投入量ではない |
| 明示的に除外した継承能力 | 4 App＋API-key MCP | Projectでfalse | Globalのinstall/on状態は変更対象外 |

rootとGSDのname+descriptionだけの小計は3,559 tokens。GSDを除外したscoped CLIのroot＋新規Skill metadataは1,915 tokensとなる。この差1,644 tokensは、共通Skills、path表示、system/developer指示、会話、動的tool schema、Memoryを含む総context削減量ではない。

重大な重複は同じ手順の全文管理を減らす方向で解消した。immutableな同一AGENTSや履歴本文は保存した。品質を文章の語数・単語の有無・固定test総件数で採点しない。

## 10. Eval Results

[ケース](../../tests/evals/codex_harness/cases.json)と[独立grader](../../tests/evals/codex_harness/fixtures.py)を固定し、gpt-6-astra / max、各ケース3回、履歴のない一時checkoutとfake外部能力で実行した。Beforeは`9001a77b38cf82f9467bd461d1177ec8aa299254`、Afterは`0d1a5eccb9a3125641734135a04de3ac97c60223`。controller isolation v3、fixture、grader、model/reasoningは一致する。制限時間は両側ともB1,200秒、その他600秒。

| Eval | Before | After | Regression | Notes |
| --- | ---: | ---: | --- | --- |
| A Local | 3/3、中央値16 | 3/3、中央値16 | なし | 読取出力中央値62,101→38,688 chars（37.7%減）。0・空値・alias優先順位 |
| B Multi-module | 3/3、中央値16 | 3/3、中央値16 | なし | 157,328→142,106 chars。config/client/normalization、same-origin、default-off、上限 |
| C Architecture | 3/3、中央値16 | 3/3、中央値16 | なし | 93,384→115,256 chars。公開投影・契約・隣接影響を確認。escape・欠損拒否 |
| D Side effect | 3/3、中央値14 | 3/3、中央値16 | 改善 | 5,662→10,566 chars。runbookとfake両statusへ到達、local prepare、失効承認維持、writeなし |
| E Business | 3/3、中央値14 | 3/3、中央値16 | 改善 | 66,126→52,455 chars。現行V3と編集Skillへ到達。同定・一次情報・UNKNOWN・選定/利益分離 |

[比較](evals/comparison.json)、[Before](evals/before.json)、[After](evals/after.json)に差分・検査・参照先・tool操作・時間・利用量を保存した。重大な境界違反0、全ケース受入達成、中央値非劣化。8項目0〜2点は観測に基づくproxyであり、内的思考の計測ではない。モデルの自己申告では採点しない。

主担当と独立レビューでC全6成果物を確認した。既存の公開2項目、HTML escape、nullableな上流契約、呼出元・内部系への境界を維持し、After全3件は読者が更新・鮮度を判断する目的と非対象を明記した。[設計例](evals/artifacts/final-after/C-1/design.txt)。E全6件はvariant不一致・古い販売店情報からBを除外し、欠損利益null、公開可能性falseを維持した。After全3件はV3の選定要素を使い、未提示値はUNKNOWNとし、架空2商品から市場全体へ一般化しない。[比較例](evals/artifacts/final-after/E-1/review.json)、[成果物レビュー](evals/semantic-review.json)。

指標は分けて読む。input tokensは複数stepの累積でcached inputを含む。Aの中央値は536,509→408,659だが、B・D・Eでは増加している。[利用量](evals/usage-summary.json)。A3の記録された読取出力は1,056,685 chars、うち1つの検証出力が1,015,780 charsだった。外れ値を保持し、全3回が小さな探索だったとは主張しない。コマンド出力量は切詰め後の実投入量・料金ではない。3回の小標本、固定共通Skill環境、fake能力による比較であり、実運用catalog・SEO/CRO・利益実測とは別である。

再構成後の最初の[Before群](evals/before-checkpoint.json)にはBの600秒timeout、[After群](evals/after-checkpoint.json)にはB/CのMODEL_FAILEDがあった。取得できなかった旧MODEL_FAILEDの原因はUNKNOWNのままにし、read-only bootstrap警告だけから推定しない。Before Bは群全体を1,200秒で再実行し、Afterは最終コードで全15件を再実行した。ACDEのBeforeは同じ条件の完全な3回群を保持し、成功した個別実行だけを選び直していない。

さらに古い受信・採点・隔離の不備は[元Before](evals/before-superseded.json)、[元After](evals/after-superseded.json)に残す。Global上書き、stream buffer、fake HTTP/正規化参照、package解決、共有/tmp、test-wrapper計測、fake MCP未到達を試行名だけで数える問題を修正した。旧条件の有効30実行も[旧Before](evals/before-pre-recovery.json)・[旧After](evals/after-pre-recovery.json)へ保存し、最終結果と混在させない。grader identity・ケース別時間制限の不一致を比較で拒否し、失敗・未完了・再採点の状態と終了コードを一致させた。

**実装検証:** 固定依存の`make setup`、owner生成、最終コードの`make fast`が成功した。並列Python20,007 pass / 7履歴skip、直列1,987 pass、実PG18.4のDB348 pass / 0skip、Storage91 pass / 0skip、Node486、Vitest4、PHP8.3.33のsource/generated各85 assertion。全146 owner、静的検査、immutable baseline、secret scanも合格。Harness88件＋検証選択19件は別の最終重点検査で107 passだった。

DBの元19失敗は同じtest IDで修正前/後を対応付けた。workerのUPDATE権限は増やしていない。PHP6件の未実行は解消し、履歴prose7件には現行activation拒否・zero-actionの7ケースを対応させた。reader型修正は10記事と753境界ケースが同一、Pyright0、mypy627ファイル・重点24件も合格。途中の失敗を含む明細は[validation.json](validation.json)。

[拡張CI](https://github.com/jamozi/rakuten/actions/runs/34023014300)は最新29/29 jobが合格。Python22,432 pass / 8skip（履歴7＋local-only ZIP1）、Node486、Vitest4。PG18.4の348件はskipなし、PHP7.4.33で各85 assertion、隔離検査のskipも解消した。初回は既存48条件のブラウザー検査が60.08秒でouter timeoutとなった。同じ入力・runnerで以前は52.52秒、同一SHAの再実行は46.35秒で合格した。失敗shard19とgateだけを1回再実行し、検査・時間制限・Required checkは変更していない。負荷変動は仮説にとどまり、timeoutの原因を証明したとは主張しない。Draftのplan-only successは検証に数えない。

製品のrecorded AI評価は既存suite内の回帰検証として実行し、Codex評価と分ける。これらの結果はlive公開・staging・Production・事業成果の証明ではない。

## 11. Remaining Gaps

合意された実装・設定再構成・ローカル検証・native比較の残課題はない。報告を含むRequired CI、squash merge、merge SHA、両checkoutとlocal/remote mainの同期結果は[統合PR #189の最終実行記録](https://github.com/jamozi/rakuten/pull/189)を正本とする。コード評価checkpointと後続の報告commit・統合状態を混同しない。

Globalは既知項目の再構成で解決する方針をユーザーが承認した。書込み直前の再読込と排他アクセスで同時更新を検出し、書込み前ファイルを`C:/Users/naoki/.codex/recovery/config-before-raos-reconstruction-20260906-160103.toml`へ保全した。model、Skillの既存disable 2件、回収済みfeature/Plugin/App設定を項目単位で戻し、現在のDesktop・通知・Memory・Windows設定を保持した。今回の一時評価のtrust 19件を除去し、実在するRAOSの2 checkoutだけをtrustへ登録した。認証ファイル・Plugin本体・Linux側Global・Global GSDは変更していない。

完全な元ファイルは存在せず、元の`model_reasoning_effort`、`preferred_auth_method`、`personality`、`service_tier`、`shell_environment_policy`は不明なため省略し、Codex既定値を使う。元の通知等もUNKNOWNだが、現在のアプリが保持している設定を優先した。これは合意済みの再構成であり、完全な原状復元を主張しない。個人Memoryの内容、利用頻度、未取得の事業実測値は監査の限界であり、架空の値で埋めない。

DesktopのProject Skill filter制約は上流に残る。RAOS専用CLIを標準経路にする合意済み運用でGSD無効化を実測した。Globalの無効化やinstruction/catalog上限で隠す対処は採用しない。

合意した運用範囲と計測限界は保持する。Desktopの上流制約、回収不能な元の個人設定、未取得の事業実測値、評価のばらつきを架空の値で埋めない。専用CLIと明示された既定値によって今回の範囲を完了する。

| Success criterion | Evidence / status |
| --- | --- |
| SC-01 | PASS — root先頭にMission、現行V3へ1 link。E全3回で正本へ到達 |
| SC-02 | PASS — root83行、仕様全文を持たない |
| SC-03 | PASS — docs map / architecture / Skillのlinks・anchorsと実装参照を検証 |
| SC-04 | PASS — 同定・編集/財務・公開隔離・承認・DB権限/並行実行のbehavior検査 |
| SC-05 | PASS — 手順はrunbook、開発入口はREADME、適用関係はdocs map |
| SC-06 | PASS — Project Skillは2つの反復workflow |
| SC-07 | PASS — 実設定・catalog・WP両statusを分離計測。専用CLI30/GSD0、既存disable2維持 |
| SC-08 | PASS — S中央値37.7%減、L/XLは設計・隣接context取得。外れ値も保持 |
| SC-09 | PASS — C全3成果物に目的・成功条件・正本・隣接影響・非対象・外部境界 |
| SC-10 | PASS — A〜E各3回、両側全受入達成、中央値非劣化、重大な境界違反0 |
| SC-11 | PASS — root25.1%減。metadata数削減を実ロード確認、総課金contextとは区別 |
| SC-12 | PASS — 公開/Production gate維持、controller隔離、Global再構成、実PG/PHPとCI |

自己レビューは2問ともYES。不要な読書を減らすだけでなく、Sでは局所、L/XLでは正本と隣接境界へ到達できることを成果物で確認した。事前知識ゼロでもMission→適用範囲→実装/検証へ進める入口があり、参照切れ・能力再公開・重要境界を継続検査する。半年後もこの構造を使える一方、将来の仕様採用は正本の更新で表し、現在の小標本を無条件の将来保証にはしない。
