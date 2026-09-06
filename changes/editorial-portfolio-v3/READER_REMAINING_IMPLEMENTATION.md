# 読者体験の残課題 — 実装・再レビュー報告

2026-09-06。基点は PR #188 マージ後の `5c94bfe463983b26130d7cc1475863a856cf9197`。
[前回実装](READER_IMPLEMENTATION_REPORT.md)と[初回AIレビュー](READER_AI_REVIEW.md)の残件を実装した。
本文・出典・図解・表示条件の編集元を更新し、ローカルWordPressで確認する作業である。

**本番送付・公開、本番下書き更新、provider request、資格情報操作、計測有効化は未実施。**
公開済み10記事のURL、33商品・74 CTAスロット・20 providerスロットの本番契約を変更していない。
Roombaは2製品、30L・3kg以下は5モデルを保持する。ローカル追加ガイドはこの本番契約へ含めない。

## 実装した範囲

| タスクID | 変更と結果 |
| --- | --- |
| AIR-01、DS-001・002、UI-003 | 最大差・見送り条件を候補カードの前へ移動。最初に確認する条件へ実在アンカーを配置 |
| AIR-02、DS-004、DW-007 | タンク・分岐水栓の毎回の作業と、アース端子がない場合の確認先を説明。給水方式を使用水量と別の列で表示 |
| AIR-03、DS-003・005、ART-008 | 9選定記事の37商品掲載箇所で妥協点、向かない条件、購入前確認を分離。根拠のない負担を補わず、負担が未設定の10箇所は除外条件として表示 |
| AIR-04、DS-009、DW-010 | 公式リンク名にメーカー・型番/SKU・確認目的を表示。既存hrefを保持し、offerの代替として公式販売リンクを追加しない |
| AIR-05、DS-007、DW-006・009 | 標準食器点数が自宅の収納量を保証しない注記と、未確認の設置条件を候補選定の近くへ配置 |
| DS-006、RX-003 | 冒頭の公式確認日は解決済み出典の観測日の範囲。記事の編集確認日、出典日、販売状態確認を混同しない |
| DS-011、MIG-010 | ロボット掃除機の本体・充電設備、スーツケースの通常・拡張時の設置面をHTML図に追加。12掲載箇所の図を既存claimに結び付けた。寸法不明の余白は図示しない |
| DW-001・005〜010、HUB-002・003 | 設置、給排水、洗剤、手入れ、費用の5本をローカル専用ガイドとして生成。既存の食洗機2記事やハブから到達し、4候補へ戻れる |
| QA-001、UI-007 | 5幅、200%文字、フォーカス、表、リンク、画像なし、UNKNOWN、CTA非表示を検査。360px拡大時の日本語見出しの横はみ出しを修正 |
| QA-002〜004・006 | 複数モデルの段階レビューをホーム・10記事・追加5ガイドへ実施。実測した人間の理解度とは分け、指摘を実表示・根拠と照合 |
| QA-005 | イベント候補・保存期間・オプトアウト・停止方法を[設計文書](READER_MEASUREMENT_DESIGN.md)に整理。収集処理は実装・有効化していない |

前半5記事はASTと既存Pythonレンダラーから生成した。後半5記事も追跡済みHTMLを入力として保持し、
共通投影で表示する。実機の使用感、価格・在庫、型番をまたいだ仕様を追加していない。

## 公式確認と残る比較ゲート

公開メーカー資料を読み取り、ローカル専用の `local-reader-guides.v1.json` に20出典・60根拠記録を保持した。
出典には型番、URL、確認日、PDFページ等の位置、KNOWN/UNKNOWNを持たせる。
部分的に分かる情報を「比較に必要な全仕様が揃った」と扱わない。

