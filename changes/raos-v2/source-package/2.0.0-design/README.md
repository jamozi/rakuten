# RAOS V2 Design Package

## Purpose

`kurashinoshirube.com` の後継プロダクトを、現行公開面を保護しながら段階実装するためのdecision-complete設計パッケージです。設計・調査・実装計画のみを含み、コード実装や外部作用は含みません。

- Package version: `2.0.0-design`
- Generated at: `2026-08-28T22:30:00+09:00`
- Authority: `DESIGN_ONLY_UNAPPROVED_FOR_EXTERNAL_ACTIONS`
- Audit snapshot HEAD: `83cfa17f91dddbee2bcd4e781545fd2bb4a5bcc4`（現在状態ではなくtime-bounded evidence）
- Initial wedge: `旅の機内持ち込み条件と荷物選び`
- Public architecture: self-hosted WordPress継続 + Git successor overlay/control plane
- First implementation PR: local Phase 0–2、B-V2-001–034

## Required deliverables

| File | Purpose |
| --- | --- |
| 00_EXECUTIVE_DECISIONS.md | 最終提案、測定定義、34判断 |
| 01_CURRENT_STATE_AND_RESEARCH.md | 監査パケット、公開面、公式資料、競合の証拠整理 |
| 02_PRODUCT_BRAND_CATEGORY_STRATEGY.md | brand、wedge、score、25資産portfolio、growth gate |
| 03_CONTENT_SEO_EDITORIAL_SYSTEM.md | content/claim/source/recommendation/SEO/freshness/publication |
| 04_UX_DESIGN_SYSTEM.md | IA、wireframe、token、component、responsive、WCAG |
| 05_TECHNICAL_DATA_ANALYTICS_ARCHITECTURE.md | architecture、data、ports、states、analytics、ops |
| 06_MIGRATION_ROADMAP_AND_BACKLOG.md | Phase 0–6、36要件、49 backlog、rollback/cost |
| 07_DECISION_TRACEABILITY.yaml | 34判断→36要件→49 backlog→51 test |
| 08_TEST_AND_ACCEPTANCE_PLAN.md | 全試験、UAT、phase exit |
| CODEX_MASTER_IMPLEMENTATION_PROMPT.md | Phase 0–2を追加判断なしで開始する実装契約 |

## Additional controls

| File | Purpose |
| --- | --- |
| 09_EVIDENCE_AND_SOURCE_REGISTER.yaml | 監査証拠hash/line hintと外部一次情報URL |
| 10_INTERFACE_CONTRACTS.yaml | entities、ports、state transition、overlay paths |
| 11_EXTERNAL_ACTIONS_REGISTER.yaml | 未実行の外部・不可逆action |
| 12_INDEPENDENT_QUALITY_REVIEW.md | 依頼品質gateに対する独立批判 |
| CONTROL/implementation_contract.yaml | 実装base/worktree/scope/stop条件 |
| CONTROL/source_integrity.json | 入力prompt/archive/packet manifest検証 |
| CONTROL/package_validation.json | 構造・参照・依存・権限検証 |
| package_manifest.json | package file inventory/hashes |
| MANIFEST.sha256 | ZIP展開後のファイルhash照合 |

## Integrity verification

From the extracted `RAOS_V2_DESIGN_PACKAGE/` directory:

```bash
sha256sum -c MANIFEST.sha256
```

`package_manifest.json` records every content/control file except itself and `MANIFEST.sha256`; `MANIFEST.sha256` then binds `package_manifest.json` and every other file. The adjacent external `RAOS_V2_DESIGN_PACKAGE.zip.sha256` binds the ZIP itself.

## Authority boundary

This package does not authorize or claim any publication, deployment, production change, WordPress write, credential access, live provider request, analytics transmission, paid purchase, irreversible migration, merge or release. Live repository instructions and separate owner approvals remain authoritative.
