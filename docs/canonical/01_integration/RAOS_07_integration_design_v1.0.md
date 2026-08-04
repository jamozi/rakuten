---
document_id: RAOS-INTEGRATION-001
title: "RAOS 正本統合・設計完了境界・実装状態設計"
version: "1.0"
baseline_date: "2026-07-30"
design_status: APPROVED_FOR_IMPLEMENTATION
implementation_status: NOT_STARTED
runtime_verification: NOT_EXECUTED
production_readiness: NOT_READY
language: ja-JP
timezone: Asia/Tokyo
---

> **状態の読み方**  
> 本書は実装可能な設計として承認済みです。ただし、`IMPLEMENTED`、`VALIDATED`、`DEPLOYED`を意味しません。  
> 特に明記しない限り、アプリケーション実装、実DB適用、外部API実接続、Runtime Test、本番設定は **未実施** です。


# 1. 目的

本書は、RAOSの既存設計と今回追加する残存設計を、Codexが一意に解釈できる正本体系へ統合する。主目的は次の三点である。

1. 後続工程で発見された差分を、元設計を消さずに正式採用する。
2. **設計完了**と**実装・検証・本番準備の完了**を厳密に分離する。
3. Codexが未決事項を推測せず、Story単位で実装・Test・Status更新を行えるようにする。

# 2. 現在地

本パッケージ完成時点では、RAOSの要求からCodex実装運用までの設計を一通り定義する。一方、動作するRAOS Application、Production Infrastructure、実Provider接続、実記事、実収益データは含まれない。

| 領域 | 設計 | 実装 | Runtime検証 | Production |
|---|---|---|---|---|
| 要求～Codex実装手順 | 完了 | 未着手 | 未実施 | 未準備 |
| PostgreSQL DDL案 | 完了 | Migration Framework未移植 | 実DB未適用 | 未準備 |
| OpenAPI/AsyncAPI/Schema | 完了 | Handler/Consumer未実装 | Contract Runtime未実施 | 未準備 |
| AI Prompt/Route/Eval | 完了 | Provider Adapter未実装 | Live Eval未実施 | 未準備 |
| Content/SEO | 完了 | Renderer未実装 | Browser/Index検証未実施 | 未準備 |
| UI/Analytics/Security/Test/Ops | 本パッケージで完了 | 未着手 | 未実施 | 未準備 |

# 3. 正本の優先順位

矛盾が生じた場合、次の順に解釈する。

1. 実装・公開時点で有効な法令、楽天・Google・OpenAI等の利用規約、公式API仕様
2. 本書、Canonical Decision、Open Decision、Implementation Status Registry
3. `RAOS-RD-001`の目的、Hard Constraint、成功条件
4. 各領域設計の最新版
5. OpenAPI、AsyncAPI、JSON Schema、DDL、Prompt等の生成可能契約
6. 実装コード

コードが設計と異なる場合、コードを正本に繰り上げない。差分をIssue化し、設計変更またはコード修正をHuman Reviewerが選択する。

# 4. 採用するAlignment差分

| 元Patch | 採用内容 | 現在の状態 |
| --- | --- | --- |
| RAOS_04_001_contract_alignment_patch_v0.1.sql | Job状態・deadline・cancel・index | ACCEPTED_DESIGN_NOT_MIGRATED |
| RAOS_05_001_ai_data_alignment_patch_v0.1.sql | AI Governance永続化 | ACCEPTED_DESIGN_NOT_MIGRATED |
| RAOS_05_002_api_alignment_patch_v0.1.yaml | AI Governance API | ACCEPTED_DESIGN_NOT_APPLIED |
| RAOS_06_001_data_alignment_patch_v0.1.sql | Content AST/Methodology/SEO等永続化 | ACCEPTED_DESIGN_NOT_MIGRATED |
| RAOS_06_002_api_alignment_patch_v0.1.yaml | Content API | ACCEPTED_DESIGN_NOT_APPLIED |
| RAOS_06_003_ai_alignment_patch_v0.1.yaml | ContentとAI Task契約の整合 | ACCEPTED_DESIGN_NOT_APPLIED |


これらは**設計上採用済み**だが、正式Migration、OpenAPI/AsyncAPI改訂、生成型更新、Runtime Testは未実施である。CodexはProposalファイルをProductionへ直接適用してはならず、Backlogの統合StoryでVersioned変更へ移植する。