SS-MA251の給水方式は、[当該型番の公式説明書](https://www.siroca.co.jp/im/ss-ma251.pdf) p.12を確認し、
新しい出典 `SRC-SIROCA-SS-MA251-MANUAL-20260906` と商品に限定したclaimを追加した。
PDFの保存内容をSHA-256で結び、閉じた出典許可リストにはこの1件だけを追加した。
旧101出典のURL集合が不変であることも検査する。

食洗機4候補の記事編集確認日はこの確認により2026-09-06となる。SS-MA251の既存販売情報等は旧観測日のままで、
ほかの記事や商品の確認日を一括更新していない。開発用reader ledgerは更新したが、
**別人が確認した本番用ledgerのhashは変更していない**。

SOLOTA `NP-TMLK1-K` は13必須項目中8項目、ラクアmini Plus `TK-MDW22B` は13項目の記録が揃う。
NP-TMLK1-Kの給排水詳細、洗剤の形状・サイズ等、手入れ、販売状態、保証が不足するため、
**新しい比較記事の本文・HTMLは生成していない**。TK-MDW22Bの「再入荷通知」は購入可能の意味ではない。
旧型NP-TML1-Wとラクアmini TK-MDW22Wの情報は転用しない。詳細は[データ欠損一覧](READER_DATA_GAPS.md)。

## ローカル専用ガイドの境界

- 入力と出力を、本番の10記事レジストリ・投稿束縛から分離。`publication_authority=false` 固定。
- 型番に一致する公式出典、日付、KNOWNの本文根拠を満たすものだけを生成する。UNKNOWNは理由・確認方法・判断への影響を表示する。
- 不正な入れ子データ、型番一覧の文字列化、競合する比較根拠、非ローカルURLを拒否する。
- 投稿のslug、既存本文hash、所有メタデータを確認してから専用ローカル環境へ同期する。無関係な同名投稿を上書きしない。
- 既存10記事の保存HTMLを変えず、ローカル表示時だけ完成済みガイドへの文脈リンクを追加する。
- 根拠リンクはJavaScriptなしでも到達可能な末尾の表示領域へつなぐ。未制作リンクとoffer CTAは出力しない。
- ハブ、カテゴリ、目的、更新、検索ではローカル投稿だけを追加し、本番の20行上限・10記事束縛を維持する。

## AIレビューと採否

新しいコンテキストの担当へ、画面→回答保存→全文の順で資料を渡した。
4モデル（gpt-5.6-sol / gpt-5.6-terra / gpt-5.5 / gpt-6-astra）、9ケース。
R01〜05はホームと代表2記事、R06〜07は残る8記事、R08〜09は追加5ガイドを対象とした。
R08は390pxの初心者、R09は1440pxの根拠を慎重に確かめる代理購入者の視点である。

R03は指定と違う幅を先に閲覧し、全文を読んだ後に初見回答を置き換えたため、
**R03のStage 1を初見評価から除外**した。全文レビューのみ参考にした。
5秒・30秒を実際に計測したテストではなく、モデルと人格・幅を同時に変えている。
人間の参加者は0人、正答率・80%達成・CVRは未測定。`reader-comprehension-results.csv` にAI回答は記入していない。

| 指摘 | 対応・根拠 |
| --- | --- |
| 全4機種がタンク式という文章とSS-MA251のUNKNOWNが不一致 | 上記の実在する型番別説明書から給水claimを追加 |
| 最初と最後で設置・食器量の確認順が違う | 設置・扉・排水・アースを先に確認する順へ統一 |
| miniとmini Plusを同じ比較対象と思いやすいリンク | TK-MDW22WとTK-MDW22Bを明記し、別機種の状態確認と分かる文言へ修正 |
| ロボットの必要余白が未知なのに置けると思える | 図は既知の本体・台のみ。復帰・手入れの空間を確認できるまで候補にとどめる条件を表示 |
| BERMASのPC条件、APPLITEの115cm境界を早く知りたい | 対応PCの目安と実寸確認、荷物を入れた状態の採寸を候補の近くへ追加 |
| 設置ガイドの本文と根拠一覧で奥行・高さの順が違う | 対象値を幅・奥行・高さの軸ラベル付きに揃えた。数値自体は変更していない |
| DWS-33Bのタンク容量が一回の給水量・使用水量と混同される | 容量と未確認の一回量を分離し、容量を費用式へ自動投入しない |
| サンコーのタブレット1個量、SS-MA251庫内洗浄の頻度が推測される | 個数・サイズ、頻度・実施の合図は記録上未確認と明示。他機種や月1回へ置換しない |
| 費用ガイドが6機種の金額比較だと期待される | 冒頭でWhを確認できた範囲と、他機種の金額比較を保留することを説明 |
| 自宅料金表のどの単価を使うか迷う | 従量単価と基本・段階料金を分ける。個々の契約・総請求額は本記事の確定対象外として残す |
| 新世代や候補をさらに追加したい | 既存比較対象と編集範囲を保持。記事対象数を増やすだけの提案は採用しない |
| 寿命を充放電回数から説明してほしい | 条件が揃わないため寿命順位を作らない。世代ごとの公表条件整理を次期編集候補として記録 |

独立コードレビューで見つかった根拠パネルへの到達、非ローカル経路、型番の部分一致、
不正な入れ子データ、比較根拠の競合、ガイドから既存記事への戻り先、1文字接頭辞SKUの取り落としも修正した。
当該挙動を回帰テストにし、否定文や未確認説明を使用感の断定と誤検出しない従来ゲートを維持した。

## 検査と表示記録

ブラウザーの最終結果は以下のとおり。通常検査・CIの最終実行結果とskip理由は[統合PR #190](https://github.com/jamozi/rakuten/pull/190)の説明とチェックに記録する。未実施を合格と扱わない。

- 生成: `make generate BASE=origin/main`、81 owner PASS（実装入力を変更したため実行）。
- 修正対象: 175テスト PASS、source-capture 70テスト PASS、WordPress統合の関連9テスト PASS。
- 通常検査: `make fast BASE=origin/main`。最終結果は上記PRに記録する。ローカル専用PostgreSQL等のskipは別記する。
- 最終ブラウザー: **46ページ×5幅、230条件で失敗0件・エラー0件**。通常と200%文字、見出し、内部リンク、表、フォーカス、画像なし、UNKNOWN、CTA非表示を確認。画像原本は `remaining/final-remediated/manifest.json` に結び付く。

ローカルURL:

- [ホーム](http://127.0.0.1:21924/)
- [食洗機4候補](http://127.0.0.1:21924/local-preview-countertop-dishwasher-for-small-households/)
- [SOLOTA状態確認](http://127.0.0.1:21924/local-preview-solota-vs-rakua-mini-plus/)
- [設置測定](http://127.0.0.1:21924/local-preview-dishwasher-installation-measurement/)
- [給水・排水](http://127.0.0.1:21924/local-preview-dishwasher-water-supply-methods/)
- [洗剤](http://127.0.0.1:21924/local-preview-dishwasher-detergent-guide/)
- [手入れ](http://127.0.0.1:21924/local-preview-dishwasher-cleaning-guide/)
- [費用](http://127.0.0.1:21924/local-preview-dishwasher-running-cost/)

成果物の基点は `output/playwright/reader-experience/`。画像・HTML・全文・原回答はGit管理外のローカル保存。

| 保存先 | 対象・意味 |
| --- | --- |
| `before/` | 最初の全面改修より前の基準 |
| `ai-review-2026-09-06/packet/` | 今回のAIR修正前のホーム・代表記事 |
| `remaining/air-verified/` | AIR修正時点の41ページ×5幅、失敗0件 |
| `remaining/review-packet/`、`remaining/final-packet/` | 各AIレビューに実際に渡した時点の画像・本文。後から最終版と呼び替えない |
| `remaining/ai-reviews/r01/`〜`r09/` | 段階回答と全文レビュー。R03の初見は上記理由で除外 |
| `remaining/research/` | 公開公式資料の観測・PDF原本と照合 |
| `remaining/final-verified/` | 修正前最終検査。230条件中、給水ガイド360px・文字200%の横はみ出し1件を記録 |
| `remaining/final-remediated/` | 上記指摘を反映した最終表示・検査。46ページ×5幅、失敗0件 |

表示差は、共通の最大差・見送り条件を先に読めること、型番を識別できる公式リンク、
本体と設備・拡張の差を数値と対応させた図、追加5ガイドへ続く導線である。
承認写真がない箇所は画像・枠を表示せず、白・紺と明朝見出しを保つ。

## 主な変更ファイル

| 責務 | 編集元・検査 |
| --- | --- |
| 共通判断表示・根拠 | `python/raos/application/editorial/reader_components.py`、`reader_experience_projection.py`、`reader_experience_v1.py` |
| 記事データ・AST | `changes/editorial-portfolio-v3/reader-experience.v1.json`、`changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json` |
| 元出典・本文生成 | `scripts/build_st1704_portfolio_source_packets.py`、`raos_editorial_portfolio_v2.py`、`build_st1704_reader_claim_coverage.py` |
| 出典境界 | `scripts/st1704_official_source_capture.py`、`python/raos/application/editorial/self_hosted_editorial_pilot.py`、`python/raos/adapters/self_hosted_editorial_source_capture.py` |
| 新規ガイド | `local-reader-guides.v1.json`、`python/raos/application/editorial/local_reader_guides.py`、`scripts/build_local_reader_guides.py` |
| WordPress | `changes/wordpress-local-preview-v1/mu-plugins/raos-local-preview.php`、`seed.php`、`bin/wordpress_preview.sh`、子テーマ`functions.php`・`assets/editorial-v2.css` |
| ナビ・生成owner | `scripts/build_editorial_portfolio_v3.py`、`build_editorial_v3_theme_navigation.py`、`build_st1704_self_hosted_theme.py` |
| 新規回帰検査 | `tests/wordpress_local_preview/test_reader_remaining.py`、`test_reader_diagrams.py`、`test_local_reader_guides.py`、`test_local_reader_guides_wordpress_integration.py`、PHP harness、`tests/st1704/test_reader_reference_navigation.py` |
| 表示検査 | `changes/wordpress-local-preview-v1/browser/reader_experience_audit.mjs`、既存source・theme・portfolioの契約検査 |
| 生成物 | V3、ナビ、出典registry/locator/開発ledger、10記事fixture、新規5ガイドfixture、theme revision、依存runtime manifest。全てownerから更新 |

measurement、finance、provider名を含む生成差分は依存入力のhashとローカル・synthetic生成物であり、
計測やprovider処理の稼働を表さない。全変更ファイルは統合PRのFiles changedで確認できる。

## 次に着手する条件付きタスク

1. NP-TMLK1-Kの5不足項目を当該型番の公式情報から確認する。揃うまでは既存状態確認記事を維持する。
2. 個々の販売元・構成・保証・現在販売状態が揃った場合だけ、既存公開承認フローへ別の候補を作る。ローカル5ガイドを自動昇格させない。
3. 写真は出典・利用根拠・確認日・承認・alt等が揃った時に導入する。現行の図と画像なし表示は利用可能。
4. 家庭別の料金入力補助、世代別の寿命表記条件はP3編集候補。未確認のWh・寿命・料金を作って埋めない。
5. 実参加者を確保できた場合の検証用紙は保持する。当面は指摘を根拠と照合するAIレビューで改善し、人の成功率を報告しない。
6. 任意計測は設計の保存先・管理者・承認が整うまで無効とする。
