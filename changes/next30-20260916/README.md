# next30 企画の記録 — 2026-09-16（intake 30 本 → 生存 25 本・8 波）

入力パッケージ `tmp/next30/kurashinoshirube_30_articles_20260916`（2026-09-16 作成）に対する、オーナー決定・編集判断・
検証済みの商品カタログ・波計画の記録。**この directory に記事本文はない。** 状態の一次情報は `decisions.v1.json`、
商品は `products.candidate.v1.json`（まだどこにも接続していない候補データ）。

対象は水切りラック・衣類乾燥除湿機・ノンフライヤー（熱風調理器）・軽量コードレス掃除機の 4 分野。
波 0 は**新記事を 1 本も含まない**。新記事より先に、サイトが自分について書いている記述（方針ページの「扱う領域」と
カテゴリの表示名）を実態に合わせる波である。

## 入力パッケージ

| 項目 | 値 |
| --- | --- |
| 置き場所 | `tmp/next30/kurashinoshirube_30_articles_20260916`（66 ファイル・`MANIFEST.sha256` つき。Git 管理外） |
| 中身 | 30 本の編集設計（`article_master.csv` / `articles/A01.md`〜`A30.md` / `article_specs.json` ほか） |
| 種別 | 企画パッケージ。記事本文でも、公開済みサイトの写しでもない |
| 内訳 | 水切りラック 7・衣類乾燥除湿機 9・ノンフライヤー/熱風調理 8・軽量コードレス掃除機 6 |
| パッケージが保証していないこと | 検索量・順位・PV・利益は未測定／公開 20 投稿の全文監査は未実施／新商品の承認済みアフィリエイト offer はゼロ／同梱 JSON は現行 RAOS API のスキーマと未照合 |

パッケージの JSON を現行の契約（台帳・`purchase-support.v1.json`・投影）へ写像し直し、実現性の判定と重複解決を経て
確定したのが本記録である。写像と上限の調査は `next30_map.json`、確定版の編集判断は `next30/plan.md` にある。

## オーナー決定（2026-09-16）

1. **カテゴリの表示名を広げ、カテゴリページの名前もそろえる。** `kitchen` は「食洗機」→「台所」、
   `cleaning` は「ロボット掃除機」→「掃除」。キー（`kitchen` / `cleaning` / `travel` / `preparedness`）は変えず、
   読者が見るラベルだけを変える。既存記事の `listing.category` は 1 件も動かしていない。
   ラベルだけを広げるとカテゴリページが 1 画面で 2 つの名前を名乗る（パンくずは「台所」、見出しと `<title>` と
   JSON-LD は「食洗機の選び方・比較」）ので、ページ名・`excerpt`・ハブ本文の見出しも同じ波でそろえた
   （「台所の道具の選び方・比較」「掃除の道具の選び方・比較」）。掲載中の商品は本文と `excerpt` の中で明示し、
   まだ無い記事は名乗らない。W0-A で反映済み。
2. **「洗濯・乾燥」カテゴリ（`laundry`）を新設する。ただし後の波で。**
   WordPress 側の固定ページは post 701 として**下書きのまま存在し、まだ委譲登録されていない**ので、
   **波 0 はこのページを一切触らない**。publisher は `post_type='post'` 固定でページを作れないため、
   オーナーが wp-admin で公開 → post_id を委譲 → ハブ登録、が済むまで W3（除湿機 8 本）は始められない。
3. **新記事を 1 本も公開する前に、方針ページの「扱う領域」を改訂する。** 4 分野の宣言を 8 分野へ広げ、
   末尾に公開済み記事の一覧（`/categories/`）への案内を添えた。あわせて「根拠の確認手順」を、
   仕様の確認と型番の照合／購入先を案内する商品の販売条件の記録／照合できた販売先がない商品の扱い、の 3 つに分けた。
   新 17 商品は承認済み offer がゼロで、「販売店で販売条件を確認する」という無条件の記述が偽になるため。
