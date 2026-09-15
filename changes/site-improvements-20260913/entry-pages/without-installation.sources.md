# /without-installation/ 本文候補と取り込みメモ

作成・公式資料確認日：2026-09-13。対象は既存固定ページ **ID144 /without-installation/**。表示タイトル案は「工事なしの食洗機」。状態は **候補作成済み・統合前・ユーザーレビュー待ち**。本番公開の承認・実行はない。

## ファイル

- `body.html`：WordPress HTMLブロック形式の独立本文。H1はWordPress側のページタイトルを使う。
- `metadata.proposal.json`：ID・slug・タイトル・抜粋・保持アンカー・同時統合待ちリンク。
- `page-style.proposal.css`：`.ks-no-plumbing` 配下だけに適用するページ専用スタイルの提案。共有テーマは変更していない。
- `assets/`：既存のAI編集画像4枚の同一バイトコピーと `provenance.json`。画像を新規生成・改変していない。
- `preview/preview.html`：共有ローカルWordPressのHTMLを読み取り、独立ブラウザー内で本文・タイトル・CSSだけを差し替えて保存した表示候補。WordPress/DBへの保存はしていない。
- `preview/1440.png` / `preview/390.png`：PC・スマートフォンの全体像。`*-top.png` は冒頭の画面。
- `preview/browser-checks.json` / `preview/content-checks.json`：今回実行した範囲の記録。

すべての絶対パスの基点：`/home/minami/rakuten/changes/site-improvements-20260913/page-drafts/no-plumbing/`

## 役割・比較範囲

食洗機カテゴリの給水方法3入口の「工事なし（タンク式など）」。分岐水栓を使わない **タンク給水と外部容器からのポンプ給水** を、毎回の作業と置き場所で整理するガイド。容量の区分とは別軸であり、掲載例3機種を市場全体の比較・順位・最良候補とは扱わない。

機種例は、着脱タンク・タンク専用のNP-TML1、本体上部給水・分岐併用のSS-MA251、外部容器のポンプ給水・分岐併用のSS-LH451。方式の違いを示す例で、実測の洗浄性能・作業時間・取り回し、現行販売価格・在庫・納期を確認したという主張はしない。未確認の販売条件・排水容器の必要容量は `UNAVAILABLE`。JAN・色別variantを用いた販売商品同定や購入リンクの追加は対象外。

既存の意味を保持した事項：分岐水栓への対応の型番別確認、電源・接地の確認、排水経路と固定方法、本体・扉・給水作業の空間、台の耐荷重と運転時の重量、相談先と採寸値、個人情報を公開投稿しない案内、公式仕様と編集判断の区別、報酬条件によらない評価、既存の比較・方針リンク。

保持した既存アンカー：`first-read` / `purpose-articles` / `next-step` / `site-editorial-policy`。それぞれ実際の節に付与し、空のページ先頭リンクにはしていない。

## 実際に読んだ公式資料

| 資料 | 読んだ位置 | 本文への対応 |
| --- | --- | --- |
| [シロカ「食洗機選びはじめてガイド」](https://www.siroca.co.jp/news/contents_dishwasher_01/#point01) | 「1. 給水方法」「3. 設置スペース」 | 分岐水栓、外部容器の自動給水、タンクの区別。シンク外で排水するときの別容器。水栓適合を確認したうえで賃貸でも検討可能。 |
| [SS-MA251取扱説明書](https://www.siroca.co.jp/im/ss-ma251.pdf) | 印刷p.12「給水する」、p.21〜24「据え付け」 | 上部給水口・トレイ、約6L、カップ4〜5杯、満水ブザー。分岐水栓対応。アース、電源、台、排水固定。 |
| [SS-LH451取扱説明書](https://www.siroca.co.jp/im/ss-lh451.pdf) | 印刷p.14「給水の準備」、p.23〜27「据え付け」 | バケツに用意する約10L、専用容器・付属ホース、給水と排水の別容器、分岐水栓対応。外部給水ホース先端と本体設置面の関係、排水固定・電源・接地。 |
| [Panasonic NP-TML1](https://panasonic.jp/dish/products/NP-TML1/shopping.html) | 商品説明画像の「着脱式のタンク」記載（HTML代替テキストでも確認） | NP-TML1の着脱タンク。販売操作・価格・会員情報・販売状態は参照していない。 |
| [Panasonic公式FAQ：給水ホースの取り付け方](https://jpn.faq.panasonic.com/app/answers/detail/p/1776/a_id/26692) | 「タンク式食洗機の給水ホースについて」 | NP-TML1に給水ホースを取り付けられないこと。FAQ内の他機種のホース長等は転用していない。 |
| [Panasonic「食洗機の取り付け方」](https://panasonic.jp/dish/attachment.html) | 設置スペース、分岐水栓タイプの取り付け、適合確認 | 本体寸法と扉の空間の区別、水栓型番に応じた確認。 |

PDFの `#page=N` は今回の資料では印刷ページ番号と一致する。今回の数字はSS-MA251/SS-LH451の上記説明書だけに適用し、SS-LH351・SS-MH351・SS-M151等へ転用しない。SS-LH451の約10Lは **給水前に用意する水量** であり、排水バケツの最低容量や毎回の実測使用水量ではない。

シロカの旧候補URL `https://www.siroca.co.jp/contents_dishwasher_01/` は取得できなかったため、実在する `/news/contents_dishwasher_01/` を読んで本文に採用した。シリーズ紹介の容量表示は本ページの機種別容量の証拠に使っていない。

## 画像の来歴

メーカー写真・PDF内の図は利用権の確認をしておらず、本文へ複製していない。既存プロジェクトで生成・検視済みのAI編集画像を、同じ概念用途で再利用する。生成物であることを本文で表示し、実機・製品同定・設置図・収納点数の根拠にしない。画像への文字や型番の焼き込みはない。

- 給水容器と未接続ホース：最新worktreeの `changes/site-improvements-20260913/home-recent-images.v1.json` の `theme=water`。原画像の用途は匿名の編集静物、設置主張なし。ファイルSHA-256を来歴記録と照合し、今回も目視した。
- 容量3枚：同 `kitchen-capacity-images.v1.json`。食器量の概念を示す容量別ナビゲーションとして再利用。`CATEGORY_CAPACITY_EDITORIAL_ILLUSTRATION` の用途を維持。
- 実際のコピー元・SHA-256・バイト数は `assets/provenance.json`。本文はすでにテーマに存在する `/wp-content/themes/kurashinoshirube-child/assets/images/` の同じ名前を参照する。重複アップロードや新しい本番メディアIDは不要。

## 正規ownerへの取り込み

参照した最新worktree：`/home/minami/rakuten/.worktrees/all-pages-20260913`。参照時HEAD：`86c3e775c794ccd18e2462483bf5b08e661938df`。対象の旧本文hashは `metadata.proposal.json` に記録。共有コードの未commit変更は新規投稿を公開一覧から除外するものだったため、対象本文の作業競合は確認していない。

正規ownerは `scripts/build_site_editorial_pages.py` → `python/raos/application/editorial/site_editorial_pages.py::render_pages` の `without-installation` 分岐。現行の出力は `changes/wordpress-direct-publish-v1/articles/without-installation.html`。この出力HTMLだけを書き換えると再生成で失われるため、統合担当が上記owner入力へ採用する。

注意：候補 `body.html` はヘッダー・保持アンカー・編集方針を含む **全文**。現行ownerは `PURPOSES` のページに `first-read` / `purpose-articles` / `next-step` を自動付与し、パンくずと `site-editorial-policy` も自動追加する。全文をそのまま既存 `body` 変数に差すだけでは二重ヘッダー・重複IDになる。ページ専用の全文取り込み経路を設けるか、本文・ヘッダー・方針を分割し、既存ラッパーと重複しないよう統合する。`PURPOSES` の旧タイトル・説明文はregistry更新の値も支配しているので、`metadata.proposal.json` の案をそちらにも反映する。

CSSはページ限定の提案であり、共有テーマの正規sourceへの採否・生成・反映は統合担当が行う。候補本文の `.ks-no-plumbing` は維持する。単なる全体 `figure` 指定では既存テーマの480px上限でメイン画像が縮むため、本案ではページのヒーロー写真だけ上限を解除している。

本人は共有registry/catalog/generator/theme/Git index・branch/DBを変更せず、commitを作成していない。書込は指定のページ専用ディレクトリ内だけ。候補はcommit前の絶対パスで渡し、取り込みcommitは統合担当へ集約する。`direct prepare` はcommitとWP側の準備を伴うため、今回の専任分担では実行していない。

## リンク関係と残る確認

- 上位：パンくずの親は `/purposes/`（悩み・目的から探す）。2026-09-16 の KS-029-b2 で、見えるパンくずを構造化データ（functions.php が hub_kind=purpose から出す BreadcrumbList）と同じ親に揃えた。以前は `/kitchen/`（食洗機）を親として表示していた。現在ページ名は台帳 title の「工事なしの食洗機」、nav の aria-label は「パンくずリスト」。`/kitchen/` の #choose から本ページへの入口は変えていない。
- 容量別3記事：`/compact-dishwasher-comparison/`、`/standard-dishwasher-comparison/`、`/large-dishwasher-comparison/`。統合担当から指定されたURLで **同時統合待ち**。このページは人数・食器点数の境界を新たに定義していない。
- 給水方法：既存 `/dishwasher-water-supply-methods/`。新規 `/dishwasher-branch-faucet-guide/` は **同時統合待ち**。
- 既存ID41 `/countertop-dishwasher-for-small-households/` は「タンク式4モデル」と表示し、リンク先のPR・広告を明記。工事なし全体の包括比較として扱わない。
- 既存 `/solota-vs-rakua-mini-plus/` は下位の2機種詳細比較として保持。SOLOTA・ラクアmini colorの4モデル比較とmini Plusを混同しない。
- 既存 `/dishwasher-installation-measurement/` は具体的な採寸先として保持。広告方針・比較方針へのリンクも保持。

実施した検証は候補HTMLの構造、画像来歴のhash、PC1440px/スマートフォン390pxの表示・横はみ出し・画像読込・H1とIDの重複・既存アンカー・出典の開閉。実行結果は `preview/` に保存。記事以外の全体テストは行っていない。

未実施：正規generator経由の再生成、WordPress保存時のKSESとblock検証、統合後の同時作成4リンク先の実在確認、共有WP保存後の表示、ユーザーのレビュー完了、本番反映・本番照合。統合担当が正規ownerから生成し、共有ローカルへ反映後に対象画面とリンクを確認する。今回の静的候補の表示合格を、これらの完了へ置換しない。

## 2026-09-16 追記（KS-113：給水を3経路に分ける）

本文の「タンク式・ポンプ給水」の2分類を、①タンク式（手注ぎ）②タンク式＋別売の給水補助ポンプ③外部容器から本体が吸い上げる、の3経路に分けた。②と③が同じ「ポンプ給水」の語で並ばないよう、kicker・方式の比較表・機種表・`PURPOSES` の説明文（/purposes/ と registry-updates に出る）をそろえた。値は、別担当が公式ページを再取得して照合した記録（2026-09-15〜16）にあるものだけを使い、原文は引用符で示した。

| 資料 | 位置 | 本文への対応 |
| --- | --- | --- |
| [サンコー Q&A ラクアシリーズ用電動給水ポンプ](https://www.thanko.jp/smartphone/page262.html)（2026-09-16 確認） | 最初の Q「対応機種は？」の一覧、「mini plus対応可否の見分け方（給水口を確認してください）」、その後の過去のセット販売品の段落。2番目の Q「給水チャイムが鳴りましたが…」 | 対応機種の6行を原文のまま引用。TK-MDW22W は「使用できません」と過去のセット販売品の記載を並べ、単独で「非対応」と要約しない。ラクアmini Plus は2型番とも「現行販売品のみ」で、給水口の写真で見分ける。満水チャイム後に遅れて止まる動作。 |
| [サンコー ポンプ商品ページ STTDKYSWH](https://www.thanko.jp/view/item/000000004261)（2026-09-16 確認） | 仕様表「注意事項」 | 「ラクアは5L以上、ラクアmini Plus/ラクアmini colorは3.2L以上の水が必要」。型番は書かれていないため、対応可否は Q&A を優先する。 |
| [ポンプ取扱説明書](https://data.thanko.jp/download/manual/sttdkyswh_man_web_01.pdf)（2026-09-15 確認） | PDF p.2 注意事項 | 「ラクア・ラクアmini専用オプション」とあり Q&A と異なる。どちらが新しいかは未確認のため、食い違いがあることだけを書く。 |
| [シロカ 大容量食洗機](https://www.siroca.co.jp/product/dishwasher_largecapacity/)（2026-09-15 確認） | 製品仕様表「給水方式」 | 「自動給水式/分岐水栓式」。本文は「シロカは③を『自動給水式』と呼んでいます」とし、一般的な定義として書かない。 |
| [シロカ 据え付けについて](https://www.siroca.co.jp/support/食器洗い乾燥機：据え付けについて-6267995f924c65001d340936)（2026-09-15 確認） | 給水専用バケツ（SS-LH451/SS-LA451/SS-MH351/SS-MA351用）の2行目 | 組み立てた状態 縦240mm 横300mm 奥行270mm（持ち手含む）。 |
| [SS-LH451 取扱説明書](https://www.siroca.co.jp/im/ss-lh451.pdf)（2026-09-15 確認） | p.14「給水の準備をする」、p.26〜27「バケツで給水する場合」 | 約10Lは給水前に用意する量。既存の p.23〜27 の出典に「p.26〜27 バケツで給水する場合」を添えた。給水ホース先端（p.26）と排水ホース先端（p.25）の分割は、照合記録に該当の記載がないため今回は行っていない。 |
| ラクアmini color 取扱説明書 [tdws25s_man_web_01.pdf](https://www.data.thanko.jp/download/manual/tdws25s_man_web_01.pdf) | p.15（catalog `PRD-THANKO-RAKUA-MINI-COLOR` guide_facts、2026-09-10 確認の既存記載） | 上部の給水口から注ぐ手順と、分岐水栓は接続できないこと。機種表に行を追加。 |

変えていないこと：NP-TML1 の行（出典は NP-TML1 のページと FAQ で、NP-TMLK1-K の値を混ぜない）、必須アンカー、4つの設置確認、画像。41 へのリンク文は、題名変更（「タンク式食洗機4モデルの給水と設置を比較」）に合わせて「タンク式食洗機4モデルの給水と設置を比べる」にした。

未確認のまま：ポンプ使用時に容器を置く場所の条件とホースの長さ、ポンプの型番ごとの価格、ラクアmini color の1回の運転に使う実測水量。
