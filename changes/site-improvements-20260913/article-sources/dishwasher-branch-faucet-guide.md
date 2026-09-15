# 分岐水栓式の食洗機：本文候補の根拠と引き継ぎ

確認日：2026-09-13。本文は `article.body.html`、見出し・URL・画像情報は `metadata.json`。

## 範囲

新規候補URL：`/dishwasher-branch-faucet-guide/`。WordPress IDは未取得（UNKNOWN／metadataではnull）。`/kitchen/` の給水方法3入口における「工事あり」。卓上食洗機の分岐水栓方式を選ぶための記事であり、ビルトインリフォーム・DIY施工・市場全体の機種順位は対象外。

蛇口の品番と適合 → 住まいと置き場 → 費用と販売店への相談、の順で構成。工事なしの `/without-installation/`（既存固定ページID144）、方式比較の `/dishwasher-water-supply-methods/`（既存投稿ID263）と相互接続する。容量の包括比較は `/kitchen/` へ戻して選ぶ。既存2機種比較への新たな上位入口は作らない。

## 今回読んだ公式一次情報

| 確認元 | 確認した位置 | 本文で支える内容・扱い |
| --- | --- | --- |
| [パナソニック：食洗機の取り付け方](https://panasonic.jp/dish/attachment.html) | 冒頭の方式説明、「賃貸住宅にもオススメ！」と脚注、分岐水栓タイプ、排水ホース固定、FAQ Q1 | 分岐水栓で自動給水でき、都度注水が省ける。賃貸は契約条件を確認し元の蛇口を保管。排水先の固定は給水と別。指定の別売ホースが必要になる場合がある。個別住宅の設置可を保証する根拠にはしない。 |
| [パナソニック：分岐水栓ガイド](https://panasonic.jp/dish/branch-faucet.html) | 品番検索、入力時の注意、検索結果の注意、品番不明時の案内、各部品の「取付工事費別」表示 | 品番から適合を確認。取り付けできない蛇口や同一品番でも異なる仕様がある。施工は販売店・施工業者へ。パナソニック専用部品検索を他社機の適合証明に流用しない。部品価格の例は本文へ転記しない。 |
| [パナソニック：水栓品番が不明な場合](https://panasonic.jp/dish/branch-faucet/inquiry.html) | 写真相談の説明、末尾の対象外部品・メーカーへの案内 | 品番不明時の写真相談ルート。写真で必ず特定できるとはしない。品番表示が読める場合の写真添付や販売店へ持参する情報の整理は編集上の提案。 |
| [シロカ SS-MA251取扱説明書](https://www.siroca.co.jp/im/ss-ma251.pdf) | 表紙の型番、印刷p.21設置、p.22電源・アース、pp.23–24給排水 | 安定した設置面、扉の可動範囲、余白、機種別の給水圧と給湯接続制限、排水ホース条件。p.22にアース設備不足時の相談・工事費別途。数値や施工手順は本文へ横展開しない。 |
| [シロカ SS-LH451取扱説明書](https://www.siroca.co.jp/im/ss-lh451.pdf) | 表紙の型番、印刷pp.23–25設置・アース・排水、p.26分岐水栓用給水ホース、p.27試運転と注意 | 分岐水栓用給水ホースは別売、分岐水栓は同梱されない。使わないときは分岐水栓を閉じる。試運転時の給排水漏れ確認。SS-MA251とは別の条件を持つ型番として扱う。 |

参考として [パナソニック比較表](https://panasonic.jp/dish/comparison.html) を開いたが、本文抽出では動的比較の全セルを確認できなかったため、特定機種の候補選定や発売・販売状態の根拠には使用していない。指定候補の `contents_dishwasher_01` は今回のURL照合で利用できず、代わりに上記の型番を確認できる公式PDFを読んだ。

本文は公式情報の要約と購入前の確認項目。費用表の配送費、作業範囲、退去時復旧等は「請求される」という断定ではなく、見積もりに含まれるかを確かめる編集上のチェック項目。価格、部品の適合、水圧、住居の許可、具体的な施工費・保証・納期は読者の条件が未確認のためUNKNOWN。実機使用・施工経験や全機種の同一条件比較を示す表現は使わない。

## 2026-09-16 の追記（KS-130）

本文は `articles.v1.json` の `body_source` が指す `changes/wordpress-direct-publish-v1/articles/dishwasher-branch-faucet-guide.html` を直接編集する。`scripts/build_reader_purchase_support_v1.py` の `ARTICLE_OUTPUT_PATHS` にも `scripts/build_site_editorial_pages.py` の `OUTPUT_PATHS` にも含まれず、生成器はない（2026-09-16 に両ファイルで確認）。

- `#branch-check` の手順の後に、適合を「本体側／水栓側／設置条件」の3行に分けた表を追加した。数値は書かず、確認先だけを示す。
  - 本体側：比較表の仕様欄にある給水方式と、型番の説明書。例は既出の [SS-LH451説明書 p.26](https://www.siroca.co.jp/im/ss-lh451.pdf#page=26)（分岐水栓用給水ホースは別売）。550 の比較表には「給水」という列名がなく、給水方式は仕様セル内の表記（例：タンク／分岐水栓）なので「給水欄」とは書かない。
  - 水栓側：既出の [パナソニック「蛇口の品番から分岐水栓を探す」](https://panasonic.jp/dish/branch-faucet.html)。他社機はそのメーカーの案内で確認する（パナソニックの検索を他社機の適合証明に使わない）。
  - 設置条件：水圧・給湯接続・排水・電源とアースは、既出の [SS-MA251説明書 pp.21–24](https://www.siroca.co.jp/im/ss-ma251.pdf#page=21) と [SS-LH451説明書 pp.23–27](https://www.siroca.co.jp/im/ss-lh451.pdf#page=23)。数値は別機種へ流用しない。
- `#branch-consult` の最後の段落の前に、容量別の比較表への導線を追加した：`/standard-dishwasher-comparison/#std-comparison`（「標準容量の比較（掲載機種は16〜28点）」。550 は標準を13〜29点と定義し、掲載機種が16〜28点なので区分の定義と読めない表記にした）と `/large-dishwasher-comparison/#large-compare`（6機種とも公称40点）。
- 型番の列挙とヒーロー画像の差し替えは今回行わない（オーナー判断待ち）。「上記の機種名は条件の例示で、推奨順位を表しません。」の記載は維持する。

## 画像

既存の所有者指示によるAI生成画像を、加工せず再利用する。メーカーの実物画像や汎用の施工写真は新規取得していない。画像上へ文字・型番を追加していない。

- 提供ファイル：`assets/home-recent-water-20260913.webp`（900×600、48,162 bytes）。
- SHA-256：`7decdb2892a5ea9ac2e488c015060fde18893f578bcf69b56639bed52814c916`。
- 読み取り元：`/home/minami/rakuten/.worktrees/all-pages-20260913/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-recent-water-20260913.webp`。
- 来歴：最新worktreeの `changes/site-improvements-20260913/home-recent-images.v1.json` とテーマの `raos-assets.v1.json`。2026-09-13生成、`OWNER_AUTHORIZED_GENERATION_FOR_THIS_SITE`、外部ライセンス依存なし、カテゴリガイド用サムネイル用途の記録あり。
- 本文の画像リンク：`/dishwasher-water-supply-methods/`。altとcaptionで給水容器・未接続ホースのイメージと説明し、実機の部品・適合設置の証拠として扱わない。
- URLは既存テーマの画像パスを利用。画像の来歴登録の更新が必要なら統合担当で判断する。既存画像のコピーを素材として同梱しただけで、共有画像registryは変更していない。

## 正規経路への取り込み

専有書込先は `/home/minami/rakuten/changes/site-improvements-20260913/page-drafts/branch-faucet/` のみ。Git branch/index/commit、共有catalog・registry・generator・台帳・theme、共有WordPress・DBは変更していない。commit/refは統合担当へ集約する指定に従い未作成。

1. 新規記事の通常registryへ、metadataのslug・title・excerpt・関連記事関係を登録する。本文fragmentはH1を含まず、WordPressの通常のタイトル表示を利用する。公開済み記事のID・公開日を流用しない。
2. `article.body.html` を新規ガイドに対応する正規owner入力へ取り込む。既存方式比較は `scripts/build_reader_purchase_support_v1.py` → `purchase_support.py::render_guide` と `site_guide_improvements.py` が本文を構成しており、既存HTMLやtemplateだけの置換では全文変更にならない点を読み取り確認した。新規URLを既存water stageや4機種の候補一覧に偽装しない。
3. `branch-faucet.proposed.css` は新規 `.ks-branch-guide` 配下だけの提案。写真と短い結論の2列、3つの確認手順、横スクロール不要の2列表を整える。統合担当の共有スタイル方針に合わせて取り込む。共有テーマへ直接適用していない。
4. 本文に広告リンク・商品順位・購入ボタンは追加していない。通常wrapperの「この記事にアフィリエイトリンクはありません。」という現行表示を1か所に維持。著者・確認日・出典・運営広告方針も維持する。後に商品広告を追加する際は、その状態に合う表示が必要。
5. owner generatorと新規記事のローカルWordPressプレビューを統合担当で実行する。今回の専用プレビューは共有WordPressを読み取った外枠に候補本文を表示したもの。WordPress保存・KSES・snapshot・公開readbackの合格とは区別する。

## 検証と残る状態

静的確認と関連URLのHTTP応答は `validation.json`、専用プレビューは `preview/index.html`、画面画像は `preview/` へ記録する。確認対象はこのページと関連するリンクに限定した。新しい全体監査や全体テストは実行していない。

最終本文は1,826字（HTMLタグを除いた文字列、出典・閉じた詳細を含む）。静的確認PASS、PC 1440px・スマートフォン390pxのブラウザー確認PASS。ページ全体と2列表に横はみ出しなし、画像1点の読み込みとリンク、費用へのページ内移動を確認。関連するローカルURL5件はすべてHTTP 200。`preview/desktop-1440.png` と `preview/mobile-390.png` が全体画面、`*-top.png` が初期画面。

共有テンプレートのタイトル・概要・著者欄と余白により、写真は初期画面の下に続く。本文内の著者欄の重複は削除済み。初期画面の余白や概要表示を調整する場合は統合担当が共有スタイル方針で判断する。専用プレビューは表示に不要なスクリプトを除いており、共通メニュー等の操作検証には用いない。

WordPress MCPの `raos_codex_site_status` を読み取り実行して接続を確認した。MCP不能を仮定した迂回ではない。委任範囲は候補ファイルだけなので、draft作成・prepare・previewの共有状態への反映・本番writeは実行していない。

ユーザーのページレビューは未完了。本番公開承認なし。技術上の表示確認をユーザーレビュー完了・公開完了へ置き換えない。
