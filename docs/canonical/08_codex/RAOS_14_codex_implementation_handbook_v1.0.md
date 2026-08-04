---
document_id: RAOS-CODEX-001
title: "Codex実装ハンドブック・Repository運用・PR設計"
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

本書は、完成したRAOS設計をCodexが安全に実装するための統括手順を定義する。個別PackageのKickoffを置換するのではなく、Canonical BacklogとStatus Registryを入口として統合する。

# 2. Codexの役割

Codexは設計に基づきコード、Test、Migration、Documentationを作成する実装Agentである。Product Owner、法務、Security Approver、Editorial Reviewer、Production Operatorではない。公開、契約同意、実Credential発行、法的判断、最終Releaseを代替しない。

# 3. 最初の実装

最初は`ST-0001 Import canonical design package`のみを実装する。Business logicを先に作らない。次にAlignment revisions、Repository/toolchain、Contract CIへ進む。

# 4. Story実装Protocol

1. Storyを一件選ぶ。
2. `depends_on`とEvidenceを確認する。
3. `AGENTS.md`、Design refs、Contracts、Testsを読む。
4. Preflightを提示する。
5. 必要ならExecPlanを作る。
6. Contract/Testを先に変更または追加する。
7. 最小Scopeで実装する。
8. Required Testを実行する。
9. Security/Privacy/A11y/Operations impactをReviewする。
10. Status RegistryへEvidence付きで反映する。
11. PRを作りHuman Reviewを受ける。

# 5. Contract-first

OpenAPI、AsyncAPI、JSON Schema、Prompt、Policy、DDL等に影響する機能は、既存契約を無視してHandlerだけを実装しない。Breaking changeはVersioned contractを先に提案し、互換性Testを通す。

# 6. CodexがWeb確認すべき場合

楽天、OpenAI、Google、AWS、Next.js、FastAPI、PostgreSQL、GitHub Actions等の外部仕様は変更され得るため、実装時に公式一次Sourceを確認する。検索結果やBlogだけを正本にしない。確認日、Version、URL、実装への影響をADRまたはProvider snapshotへ残す。

# 7. Generated Code

Generated fileは手編集せず、Source contractと生成Commandを変更する。CIで再生成差分を検知する。Generator versionもLockする。生成型がDomain Modelを直接規定しすぎないよう、Boundary mappingを用意する。

# 8. Migration

Proposal SQLをcopy/pasteでProductionへ適用しない。Migration frameworkへ移植し、zero-to-latest、upgrade、constraint、role、rollback/forward recoveryをTestする。大きなBackfillはChunk、checkpoint、observability、pause/resumeを設計する。

# 9. Provider Adapter

Recorded fixture → Domain normalization → Failure behavior → bounded live smokeの順で実装する。Provider SDK ObjectをDomainやDBへ保存せず、Raw artifactとCanonical modelを分離する。Secretと利用規約で禁止される情報をFixtureへ含めない。

# 10. PR Review

Reviewerは次を確認する。

- Story外の変更がない
- Canonical invariantを弱めていない
- Negative/failure/authorization testがある
- Public/Internal/Finance境界が維持される
- Migration/Contract互換性が説明される
- 未実行Testが正直に残る
- StatusがEvidence以上に昇格していない

# 11. CI Failure

Failing testを削除、skip、threshold緩和、retry増加だけでGreenにしない。仕様変更が必要なら別Decision/PRとする。FlakyならIssue、Owner、原因、代替Evidenceを記録する。

# 12. Security-sensitive Work

Auth、Authorization、Secret、Upload、SSRF、Public projection、AI input、Revenue、Kill switch、DeploymentはSecurity Owner review対象である。実攻撃手順やProduction secretをPRへ載せず、安全なFixtureで検証する。

# 13. Release

CodexはRelease Evidenceを集約できるが、`decision: APPROVED`を自分で設定しない。Production deploymentはHuman-approved GitHub Environment等を通し、RollbackとKill Switchを先に確認する。

# 14. 未実施状態の記録

各PRの最後に、次を分けて記載する。

- Implemented
- Validated in CI
- Validated in staging
- Not executed
- Deferred
- Blocked by open decision

「実装したので完了」とだけ書かない。

# 15. 明示的な未実施

- Repository作成とAGENTS.md配置
- GitHub connection/branch/ruleset
- Issue/PR登録
- CodexによるStory実装
- CI/Runtime evidence
- Human review/release

本書はCodex運用設計であり、Codex実装を実行した成果物ではない。