4. **波ごとの公開承認は求めない。** 計画の順序で波を進めてよい。ただし公開操作そのもの（prepare → preview → publish）は
   従来どおりオーナーの指示で行い、`approved-layout-baselines.v1.json` の Before/After 了承、本番プロファイルの
   `allow_new_posts` の確認、固定ページ `laundry` の作成と委譲は前提として残る。
5. **4 本を落とす。** A16（連続排水）・A18（置き場所・放熱）・A23（洗い方・食洗機）・A29（充電・収納）。
   これに実現性の判定で落ちた **A06（自動排水の要否）** を加え、30 本 − 5 本 = **生存 25 本**。

## 記事の判定（KEEP / RESHAPE / DROP）

`decisions.v1.json` の `articles[]` が 30 本すべてに判定を持つ。内訳は **KEEP 1 / RESHAPE 24 / DROP 5**。
RESHAPE は「記事を落とす」ではなく「軸の格下げ」で、公式に印字がない軸を比較表から外し、読者が自分で測る手順へ回す。
KEEP は A11（除湿の 3 方式）だけ。

落ちた 5 本と、その問いの行き先:

| ID | 落ちた記事 | 判定元 | 問いの行き先 | どの記事でも判定しないもの |
| --- | --- | --- | --- | --- |
| A06 | 水切りかごの自動排水は必要？ | 実現性 | 排水方式の比較は A02 の比較表、排水先の採寸は A01 の採寸ステップ⑥ | 受け皿の取り出し方向・水はけの張り出し寸法（両商品とも未掲載） |
| A16 | 除湿機の連続排水 | オーナー | CV-U71 の連続排水は A13 が吸収 | F-YEX90D の連続排水の可否（可否そのものが未掲載） |
| A18 | ノンフライヤーの置き場所・放熱 | オーナー | A20 の比較表（放熱余白の行）＋ A17 の確認事項 ＋ A22 の前面開放の説明 | CAF-LI211 の側面余白（未掲載なので左右の適合判定をしない） |
| A23 | ノンフライヤーの洗い方・食洗機 | オーナー | A21（CONFLICT の全文提示とメーカー確認の分岐）＋ A20 の 1 行 | YCW-C120 の食洗機対応（UNKNOWN のまま断定しない） |
| A29 | コードレス掃除機の充電・収納 | オーナー | A25・A27 の確認事項どまり | EC-KR50A・EC-AR50A のスタンド台の寸法（収納の軸は完成しない） |

生存 25 本のカテゴリ内訳は `kitchen`（台所）12 本・`laundry`（洗濯・乾燥）8 本・`cleaning`（掃除）5 本、
役割の内訳は comparison 16 本・guide 9 本。承認済み offer がゼロなので、25 本すべて主 CTA は `internal` で、
メーカー公式への導線はレンダラが自動で出す参照リンク（`official_verify`）だけになる。

## 検証済みの商品カタログ（まだ接続していない）

`products.candidate.v1.json` は 17 商品の検証済みカタログの写し（sha256 `a0551667…2213d`、
コピー元は調査作業の `next30/products.catalog.json`）。リポジトリの検証器
（`python/raos/application/editorial/purchase_support.py`）へ商品配列をそのまま渡した出力:

```
validate_catalog: OK  (products=17, facts=284, guide_facts=29, installation=12)
installation_consistency_mismatches: 0 row(s)
validate_fact_state: OK  states={'CONFLICT': 9, 'KNOWN': 275, 'UNKNOWN': 29}
ALL OK
```

`facts` 284 件の内訳は KNOWN 249 / UNKNOWN 26 / CONFLICT 9、上の `states` は `guide_facts` 29 件を含めた 313 件の集計。
変異を 10 種類仕込む negative control を流し、すべて検出されること（未変異のカタログは合格すること）も確認している。

