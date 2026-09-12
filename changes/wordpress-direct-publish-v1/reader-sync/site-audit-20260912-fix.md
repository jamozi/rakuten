# 全ページ監査 (2026-09-12) の修正記録と所有者作業

対象: `output/site-audit-20260912/REPORT.md` (指摘 103 件 = P0 6 / P1 45 / P2 52)。
repo 内で直せるものは branch `claude/site-audit-fix-20260912` で修正した (下記「repo 側の修正」)。
サーバー設定・WordPress 管理画面・外部照合が必要なものは、この文書の「所有者作業」に手順を書いた。
公開 (publish) と push / PR は所有者の指示後に行う。

## 公開の手順 (repo 側の修正を live に反映する)

1. `make wordpress-production-request ARGS='direct --owner-checkout /home/minami/rakuten prepare --theme --articles home,travel,kitchen,cleaning,preparedness,categories,small-space,save-housework,without-installation,easy-maintenance,comfortable-travel,prepare-outage,purposes,guides,comparisons,updates,carry-on-suitcase-comparison,carry-on-suitcase-under-100-seats,lightweight-carry-on-suitcase-under-3kg,front-open-carry-on-suitcase-with-stopper,countertop-dishwasher-for-small-households,solota-vs-rakua-mini-plus,dishwasher-installation-measurement,dishwasher-water-supply-methods,dishwasher-detergent-guide,dishwasher-cleaning-guide,dishwasher-running-cost,compact-robot-vacuum-shortlist,roomba-mini-vs-switchbot-k11-pro,portable-power-station-guide,anker-solix-c300-c800-c1000-differences,about-ad-policy,comparison-policy,privacy-policy'`
   で候補を固定する (theme 変更を含むため `--theme` 必須。patch 方式の 6 記事は live 本文の再読込に対して patch が適用できない場合、fail-closed で READY にならない)。
2. `direct preview --candidate <id>` で home / 記事 (390px・1440px) / 一覧の代表画面を確認する。
3. `direct publish --candidate <id>`、その後 `direct sync --candidate <id>`。
4. 公開後の再計測: `output/site-audit-20260912/tools/README.md` の手順 (collect.py → linkcheck.py → browser_audit.mjs → lighthouse_run.sh → build_report.py)。

## 所有者作業 (repo からは変更できない項目)

### T-07 テキスト圧縮 (nginx)

live は `Accept-Encoding: gzip, deflate, br` を送っても `Content-Encoding` が付かない (HTML 133-215 KB、theme.css 97.7 KB を非圧縮配信)。nginx の `http` または `server` ブロックに追加する。

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_comp_level 5;
gzip_types text/html text/css text/plain application/javascript application/json application/xml image/svg+xml application/rss+xml;
# brotli module がある場合
# brotli on; brotli_types text/html text/css application/javascript application/json image/svg+xml;
```

完了条件: `curl -sI -H 'Accept-Encoding: br, gzip' https://kurashinoshirube.com/` に `content-encoding: br` または `gzip` が付き、HTML 転送量が 50 KB 未満。

### T-29 ページキャッシュ (WP Super Cache または nginx fastcgi_cache)

REST に `wp-super-cache/v1` があるので WP Super Cache は導入済みだが、応答に `Cache-Control` / `Age` / `X-Cache` が無く TTFB 0.7-1.24 s。

- WP 管理画面 > 設定 > WP Super Cache: 「キャッシュ機能を利用する (ON)」、配信方法「エキスパート (mod_rewrite)」は nginx では使えないので「シンプル」、「圧縮ページを訪問者に配信」ON、「既知のユーザーにはキャッシュを配信しない」ON、有効期限 3600 秒。
- または nginx で `fastcgi_cache_path` + `fastcgi_cache` を匿名 GET に限定して設定する。
- 注意: theme が `send_headers` で出すセキュリティヘッダ (T-09) は、静的キャッシュファイルを nginx が直接配信する構成では付かない。その構成にする場合は nginx 側でも同じ `add_header` を設定する (下記 T-09)。

完了条件: 匿名 GET の TTFB median 400 ms 未満、`x-cache` 等でキャッシュ HIT を確認。

### T-09 セキュリティヘッダ (nginx 側の二重化)

