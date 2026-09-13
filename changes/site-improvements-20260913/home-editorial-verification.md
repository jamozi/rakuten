# ホームを特定の商品に依存しない画像へ変更

> 最新のホーム構成と公開候補は [home-layout-preview.md](home-layout-preview.md) を参照。以下は前候補の記録。


ユーザーの追加指示に従い、以前の食洗機・スーツケース・ロボット掃除機のAI編集イメージ3枚へ戻した。新たな画像生成は行っていない。短くした文章・既存ヒーロー・各比較記事への画像リンクを維持し、6商品画像のホーム投影は停止した（公開metadataはnull）。各比較記事内の商品画像は変更していない。

- 候補: `bf5d76b770ef02a0675ef2727f930346f9e72b405a22bf5aaba325d9fe2786f5`
- Source: `0bf8f3403b8ad36805ec443e4041269951f40ac8c43a23f28cdc5c8f9ef0544d`
- Runtime: `21c31f2edbe12a490b42f2fdcfc66a2471fbae93c37453c839432ea89e0063a6`
- Source commit: `9182d9eb`（画像選択は`825c456c`を含む）
- Preview: http://127.0.0.1:41398/ — owner-direct prepare publication_ready=true、35URL preview PASS。本番は未公開。

3枚の既存画像は762×506px。ローカル実画面の確認で最初の画像がPCで1216pxへ拡大されていたため、上限を元の762pxに修正。スマートフォンでは3枚とも幅いっぱい（320px画面で288px、390px画面で358px）に表示する。元画像を加工・切抜きしていない。

320/375/390/768/1440px、文字200%、JavaScript無効で3枚の画像とリンクを確認。横はみ出しなし。キーボードで3つの画像リンクを順に開き、各比較記事への実遷移を確認した。PC・スマートフォンのスクリーンショットも目視した。

関連テスト30件＋16subtests、古い画像期待値を更新した確認12件＋16subtestsが通過。最終`make fast BASE=6dfd0b24`は選択範囲をすべて通過（並列4,672、serial298、136subtests。Node/data/storageは選択なし）。前候補で通過した全体検証と重複計上しない。初回の2件の失敗は6商品画像を期待する旧テストで、修正後の最終実行は終了コード0。

証拠は`output/site-improvements-20260913/home-editorial-integration.v1.json`、`home-editorial-final-verification.json`、`home-editorial-final-1440.png`、`home-editorial-final-390.png`、`home-editorial-delta.json`。ほか33本文・記事metadata・既存JavaScriptが前候補と一致することを確認した。以前の候補と検証結果は履歴として保持する。

34ページ改善に残るメーカー回答・未照合の商品画像・GSC/GA4/ASP・実CDNキャッシュ・メール・本番反映照合の未確認状態は引き継ぐ。公開はこの確認済み候補への具体的な指示を受けてからowner-direct-v1で行う。
