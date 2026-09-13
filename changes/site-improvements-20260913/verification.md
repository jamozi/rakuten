# 全34ページ改善の実装・検証

> 最新候補と食洗機カテゴリの限定変更は [kitchen-preview.md](kitchen-preview.md)。ホームは [home-recent-preview.md](home-recent-preview.md) の完成形を保持。以下の全体確認は以前の候補別記録。

> 最新のホーム構成と公開候補は [home-layout-preview.md](home-layout-preview.md) を参照。以下は前候補の記録。


> 最新のホーム画像変更と公開候補は [home-editorial-verification.md](home-editorial-verification.md) を参照。以下は前候補c69の全体改善・検証の記録。

既存34ページを対象に、比較10記事・31商品の共通化、手順5記事、ホームと入口、方針ページを修正した。公開ID・URLを維持し、新しい記事は追加していない。元監査の136項目は `progress-evidence.v1.json` と別の進捗Excelで追跡する。

## 確認する候補

- 候補: `c69bb4c4a1d258b3895e8b97d417a95f0ec6fea9ab86abbdd864cfe2ec6162f3`
- Source: `c64affdf5608f5edbe37f8732188106040e2cb1effc8d9f83a8c8f8f75c64475`
- Runtime: `77f606fb0dc097e929c50f4d3cb763c6a44b7c3a2f6a98197bfefc79e6fa6c22`
- ローカル: http://127.0.0.1:41398/
- `owner-direct-v1` の prepare は publication_ready=true。preview は34ページと投稿一覧、390/1440pxでPASS。これは本番公開ではない。
- ホームの文字量を減らし、リンク付き商品画像6枚を実WordPressで確認した。320/375/390/768/1440px、文字200%、JavaScript無効、全6画像のキーボードフォーカスとMiniの記事内移動はPASS。
- 共通改善の `make fast BASE=63d00765` は全選択段階PASS。最新の狭いID対応修正は `make fast BASE=2b332824` でPASS。ホーム追加全体を含む `make fast BASE=2184e576` も全選択段階PASS。

## 変更の要点

- 画像挿入経路と販売先を型番に結び付け、BERMAS60524・Ankerの同一性と利用根拠が未確認の画像を非掲載にした。比較本文と確認済みリンクは残した。
- 差分編集だった6比較を通常の本文と共通カタログに移行。主比較2/3/4機種と補足構成を分離し、表・販売条件・出典・未確認理由を同じ商品データから表示する。
- 数値販売価格は静的本文に表示せず、確認後24時間と提供元期限の短い方までJavaScriptで補助表示する。期限切れ、再訪、タブ復帰時は消す。費目が欠ける場合は総額・予算内を確定しない。
- 5ガイドに冒頭の答え、機種別表、採寸・給排水の説明図、洗剤と禁止材質、具体的な清掃手順、入力不要の計算例を追加。現行4機種と旧機種の根拠・アンカーを分離して維持する。
- ホームは主特集41、補助83/30、4カテゴリ、生活上の困りごと、実質更新6本、編集方針へ整理。追加のユーザー指示に従い、カードの広告有無・比較製品数・内容更新日・長い説明を削除した。件数と更新順の根拠は台帳に保持する。
- 主特集と補助特集に、型番と利用根拠を確認した6商品のリンク付き画像を配置。楽天5商品は元の240px生成HTMLを保持し、Miniは公式素材の全体・比率・正式名・出典を保持する。広告案内は冒頭1か所に短く表示する。取得できない商品画像や未承認のリンクを推測で補わない。
- 入口の残る4項目を追加。kitchen冒頭に購入前/購入後を置き、機種別の販売確認記録を共通カタログから表示する。preparednessには用途・時間・同時使用の3記入欄、travelには4比較表への直リンクを置いた。現在の市場在庫は断定しない。
- CookieYesの設定を開くフッター導線とモバイル設定画面を修正。文字だけを200%にした際の長いメールアドレスの横はみ出しも折り返しで修正した。

## 検証の証拠と範囲