**このファイルは記録であって、まだ読者に届く経路には入っていない。** 公開カタログ
`changes/reader-purchase-support-v1/purchase-support.v1.json` には 17 商品を 1 件も**取り込んでいません**。
取り込みは W1-A で行い、そのとき 17 商品すべてに `research_issues[]` を 1 件以上付ける
（`PURCHASE_DESTINATION_OR_ISSUE_REQUIRED`）。承認済み offer はゼロなので、参考価格の欄は「価格は確認中」になる。

CONFLICT 9 件（CV-U71 のモード名／CV-U60 の定格除湿能力の試験条件／CV-U60 の除湿自動時の消費電力／
F-YEX90D のケア「衣類」22W の条件／RAO-3 の食洗機／MC-PB61J の 1.3kg の内訳／MC-PB61J の付属品／
EC-AR50A の付属品／AMC-U2 の適合機種）は、どれも片側に決めず、公式 2 か所の印字を並べてメーカー確認へ送る。

## 波計画（8 波・16 候補）

1 候補は proposal 20 件が上限で、テーマが 1 枠を占めるため記事は最大 19 本。新記事は必ず候補 A（新本文）と
候補 B（台帳を published にしてハブを再生成）の 2 回に分かれる。候補 A・B とも必ずテーマ付き。

| 波 | 内容 | 候補 A | 候補 B | 依存 |
| --- | --- | --- | --- | --- |
| W0 | 方針ページの改訂・カテゴリ表示名の拡張・ハブの呼び名そろえ（新記事なし） | 19 ＋テーマ | 3 ＋テーマ（`laundry` の本文・`home`・`categories`） | 候補 B はオーナーの固定ページ作成と委譲 |
| W1 | 水切りラックの中核 3 本 | 3 ＋テーマ | 9 ＋テーマ | W0-A |
| W2 | 水切りラックの残り 3 本 | 3 ＋テーマ | 10 ＋テーマ | W1 |
| W3 | 衣類乾燥除湿機の中核 3 本 | 3 ＋テーマ | 8 ＋テーマ | **W0-B 必須** |
| W4 | 衣類乾燥除湿機の残り 5 本 | 5 ＋テーマ | 8 ＋テーマ | W3 |
| W5 | ノンフライヤーの中核 3 本 | 3 ＋テーマ | 8 ＋テーマ | W0-A・W2-B |
| W6 | ノンフライヤーの残り 3 本 | 3 ＋テーマ | 8 ＋テーマ | W5 |
| W7 | 軽量コードレス掃除機 5 本 | 5 ＋テーマ | 10 ＋テーマ | W0-A |

各波が公開する記事 ID は `decisions.v1.json` の `waves[].articles` にある。落ちた記事はここに 1 件も現れない
（テストで見張っている）。波をまたぐ前方リンクは本文に書けないので、後続波の候補 B で先行記事を編集して再公開する。
公開済み記事を 1 行足したときに自動で再生成されるのは `home` / `categories` / `updates` ＋ 役割に応じて
`comparisons` か `guides` の最大 5 ページで、`kitchen` と手書きの入口 4 ページは明示的に編集したときだけ候補に入る。

## この波（W0）で変わったもの

再生成の結果、公開候補に入る本文は **19 本＋テーマ**（proposal 20 件＝上限ちょうど）。
サイト側の 7 本に、改称した 2 つのハブへ戻るリンクを旧名で名乗っていた記事 12 本が加わる。
9fa8ee45 との差分で document が変わるのは次の行だけ:

