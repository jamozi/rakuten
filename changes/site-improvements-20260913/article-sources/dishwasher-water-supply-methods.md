# 給水方法の比較：本文候補と取り込みメモ

2026-09-13作成。担当は既存 `/dishwasher-water-supply-methods/`、投稿ID **263**。
到達点は **独立HTMLの本文候補と表示確認**。共有WordPressへの反映・ユーザーレビュー・本番公開は未実施。

## ファイルと確認先

- 完成本文：`article.html`（WordPress HTMLブロック。本文にh1を重複させない）
- タイトル・抜粋・参照元：`metadata.json`
- 独立プレビュー：`preview.html`、確認URL `http://127.0.0.1:41436/preview.html`
- ページ専用のスタイル提案：`page-style-proposal.css`（すべて `.sm-page` またはページ専用class。共有themeは未編集）
- プレビュー外枠：`preview.css`。これはサイトへ取り込まない。
- 写真：`assets/water-lifestyle.webp`。既存の生成イメージをそのまま複製。
- 表示確認：`verification.json`、PC `preview-1440.png`、スマートフォン `preview-390.png`
- 表だけの確認：`comparison-1440.png`、`comparison-390.png`
- 開いた詳細：`pump-detail-1440.png`、`pump-detail-390.png`
- 保持チェック：`content-verification.json`
- `build-draft.py`、`verify-preview.cjs` はこの候補の作成・独立表示確認の補助。正規ownerの代わりにはしない。
- `evidence/` は公式PDFの確認用資料・該当ページ画像。記事画像として配信せず、通常の素材取り込みから除外する。

本ディレクトリの絶対パス：
`/home/minami/rakuten/changes/site-improvements-20260913/page-drafts/supply-methods/`

## 本文の変更と既存記事との関係

先頭を写真、3方式の給水経路、短い比較表へ変更した。本文は次の判断順にしている。

1. タンクは自分で水を入れる。
2. 外部容器からのポンプ給水も、容器への水くみは必要。
3. 分岐水栓は水道から給水する。対応機種・水栓適合・設置条件を確認する。
4. 本体以外に、注ぐ空間・容器・ホース・排水先の置き場を確かめる。
5. 型番別の詳細を必要なところだけ開く。

掲載中4機種の固有条件を保持：NP-TMLK1-K、TDWS25SBL / TDWS25SRD、SS-MA251、NP-TSP1-W。
外部容器給水の説明例として **SS-LH451のみ** を追加。商品順位や包括的な購入推薦は作っていない。
SS-LA451など似た型番へ数値を転用していない。
既存の旧機種資料（DWS-33B(W)、SS-M171、TK-MDW22B、TK-MDW22W）は元の節を保持した。

重複するガイドリンクの箱を型番ごとの短い行に整理した。旧本文の全id、全href、執筆表示、編集者・訂正先、旧機種資料を保持した。
既存本文に広告CTAや独立した広告表示要素はなく、新しい広告リンクは追加していない。WordPressの外枠・台帳側の広告分類や開示は統合時も保持する。
型番詳細内の既存仕様確認日は勝手に更新せず、今回追加確認した事項を2026-09-13として別記した。

通常給水とタンク清掃時の指定クリーナー使用を区別し、専用洗剤・手入れ・維持費への既存リンクを保持した。
旧4機種横断の長い表は先頭から外し、同じ固有条件を型番別詳細内で読めるようにした。

## ページ間の接続

- 本記事は「給水方法で選ぶ」3入口の **違いを知りたい** に対応する。
- `/without-installation/`：既存固定ページID144。「工事なしで選ぶ」の行き先。
- `/dishwasher-branch-faucet-guide/`：新設を別担当が作成中。「工事ありで選ぶ」の予定行き先。IDは未取得、UNKNOWN。
- `/kitchen/`：洗う量の比較と給水方式を選ぶカテゴリへ戻る。
- `/countertop-dishwasher-for-small-households/` と各商品アンカー：掲載4機種の既存比較への詳細接続を維持。市場全体の比較とは呼ばない。

統合担当の指示により、工事あり記事には通常のhrefを本文候補へ用意し、作成中の説明は読者向け本文に追加しない。
独立表示確認時の共有ローカル `http://127.0.0.1:41398/dishwasher-branch-faucet-guide/` は **404**。
これは完成済みリンクではない。新記事の実体と行き先を統合担当が確認して同時反映する。
その他8本の確認対象ローカルURLはHTTP200。HTTP200はユーザーレビュー完了や本番反映の証拠ではない。

## 一次資料と主張の対応

確認日：2026-09-13。以下のURLへ実際にアクセスし、対象箇所を読んだ。
Web抽出でPanasonicのPDFが取得できなかったため、同じ公式URLから読み取り専用で取得し、PDFページ画像を確認した。
ページ数は原則 **印刷ページ**。PanasonicのPDFは見開きのため、PDFのページ番号とは異なる。