theme (`functions.php` の `send_headers`) が HSTS / X-Content-Type-Options / Referrer-Policy / X-Frame-Options / Permissions-Policy を出すようにした。キャッシュ配信や静的ファイル (CSS/JS/画像) にも付けるため nginx にも置く。

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), interest-cohort=()" always;
```

CSP は report-only から始める (楽天画像 `hbb.afl.rakuten.co.jp` / `thumbnail.image.rakuten.co.jp`、Google タグ、CookieYes の許可が必要)。

### T-10 バージョン・運用 endpoint の露出

theme 側で `<meta name="generator">` の除去と、匿名の `/wp-json/` index を `wp/v2` と `oembed/1.0` に絞る filter を追加した。残りは nginx で拒否する。

```nginx
location = /readme.html { return 404; }
location = /license.txt { return 404; }
location ~* ^/wp-content/plugins/.+/readme\.txt$ { return 404; }
location = /xmlrpc.php { return 405; }   # 現状 405 で良い
```

`/wp-login.php` は All-In-One Security (AIOS) の「ログインロックダウン」「ログインページ名変更」または nginx の IP 制限 / rate limit を検討する。

### T-03 / CP-07 ユーザー列挙と表示名

theme 側で `/wp-json/wp/v2/users` の匿名アクセス拒否、`?author=N` と author archive の 404 化、oEmbed の author 除去、公開面と feed の著者名固定 (「暮らしのしるべ編集部」) を実装した。加えて WordPress 側で:

- ユーザー > 各ユーザー (codex / kurashishirube / raos_codex_mcp_editor / raos_codex_owner_direct_publisher) の「ブログ上の表示名」を「暮らしのしるべ編集部」にする (ログイン名と別にする)。ニックネームも同じ値にする。
- AIOS > ユーザーセキュリティ > 「ユーザー列挙を防止」を ON。
- 完了条件: 匿名で `/wp-json/wp/v2/users` が 401、`/?author=1` が 404、`/feed/` の `dc:creator` にログイン名が無い。

### T-11 サイトアイコン

theme に `favicon.ico` / `apple-touch-icon.png` / 32px PNG と `<meta name="theme-color">` を追加した。WordPress の「外観 > カスタマイズ > サイト基本情報 > サイトアイコン」に 512×512 PNG (theme の `assets/images/site-icon-512.png`) を登録すると、WordPress 標準の `<link rel="icon">` / `apple-touch-icon` も同じ画像になる (登録前は theme の fallback が出る)。

### T-24 / T-08 CookieYes (cookie-law-info 3.5.5)

- T-24: CookieYes 管理画面 > バナー > レイアウト を「バー (画面下)」にし、モバイルで画面高の 25% 以下に収める。theme 側でも CSS (`max-height:25vh; overflow:auto`) と `scroll-padding-bottom` を当てたが、plugin 設定で小型化するのが本筋。
- T-08: CookieYes Lite はバナーの CSS/JS (約 85 KB) を全ページに inline 出力する。plugin 設定に外部ファイル化のオプションが無い場合は、軽量な同意バナー (WP Consent API 対応) への置換を検討する。T-07 の圧縮を先に入れると転送量への影響は大きく下がる。

### T-18 footer の template part 上書き

live の footer は repo の `parts/footer.html` と一致しない (live: `/about/` 「このメディアについて」など 4 本)。WordPress の「外観 > エディター > テンプレートパーツ > footer」に保存された上書きが存在する可能性が高い。theme の新 footer (hub 5 + 方針 3 + 問い合わせ) を有効にするため、上書きがあれば「リセット (テーマの版に戻す)」を行う。header も同様に確認する。

### T-05 Yoast の固定ページ既定テンプレート

theme が hub 15 ページの head (title「｜暮らしのしるべ」区切り、description、og:type website、JSON-LD) を出すようにしたので必須ではないが、Yoast SEO > 検索での見え方 > コンテンツタイプ > 固定ページ の「SEO タイトル」を `%%title%% ｜ %%sitename%%` に、「メタディスクリプション」を `%%excerpt%%` にしておくと theme 外のページでも区切りが揃う。

### CA-05 / CA-06 販売条件 snapshot の再取得

83 / 30 / 28 の offer (`changes/reader-purchase-support-v1/purchase-support.v1.json` の `valid_until` 2026-09-10/11) はすべて期限切れ。renderer は期限切れ offer の価格を表示せず「再確認中」に切り替えるようにしたが、価格を再掲するには公開販売ページを再照合して `checked_at` / `valid_until` / `price_yen` / `shipping_yen` を更新する (README「価格を更新するときは対象 offer の出典、税込・構成、送料、必須品、確認時刻と期限を一緒に更新する」)。ASP 正規化記録からの取り込みは `scripts/raos_purchase_support.py import-offer`。

### CA-07 BERMAS INTER CITY 60524 の楽天リンク

82 の楽天 CTA と画像は `item.rakuten.co.jp/selection/bermas-60504/` (旧型番 60504) に着地する。patch では外部リンクを差し替えられないため本文の注意書きだけ直した。楽天市場で 60524 (新仕様、USB ポート無し) の商品ページを確認し、`hb.afl` の発行 URL を所有者が差し替える (または楽天 CTA を外し BERMAS 公式通販のみにする)。

### T-02 home の readback

`changes/wordpress-direct-publish-v1/articles/home.html` が公開 source で、live との差は WordPress 保存時の正規化だけだった。KSES が落としていた `scroll-margin-top` は CSS に移した。公開後に `direct status` / readback で本文 sha256 が候補と一致することを確認する。

## 生成・再現の手順

- hub 14 ページと home の HTML は `reader-sync/tools/hub_pages_20260912.py` で生成する (記事名は `articles.v1.json` の title を読む。title を変えたら `python3 changes/wordpress-direct-publish-v1/reader-sync/tools/hub_pages_20260912.py` を再実行し、`--check-only` で id 重複・リンク先・紹介文の重複を検査)。kitchen.html だけは purchase-support renderer の生成物。
- 13 生成記事と policy 3 ページ: `.venv/bin/python scripts/build_reader_purchase_support_v1.py`。
- hub の description: `changes/editorial-portfolio-v3/reader-experience.v1.json` (`navigation.groups`) と `python/raos/application/editorial/reader_experience_v1.py` (`reader_navigation()` の core) → `scripts/build_editorial_portfolio_v3.py` → `scripts/build_editorial_v3_theme_navigation.py`。
- theme の sha256 束縛: `scripts/build_st1704_self_hosted_theme.py --generate` (最後に 1 回)。

## repo 側の修正 (findings.json の key ごと)

### 子テーマ (`changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/`)

- T-01: `kurashinoshirube_reader_hub_page_head` / `kurashinoshirube_reader_hub_url` を fail-open 化 (登録済 slug + publish + 非パスワードで通す。post_content の shortcode 比較を廃止)。navigation-link を削る filter を削除し header / footer の hub 5 リンクを常時出力。パンくず・BreadcrumbList の hub 段は hub page の post_title。
- T-03: `rest_endpoints` で `/wp/v2/users` を匿名 401、`is_author()` を 404 (`?author=N` も 404)、`oembed_response_data` の author 除去。
- T-05: hub を fixed_page として head 生成 (title `｜暮らしのしるべ`、description = post_excerpt が 30-180 字なら採用、無ければ JSON、og:type website、CollectionPage + BreadcrumbList)。
- T-06: article_id → 既存 webp 15 件のマップ (食洗機ガイド 5 本は countertop、86 は solota-rakua、home/hub/policy は home-hero) で og:image / width / height / type / twitter:image / Article.image を出力。
- T-08 / T-09 / T-10 / T-14 / T-15: core block の inline style 分離と上限、`send_headers` のセキュリティヘッダ (HSTS は https 時のみ)、generator 除去と匿名 REST index の `wp/v2`・`oembed/1.0` 限定、大文字 URL の 301 と archive の self canonical、コメント feed link 停止と tagline fallback。
- T-11 / T-13: `scripts/build_st1704_theme_icons.py` (brand-mark.svg → 512px PNG / apple-touch-icon 180px / favicon-32 / favicon.ico、sha256 固定)、`theme-color`、`do_faviconico` で ICO を直接応答。JSON-LD は Organization「暮らしのしるべ」(logo ImageObject、contactPoint)、WebSite の SearchAction、Article.author = `#editorial-team`「暮らしのしるべ編集部」。single.html に公開日/更新日ラベルと「執筆・確認：暮らしのしるべ編集部」。
- T-16 / T-22 / T-27: `the_content` (priority 14) で楽天画像リンクの `<img>` に alt「<商品名> の商品画像（楽天市場）」・width/height・loading=lazy を付与し、240px 版 wrapper を出力から除外 (保存 HTML と原文コードは不変)。CSS で `aspect-ratio:1/1`。
- T-18 / CP-08: footer = hub 5 + 方針 3 + 問い合わせ (mailto)。
- T-21: `[kurashinoshirube_article_disclosure]` を h1 直下 (目次より前) に出力。`hb.afl.rakuten.co.jp` を含む記事だけ広告文、他は「アフィリエイトリンクはありません」。front-page は header 直下。
- T-23 / T-24 / T-25 / T-26 / T-28 / T-29: メタ情報を 0.875rem 以上、Cookie バナーを 390px で 25vh 以内 + focus guard、theme 独自の skip link nav、目次の初期状態を viewport で統一、hub page 解決の request cache + transient 1h、CookieYes script の defer、editorial-v2.css を記事だけに限定、front page の hero を preload。
- CA-23 / CA-24 / CA-28 / CB-16 / CB-17 / CP-05 / CP-07 / CP-14 / CP-15 / CP-18 / CP-19 / CP-20: 挿入リンクの条件文、Rakuten Developers 表記を出典外へ (表示時)、読了時間を本文文字数から算出、post-date のラベル、抜粋を語中で切らない、archive を更新日順、公開面の著者名固定、検索の hub 案内、再検索フォーム、カードの二重リンク解消、404 の hub 導線と h1、唯一の category archive を /updates/ へ 301。
- 関連ガイド末尾に「目的別の入口」(所属 purpose hub) を追加 (T-19)。
- SEO 監査 script (`scripts/raos_wordpress_seo_audit.py`) と test を新しい JSON-LD グラフに更新。