`output/site-improvements-20260913/owner-direct-preview-home-idfix.json` が最終候補の35URL preview結果。実画像・リンク・5幅・拡大・noJS・キーボードは `home-idfix-actual-verification.json`、実画面は `home-idfix-1440.png` と `home-idfix-390.png`。ホーム本文の可視文字数は609文字（ブラウザで集計）。画像6枚が読み込まれ、楽天5枚は240pxを240pxで表示し、切抜きや拡大をしていない。

`home-idfix-generated-delta.json` は、共通改善完了候補ddd32380から本文の変更はホームだけであることを確認する。他33本文、記事メタデータ、すべての既存JavaScript、比較記事の画像filterは同一。共通CSSはstampのみ変更、追加スタイルはホームに限定する。全34×5幅の170表示は `entryfinal-layout-audit.json` と `home-short-layout-audit.json`、全34の文字200%・15記事の意味/可視日付/noJS・26表/4種類のナビゲーション操作は `entryfinal-*` に候補別に記録した。新しく画像を追加したホームは、最終候補で同じ5幅と操作を再実測した。

旧候補53dc508cは汎用previewがPASSでも専用の画像確認で6枚中0枚だったため、不合格として `home-short-image-failure.json` に残した。ローカルがホームをID5へ再採番したことが原因。既存のローカル判定内だけでfront/query/current/snapshotの実ID一致を確認する分岐を加え、本番ID15・保存本文・snapshot・metadata・個別画像hashの照合を維持した。修正後の最終候補ではJavaScript有効/無効とも6枚を確認している。

回帰検証は商品の同定と画像の利用条件、広告リンク属性、欠損費目、価格期限、キャッシュされた本文、JavaScript無効、放置・再訪、比較2/3/4機種、同意前・拒否・許可・撤回と重複イベントを含む。費用・採寸の計算は空欄・0・負数・小数・境界値・機種切替を既存の計算根拠と照合する。

旧本番の読み取り確認では通常34URLすべてHTTP200、15記事のArticle見出し・可視日付が一致。カテゴリ転送、検索、ページ送り、添付転送、404を確認した。著者アーカイブの実在URLは取得できず未確認。`technical-external-verification.md` に対象と限界を記録している。

公式31URLは29到達・2取得不能。実際に掲載が認められた26固有リンクは、広告16すべて到達、通常10のうち9到達・1取得不能。HTTP200を色・構成別の在庫、保証適用、成果帰属の証明にはしていない。`technical-ad-destinations.md` に詳細を記録した。

CookieYesの通信は本番baselineで初回・拒否・許可・撤回・再訪を観測し、初回/拒否/撤回後の観測窓ではGoogle送信を検出しなかった。ローカル修正を本番DOMへ注入する試験では320/390pxで設定の拒否ボタンが画面内に収まった。これは本番への変更ではなく、GA4アカウント設定や全将来の通信を保証しない。

## 残っている確認

- K11+ Proの寸法軸、Miniの一部の清掃頻度・部品・費用、機種別の未公表収納寸法や開閉条件、mini colorのタブレット個数/サイズ、選択構成別の注文可否などは理由と確認先を表示したまま。
- C1000 Gen2は説明書の単口1500W/複数口合計1550Wを明記。特設ページの説明不足についてメーカー回答は未取得。
- 未照合画像の再掲載には型番・世代・構成・利用根拠の確認が必要。表示を止めたことを確認済み画像への修正とは扱わない。
- GSC・GA4アカウント・ASP確定報酬はUNAVAILABLE。field CWV/INP、実CDN/ページキャッシュの期限境界、全購入CTAの本番1操作1イベントと記事/商品/販売先/配置/版の実対応、実サーバー保持設定、メール到達・返信・送信元認証は未検証。
- メーカー問い合わせとメール試験の文面は `output/site-improvements-20260913/drafts/` に準備した。送信はしていない。

## 公開と復元の境界（Q16）

本番は未変更。確認済み候補への具体的な公開指示を受けてから、同じ候補を `owner-direct-v1` で公開し、34ページ・テーマの反映結果、主要導線と同意動作を再取得して照合する。今回の実装指示を公開やメール送信の承認にはしない。