| 一次資料 | 読んだ箇所 | 本文へ採用した範囲 |
| --- | --- | --- |
| [Panasonic 食洗機の取り付け方](https://panasonic.jp/dish/attachment.html) | 分岐水栓式とタンク式、蛇口の適合、賃貸条件の注記 | 分岐水栓式の水くみ不要、タンクの都度給水、賃貸契約条件の確認。住居種別だけで可否を断定しない |
| [Panasonic 分岐水栓ガイド](https://panasonic.jp/dish/branch-faucet.html) | 水栓に合う部品を探す入口 | 水栓のメーカー・型番に基づく適合確認への案内。個々の住宅で適合・施工可能とは未判定 |
| [Panasonic 機能比較表](https://panasonic.jp/dish/comparison.html) | 給水方式の行、標準使用水量と注記 | タンクと分岐水栓の両方式に対応する機種があることの補助確認。新しいNP-TSP2の数値をNP-TSP1へ転用しない |
| [シロカ SS-LH451 説明書](https://www.siroca.co.jp/im/ss-lh451.pdf) | p.14、24〜27、33 | 約10Lを給水専用バケツへ準備。付属ホースを固定しスタート後給水。ホース先端は本体設置面より低い位置。給排水に同じバケツを使わない。排水ホースの固定。アース・試運転。分岐水栓用ホースは別売。水圧0.02〜0.80MPa、給湯機接続不可。バケツ給水時約9L／分岐水栓時約8.5Lという使用水量は準備量10Lと区別 |
| [シロカ 大人数向け食器洗い乾燥機](https://www.siroca.co.jp/product/dishwasher_largecapacity/) | 「2wayの給水方式」「自動給水式」 | 給水専用バケツから自動でくみ上げる方式の説明。web抽出のfindでは本文が返らず、公式HTMLの該当段落を読み確認。どこでも設置できるという一般化は採用していない |
| [シロカ SS-MA251 説明書](https://www.siroca.co.jp/im/ss-ma251.pdf) | p.6、12、23〜24 | カップ4〜5杯・約6L、満水の合図、分岐水栓の条件を確認。付属排水ホース1.5mを新規確認し、既存の「付属長未確認」を更新。水圧0.04〜1MPaはSS-MA251固有条件のまま保持 |
| [Panasonic NP-TML1 / NP-TMLK1 説明書](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/379/872/000000000379872/np-tml1.pdf) | 表紙、p.6、8〜10 | 表紙で両型番を確認。タンクを外してFULL線まで給水、使用できない水、排水固定・高さ・指定延長条件を確認。給水量のL換算値を作らない |
| [サンコー ラクアmini color 説明書](https://www.data.thanko.jp/download/manual/tdws25s_man_web_01.pdf) | p.10〜12、15 | 上部給水口、3.2L、付属カップ約2杯、チャイム・給水ランプ消灯、分岐水栓接続不可、排水ホースの高さ・固定を画像で確認 |
| [Panasonic NP-TSP1 説明書](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/370/092/000000000370092/np-tsp1.pdf) | p.16〜21、既存locator p.12・15・22 | 排水ホース固定・20cm以上持ち上げない条件、分岐水栓・水圧0.03〜1MPa・全開時毎分8L以上、方式設定・試運転。追加取得した画像でp.18〜21の設置条件を確認 |
| [Panasonic タンク給水FAQ](https://jpn.faq.panasonic.com/app/answers/detail/a_id/17176) | NP-TSP1の項目 | ドアを閉めて電源を入れ、付属カップで水道水を注ぎ、音3回と給水ランプ消灯で止める。40℃以上のお湯などの禁止。FAQのNP-TML1記述をNP-TMLK1の同定根拠には使っていない |

参考としてシロカの [食洗機選びはじめてガイド](https://www.siroca.co.jp/news/contents_dishwasher_01/) へもアクセスしたが、方式別の主張は上記の説明書・商品ページに直接結び付けた。

## 旧機種の資料は保持、今回の再確認とは分ける

次の旧機種資料は既存本文から保持した。今回、それぞれの説明書全体を読み直したとは報告しない。

- DWS-33B(W)：`https://www.toshiba-lifestyle.com/jp/dish-drye/dws-33b/`（寸法/仕様・脚注1・4）
- SS-M171：`https://www.siroca.co.jp/im/ss-m171.pdf`（p.12、21〜23、29）
- TK-MDW22B：`https://www.data.thanko.jp/download/manual/tk-mdw22b_man_web_01.pdf`（p.9、12、19）
- TK-MDW22W：`https://www.data.thanko.jp/download/manual/tk-mdw22w_man_web_01.pdf`（p.8〜9、12、19、23）

## 写真の来歴

- 使用画像：既存 `home-recent-water-20260913.webp`（900×600px、48,162 bytes）。
- 元の絶対パス：`/home/minami/rakuten/.worktrees/all-pages-20260913/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-recent-water-20260913.webp`
- 来歴：最新worktreeの `changes/site-improvements-20260913/home-recent-images.v1.json` と `home-recent-preview.md` を確認。
- ユーザー指示で組み込みimage_genから生成した、匿名の給水容器と未接続ホースの生活イメージ。実物機種の写真でも適合設置例でもない。
- SHA-256：`7decdb2892a5ea9ac2e488c015060fde18893f578bcf69b56639bed52814c916`
- 画像へ文字・型番は追加していない。新たなメーカー画像は使用していない。
- `article.html` は既存themeの `/wp-content/themes/kurashinoshirube-child/assets/images/home-recent-water-20260913.webp` を参照。独立プレビューだけが手元の複製 `assets/water-lifestyle.webp` を使用する。
- 今回の写真コピーは既存画像とバイト同一。再生成・画像加工をしていない。

## 統合担当向け：SOLOTA設置条件の別記

給水記事の一次資料確認中に見つけた周辺情報。**この候補から共有カタログの設置値を変更していない。**

- 正確な資料URL：`https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/379/872/000000000379872/np-tml1.pdf`
- 表紙の品番：NP-TML1 / NP-TMLK1。版番号 **P9901-20V10**、印字 **S1122-1105**。
- 表紙画像：`evidence/np-tml1-pdfpage-1.png`（PDF第1ページ）
- 該当箇所：印刷 **p.8**「設置場所の確認と準備」。ローカル画像 `evidence/np-tml1-pdfpage-5.png`（PDF第5ページ、印刷p.8〜9の見開き）。
- 画像の絶対パス：`/home/minami/rakuten/changes/site-improvements-20260913/page-drafts/supply-methods/evidence/np-tml1-pdfpage-5.png`
- 設置図には「設置面から49cm以上」「後方0.5cm以上」「側方（左右）0.5cm以上」。
- 別の表「消防法 基準適合 組込形等の離隔距離（cm）」は **上方5／側方0.5／後方0.5**。設置面から49cmという全高条件と、上方5cmの離隔を同一の数値として扱わない。
- ドアが手前へ開く図示はあるが、このp.8には開扉時奥行きの数値がなく、49cmを開扉時寸法へ転用しない。本文の給水量にも無関係。
- 元の共有値が「上・左右未確認」であれば、同一資料・版・対象型番・図と表の条件を照合したうえで、設置担当／統合担当が採用可否を判断する。

## 検証と未確認

- HTML：既存全id保持、id重複なし、旧href欠落なし、本文内アンカー解決、画像alt、scriptなしを確認。
- 旧機種資料の節、執筆表示、編集者・訂正先は元のHTMLと同一。
- ChromiumでPC1440px・スマートフォン390pxを確認。ページ自体の横はみ出しなし、写真読込、h1一つ、5件の型番詳細を開閉、ページエラーなし。
- 比較表はスマートフォンで表の領域だけ横スクロール。PCでは全列が収まる。
- 旧4機種の固有条件を残し、SS-MA251の付属長1.5mだけを今回の一次確認に基づき更新。
- 実機の運用・音・持ち運びやすさ・個別住宅での設置可否は未検証。未確認値を0・適合へ置き換えていない。
- 新規工事ありガイドは現時点404。ID不明。統合時に行き先の作成・実体照合が必要。
- 正規owner生成・WordPressのKSES／snapshot検査・共有テーマでの表示は統合担当側で未実施。独立HTMLの表示確認を、それらのPASSとして扱わない。
- ユーザーレビュー未完了。本番承認なし。本番write・共有ローカルWP/DB更新・Git stage/commit/pushなし。

## 正規ownerへの取り込み

参照元は最新worktree `/home/minami/rakuten/.worktrees/all-pages-20260913`、引き継ぎcommit `42ebf7dfd496d795cf653294abc1539064e6f52f`。
読み取った本文のhashは `metadata.json` にある。今回の独立候補は未commitで、Git保存は統合担当へ集約する。

1. `metadata.json` のタイトル・抜粋を既存ID263の条項に適用する。URL・投稿種別を保持する。
2. `article.html` をページ専用の本文仕様として読み、owner `scripts/build_reader_purchase_support_v1.py` → `python/raos/application/editorial/purchase_support.py::render_guide` と `site_guide_improvements.py` へ統合する。
3. 共通入力は `changes/reader-purchase-support-v1/purchase-support.v1.json`。通常テンプレートだけの差し替えではこのガイドの全文が出ない。`changes/wordpress-direct-publish-v1/articles/` の出力を手編集で維持しない。
4. 新しい比較表・給水経路・SS-LH451の方式例は `water` stage / 対象slugに限定する。共有の機種数・4機種判定を無断で5機種へ変更しない。SS-LH451は方式例であり、元の主比較の商品枠への追加ではない。
5. `.sm-page` のページ専用スタイル提案を必要な範囲でテーマownerへ反映する。プレビュー外枠の `preview.css` は取り込まない。既存画像を再利用し、追加のメーカー画像取得は不要。
6. `guide-water-*`、旧互換アンカー、`product-dish-*`、旧機種資料、型番ガイドへの接続を維持する。比較表に使うSS-MA251排水ホース長の共有値は一次資料p.6と照合して統合側で更新する。
7. 工事なし・工事あり・違いの3記事を共有ローカルで接続し、owner生成、対象本文・リンクと代表PC/スマートフォン表示を確認してユーザーへ返す。

このフォルダの候補作成だけを理由に、ユーザーレビュー済み・本番公開可とはしない。
