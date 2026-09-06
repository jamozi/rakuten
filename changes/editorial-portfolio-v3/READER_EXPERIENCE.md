# 暮らしのしるべ・読者体験改善

## 編集元と表示経路（RX-000 / RX-002 / RX-004）

| 責務 | 編集元・実装 |
| --- | --- |
| ホーム | `changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/templates/front-page.html` |
| 記事外枠 | 同子テーマの `templates/single.html`、`functions.php` |
| 共通CSS | 同子テーマの `theme.json`、`assets/theme.css`、`assets/editorial-v2.css` |
| ナビ・カード・パンくず | 同子テーマの `parts/header.html`、`parts/footer.html`、`functions.php` |
| 前半5記事の入力 | `changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json` のAST・render_model |
| 前半5記事のレンダラー | `python/raos/application/editorial/self_hosted_editorial_pilot.py` |
| 後半5記事の入力 | `changes/wordpress-local-preview-v1/fixtures/articles/` のHTML |
| 本文の生成・正規化 | `scripts/raos_editorial_portfolio_v2.py` の `generate-old-fixtures`、`sanitize-source-fixtures` |
| 商品と販売状態 | `changes/editorial-portfolio-v2/editorial-portfolio.v2.json`、`manufacturer-sales-state.v1.json` |
| 出典とclaim | `changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json` |
| 記事の識別・目的 | `changes/editorial-portfolio-v3/editorial-identities.v1.json` |
| 画像 | 子テーマの `raos-assets.v1.json`、`media/product-media-registry.v1.json`、既存の検証済み商品画像adapter |
| 画像生成物のowner | `scripts/build_st1704_theme_assets.py`、`scripts/build_st1704_self_hosted_theme.py` |
| Portfolio生成 | `scripts/build_editorial_portfolio_v3.py` |
| WPナビ・検査対象生成 | `scripts/build_editorial_v3_theme_navigation.py` |
| ローカルWP | `changes/wordpress-local-preview-v1/`、`make wordpress-preview-up` / `sync` / `environment` |
| 公開候補の共通入口 | `scripts/raos_wordpress_publication_request.py`、`raos_wordpress_release_workflow.py` |
| 既存の非商用候補 | `scripts/raos_wordpress_incremental_candidate.py`、`verified_incremental_v1.omit_unverified_commerce` |
| 通常検査 | `make fast`、`tests/st1704/`、`tests/editorial_portfolio_v2/`、`tests/editorial_portfolio_v3/`、`tests/wordpress_local_preview/` |
| ブラウザー検査 | `changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js` |

前半5記事の生成HTMLは直接編集しない。後半5記事は100席未満、30L・3kg以下、前開き＋ストッパー、Roomba、SOLOTA状態確認。
公開UIはWordPress子テーマが所有する。別のWebアプリのpublic article rendererは本改修の表示経路ではない。

## 公開版と追跡済み原稿

2026-09-06 JSTのproject WordPress MCP読み取りでは公開記事10本、子テーマ1.5.1、計測OFFを確認した。
公開状態をこの記録だけで将来の適用条件に使わない。適用時のID・revision・hashは既存MCP経路で取得する。

- SOLOTA `/solota-vs-rakua-mini-plus/`（公開ID 86）は状態確認記事。型番NP-TMLK1-KとTK-MDW22Bを扱い、購入リンクなし。
- Roomba公開版は3構成。追跡済み原稿はMini Slim＋K11+ Proの2製品へ整理済み。原稿を保持する。
- 30L・3kg以下の公開版は4モデル。追跡済み原稿は5モデル。原稿を保持する。
- 商品集合、型番、確認日、出典、UNKNOWNを表示改修の都合で変更しない。

## 実装と公開の境界

本改修はlocal/recorded dataで実装・検査する。provider capture、画像生成API、本番下書き更新、公開提案、公開適用、計測有効化を実行しない。
画像や販売リンクの欠損を埋めず、検証済み表示条件を満たさない枠・offerを出力しない。
新しいSOLOTA比較記事は、必要な公式仕様・型番・販売状態・保証・同一構成の確認が完了するまで生成対象にしない。
既存の承認待ち候補、canonical/upstream/package、独立承認、hash/precondition、kill switchは維持する。

## 実装順と検証

最初にRX-000、RX-001、RX-003、UI-001〜005、DS-006、DS-001を完了する。
続いて共通部品、ホーム、食洗機代表実装、ハブ、記事移行の順で進める。
5幅（360/390/768/1024/1440）を検査し、画像なし・UNKNOWN・CTAなし・長い型番とタイトルを含める。
ブラウザーartifactは `output/playwright/` に保存する。local resultはCIや本番の証跡と区別する。

実読者5人以上の6問理解テスト、ホーム5秒、記事30秒テストは未実施。
自動検査で人の理解度や売上改善を推定しない。ローカル移行は人のテストと並行する。