| article_key | post_id | 変わったフィールド | 読者に見える変化 |
| --- | --- | --- | --- |
| `about-ad-policy` | 10 | block_markup | 扱う領域を 8 分野に（準備中の 4 分野を明示）、根拠の確認手順を 3 つに分割、参考価格の確認日時を販売条件を記録した商品に限定、改定内容に 2 ページの改称を旧名と新名で記載（そろえたと名乗る面は、この 2 ページへ案内するカード・記事のパンくず・記事から戻るリンクに限定。記事カードを並べるページのうち `/easy-maintenance/` はまだ旧い呼び方なので DF07 に回した）、最終更新日 2026-09-16 |
| `home` | 15 | block_markup | カテゴリカードとリード文の表示名、カードの説明と CTA を商品 1 種類の言い方から外す |
| `categories` | 130 | excerpt・block_markup | リード文・カード見出し・「…の記事 N本」 |
| `cleaning` | 131 | title・excerpt・block_markup | ページ名を「掃除の道具の選び方・比較」に、パンくずの現在地、見出しに掲載中の商品 |
| `comparisons` | 133 | block_markup | カテゴリ別の見出しとジャンプナビ |
| `guides` | 135 | block_markup | カテゴリ別のジャンプナビ |
| `kitchen` | 136 | title・excerpt・block_markup | ページ名を「台所の道具の選び方・比較」に、パンくずの現在地、見出しに掲載中の商品、広告の断りを「広告リンクを含む記事は…」に |
| `compact-robot-vacuum-shortlist` | 30 | block_markup | `/cleaning/` へ戻るリンク 2 本の文言 |
| `countertop-dishwasher-for-small-households` | 41 | block_markup | `/kitchen/` へ戻るリンク 1 本の文言 |
| `roomba-mini-vs-switchbot-k11-pro` | 85 | block_markup | `/cleaning/` へ戻るリンク 2 本の文言 |
| `solota-vs-rakua-mini-plus` | 86 | block_markup | `/kitchen/` へ戻るリンク 2 本の文言 |
| `dishwasher-installation-measurement` | 262 | block_markup | `/kitchen/` へ戻るリンク 2 本の文言 |
| `dishwasher-water-supply-methods` | 263 | block_markup | `/kitchen/` へ戻るリンク 2 本の文言 |
| `dishwasher-detergent-guide` | 264 | block_markup | `/kitchen/` へ戻るリンク 2 本の文言 |
| `dishwasher-cleaning-guide` | 265 | block_markup | `/kitchen/` へ戻るリンク 2 本の文言 |
| `dishwasher-running-cost` | 266 | block_markup | `/kitchen/` へ戻るリンク 2 本の文言 |
| `standard-dishwasher-comparison` | 550 | block_markup | `/kitchen/` へ戻るリンク 1 本の文言 |
| `large-dishwasher-comparison` | 551 | block_markup | `/kitchen/` へ戻るリンク 1 本の文言 |
| `dishwasher-branch-faucet-guide` | 552 | block_markup | `/kitchen/` へのリンク 2 本の文言 |

台帳（`articles.v1.json`）で公開フィールドが変わったのは 5 件:
`categories` の `excerpt`（「スーツケース・食洗機・ロボット掃除機・ポータブル電源から…」→
「スーツケース・台所・掃除・ポータブル電源から…」）と、`kitchen`（136）・`cleaning`（131）の `title` と `excerpt`。
全文は `decisions.v1.json` の `wave_zero_applied.ledger_publish_field_changes` にある。
あわせて `compact-robot-vacuum-shortlist` の `listing.short_title` と、規約で同じ値を保つ
`cleaning` の `reader_role.main_cta.label` を「省スペースの掃除機を比べる」→
「省スペースのロボット掃除機を比べる」に直した（home のカテゴリカードの CTA は代表記事の
short_title を刷るので、「掃除」の見出しの下ではまだ扱っていないスティック掃除機まで含むように
読める。この文字列は生成した home の本文に実際に出る）。`home` の
`reader_role.main_cta.label` は「商品カテゴリーから選ぶ」→「商品カテゴリから選ぶ」で、
こちらの文字列は生成本文に出ない。

