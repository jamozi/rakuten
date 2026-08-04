---
document_id: RAOS-BACKLOG-001
title: "Epic・Story・依存関係・MVP実装Backlog設計"
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

本書は、既存のArchitecture/API/AI/Content/UI/Analytics/Security/Test/Opsに分散した実装Sliceを、Codexが一つずつ実装できるCanonical Backlogへ統合する。Epicは20件、Storyは129件である。

全Storyは初期状態が`NOT_STARTED`、Post-MVP Storyは`DEFERRED_POST_MVP`である。Story数は作業完了を意味せず、Codexが勝手に複数Storyを一つの巨大PRへまとめることを許可しない。

# 2. Backlog正本

- `RAOS_13_story_backlog_v1.0.yaml`: 機械可読正本
- `RAOS_13_story_backlog_v1.0.csv`: 人間の一覧・Filter用
- `RAOS_13_epic_catalog_v1.0.yaml`: Epic定義
- `RAOS_13_critical_path_v1.0.md`: MVP主要順序

# 3. StoryのDefinition of Ready

Codexへ渡す前に次が必要である。

1. Story ID、目的、対象外が明確
2. `depends_on`がすべて`VALIDATED`または明示的にMock可能
3. Requirement/Design refが存在
4. Open Decisionに安全なDefaultまたはBlockがある
5. DeliverableとAcceptance CriteriaがTest可能
6. Test SuiteとSecurity影響が特定
7. Migration/Contract breakingの有無が特定
8. 1 PRで安全にReviewできるScope

# 4. Definition of Done

- StoryのDeliverableがRepositoryに存在
- 対象ContractとCodeが一致
- Unit/Integration/Contract/必要なRuntime TestがPASS
- Security/Privacy/A11y要件を満たす
- Migrationはzero-to-latest/upgradeをPASS
- Documentation/ADR/Runbookを更新
- Status Registryに実行Evidence URIを記録
- 未実施項目を残す場合は理由、Owner、Follow-up Storyを記録
- Human ReviewerがPRを承認

`IMPLEMENTED_NOT_VALIDATED`はDoneではない。Runtime Testが必要なStoryはEvidenceがない限り`VALIDATED`へ進めない。

# 5. PR単位

- 原則1 Story = 1 PR
- LサイズStoryは内部CommitまたはSub-PR計画をExecPlanへ記載
- Contract revisionとBusiness implementationを同じPRへ混ぜない
- Migrationと大量Data backfillは段階を分ける
- Generated fileだけの巨大差分にはSourceとgeneration commandを明記
- 無関係なrefactor、dependency update、format rewriteを混在させない

# 6. MVPの縦断順序

```text
Canonical/Repository
→ PostgreSQL/Runtime
→ IAM/Security
→ Rakuten/Catalog
→ Evidence
→ AI Draft
→ Content/Review
→ Snapshot/Public
→ Click/Revenue
→ Operations/Recovery
→ 1 article
→ 5–10 article pilot
→ 30–45 article GATE-1
```

全機能を横に完成させてから統合するのではなく、早期に一つの安全な縦断Flowを通す。ただし、Security、Audit、Human approval、Kill Switchを「後で追加する」扱いにしない。

# 7. 並列化

Repository/Contract後は、次を限定的に並列化できる。

- Database foundationとUI Design System
- Rakuten Adapter recorded testとAI registry loader
- Public shellとAdmin shell
- Analytics schemaとRevenue secure intake
- Terraform moduleとApplication local runtime

共有Contractを変更する場合は、先にContract PRをMergeし、各実装Branchをrebaseする。

# 8. Post-MVP延期

Model Judge、Champion/Challenger、部分自動公開、複数カテゴリ、高度帰属、Portfolio optimizer、Fine-tuningは設計候補として残すが、MVPで実装しない。MVPの収益・品質・運用Evidenceなしに前倒ししない。

# 9. Open Decision

Business/Provider固有のDecisionはStoryの`open_decisions`へ紐付ける。Blocking Decision未解決時、Codexは仮値でProduction実装を完成扱いにせず、Mock/Interfaceまでで停止する。

# 10. Status更新

Story statusはPRとCIから更新するが、Human approvalなしに`VALIDATED`/`DEPLOYED_PRODUCTION`へ昇格しない。Evidenceが削除・期限切れ・Regressionで無効になった場合は状態を降格できる。

# 11. 明示的な未実施

- 全129 Storyの製品実装
- GitHub Issue/Projectへの登録
- Story owner/assigneeの実割当
- Open Decisionの解決
- PR/CI/Runtime Evidence
- Staging/Production deployment

Backlogは実装可能な設計であり、進捗は0から開始する。