# 5. Canonical境界

## 5.1 公開の境界

- AIはDraftとFinding候補を生成できるが、承認・公開・Kill Switch解除はできない。
- 公開対象は、承認済みArticle Versionから生成された不変Publication Snapshotだけである。
- Public WebはPublic Read Modelのみを参照し、Editorial、Evidence、Finance、AI Raw Artifactへ到達しない。
- Affiliate CTAは正規の楽天Affiliate URLへ直接遷移し、計測失敗で遷移を妨げない。

## 5.2 編集と収益の境界

- Recommendation順位は読者の条件とEvidenceにより決定し、料率、EPC、RPM、利益を入力に含めない。
- Financeは公開後の事業判断に使えるが、記事内のおすすめ順位を自動変更しない。
- Providerが保証した成果とRAOS推定帰属を別表示する。

## 5.3 自動化の境界

自動処理が許可されるのは、決定論的な取込・検査・投影・安全な縮退までである。次はHuman Approvalが必要である。

- 新規記事の公開
- 主要Claimの追加・変更
- Recommendation順位の変更
- 商品同一性の曖昧な統合
- Critical Findingの解除
- Policy BundleのActivation
- Production Release
- Kill Switchの解除

# 6. 状態管理

状態は `design_status`、`implementation_status`、`verification_status`、`production_readiness` の四軸で管理する。例えば、設計書のYAML ParseがPASSでも、実装状態は`NOT_STARTED`、Runtime検証は`NOT_EXECUTED`のままである。

## 6.1 Statusを変更できるEvidence

| 遷移 | 必須Evidence |
|---|---|
| NOT_STARTED → IN_PROGRESS | Storyに紐付いたBranch/PR、変更予定、Test Plan |
| IN_PROGRESS → IMPLEMENTED_NOT_VALIDATED | Code Review可能な実装、Unit/Static Test結果 |
| IMPLEMENTED_NOT_VALIDATED → VALIDATED | 定義済みRuntime/Integration/E2E TestのPASS Artifact |
| VALIDATED → DEPLOYED_STAGING | Staging Deployment ID、Smoke Test、Rollback手順 |
| DEPLOYED_STAGING → DEPLOYED_PRODUCTION | Release Decision、GATE条件、Security/Operations承認 |

# 7. 未決事項の扱い

Open Decisionは欠陥ではなく、実環境・事業判断を必要とする明示的な入力である。ただし`blocking: true`の項目が未解決のまま、関連するGateやProduction Releaseへ進めてはならない。Codexは仮値を本番値として固定しない。

# 8. 変更管理

- 互換性のないContract変更は新Versionを作る。
- DDL変更はExpand–Migrate–Contractとし、既存データを破壊するMigrationを一段で行わない。
- Prompt、Model Route、Evaluation Dataset、Policy、Recommendation MethodologyはHash付きVersionとして扱う。
- 正本変更はADRまたはCanonical Decisionを追加し、過去Decisionを削除しない。
- 実装StatusはPRごとに更新し、推測で一括完了にしない。

# 9. Codexが実装前に必ず確認する事項

1. 対象Storyと依存Storyが明示されている。
2. Open Decisionが必要なら、安全なDefaultまたはBlock条件がある。
3. 変更対象ContractとRequirement IDが分かる。
4. Migration、Provider、Security、Public UIのどれに該当するか分類できる。
5. Test SuiteとAcceptance Criteriaが定義されている。
6. 実装しない範囲が明示されている。

# 10. 設計完了の定義

本パッケージにおける「残りの設計完了」は、要求された領域について次が存在し相互参照できる状態をいう。

- 人間向け設計書
- 機械可読カタログ
- 実装Backlogと依存関係
- Acceptance/Test方針
- Open Decisionと安全なDefault
- 未実装・未検証Register
- Codex向け実装規則とPrompt

これは、製品の完成、収益性の証明、法令適合の保証、外部Providerの利用承認を意味しない。

# 11. 完了条件

- 全残存設計が`APPROVED_FOR_IMPLEMENTATION`
- 全Storyの初期実装状態が`NOT_STARTED`または明示的な`DEFERRED_POST_MVP`
- 全Runtime Suiteの初期状態が`NOT_EXECUTED`
- Blocking Open DecisionがMaster Registerに掲載される
- Canonical Patch採用方針が一意
- Package ManifestとChecksumが検証可能