台帳で動いた値は合計 8 件（公開フィールド 5・listing 1・reader_role 2）、行数は 5 行。
いずれも既存の公開文書の中の変更で、この 3 件で増える公開候補はない。
記事本文で動いたのは、改称した 2 つのハブへ戻るリンクの文言だけである
（「食洗機の選び方・記事一覧」「食洗機選びの全体像に戻る」「ロボット掃除機の選び方・記事一覧」ほかを、
着地するページの名前「台所の道具の選び方・比較」「掃除の道具の選び方・比較」にそろえた）。
テーマは記事のパンくずと BreadcrumbList をハブの `post_title` から刷るため、本文を直さないと
同じ画面が 1 つの URL を 2 つの名前で呼ぶ。比較表の値・商品データ・記事タイトル・記事の `excerpt` は
1 文字も動いていない。`compact-dishwasher-comparison`（549）は `/kitchen/` へのリンクを持たないので候補に入らない。
テーマは再刻印されるので、W0-A ではテーマの再アップロードが必須になる。

`/dishwasher-branch-faucet-guide/`（552）の記事内ナビは、3 本のリンクが区切りなしで 1 本の文字列として
描画されていた（「台所の道具の選び方・比較蛇口を確認費用を確認」）。552 は purchase-support ランタイムの
23 本に無いので `inc/purchase-support.php` が context なしで return し、`.ps-article .ps-toc` に間隔を持つ
`purchase-support.css` が読み込まれない。読者に届く `theme.css` の `.ks-branch-guide .ps-toc` に、他の記事の
ナビと同じ間隔（`display:flex; gap:.5em 1.2em`）を足した。320・390・1440px の実描画で隣接リンクの間隔は
0px → 19.19px（折り返す場合は縦 8px）になり、他 18 本の最小 14.39px は動いていない。記事本文は触っていないので
公開候補は 19 本のまま。測り方は `tests/purchase_support/test_ks_n30_w0_article_nav_20260916.py` が持つ。

あわせて `home` の見出しと `reader_role.main_cta.label` を「商品カテゴリー」→「商品カテゴリ」にそろえ
（パンくずと両メニューはもともと長音なし）、テーマの検索ヒットの案内文を
「食洗機の比較はこちら」「ロボット掃除機の比較はこちら」→「台所の道具の比較はこちら」
「掃除の道具の比較はこちら」に直した。どちらも公開候補は増えない。

方針ページの「広告を含まない記事は、その旨を記事側で明示する運用にしています。」は、本文ではなく
テーマが守っている: `templates/single.html` の `[kurashinoshirube_article_disclosure]` が、広告リンクを
持たない記事のタイトル直下に「この記事にアフィリエイトリンクはありません。」を刷る（方針ページのこの一文と
同じコミット 47ed499a で入った）。広告リンクを持つ 15 本は本文の `ps-disclosure` を最初の広告リンクより前に
刷り、そのときテーマは自分の一文を出さないので、読者に届く断りは 1 記事につき 1 つである。
本文側にも同じ断りを足す案は採らなかった: 552 はランタイムに無くテーマが本文を検証できないため断りが 2 回出て、
残る 4 本は読者に見える本文変更として `/updates/` のカードが要り、候補が上限を超える。
測り方は `tests/site_editorial_pages/test_ks_n30_w0_advertising_notice_20260916.py` が持つ。

触っていないもの: 既存記事の `listing.category`、記事本文の中身、洗濯・乾燥カテゴリ、
画像の alt（商品種別ではなく画像そのものの説明）、テーマの記事パンくずのハブ label（「キッチン・家事」「掃除・時短」）。

## 公開（2026-09-17）

W0-A は 2026-09-17 に本番へ公開し、匿名（ログインなし）の読み直しで照合した。
状態は `PUBLISHED_AND_READBACK_VERIFIED`。一次情報は `decisions.v1.json` の
`wave_zero_applied.published`。

