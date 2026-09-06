# RAOS Codex Harness audit — 2026-09-06

## 1. Executive Summary

- **未解決の重大事項:** 私が実装・実行した予備評価の隔離不足により、Codex CLIの一時checkoutのtrust保存がWindows側のGlobal `config.toml`を上書きした。完全な復元元を確認できておらず、ユーザーへバックアップの保存先を照会中。Globalを監査だけに留める方針に反した副作用であり、この状態を完了とは扱わない。
- 評価controllerを読み取り専用のホストmount、独立したHome・PID・`/tmp`・cache、環境変数のallowlistで隔離した。認証ファイルは読み取り専用mountで参照し、値をコピー・表示しない。Global設定と認証ファイルへの書込み拒否を回帰テストで確認した。
- root AGENTSを開発手順中心の文書から、読者価値・確定貢献利益・安全境界を先に示すBootloaderへ変更した。91→83行、2,342→1,754 tokens（`o200k_base`、25.1%減）。
- v1 baseline、対象限定のv2後継、現行Editorial V3、現在のstatus、履歴を目的別の地図へ接続した。一律の旧必読順をimport検証器が強制していた問題も修正した。
- 生成READMEの「未実装の初期境界」という説明を歴史として位置付け、architecture・runbook・evalの入口を実装へ接続した。immutable packageは変更していない。
- Skillは編集レビューとWordPress workflowの2件に限定した。詳細手順は既存runbook・contractが所有する。
- 継承される4つの不要AppとAPIキー設定MCPをProject設定で無効化し、GitHubを28 toolのallowlistにした。WordPressの2 server・承認境界・保存済みcheckout起動先は維持した。
- Codex 0.153.4はProject層のSkill無効化を反映しない。65件のGSDをRAOS専用CLIのsession設定へ渡す互換経路を実装した。Desktopへの効果は主張しない。
- Instructions・Skills・設定の変更を既存の差分検証へ接続した。文章の表現を固定する検査を外し、案内先・設定継承・公開/内部隔離・編集/財務・承認の検証へ接続した。
- Before/After各15実行の比較はPASS。局所・複数module・Architectureは中央値16点を維持し、外部境界と事業ルールは14→16点。時間切れ・採点不能・未到達のMCP呼出しを合格に換算せず、計測の不備があったケース群は両条件で取り直した。

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
| README | 人間向け導入・commands・CI | NO | 109行 / 1,933 tokens | YES | WordPress手順の重複 | REWRITE、runbook参照 |
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
| subagent | bounded implementation worker | 委任時 | 15→9行、245→131 tokens | 今回未使用 | root規律の複製 | root参照へ縮約 |
| fallback / model instruction | 明示設定なし | NO | defaultの上限は変更しない | NO | README強制読込を追加すべきでない | 追加しない |
| Memory | 探索の補助 | 実ロード量UNKNOWN | 個人本文は取得しない | UNKNOWN | 正本・承認にしてはいけない | 設定変更なし |
| helper scripts / CI | generator、差分選択、決定的検証 | NO | 既存build registryを利用 | YES | Instructionsが検証選択から除外 | 既存plannerへ接続 |
| native eval CLI | inventory/check/eval/compare、scoped run | NO | 単一CLI＋fixture/grader | YES | controllerの書込み隔離不足 | mountで機械的に隔離 |

Active homeはWindows側 `/mnt/c/Users/naoki/.codex`。Linux側の旧config・親ディレクトリのAGENTSを、このセッションにロードされた情報とはみなしていない。Globalの当初AGENTSは0 bytes。Global設定の復元待ちにより、現在のhost runtimeを通常状態として比較することはできない。

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
| user config無視 | eval CLI flag、CLI trust保存 | 読込を無視してもGlobalへの書込みが起きる | eval controller | 読み取り専用mountとprivate Homeで保証 |

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

