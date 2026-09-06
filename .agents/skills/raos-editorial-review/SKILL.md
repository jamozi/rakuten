---
name: raos-editorial-review
description: RAOSの記事・商品比較候補を、商品同定、一次情報、比較範囲、日本語、購入判断支援、SEO/CROの観点でレビューする。記事候補や選定理由の品質監査に使う。一般のコード修正、ASP接続実装、公開操作のみの依頼には使わない。
---

# Editorial review

## Input and references

対象のtracked sourceまたは比較候補、意図する読者・比較範囲、evidence locator、既存Findingを
特定する。不明な値はUNKNOWNとして扱い、安全に確認できる範囲を進める。

- [現行portfolioと選定contract](../../../changes/editorial-portfolio-v3/README.md)
- [仕様の適用範囲](../../../docs/README.md)
- 表示変更を伴う場合だけ[WordPress workflow](../raos-wordpress-workflow/SKILL.md)

## Procedure

1. 対象記事と依存する商品・出典だけを読む。既存Findingと現行V3のselection policyを確認する。
2. 型番・variant・JAN等の同定、primary sourceのlocator、鮮度、主張との対応を照合する。
   不足した根拠を推定で埋めず、同一系列の別商品へ転用しない。
3. 比較範囲と除外理由、用途別の選び方、弱点、自然な日本語を点検する。
   検索意図・関連記事・CTA・広告表示は、読者が判断する流れの中で確認する。
4. selection policyの加点要素とzero-weight要素を照合し、編集判断と利益計測を分離する。
5. 修正した場合はowner generatorと関連testを実行する。表示の変更はlocal previewへ進む。

## Validation and output

`make fast`の選択を使う。V3 contractでは`tests/editorial_portfolio_v3/`、decision supportでは
`tests/raos_v2/`の関連境界を確認する。

対象・比較範囲、重大度付きFinding、根拠locator、修正内容、検査結果、UNKNOWNと残る条件を返す。
Findingなしと未検証を区別する。Criticalな同定・出典不足は公開不可として示す。
公開の依頼はWordPress workflowへ渡す。レビュー合格を公開承認へ置換しない。