| 項目 | 値 |
| --- | --- |
| 候補 | W0-A ／ `6a7bc2c6b5f5c8f9e4514067093188326f5688b8b4f4b5702367b70dedd70d8c` |
| commit | `cd8c6eec`（tree `85f19b74`、ブランチ `claude/ks-n30-w0-20260916`） |
| 公開した文書 | 19 本＋テーマ（proposal 20 件＝上限ちょうど）。内訳は上の表と同じ 19 行 |
| 公開時刻 | 2026-09-17T00:35:35Z〜00:37:38Z（JST 09:35:35〜09:37:38） |
| 認可 | オーナーの「公開して」（thread `7b238a17-f16f-4f75-9e66-251570af7781`） |
| 状態 | `PUBLISHED_AND_READBACK_VERIFIED`（publish の戻り値。Git 同期は noop・`ALREADY_COMPLETED_NO_REPUBLISH`） |

公開前のゲートは commit `cd8c6eec` で実行した: pytest は
`3279 passed, 442 subtests passed in 335.93s (0:05:35)`、`make check BASE=origin/main` は
戻り値 0（`RAOS_STATUS_V2 status=PASS`）、preview は `preview PASS failures [] urls 20`
（19 本＋記事一覧の 20 URL を 390px と 1440px で 40 枚撮影）。候補は
`{"candidate_id": "6a7bc2c6…", "publication_ready": true}`。

匿名照合で測った値（形容ではなく実測値をそのまま書く）:

- 更新された文書 (2026-09-17T00:35Z 以降): 19 / 期待 19
- 期待にあって未更新: []
- 期待外で更新: []
- 内部語 0 []／楽天画像ページのクレジット 15/15／免責文リンク 54
- カテゴリページの名前は `/kitchen/` が「台所の道具の選び方・比較」、`/cleaning/` が「掃除の道具の選び方・比較」
- 方針ページは扱う領域を 8 分野で並べ、まだ記事のない 4 分野に「準備中」の断りが付く。改定内容は旧名（「食洗機の選び方・比較」「ロボット掃除機の選び方・比較」）と新名（「台所の道具の選び方・比較」「掃除の道具の選び方・比較」）の両方を書いている
- 旧いハブ名を名乗る記事は 0 本（記事から `/kitchen/`・`/cleaning/` へ張るリンク 21 本はすべて新しいページ名で始まる）
- `/dishwasher-branch-faucet-guide/`（552）の記事内ナビは「台所の道具の選び方・比較蛇口を確認費用を確認」と 1 本につながった状態ではなくなっている

同じ指示で `approved-layout-baselines.v1.json` の 3 本
（`standard-dishwasher-comparison`・`large-dishwasher-comparison`・`compact-robot-vacuum-shortlist`）の
`pending_revision` を `latest_accepted` に移した。了承の範囲は公開した本文そのもので、
`body_sha256` と `snapshot_id` はこのブランチが公開した本文から測っている。W4 の了承は
`previous_accepted` に下がり、`publication_authorized` は 3 本とも false のまま
（公開の認可は波ごとの指示で与えるため）。測り方は
`tests/purchase_support/test_ks_n30_w0_publication_20260917.py` が持つ。

## 先送り（deferrals）

先送りした作業は `decisions.v1.json` の `deferrals` が一次情報で、各項目はそれを**実際に強制する波**を名乗る。
波はテストが `waves[]` から導出して突き合わせるので、記録した波が計画とずれると落ちる
（以前の記録はカテゴリページの拡張を W5 / W7 に送っていたが、台所の棚が増えるのは W1 である）。

| ID | 先送りした作業 | 波 | 強制するもの |
| --- | --- | --- | --- |
| DF01 | `/categories/` と `home` のリードに「洗濯・乾燥」を足す | W0-B | `laundry` の固定ページ公開と委譲 |
| DF02 | `/kitchen/` のハブ本文と `excerpt`、`/categories/`・`home` のカード文を水切りラックまで広げる | W1-B | A01〜A03 が `kitchen` で published になる |
| DF03 | 方針ページの「扱う領域」から準備中の断りを 1 分野ずつ外す | W1-B（以後 W3・W5・W7） | 各分野の最初の公開 |
| DF04 | カード画像が無い記事の alt フォールバックがカテゴリ表示名を差し込む | W1-B | `listing.card_image` が null の新着カード |
| DF06 | `/cleaning/` のハブ本文と `excerpt`、`/categories/`・`home` のカード文を軽量コードレス掃除機まで広げる | W7-B | A25〜A30 が `cleaning` で published になる |
| DF07 | `/easy-maintenance/`（134）の棚見出し「食洗機」「掃除機」を、他の一覧と同じ「台所」「掃除」へそろえる | W1-B | W0-A の候補に枠がなかった（19 ＋テーマ＝上限） |