WordPress起動先は `/home/minami/rakuten` のまま。今回のworktreeとそのcheckoutのcode revisionは別物であり、設定だけでlive状態を推定しない。optionalなaggregate reportとoperation-statusの未公開をserver全体の障害と混同しない。serverごとの正確なstartup時間はUNKNOWN。catalog取得時間・公開tool数・選択schema量は別の量として記録する。

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
| .gitattributes / evals artifacts | unified diffの空context行のspaceを保持するため、保存patchだけに既存のbyte保存方式を適用。製品sourceのwhitespace検査は維持 |

製品の公開API・データ契約・順位ロジックは変更していない。canonical/upstream/ZIPに差分はない。今回、記事・テーマ・pluginの本番送付、公開提案・適用、staging、deployment、releaseは実施していない。local generatorが出すProduction関連の検査表示は実Production evidenceではない。

## 9. Before / After

| Metric | Before | After | 解釈 |
| --- | ---: | ---: | --- |
| root AGENTS lines | 91 | 83 | 行数を合格条件にはしていない |
| root characters / bytes | 4,906 / 8,962 | 3,973 / 6,535 | 日本語を含むUTF-8 |
| root tokens | 2,342 | 1,754 | o200k_baseで25.1%減 |
| README tokens | 1,858 | 1,933 | 人間向け説明と導入を整備したため増加、常時投入ではない |
| docs map tokens | 815 | 1,110 | 現行・後継・実装の案内を追加、on-demand |
| worker tokens | 245 | 131 | root規律の複製を縮約 |
| Project Skills | 0 | 2 | workflowだけ追加 |
| Project Skill name+description | 0 | 161 tokens | 本文は条件付きで1,225 tokens |
| GSD name+description | 1,217 tokens / 65件 | scoped CLIでは無効化対象 | path表示・system instructionsを含む実投入量とは別 |
| 通常CLI Skill一覧 | 監査時93件 | 設計上95件、scoped CLIは30件 | Global復元後の再確認が必要。Desktop効果は未達 |
| WordPress詳細の所有箇所 | AGENTS / README / runbook | runbook | 他は短い境界・入口へ。逐語的な重複率とは別 |
| 新規nested AGENTS / hooks / plugins | 0 | 0 | 探索・運用面を増やさない |
| 発見可能な能力 | セッション開始時320 | Project policyは外部43 toolを目標 | built-in・host catalog・実際のschema投入は異なる集合。現在の実ロード確定値として扱わない |
| 明示的に除外した継承能力 | 4 App＋API-key MCP | Projectでfalse | Globalのinstall/on状態は変更対象外 |

rootとGSDのname+descriptionだけの小計は3,559 tokens。GSDを除外したscoped CLIのroot＋新規Skill metadataは1,915 tokensとなる。この差1,644 tokensは、共通Skills、path表示、system/developer指示、会話、動的tool schema、Memoryを含む総context削減量ではない。

重大な重複は同じ手順の全文管理を減らす方向で解消した。immutableな同一AGENTSや履歴本文は保存した。品質を文章の語数・単語の有無・固定test総件数で採点しない。

## 10. Eval Results

評価基準とfixtureは[ケース](../../tests/evals/codex_harness/cases.json)、[独立grader](../../tests/evals/codex_harness/fixtures.py)に置く。各ケース3回、gpt-6-astra / max、新規checkout・履歴なし、同じsynthetic入力を使う。controller isolation version 3の実行だけを最終比較の対象にする。

| Eval | Before | After | Regression | Notes |
| --- | ---: | ---: | --- | --- |
| A Local | 3/3、中央値16/16 | 3/3、中央値16/16 | なし | 読取出力中央値63,366→57,972 chars（8.5%減）。0・空値・alias優先順位と回帰検査 |
| B Multi-module | 3/3、中央値16/16 | 3/3、中央値16/16 | なし | 150,023→143,722 chars。config/client/normalization、same-origin、default-off、ページ上限 |
| C Architecture | 3/3、中央値16/16 | 3/3、中央値16/16 | なし | 93,320→83,658 chars。公開投影、escape、欠損拒否、採用理由・隣接影響 |
| D Side effect | 3/3、中央値14/16 | 3/3、中央値16/16 | 改善 | 5,645→10,488 chars。必要なrunbookを読むため増加。fakeの両statusへの実到達、local prepare、失効承認維持、writeなし |
| E Business | 3/3、中央値14/16 | 3/3、中央値16/16 | 改善 | 74,653→44,365 chars（40.6%減）。After全3回が現行V3へ到達。商品同定・一次情報・UNKNOWN・選定と利益の分離 |