### 統合 (生成チェーンと検証)

- 生成順: `build_reader_purchase_support_v1.py` → `build_editorial_portfolio_v3.py` → `build_editorial_v3_theme_navigation.py` → `build_st1704_theme_icons.py --check` → `build_st1704_self_hosted_theme.py --generate` → `make generate` で収束 (theme revision `6bfe1b1d…`)。
- `make check` PASS、`ruff` / `mypy` / `npm run format:check` / `lint` / `typecheck` PASS、`php -l` (functions.php / inc/*.php) OK、`make final-secrets` OK。
- 旧仕様を固定していた test は新仕様に更新: `tests/wordpress_public_acceptance/test_directories.py` (guides/comparisons の役割分担と注記文)、`tests/purchase_support/*` (画像 18・EXPIRED・JST 表示)、`tests/st1704/*` (fail-open・3 段パンくず・icons)、`tests/wordpress_reader_navigation_v3/*` (hero img 13 枚・CSS の scroll-margin)。

### 生成記事 13 本・policy 3・kitchen (編集元 `changes/reader-purchase-support-v1/`、renderer `python/raos/application/editorial/purchase_support.py`)

- CA-06 / CA-05: renderer が `min(valid_until, checked_at+24h)` を過ぎた offer の価格行を出さず「販売条件の期限切れ・再確認中（確認日／期限）」(`data-ps-price-state="EXPIRED"`) に切り替え、現行価格は「（…まで有効な確認値）」を同じ行に表示。「次回確認」は valid_until 翌日以降を自動算出。Jackery 500 New は公式ストアで通常価格 59,800 円 (2026-09-12 確認) に offer を更新しセール終了を記録。生成は `editorial_updated_on` の JST 終端を基準にして再現可能 (閲覧時の期限判定は theme の purchase-support.js)。
- CB-01 / CA-03: 型番照合済みで注文可能な offer がある候補だけ楽天画像ブロックを投影 (`media_allowed()`)。未照合・売り切れの候補は「商品写真：販売先を照合できるまで未掲載。」。figcaption は「広告リンク：楽天市場（店名）の販売ページへ進みます。構成・送料・保証は未確認。」。画像 binding 30→18。
- CB-02: 結論・比較表の CTA を `#ps-seller-…` 内部リンクに、外部 CTA は商品カードと販売先パネルの 2 箇所 (h1〜比較表間の外部購入リンク 0)。28 は 4 候補すべて照合済みのため文字 8 + 画像 2 サイズ×4 = 16 本 (240px 版は CSS で非表示、可視 12)。
- CB-03 / CB-04 / CB-05 / CB-06 / CB-07 / CB-08 / CB-23: SS-MA251 6L の方針文を 263/266/41 で統一し 266 の根拠を仕様欄 p.29 の記録へ、265 から保証・購入先文を除外、5 ガイド先頭に 4 機種横断表、265 は 4 機種×3 区分 12 セル (未確認は明示)、定型段落の除去と「実機での確認状況」のガイド固有化、逐語再掲の解消、264 に「複数機種で共通の条件」節。
- CB-09 (41 側) / CB-10 / CB-11 / CB-13 / CB-14 / CB-15 / CB-18 / CB-19 / CB-20 / CB-21 / CB-22: THANKO 公式 (36,800 円・保証 24 か月・再入荷通知、2026-09-12 確認) を売り切れ相当 offer として追加、NP-TSP1 に代替導線、SOLOTA の上・左右余白は公式資料に数値が無い旨を 41/262 に明記、作業メモ 8 箇所を削除・読者語化、注意文はカードのみ、結論 h3 直下に決め手 1 行、日付は「2026年9月12日」形式、`～`→`〜`、店名の全角スペース除去、266 の記録を敬体・「型番→Wh→水量→洗剤」順に、264 に試験条件の洗剤量、SS-MA251 は SS-MU251 共通ページの注記 (variant 選択を 2026-09-12 確認)、5 ガイド + 4 比較に「確認・更新履歴」と編集部行。
- CA-11 / CA-12 / CA-16 / CA-18 / CA-21 / CA-22 / CA-24 / CA-25 / CA-26 / CA-27 / T-12 / T-17 / T-20 / T-25: 条件カードに主要値行と行動リンク、byline、開示文の統一 (楽天アフィリエイト・成果報酬を details の外へ)、英語 section-number の除去、83 の旧型番注記を末尾 aside に (C-Lite 134679-1549 は色違いの同一モデルとサムソナイト公式で確認)、Rakuten Developers 表記を商品画像ブロック直後に日本語補足付きで 1 回、30 の結論に Roomba Mini Slim + SlimCharge 導線、APPLITE の文言を読者向けに、title ≤32 字・excerpt 80-120 字、Thanko PDF を `www.data.thanko.jp` に、ガイド nav にラベル・機種別確認先を h4 + ul に。
- CP-01 / CP-02 / CP-03 / CP-04 / CP-09 / CP-10 / CP-11 / CP-12 / CP-13: privacy-policy を実装 (CookieYes + WP Consent API、同意後のみ GA4 (GT-5TWW6GFS / G-7CV8F96487)、拒否時は読込なし、footer から撤回) に全面改稿し、外部送信先の表 (Google / CookieYes / 楽天)、Cookie 名と保存期間 (標準値)、運営者情報の請求対応を記載。about-ad-policy に「編集者について」(領域・確認手順・公開前点検・更新頻度・できないこと)、広告の断定形、画像広告の説明、内部工程文の削除、comparison-policy との役割分担、「根拠の扱い」の h3 分割。
- CH-06 (kitchen): 他 3 category hub と同じ骨格 (入口パンくず、読み方 nav、目的別 hub 導線、PR 表示は 41 のみ、注記、ほかのカテゴリ／編集方針 nav)。
- 未確認のまま (捏造しない): SOLOTA の上・左右余白の数値と保管前手順、mini color の長期不使用手順・洗剤種別・試験条件量、SS-MA251 の試験条件量、APPLITE の現行販売条件 (americantourister.jp は証明書検証失敗)、NP-TSP1 の再入荷、楽天 Panasonic Store 2 品の現在価格 (期限切れ表示)。

### live patch 6 本 (`changes/wordpress-direct-publish-v1/articles/*.patch.json`)

- CA-01: 82/84 は START HERE 節を候補別の一行結論に置換、29/85 は最初の section の前に「先に結論」section (`ks-start-29` / `ks-start-85`、出典付き) を追加。
- CA-03 / CA-20 (29): 冒頭注記を「この記事には広告（商品画像＝楽天市場の販売店へ進むアフィリエイトリンク）が含まれます。…」に。4 商品の注記から「一致する楽天商品を確認できなかった」を除き、画像の遷移先 (ディーショップワン／株式会社ECメゾン／アンカー・ダイレクト楽天市場店) と「型番・構成の照合は行っていない」を明記。
- CA-07 (82): リンク先が旧型番 60504 の商品ページ (商品名は 60524、USB 仕様変更の記載あり) である旨と BERMAS 公式通販の案内を追加。リンク自体の差し替えは所有者作業。
- CA-08 (84): 100 席以上便の枠 (幅40×奥行25×高さ55cm・3辺115cm) の前提と 82 へのリンクを冒頭に。
- CA-09 (19): 近道の「購入前の確認へ」を記事内 `#purchase-checks` に。
- CA-10 / CA-14 / CA-16 / CA-17 / CA-21 / CA-24 / CA-29 / CB-09 / CB-12 / CB-18 / CB-22 / T-12: 同文の短縮、「最終確認日」→「商品仕様の確認日」、確認者行、CTA 直前の「比較表と購入前の確認をご覧ください」、英語ラベルの日本語化 (出典／編集後記／よくある質問 等)、Rakuten Developers の注記、19 の PC 収納は公式仕様 (14.0 インチ、W33×H24×D2.5cm、2026-09-12 確認)、86 に販売先の状況 (SOLOTA→41 の販売先節、mini Plus は THANKO 公式 29,800 円・再入荷通知を 2026-09-12 確認) と TK-MDW22B の 4 ガイドへの直リンク、h2 の句点除去、表 caption に確認日、title ≤32 字・excerpt 80-120 字。
- engine 制約で不可: 82/84/85 の `2026.08.29` 表記の変換 (保護される日付出現数が変わる)、19/29 の結論とカードで同一テキストノードの注意点の片方だけの短縮、外部リンク (楽天 CTA・画像・Rakuten Developers) の移動・削除。
- 6 本とも evidence の live 本文に適用して PatchFailure なし・冪等を確認。保存本文が異なれば prepare は fail-closed で止まる。

### home と hub 14 (`changes/wordpress-direct-publish-v1/articles/`、生成器 `reader-sync/tools/hub_pages_20260912.py`)

- T-02: WP 正規化で消える属性を source から除去、`scroll-margin-top` は home-magazine.css へ、`content/home.html` を `articles/home.html` と同一に (base64 廃止)、`data-release` = `20260912-audit-fix`。
- T-05: hub 15 件の description を 80-120 字に (`reader-experience.v1.json` の groups と `reader_experience_v1.py` の core)。`articles.v1.json` の hub 行に同じ excerpt を追加。
- T-16 / T-19 / T-23 / T-25 / CH-02 / CH-03 / CH-08 / CH-10: home の 12 枚に alt、hero を `<img>` 化、「掲載記事の一覧」で 15 本すべてに直リンク + 1 行紹介 + 更新日、10-11px を全廃 (12px 未満 0)、h1→h2→h3、同一 URL ≤2 で同ラベル、anchor = 遷移先 h1 (対応表 261 リンク)、hero の h1 を `<a>` から出し代表記事 4 本へ直リンク、h2 を日本語に。
- CH-01 / CH-05 / CH-06 / CH-07 / CH-09 / CH-12 / CH-13: purpose hub 6 件を固有本文 715-1209 字 (リード・まず読む 1 本・固有の判断軸・記事ごとの「この記事で決まること」)、guides = 食洗機ガイド 5 本 + 比較記事の条件節への fragment、comparisons = 比較記事 10 本、category hub 4 件を同じ骨格に、紹介文を hub 種別ごとに書き分け (同一文 0)、updates を更新日降順 + 変更点 1 文、広告あり 9 記事に PR 表示と注記の具体化、冒頭 nav をパンくず形式に統一。

