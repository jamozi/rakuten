# 段階公開用の商品証跡取得

契約・型番は実行中のcheckoutから読み、資格情報と楽天API応答・画像・証跡は保存済みcheckoutへ保持する。保存済みcheckoutのbranchを変更せず、認証情報やAPI応答を作業worktree、ログ、Gitへコピーしない。

```sh
scripts/raos_editorial_portfolio_v2.py capture \
  --owner-checkout /home/minami/rakuten \
  --product-ids PRD-EXACT-REGISTERED-PRODUCT
```

実在する契約内の商品IDだけを渡す。重複・未知のIDを拒否する。`--owner-checkout` は保存済みcheckoutの固定絶対パスだけを認める。資格情報の入力はこのコマンドでは行わない。

`--product-ids` を省略した既存呼び出しは、従来の全件取得と `RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2` を維持する。明示した対象が空の場合は、API、資格情報、JAN証跡、商品証跡を読み出さずに0件を返す。これは購入導線のない記事を扱うための状態であり、全商品の収益機能が検証済みという意味ではない。

## 対象限定の証跡

対象を明示した取得は次の独立した証跡を出力する。

- schema: `RAOS_EDITORIAL_PORTFOLIO_INCREMENTAL_PRODUCT_EVIDENCE_STATUS_V1`
- 保存場所: `.secrets/editorial-portfolio-v2/incremental/product-evidence-status.<scope-sha256>.v1.json`
- scope hash: 現行portfolioのSHA-256と、並べ替えた対象商品ID集合を結合した正規JSONのSHA-256
- 必須フィールド: `schema`, `captured_at`, `portfolio_sha256`, `scope_sha256`, `product_ids`, `owner_attested`, `publication_authority`, `products`

`owner_attested` と `publication_authority` はともに `false`。API同定は所有者による確認ではなく、公開承認にもならない。対象限定の証跡で従来の全件証跡を上書き・代用しない。

各商品は `verified`, `not_found`, `ambiguous`, `unresolved` のいずれかとして記録する。`verified` は実際のAPI本体応答・アフィリエイト応答・画像を照合した場合だけ。公式JANの証跡が不足する場合はAPI取得を行わず、`unresolved` と `OFFICIAL_JAN_EVIDENCE_MISSING` を記録する。JAN証跡の改ざん、期限切れ、型番不一致や所有者確認の欠落を自動修復しない。

## 公開準備側の再検証

```python
views = product_evidence_views_v2(
    current_source_checkout,
    private_root=owner_checkout,
    product_ids=exact_commerce_product_ids,
    require_fresh_set=True,
    require_verified_set=True,
)
```

比較対象全体ではなく、今回実際に画像・購入リンクを掲載する正確な商品集合を渡す。保存先は `incremental_product_evidence_status_relative_path(current_source_checkout, product_ids)` で算出する。再検証は同じ対象集合・現行契約・24時間の鮮度・各応答と画像のハッシュを確認し、不足・改ざん・別集合・方式違いの証跡を拒否する。リンクURLはAPIから取得した値を改変しない。

この取得だけでは記事本文の出典確認、ローカル表示監査、独立したCodex点検、所有者の公開承認、公開後の照合は完了しない。
