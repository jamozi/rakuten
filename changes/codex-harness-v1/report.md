# RAOS Codex Harness audit — integrated source review

## 1. Executive Summary

- 本報告のコード検証対象は `f746e0a1c43141e5d6d27e14ec72cb403f841014`。後続の報告commitとGit統合の実績は[PR #191本文](https://github.com/jamozi/rakuten/pull/191)の最終receiptが所有する。
- Missionは読者の信頼できる購入判断と、品質制約下の持続的な確定貢献利益の改善。目的・正本・編集/財務分離・public投影・承認境界を保持した。
- root AGENTSは91→85行、2,342→1,830 o200k tokens（21.9%減）。目的別地図、既存runbook、2件のProject Skillへ案内し、局所Python検証とM以上・生成・contract・境界のmake fastを分けた。
- f746 runtime inventoryはPASS。catalog97、通常CLI有効95、専用CLI30、GSD0、Project Skill2、選択tool43、schema10,472 tokens。既存disable2件を保持し、総context・課金量と区別する。
- Globalは承認された既知項目から再構成し、その再構成済みconfigとの一致と一時trust0を確認した。事故前の未知の原本へのexact restoreではない。専用CLI標準運用とDesktop上流制約は合意済みの適用範囲である。
- DB・PHP・型検査・隔離・bytecode生成・browser検証の問題を修正した。PR190の読者表示とpublication_authority=falseのlocal guide5本を保持して統合し、147 owner生成/CI検査が合格した。旧0dの出力同一証拠を意図した製品変更へ拡張しない。
- f746の実PR CIは29/29 SUCCESS、Final Integrationも実行成功。Python22,858 PASS / 8skip、Node486、Vitest4、PHP7.4.33 source/generated各85 assertions、mypy628ファイル、147 owner checksが合格。別途明示したlocal Pyrightも0 errors / 0 warnings / 0 informations、26.73秒で合格した。
- f746 native Afterは全15件が品質16、受入達成、比較PASS。A/B/C中央値16を維持しD/E14→16。A独立品質/境界reviewはPASS、最終A/C/E意味レビューと全30 record/48 artifactの独立cohort監査もPASS。
- Aのraw read中央値は62,101→68,381 chars（10.1%増）で削減はNOT_DEMONSTRATED。保存パス上の範囲限定とinput-token減少は別の観測で、主指標を代替しない。SC-08は部分達成であり、全12条件の無条件PASSとはしない。
- f746 local make fastはexit0、1,698.2秒。Python22,859 PASS / 7履歴skip、Node486、Vitest4、PHP8.3.33 source/generated各85 assertions、147 owners・mypy628・static・secret/immutable検査が合格し、生成cache0を確認した。最終native artifact/cohort独立意味レビューも完了し、source検証は完了した。
- PR189のplan-only CIからの早期mergeは、マージ前実行済みRequired CI条件FAILとして保持する。d75事後CI成功は遡及的な充足にならない。是正後f746の実gate成功と、最終report-head CI・merge・同期・AutoMerge復旧receiptを分けて記録する。

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
| Local reader guides | PR190の設置・給排水・洗剤・手入れ・費用5ガイド。publication_authority=false、本番記事へ自動昇格せず根拠欠損はblocker | [採用範囲](../editorial-portfolio-v3/READER_REMAINING_IMPLEMENTATION.md#ローカル専用ガイドの境界)、[renderer](../../python/raos/application/editorial/local_reader_guides.py) |
| WordPress | 非本番データとlocal previewが先。独立2巡、Required CI、wp-admin別人承認、期限、対象hash、precondition、idempotency、kill switch、default-off | `tests/wordpress_mcp_v1/`、`tests/wordpress_local_preview/` |
| Roadmap / actuals | 新規記事は実測データのgateを満たすまで増やさない。実装済みとlive検証済みを分ける | [status v2](../status/README.md)、[ASP初回接続 Issue #165](https://github.com/jamozi/rakuten/issues/165)、[readiness tracker #57](https://github.com/jamozi/rakuten/issues/57) |

実測利益・CVR・運営時間・現在のlive gate値は今回取得していないためUNKNOWN。技術の整備を事業成果と同一視しない。Issue #165と#57は監査時点でOPEN。旧ExecPlanのACTIVE表記は現在の作業権限・進捗の根拠にしない。

## 3. Current Harness Inventory

サイズの明細は[inventory.json](inventory.json)、比較・Skillごとの判断と資源数は[metrics.json](metrics.json)。ファイル計測は対象revisionを付して保存する。root/README、Project設定・Skillsはf746でもbyte不変なので再利用する。別途最新f746 runtime snapshotもPASSを確認し、その新しい観測として記録する。main190でcurrent-system地図は211→214行へ更新され、現行f746は4,192 tokens。旧4,034 tokensはbfdf時点の値である。指定encodingのtoken数と実際の課金context量を同一視しない。

| Component | Current role | Always loaded | Size / cost | Used? | Problem | Decision |
| --- | --- | ---: | ---: | --- | --- | --- |
| root AGENTS | Mission、不変条件、案内、境界 | root作業時 | 85行 / 4,057 chars / 6,811 bytes / 1,830 tokens | YES | 旧版は開発手順が先 | REWRITE |
| canonical nested AGENTS ×2 | import時のbaseline | NO、対象scope次第 | 各90行 / 1,056 tokens | 履歴 | 同一内容と旧workflow | KEEP immutable、常時案内しない |
| AGENTS.override | なし | NO | 0 | NO | なし | 追加しない |
| README | 人間向け導入・commands・CI | NO | 128行 / 5,139 chars / 8,511 bytes / 2,212 tokens | YES | WordPress手順の重複 | REWRITE、runbook参照 |
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

Active homeはWindows側 `/mnt/c/Users/naoki/.codex`。Linux側の旧config・親ディレクトリのAGENTSを、監査でロードされた情報とはみなしていない。Globalの当初AGENTSは0 bytes。f746の最新runtime inventoryで通常CLIと専用CLIの実ロードを確認した。catalog全97件のうち通常経路の有効95件、専用CLIの有効30件（GSD0件、Project Skill2件、既存disable2件を維持）。AppはGitHubだけがenabled/callableで、実設定を`config/read`の明示cwd付き応答から確認した。

最新runtime snapshotのcode revisionはf746、WordPress起動checkoutの記録SHAは7b42a3d6cc6489ca98b01fbbdc397a78a18862d8で、両者を同一視しない。固定status応答の成功は接続能力の観測であり、local/本番WordPressの全機能・公開・利益検証完了を意味しない。

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
| Required CI / AutoMerge | draft時final job skip、workflow全体success | 実行済みaggregateを確認せずmerge | CI final job＋AutoMerge guard | draft未検証を不合格、run/attempt/current headを照合 |
| 検証入口 / import cache | root/README、make最初のrecipe、直接CLI | 局所検証の案内不足、子process設定より先にcache生成 | README、Makefile、build入口 | 局所/広域検証を明示、呼出側のimportからbytecode書込みを抑制 |

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
  .github/workflows/ci.yml                # 選択検査の実行済みaggregate
  .github/workflows/auto-merge.yml         # 実成功gate・run/attempt/current headの照合
  tests/evals/codex_harness/              # synthetic入力、独立grader、回帰tests
  changes/codex-harness-v1/               # この監査の報告と計測結果
```

Sは対象と関連test、Mはsubsystemと利用側、Lはdata flowと隣接領域、XLはMission・採用判断まで読む。L/XLと曖昧なMで、要求・上位目的・指標・影響域・隣接影響・正本・不可逆作用・非対象を確認する。局所不具合も症状・根因・違反不変条件・隣接影響から最小の完全な修正を選ぶ。

codeはlocal search、architectureはcanonical map、Issue/PR/CIはGitHub、Gitはlocal、現在のAPIは公式docs/web、反復手順はSkill、決定的作業はscript/testへ進む。正本へ到達後は探索を打ち切り、全履歴の読込を通常手順にしない。

SのPython修正は[READMEの局所検証](../../README.md#局所検証)から開始する。live・external・raos_owner_private・database・storageを除外し、DB/Storageは専用partitionへ進む。対象test成功後も利用側・隣接契約を確認し、検証不足・失敗・影響拡大時には関連testとmake fastへ広げる。正本や必要な検証の閲覧を禁止する案内ではない。

PR190で追加された[local guide renderer](../../python/raos/application/editorial/local_reader_guides.py)と[owner](../../scripts/build_local_reader_guides.py)は、既存public projectionおよび本番10記事レジストリとは別の経路である。[current-system](../../docs/architecture/current-system.md)は5ガイド、publication_authority=false、根拠欠損時のblockerを案内する。従来の10記事＋固定policy3ページというlegacy13件の経路とも区別する。[preview guide](../wordpress-local-preview-v1/README.md)のlegacy診断にはhome/search等も含まれ、13を全診断surface数とは扱わない。

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

最新f746 runtime inventoryに記録したWordPress起動先は `/home/minami/rakuten` のまま。検証worktreeとそのcheckoutのcode revisionは別物であり、設定だけでlive状態を推定しない。optionalなaggregate reportとoperation-statusの未公開をserver全体の障害と混同しない。最新f746測定で両MCPの読み取り専用status呼出しはPASS。起動checkoutは7b42のままで、最終同期済みとは扱わない。最終checkout同期・MCP再診断の実績はPR191本文のreceiptで確認する。応答本文や個人情報を保存せず、tool名・応答field名・起動checkoutのSHAをinventoryへ保存する。serverごとの正確なstartup時間はUNKNOWN。catalog取得時間・公開tool数・選択schema量は別の量として記録する。

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
| CI / AutoMerge / policy test | draft時もFinal Integrationを実行し、未検証lockを既存aggregateで拒否。対象run/attemptの実成功gateと現在PR headを確認し、merge時もheadを固定 |
| AGENTS / READMEのnavigation | S局所Python検証と5 marker除外を明示。M以上・境界・生成・共通基盤のmake fastと、失敗時の調査拡大を維持 |
| Makefile / raos_build / bytecode tests | Make recipeの環境と直接CLIのlocal importより前でbytecode書込みを抑制。owner/check子processへの既存伝播を保持 |
| header browser matrix test | 同じ48条件を単一browser内の最大2 contextで実行し、元indexへ結果を格納。実click・scroll安定性確認・全assert・60秒deadlineを維持 |
| main PR190 / local guide owner / architecture map | reader改善を保持し、非本番guide5本のownerと案内を統合。147 owner生成PASS、製品境界・既存guard/harnessの独立review PASS |

Harness/型修正による既存公開境界の保持と、PR190の意図した読者表示・local guide追加を分けて扱う。canonical/upstream/ZIPに差分はない。今回、記事・テーマ・pluginの本番送付、公開提案・適用、staging、deployment、releaseは実施していない。local generatorが出すProduction関連の検査表示は実Production evidenceではない。

根因と修正範囲は分けて記録する。CI事故の観測主因はrequired final jobのskipとworkflow全体successによるmerge判断だった。head固定欠落は別の潜在欠陥であり、本件で異なるheadがmergeされた証拠はない。通知のaction subtype・競合順序はUNKNOWN。privileged AutoMerge workflowへPRコードのcheckout/importやartifact実行を追加していない。

bytecode問題は、make generateの最初のeditorial recipeと直接build CLIのimportが、子process用抑制より先に走る点を修正した。隔離したhelp起動だけで277個のgenerated cache生成を再現し、RED3件→既存owner子process検査を含むGREEN4件を確認した。元の汚染cache277個は隔離先へ保全し、tracked生成物は移動していない。生成receiptはexit0、呼出環境のbytecode指定なしで生成後cache0を記録する。生成receipt単独を全make fastの証拠とはせず、全体の結果は別のreceiptで確認する。

browserは48条件の逐次action待機の累積を最大2 contextへ分散する。独立reviewでcase本体のcheck/interaction維持、順序・全48条件・両workerの失敗伝播を確認した。local負荷下の25.466→19.906秒（21.8%短縮）、重点24件PASSは限定的な証拠であり、hosted CIの遅延原因確定や再発解消の保証ではない。

main190統合は、購買条件・型番・出典日・不確実性・次の確認行動を読み取りやすくする変更を保持する。独立reviewでselection_policy/strategy、7選定要素、料率・価格・楽天取扱有無の重み0、確定利益の式、欠損時UNAVAILABLE、新規本番記事gateを確認した。既存10記事ID/本番slug、33 CTA参照商品、74 CTA束縛の関係を保持する一方、編集に伴うrender/snapshot hashは変わる。旧0dの型修正時に確認した「10記事＋753境界の出力同一」は当時の前後比較であり、PR190統合後の出力不変を主張しない。

local guideは型番別official HTTPS出典・日付・KNOWN evidence・local routeを検証し、不足する比較根拠はblockerとして本文/HTML生成を拒否する。previewの明示定数、loopback origin/port、local環境、home/site URL、既存post所有権・hash/readbackを検証し、他者slugや既存記事への無条件書込み権限にしない。5ガイドは本番10記事やlegacy13件経路と分離し、publication_authority=falseを維持する。

main190-integration-reviewは統合途中の目的・重要境界・既存guard/harness互換性への静的review PASSで、当時未解決だった生成物や全実行結果の承認ではない。その後のowner生成147 PASSは別receiptで確認した。製品/context sourceが変わったため、bfdf Afterをf746の代用にせず全15件を新規評価する。

## 9. Before / After

| Metric | Before | bfdf測定 / f746での適用 | 解釈 |
| --- | ---: | --- | --- |
| root AGENTS lines | 91 | 85 | bfdf→f746でbyte不変。行数だけを合格条件にしない |
| root characters / bytes | 4,906 / 8,962 | 4,057 / 6,811 | UTF-8実ファイル |
| root tokens | 2,342 | 1,830 | o200k_baseで21.9%減。旧0dの1,754/25.1%減は履歴 |
| README lines / characters / bytes | 99 / 4,366 / 7,310 | 128 / 5,139 / 8,511 | 局所検証とCI境界を明確化、f746でも不変 |
| README tokens | 1,858 | 2,212 | 人間向け案内、常時投入ではない |
| docs map tokens | 815 | 1,110 | 正本・適用範囲の案内 |
| architecture map | 初期placeholder | bfdf 211行、f746 214行 | main190のlocal guide経路を追加。f746測定4,192 tokens、bfdfは4,034 |
| worker tokens | 245 | 131 | 15→9行、root規律の複製を縮約 |
| Project Skills | 0 | 2 | metadata161 / 本文1,225 tokens。workflowのみ |
| GSD metadata | 65件 / 1,217 tokens | scoped CLIで無効化 | Global削除なし、総contextとは別 |
| Skill実ロード | 通常CLI有効95件 | 専用CLI30件/GSD0 | 最新f746実測catalog97件、Project2件、既存disable2件を保持 |
| WordPress手順の所有箇所 | AGENTS / README / runbook | runbook | 他は短い境界・入口 |
| 新規nested AGENTS / hooks / plugins | 0 | 0 | 機能の複製を増やさない |
| 外部能力 | 開始時に発見可能320能力 | f746選択43 tool（bfdfと同数）、Apps catalog484 toolはbfdf観測 | 集合が異なり削減率にしない。schema10,472 tokensも総投入量ではない |
| 継承能力の除外 | 個別trueを継承 | 4 App＋API-key MCPをProjectでfalse | Global本体の削除ではない |
| 統合gate | draft時aggregate skip、run全体success | 実成功gate・run/attempt/head照合を実装/review済み | PR189の事前違反と、PR191の現行検証/統合receiptを分離 |

旧root＋GSD metadataの小計3,559 tokensに対し、bfdf/f746のroot＋Project Skill metadataは1,830＋161＝1,991 tokens、差は1,568 tokens。この限定した小計は、共通Skills、path、system/developer指示、会話、動的tool schema、Memoryや課金context全体の削減量ではない。

immutableな同一AGENTSや履歴本文を保存する。品質・成功を文章の語数、固定test総数、局所test一件の成功だけで判定しない。

## 10. Eval Results

現行評価対象は統合コード `f746e0a1c43141e5d6d27e14ec72cb403f841014`。After全15件はCOMPLETED/exit0・品質16・acceptedで、重大な境界違反0、保存comparisonはPASS。Before/Afterのcase構成は各A〜E×3件である。最終A/C/E意味レビューと全30 record/48 artifactの独立cohort監査はPASS。実PR CI、別途local Pyright、local make fast全体はいずれも合格。それぞれの実行環境・件数・receiptを分けて記録する。

[ケース](../../tests/evals/codex_harness/cases.json)と[grader](../../tests/evals/codex_harness/fixtures.py)を固定する。Beforeは `9001a77b38cf82f9467bd461d1177ec8aa299254`、gpt-6-astra / max、isolation v3、B1,200秒・他600秒、各3回。main190統合reviewでharness/fixture/graderの不変とBefore互換性を確認した。モデル設定・budget・完全cohortの一致も比較時に確認し、個別成功の抜取りや過去Afterとの混合をしない。

| Eval | Before品質中央値 | f746品質中央値 | read中央値 Before→f746 | 判定範囲 |
| --- | ---: | ---: | --- | --- |
| A Local | 16 | 16 | 62,101→68,381 chars（＋10.1%） | 品質/境界独立PASS、read削減NOT_DEMONSTRATED |
| B Multi-module | 16 | 16 | 157,328→156,096 chars | 保存品質比較PASS |
| C Architecture | 16 | 16 | 93,384→120,208 chars | 全3件意味/境界review PASS、C1設計名P3を注記 |
| D Side effect | 14 | 16 | 5,662→9,377 chars | 保存品質比較PASS |
| E Business | 14 | 16 | 66,126→44,771 chars | 保存品質比較PASS |

品質proxyの比較PASSは全caseの出力量減少を意味しない。[独立意味・cohort監査](evals/semantic-review.json)を正本に、A/C/E全9成果物の意味レビュー、固定Before再利用、全30 record/48 artifactの整合をPASSと確認した。B/Dはbehavior metadataとcohort整合の確認で、新たな全件手動意味レビューではない。

現行f746 Aの全3件は独立reviewで品質/境界PASS、read-output reduction NOT demonstrated。全patch・保存pytest成功証拠を確認しており、全15件の品質・cohort監査PASSと、効率条件NOT_DEMONSTRATEDを区別する。

| A指標 | 固定Before | f746 A全3件 / 中央値 | 解釈 |
| --- | --- | --- | --- |
| 品質 | 各16 | 各16 | 全cohortの独立意味レビューとは別 |
| 事前定義read文字数 | 中央値62,101 | 87,758 / 58,061 / 68,381、中央値68,381（＋10.1%） | 主指標による出力削減は未実証。bfdf60,376をcurrentに流用しない |
| 保存read_paths件数 | 11 / 9 / 9 | 8 / 8 / 8 | 全3件build internalsなし、局所対象・利用側・test/docs等へ範囲限定 |
| 累積input tokens | 中央値536,509 | 270,010（−49.7%） | cacheを含む補助観測。raw read条件や課金量の代替ではない |
| command数 | 中央値21 | 23（＋9.5%） | 一律の作業量削減は示さない |
| 所要秒数 | 中央値266.9 | 290（＋8.7%） | 一律の高速化は示さない |

保存されたパス集合上では範囲を限定した探索を確認できる。一方、raw readはmixed outcomeを含む事前定義のまま増えている。記録にはcommand本文、read算入flag、閲覧範囲、編集時刻、raw出力がないため、純粋な初期探索量は復元できない。A1/A3には最初の保存pytest成功より前の出力増もあり、検証出力だけの増加として除外できない。記録外の閲覧不存在や、出力量・時間の一様削減を主張しない。探索範囲の観測を既存効率条件の代替指標へ昇格させず、指標・受入条件は変更しない。主指標の増加は事実として残すが、それだけでnavigationの実装欠陥や特定変更との因果が立証されたとはしない。全15件と過去cohortを保持し、case別の成功抜取り・良い値までの再試行は行わない。


現行C全3件はCOMPLETED/exit0・accepted16で、実装はsnapshot→public projection→renderer、updated_public_at/freshness_statusのescape、欠損拒否、内部Evidence/Financeや現在時刻へのfallback拒否を維持する。全Cの独立意味レビューもPASSで、保存pytest成功件数はC1/C2/C3それぞれ41/41/44。独立reviewの**P3: C1 design.txt:29**はOpenAPI schema名の引用誤記で、記載PublicArticleの正名は **PublicArticleDocument**（[契約](../../contracts/raos-v0.4/contracts/openapi-public.v0.1.yaml):546）。参照ファイル・field・nullable解釈・実装は正しく、受入/安全性の失敗ではない。native artifactは原文のまま保持し、このレビュー注記で訂正する。


先行bfdfは全15件品質16、比較とA/C/E・全30 record/48 artifactの独立監査PASSだった。A readは62,101→60,376（2.8%の小改善）だがC/Dは増加し、安定性・因果・一様改善を証明していない。この記録はbfdfに限定し、現行f746の68,381へ置き換えたり選別したりしない。f746の意味レビューは新しい成果物を直接検証して完了しており、先行判定から推定したものではない。

| 履歴cohort | 保持する結果 / 制約 | 保存先 |
| --- | --- | --- |
| 旧0d | 品質中央値A/B/C16、D/E14→16、A read中央値37.7%減。一方A3 read1,056,685 charsも保持 | [after-pre-ci-guard](evals/after-pre-ci-guard.json)、対応comparison/semantic/usageとartifact |
| 757 | 品質15件PASS、全case中央値16。A62,101→74,690（20.3%増）でS効率未実証。原因因果UNKNOWN、検証出力だけを差し引く再採点はしない | [after-pre-navigation](evals/after-pre-navigation.json)、対応comparisonとartifact |
| bfdf | 全15件品質16、比較・A/C/E/全cohort独立review PASS。A read2.8%の小改善、C/D増加 | [after-pre-main-integration](evals/after-pre-main-integration.json)、対応comparison/semantic-review/usageとartifact |
| f746 | 全15件品質16・比較/独立意味/cohort監査PASS。A raw read中央値＋10.1%、削減NOT_DEMONSTRATED | current after.json / comparison.json / usage-summary.json / semantic-review.json |

評価・利用量・比較はsource refを付けた[After](evals/after.json)、[comparison](evals/comparison.json)、[usage](evals/usage-summary.json)に、実装検証は[validation.json](validation.json) v4に対応付ける。currentはf746で、local/CI/Pyrightの実行範囲をそれぞれ保持する。0d、757、bfdfはそれぞれpre-ci-guard、pre-navigation、pre-main-integrationの別cohortとして全件保全する。旧0d validationは[validation-pre-ci-guard.json](validation-pre-ci-guard.json)、bfdf validationも[validation-pre-main-integration.json](validation-pre-main-integration.json)に分離済みである。過去のSHA・artifact・不採用結果をcurrentへ混ぜない。

より古い[Before checkpoint](evals/before-checkpoint.json)のB600秒TIMEOUT、[After checkpoint](evals/after-checkpoint.json)のB/C MODEL_FAILED、[元Before](evals/before-superseded.json)・[元After](evals/after-superseded.json)の隔離/計測不備、[旧Before](evals/before-pre-recovery.json)・[旧After](evals/after-pre-recovery.json)も保持する。Before Bは全3件を1,200秒で揃えており、成功runだけを旧群から残していない。取得不能な失敗原因はUNKNOWNのままにする。

| 検証checkpoint | 確認済み結果 | 適用範囲 |
| --- | --- | --- |
| 旧0d local / CI34023014300 attempt2 | local Python22,433 / 7履歴skip、CI22,432 / 8skip、最新29/29成功 | 初回browser timeoutと同一SHA再実行を保持。型修正時10記事/753境界の出力同一、旧146 owner等も当時の証拠 |
| 757 local | parallel20,056 PASS後、serial1 failure / 54 errors | generated-tree既存pyc277個のST0105不変条件違反。全体FAIL |
| [757 CI34026604628](https://github.com/jamozi/rakuten/actions/runs/34026604628) | 27 success / 2 failure | browser48条件60秒timeoutと実行済みFinal Integration failure。失敗をgateが拒否 |
| bfdf make fast | exit0、Python22,485 / 7履歴skip：parallel20,059、serial1,987、DB348 / 0skip、Storage91 / 0skip。Node486、Vitest4 | bytecode是正後の成功。cache保全と全生成後cache0も別receiptで保持 |
| [bfdf CI34028770234](https://github.com/jamozi/rakuten/actions/runs/34028770234) | 29/29成功、Python22,484 / 8skip（履歴7＋local-only ZIP1）。Node486、Vitest4、PHP7.4 source/generated各85 assertions | 実full workflow_dispatch。browser46.49秒、deadline60秒不変。将来のtimeout不発を保証しない |
| main190統合owner生成 | 147 owner PASS | 独立ソースreviewとは別の生成receipt。f746全検証の代用ではない |
| f746 local make fast | exit0、1,698.2秒。Python22,859 PASS / 7履歴skip：parallel20,431 / 7skip、serial1,989 / 0skip、DB348 / 0skip、Storage91 / 0skip | Node486、Vitest4、PHP8.3.33 source/generated各85 assertions、147 owner checks・mypy628・static・secret/immutable PASS、生成cache0 |
| f746 PR CI34031099874 attempt1 | 実29/29 SUCCESS、Python22,858 PASS / 0failed / 8skip：parallel20,430、serial1,989、DB348、Storage91。Node486、Vitest4、PHP7.4.33 source85＋generated85 assertions | 実行済みFinal Integration/aggregate成功。mypy628 source files、147 owner checks PASS |
| f746 PR CI隔離 / browser | 全20 shardsでbubblewrap0.6.1、隔離skip0。browser48条件41.77秒PASS | 既存60秒deadline維持。CIに独立した全case観測値は出力されず、local観測の再計測とはしない |
| f746 Pyright | 別途明示local npm run pyrightはexit0、0 errors / 0 warnings / 0 informations、26.73秒 | PR CI自体はevent policyによりNOT_EXECUTED。schedule/workflow_dispatchのextended検査と区別 |
| f746 native | 全15件品質16・比較/独立意味/cohort監査PASS。A read削減未実証、C1設計名P3を注記 | 全30 recordはartifact移設以外一致、全48 artifactと中央値整合を確認。記録を編集せず保持 |

local実行は `make fast BASE=4aa7739eaa0c3b8c0c1b471b8f1a190c0c3e1c8f`、source checkpointはf746。pytest自身の所要時間はparallel641.49秒、serial538.13秒、DB350.45秒、Storage25.83秒。wrapperを含むRAOS_CHECKの時間はそれぞれ645.22/543.76/356.09/31.12秒で、全makeの1,698.2秒と測定範囲を区別する。local22,859/7skipとCI22,858/8skipの差はCIのみのlocal-only ZIP skipで、DB/Storage/隔離の欠落ではない。


PR CIの実checkoutはsynthetic merge `d755c29fb6f54080dbe514000cbdf3c07a4b58f7`。base `4aa7739eaa0c3b8c0c1b471b8f1a190c0c3e1c8f` とPR head f746を親に含み、headと同一tree `b017e1105dbce944266105afcef86de2f46db5b7` を確認した。PR headとcheckout commitの違いを隠さず、同一内容への検証として対応付ける。今回の29/29成功はこのcode headへの実PR検証であり、後続report commitのRequired CIやmerge receiptを先取りしない。

CIの8skipは履歴prose7＋local-only ZIP1で、PG/Storage/隔離の未実行を隠していない。実PG18.4の348件PASSはlocal CI runtimeの証拠で、formal TST-008はNOT_EXECUTED。PHPもLOCAL_CI_NOT_WORDPRESS_PRODUCTION。PR CIの空のPyright記録を0 errorsとは読まない。現行0/0/0は別途明示local実行のreceiptによるもので、旧SHAのPASSの流用ではない。


DBの元19失敗、worker UPDATE権限不増、PHP未実行6件の是正、履歴prose7skipと現行activation拒否/zero-actionの対応を保持する。旧0dでのreader型修正の出力同一/Pyright0/mypy627ファイルの記録は歴史的証拠であり、意図的なPR190読者表示変更を無効化したり、現在の出力不変を主張する根拠にはしない。

| Gate incident / correction | 記録 | 意味 |
| --- | --- | --- |
| [PR #189](https://github.com/jamozi/rakuten/pull/189)、[run34025139690](https://github.com/jamozi/rakuten/actions/runs/34025139690) | plan-only 1 success / 9 skips、Final Integrationもskipped | マージ前実行済みRequired CI条件はFAIL |
| [AutoMerge34025218367](https://github.com/jamozi/rakuten/actions/runs/34025218367) | 2026-09-06 09:38:31 UTC、d75d9363a2f88992c8e34577df37afc65272e32dへmerge | 早期merge事故。run全体successを実aggregate成功と同一視 |
| [d75事後CI34025371618](https://github.com/jamozi/rakuten/actions/runs/34025371618) | merge後workflow_dispatch、29/29成功 | d75事後検証。PR189事前違反を遡及充足せず、後続guardの検証にもならない |
| 757 gate是正 | 重点58件、独立guard24＋aggregate3 probe PASS | skipped/missing/failed gate、run/attempt/current head不一致、曖昧metadataを拒否 |
| [PR191](https://github.com/jamozi/rakuten/pull/191) | 観測時non-Draft open、head f746、run34031099874実29/29 SUCCESS | code headへの実gate成功。最終report-head CI・merge/同期の実績はPR191本文のreceiptが正本 |
| AutoMerge workflow342949703 | 監査時disabled_manually、Required CI/branch protectionを維持 | 是正merge後の再有効化実績もPR191本文のreceiptへ記録 |

製品recorded AI回帰、Codex native評価、Git統合手順遵守、WordPress公開/Production承認は別の証拠である。これらをlive business利益やlive WordPress検証完了とは扱わない。

## 11. Remaining Gaps

本報告はf746のsource検証を対象とする。実PR CI29/29、別途local Pyright0/0/0、native全15件品質16・比較PASSを確認した。local make fastもexit0、1,698.2秒、Python22,859 PASS / 7履歴skipで完了した。最終A/C/E意味レビューと全30 record/48 artifactの独立export監査もPASSで、sourceの実装・検証作業は完了した。固定Before15件、f746 After15件と過去cohortを保持し、品質完了と未実証の効率条件を区別する。

**SC-08は部分達成で、Sのraw read削減はNOT_DEMONSTRATED。** 記録上の閲覧先は全3件とも同じ8パスに限定され、build内部を含まないが、事前定義read中央値は10.1%増加した。input-token中央値49.7%減等の補助観測で条件を差し替えない。mixed outcomeから純粋な初期探索量は復元不能で、初期探索・実context削減の保証はUNKNOWN。品質は保持されており、この記録だけで特定の実装欠陥や変更との因果が証明されたとはしない。全件保全と指標固定を維持する。

[PR191本文](https://github.com/jamozi/rakuten/pull/191)の最終receiptがGit統合完了の正本である。そこで最終report commitに対応する実行済みRequired CIのrun/attempt/head、merge SHA、remote/local main・保存済みcheckout・作業worktreeの同期、必要なMCP再診断、AutoMerge再有効化の実結果を確認する。source checkpointの成功とreport-headへの検証を区別し、本報告自身に未来merge hashを埋め込まない。PR189のマージ前条件FAILは後日の成功で上書きせず、既存commitと旧branchの履歴を保持する。

pre-final-delivery-stateは現在Global configが承認済み再構成後のconfigと一致し、一時評価trustが0件であることを記録する。この一致は事故前の未知の原本へのexact restoreではない。Globalは既知項目の再構成で解決する方針をユーザーが承認した。書込み直前の再読込と排他アクセスで同時更新を検出し、書込み前ファイルを`C:/Users/naoki/.codex/recovery/config-before-raos-reconstruction-20260906-160103.toml`へ保全した。model、Skillの既存disable 2件、回収済みfeature/Plugin/App設定を項目単位で戻し、現在のDesktop・通知・Memory・Windows設定を保持した。今回の一時評価のtrust 19件を除去し、実在するRAOSの2 checkoutだけをtrustへ登録した。認証ファイル・Plugin本体・Linux側Global・Global GSDは変更していない。

完全な元ファイルは存在せず、元の`model_reasoning_effort`、`preferred_auth_method`、`personality`、`service_tier`、`shell_environment_policy`は不明なため省略し、Codex既定値を使う。元の通知等もUNKNOWNだが、現在のアプリが保持している設定を優先した。これは合意済みの再構成であり、完全な原状復元を主張しない。個人Memoryの内容、利用頻度、未取得の事業実測値は監査の限界であり、架空の値で埋めない。

DesktopのProject Skill filter制約は上流に残る。RAOS専用CLIを標準経路にする合意済み運用でGSD無効化を実測した。Globalの無効化やinstruction/catalog上限で隠す対処は採用しない。

Globalのexact restore不能、DesktopでのProject Skill filter制約、Skills/Pluginsの利用頻度UNKNOWN、未取得のProduction・利益/CVR/運営時間の実測は、合意した適用範囲・計測限界である。既知再構成と専用CLI運用の完了を否定する修正可能なbugとして扱わず、未知値を補完したりlive検証成功を主張したりしない。

| Success criterion | 証拠 / 判定 |
| --- | --- |
| SC-01 | PASS — Mission・現行V3入口を維持。f746 E全3件品質16・独立意味レビューで上位目的と欠損値保持を確認 |
| SC-02 | PASS — root85行/1,830 tokens、仕様全文を持たない。review済みnavigationを保持 |
| SC-03 | owner主導のdocs map/参照とnavigation review PASS。main190の5guide経路を地図へ追加し静的reviewで確認 |
| SC-04 | PASS — main190重要境界、実PR CI/local全体、A/C/E独立意味レビューで同定・public/Finance・承認・欠損値境界を確認 |
| SC-05 | PASS — runbookが手順、READMEが開発入口、docs mapが採用関係を所有。本番/新5guide/legacy13件を区別 |
| SC-06 | PASS — 最新runtimeでProject Skill2件。metadata161 tokens、反復workflowだけを所有 |
| SC-07 | PASS — f746 catalog97/通常95/専用30/GSD0/Project2/43tool/schema10,472。WP読み取り専用status成功を起動7b42と結び付け、公開権限へ昇格しない |
| SC-08 | PARTIAL — 保存パス上の範囲限定を確認。一方S raw read削減NOT_DEMONSTRATED（中央値＋10.1%）。純粋な初期探索量はUNKNOWN。補助指標で条件を代替しない |
| SC-09 | PASS（P3注記付き）— f746 C全3件品質16・独立設計/実装reviewで目的・正本・隣接影響・非対象・境界を確認。C1 schema名の引用誤記はartifactを保持して訂正注記 |
| SC-10 | PASS（品質/cohort）— 全15件品質16・受入達成・中央値非劣化・重大境界違反0。A/C/E全9成果物と全30 record/48 artifactの独立監査完了。SC-08効率達成を含まない |
| SC-11 | PASS — root2,342→1,830（21.9%減）、限定metadata小計3,559→1,991。総課金contextと区別 |
| SC-12 | 是正sourceの実PR gate29/29 SUCCESS、別途Pyright PASS。PR189の事前CI条件FAILは永久に履歴保持。統合完了はPR191の最終report-head CI/merge・同期・AutoMerge receiptで判定 |

source品質・全体検証・独立意味/cohort監査は完了した。SC-08のraw read削減はNOT_DEMONSTRATEDのままで、全12条件の無条件PASSとはしない。Git統合の最終完了はPR191本文のreceiptで判定し、sourceの成功からmerge・同期・AutoMerge復旧の実績を推測しない。

最終自己レビューでは、「必要なことを必要な時に正確に見つけられるようになった」点はYESと判断する。会話履歴を継承しない代表評価のC/Eで、目的・公開projection・商品同定・正本・収益分離に到達し、独立レビューでも確認できた。Aも対象と利用側に閲覧先を限定した。ただし、これを読取出力量の削減や全ての未知タスクの成功保証とはみなさない。

半年後に事前知識ゼロで開始しても目的を復元できるかについても、設計上はYESと判断する。短いMissionから適用範囲付きの正本と実装へ進み、生成元・参照整合性・公開境界・承認・DB権限の実行可能な検査で確かめられる。稼働能力と承認状態は専用CLIと既存運用入口からその時点で再取得する。将来の外部仕様変更は再確認する必要があり、この判断でSC-08の未実証を上書きしない。