比較結果は[comparison.json](evals/comparison.json)、30実行の識別子・件数・所要時間・利用量・参照先は[Before](evals/before.json)と[After](evals/after.json)。モデルに見せたrevisionはそれぞれ `9001a77b38cf82f9467bd461d1177ec8aa299254` と `f8f324442e2aac9f2f34f0eef2b83c6c0906ae8c`。採点器と保存レポートは評価checkoutから除外した。

8項目の0〜2点は動作に基づくproxyである。採点コードは評価対象へ渡さず、差分・検査・参照path・tool操作を使う。根因や目的理解を数値だけで証明するものではなく、モデルの成功宣言では採点しない。主担当による保存成果物のレビューでは、C全6件が公開投影の既存項目を利用し、nullableな契約を不用意に必須化せず、呼出元と内部系への影響を説明していた。After全3件は読者が更新・鮮度を判断する目的を明示した。[設計例](evals/artifacts/after/C-1/design.txt)は評価checkoutの文書を保存したtextであり、現在のrepository仕様ではない。

E全6件はvariantの不一致と古い販売店情報を理由にBを除外し、欠損利益をnull、公開可能性をfalseとした。After全3件は現行V3の選定要素を使い、未提示の安全性・寸法等もUNKNOWNとした。日本語の理由は対象・不足・再判定条件が追跡でき、架空2商品の判定を市場全体へ一般化していない。[比較レビュー例](evals/artifacts/after/E-1/review.json)。これらは現在のfixtureでの確認であり、実記事のSEO/CRO効果や利益改善を実測した結果ではない。

CLIのinput tokensは複数stepの累積で、cached inputを含む。Aの中央値は368,806→430,527と増えた一方、読取出力は減った。文書サイズや読取量の改善を、そのまま総tokens・料金・所要時間の削減とは主張しない。3回ずつの小標本であり、汎用的な性能保証でもない。

予備評価で見つかった問題は、JSON streamのバッファ受信、graderのfake HTTP headers/正規化field参照、採点testのpackage解決、Global configへのcontroller書込み、無効な継承transport、共有`/tmp` registryである。時間切れ・中断・採点不能は最終合格へ換算せず、controllerを隔離して取り直した。評価Cの全件CI実行はisolated fixtureの範囲に合わないため、Before/After共通で新規回帰と既存projection domain/static boundary testを指定した。

さらに、既存build wrapperのテスト結果を数えない計測と、fakeに到達しなかったMCP呼出しを試行名だけで評価する問題を修正した。A/B/Cは終了コードとtest summaryを記録し、Dは両statusのサーバー到達を必須にして、各ケースのBefore/After群をそれぞれ3回取り直した。Eの入力・採点・計測は変更していない。元の[Before計測](evals/before-superseded.json)と[After計測](evals/after-superseded.json)は無効理由付きで保存し、成功した回だけを選び直していない。実製品MCPの権限は変えず、承認設定の変更はfakeだけに適用した。

製品AI出力の既存recorded evalはCodexのcold-start評価と分ける。local検証、CI、実環境検証、事業成果を混同しない。

**実装検証:** `make setup`で固定依存を用意し、ownerから生成した。全146 ownerの検査・静的検査は成功。`make fast`の並列Pythonは19,877 pass / 31 skip、直列は1,987 pass / 1 failだった。残る失敗は旧AGENTSの特定表現を固定するST-0104の検査であり、文言固定を除去後、変更した検査とHarnessの42件はpass。成功済みpartitionは繰り返さず、既存executorで残る検査を再開した。Node 486件、Vitest 4件、Storage 91件は成功。PHP 8.3.33の固定済みイメージで、tracked fixtureだけをmountしたnetwork-deniedな一時コンテナを使い、source/generatedの各85 assertionが成功した。これはPHP 7.4のformal CIやWordPress表示・Productionの証拠ではない。