記事の変更前本文とrevisionは候補内のprivate baselineへ保存済み。テーマは変更前tree hashを記録している。公開時には限定bridgeがbatch開始時の復元用状態を保存し、確定した適用失敗や反映不一致を検出した場合は既存のrollback処理を使う。未知の操作状態では推測して再送・復元しない。

中断時は `direct --owner-checkout /home/minami/rakuten status --candidate <上記候補>` で状態を読み、同じ候補の既存操作を照合する。公開成功後のGit同期だけが未完なら `sync` を使い、記事を再公開しない。公開成功後に内容を戻す場合は、保存した変更前本文を新しい候補として現状のrevisionに照合し、プレビューと具体的な復元指示を経て反映する。過去のGit基点が実際の本番テーマそのものだとは仮定しない。

本番公開・本番復元・反映後照合は未実施。Gitへのコード保存と本番反映の状態は別に記録する。

## 再現する際の生成順序

このテーマの正規stamp generatorはowner-private区分にあり、通常の `make generate` からは実行されない。一般の入力・本文・公開データを生成した後、ローカルstampだけを作る `.venv/bin/python scripts/build_st1704_self_hosted_theme.py --generate` を明示実行し、依存manifestを通常generatorで更新する。`--source-check` と品質監査のblocked-baseline `--check` で整合性を確認した。owner-private区分・公開権限・品質未実行の判定を解除していない。同意assetの期待値をhash入力に持つ `build_editorial_measurement_v1.py --generate` もローカルmanifestの更新として実行した。`--package` は使わず、計測はdefault-offのままで有効化していない。

固定toolchainはPython3.14.6、Node24.18.1、npm11.16.0。分離配置されたnpmのshell launcherがprefix moduleを見つけないため、この作業ではローカルな `/tmp/raos-site-toolchain-bin/npm` から固定Nodeと `npm/11.16.0/node_modules/npm/bin/npm-cli.js` を直接呼ぶ。npmや検査の版・内容を代替していない。

実装はローカルcommit `4408ab28`、共通の回帰修正は `63d00765`、入口4項目と同意asset期待値の修正は `2184e576`。初回の全体実行は21,906通過・83失敗（subtestを含む）で、旧レイアウト期待値と実不具合を収集し修正した。次の `make fast BASE=4408ab28` は14,599通過・1失敗・7skip・161 subtests通過。その1件は追加済み同意assetに対する古い閉じた許可リスト期待値であり、1行修正し正規の計測manifestを再生成した。共有一時ディレクトリ更新を検出したレジストリ試験49件は既存race guardを維持してserial区分へ移した。`make fast BASE=63d00765` は全選択段階PASS（Python並列14,346・serial1,696・data348・storage64、7skip、46subtests。NodeとVitest4件もPASS）。ホーム初版の実行は画像欠落の発見後に中止し、PASSと扱わない。修正後の `make fast BASE=2b332824` は並列4,806・serial298・30subtests、全選択段階PASS（data/storageは選択0、Node選択なし）。ホームの追加全体を含む `make fast BASE=2184e576` も全選択段階PASS（並列14,259・serial1,662・data348・storage64、7skip、136subtests、NodeとVitest4件）。選択はgenerators78・Python644ファイル・Node87ファイル、終了コード0。重複する実行件数を合算して水増しせず、未選択の区分を全件合格とは呼ばない。

ホーム短文化・6画像投影のsourceは `2b332824`、ローカル再採番対応は `52e9a56f`。最終候補は後者を含む。進捗表の候補・公開状態もこの候補へ更新する。

最終結果の集約は `output/site-improvements-20260913/integration-verification.v1.json`。元Excelを保持し、136項目と技術確認16行へ5つの進捗列を加えた別版を作成した。元の全セルと他24個のarchive部分の保持、ZIP整合性を `progress-artifact-validation.json` で確認する。最終記録の更新後に成果物を再生成し、Downloadsへ `kurashinoshirube_all_pages_improvements_20260913_progress.xlsx` として保存・同一性を確認した。