`later_waves` を持つ先送り（DF02 の W2・W5・W6、DF03 の W3・W5・W7）は、その波の候補に
対象 document の枠が無いと落ちる。枠が無かった 4 候補にこの波で足した:
W6-B に `kitchen`（7→8）、W3-B・W5-B・W7-B に `about-ad-policy`（7→8 / 7→8 / 9→10）。
DF07 の `/easy-maintenance/` も同じ扱いで、W1-B に `easy-maintenance`（8→9）を足した。

記事から `/kitchen/`・`/cleaning/` へ戻るリンクの文言（旧 DF05）は先送りから外した。
旧 DF05 は `compact-dishwasher-comparison` を名指ししていたが、その本文は `/kitchen/` へのリンクを
1 件も持たず、実際に旧名を名乗っていたのは別の 12 本だった。12 本ともこの波（W0-A）で直している。

`changes/wordpress-local-preview-v1/content/home.html` は休眠ツールだけが書く死んだ出力で、古い表示名が残っている。
生成物なので手編集せず、再実行すると現行の生成器が持つ記事本文を上書きするため走らせない。
ツール側の定数（`CAT_NAME` / `HUB_TITLE` / lead）は新しい表示名へ直したので、再実行しても巻き戻らない。

## 未解決

- 固定ページ `laundry` の作成・委譲登録・ハブ登録（オーナー作業。未了なら W0-B と W3 は開始できない）
- 本番プロファイルの `allow_new_posts` の現在値（W1-A の前にオーナー確認が要る）
- `/categories/` のリードが商品種別・場所・行為の混在（スーツケース・台所・掃除・ポータブル電源）。そろえ方はオーナー判断
- カテゴリページのパンくずの区切り記号が 4 ページで不揃い（kitchen は ＞、cleaning は ／、travel・preparedness は /）。kitchen と cleaning は候補内なので揃えても候補は増えないが、どの記号に寄せるかは編集判断。4 ページ揃えるには別の候補が要る
- `/guides/` のジャンプ先 3 つが、カテゴリ名を書いた見出しではなく記事カードに着地する（W0 はラベルだけを改称した）
- 方針ページの改定内容が 1 つの丸括弧に 5 文・435 文字（320px では最長の段落）。読者に見える変更と方針文そのものの改定に分けるかは編集判断（改定履歴の体裁を変えることになる）
- ハブの編集方針の一文が 2 通り（`/kitchen/` の「広告リンクを含む記事は…」と、共通文「記事ごとの広告表示は実際のリンクに基づきます。」を刷る 12 本）。どちらに寄せるかは編集判断
- `tests/purchase_support/test_ks_w4b_round7_20260916.py` の `_batch_shipped` は本文のバイト一致で公開済みを判定するので、W0-A を公開すると W4b の 2 件が再び発火する（`origin/main` は squash merge で祖先関係も使えない）
- AF04 / YCW-C120 のハンドル質量とパンくずトレイの帰属、食洗機対応（いずれも公式に印字がない）
- DH03 / F-YEX90D のケア「衣類」22W の条件と、「※50cm以上（ルーバーを閉じて使うとき）」の方向
- DH01 / CV-U71 の衣類乾燥モード名（取扱説明書・仕様ページ・商品ページで不一致）
- catalog 全 284 facts の再監査（各波の候補 A で、その波が使う fact だけを公式ページで再照合する運用）
- `listing.card_image` は 25 本すべて null（カード画像を出すなら画像と alt のオーナー承認が要る）