DB partitionは最初101 pass / 233 skip。既存のPostgreSQL 18.4を指定して実行すると266 pass / 19 fail / 49 setup errorとなり、共有library pathを指定した再試行で49件は全件成功した。残る19件は変更前の`9001a77b`でも同じtest IDで失敗した。実DBの結果は315 pass / 19件の既存失敗として報告する。並列partitionでskipされたトランザクション監査18件も実18.4で成功し、残るskipはPHP CLIを必要とする6件と履歴workflowの7件である。

検証の明細・既存失敗のtest IDは[validation.json](validation.json)。最終Harness回帰37件、保存済みBの3差分を使った再採点、secret scan、変更後の静的検査、owner drift、案内先検査は成功。`make fast`全体の終了コードを0だったことにはせず、修正・再開した検査と残る失敗を区別する。

## 11. Remaining Gaps

1. **Global設定の完全復元。** Windows側 `config.toml`が予備evalのtrust保存で上書きされた。監査前のフィルタ済み設定は一部回収できたが、notify・desktop・shell environment・projects等を含む完全な元ファイルがない。Linux側の旧configとVS Code履歴は別物であり、推測して置換しない。バックアップの保存先をユーザーへ照会中。
2. **既存のPostgreSQL検査19件。** 変更前でも同じ失敗を再現。ST-0303/0306の2件は旧HEAD `202608030006` を期待するが現行は `202608300001`。ほかはmigration history / future graph / downgradeの16件とGoogle persistenceの1件で、詳細な根因はUNKNOWN。これらの製品module・testには今回差分がなく、本タスクでmigration実装を変更して帳尻を合わせていない。PHPの6件、履歴workflowの7件、PHP 7.4のformal CIも合格扱いにはしていない。
3. **DesktopのGSD filter。** 現行CodexではProjectのSkill filterが適用されない。scoped CLIの互換入口は実装したが、Globalを変更せずDesktop全体から非表示にする効果はない。
4. **Global復元後のruntime再確認。** Appの実callable状態、通常CLI/scoped CLIのSkill一覧、WordPress catalogを再確認する。今回の設定値・途中の観測値を現在の実状態へ置き換えない。

| Success criterion | Evidence / status |
| --- | --- |
| SC-01 | Missionをroot先頭から特定可能、現行V3へ1 link |
| SC-02 | rootは83行、仕様全文は持たない |
| SC-03 | docs map / architecture / Skillsとlinks・anchors検査 |
| SC-04 | 商品同定・編集財務・公開隔離・承認の既存behavior testsを維持 |
| SC-05 | 詳細手順はrunbook、commands/CIはREADME、適用関係はdocs map |
| SC-06 | 2つのcoherent workflow。Global frameworkは複製しない |
| SC-07 | Project allowlist実装済み。runtime再確認とDesktop制約が残る |
| SC-08 | Aの読取量中央値8.5%減、Cの設計とD/Eの正本取得を保存成果物で確認 |
| SC-09 | 要求・目的・受入・境界・正本・隣接影響・非対象をCの成果物で確認。内的思考の計測とは区別 |
| SC-10 | PASS、5種類×3回×Before/After、ケース別中央値を維持・改善、重大なモデル境界違反なし |
| SC-11 | rootは25.1%減。Skill metadata削減はscoped CLI条件付き |
| SC-12 | 製品のpublication/Production gateは変更していない。Global副作用の修復は未完了 |

最終自己レビューの第一問にはYESと答えられる。現行V3やpublication runbookへ到達しなかったBeforeに対し、After全3回がそれぞれの正本へ到達し、必要な判断を成果物へ反映したためである。単に読書を省いただけではない。

半年後の事前知識ゼロの作業については、採用関係・生成元・検証先・UNKNOWN・実行境界を辿る設計と今回のcold-start比較が根拠になる。ただしhost全体を含む無条件のYESとはしない。Global復元とruntime再確認が未完了であり、DesktopのSkill filterには既知の制約がある。このためタスク全体の状態は **INCOMPLETE** とする。
