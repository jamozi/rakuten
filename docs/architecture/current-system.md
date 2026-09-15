# Current RAOS system

この文書は実装への地図です。仕様の適用範囲は[docs map](../README.md)、現行の編集・利益
contractは[Editorial V3](../../changes/editorial-portfolio-v3/README.md)を参照します。
実装・local testの存在と、live接続・公開・事業成果は別の状態です。

## Data flow and ownership

```text
provider / official evidence
  → bounded adapters → application use cases → domain + versioned contracts
  → editorial review → approved immutable publication snapshot
  → public projection → public API / Web / tracked WordPress materialization

confirmed rewards → private finance / reconciliation → portfolio economics
                                      (not editorial ranking input)
```

| Boundary | Implementation | Verification / source |
| --- | --- | --- |
| Business rules / use cases | `python/raos/domain/`, `python/raos/application/` | 領域tests、versioned contracts |
| External interfaces | `python/raos/ports/`, `python/raos/adapters/` | 接続先・auth・idempotencyのnegative tests |
| Delivery | `apps/`, `python/raos/api/`, `python/raos/workers/` | public/admin分離、authn/authz |
| Snapshot / public read | [snapshot](../../python/raos/domain/publishing/publication_snapshot_v2.py), [projection](../../python/raos/domain/publishing/public_projection_v2.py) | `tests/st0902_v2/`, `tests/st0905/`, `tests/st1001/` |
| Identity / evidence | `domain/catalog`, `domain/evidence`, `domain/decision_support_v2` | `tests/raos_v2/`, `tests/editorial_portfolio_v3/` |
| Reader UI / WordPress | `packages/web-ui/`, `changes/wordpress-local-preview-v1/` | `tests/wordpress_local_preview/`, `tests/wordpress_seo_audit_v1/` |
| Local reader guides | [renderer](../../python/raos/application/editorial/local_reader_guides.py)、`scripts/build_local_reader_guides.py` | [採用範囲・境界](../../changes/editorial-portfolio-v3/READER_REMAINING_IMPLEMENTATION.md#ローカル専用ガイドの境界)、`tests/wordpress_local_preview/test_local_reader_guides.py` |
| Publication bridge | `packages/wordpress-mcp-bridge/`, `changes/wordpress-mcp-v1/` | `tests/wordpress_mcp_v1/`、[runbook](../runbooks/wordpress-verified-incremental.md) |
| ASP ingestion | `tools/affiliate_ingestion/` | `tests/test_affiliate_ingestion.py`、[guide](../affiliate-network-ingestion.md) |
| Generated artifacts | `scripts/raos_build_core.py` registry | `changes/build/manifest.v2.json`、owner drift tests |

`domain`は純粋なルール、`application`はuse case、`ports`は契約、`adapters`は外部実装を所有します。
公開側へ新しい情報を出す場合はsnapshotとprojectionの閉じた契約を検討し、内部repositoryを
rendererへ接続しません。Evidence locator・raw AI・Financeの内部値は公開payloadに出しません。
既存source_note等で解決できる場合は、公開契約を不用意に増やしません。

## Invariants and executable constraints

| Invariant | Executable constraint |
| --- | --- |
| Authentication / authorization | `tests/st0401/test_authentication.py`, `tests/st0403/test_authorization.py`, `tests/st0404/test_security.py` |
| Public/internal isolation, hostile input | `tests/st0905/test_runtime_hostile_v2.py`, `tests/st1001/public-shell-boundaries.test.ts` |
| Disclosure and affiliate CTA behavior | `tests/st1004_v2/disclosure-affiliate-negative.test.ts` |
| Snapshot approval / idempotency | `tests/st0901_pr3/test_authorization_idempotency.py`, `tests/st0902_v2/test_domain.py` |
| Confirmed versus estimated economics | `tests/st1305_v2/test_reconciliation_negative.py`, `tests/editorial_portfolio_v3/test_economics_cli.py` |
| Identity, freshness, comparison scope, zero-weight finance factors | `tests/editorial_portfolio_v3/test_contract.py`, `tests/raos_v2/test_decision_engine.py` |
| WordPress bounded owner authority / snapshot / recovery / default-off | `tests/wordpress_mcp_v1/`, `tests/wordpress_local_preview/`。旧候補の別人承認は互換経路だけ |
| AI truthfulness / no invented experience | [product eval](../../python/raos/application/ai/evaluation_harness.py), `tests/st0707_runtime/test_harness.py` |

不変条件を変える場合は入力から公開・集計までの隣接影響を確認します。
通常のlocal実装に追加承認台帳は不要です。外部適用は既存の実行境界に従います。

WordPressの日常更新は[owner-direct-v1](../../changes/wordpress-direct-publish-v1/README.md)が
旧公開手順の後継です。初回に設定した専用principalと会話上の対象への公開指示を使い、
独立監査・繰り返しのwp-admin承認を不要にします。固定snapshotから限定bridgeへ送り、
保存後のpublic projectionをテーマが読みます。Git checkpointは公開前、push/PR/CI/mergeは公開後です。

## Reader purchase-support successor

[購入判断契約](../../changes/reader-purchase-support-v1/README.md)は16商品枠と13既存URLに限定します。
商品仕様・販売条件・調査課題・商品別guide routeを共通カタログから生成し、適用済みowner-direct
snapshotの本文hashと一致するpublic runtimeだけでUIとCTA計測を有効にします。内部カタログや
ASP rawをPHPへ渡しません。価格は性能評価へ加点せず、24時間以下の販売条件に基づく予算判定に
使います。欠損費目・期限切れは予算未判定です。既存6機種の費用コースを残し、型番とコースが一致する
一次情報だけを8機種へ展開します。公開済み262〜266は既存IDを明記して編集元へ取り込みました。
GA4は同意と明示enableを必要とする既定OFFの別profileです。旧provider識別子の位置を推測せず、
クリックとpage_view sessionを別集計し、財務の確定報酬へ変換しません。

## Current product contracts

Editorial V3はV2の履歴を変更せずに採用された後継です。
`changes/editorial-portfolio-v3/editorial-portfolio.v3.json`がstrategyとselection policy、
`editorial-identities.v1.json`が記事分類と比較範囲、`market-candidate-audit.v1.json`が候補・除外根拠、
`generated/navigation.v3.json`がホーム・関連記事の唯一の機械可読元です。
ownerは`scripts/build_editorial_portfolio_v3.py`です。

確定貢献利益の式、欠損時のUNAVAILABLE、新規記事を増やす条件はstrategyを参照します。
公開用情報とowner-private economicsを分離し、未帰属報酬を記事へ推測配賦しません。
記事単位の一般的出典を、型番・variant別の安全性や保証確認の完了へ昇格させません。
ローカル読者ガイドは`local-reader-guides.v1.json`を入力とする別経路で、`publication_authority=false`です。
既存の本番記事レジストリへ自動昇格させず、比較に必要な根拠の欠損は生成停止条件として保持します。

v2 decision supportのルールは`changes/raos-v2/`と`domain/decision_support_v2`が所有します。
旧v2の単一wedgeを現行portfolio全体の範囲として解釈しません。
実装状況と外部未実行項目は[status v2](../../changes/status/README.md)から確認します。

## Codex context and capability boundaries

AGENTSは目的・不変条件・正本への入口、READMEは開発案内、Skillは対象作業の手順を所有する。
Project設定は`.codex/config.toml`、workflowは`.agents/skills/`。個人設定・認証・Memoryをrepositoryへ複製しない。
GitHubと限定されたWordPress能力の承認境界はAGENTSと各workflowに従う。

Codex設定、スキルの有効化、起動・実ロードの診断を扱う時だけ
[ハーネス運用](../development/codex-harness.md#codex-context-and-capability-boundaries) を読む。
製品コードの通常修正では、上記の該当するdata flow・不変条件と対象実装から調べる。

## Cold-start evaluation

指示やハーネスの品質・トークン効率を評価する時は
[評価手順](../development/codex-harness.md#cold-start-evaluation) を使う。
実利用量とファイルサイズを区別し、受入成功・境界保全・ケース別評価の維持を満たしたうえで効率を判定する。
