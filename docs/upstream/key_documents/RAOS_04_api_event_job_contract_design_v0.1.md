# RAOS-API-001 API・イベント・Job契約設計書

- **文書ID**: RAOS-API-001
- **Version**: 0.1
- **基準日**: 2026-07-30
- **Status**: BASELINE_CANDIDATE
- **上位文書**: RAOS-REQ-001 v0.1 / RAOS-ARCH-001 v0.1 / RAOS-DATA-001 v0.1
- **契約正本**: OpenAPI 3.1.1、AsyncAPI 3.0.0互換、JSON Schema Draft 2020-12

> 本書はCodexがHTTP Router、Pydantic Model、Worker Message、Contract Test、SDK、Adapterを実装するための設計正本である。コード、DB、Queue、AI出力、CSV取込をこの契約より暗黙に拡張してはならない。

---

## 0. Executive Summary

RAOSの契約層を、Public HTTP、Admin HTTP、Internal HTTP、Domain Event、Worker Job、AI Structured Output、Import Rowの七種類へ分離した。各契約は同じJSONを便利に流用するのではなく、信頼境界、整合性、再試行、公開可否に応じて個別に定義する。

- HTTP Operation: **151**
- Resource Contract: **55**
- Error Code: **66**
- Job Type: **39**
- Domain Event Type: **63**
- State Machine: **10**
- JSON Schema file: **118**

### 0.1 今回解消する主要リスク

1. Public APIから編集・根拠・AI・財務データが漏れるリスク。
2. Commandを同期実行してtimeoutや二重実行が起きるリスク。
3. Queueの重複配送を「一度しか届かない」と誤解するリスク。
4. AI自由文を解釈して不正な記事・Claim・Policy判断を保存するリスク。
5. 発生成果、確定成果、推定帰属を同じFieldで扱うリスク。
6. 管理APIの更新競合により承認、公開、Kill Switchを上書きするリスク。
7. Provider APIやCSVの変更を内部Domainへ直接波及させるリスク。

### 0.2 上位設計との差分検出

`RAOS-ARCH-001`はJobのCanonical Stateを10状態で定義した一方、`RAOS-DATA-001`の`ops.job.status`は7状態に簡略化され、`FAILED_RETRYABLE`、`RETRY_SCHEDULED`、`FAILED_TERMINAL`、`EXPIRED`を区別できない。本工程では契約を上位設計へ揃え、`RAOS_04_001_contract_alignment_patch_v0.1.sql`を提案Migrationとして同梱する。CodexはこのPatchをMigration Frameworkへ移植し、既存データ変換とRollback試験を行う。

---

## 1. 目的・適用範囲

### 1.1 目的

- API ConsumerとProviderの責務を明文化する。
- HTTP、Event、Job、AI、ImportのSchema DriftをCIで検出する。
- 再試行、重複、順序入替、部分失敗に対して安全な契約を定義する。
- 要求ID、設計ID、Operation、Job、Event、Testを追跡可能にする。
- Codexが一つの巨大なCRUD APIを自動生成することを防止する。

### 1.2 対象

- `GET/POST/PATCH`を中心とするPublic/Admin/Internal API。
- OIDC/OAuth 2.0とService Principal。
- RFC 9457 Problem Details。
- Idempotency、Optimistic Concurrency、Cursor Pagination。
- Outbox経由のDomain EventとQueue Job。
- AI Structured Output、Revenue/Rank CSV canonical row。
- Contract Test、Compatibility Test、Schema Registry。

### 1.3 対象外

- 画面のVisual Design。
- SQL/ORMの完全実装。
- Provider固有CredentialやProduction URL。
- 楽天成果CSVの実ファイル列名を未検証のまま固定すること。
- GraphQL、WebSocket、一般公開Developer API。
- AIにApprovalやPublish権限を付与すること。

---

## 2. 契約原則

| 原則 | 具体化 |
| --- | --- |
| Explicit boundaries | Public/Admin/Internalを別OpenAPIへ分ける。 |
| Command/Query separation | 取得はQuery、業務変更はCommand。長時間処理はJob。 |
| Schema-first | JSON Schemaを正本とし、Pydantic/TypeScript/Fixtureを生成・検証する。 |
| Fail closed | Policy、Approval、Freshness、Security依存が不明なら公開・取込・リンク表示を止める。 |
| At-least-once safe | Job/Eventは重複、遅延、順序入替が起こる前提。 |
| Immutable facts | Event、Approval、Snapshot、Provider Factは訂正追記し上書きしない。 |
| Least privilege | Public、User、Worker、Projection、FinanceをDB/API両方で分離する。 |
| No DB row leakage | API ViewはDB列の自動Exposeではなく明示Field Allowlist。 |
| No affiliate redirect dependency | クリックBeacon失敗でも楽天への直接遷移を妨げない。 |
| No hidden AI autonomy | AI出力は候補Artifactであり、承認・公開Commandではない。 |

## 3. Standards Decision Records

| ADR | Status | Decision | Rationale |
| --- | --- | --- | --- |
| API-ADR-001 | accepted | OpenAPI 3.1.1をHTTP契約正本とし、3.2固有機能をMVPで使用しない | FastAPIと主要Codegenの互換性を優先しながらJSON Schema 2020-12を利用する。 |
| API-ADR-002 | accepted | Public、Admin、InternalのOpenAPI文書を分離する | Trust Boundary、認証、Rate Limit、公開範囲の誤混在を防ぐ。 |
| API-ADR-003 | accepted | URI major versioningとして/api/v1を使用する | 破壊的変更は/v2、新規任意Fieldはv1内で追加可能とする。 |
| API-ADR-004 | accepted | RFC 9457 Problem Detailsを唯一のHTTPエラー形式とする | 独自エラーEnvelope乱立を防ぎ、機械処理可能なcodeとviolationsを拡張する。 |
| API-ADR-005 | accepted | 重要な状態変更CommandにIdempotency-Keyを必須化する | 二重Publish、二重承認、二重成果取込、二重Job作成を防止する。 |
| API-ADR-006 | accepted | 編集可能Aggregateの更新にIf-Matchを必須化する | last-write-winsを禁止し、lock_version由来ETagで競合を検出する。 |
| API-ADR-007 | accepted | 長時間処理は202 Accepted＋JobResourceを返す | 外部API、AI、品質、公開、ImportをHTTP request lifecycleから分離する。 |
| API-ADR-008 | accepted | EventとJobを別メッセージ種別として定義する | Eventは過去事実、Jobは実行要求であり、再送・失敗・責任が異なる。 |
| API-ADR-009 | accepted | Domain Event EnvelopeはCloudEvents互換フィールドを持つ | event ID、source、type、subject、time、data schemaを標準化する。 |
| API-ADR-010 | accepted | AsyncAPI 3.0互換構文で論理Channelを記述する | 現行3.1仕様に適合しつつ、利用ツールの3.0互換性を確保する。 |
| API-ADR-011 | accepted | Event/Job/AI OutputはJSON Schema 2020-12を単独ファイルで管理する | Provider SDKやPydantic内部Schemaを外部契約正本にしない。 |
| API-ADR-012 | accepted | Cursor paginationを標準としoffset paginationを禁止する | 更新中の一覧でも重複・欠落を抑え、大規模化に耐える。 |
| API-ADR-013 | accepted | Affiliate click endpointは204を即時返し、楽天Navigationを待たせない | 計測失敗が購入導線を阻害しない。 |
| API-ADR-014 | accepted | 楽天Affiliate URLはrequest payloadに受け取らない | Catalog projectionに保存済みの公式URLを参照し、改変経路を作らない。 |
| API-ADR-015 | accepted | 公開APIはreadmodelのみを返し内部ID・原本・AI情報を露出しない | One-way public boundaryを契約で固定する。 |
| API-ADR-016 | accepted | 管理APIはOIDC Bearer Token＋RBAC scopeを使用する | Cookie認証に依存せず、操作単位の最小権限を表現する。 |
| API-ADR-017 | accepted | Internal APIはPrivate Network＋Service Identity限定とする | Scheduler等のControl Plane以外はQueueを一次経路とする。 |
| API-ADR-018 | accepted | Event/Job payloadに秘密、原本文、Affiliate URL全文を含めない | 漏えい面積、Queue制限、ログ汚染を減らす。 |
| API-ADR-019 | accepted | 大きな入力・出力はObjectArtifact参照とSHA-256で渡す | SQS等のMessage size制約と不変原本を両立する。 |
| API-ADR-020 | accepted | API responseに推定値とProvider Factのprovenanceを明示する | 成果・帰属・計測を誤認させない。 |
| API-ADR-021 | accepted | 推薦編集APIから料率・利益Fieldを除外する | 編集順位とAffiliate economicsを構造的に分離する。 |
| API-ADR-022 | accepted | CSV Uploadはpresigned upload session→scan→dry run→confirmとする | 巨大multipart、Formula Injection、重複原本、無確認Importを防ぐ。 |
| API-ADR-023 | accepted | Schema registryは互換性モードBACKWARD_TRANSITIVEを基本とする | 既存Consumerが新しいProducer Eventを処理できることを保証する。 |
| API-ADR-024 | accepted | DeprecationとSunset headerを廃止プロセスに使用する | 暗黙的なEndpoint撤去を禁止する。 |
| API-ADR-025 | accepted | traceparent、X-Request-ID、correlation_idをHTTPからJob/Eventへ伝播する | 1操作の監査・障害調査・費用配賦を連結する。 |
| API-ADR-026 | accepted | GET以外の監査対象操作はAudit Eventを同一Transactionで記録する | 通知やログだけを監査正本としない。 |
| API-ADR-027 | accepted | 公開・Affiliate Kill SwitchはCommand APIとruntime projectionの双方で強制する | 古いWeb cacheや古いJobが停止状態を上書きしない。 |
| API-ADR-028 | accepted | OpenAPIからTypeScript clientを生成し手書きHTTP clientを禁止する | UIとAPIの契約driftをCIで検知する。 |
| API-ADR-029 | accepted | Job statusを上位アーキテクチャの10状態へDB整合させる | retryable/terminal/expiredをAPIと運用で区別できるようにする。 |
| API-ADR-030 | accepted | 実装PRはOperation ID・Event type・Job type・Requirement IDをテスト名へ保持する | Codex実装のトレーサビリティを自動検査する。 |

## 4. Trust Surface

| Surface | Principal | Network | Data source | 禁止事項 |
| --- | --- | --- | --- | --- |
| Public | 匿名Browser/CDN | Internet | readmodelのみ | 編集、根拠、AI、財務、内部IDの漏えい |
| Admin | OIDC User＋MFA/RBAC | Internet＋WAF | Core APIの許可View | Service用Command、直接Queue送信、DB access |
| Internal | Workload identity | Private network | Scheduler/Worker/Projection用最小API | User token、Public origin、任意Job type |
| Event | Domain producer | Private bus | Committed fact＋Outbox | 命令形、未来予測、秘密、巨大payload |
| Job | Authorized producer | Private queue | Versioned execution request | 暗黙権限、無期限retry、自由URL |
| AI | AI orchestrator | Provider egress allowlist | Approved Source Packet | DB/Queue/Publish/Kill Switch access |
| Import | Operator＋Scanner/Parser | Object storage＋Worker | 不変原本＋canonical row | 未確認の直接commit、式注入、silent coercion |

## 5. HTTP共通契約

### 5.1 Media Type

- 通常Request/Response: `application/json`。
- Error: `application/problem+json`。
- Upload本体はPresigned Object Storageへ送信し、API bodyへBase64を載せない。
- CSV/JSONL ExportはObject Artifactとして配布し、同期Responseへ巨大データを載せない。

### 5.2 Identifier・時刻・金額

- 内部IDはUUID文字列。人間向け参照には不変`display_id`を併用する。
- 時刻はRFC 3339形式UTC。Business dateは`YYYY-MM-DD`。
- 金額は円の整数、または明示Scaleを持つDecimal。IEEE 754 floatで会計計算しない。
- Enumは安定した大文字snake caseまたは契約に明示した文字列。表示文言をEnumにしない。

### 5.3 Request headers

| Header | Required | Rule |
| --- | --- | --- |
| Authorization | Admin/Internal | AdminはOIDC Access Token、InternalはService JWT。 |
| X-Request-ID | 任意 | UUID。欠落・不正ならServer採番。 |
| traceparent | 任意 | W3C Trace Context。信頼できないtracestateは除去可。 |
| Idempotency-Key | 指定Command | 8〜200文字。Tenant/Principal/Operationとpayload hashにscope。 |
| If-Match | 競合制御Command | 直前GETのstrong ETag。`*`は特別に許可したOperation以外拒否。 |
| Content-Type | bodyあり | `application/json`。 |

### 5.4 Response headers

| Header | Rule |
| --- | --- |
| X-Request-ID | 全Response。 |
| traceparent | Trace開始済みResponse。 |
| ETag | Versioned Resource/Projection。 |
| Location | 201 Resource URL、202 Job status URL。 |
| Retry-After | 429/503/先行Idempotency処理。 |
| Deprecation | Deprecated API。日付形式。 |
| Sunset | 廃止予定API。 |
| Link | 後継API、Policy、Documentation。 |

### 5.5 Cursor Pagination

Listは`cursor`と`limit`を使用する。Offset Paginationは小規模な静的参照データ以外では禁止する。Cursorは不透明かつ署名付きとし、sort key、tie-breaker ID、filter hash、expirationを含める。ClientはCursorを解析・生成してはならない。

Responseは`items`と`page.next_cursor`、`page.has_more`、`page.limit`を持つ。並び順はOperationごとのAllowlistに固定し、必ずIDによる安定Tie-breakerを含める。

### 5.6 Idempotency

1. Command開始時にPrincipal、Site、Operation ID、Idempotency-Key、canonical payload hashを同一Transactionで予約する。
2. 同一Key＋同一Hashが完了済みなら、元Status、Response body、Locationを返す。
3. 同一Key＋異なるHashは`RAOS-IDEMP-002`。
4. 同一Keyの先行処理中は`RAOS-IDEMP-003`とRetry-After。
5. Job作成CommandはJob IDも再利用し、二重Outbox/Queue投入を防ぐ。
6. Key保持期間は外部重複再送期間・業務リスクより短くしない。

### 5.7 Optimistic Concurrency

Mutable ResourceのGETはstrong ETagを返す。PATCH/State Transitionは`If-Match`必須とし、現在Versionと一致したときだけ変更する。Bodyの`lock_version`だけに依存しない。Approval、Publication、Kill Switch、Policy activation等は専用State Machine Guardを追加する。

### 5.8 Asynchronous Command

長時間処理は`202 Accepted`と`JobAccepted`を返す。HTTP handlerはProvider呼出し、AI生成、CSV parsing、Snapshot build、Publish verificationを実行しない。Transaction内でDomain状態、Job、Outboxを記録した時点をAcceptedとする。

```json
{
  "job_id": "0198f98b-5c4e-7d1a-9a66-11bb28a2ab01",
  "display_id": "JOB-20260730-000123",
  "status": "QUEUED",
  "status_url": "/api/v1/admin/ops/jobs/0198f98b-5c4e-7d1a-9a66-11bb28a2ab01",
  "correlation_id": "0198f98b-5c4e-7d1a-9a66-11bb28a2ab02",
  "idempotency_replayed": false
}
```

## 6. Authentication・Authorization

### 6.1 Admin

- Authorization Code＋PKCEによるOIDC/OAuth 2.0。
- Tokenはissuer、audience、signature、exp、nbf、jti、required scopesを検証する。
- Kill Switch解除、Role変更、Final Approval等はMFA claimとStep-up freshnessを要求する。
- Site/Category/Article scopeはAPI GatewayのscopeだけでなくDomain Authorizationで検証する。

### 6.2 Internal

- Workload identityから発行した短命Token。User Tokenは拒否する。
- Private endpoint、egress/ingress policy、必要に応じmTLSを併用する。
- `job_type`、projection、schedule codeをProducerごとのAllowlistで制限する。

### 6.3 Public

- Authenticationなし。ただしWAF、Route別Rate Limit、body size、Bot/abuse controlsを適用する。
- Click Beaconは匿名Sessionを使い、生IPやAffiliate URLをPayloadへ含めない。

## 7. Error Contract

Error bodyはRFC 9457 Problem Detailsに安定Extensionを加える。`code`は機械判定用で翻訳しない。`detail`へSecret、Token、Provider原文、個人情報、SQLを含めない。

```json
{
  "type": "https://errors.raos.local/raos-conc-001",
  "title": "Resource version conflict",
  "status": 409,
  "detail": "Resource was changed after the supplied ETag.",
  "instance": "/api/v1/admin/articles/0198...",
  "code": "RAOS-CONC-001",
  "request_id": "0198f98b-5c4e-7d1a-9a66-11bb28a2ab03",
  "correlation_id": "0198f98b-5c4e-7d1a-9a66-11bb28a2ab02",
  "retryable": false,
  "violations": []
}
```

| Code | HTTP | Domain | Retry | Title |
| --- | --- | --- | --- | --- |
| RAOS-AUTH-001 | 401 | IAM | no | Authentication required |
| RAOS-AUTH-002 | 403 | IAM | no | Permission denied |
| RAOS-AUTH-003 | 403 | IAM | no | MFA required |
| RAOS-AUTH-004 | 403 | IAM | no | Service identity required |
| RAOS-REQ-001 | 422 | Common | no | Request validation failed |
| RAOS-REQ-002 | 400 | Common | no | Malformed request |
| RAOS-REQ-003 | 413 | Common | no | Payload too large |
| RAOS-REQ-004 | 415 | Common | no | Unsupported media type |
| RAOS-REQ-005 | 400 | Common | no | Unknown filter or sort field |
| RAOS-IDEMP-001 | 400 | Common | no | Idempotency-Key required |
| RAOS-IDEMP-002 | 409 | Common | no | Idempotency-Key payload mismatch |
| RAOS-IDEMP-003 | 409 | Common | yes | Idempotency result unavailable |
| RAOS-CONC-001 | 409 | Common | no | Resource version conflict |
| RAOS-CONC-002 | 428 | Common | no | If-Match required |
| RAOS-NOTFOUND-001 | 404 | Common | no | Resource not found |
| RAOS-STATE-001 | 409 | Common | no | Invalid state transition |
| RAOS-RATE-001 | 429 | Common | yes | Rate limit exceeded |
| RAOS-BUDGET-001 | 409 | Operations | no | Execution budget exceeded |
| RAOS-JOB-001 | 409 | Operations | no | Job is not retryable |
| RAOS-JOB-002 | 409 | Operations | no | Job is already terminal |
| RAOS-JOB-003 | 409 | Operations | yes | Job lease conflict |
| RAOS-JOB-004 | 410 | Operations | no | Job expired |
| RAOS-JOB-005 | 503 | Operations | yes | Queue unavailable |
| RAOS-PROVIDER-001 | 503 | Integration | yes | External provider temporarily unavailable |
| RAOS-PROVIDER-002 | 502 | Integration | no | External provider contract changed |
| RAOS-PROVIDER-003 | 503 | Integration | no | External provider authentication failed |
| RAOS-PROVIDER-004 | 409 | Integration | no | External provider operation disabled |
| RAOS-CAT-001 | 409 | Catalog | no | Product identity unresolved |
| RAOS-CAT-002 | 409 | Catalog | no | Grouping decision superseded |
| RAOS-CAT-003 | 422 | Catalog | no | Affiliate URL is not provider-issued |
| RAOS-CAT-004 | 409 | Catalog | yes | Offer information is stale |
| RAOS-EVD-001 | 409 | Evidence | no | Approved source packet required |
| RAOS-EVD-002 | 422 | Evidence | no | Claim has insufficient evidence |
| RAOS-EVD-003 | 409 | Evidence | yes | Source snapshot is invalid or expired |
| RAOS-EVD-004 | 422 | Evidence | no | Prohibited review content detected |
| RAOS-AI-001 | 422 | AI | yes | Structured output schema violation |
| RAOS-AI-002 | 409 | AI | no | AI task refused |
| RAOS-AI-003 | 409 | AI | no | AI source reference mismatch |
| RAOS-AI-004 | 409 | AI | no | AI cost cap exceeded |
| RAOS-POL-001 | 409 | Policy | no | Blocking policy finding exists |
| RAOS-POL-002 | 409 | Policy | no | Quality threshold not met |
| RAOS-POL-003 | 409 | Policy | no | Policy bundle not active |
| RAOS-POL-004 | 409 | Policy | no | Waiver not permitted |
| RAOS-REV-001 | 409 | Publishing | no | Human review incomplete |
| RAOS-REV-002 | 403 | Publishing | no | Self approval is not permitted |
| RAOS-PUB-001 | 409 | Publishing | no | Final approval missing or invalid |
| RAOS-PUB-002 | 409 | Publishing | yes | Publication snapshot not ready |
| RAOS-PUB-003 | 409 | Publishing | no | Canonical route conflict |
| RAOS-PUB-004 | 409 | Publishing | no | Rollback target invalid |
| RAOS-KILL-001 | 409 | Operations | no | Publication is frozen |
| RAOS-KILL-002 | 409 | Operations | no | Kill switch generation conflict |
| RAOS-KILL-003 | 403 | Operations | no | Kill switch release requires elevated approval |
| RAOS-FRESH-001 | 409 | Freshness | no | Freshness policy blocks exposure |
| RAOS-LINK-001 | 409 | Freshness | no | Affiliate link validation failed |
| RAOS-IMPORT-001 | 422 | Finance | no | Import file format invalid |
| RAOS-IMPORT-002 | 409 | Finance | no | Duplicate import detected |
| RAOS-IMPORT-003 | 409 | Finance | no | Import reconciliation mismatch |
| RAOS-IMPORT-004 | 409 | Finance | no | Dry run confirmation mismatch |
| RAOS-FIN-001 | 409 | Finance | no | Provider fact cannot be mutated |
| RAOS-FIN-002 | 422 | Finance | no | Invalid attribution provenance |
| RAOS-FIN-003 | 409 | Finance | yes | Unit economics source watermark incomplete |
| RAOS-PRIV-001 | 422 | Privacy | no | Prohibited personal data detected |
| RAOS-SEC-001 | 400 | Security | no | Unsafe URL rejected |
| RAOS-SEC-002 | 422 | Security | no | CSV formula injection detected |
| RAOS-SEC-003 | 503 | Security | no | Security control unavailable |
| RAOS-INTERNAL-001 | 500 | Common | no | Internal invariant violated |

## 8. HTTP Operation Catalog

以下のOperation定義はOpenAPIファイルの人間向け説明である。Path、Operation ID、Schema、Scope、Idempotency、Concurrency、Async Jobを変更する場合、OpenAPI、Catalog、Test、Traceabilityを同一PRで更新する。

### 8.1 Public API

| ID | Method | Path | Tag | Success | Async Job |
| --- | --- | --- | --- | --- | --- |
| PUB-001 | GET | /api/v1/public/articles/{slug} | Public | 200 | — |
| PUB-002 | GET | /api/v1/public/routes/resolve | Public | 200 | — |
| PUB-003 | GET | /api/v1/public/runtime-control | Public | 200 | — |
| PUB-004 | POST | /api/v1/events/click | Public | 204 | — |
| SYS-001 | GET | /api/v1/health/live | System | 200 | — |
| SYS-002 | GET | /api/v1/health/ready | System | 200 | — |

### PUB-001 — `GET /api/v1/public/articles/{slug}`

公開記事を取得

| 項目 | 契約 |
| --- | --- |
| Surface | public |
| Tag | Public |
| Kind | query |
| Authentication | none |
| Scopes | なし |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PublicArticleDocument |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-016 |

**受入条件**

- 公開Read Modelまたは安全な集計Projection以外のDB Entityを返さない。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`

### PUB-002 — `GET /api/v1/public/routes/resolve`

公開Routeを解決

| 項目 | 契約 |
| --- | --- |
| Surface | public |
| Tag | Public |
| Kind | query |
| Authentication | none |
| Scopes | なし |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PublicRoute |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-010 |
| Implementation Slice | SLICE-016 |

**Query parameters**: `path`

**受入条件**

- 公開Read Modelまたは安全な集計Projection以外のDB Entityを返さない。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`

### PUB-003 — `GET /api/v1/public/runtime-control`

公開制御Projectionを取得

| 項目 | 契約 |
| --- | --- |
| Surface | public |
| Tag | Public |
| Kind | query |
| Authentication | none |
| Scopes | なし |
| Success | 200 |
| Request Schema | なし |
| Response Schema | RuntimeControl |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-019 |
| Implementation Slice | SLICE-022 |

**受入条件**

- 公開Read Modelまたは安全な集計Projection以外のDB Entityを返さない。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`

### PUB-004 — `POST /api/v1/events/click`

Affiliate click beaconを記録

| 項目 | 契約 |
| --- | --- |
| Surface | public |
| Tag | Public |
| Kind | event_ingest |
| Authentication | none |
| Scopes | なし |
| Success | 204 |
| Request Schema | AffiliateClickInput |
| Response Schema | なし |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-013 |
| Implementation Slice | SLICE-017 |

**固有ルール**

- Navigation must not wait for this response.
- Affiliate URL must not be included in payload.

**受入条件**

- 公開Read Modelまたは安全な集計Projection以外のDB Entityを返さない。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-RATE-001`, `RAOS-REQ-001`

### SYS-001 — `GET /api/v1/health/live`

Livenessを取得

| 項目 | 契約 |
| --- | --- |
| Surface | public |
| Tag | System |
| Kind | query |
| Authentication | none |
| Scopes | なし |
| Success | 200 |
| Request Schema | なし |
| Response Schema | HealthStatus |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | — |
| Implementation Slice | SLICE-001 |

**受入条件**

- 公開Read Modelまたは安全な集計Projection以外のDB Entityを返さない。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`

### SYS-002 — `GET /api/v1/health/ready`

Readinessを取得

| 項目 | 契約 |
| --- | --- |
| Surface | public |
| Tag | System |
| Kind | query |
| Authentication | none |
| Scopes | なし |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ReadinessStatus |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | — |
| Implementation Slice | SLICE-002 |

**受入条件**

- 公開Read Modelまたは安全な集計Projection以外のDB Entityを返さない。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`

### 8.2 Admin API

| ID | Method | Path | Tag | Success | Async Job |
| --- | --- | --- | --- | --- | --- |
| IAM-001 | GET | /api/v1/admin/me | IAM | 200 | — |
| IAM-002 | GET | /api/v1/admin/roles | IAM | 200 | — |
| IAM-003 | GET | /api/v1/admin/permissions | IAM | 200 | — |
| IAM-004 | POST | /api/v1/admin/session-revocations | IAM | 201 | — |
| SITE-001 | GET | /api/v1/admin/sites | Portfolio | 200 | — |
| SITE-002 | POST | /api/v1/admin/sites | Portfolio | 201 | — |
| SITE-003 | GET | /api/v1/admin/sites/{id} | Portfolio | 200 | — |
| SITE-004 | PATCH | /api/v1/admin/sites/{id} | Portfolio | 200 | — |
| CATG-001 | GET | /api/v1/admin/categories | Portfolio | 200 | — |
| CATG-002 | POST | /api/v1/admin/categories | Portfolio | 201 | — |
| CATG-003 | GET | /api/v1/admin/categories/{id} | Portfolio | 200 | — |
| CATG-004 | PATCH | /api/v1/admin/categories/{id} | Portfolio | 200 | — |
| INTENT-001 | GET | /api/v1/admin/intent-clusters | Portfolio | 200 | — |
| INTENT-002 | POST | /api/v1/admin/intent-clusters | Portfolio | 201 | — |
| INTENT-003 | GET | /api/v1/admin/intent-clusters/{id} | Portfolio | 200 | — |
| INTENT-004 | PATCH | /api/v1/admin/intent-clusters/{id} | Portfolio | 200 | — |
| KEY-001 | GET | /api/v1/admin/keywords | Portfolio | 200 | — |
| KEY-002 | POST | /api/v1/admin/keywords | Portfolio | 201 | — |
| KEY-003 | GET | /api/v1/admin/keywords/{id} | Portfolio | 200 | — |
| KEY-004 | PATCH | /api/v1/admin/keywords/{id} | Portfolio | 200 | — |
| PORT-001 | GET | /api/v1/admin/opportunity-assessments | Portfolio | 200 | — |
| PORT-002 | POST | /api/v1/admin/opportunity-assessments | Portfolio | 202 | portfolio.assess_opportunity.v1 |
| PORT-003 | GET | /api/v1/admin/action-candidates | Portfolio | 200 | — |
| PORT-004 | POST | /api/v1/admin/action-candidates/{id}/decision | Portfolio | 200 | — |
| CAT-001 | GET | /api/v1/admin/catalog/ingestions | Catalog | 200 | — |
| CAT-002 | POST | /api/v1/admin/catalog/ingestions | Catalog | 202 | catalog.rakuten_item_search.v1 |
| CAT-003 | GET | /api/v1/admin/catalog/ingestions/{id} | Catalog | 200 | — |
| CAT-004 | GET | /api/v1/admin/catalog/product-candidates | Catalog | 200 | — |
| CAT-005 | GET | /api/v1/admin/catalog/product-candidates/{id} | Catalog | 200 | — |
| CAT-006 | POST | /api/v1/admin/catalog/grouping-decisions | Catalog | 201 | — |
| CAT-007 | GET | /api/v1/admin/catalog/products | Catalog | 200 | — |
| CAT-008 | POST | /api/v1/admin/catalog/products | Catalog | 201 | — |
| CAT-009 | GET | /api/v1/admin/catalog/products/{id} | Catalog | 200 | — |
| CAT-010 | PATCH | /api/v1/admin/catalog/products/{id} | Catalog | 200 | — |
| CAT-011 | GET | /api/v1/admin/catalog/offers | Catalog | 200 | — |
| CAT-012 | GET | /api/v1/admin/catalog/offers/{id} | Catalog | 200 | — |
| CAT-013 | POST | /api/v1/admin/catalog/offers/refresh | Catalog | 202 | catalog.refresh_offer.v1 |
| EVD-001 | GET | /api/v1/admin/evidence/sources | Evidence | 200 | — |
| EVD-002 | POST | /api/v1/admin/evidence/sources | Evidence | 201 | — |
| EVD-003 | GET | /api/v1/admin/evidence/sources/{id} | Evidence | 200 | — |
| EVD-004 | PATCH | /api/v1/admin/evidence/sources/{id} | Evidence | 200 | — |
| EVD-005 | POST | /api/v1/admin/evidence/source-snapshots/capture | Evidence | 202 | evidence.capture_source_snapshot.v1 |
| EVD-006 | GET | /api/v1/admin/evidence/source-snapshots | Evidence | 200 | — |
| EVD-007 | GET | /api/v1/admin/evidence/facts | Evidence | 200 | — |
| EVD-008 | POST | /api/v1/admin/evidence/facts | Evidence | 201 | — |
| EVD-009 | GET | /api/v1/admin/evidence/source-packets | Evidence | 200 | — |
| EVD-010 | POST | /api/v1/admin/evidence/source-packets/build | Evidence | 202 | evidence.build_source_packet.v1 |
| EVD-011 | GET | /api/v1/admin/evidence/source-packets/{id} | Evidence | 200 | — |
| EVD-012 | GET | /api/v1/admin/evidence/source-packet-versions/{id} | Evidence | 200 | — |
| EVD-013 | POST | /api/v1/admin/evidence/source-packet-versions/{id}/decision | Evidence | 200 | — |
| EVD-014 | GET | /api/v1/admin/evidence/claims | Evidence | 200 | — |
| ED-001 | GET | /api/v1/admin/article-plans | Editorial | 200 | — |
| ED-002 | POST | /api/v1/admin/article-plans | Editorial | 201 | — |
| ED-003 | GET | /api/v1/admin/article-plans/{id} | Editorial | 200 | — |
| ED-004 | PATCH | /api/v1/admin/article-plans/{id} | Editorial | 200 | — |
| ED-005 | POST | /api/v1/admin/article-plans/{id}/articles | Editorial | 201 | — |
| ED-006 | GET | /api/v1/admin/articles | Editorial | 200 | — |
| ED-007 | GET | /api/v1/admin/articles/{id} | Editorial | 200 | — |
| ED-008 | PATCH | /api/v1/admin/articles/{id} | Editorial | 200 | — |
| ED-009 | POST | /api/v1/admin/articles/{id}/versions | Editorial | 201 | — |
| ED-010 | GET | /api/v1/admin/article-versions/{id} | Editorial | 200 | — |
| ED-011 | PATCH | /api/v1/admin/article-versions/{id} | Editorial | 200 | — |
| ED-012 | POST | /api/v1/admin/article-plans/{id}/generate-draft | Editorial | 202 | ai.generate_article_draft.v1 |
| ED-013 | GET | /api/v1/admin/article-versions/{id}/comments | Editorial | 200 | — |
| ED-014 | POST | /api/v1/admin/article-versions/{id}/comments | Editorial | 201 | — |
| ED-015 | POST | /api/v1/admin/articles/{id}/links | Editorial | 201 | — |
| AI-001 | GET | /api/v1/admin/ai/jobs | AI | 200 | — |
| AI-002 | POST | /api/v1/admin/ai/jobs | AI | 202 | ai.generic_task.v1 |
| AI-003 | GET | /api/v1/admin/ai/jobs/{id} | AI | 200 | — |
| AI-004 | POST | /api/v1/admin/ai/jobs/{id}/cancel | AI | 200 | — |
| AI-005 | GET | /api/v1/admin/ai/prompt-versions | AI | 200 | — |
| AI-006 | GET | /api/v1/admin/ai/model-routes | AI | 200 | — |
| AI-007 | GET | /api/v1/admin/ai/evaluation-results | AI | 200 | — |
| AI-008 | POST | /api/v1/admin/ai/evaluations | AI | 202 | ai.evaluate_output.v1 |
| QLT-001 | GET | /api/v1/admin/quality/runs | Quality | 200 | — |
| QLT-002 | POST | /api/v1/admin/quality/runs | Quality | 202 | quality.evaluate_article.v1 |
| QLT-003 | GET | /api/v1/admin/quality/runs/{id} | Quality | 200 | — |
| QLT-004 | GET | /api/v1/admin/quality/findings | Quality | 200 | — |
| QLT-005 | GET | /api/v1/admin/quality/findings/{id} | Quality | 200 | — |
| QLT-006 | POST | /api/v1/admin/quality/findings/{id}/resolution | Quality | 200 | — |
| QLT-007 | POST | /api/v1/admin/quality/waivers | Quality | 201 | — |
| POL-001 | GET | /api/v1/admin/policy/bundles | Policy | 200 | — |
| POL-002 | POST | /api/v1/admin/policy/bundles | Policy | 201 | — |
| POL-003 | POST | /api/v1/admin/policy/bundles/{id}/activate | Policy | 200 | — |
| POL-004 | GET | /api/v1/admin/policy/gate-decisions | Policy | 200 | — |
| POL-005 | POST | /api/v1/admin/policy/gate-decisions | Policy | 201 | — |
| PUBADM-001 | GET | /api/v1/admin/review-assignments | Publishing | 200 | — |
| PUBADM-002 | POST | /api/v1/admin/review-assignments | Publishing | 201 | — |
| PUBADM-003 | PATCH | /api/v1/admin/review-assignments/{id} | Publishing | 200 | — |
| PUBADM-004 | POST | /api/v1/admin/review-decisions | Publishing | 201 | — |
| PUBADM-005 | POST | /api/v1/admin/approvals | Publishing | 201 | — |
| PUBADM-006 | POST | /api/v1/admin/approvals/{id}/revoke | Publishing | 201 | — |
| PUBADM-007 | POST | /api/v1/admin/publication-candidates | Publishing | 202 | publishing.build_snapshot.v1 |
| PUBADM-008 | GET | /api/v1/admin/publication-candidates/{id} | Publishing | 200 | — |
| PUBADM-009 | POST | /api/v1/admin/publication-candidates/{id}/publish | Publishing | 202 | publishing.publish_snapshot.v1 |
| PUBADM-010 | GET | /api/v1/admin/publications | Publishing | 200 | — |
| PUBADM-011 | GET | /api/v1/admin/publications/{id} | Publishing | 200 | — |
| PUBADM-012 | POST | /api/v1/admin/publications/{id}/rollback | Publishing | 202 | publishing.rollback.v1 |
| PUBADM-013 | POST | /api/v1/admin/publications/{id}/unpublish | Publishing | 202 | publishing.unpublish.v1 |
| PUBADM-014 | GET | /api/v1/admin/publication-snapshots/{id} | Publishing | 200 | — |
| FRSH-001 | GET | /api/v1/admin/freshness/policies | Freshness | 200 | — |
| FRSH-002 | POST | /api/v1/admin/freshness/policies | Freshness | 201 | — |
| FRSH-003 | POST | /api/v1/admin/freshness/refresh-runs | Freshness | 202 | freshness.run_refresh_batch.v1 |
| FRSH-004 | GET | /api/v1/admin/freshness/refresh-runs/{id} | Freshness | 200 | — |
| FRSH-005 | GET | /api/v1/admin/freshness/staleness-assessments | Freshness | 200 | — |
| FRSH-006 | POST | /api/v1/admin/freshness/link-checks | Freshness | 202 | freshness.check_affiliate_link.v1 |
| FRSH-007 | GET | /api/v1/admin/freshness/link-checks | Freshness | 200 | — |
| FRSH-008 | POST | /api/v1/admin/freshness/impact-assessments | Freshness | 202 | freshness.assess_change_impact.v1 |
| FRSH-009 | GET | /api/v1/admin/freshness/impact-assessments | Freshness | 200 | — |
| AN-001 | POST | /api/v1/admin/analytics/imports | Analytics | 202 | analytics.import_provider_data.v1 |
| AN-002 | GET | /api/v1/admin/analytics/imports | Analytics | 200 | — |
| AN-003 | GET | /api/v1/admin/analytics/imports/{id} | Analytics | 200 | — |
| AN-004 | GET | /api/v1/admin/analytics/articles/{article_id}/daily-metrics | Analytics | 200 | — |
| AN-005 | GET | /api/v1/admin/analytics/click-summary | Analytics | 200 | — |
| AN-006 | GET | /api/v1/admin/analytics/data-quality-findings | Analytics | 200 | — |
| FIN-001 | POST | /api/v1/admin/uploads | Finance | 201 | — |
| FIN-002 | POST | /api/v1/admin/finance/revenue-imports | Finance | 201 | — |
| FIN-003 | GET | /api/v1/admin/finance/revenue-imports | Finance | 200 | — |
| FIN-004 | GET | /api/v1/admin/finance/revenue-imports/{id} | Finance | 200 | — |
| FIN-005 | POST | /api/v1/admin/finance/revenue-imports/{id}/dry-run | Finance | 202 | finance.parse_revenue_csv.v1 |
| FIN-006 | POST | /api/v1/admin/finance/revenue-imports/{id}/confirm | Finance | 202 | finance.commit_revenue_import.v1 |
| FIN-007 | GET | /api/v1/admin/finance/commissions | Finance | 200 | — |
| FIN-008 | GET | /api/v1/admin/finance/unit-economics | Finance | 200 | — |
| FIN-009 | POST | /api/v1/admin/finance/external-costs | Finance | 201 | — |
| FIN-010 | GET | /api/v1/admin/finance/external-costs | Finance | 200 | — |
| FIN-011 | POST | /api/v1/admin/finance/human-work-logs | Finance | 201 | — |
| FIN-012 | GET | /api/v1/admin/finance/human-work-logs | Finance | 200 | — |
| OPS-001 | GET | /api/v1/admin/ops/jobs | Operations | 200 | — |
| OPS-002 | GET | /api/v1/admin/ops/jobs/{id} | Operations | 200 | — |
| OPS-003 | POST | /api/v1/admin/ops/jobs/{id}/retry | Operations | 202 | — |
| OPS-004 | POST | /api/v1/admin/ops/jobs/{id}/cancel | Operations | 200 | — |
| OPS-005 | GET | /api/v1/admin/ops/kill-switches | Operations | 200 | — |
| OPS-006 | POST | /api/v1/admin/ops/kill-switch-changes | Operations | 201 | — |
| OPS-007 | GET | /api/v1/admin/ops/incidents | Operations | 200 | — |
| OPS-008 | POST | /api/v1/admin/ops/incidents | Operations | 201 | — |
| OPS-009 | GET | /api/v1/admin/ops/incidents/{id} | Operations | 200 | — |
| OPS-010 | PATCH | /api/v1/admin/ops/incidents/{id} | Operations | 200 | — |
| OPS-011 | POST | /api/v1/admin/ops/incidents/{id}/events | Operations | 201 | — |
| OPS-012 | GET | /api/v1/admin/ops/audit-events | Operations | 200 | — |
| OPS-013 | POST | /api/v1/admin/ops/audit-exports | Operations | 202 | ops.export_audit.v1 |
| OPS-014 | GET | /api/v1/admin/ops/alerts | Operations | 200 | — |

#### AI

### AI-001 — `GET /api/v1/admin/ai/jobs`

AI Job一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | query |
| Authentication | admin |
| Scopes | ai:job:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AIJobList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**Query parameters**: `status`, `task_code`, `article_id`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AI-002 — `POST /api/v1/admin/ai/jobs`

AI Jobを明示要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | async_command |
| Authentication | admin |
| Scopes | ai:job:write |
| Success | 202 |
| Request Schema | AIJobRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | ai.generic_task.v1 |
| Audit Action | ai_job_request |
| Requirements | FR-006, FR-018 |
| Implementation Slice | SLICE-011 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`ai.generic_task.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### AI-003 — `GET /api/v1/admin/ai/jobs/{id}`

AI Job詳細を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | query |
| Authentication | admin |
| Scopes | ai:job:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AIJobDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AI-004 — `POST /api/v1/admin/ai/jobs/{id}/cancel`

AI Jobを取消要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | command |
| Authentication | admin |
| Scopes | ai:job:cancel |
| Success | 200 |
| Request Schema | JobCancelRequest |
| Response Schema | Job |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | ai_job_cancel |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### AI-005 — `GET /api/v1/admin/ai/prompt-versions`

Prompt Version一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | query |
| Authentication | admin |
| Scopes | ai:config:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PromptVersionList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AI-006 — `GET /api/v1/admin/ai/model-routes`

Model Route一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | query |
| Authentication | admin |
| Scopes | ai:config:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ModelRouteVersionList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AI-007 — `GET /api/v1/admin/ai/evaluation-results`

AI評価結果一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | query |
| Authentication | admin |
| Scopes | ai:evaluation:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | EvaluationResultList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AI-008 — `POST /api/v1/admin/ai/evaluations`

AI Evaluation Suite実行Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | AI |
| Kind | async_command |
| Authentication | admin |
| Scopes | ai:evaluation:run |
| Success | 202 |
| Request Schema | AIEvaluationRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | ai.evaluate_output.v1 |
| Audit Action | ai_evaluation_request |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`ai.evaluate_output.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

#### Analytics

### AN-001 — `POST /api/v1/admin/analytics/imports`

Analytics Import Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Analytics |
| Kind | async_command |
| Authentication | admin |
| Scopes | analytics:import:write |
| Success | 202 |
| Request Schema | AnalyticsImportRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | analytics.import_provider_data.v1 |
| Audit Action | analytics_import_request |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`analytics.import_provider_data.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### AN-002 — `GET /api/v1/admin/analytics/imports`

Analytics Import Run一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Analytics |
| Kind | query |
| Authentication | admin |
| Scopes | analytics:import:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AnalyticsImportRunList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**Query parameters**: `source_type`, `status`, `date_from`, `date_to`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AN-003 — `GET /api/v1/admin/analytics/imports/{id}`

Analytics Import Runを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Analytics |
| Kind | query |
| Authentication | admin |
| Scopes | analytics:import:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AnalyticsImportRun |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AN-004 — `GET /api/v1/admin/analytics/articles/{article_id}/daily-metrics`

Article日次指標を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Analytics |
| Kind | query |
| Authentication | admin |
| Scopes | analytics:metric:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | DailyArticleMetricList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-013, FR-015 |
| Implementation Slice | SLICE-021 |

**Query parameters**: `date_from`, `date_to`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AN-005 — `GET /api/v1/admin/analytics/click-summary`

Affiliate Click集計を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Analytics |
| Kind | query |
| Authentication | admin |
| Scopes | analytics:click:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ClickSummary |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-013 |
| Implementation Slice | SLICE-021 |

**Query parameters**: `site_id`, `article_id`, `date_from`, `date_to`, `group_by`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### AN-006 — `GET /api/v1/admin/analytics/data-quality-findings`

Analytics DQ Finding一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Analytics |
| Kind | query |
| Authentication | admin |
| Scopes | analytics:dq:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AnalyticsDQFindingList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-013 |
| Implementation Slice | SLICE-021 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

#### Catalog

### CAT-001 — `GET /api/v1/admin/catalog/ingestions`

取込要求一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:ingestion:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | IngestionRequestList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-002 |
| Implementation Slice | SLICE-008 |

**Query parameters**: `status`, `operation`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-002 — `POST /api/v1/admin/catalog/ingestions`

楽天取込Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | async_command |
| Authentication | admin |
| Scopes | catalog:ingestion:write |
| Success | 202 |
| Request Schema | RakutenIngestionRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | catalog.rakuten_item_search.v1 |
| Audit Action | catalog_ingestion_request |
| Requirements | FR-002, FR-004 |
| Implementation Slice | SLICE-008 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`catalog.rakuten_item_search.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### CAT-003 — `GET /api/v1/admin/catalog/ingestions/{id}`

取込要求を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:ingestion:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | IngestionRequest |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-002 |
| Implementation Slice | SLICE-008 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-004 — `GET /api/v1/admin/catalog/product-candidates`

商品候補一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:candidate:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ProductCandidateList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**Query parameters**: `listing_status`, `shop_id`, `unresolved_only`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-005 — `GET /api/v1/admin/catalog/product-candidates/{id}`

商品候補を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:candidate:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ProductCandidate |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-006 — `POST /api/v1/admin/catalog/grouping-decisions`

商品Grouping判断を記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | command |
| Authentication | admin |
| Scopes | catalog:grouping:decide |
| Success | 201 |
| Request Schema | GroupingDecisionRequest |
| Response Schema | GroupingDecision |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | grouping_decision_record |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### CAT-007 — `GET /api/v1/admin/catalog/products`

Canonical Product一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:product:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | CanonicalProductList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**Query parameters**: `category_id`, `lifecycle_status`, `brand_name`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-008 — `POST /api/v1/admin/catalog/products`

Canonical Productを手動作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | command |
| Authentication | admin |
| Scopes | catalog:product:write |
| Success | 201 |
| Request Schema | CanonicalProductCreateRequest |
| Response Schema | CanonicalProduct |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | canonical_product_create |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### CAT-009 — `GET /api/v1/admin/catalog/products/{id}`

Canonical Productを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:product:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | CanonicalProduct |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-010 — `PATCH /api/v1/admin/catalog/products/{id}`

Canonical Productを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | command |
| Authentication | admin |
| Scopes | catalog:product:write |
| Success | 200 |
| Request Schema | CanonicalProductUpdateRequest |
| Response Schema | CanonicalProduct |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | canonical_product_update |
| Requirements | FR-003, FR-004 |
| Implementation Slice | SLICE-009 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### CAT-011 — `GET /api/v1/admin/catalog/offers`

Offer一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:offer:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | OfferList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-004, FR-011, FR-012 |
| Implementation Slice | SLICE-009 |

**Query parameters**: `product_id`, `shop_id`, `status`, `freshness_status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-012 — `GET /api/v1/admin/catalog/offers/{id}`

Offerと安全なCurrent Projectionを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | query |
| Authentication | admin |
| Scopes | catalog:offer:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | OfferDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-004, FR-011, FR-012 |
| Implementation Slice | SLICE-009 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CAT-013 — `POST /api/v1/admin/catalog/offers/refresh`

Offer情報更新Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Catalog |
| Kind | async_command |
| Authentication | admin |
| Scopes | catalog:offer:refresh |
| Success | 202 |
| Request Schema | OfferRefreshRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | catalog.refresh_offer.v1 |
| Audit Action | offer_refresh_request |
| Requirements | FR-011, FR-012 |
| Implementation Slice | SLICE-018 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`catalog.refresh_offer.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

#### Editorial

### ED-001 — `GET /api/v1/admin/article-plans`

Article Plan一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | query |
| Authentication | admin |
| Scopes | editorial:plan:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ArticlePlanList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**Query parameters**: `site_id`, `category_id`, `status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### ED-002 — `POST /api/v1/admin/article-plans`

Article Planを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:plan:write |
| Success | 201 |
| Request Schema | ArticlePlanCreateRequest |
| Response Schema | ArticlePlan |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | article_plan_create |
| Requirements | FR-001, FR-005 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### ED-003 — `GET /api/v1/admin/article-plans/{id}`

Article Planを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | query |
| Authentication | admin |
| Scopes | editorial:plan:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ArticlePlan |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### ED-004 — `PATCH /api/v1/admin/article-plans/{id}`

Article Planを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:plan:write |
| Success | 200 |
| Request Schema | ArticlePlanUpdateRequest |
| Response Schema | ArticlePlan |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | article_plan_update |
| Requirements | FR-001, FR-005 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### ED-005 — `POST /api/v1/admin/article-plans/{id}/articles`

PlanからArticleを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:article:write |
| Success | 201 |
| Request Schema | ArticleCreateFromPlanRequest |
| Response Schema | Article |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | article_create |
| Requirements | FR-001 |
| Implementation Slice | SLICE-012 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### ED-006 — `GET /api/v1/admin/articles`

Article一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | query |
| Authentication | admin |
| Scopes | editorial:article:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ArticleList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-012 |

**Query parameters**: `site_id`, `category_id`, `status`, `article_type`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### ED-007 — `GET /api/v1/admin/articles/{id}`

Articleを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | query |
| Authentication | admin |
| Scopes | editorial:article:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ArticleDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001, FR-007 |
| Implementation Slice | SLICE-012 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### ED-008 — `PATCH /api/v1/admin/articles/{id}`

Article状態を更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:article:write |
| Success | 200 |
| Request Schema | ArticleUpdateRequest |
| Response Schema | Article |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | article_update |
| Requirements | FR-001 |
| Implementation Slice | SLICE-012 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### ED-009 — `POST /api/v1/admin/articles/{id}/versions`

Article Versionを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:version:write |
| Success | 201 |
| Request Schema | ArticleVersionCreateRequest |
| Response Schema | ArticleVersion |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | article_version_create |
| Requirements | FR-007 |
| Implementation Slice | SLICE-012 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### ED-010 — `GET /api/v1/admin/article-versions/{id}`

Article VersionとASTを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | query |
| Authentication | admin |
| Scopes | editorial:version:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ArticleVersionDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-007, FR-008 |
| Implementation Slice | SLICE-012 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### ED-011 — `PATCH /api/v1/admin/article-versions/{id}`

Article VersionとASTを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:version:write |
| Success | 200 |
| Request Schema | ArticleVersionPatchRequest |
| Response Schema | ArticleVersionDetail |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | article_version_update |
| Requirements | FR-007, FR-008 |
| Implementation Slice | SLICE-012 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### ED-012 — `POST /api/v1/admin/article-plans/{id}/generate-draft`

AI Draft生成Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | async_command |
| Authentication | admin |
| Scopes | editorial:draft:generate |
| Success | 202 |
| Request Schema | GenerateDraftRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | ai.generate_article_draft.v1 |
| Audit Action | draft_generation_request |
| Requirements | FR-006, FR-007, FR-018 |
| Implementation Slice | SLICE-012 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`ai.generate_article_draft.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### ED-013 — `GET /api/v1/admin/article-versions/{id}/comments`

Review Comment一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | query |
| Authentication | admin |
| Scopes | editorial:comment:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ReviewCommentList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### ED-014 — `POST /api/v1/admin/article-versions/{id}/comments`

Review Commentを追加

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:comment:write |
| Success | 201 |
| Request Schema | ReviewCommentCreateRequest |
| Response Schema | ReviewComment |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | review_comment_create |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### ED-015 — `POST /api/v1/admin/articles/{id}/links`

内部リンク候補を登録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Editorial |
| Kind | command |
| Authentication | admin |
| Scopes | editorial:link:write |
| Success | 201 |
| Request Schema | ArticleLinkCreateRequest |
| Response Schema | GenericResource |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | article_link_create |
| Requirements | FR-016 |
| Implementation Slice | SLICE-021 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

#### Evidence

### EVD-001 — `GET /api/v1/admin/evidence/sources`

Source一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:source:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | SourceList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**Query parameters**: `source_type`, `status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-002 — `POST /api/v1/admin/evidence/sources`

Sourceを登録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | command |
| Authentication | admin |
| Scopes | evidence:source:write |
| Success | 201 |
| Request Schema | SourceCreateRequest |
| Response Schema | Source |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | source_create |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### EVD-003 — `GET /api/v1/admin/evidence/sources/{id}`

Sourceを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:source:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | Source |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-004 — `PATCH /api/v1/admin/evidence/sources/{id}`

Sourceを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | command |
| Authentication | admin |
| Scopes | evidence:source:write |
| Success | 200 |
| Request Schema | SourceUpdateRequest |
| Response Schema | Source |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | source_update |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### EVD-005 — `POST /api/v1/admin/evidence/source-snapshots/capture`

Source Snapshot取得Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | async_command |
| Authentication | admin |
| Scopes | evidence:snapshot:capture |
| Success | 202 |
| Request Schema | CaptureSourceSnapshotRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | evidence.capture_source_snapshot.v1 |
| Audit Action | source_snapshot_capture_request |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`evidence.capture_source_snapshot.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### EVD-006 — `GET /api/v1/admin/evidence/source-snapshots`

Source Snapshot一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:snapshot:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | SourceSnapshotList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**Query parameters**: `source_id`, `validation_status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-007 — `GET /api/v1/admin/evidence/facts`

Fact一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:fact:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | FactList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-004, FR-007 |
| Implementation Slice | SLICE-010 |

**Query parameters**: `subject_type`, `subject_id`, `predicate`, `valid_at`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-008 — `POST /api/v1/admin/evidence/facts`

手動検証Factを記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | command |
| Authentication | admin |
| Scopes | evidence:fact:write |
| Success | 201 |
| Request Schema | FactCreateRequest |
| Response Schema | Fact |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | fact_create |
| Requirements | FR-004, FR-007 |
| Implementation Slice | SLICE-010 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### EVD-009 — `GET /api/v1/admin/evidence/source-packets`

Source Packet一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:packet:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | SourcePacketList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-006 |
| Implementation Slice | SLICE-010 |

**Query parameters**: `article_plan_id`, `status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-010 — `POST /api/v1/admin/evidence/source-packets/build`

Source Packet構築Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | async_command |
| Authentication | admin |
| Scopes | evidence:packet:write |
| Success | 202 |
| Request Schema | SourcePacketBuildRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | evidence.build_source_packet.v1 |
| Audit Action | source_packet_build_request |
| Requirements | FR-006, FR-007 |
| Implementation Slice | SLICE-010 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`evidence.build_source_packet.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### EVD-011 — `GET /api/v1/admin/evidence/source-packets/{id}`

Source Packetを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:packet:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | SourcePacketDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-006, FR-007 |
| Implementation Slice | SLICE-010 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-012 — `GET /api/v1/admin/evidence/source-packet-versions/{id}`

Source Packet Versionを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:packet:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | SourcePacketVersion |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-006, FR-007 |
| Implementation Slice | SLICE-010 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### EVD-013 — `POST /api/v1/admin/evidence/source-packet-versions/{id}/decision`

Source Packet Versionを承認または拒否

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | command |
| Authentication | admin |
| Scopes | evidence:packet:approve |
| Success | 200 |
| Request Schema | SourcePacketDecisionRequest |
| Response Schema | SourcePacketVersion |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | source_packet_decision |
| Requirements | FR-006 |
| Implementation Slice | SLICE-010 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### EVD-014 — `GET /api/v1/admin/evidence/claims`

Claimと根拠状態を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Evidence |
| Kind | query |
| Authentication | admin |
| Scopes | evidence:claim:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ClaimList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-007, FR-008 |
| Implementation Slice | SLICE-013 |

**Query parameters**: `article_version_id`, `support_status`, `criticality`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

#### Finance

### FIN-001 — `POST /api/v1/admin/uploads`

Upload Sessionを発行

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | command |
| Authentication | admin |
| Scopes | artifact:upload |
| Success | 201 |
| Request Schema | UploadSessionRequest |
| Response Schema | UploadSession |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | upload_session_create |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### FIN-002 — `POST /api/v1/admin/finance/revenue-imports`

Revenue Importを登録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | command |
| Authentication | admin |
| Scopes | finance:revenue:write |
| Success | 201 |
| Request Schema | RevenueImportRequest |
| Response Schema | RevenueImport |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | revenue_import_create |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### FIN-003 — `GET /api/v1/admin/finance/revenue-imports`

Revenue Import一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | query |
| Authentication | admin |
| Scopes | finance:revenue:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | RevenueImportList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**Query parameters**: `status`, `period_from`, `period_to`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FIN-004 — `GET /api/v1/admin/finance/revenue-imports/{id}`

Revenue Importを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | query |
| Authentication | admin |
| Scopes | finance:revenue:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | RevenueImportDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FIN-005 — `POST /api/v1/admin/finance/revenue-imports/{id}/dry-run`

Revenue Import Dry Runを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | async_command |
| Authentication | admin |
| Scopes | finance:revenue:write |
| Success | 202 |
| Request Schema | なし |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | finance.parse_revenue_csv.v1 |
| Audit Action | revenue_import_dry_run |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- 同期処理を実行せず、`finance.parse_revenue_csv.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`, `RAOS-JOB-005`

### FIN-006 — `POST /api/v1/admin/finance/revenue-imports/{id}/confirm`

検証済みRevenue Importを確定

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | async_command |
| Authentication | admin |
| Scopes | finance:revenue:confirm |
| Success | 202 |
| Request Schema | RevenueImportConfirmRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | finance.commit_revenue_import.v1 |
| Audit Action | revenue_import_confirm |
| Requirements | FR-014, FR-020 |
| Implementation Slice | SLICE-020 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- 同期処理を実行せず、`finance.commit_revenue_import.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`, `RAOS-JOB-005`

### FIN-007 — `GET /api/v1/admin/finance/commissions`

Commission一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | query |
| Authentication | admin |
| Scopes | finance:commission:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | CommissionList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**Query parameters**: `status`, `business_month`, `provider_code`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FIN-008 — `GET /api/v1/admin/finance/unit-economics`

確定Unit Economicsを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | query |
| Authentication | admin |
| Scopes | finance:economics:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | UnitEconomicsSnapshotList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-015 |
| Implementation Slice | SLICE-021 |

**Query parameters**: `scope_type`, `scope_id`, `period_from`, `period_to`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FIN-009 — `POST /api/v1/admin/finance/external-costs`

外部変動費を記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | command |
| Authentication | admin |
| Scopes | finance:cost:write |
| Success | 201 |
| Request Schema | ExternalCostCreateRequest |
| Response Schema | ExternalCost |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | external_cost_create |
| Requirements | FR-015, FR-018 |
| Implementation Slice | SLICE-020 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### FIN-010 — `GET /api/v1/admin/finance/external-costs`

外部費用一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | query |
| Authentication | admin |
| Scopes | finance:cost:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ExternalCostList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-015, FR-018 |
| Implementation Slice | SLICE-020 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FIN-011 — `POST /api/v1/admin/finance/human-work-logs`

人作業時間を記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | command |
| Authentication | admin |
| Scopes | finance:labor:write |
| Success | 201 |
| Request Schema | HumanWorkLogCreateRequest |
| Response Schema | HumanWorkLog |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | human_work_log_create |
| Requirements | FR-015 |
| Implementation Slice | SLICE-020 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### FIN-012 — `GET /api/v1/admin/finance/human-work-logs`

人作業時間一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Finance |
| Kind | query |
| Authentication | admin |
| Scopes | finance:labor:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | HumanWorkLogList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-015 |
| Implementation Slice | SLICE-020 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

#### Freshness

### FRSH-001 — `GET /api/v1/admin/freshness/policies`

Freshness Policy一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | query |
| Authentication | admin |
| Scopes | freshness:policy:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | FreshnessPolicyList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-012 |
| Implementation Slice | SLICE-018 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FRSH-002 — `POST /api/v1/admin/freshness/policies`

Freshness Policy Versionを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | command |
| Authentication | admin |
| Scopes | freshness:policy:write |
| Success | 201 |
| Request Schema | FreshnessPolicyRequest |
| Response Schema | FreshnessPolicy |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | freshness_policy_create |
| Requirements | FR-012 |
| Implementation Slice | SLICE-018 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### FRSH-003 — `POST /api/v1/admin/freshness/refresh-runs`

Refresh Runを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | async_command |
| Authentication | admin |
| Scopes | freshness:refresh:run |
| Success | 202 |
| Request Schema | RefreshRunRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | freshness.run_refresh_batch.v1 |
| Audit Action | refresh_run_request |
| Requirements | FR-011, FR-012 |
| Implementation Slice | SLICE-018 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`freshness.run_refresh_batch.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### FRSH-004 — `GET /api/v1/admin/freshness/refresh-runs/{id}`

Refresh Runを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | query |
| Authentication | admin |
| Scopes | freshness:refresh:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | RefreshRun |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-012 |
| Implementation Slice | SLICE-018 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FRSH-005 — `GET /api/v1/admin/freshness/staleness-assessments`

Staleness Assessment一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | query |
| Authentication | admin |
| Scopes | freshness:assessment:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | StalenessAssessmentList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-012 |
| Implementation Slice | SLICE-018 |

**Query parameters**: `target_type`, `target_id`, `freshness_status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FRSH-006 — `POST /api/v1/admin/freshness/link-checks`

Affiliate Link Checkを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | async_command |
| Authentication | admin |
| Scopes | freshness:link:check |
| Success | 202 |
| Request Schema | LinkCheckRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | freshness.check_affiliate_link.v1 |
| Audit Action | link_check_request |
| Requirements | FR-011 |
| Implementation Slice | SLICE-018 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`freshness.check_affiliate_link.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### FRSH-007 — `GET /api/v1/admin/freshness/link-checks`

Link Check一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | query |
| Authentication | admin |
| Scopes | freshness:link:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | LinkCheckList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-011 |
| Implementation Slice | SLICE-018 |

**Query parameters**: `offer_id`, `result`, `risk_code`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### FRSH-008 — `POST /api/v1/admin/freshness/impact-assessments`

Change Impact Assessmentを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | async_command |
| Authentication | admin |
| Scopes | freshness:impact:write |
| Success | 202 |
| Request Schema | ImpactAssessmentRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | freshness.assess_change_impact.v1 |
| Audit Action | impact_assessment_request |
| Requirements | FR-012, FR-016 |
| Implementation Slice | SLICE-018 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`freshness.assess_change_impact.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### FRSH-009 — `GET /api/v1/admin/freshness/impact-assessments`

Impact Assessment一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Freshness |
| Kind | query |
| Authentication | admin |
| Scopes | freshness:impact:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ImpactAssessmentList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-012, FR-016 |
| Implementation Slice | SLICE-018 |

**Query parameters**: `impact_level`, `required_action`, `article_id`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

#### IAM

### IAM-001 — `GET /api/v1/admin/me`

現在Principalと権限を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | IAM |
| Kind | query |
| Authentication | admin |
| Scopes | iam:me:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | CurrentPrincipal |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-020 |
| Implementation Slice | SLICE-005 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### IAM-002 — `GET /api/v1/admin/roles`

Role一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | IAM |
| Kind | query |
| Authentication | admin |
| Scopes | iam:role:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | RoleList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | — |
| Implementation Slice | SLICE-005 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### IAM-003 — `GET /api/v1/admin/permissions`

Permission一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | IAM |
| Kind | query |
| Authentication | admin |
| Scopes | iam:permission:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PermissionList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | — |
| Implementation Slice | SLICE-005 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### IAM-004 — `POST /api/v1/admin/session-revocations`

Sessionを失効

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | IAM |
| Kind | command |
| Authentication | admin |
| Scopes | iam:session:revoke |
| Success | 201 |
| Request Schema | SessionRevocationRequest |
| Response Schema | GenericResource |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | session_revoke |
| Requirements | FR-020 |
| Implementation Slice | SLICE-005 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

#### Operations

### OPS-001 — `GET /api/v1/admin/ops/jobs`

Job一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:job:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | JobList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018, FR-020 |
| Implementation Slice | SLICE-004 |

**Query parameters**: `status`, `job_type`, `queue_name`, `correlation_id`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### OPS-002 — `GET /api/v1/admin/ops/jobs/{id}`

JobとAttemptを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:job:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | JobDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-018, FR-020 |
| Implementation Slice | SLICE-004 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### OPS-003 — `POST /api/v1/admin/ops/jobs/{id}/retry`

Jobを手動再実行

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | command |
| Authentication | admin |
| Scopes | ops:job:retry |
| Success | 202 |
| Request Schema | JobRetryRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | manual_job_retry |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### OPS-004 — `POST /api/v1/admin/ops/jobs/{id}/cancel`

Jobを取消要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | command |
| Authentication | admin |
| Scopes | ops:job:cancel |
| Success | 200 |
| Request Schema | JobCancelRequest |
| Response Schema | Job |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | job_cancel |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### OPS-005 — `GET /api/v1/admin/ops/kill-switches`

Kill Switch状態を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:kill_switch:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | KillSwitchList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-019 |
| Implementation Slice | SLICE-022 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### OPS-006 — `POST /api/v1/admin/ops/kill-switch-changes`

Kill Switchを変更

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | command |
| Authentication | admin |
| Scopes | ops:kill_switch:write |
| Success | 201 |
| Request Schema | KillSwitchChangeRequest |
| Response Schema | KillSwitch |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | kill_switch_change |
| Requirements | FR-019, FR-020 |
| Implementation Slice | SLICE-022 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-KILL-002`, `RAOS-CONC-001`, `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### OPS-007 — `GET /api/v1/admin/ops/incidents`

Incident一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:incident:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | IncidentList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-020 |
| Implementation Slice | SLICE-022 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### OPS-008 — `POST /api/v1/admin/ops/incidents`

Incidentを宣言

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | command |
| Authentication | admin |
| Scopes | ops:incident:write |
| Success | 201 |
| Request Schema | IncidentCreateRequest |
| Response Schema | Incident |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | incident_declare |
| Requirements | FR-019, FR-020 |
| Implementation Slice | SLICE-022 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### OPS-009 — `GET /api/v1/admin/ops/incidents/{id}`

Incidentを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:incident:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | IncidentDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-020 |
| Implementation Slice | SLICE-022 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### OPS-010 — `PATCH /api/v1/admin/ops/incidents/{id}`

Incident状態を更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | command |
| Authentication | admin |
| Scopes | ops:incident:write |
| Success | 200 |
| Request Schema | IncidentUpdateRequest |
| Response Schema | Incident |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | incident_update |
| Requirements | FR-020 |
| Implementation Slice | SLICE-022 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### OPS-011 — `POST /api/v1/admin/ops/incidents/{id}/events`

Incident Timeline Eventを追加

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | command |
| Authentication | admin |
| Scopes | ops:incident:write |
| Success | 201 |
| Request Schema | IncidentEventRequest |
| Response Schema | GenericResource |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | incident_event_create |
| Requirements | FR-020 |
| Implementation Slice | SLICE-022 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### OPS-012 — `GET /api/v1/admin/ops/audit-events`

Audit Eventを検索

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:audit:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AuditEventList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-020 |
| Implementation Slice | SLICE-023 |

**Query parameters**: `actor_id`, `action`, `target_type`, `target_id`, `date_from`, `date_to`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### OPS-013 — `POST /api/v1/admin/ops/audit-exports`

Audit Export Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | async_command |
| Authentication | admin |
| Scopes | ops:audit:export |
| Success | 202 |
| Request Schema | AuditExportRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | ops.export_audit.v1 |
| Audit Action | audit_export_request |
| Requirements | FR-020 |
| Implementation Slice | SLICE-023 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`ops.export_audit.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### OPS-014 — `GET /api/v1/admin/ops/alerts`

Alert一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Operations |
| Kind | query |
| Authentication | admin |
| Scopes | ops:alert:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | AlertList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | — |
| Implementation Slice | SLICE-023 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

#### Policy

### POL-001 — `GET /api/v1/admin/policy/bundles`

Policy Bundle一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Policy |
| Kind | query |
| Authentication | admin |
| Scopes | policy:bundle:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PolicyBundleList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-017 |
| Implementation Slice | SLICE-013 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### POL-002 — `POST /api/v1/admin/policy/bundles`

Policy Bundle Versionを登録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Policy |
| Kind | command |
| Authentication | admin |
| Scopes | policy:bundle:write |
| Success | 201 |
| Request Schema | PolicyBundleCreateRequest |
| Response Schema | PolicyBundle |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | policy_bundle_create |
| Requirements | FR-017, FR-020 |
| Implementation Slice | SLICE-013 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### POL-003 — `POST /api/v1/admin/policy/bundles/{id}/activate`

Policy Bundleを有効化

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Policy |
| Kind | command |
| Authentication | admin |
| Scopes | policy:bundle:activate |
| Success | 200 |
| Request Schema | PolicyBundleActivateRequest |
| Response Schema | PolicyBundle |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | policy_bundle_activate |
| Requirements | FR-017, FR-020 |
| Implementation Slice | SLICE-013 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### POL-004 — `GET /api/v1/admin/policy/gate-decisions`

Gate Decision一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Policy |
| Kind | query |
| Authentication | admin |
| Scopes | policy:gate:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | GateDecisionList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-017 |
| Implementation Slice | SLICE-025 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### POL-005 — `POST /api/v1/admin/policy/gate-decisions`

Gate Decisionを記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Policy |
| Kind | command |
| Authentication | admin |
| Scopes | policy:gate:decide |
| Success | 201 |
| Request Schema | GateDecisionRequest |
| Response Schema | GateDecision |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | gate_decision_record |
| Requirements | FR-017, FR-020 |
| Implementation Slice | SLICE-025 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

#### Portfolio

### SITE-001 — `GET /api/v1/admin/sites`

Site一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:site:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | SiteList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**Query parameters**: `cursor`, `limit`, `status`, `site_id`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### SITE-002 — `POST /api/v1/admin/sites`

Siteを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:site:write |
| Success | 201 |
| Request Schema | SiteCreateRequest |
| Response Schema | Site |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | site_create |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### SITE-003 — `GET /api/v1/admin/sites/{id}`

Siteを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:site:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | Site |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### SITE-004 — `PATCH /api/v1/admin/sites/{id}`

Siteを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:site:write |
| Success | 200 |
| Request Schema | SiteUpdateRequest |
| Response Schema | Site |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | site_update |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### CATG-001 — `GET /api/v1/admin/categories`

Category一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:category:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | CategoryList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**Query parameters**: `cursor`, `limit`, `status`, `site_id`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CATG-002 — `POST /api/v1/admin/categories`

Categoryを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:category:write |
| Success | 201 |
| Request Schema | CategoryCreateRequest |
| Response Schema | Category |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | category_create |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### CATG-003 — `GET /api/v1/admin/categories/{id}`

Categoryを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:category:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | Category |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### CATG-004 — `PATCH /api/v1/admin/categories/{id}`

Categoryを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:category:write |
| Success | 200 |
| Request Schema | CategoryUpdateRequest |
| Response Schema | Category |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | category_update |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### INTENT-001 — `GET /api/v1/admin/intent-clusters`

IntentCluster一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:intent:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | IntentClusterList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**Query parameters**: `cursor`, `limit`, `status`, `site_id`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### INTENT-002 — `POST /api/v1/admin/intent-clusters`

IntentClusterを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:intent:write |
| Success | 201 |
| Request Schema | IntentClusterCreateRequest |
| Response Schema | IntentCluster |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | intentcluster_create |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### INTENT-003 — `GET /api/v1/admin/intent-clusters/{id}`

IntentClusterを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:intent:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | IntentCluster |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### INTENT-004 — `PATCH /api/v1/admin/intent-clusters/{id}`

IntentClusterを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:intent:write |
| Success | 200 |
| Request Schema | IntentClusterUpdateRequest |
| Response Schema | IntentCluster |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | intentcluster_update |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### KEY-001 — `GET /api/v1/admin/keywords`

Keyword一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:keyword:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | KeywordList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**Query parameters**: `cursor`, `limit`, `status`, `site_id`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### KEY-002 — `POST /api/v1/admin/keywords`

Keywordを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:keyword:write |
| Success | 201 |
| Request Schema | KeywordCreateRequest |
| Response Schema | Keyword |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | keyword_create |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### KEY-003 — `GET /api/v1/admin/keywords/{id}`

Keywordを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:keyword:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | Keyword |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### KEY-004 — `PATCH /api/v1/admin/keywords/{id}`

Keywordを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:keyword:write |
| Success | 200 |
| Request Schema | KeywordUpdateRequest |
| Response Schema | Keyword |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | keyword_update |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### PORT-001 — `GET /api/v1/admin/opportunity-assessments`

機会評価一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:assessment:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | OpportunityAssessmentList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-005 |
| Implementation Slice | SLICE-006 |

**Query parameters**: `category_id`, `keyword_id`, `decision`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### PORT-002 — `POST /api/v1/admin/opportunity-assessments`

機会評価Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | async_command |
| Authentication | admin |
| Scopes | portfolio:assessment:write |
| Success | 202 |
| Request Schema | OpportunityAssessmentRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | portfolio.assess_opportunity.v1 |
| Audit Action | opportunity_assessment_request |
| Requirements | FR-005, FR-016 |
| Implementation Slice | SLICE-006 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`portfolio.assess_opportunity.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### PORT-003 — `GET /api/v1/admin/action-candidates`

Action Candidate一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | query |
| Authentication | admin |
| Scopes | portfolio:action:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ActionCandidateList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-016 |
| Implementation Slice | SLICE-021 |

**Query parameters**: `action_type`, `status`, `category_id`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### PORT-004 — `POST /api/v1/admin/action-candidates/{id}/decision`

Action Candidateを判断

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Portfolio |
| Kind | command |
| Authentication | admin |
| Scopes | portfolio:action:decide |
| Success | 200 |
| Request Schema | ActionDecisionRequest |
| Response Schema | ActionCandidate |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | action_candidate_decide |
| Requirements | FR-016 |
| Implementation Slice | SLICE-021 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

#### Publishing

### PUBADM-001 — `GET /api/v1/admin/review-assignments`

Review Assignment一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | query |
| Authentication | admin |
| Scopes | publishing:review:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | ReviewAssignmentList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**Query parameters**: `article_version_id`, `assigned_to`, `status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### PUBADM-002 — `POST /api/v1/admin/review-assignments`

Review Assignmentを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | command |
| Authentication | admin |
| Scopes | publishing:review:assign |
| Success | 201 |
| Request Schema | ReviewAssignmentCreateRequest |
| Response Schema | ReviewAssignment |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | review_assignment_create |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### PUBADM-003 — `PATCH /api/v1/admin/review-assignments/{id}`

Review Assignmentを更新

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | command |
| Authentication | admin |
| Scopes | publishing:review:assign |
| Success | 200 |
| Request Schema | ReviewAssignmentUpdateRequest |
| Response Schema | ReviewAssignment |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | なし |
| Audit Action | review_assignment_update |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`

### PUBADM-004 — `POST /api/v1/admin/review-decisions`

Review Decisionを記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | command |
| Authentication | admin |
| Scopes | publishing:review:decide |
| Success | 201 |
| Request Schema | ReviewDecisionRequest |
| Response Schema | ReviewDecision |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | review_decision_record |
| Requirements | FR-009, FR-020 |
| Implementation Slice | SLICE-014 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### PUBADM-005 — `POST /api/v1/admin/approvals`

Approvalを記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | command |
| Authentication | admin |
| Scopes | publishing:approval:decide |
| Success | 201 |
| Request Schema | ApprovalRequest |
| Response Schema | Approval |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | approval_record |
| Requirements | FR-009, FR-020 |
| Implementation Slice | SLICE-014 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### PUBADM-006 — `POST /api/v1/admin/approvals/{id}/revoke`

Approvalを取消

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | command |
| Authentication | admin |
| Scopes | publishing:approval:revoke |
| Success | 201 |
| Request Schema | RevokeApprovalRequest |
| Response Schema | Approval |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | approval_revoke |
| Requirements | FR-009, FR-020 |
| Implementation Slice | SLICE-014 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### PUBADM-007 — `POST /api/v1/admin/publication-candidates`

Publication Candidateを作成

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | async_command |
| Authentication | admin |
| Scopes | publishing:candidate:write |
| Success | 202 |
| Request Schema | PublicationCandidateRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | publishing.build_snapshot.v1 |
| Audit Action | publication_candidate_create |
| Requirements | FR-009, FR-010 |
| Implementation Slice | SLICE-015 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`publishing.build_snapshot.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### PUBADM-008 — `GET /api/v1/admin/publication-candidates/{id}`

Publication Candidateを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | query |
| Authentication | admin |
| Scopes | publishing:candidate:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PublicationCandidate |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-010 |
| Implementation Slice | SLICE-015 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### PUBADM-009 — `POST /api/v1/admin/publication-candidates/{id}/publish`

承認済みSnapshotを公開

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | async_command |
| Authentication | admin |
| Scopes | publishing:publish |
| Success | 202 |
| Request Schema | PublishRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | publishing.publish_snapshot.v1 |
| Audit Action | publication_publish |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- 同期処理を実行せず、`publishing.publish_snapshot.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-PUB-001`, `RAOS-PUB-002`, `RAOS-POL-001`, `RAOS-KILL-001`, `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`, `RAOS-JOB-005`

### PUBADM-010 — `GET /api/v1/admin/publications`

Publication一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | query |
| Authentication | admin |
| Scopes | publishing:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PublicationList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-010 |
| Implementation Slice | SLICE-015 |

**Query parameters**: `site_id`, `state`, `article_id`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### PUBADM-011 — `GET /api/v1/admin/publications/{id}`

Publicationを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | query |
| Authentication | admin |
| Scopes | publishing:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | Publication |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-010 |
| Implementation Slice | SLICE-015 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### PUBADM-012 — `POST /api/v1/admin/publications/{id}/rollback`

Publicationを旧SnapshotへRollback

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | async_command |
| Authentication | admin |
| Scopes | publishing:rollback |
| Success | 202 |
| Request Schema | RollbackRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | publishing.rollback.v1 |
| Audit Action | publication_rollback |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- 同期処理を実行せず、`publishing.rollback.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`, `RAOS-JOB-005`

### PUBADM-013 — `POST /api/v1/admin/publications/{id}/unpublish`

Publicationを非公開化

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | async_command |
| Authentication | admin |
| Scopes | publishing:unpublish |
| Success | 202 |
| Request Schema | UnpublishRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 必須 |
| Async Job | publishing.unpublish.v1 |
| Audit Action | publication_unpublish |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- `If-Match`を現在のstrong ETagと比較し、不一致なら`RAOS-CONC-001`、欠落なら`RAOS-CONC-002`。
- 同期処理を実行せず、`publishing.unpublish.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-CONC-001`, `RAOS-CONC-002`, `RAOS-JOB-005`

### PUBADM-014 — `GET /api/v1/admin/publication-snapshots/{id}`

Publication Snapshot metadataを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Publishing |
| Kind | query |
| Authentication | admin |
| Scopes | publishing:snapshot:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | PublicationSnapshotSummary |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-010 |
| Implementation Slice | SLICE-015 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

#### Quality

### QLT-001 — `GET /api/v1/admin/quality/runs`

Quality Check Run一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | query |
| Authentication | admin |
| Scopes | quality:run:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | QualityCheckRunList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**Query parameters**: `article_version_id`, `status`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### QLT-002 — `POST /api/v1/admin/quality/runs`

Quality Check Jobを要求

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | async_command |
| Authentication | admin |
| Scopes | quality:run:write |
| Success | 202 |
| Request Schema | QualityCheckRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | quality.evaluate_article.v1 |
| Audit Action | quality_check_request |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- 同期処理を実行せず、`quality.evaluate_article.v1` JobをTransaction内で登録し`202 JobAccepted`を返す。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`, `RAOS-JOB-005`

### QLT-003 — `GET /api/v1/admin/quality/runs/{id}`

Quality Check Run詳細を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | query |
| Authentication | admin |
| Scopes | quality:run:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | QualityCheckRunDetail |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### QLT-004 — `GET /api/v1/admin/quality/findings`

Finding一覧を取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | query |
| Authentication | admin |
| Scopes | quality:finding:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | FindingList |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**Query parameters**: `severity`, `is_blocking`, `status`, `article_version_id`, `cursor`, `limit`

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### QLT-005 — `GET /api/v1/admin/quality/findings/{id}`

Findingを取得

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | query |
| Authentication | admin |
| Scopes | quality:finding:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | Finding |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### QLT-006 — `POST /api/v1/admin/quality/findings/{id}/resolution`

Finding解決を記録

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | command |
| Authentication | admin |
| Scopes | quality:finding:resolve |
| Success | 200 |
| Request Schema | FindingResolutionRequest |
| Response Schema | Finding |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | finding_resolve |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### QLT-007 — `POST /api/v1/admin/quality/waivers`

期限付きWaiverを申請

| 項目 | 契約 |
| --- | --- |
| Surface | admin |
| Tag | Quality |
| Kind | command |
| Authentication | admin |
| Scopes | quality:waiver:request |
| Success | 201 |
| Request Schema | WaiverRequest |
| Response Schema | Waiver |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | waiver_request |
| Requirements | FR-008, FR-017 |
| Implementation Slice | SLICE-013 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### 8.3 Internal API

| ID | Method | Path | Tag | Success | Async Job |
| --- | --- | --- | --- | --- | --- |
| INT-001 | POST | /api/v1/internal/scheduled-jobs | Internal | 202 | — |
| INT-002 | POST | /api/v1/internal/projections/rebuild | Internal | 202 | — |
| INT-003 | GET | /api/v1/internal/dependencies/health | Internal | 200 | — |
| INT-004 | POST | /api/v1/internal/providers/{provider}/probe | Internal | 202 | — |

### INT-001 — `POST /api/v1/internal/scheduled-jobs`

SchedulerからJobを登録

| 項目 | 契約 |
| --- | --- |
| Surface | internal |
| Tag | Internal |
| Kind | async_command |
| Authentication | service |
| Scopes | internal:schedule:write |
| Success | 202 |
| Request Schema | ScheduledJobRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | scheduled_job_create |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### INT-002 — `POST /api/v1/internal/projections/rebuild`

Projection再構築Jobを登録

| 項目 | 契約 |
| --- | --- |
| Surface | internal |
| Tag | Internal |
| Kind | async_command |
| Authentication | service |
| Scopes | internal:projection:rebuild |
| Success | 202 |
| Request Schema | ProjectionRebuildRequest |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | projection_rebuild_request |
| Requirements | FR-010, FR-013, FR-019 |
| Implementation Slice | SLICE-004 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

### INT-003 — `GET /api/v1/internal/dependencies/health`

依存サービスHealthを取得

| 項目 | 契約 |
| --- | --- |
| Surface | internal |
| Tag | Internal |
| Kind | query |
| Authentication | service |
| Scopes | internal:health:read |
| Success | 200 |
| Request Schema | なし |
| Response Schema | DependencyHealth |
| Idempotency-Key | 不要 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | なし |
| Requirements | — |
| Implementation Slice | SLICE-023 |

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`

### INT-004 — `POST /api/v1/internal/providers/{provider}/probe`

Provider Contract Probeを要求

| 項目 | 契約 |
| --- | --- |
| Surface | internal |
| Tag | Internal |
| Kind | async_command |
| Authentication | service |
| Scopes | internal:provider:probe |
| Success | 202 |
| Request Schema | なし |
| Response Schema | JobAccepted |
| Idempotency-Key | 必須 |
| If-Match | 不要 |
| Async Job | なし |
| Audit Action | provider_probe_request |
| Requirements | — |
| Implementation Slice | SLICE-023 |

**受入条件**

- `Idempotency-Key`を保存済みpayload hashと照合し、同一入力なら元結果を返す。異なる入力なら`RAOS-IDEMP-002`。
- Request/responseはOpenAPIのJSON Schemaに適合し、未知Fieldは明示的に許可された箇所以外で拒否する。
- `X-Request-ID`と`traceparent`をLog、Audit、Job/Eventへ伝播する。

**主要Error Code**: `RAOS-REQ-001`, `RAOS-RATE-001`, `RAOS-AUTH-001`, `RAOS-AUTH-002`, `RAOS-IDEMP-001`, `RAOS-IDEMP-002`, `RAOS-IDEMP-003`

## 9. Resource Contract

Resource SchemaはDB RowのSerializationではない。Field allowlist、classification、read-only、create/update許可を明示する。DBに列が増えてもAPIへ自動Exposeしてはならない。

### 9.AIJob `AIJob`

| 項目 | 値 |
| --- | --- |
| Source tables | ai.ai_job |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | AIJ-接頭辞を持つアプリケーション生成の不変表示ID。 |
| ops_job_id | string | no | ops job id |
| task_definition_id | string | no | task definition id |
| article_plan_id | anyOf | no |  |
| article_version_id | anyOf | no |  |
| source_packet_version_id | string | no | source packet version id |
| prompt_version_id | string | no | prompt version id |
| output_schema_version_id | string | no | output schema version id |
| model_route_version_id | string | no | model route version id |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| max_cost_jpy | integer | no | max cost jpy |
| completed_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.ActionCandidate `ActionCandidate`

| 項目 | 値 |
| --- | --- |
| Source tables | portfolio.action_candidate |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | status, decision_note |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | ACT-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| category_id | anyOf | no |  |
| action_type | string | no | action type |
| target_entity_type | string | no | target entity type |
| target_entity_id | anyOf | no |  |
| secondary_entity_id | anyOf | no |  |
| source_signal | string | no | source signal |
| expected_incremental_profit_jpy | anyOf | no |  |
| urgency_score | number | no | urgency score |
| confidence | number | no | confidence |
| priority_score | number | no | priority score |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| rationale | object | no | rationale |
| generated_at | string | no | generated at |
| expires_at | anyOf | no |  |
| decided_at | anyOf | no |  |
| decision_note | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.Alert `Alert`

| 項目 | 値 |
| --- | --- |
| Source tables | ops.alert |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| alert_key | string | no | alert key |
| severity | string | no | severity |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| source | string | no | source |
| title | string | no | title |
| description | string | no | description |
| first_seen_at | string | no | first seen at |
| last_seen_at | string | no | last seen at |
| occurrence_count | integer | no | occurrence count |
| incident_id | anyOf | no |  |
| metadata | object | no | 検索対象を限定した補助メタデータ。原本や秘密を格納しない。 |
| acknowledged_by_principal_id | anyOf | no |  |
| acknowledged_at | anyOf | no |  |
| resolved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.AnalyticsImportRun `AnalyticsImportRun`

| 項目 | 値 |
| --- | --- |
| Source tables | analytics.import_run |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | AIR-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| source_type | string | no | source type |
| ops_job_id | string | no | ops job id |
| source_artifact_id | anyOf | no |  |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| date_from | string | no | date from |
| date_to | string | no | date to |
| dimensions | object | no | 要求したdimension・filter・property等。 |
| watermark | anyOf | no |  |
| row_count | integer | no | row count |
| inserted_count | integer | no | inserted count |
| rejected_count | integer | no | rejected count |
| started_at | string | no | started at |
| completed_at | anyOf | no |  |
| error_summary | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Approval `Approval`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.approval |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | APR-接頭辞を持つアプリケーション生成の不変表示ID。 |
| article_version_id | string | no | 記事の特定Version。 |
| approval_type | string | no | approval type |
| decision | string | no | decision |
| quality_check_run_id | anyOf | no |  |
| policy_bundle_id | anyOf | no |  |
| decision_reason | string | no | decision reason |
| approved_at | string | no | approved at |
| valid_until | anyOf | no |  |
| revoked_at | anyOf | no |  |
| revocation_reason | anyOf | no |  |
| supersedes_approval_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Article `Article`

| 項目 | 値 |
| --- | --- |
| Source tables | editorial.article |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | status, archive_reason |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | ART-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| article_plan_id | string | no | article plan id |
| article_type | string | no | article type |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| current_version_id | anyOf | no |  |
| published_version_id | anyOf | no |  |
| archived_at | anyOf | no |  |
| archive_reason | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.ArticlePlan `ArticlePlan`

| 項目 | 値 |
| --- | --- |
| Source tables | editorial.article_plan |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | site_id, category_id, intent_cluster_id, primary_keyword_id, article_type, working_title, objective, priority, opportunity_assessment_id, brief |
| Update fields | category_id, intent_cluster_id, primary_keyword_id, article_type, working_title, objective, status, priority, opportunity_assessment_id, brief |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PLAN-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| category_id | string | no | 対象カテゴリ。 |
| intent_cluster_id | string | no | intent cluster id |
| primary_keyword_id | string | no | primary keyword id |
| article_type | string | no | article type |
| working_title | string | no | working title |
| objective | string | no | objective |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| priority | integer | no | priority |
| opportunity_assessment_id | anyOf | no |  |
| approved_at | anyOf | no |  |
| brief | object | no | Target user、decision questions、required sections、unique value hypothesis。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.ArticleVersion `ArticleVersion`

| 項目 | 値 |
| --- | --- |
| Source tables | editorial.article_version |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | article_id, content_schema_version, title, meta_title, meta_description, excerpt, source_packet_version_id, based_on_version_id |
| Update fields | title, meta_title, meta_description, excerpt, status, source_packet_version_id |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | ARV-接頭辞を持つアプリケーション生成の不変表示ID。 |
| article_id | string | no | 論理記事ID。 |
| version_no | integer | no | Aggregate内で1から増加する不変Version番号。 |
| content_schema_version | integer | no | content schema version |
| title | string | no | title |
| meta_title | anyOf | no |  |
| meta_description | anyOf | no |  |
| excerpt | anyOf | no |  |
| body_sha256 | string | no | body sha256 |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| source_packet_version_id | string | no | source packet version id |
| based_on_version_id | anyOf | no |  |
| ai_job_id | anyOf | no |  |
| submitted_at | anyOf | no |  |
| reviewed_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.AuditEvent `AuditEvent`

| 項目 | 値 |
| --- | --- |
| Source tables | ops.audit_event |
| Classification | RESTRICTED |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| occurred_at | string | no | occurred at |
| actor_type | string | no | actor type |
| actor_id | anyOf | no |  |
| action | string | no | action |
| target_type | string | no | target type |
| target_id | anyOf | no |  |
| outcome | string | no | outcome |
| severity | string | no | severity |
| correlation_id | string | no | 要求・Job・Eventを横断して追跡するCorrelation ID。 |
| request_id | anyOf | no |  |
| before_hash | anyOf | no |  |
| after_hash | anyOf | no |  |
| details | object | no | 差分要約、理由、Policy/Prompt版。秘密、原文、raw IPは含めない。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.CanonicalProduct `CanonicalProduct`

| 項目 | 値 |
| --- | --- |
| Source tables | catalog.canonical_product |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | category_id, canonical_name, brand_name, manufacturer_name, model_number, jan_code, product_type, identity_confidence, identity_attributes |
| Update fields | canonical_name, brand_name, manufacturer_name, model_number, jan_code, product_type, lifecycle_status, identity_confidence, identity_attributes, merged_into_product_id |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PRD-接頭辞を持つアプリケーション生成の不変表示ID。 |
| category_id | string | no | 対象カテゴリ。 |
| canonical_name | string | no | canonical name |
| brand_name | anyOf | no |  |
| manufacturer_name | anyOf | no |  |
| model_number | anyOf | no |  |
| jan_code | anyOf | no |  |
| product_type | string | no | product type |
| lifecycle_status | string | no | lifecycle status |
| identity_confidence | number | no | identity confidence |
| identity_attributes | object | no | 同定に使用した正規化Attribute。 |
| merged_into_product_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.Category `Category`

| 項目 | 値 |
| --- | --- |
| Source tables | portfolio.category |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | site_id, parent_category_id, category_code, name, description, risk_class, article_limit, entry_criteria |
| Update fields | parent_category_id, name, description, risk_class, stage, article_limit, entry_criteria |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | CAT-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| parent_category_id | anyOf | no |  |
| category_code | string | no | category code |
| name | string | no | name |
| description | anyOf | no |  |
| risk_class | string | no | risk class |
| stage | string | no | stage |
| article_limit | anyOf | no |  |
| entry_criteria | object | no | 当該Categoryへ参入するための定量・定性基準。 |
| approved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.Claim `Claim`

| 項目 | 値 |
| --- | --- |
| Source tables | evidence.claim |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | CLM-接頭辞を持つアプリケーション生成の不変表示ID。 |
| article_version_id | string | no | 記事の特定Version。 |
| block_id | anyOf | no |  |
| claim_key | string | no | claim key |
| claim_type | string | no | claim type |
| claim_text | string | no | claim text |
| criticality | string | no | criticality |
| support_status | string | no | support status |
| generated_by_ai_attempt_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Commission `Commission`

| 項目 | 値 |
| --- | --- |
| Source tables | finance.commission |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | COM-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| provider_code | string | no | provider code |
| provider_event_id | string | no | provider event id |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| ordered_at | anyOf | no |  |
| confirmed_at | anyOf | no |  |
| cancelled_at | anyOf | no |  |
| business_month | string | no | business month |
| gross_order_amount_jpy | anyOf | no |  |
| confirmed_order_amount_jpy | anyOf | no |  |
| generated_commission_jpy | anyOf | no |  |
| confirmed_commission_jpy | anyOf | no |  |
| currency | string | no | currency |
| provider_category_code | anyOf | no |  |
| provider_shop_code | anyOf | no |  |
| provider_item_code | anyOf | no |  |
| last_event_at | string | no | last event at |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.DailyArticleMetric `DailyArticleMetric`

| 項目 | 値 |
| --- | --- |
| Source tables | analytics.daily_article_metric |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| article_id | string | no | 論理記事ID。 |
| metric_date | string | no | metric date |
| publication_snapshot_id | anyOf | no |  |
| page_views | integer | no | page views |
| sessions | integer | no | sessions |
| engaged_sessions | integer | no | engaged sessions |
| affiliate_clicks | integer | no | affiliate clicks |
| gsc_clicks | integer | no | gsc clicks |
| gsc_impressions | integer | no | gsc impressions |
| average_position | anyOf | no |  |
| affiliate_click_rate | anyOf | no |  |
| source_watermark | string | no | source watermark |
| projection_version | integer | no | projection version |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |

### 9.EvaluationResult `EvaluationResult`

| 項目 | 値 |
| --- | --- |
| Source tables | ai.evaluation_result |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| suite_code | string | no | suite code |
| suite_version | integer | no | suite version |
| run_id | string | no | run id |
| task_definition_id | string | no | task definition id |
| model_route_version_id | string | no | model route version id |
| prompt_version_id | string | no | prompt version id |
| case_key | string | no | case key |
| metric_code | string | no | metric code |
| metric_value | number | no | metric value |
| passed | boolean | no | passed |
| details | object | no | details |
| result_artifact_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.ExternalCost `ExternalCost`

| 項目 | 値 |
| --- | --- |
| Source tables | finance.external_cost |
| Classification | INTERNAL |
| ETag | no |
| Create fields | site_id, cost_type, vendor_code, service_code, occurred_on, amount_original, currency_original, fx_rate_to_jpy, amount_jpy, article_id, category_id, ai_job_id, source_artifact_id, source_record_key |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | CST-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| cost_type | string | no | cost type |
| vendor_code | string | no | vendor code |
| service_code | anyOf | no |  |
| occurred_on | string | no | occurred on |
| amount_original | number | no | amount original |
| currency_original | string | no | currency original |
| fx_rate_to_jpy | number | no | fx rate to jpy |
| amount_jpy | integer | no | amount jpy |
| article_id | anyOf | no |  |
| category_id | anyOf | no |  |
| ai_job_id | anyOf | no |  |
| source_artifact_id | anyOf | no |  |
| source_record_key | string | no | source record key |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Fact `Fact`

| 項目 | 値 |
| --- | --- |
| Source tables | evidence.fact |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | FCT-接頭辞を持つアプリケーション生成の不変表示ID。 |
| source_snapshot_id | string | no | source snapshot id |
| subject_type | string | no | subject type |
| subject_id | string | no | subject id |
| predicate | string | no | predicate |
| value_text | anyOf | no |  |
| value_numeric | anyOf | no |  |
| value_boolean | anyOf | no |  |
| value_date | anyOf | no |  |
| value_timestamp | anyOf | no |  |
| value_json | anyOf | no |  |
| unit_code | anyOf | no |  |
| locale | anyOf | no |  |
| fact_kind | string | no | fact kind |
| confidence | number | no | confidence |
| valid_from | anyOf | no |  |
| valid_to | anyOf | no |  |
| locator | object | no | JSON Pointer、page、section、table cell等の出典内位置。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Finding `Finding`

| 項目 | 値 |
| --- | --- |
| Source tables | policy.finding |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| quality_check_run_id | string | no | quality check run id |
| rule_version_id | string | no | rule version id |
| finding_code | string | no | finding code |
| severity | string | no | severity |
| is_blocking | boolean | no | is blocking |
| entity_type | string | no | entity type |
| entity_id | anyOf | no |  |
| article_block_id | anyOf | no |  |
| claim_id | anyOf | no |  |
| message | string | no | message |
| evidence | object | no | 検出値、expected、locator、comparison等。 |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| resolved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.FreshnessPolicy `FreshnessPolicy`

| 項目 | 値 |
| --- | --- |
| Source tables | freshness.freshness_policy |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | FPL-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| category_id | anyOf | no |  |
| article_type | anyOf | no |  |
| fact_type | string | no | fact type |
| version_no | integer | no | Aggregate内で1から増加する不変Version番号。 |
| warning_after | string | no | warning after |
| critical_after | string | no | critical after |
| refresh_interval | string | no | refresh interval |
| on_critical_action | string | no | on critical action |
| effective_from | string | no | 設定・関係が有効になる時刻。 |
| effective_to | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.GateDecision `GateDecision`

| 項目 | 値 |
| --- | --- |
| Source tables | policy.gate_decision |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | GTD-接頭辞を持つアプリケーション生成の不変表示ID。 |
| gate_code | string | no | gate code |
| scope_type | string | no | scope type |
| scope_id | string | no | scope id |
| policy_bundle_id | string | no | policy bundle id |
| result | string | no | result |
| conditions | object | no | Conditional passの未達・期限・scale limit。 |
| evidence_artifact_id | string | no | evidence artifact id |
| decided_at | string | no | decided at |
| expires_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.GroupingDecision `GroupingDecision`

| 項目 | 値 |
| --- | --- |
| Source tables | catalog.grouping_decision |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| product_candidate_id | string | no | product candidate id |
| proposed_product_id | anyOf | no |  |
| decision_type | string | no | decision type |
| decision_score | anyOf | no |  |
| rule_version | string | no | rule version |
| reasons | object | no | 一致・不一致Attribute、閾値、Manual note。 |
| decided_by_actor_type | string | no | decided by actor type |
| decided_by_actor_id | anyOf | no |  |
| decided_at | string | no | decided at |
| supersedes_decision_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.HumanWorkLog `HumanWorkLog`

| 項目 | 値 |
| --- | --- |
| Source tables | finance.human_work_log |
| Classification | INTERNAL |
| ETag | no |
| Create fields | site_id, principal_id, work_date, work_type, minutes, hourly_cost_jpy, article_id, category_id, article_version_id, note |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | HWL-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| principal_id | string | no | principal id |
| work_date | string | no | work date |
| work_type | string | no | work type |
| minutes | integer | no | minutes |
| hourly_cost_jpy | integer | no | hourly cost jpy |
| computed_cost_jpy | integer | no | computed cost jpy |
| article_id | anyOf | no |  |
| category_id | anyOf | no |  |
| article_version_id | anyOf | no |  |
| note | anyOf | no |  |
| approved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.ImpactAssessment `ImpactAssessment`

| 項目 | 値 |
| --- | --- |
| Source tables | freshness.impact_assessment |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| change_type | string | no | change type |
| changed_entity_type | string | no | changed entity type |
| changed_entity_id | string | no | changed entity id |
| article_id | anyOf | no |  |
| article_version_id | anyOf | no |  |
| claim_id | anyOf | no |  |
| publication_id | anyOf | no |  |
| impact_level | string | no | impact level |
| required_action | string | no | required action |
| reason | string | no | reason |
| detected_at | string | no | detected at |
| resolved_at | anyOf | no |  |
| resolved_by_job_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Incident `Incident`

| 項目 | 値 |
| --- | --- |
| Source tables | ops.incident |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | severity, title, summary |
| Update fields | severity, status, title, summary, root_cause, impact |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | INC-接頭辞を持つアプリケーション生成の不変表示ID。 |
| severity | string | no | severity |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| title | string | no | title |
| summary | string | no | summary |
| declared_at | string | no | declared at |
| contained_at | anyOf | no |  |
| recovered_at | anyOf | no |  |
| closed_at | anyOf | no |  |
| root_cause | anyOf | no |  |
| impact | object | no | 影響ページ、期間、件数、金額、ユーザー影響の構造化要約。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.IngestionRequest `IngestionRequest`

| 項目 | 値 |
| --- | --- |
| Source tables | catalog.ingestion_request |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | ING-接頭辞を持つアプリケーション生成の不変表示ID。 |
| provider_endpoint_id | string | no | provider endpoint id |
| job_id | string | no | 非同期Job。 |
| request_fingerprint | string | no | request fingerprint |
| request_parameters | object | no | Secretを除外したCanonical request parameters。 |
| requested_at | string | no | requested at |
| responded_at | anyOf | no |  |
| http_status | anyOf | no |  |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| raw_response_artifact_id | anyOf | no |  |
| item_count | anyOf | no |  |
| rate_limit_observation | object | no | Remaining、reset時刻等。 |
| error_class | anyOf | no |  |
| error_code | anyOf | no |  |
| error_message | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.IntentCluster `IntentCluster`

| 項目 | 値 |
| --- | --- |
| Source tables | portfolio.intent_cluster |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | category_id, cluster_code, name, description, intent_type, decision_requirements |
| Update fields | name, description, intent_type, status, decision_requirements |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | INT-接頭辞を持つアプリケーション生成の不変表示ID。 |
| category_id | string | no | 対象カテゴリ。 |
| cluster_code | string | no | cluster code |
| name | string | no | name |
| description | string | no | description |
| intent_type | string | no | intent type |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| decision_requirements | object | no | ユーザーが当該意図で判断するために必要な比較軸・疑問・不安。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.Job `Job`

| 項目 | 値 |
| --- | --- |
| Source tables | ops.job |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | JOB-接頭辞を持つアプリケーション生成の不変表示ID。 |
| job_type | string | no | job type |
| queue_name | string | no | queue name |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| priority | integer | no | priority |
| idempotency_key | anyOf | no |  |
| site_id | anyOf | no |  |
| aggregate_type | anyOf | no |  |
| aggregate_id | anyOf | no |  |
| payload_artifact_id | anyOf | no |  |
| scheduled_at | anyOf | no |  |
| available_at | string | no | available at |
| started_at | anyOf | no |  |
| completed_at | anyOf | no |  |
| max_attempts | integer | no | max attempts |
| attempt_count | integer | no | attempt count |
| lease_owner | anyOf | no |  |
| lease_expires_at | anyOf | no |  |
| correlation_id | string | no | 要求・Job・Eventを横断して追跡するCorrelation ID。 |
| causation_id | anyOf | no |  |
| parent_job_id | anyOf | no |  |
| budget_jpy | anyOf | no |  |
| last_error_class | anyOf | no |  |
| last_error_code | anyOf | no |  |
| last_error_message | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.Keyword `Keyword`

| 項目 | 値 |
| --- | --- |
| Source tables | portfolio.keyword |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | site_id, display_text, locale, sensitive_query |
| Update fields | display_text, locale, status, sensitive_query |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | KW-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| display_text | string | no | display text |
| normalized_text | string | no | normalized text |
| locale | string | no | locale |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| sensitive_query | boolean | no | sensitive query |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.KillSwitch `KillSwitch`

| 項目 | 値 |
| --- | --- |
| Source tables | ops.kill_switch |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| scope_type | string | no | scope type |
| scope_id | anyOf | no |  |
| switch_type | string | no | switch type |
| is_engaged | boolean | no | is engaged |
| generation | integer | no | generation |
| reason | anyOf | no |  |
| incident_id | anyOf | no |  |
| changed_at | string | no | changed at |
| expires_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.LinkCheck `LinkCheck`

| 項目 | 値 |
| --- | --- |
| Source tables | freshness.link_check |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| offer_id | string | no | ショップ単位の販売Offer。 |
| affiliate_link_observation_id | anyOf | no |  |
| refresh_run_id | anyOf | no |  |
| checked_at | string | no | checked at |
| check_method | string | no | check method |
| result | string | no | result |
| http_status | anyOf | no |  |
| destination_host | anyOf | no |  |
| destination_url_sha256 | anyOf | no |  |
| latency_ms | anyOf | no |  |
| risk_code | anyOf | no |  |
| response_artifact_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.ModelRouteVersion `ModelRouteVersion`

| 項目 | 値 |
| --- | --- |
| Source tables | ai.model_route_version |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| route_code | string | no | route code |
| version_no | integer | no | Aggregate内で1から増加する不変Version番号。 |
| task_definition_id | string | no | task definition id |
| primary_model_id | string | no | primary model id |
| fallback_model_id | anyOf | no |  |
| route_config | object | no | Timeout、retry、temperature、max tokens等。 |
| monthly_budget_jpy | anyOf | no |  |
| per_job_budget_jpy | integer | no | per job budget jpy |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| effective_from | anyOf | no |  |
| effective_to | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Offer `Offer`

| 項目 | 値 |
| --- | --- |
| Source tables | catalog.offer |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | product_id, status |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | OFF-接頭辞を持つアプリケーション生成の不変表示ID。 |
| provider_endpoint_id | string | no | provider endpoint id |
| external_offer_id | string | no | external offer id |
| product_candidate_id | string | no | product candidate id |
| product_id | anyOf | no |  |
| shop_id | string | no | shop id |
| item_url | string | no | item url |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| first_observed_at | string | no | first observed at |
| last_observed_at | string | no | last observed at |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.OfferCurrent `OfferCurrent`

| 項目 | 値 |
| --- | --- |
| Source tables | catalog.offer_current_projection |
| Classification | CONFIDENTIAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| offer_id | string | no | ショップ単位の販売Offer。 |
| product_id | anyOf | no |  |
| current_price_jpy | anyOf | no |  |
| current_shipping_fee_jpy | anyOf | no |  |
| current_availability | string | no | current availability |
| review_count | anyOf | no |  |
| review_average | anyOf | no |  |
| destination_host | anyOf | no |  |
| price_observed_at | anyOf | no |  |
| availability_observed_at | anyOf | no |  |
| link_observed_at | anyOf | no |  |
| freshness_status | string | no | freshness status |
| projection_version | integer | no | projection version |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |

- affiliate_url is intentionally excluded from general admin response; dedicated restricted action may inspect link metadata.

### 9.OpportunityAssessment `OpportunityAssessment`

| 項目 | 値 |
| --- | --- |
| Source tables | portfolio.opportunity_assessment |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | OPA-接頭辞を持つアプリケーション生成の不変表示ID。 |
| category_id | string | no | 対象カテゴリ。 |
| intent_cluster_id | anyOf | no |  |
| keyword_id | anyOf | no |  |
| assessment_type | string | no | assessment type |
| formula_version | string | no | formula version |
| editorial_feasibility_score | number | no | editorial feasibility score |
| business_opportunity_score | number | no | business opportunity score |
| compliance_risk_score | number | no | compliance risk score |
| overall_priority_score | number | no | overall priority score |
| decision | string | no | decision |
| editorial_components | object | no | Editorialに必要な一次情報、独自価値、比較可能性等。 |
| business_components | object | no | 需要、競争、商品数、想定EPC等。推薦順位には渡さない。 |
| compliance_components | object | no | Category、表示、著作権、規約、YMYL等のRisk。 |
| assessed_at | string | no | assessed at |
| expires_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.PolicyBundle `PolicyBundle`

| 項目 | 値 |
| --- | --- |
| Source tables | policy.policy_bundle |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | POL-接頭辞を持つアプリケーション生成の不変表示ID。 |
| bundle_code | string | no | bundle code |
| version_no | integer | no | Aggregate内で1から増加する不変Version番号。 |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| git_commit_sha | string | no | git commit sha |
| bundle_sha256 | string | no | bundle sha256 |
| effective_from | anyOf | no |  |
| effective_to | anyOf | no |  |
| approved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.ProductCandidate `ProductCandidate`

| 項目 | 値 |
| --- | --- |
| Source tables | catalog.product_candidate |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | normalized_item_name, model_number_candidate, jan_code_candidate, listing_status |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PCD-接頭辞を持つアプリケーション生成の不変表示ID。 |
| provider_endpoint_id | string | no | provider endpoint id |
| external_item_code | string | no | external item code |
| shop_id | string | no | shop id |
| rakuten_genre_id | anyOf | no |  |
| item_name | string | no | item name |
| normalized_item_name | string | no | normalized item name |
| model_number_candidate | anyOf | no |  |
| jan_code_candidate | anyOf | no |  |
| image_set | object | no | APIが返した許可画像URL、order、size。Overlay/Crop後画像は登録しない。 |
| listing_status | string | no | listing status |
| first_observed_at | string | no | first observed at |
| last_observed_at | string | no | last observed at |
| source_snapshot_id | string | no | source snapshot id |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.PromptVersion `PromptVersion`

| 項目 | 値 |
| --- | --- |
| Source tables | ai.prompt_version |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PRM-接頭辞を持つアプリケーション生成の不変表示ID。 |
| task_definition_id | string | no | task definition id |
| prompt_code | string | no | prompt code |
| version_no | integer | no | Aggregate内で1から増加する不変Version番号。 |
| git_path | string | no | git path |
| git_commit_sha | string | no | git commit sha |
| template_sha256 | string | no | template sha256 |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| effective_from | anyOf | no |  |
| effective_to | anyOf | no |  |
| approved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Publication `Publication`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.publication |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PUB-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| article_id | string | no | 論理記事ID。 |
| channel | string | no | channel |
| state | string | no | state |
| current_snapshot_id | anyOf | no |  |
| current_route_id | anyOf | no |  |
| first_published_at | anyOf | no |  |
| last_published_at | anyOf | no |  |
| unpublished_at | anyOf | no |  |
| etag | anyOf | no |  |
| projection_generation | integer | no | projection generation |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.PublicationCandidate `PublicationCandidate`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.publication_candidate |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PBC-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| article_version_id | string | no | 記事の特定Version。 |
| final_approval_id | string | no | final approval id |
| quality_check_run_id | string | no | quality check run id |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| snapshot_build_job_id | anyOf | no |  |
| publication_snapshot_id | anyOf | no |  |
| blocked_reason_code | anyOf | no |  |
| blocked_detail | anyOf | no |  |
| requested_at | string | no | requested at |
| completed_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.PublicationSnapshotSummary `PublicationSnapshotSummary`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.publication_snapshot |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | PBS-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| article_id | string | no | 論理記事ID。 |
| article_version_id | string | no | 記事の特定Version。 |
| publication_candidate_id | string | no | publication candidate id |
| artifact_id | string | no | S3互換Object Storage上の不変Artifactレジストリ。 |
| schema_version | integer | no | schema version |
| content_sha256 | string | no | content sha256 |
| source_packet_version_id | string | no | source packet version id |
| policy_bundle_id | string | no | policy bundle id |
| quality_check_run_id | string | no | quality check run id |
| final_approval_id | string | no | final approval id |
| canonical_path | string | no | canonical path |
| title | string | no | title |
| built_by_job_id | string | no | built by job id |
| built_at | string | no | built at |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.QualityCheckRun `QualityCheckRun`

| 項目 | 値 |
| --- | --- |
| Source tables | policy.quality_check_run |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | QCR-接頭辞を持つアプリケーション生成の不変表示ID。 |
| article_version_id | string | no | 記事の特定Version。 |
| source_packet_version_id | string | no | source packet version id |
| policy_bundle_id | string | no | policy bundle id |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| started_at | string | no | started at |
| completed_at | anyOf | no |  |
| total_score | anyOf | no |  |
| blocking_finding_count | integer | no | blocking finding count |
| report_artifact_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.RefreshRun `RefreshRun`

| 項目 | 値 |
| --- | --- |
| Source tables | freshness.refresh_run |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | RFR-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| ops_job_id | string | no | ops job id |
| run_type | string | no | run type |
| scope_type | string | no | scope type |
| scope_id | anyOf | no |  |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| started_at | string | no | started at |
| completed_at | anyOf | no |  |
| target_count | integer | no | target count |
| success_count | integer | no | success count |
| failure_count | integer | no | failure count |
| continuation | object | no | Provider cursor・page・resume token。 |
| report_artifact_id | anyOf | no |  |
| error_summary | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.RevenueImport `RevenueImport`

| 項目 | 値 |
| --- | --- |
| Source tables | finance.revenue_import |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | RVI-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| provider_code | string | no | provider code |
| source_artifact_id | string | no | source artifact id |
| source_sha256 | string | no | source sha256 |
| parser_version_id | string | no | parser version id |
| ops_job_id | anyOf | no |  |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| is_dry_run | boolean | no | is dry run |
| period_from | string | no | period from |
| period_to | string | no | period to |
| row_count | integer | no | row count |
| accepted_count | integer | no | accepted count |
| rejected_count | integer | no | rejected count |
| gross_order_amount_jpy | anyOf | no |  |
| commission_amount_jpy | anyOf | no |  |
| confirmed_at | anyOf | no |  |
| reconciliation_status | string | no | reconciliation status |
| report_artifact_id | anyOf | no |  |
| error_summary | anyOf | no |  |
| uploaded_at | string | no | uploaded at |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.ReviewAssignment `ReviewAssignment`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.review_assignment |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | article_version_id, review_type, assigned_to_principal_id, priority, due_at, instructions |
| Update fields | status, priority, due_at, instructions |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | RVA-接頭辞を持つアプリケーション生成の不変表示ID。 |
| article_version_id | string | no | 記事の特定Version。 |
| review_type | string | no | review type |
| assigned_to_principal_id | string | no | assigned to principal id |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| priority | integer | no | priority |
| due_at | anyOf | no |  |
| started_at | anyOf | no |  |
| completed_at | anyOf | no |  |
| cancelled_at | anyOf | no |  |
| instructions | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.ReviewComment `ReviewComment`

| 項目 | 値 |
| --- | --- |
| Source tables | editorial.review_comment |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| article_version_id | string | no | 記事の特定Version。 |
| article_block_id | anyOf | no |  |
| claim_id | anyOf | no |  |
| thread_id | string | no | thread id |
| parent_comment_id | anyOf | no |  |
| author_principal_id | string | no | author principal id |
| comment_text | string | no | comment text |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| resolved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.ReviewDecision `ReviewDecision`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.review_decision |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | RVD-接頭辞を持つアプリケーション生成の不変表示ID。 |
| review_assignment_id | string | no | review assignment id |
| article_version_id | string | no | 記事の特定Version。 |
| decision | string | no | decision |
| summary | string | no | summary |
| checklist_results | object | no | Review checklist項目・結果・Evidence locator。 |
| decision_artifact_id | anyOf | no |  |
| decided_at | string | no | decided at |
| supersedes_decision_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.RollbackRecord `RollbackRecord`

| 項目 | 値 |
| --- | --- |
| Source tables | publishing.rollback_record |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | RBK-接頭辞を持つアプリケーション生成の不変表示ID。 |
| publication_id | string | no | publication id |
| from_snapshot_id | string | no | from snapshot id |
| to_snapshot_id | string | no | to snapshot id |
| incident_id | anyOf | no |  |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| reason | string | no | reason |
| verification_result | anyOf | no |  |
| requested_at | string | no | requested at |
| executed_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Site `Site`

| 項目 | 値 |
| --- | --- |
| Source tables | portfolio.site |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | site_code, name, primary_domain, brand_name, locale, timezone, currency, public_settings |
| Update fields | name, primary_domain, brand_name, locale, timezone, currency, status, public_settings |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | SITE-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_code | string | no | site code |
| name | string | no | name |
| primary_domain | string | no | primary domain |
| brand_name | string | no | brand name |
| locale | string | no | locale |
| timezone | string | no | timezone |
| currency | string | no | currency |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| public_settings | object | no | 公開表示に安全なSite設定。秘密や内部KPIを含めない。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.Source `Source`

| 項目 | 値 |
| --- | --- |
| Source tables | evidence.source |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | source_type, provider_endpoint_id, name, base_url, authority_level, permitted_use, metadata |
| Update fields | name, base_url, authority_level, permitted_use, terms_checked_at, status, metadata |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | SRC-接頭辞を持つアプリケーション生成の不変表示ID。 |
| source_type | string | no | source type |
| provider_endpoint_id | anyOf | no |  |
| name | string | no | name |
| base_url | anyOf | no |  |
| authority_level | string | no | authority level |
| permitted_use | string | no | permitted use |
| terms_checked_at | anyOf | no |  |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| metadata | object | no | Contact、acquisition method、robots/terms note等。 |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.SourcePacket `SourcePacket`

| 項目 | 値 |
| --- | --- |
| Source tables | evidence.source_packet |
| Classification | INTERNAL |
| ETag | yes |
| Create fields | article_plan_id, packet_type |
| Update fields | status |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | SP-接頭辞を持つアプリケーション生成の不変表示ID。 |
| article_plan_id | string | no | article plan id |
| packet_type | string | no | packet type |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| current_version_no | integer | no | current version no |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |
| updated_at | string | yes | 最終更新時刻。UTCのtimestamptz。 |
| lock_version | integer | yes | 楽観的排他制御用の単調増加Version。 |

### 9.SourcePacketVersion `SourcePacketVersion`

| 項目 | 値 |
| --- | --- |
| Source tables | evidence.source_packet_version |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | SPV-接頭辞を持つアプリケーション生成の不変表示ID。 |
| source_packet_id | string | no | source packet id |
| version_no | integer | no | Aggregate内で1から増加する不変Version番号。 |
| artifact_id | string | no | S3互換Object Storage上の不変Artifactレジストリ。 |
| content_sha256 | string | no | content sha256 |
| schema_version | integer | no | schema version |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| built_by_job_id | anyOf | no |  |
| reviewed_at | anyOf | no |  |
| review_note | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.SourceSnapshot `SourceSnapshot`

| 項目 | 値 |
| --- | --- |
| Source tables | evidence.source_snapshot |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | SSN-接頭辞を持つアプリケーション生成の不変表示ID。 |
| source_id | string | no | source id |
| artifact_id | string | no | S3互換Object Storage上の不変Artifactレジストリ。 |
| external_reference | anyOf | no |  |
| acquired_at | string | no | acquired at |
| effective_at | anyOf | no |  |
| expires_at | anyOf | no |  |
| content_sha256 | string | no | content sha256 |
| parser_version | string | no | parser version |
| validation_status | string | no | validation status |
| validation_message | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.StalenessAssessment `StalenessAssessment`

| 項目 | 値 |
| --- | --- |
| Source tables | freshness.staleness_assessment |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| target_type | string | no | target type |
| target_id | string | no | target id |
| freshness_policy_id | string | no | freshness policy id |
| observation_id | anyOf | no |  |
| observation_at | anyOf | no |  |
| assessed_at | string | no | assessed at |
| age_seconds | anyOf | no |  |
| freshness_status | string | no | freshness status |
| recommended_action | string | no | recommended action |
| reason_code | string | no | reason code |
| refresh_run_id | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.UnitEconomicsSnapshot `UnitEconomicsSnapshot`

| 項目 | 値 |
| --- | --- |
| Source tables | finance.unit_economics_snapshot |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | UES-接頭辞を持つアプリケーション生成の不変表示ID。 |
| site_id | string | no | 対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。 |
| scope_type | string | no | scope type |
| scope_id | string | no | scope id |
| period_month | string | no | period month |
| calculation_version | string | no | calculation version |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| confirmed_commission_jpy | integer | no | confirmed commission jpy |
| generated_commission_jpy | integer | no | generated commission jpy |
| external_cost_jpy | integer | no | external cost jpy |
| human_cost_jpy | integer | no | human cost jpy |
| contribution_profit_jpy | integer | no | contribution profit jpy |
| eligible_sessions | integer | no | eligible sessions |
| affiliate_clicks | integer | no | affiliate clicks |
| confirmed_orders | integer | no | confirmed orders |
| confirmed_epc_jpy | anyOf | no |  |
| confirmed_rpm_jpy | anyOf | no |  |
| confirmation_rate | anyOf | no |  |
| cost_recovery_months | anyOf | no |  |
| source_watermark | string | no | source watermark |
| report_artifact_id | string | no | report artifact id |
| calculated_at | string | no | calculated at |
| approved_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

### 9.Waiver `Waiver`

| 項目 | 値 |
| --- | --- |
| Source tables | policy.waiver |
| Classification | INTERNAL |
| ETag | no |
| Create fields | — |
| Update fields | — |

| Field | Type | Read only | Description |
| --- | --- | --- | --- |
| id | string | yes | 内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。 |
| display_id | string | yes | WVR-接頭辞を持つアプリケーション生成の不変表示ID。 |
| finding_id | string | no | finding id |
| scope_type | string | no | scope type |
| scope_id | string | no | scope id |
| justification | string | no | justification |
| status | string | no | 業務状態を示す安定Enum文字列。 |
| requested_at | string | no | requested at |
| decided_at | anyOf | no |  |
| decision_reason | anyOf | no |  |
| expires_at | anyOf | no |  |
| revoked_at | anyOf | no |  |
| created_at | string | yes | レコード作成時刻。UTCのtimestamptz。 |

## 10. Domain Event Contract

Domain Eventはすでに確定した事実を過去形で表す。ProducerはDomain変更とOutbox Eventを同一DB TransactionでCommitする。Consumerは`event.id`またはConsumer固有Inbox Keyで冪等化する。EventをCommandとして扱わない。

### 10.1 Event Envelope

- CloudEvents互換Field: `specversion`、`id`、`source`、`type`、`subject`、`time`、`datacontenttype`、`dataschema`。
- RAOS Field: `event_version`、`producer`、`aggregate`、`site_id`、`correlation_id`、`causation_id`、`actor`、`classification`、`partition_key`、`metadata`。
- `data`へSecret、Access Token、生IP、楽天Review本文、巨大原本を含めない。原本はArtifact Refで参照する。
- Aggregate内順序が必要なConsumerは`aggregate.version`を利用し、Global orderingを仮定しない。

| Event Type | Producer | Channel | Aggregate | Consumers | Requirements |
| --- | --- | --- | --- | --- | --- |
| jp.raos.ops.job_requested.v1 | ops | ops.events | job | outbox_dispatcher, ops_metrics | FR-020 |
| jp.raos.ops.job_succeeded.v1 | ops | ops.events | job | workflow_router, cost_allocator, notification_policy | FR-018, FR-020 |
| jp.raos.ops.job_failed_terminal.v1 | ops | ops.events | job | alerting, incident_assist, workflow_router | FR-020 |
| jp.raos.ops.job_quarantined.v1 | ops | ops.events | job | alerting, admin_dashboard | FR-020 |
| jp.raos.ops.kill_switch_changed.v1 | ops | publication.events | kill_switch | public_projection, publication_guard, worker_guard, alerting | FR-019, FR-020 |
| jp.raos.ops.incident_declared.v1 | ops | notification.events | incident | notification_policy, admin_dashboard | FR-020 |
| jp.raos.ops.incident_closed.v1 | ops | notification.events | incident | notification_policy, postmortem_tracker | FR-020 |
| jp.raos.ops.audit_export_completed.v1 | ops | analytics.events | audit_export | audit_archive, notification_policy | FR-020 |
| jp.raos.ops.child_jobs_created.v1 | ops | ops.events | job | workflow_router | FR-020 |
| jp.raos.ops.readmodel_rebuilt.v1 | ops | publication.events | projection | cache_invalidator, ops_metrics | FR-010, FR-013, FR-019 |
| jp.raos.ops.notification_dispatched.v1 | ops | notification.events | notification | ops_metrics | FR-020 |
| jp.raos.ops.retention_sweep_completed.v1 | ops | analytics.events | retention_policy | audit_archive, notification_policy | FR-020 |
| jp.raos.portfolio.opportunity_assessed.v1 | portfolio | quality.events | opportunity_assessment | action_candidate_generator, admin_dashboard | FR-005, FR-016 |
| jp.raos.portfolio.action_candidates_generated.v1 | portfolio | analytics.events | site | admin_dashboard | FR-016 |
| jp.raos.portfolio.action_candidate_decided.v1 | portfolio | ops.events | action_candidate | workflow_router, audit_projection | FR-016, FR-020 |
| jp.raos.catalog.ingestion_completed.v1 | catalog | ingestion.events | ingestion_request | catalog_normalizer, contract_monitor | FR-002, FR-004 |
| jp.raos.catalog.genre_sync_completed.v1 | catalog | ingestion.events | rakuten_genre | portfolio_mapping_assist | FR-002 |
| jp.raos.catalog.candidates_normalized.v1 | catalog | ingestion.events | ingestion_request | product_grouping, freshness_projection | FR-003, FR-004 |
| jp.raos.catalog.grouping_proposals_created.v1 | catalog | ingestion.events | product_candidate | admin_review_queue | FR-003 |
| jp.raos.catalog.grouping_decision_recorded.v1 | catalog | ingestion.events | product_candidate | catalog_projection, impact_assessor | FR-003 |
| jp.raos.catalog.offer_observed.v1 | catalog | freshness.events | offer | freshness_assessor, impact_assessor, offer_projection | FR-004, FR-011, FR-012 |
| jp.raos.catalog.offer_unavailable.v1 | catalog | freshness.events | offer | impact_assessor, public_projection, alerting | FR-012 |
| jp.raos.catalog.affiliate_link_invalid.v1 | catalog | freshness.events | offer | public_projection, alerting, impact_assessor | FR-011, FR-019 |
| jp.raos.evidence.source_snapshot_captured.v1 | evidence | ingestion.events | source_snapshot | fact_extractor, admin_dashboard | FR-004 |
| jp.raos.evidence.facts_extracted.v1 | evidence | quality.events | source_snapshot | source_packet_builder | FR-004, FR-007 |
| jp.raos.evidence.source_packet_ready.v1 | evidence | quality.events | source_packet | review_queue, admin_dashboard | FR-006, FR-007 |
| jp.raos.evidence.source_packet_approved.v1 | evidence | quality.events | source_packet | draft_workflow, quality_workflow | FR-006 |
| jp.raos.evidence.claims_extracted.v1 | evidence | quality.events | article_version | quality_engine | FR-007, FR-008 |
| jp.raos.evidence.claim_unsupported.v1 | evidence | quality.events | claim | quality_engine, admin_dashboard | FR-007, FR-008 |
| jp.raos.editorial.article_plan_approved.v1 | editorial | quality.events | article_plan | source_packet_workflow | FR-001 |
| jp.raos.editorial.article_created.v1 | editorial | ops.events | article | admin_dashboard | FR-001 |
| jp.raos.editorial.draft_generated.v1 | editorial | ai.events | article_version | claim_extractor, quality_workflow, admin_dashboard | FR-006, FR-007, FR-018 |
| jp.raos.editorial.article_version_submitted.v1 | editorial | publication.events | article_version | review_assignment_workflow | FR-009 |
| jp.raos.ai.job_requested.v1 | ai | ai.events | ai_job | ai_metrics | FR-018 |
| jp.raos.ai.job_succeeded.v1 | ai | ai.events | ai_job | workflow_router, cost_allocator, ai_metrics | FR-018 |
| jp.raos.ai.job_failed.v1 | ai | ai.events | ai_job | workflow_router, alerting, ai_metrics | FR-018 |
| jp.raos.ai.policy_assist_completed.v1 | ai | quality.events | quality_check_run | quality_engine | FR-008, FR-018 |
| jp.raos.ai.evaluation_completed.v1 | ai | ai.events | evaluation_suite | release_gate, admin_dashboard | FR-018 |
| jp.raos.policy.quality_check_completed.v1 | policy | quality.events | quality_check_run | review_workflow, publication_guard, admin_dashboard | FR-008, FR-009 |
| jp.raos.policy.blocking_finding_raised.v1 | policy | quality.events | finding | publication_guard, alerting, admin_dashboard | FR-008 |
| jp.raos.policy.finding_resolved.v1 | policy | quality.events | finding | quality_recheck_assist | FR-008 |
| jp.raos.policy.policy_bundle_activated.v1 | policy | quality.events | policy_bundle | policy_recheck_scheduler, publication_guard | FR-017, FR-020 |
| jp.raos.policy.gate_decision_recorded.v1 | policy | quality.events | gate_decision | release_gate, admin_dashboard | FR-017, FR-020 |
| jp.raos.policy.policy_recheck_completed.v1 | policy | quality.events | policy_bundle | admin_dashboard, alerting | FR-017 |
| jp.raos.publishing.review_assigned.v1 | publishing | notification.events | review_assignment | notification_policy, admin_dashboard | FR-009 |
| jp.raos.publishing.review_decision_recorded.v1 | publishing | publication.events | review_decision | approval_workflow, admin_dashboard | FR-009, FR-020 |
| jp.raos.publishing.approval_granted.v1 | publishing | publication.events | approval | publication_workflow, admin_dashboard | FR-009, FR-020 |
| jp.raos.publishing.approval_revoked.v1 | publishing | publication.events | approval | publication_guard, impact_assessor, alerting | FR-009, FR-020 |
| jp.raos.publishing.snapshot_built.v1 | publishing | publication.events | publication_candidate | publication_workflow, admin_dashboard | FR-010 |
| jp.raos.publishing.article_published.v1 | publishing | publication.events | publication | cache_invalidator, sitemap_builder, analytics_route_map, freshness_scheduler | FR-010, FR-019 |
| jp.raos.publishing.article_unpublished.v1 | publishing | publication.events | publication | cache_invalidator, sitemap_builder, analytics_route_map | FR-010, FR-019 |
| jp.raos.publishing.article_rolled_back.v1 | publishing | publication.events | publication | cache_invalidator, alerting, audit_projection | FR-010, FR-019, FR-020 |
| jp.raos.publishing.public_projection_rebuilt.v1 | publishing | publication.events | publication | cache_invalidator, ops_metrics | FR-010 |
| jp.raos.freshness.staleness_assessed.v1 | freshness | freshness.events | offer | public_projection, refresh_scheduler, impact_assessor | FR-012 |
| jp.raos.freshness.refresh_completed.v1 | freshness | freshness.events | refresh_run | admin_dashboard, alerting, daily_metrics | FR-011, FR-012 |
| jp.raos.freshness.link_check_completed.v1 | freshness | freshness.events | refresh_run | public_projection, impact_assessor, alerting | FR-011 |
| jp.raos.freshness.impact_detected.v1 | freshness | freshness.events | impact_assessment | action_candidate_generator, publication_guard, alerting | FR-012, FR-016 |
| jp.raos.analytics.import_completed.v1 | analytics | analytics.events | import_run | daily_metric_rollup, data_quality_monitor | FR-013 |
| jp.raos.analytics.daily_metrics_updated.v1 | analytics | analytics.events | daily_article_metric | unit_economics_calculator, action_candidate_generator, dashboard_projection | FR-013, FR-015, FR-016 |
| jp.raos.finance.revenue_import_dry_run_ready.v1 | finance | analytics.events | revenue_import | admin_dashboard, notification_policy | FR-014 |
| jp.raos.finance.revenue_import_committed.v1 | finance | analytics.events | revenue_import | unit_economics_calculator, audit_projection | FR-014, FR-020 |
| jp.raos.finance.commission_status_changed.v1 | finance | analytics.events | commission | unit_economics_calculator, dashboard_projection | FR-014, FR-015 |
| jp.raos.finance.unit_economics_calculated.v1 | finance | analytics.events | unit_economics_snapshot | dashboard_projection, action_candidate_generator | FR-015, FR-016 |

### 10.2 `jp.raos.ops.job_requested.v1`

Jobが正本へ登録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-job-requested-v1.schema.json |
| Producer | ops |
| Channel | ops.events |
| Aggregate | job |
| Consumers | outbox_dispatcher, ops_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.3 `jp.raos.ops.job_succeeded.v1`

Jobが成功した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-job-succeeded-v1.schema.json |
| Producer | ops |
| Channel | ops.events |
| Aggregate | job |
| Consumers | workflow_router, cost_allocator, notification_policy |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-018, FR-020 |
| Implementation Slice | SLICE-004 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.4 `jp.raos.ops.job_failed_terminal.v1`

Jobが自動再試行不能な終端失敗になった。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-job-failed-terminal-v1.schema.json |
| Producer | ops |
| Channel | ops.events |
| Aggregate | job |
| Consumers | alerting, incident_assist, workflow_router |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.5 `jp.raos.ops.job_quarantined.v1`

Jobまたは入力が隔離された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-job-quarantined-v1.schema.json |
| Producer | ops |
| Channel | ops.events |
| Aggregate | job |
| Consumers | alerting, admin_dashboard |
| Classification | CONFIDENTIAL |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.6 `jp.raos.ops.kill_switch_changed.v1`

Kill Switch generationが変更された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-kill-switch-changed-v1.schema.json |
| Producer | ops |
| Channel | publication.events |
| Aggregate | kill_switch |
| Consumers | public_projection, publication_guard, worker_guard, alerting |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-019, FR-020 |
| Implementation Slice | SLICE-022 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.7 `jp.raos.ops.incident_declared.v1`

Incidentが宣言された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-incident-declared-v1.schema.json |
| Producer | ops |
| Channel | notification.events |
| Aggregate | incident |
| Consumers | notification_policy, admin_dashboard |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-022 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.8 `jp.raos.ops.incident_closed.v1`

Incidentが閉鎖された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-incident-closed-v1.schema.json |
| Producer | ops |
| Channel | notification.events |
| Aggregate | incident |
| Consumers | notification_policy, postmortem_tracker |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-022 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.9 `jp.raos.ops.audit_export_completed.v1`

Audit Export Artifactが作成された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-audit-export-completed-v1.schema.json |
| Producer | ops |
| Channel | analytics.events |
| Aggregate | audit_export |
| Consumers | audit_archive, notification_policy |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-023 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.10 `jp.raos.ops.child_jobs_created.v1`

Dispatcher Jobが子Job群を作成した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-child-jobs-created-v1.schema.json |
| Producer | ops |
| Channel | ops.events |
| Aggregate | job |
| Consumers | workflow_router |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-004 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.11 `jp.raos.ops.readmodel_rebuilt.v1`

Read Model再構築が完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-readmodel-rebuilt-v1.schema.json |
| Producer | ops |
| Channel | publication.events |
| Aggregate | projection |
| Consumers | cache_invalidator, ops_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-010, FR-013, FR-019 |
| Implementation Slice | SLICE-023 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.12 `jp.raos.ops.notification_dispatched.v1`

通知Adapterへの送信結果が記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-notification-dispatched-v1.schema.json |
| Producer | ops |
| Channel | notification.events |
| Aggregate | notification |
| Consumers | ops_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-023 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.13 `jp.raos.ops.retention_sweep_completed.v1`

Retention sweepが完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ops-retention-sweep-completed-v1.schema.json |
| Producer | ops |
| Channel | analytics.events |
| Aggregate | retention_policy |
| Consumers | audit_archive, notification_policy |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-020 |
| Implementation Slice | SLICE-025 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.14 `jp.raos.portfolio.opportunity_assessed.v1`

機会評価が記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-portfolio-opportunity-assessed-v1.schema.json |
| Producer | portfolio |
| Channel | quality.events |
| Aggregate | opportunity_assessment |
| Consumers | action_candidate_generator, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-005, FR-016 |
| Implementation Slice | SLICE-006 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.15 `jp.raos.portfolio.action_candidates_generated.v1`

Action Candidate群が生成された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-portfolio-action-candidates-generated-v1.schema.json |
| Producer | portfolio |
| Channel | analytics.events |
| Aggregate | site |
| Consumers | admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-016 |
| Implementation Slice | SLICE-021 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.16 `jp.raos.portfolio.action_candidate_decided.v1`

Action Candidateへの人間判断が記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-portfolio-action-candidate-decided-v1.schema.json |
| Producer | portfolio |
| Channel | ops.events |
| Aggregate | action_candidate |
| Consumers | workflow_router, audit_projection |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-016, FR-020 |
| Implementation Slice | SLICE-021 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.17 `jp.raos.catalog.ingestion_completed.v1`

Provider取込原本が保存された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-ingestion-completed-v1.schema.json |
| Producer | catalog |
| Channel | ingestion.events |
| Aggregate | ingestion_request |
| Consumers | catalog_normalizer, contract_monitor |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-002, FR-004 |
| Implementation Slice | SLICE-008 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.18 `jp.raos.catalog.genre_sync_completed.v1`

Genre同期が完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-genre-sync-completed-v1.schema.json |
| Producer | catalog |
| Channel | ingestion.events |
| Aggregate | rakuten_genre |
| Consumers | portfolio_mapping_assist |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-002 |
| Implementation Slice | SLICE-008 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.19 `jp.raos.catalog.candidates_normalized.v1`

Product CandidateとObservationが正規化された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-candidates-normalized-v1.schema.json |
| Producer | catalog |
| Channel | ingestion.events |
| Aggregate | ingestion_request |
| Consumers | product_grouping, freshness_projection |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-003, FR-004 |
| Implementation Slice | SLICE-009 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.20 `jp.raos.catalog.grouping_proposals_created.v1`

Grouping提案が作成された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-grouping-proposals-created-v1.schema.json |
| Producer | catalog |
| Channel | ingestion.events |
| Aggregate | product_candidate |
| Consumers | admin_review_queue |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.21 `jp.raos.catalog.grouping_decision_recorded.v1`

不変Grouping Decisionが記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-grouping-decision-recorded-v1.schema.json |
| Producer | catalog |
| Channel | ingestion.events |
| Aggregate | product_candidate |
| Consumers | catalog_projection, impact_assessor |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.22 `jp.raos.catalog.offer_observed.v1`

Offerの新Observationが保存された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-offer-observed-v1.schema.json |
| Producer | catalog |
| Channel | freshness.events |
| Aggregate | offer |
| Consumers | freshness_assessor, impact_assessor, offer_projection |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-004, FR-011, FR-012 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.23 `jp.raos.catalog.offer_unavailable.v1`

Offerが利用不能と判断された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-offer-unavailable-v1.schema.json |
| Producer | catalog |
| Channel | freshness.events |
| Aggregate | offer |
| Consumers | impact_assessor, public_projection, alerting |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-012 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.24 `jp.raos.catalog.affiliate_link_invalid.v1`

Affiliate Linkが安全条件を満たさない。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-catalog-affiliate-link-invalid-v1.schema.json |
| Producer | catalog |
| Channel | freshness.events |
| Aggregate | offer |
| Consumers | public_projection, alerting, impact_assessor |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-011, FR-019 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.25 `jp.raos.evidence.source_snapshot_captured.v1`

不変Source Snapshotが取得・検証された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-evidence-source-snapshot-captured-v1.schema.json |
| Producer | evidence |
| Channel | ingestion.events |
| Aggregate | source_snapshot |
| Consumers | fact_extractor, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.26 `jp.raos.evidence.facts_extracted.v1`

Fact候補が抽出された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-evidence-facts-extracted-v1.schema.json |
| Producer | evidence |
| Channel | quality.events |
| Aggregate | source_snapshot |
| Consumers | source_packet_builder |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-004, FR-007 |
| Implementation Slice | SLICE-010 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.27 `jp.raos.evidence.source_packet_ready.v1`

Source Packet Versionがreview可能になった。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-evidence-source-packet-ready-v1.schema.json |
| Producer | evidence |
| Channel | quality.events |
| Aggregate | source_packet |
| Consumers | review_queue, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-006, FR-007 |
| Implementation Slice | SLICE-010 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.28 `jp.raos.evidence.source_packet_approved.v1`

Source Packet Versionが人間承認された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-evidence-source-packet-approved-v1.schema.json |
| Producer | evidence |
| Channel | quality.events |
| Aggregate | source_packet |
| Consumers | draft_workflow, quality_workflow |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-006 |
| Implementation Slice | SLICE-010 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.29 `jp.raos.evidence.claims_extracted.v1`

Article Claim群が抽出された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-evidence-claims-extracted-v1.schema.json |
| Producer | evidence |
| Channel | quality.events |
| Aggregate | article_version |
| Consumers | quality_engine |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-007, FR-008 |
| Implementation Slice | SLICE-012 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.30 `jp.raos.evidence.claim_unsupported.v1`

主要Claimの根拠不足が検出された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-evidence-claim-unsupported-v1.schema.json |
| Producer | evidence |
| Channel | quality.events |
| Aggregate | claim |
| Consumers | quality_engine, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-007, FR-008 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.31 `jp.raos.editorial.article_plan_approved.v1`

Article Planが承認された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-editorial-article-plan-approved-v1.schema.json |
| Producer | editorial |
| Channel | quality.events |
| Aggregate | article_plan |
| Consumers | source_packet_workflow |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-001 |
| Implementation Slice | SLICE-006 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.32 `jp.raos.editorial.article_created.v1`

Articleが作成された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-editorial-article-created-v1.schema.json |
| Producer | editorial |
| Channel | ops.events |
| Aggregate | article |
| Consumers | admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-001 |
| Implementation Slice | SLICE-012 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.33 `jp.raos.editorial.draft_generated.v1`

AI Draft Article Versionが保存された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-editorial-draft-generated-v1.schema.json |
| Producer | editorial |
| Channel | ai.events |
| Aggregate | article_version |
| Consumers | claim_extractor, quality_workflow, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-006, FR-007, FR-018 |
| Implementation Slice | SLICE-012 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.34 `jp.raos.editorial.article_version_submitted.v1`

Article VersionがHuman Reviewへ提出された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-editorial-article-version-submitted-v1.schema.json |
| Producer | editorial |
| Channel | publication.events |
| Aggregate | article_version |
| Consumers | review_assignment_workflow |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.35 `jp.raos.ai.job_requested.v1`

AI Jobが登録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ai-job-requested-v1.schema.json |
| Producer | ai |
| Channel | ai.events |
| Aggregate | ai_job |
| Consumers | ai_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.36 `jp.raos.ai.job_succeeded.v1`

AI JobがSchema検証を通過して成功した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ai-job-succeeded-v1.schema.json |
| Producer | ai |
| Channel | ai.events |
| Aggregate | ai_job |
| Consumers | workflow_router, cost_allocator, ai_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.37 `jp.raos.ai.job_failed.v1`

AI Jobが失敗した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ai-job-failed-v1.schema.json |
| Producer | ai |
| Channel | ai.events |
| Aggregate | ai_job |
| Consumers | workflow_router, alerting, ai_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.38 `jp.raos.ai.policy_assist_completed.v1`

AI Policy assistが完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ai-policy-assist-completed-v1.schema.json |
| Producer | ai |
| Channel | quality.events |
| Aggregate | quality_check_run |
| Consumers | quality_engine |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-008, FR-018 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.39 `jp.raos.ai.evaluation_completed.v1`

AI Evaluation Suiteが完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-ai-evaluation-completed-v1.schema.json |
| Producer | ai |
| Channel | ai.events |
| Aggregate | evaluation_suite |
| Consumers | release_gate, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.40 `jp.raos.policy.quality_check_completed.v1`

Quality Check結果が確定した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-policy-quality-check-completed-v1.schema.json |
| Producer | policy |
| Channel | quality.events |
| Aggregate | quality_check_run |
| Consumers | review_workflow, publication_guard, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-008, FR-009 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.41 `jp.raos.policy.blocking_finding_raised.v1`

Blocking Findingが発生した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-policy-blocking-finding-raised-v1.schema.json |
| Producer | policy |
| Channel | quality.events |
| Aggregate | finding |
| Consumers | publication_guard, alerting, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.42 `jp.raos.policy.finding_resolved.v1`

Findingが解決または判断された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-policy-finding-resolved-v1.schema.json |
| Producer | policy |
| Channel | quality.events |
| Aggregate | finding |
| Consumers | quality_recheck_assist |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-008 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.43 `jp.raos.policy.policy_bundle_activated.v1`

Policy Bundle Versionが有効化された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-policy-policy-bundle-activated-v1.schema.json |
| Producer | policy |
| Channel | quality.events |
| Aggregate | policy_bundle |
| Consumers | policy_recheck_scheduler, publication_guard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-017, FR-020 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.44 `jp.raos.policy.gate_decision_recorded.v1`

Gate Decisionが記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-policy-gate-decision-recorded-v1.schema.json |
| Producer | policy |
| Channel | quality.events |
| Aggregate | gate_decision |
| Consumers | release_gate, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-017, FR-020 |
| Implementation Slice | SLICE-025 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.45 `jp.raos.policy.policy_recheck_completed.v1`

Policy Bundle影響再検査が完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-policy-policy-recheck-completed-v1.schema.json |
| Producer | policy |
| Channel | quality.events |
| Aggregate | policy_bundle |
| Consumers | admin_dashboard, alerting |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-017 |
| Implementation Slice | SLICE-013 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.46 `jp.raos.publishing.review_assigned.v1`

Human Reviewが割り当てられた。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-review-assigned-v1.schema.json |
| Producer | publishing |
| Channel | notification.events |
| Aggregate | review_assignment |
| Consumers | notification_policy, admin_dashboard |
| Classification | CONFIDENTIAL |
| Ordering | aggregate_version |
| Requirements | FR-009 |
| Implementation Slice | SLICE-014 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.47 `jp.raos.publishing.review_decision_recorded.v1`

Human Review Decisionが不変記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-review-decision-recorded-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | review_decision |
| Consumers | approval_workflow, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-009, FR-020 |
| Implementation Slice | SLICE-014 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.48 `jp.raos.publishing.approval_granted.v1`

有効Approvalが記録された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-approval-granted-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | approval |
| Consumers | publication_workflow, admin_dashboard |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-009, FR-020 |
| Implementation Slice | SLICE-014 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.49 `jp.raos.publishing.approval_revoked.v1`

Approvalが取消された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-approval-revoked-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | approval |
| Consumers | publication_guard, impact_assessor, alerting |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-009, FR-020 |
| Implementation Slice | SLICE-014 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.50 `jp.raos.publishing.snapshot_built.v1`

Publication Snapshotが不変保存された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-snapshot-built-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | publication_candidate |
| Consumers | publication_workflow, admin_dashboard |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-010 |
| Implementation Slice | SLICE-015 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.51 `jp.raos.publishing.article_published.v1`

Snapshotが公開Projectionへ反映された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-article-published-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | publication |
| Consumers | cache_invalidator, sitemap_builder, analytics_route_map, freshness_scheduler |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.52 `jp.raos.publishing.article_unpublished.v1`

Publicationが非公開化された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-article-unpublished-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | publication |
| Consumers | cache_invalidator, sitemap_builder, analytics_route_map |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.53 `jp.raos.publishing.article_rolled_back.v1`

Publicationが旧Snapshotへ切替された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-article-rolled-back-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | publication |
| Consumers | cache_invalidator, alerting, audit_projection |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-010, FR-019, FR-020 |
| Implementation Slice | SLICE-015 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.54 `jp.raos.publishing.public_projection_rebuilt.v1`

Public Projection再構築が完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-publishing-public-projection-rebuilt-v1.schema.json |
| Producer | publishing |
| Channel | publication.events |
| Aggregate | publication |
| Consumers | cache_invalidator, ops_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-010 |
| Implementation Slice | SLICE-016 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.55 `jp.raos.freshness.staleness_assessed.v1`

Freshness状態が判定された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-freshness-staleness-assessed-v1.schema.json |
| Producer | freshness |
| Channel | freshness.events |
| Aggregate | offer |
| Consumers | public_projection, refresh_scheduler, impact_assessor |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-012 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.56 `jp.raos.freshness.refresh_completed.v1`

Refresh Batchが完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-freshness-refresh-completed-v1.schema.json |
| Producer | freshness |
| Channel | freshness.events |
| Aggregate | refresh_run |
| Consumers | admin_dashboard, alerting, daily_metrics |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-011, FR-012 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.57 `jp.raos.freshness.link_check_completed.v1`

Affiliate Link Check Batchが完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-freshness-link-check-completed-v1.schema.json |
| Producer | freshness |
| Channel | freshness.events |
| Aggregate | refresh_run |
| Consumers | public_projection, impact_assessor, alerting |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-011 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.58 `jp.raos.freshness.impact_detected.v1`

公開・Claimへの影響が検出された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-freshness-impact-detected-v1.schema.json |
| Producer | freshness |
| Channel | freshness.events |
| Aggregate | impact_assessment |
| Consumers | action_candidate_generator, publication_guard, alerting |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-012, FR-016 |
| Implementation Slice | SLICE-018 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.59 `jp.raos.analytics.import_completed.v1`

Analytics source取込が完了した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-analytics-import-completed-v1.schema.json |
| Producer | analytics |
| Channel | analytics.events |
| Aggregate | import_run |
| Consumers | daily_metric_rollup, data_quality_monitor |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.60 `jp.raos.analytics.daily_metrics_updated.v1`

Article日次指標が更新された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-analytics-daily-metrics-updated-v1.schema.json |
| Producer | analytics |
| Channel | analytics.events |
| Aggregate | daily_article_metric |
| Consumers | unit_economics_calculator, action_candidate_generator, dashboard_projection |
| Classification | INTERNAL |
| Ordering | aggregate_version |
| Requirements | FR-013, FR-015, FR-016 |
| Implementation Slice | SLICE-021 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.61 `jp.raos.finance.revenue_import_dry_run_ready.v1`

Revenue Import Previewが人間確認可能になった。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-finance-revenue-import-dry-run-ready-v1.schema.json |
| Producer | finance |
| Channel | analytics.events |
| Aggregate | revenue_import |
| Consumers | admin_dashboard, notification_policy |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.62 `jp.raos.finance.revenue_import_committed.v1`

Revenue Provider Fact取込が確定した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-finance-revenue-import-committed-v1.schema.json |
| Producer | finance |
| Channel | analytics.events |
| Aggregate | revenue_import |
| Consumers | unit_economics_calculator, audit_projection |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-014, FR-020 |
| Implementation Slice | SLICE-020 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.63 `jp.raos.finance.commission_status_changed.v1`

Provider Commission statusが新Eventで変化した。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-finance-commission-status-changed-v1.schema.json |
| Producer | finance |
| Channel | analytics.events |
| Aggregate | commission |
| Consumers | unit_economics_calculator, dashboard_projection |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-014, FR-015 |
| Implementation Slice | SLICE-020 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

### 10.64 `jp.raos.finance.unit_economics_calculated.v1`

確定Unit Economics Snapshotが算出された。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/events/jp-raos-finance-unit-economics-calculated-v1.schema.json |
| Producer | finance |
| Channel | analytics.events |
| Aggregate | unit_economics_snapshot |
| Consumers | dashboard_projection, action_candidate_generator |
| Classification | RESTRICTED |
| Ordering | aggregate_version |
| Requirements | FR-015, FR-016 |
| Implementation Slice | SLICE-021 |

**Compatibility**: 同一`.v1`ではoptional Field追加のみ。意味変更、型変更、required追加、Enum削除は`.v2`を発行する。Consumerは未知optional Fieldを無視する。

## 11. Worker Job Contract

Jobは実行要求でありEventではない。HTTP Command、Scheduler、Domain OrchestratorだけがAllowlist済みJobを作成できる。Queue配送はat-least-onceであり、Workerは同一Jobを複数回受信しても業務副作用を一度に保つ。

### 11.1 Job State

| State | Meaning |
| --- | --- |
| REQUESTED | DBに登録済み。 |
| QUEUED | Queue投入済み。 |
| RUNNING | 有効Leaseで実行中。 |
| SUCCEEDED | 結果Artifact/StateがCommit済み。 |
| FAILED_RETRYABLE | 分類上再試行可能な失敗。 |
| RETRY_SCHEDULED | 次回available_at設定済み。 |
| FAILED_TERMINAL | 自動再試行しない終端失敗。 |
| QUARANTINED | 契約・Security・Data問題で隔離。 |
| CANCELLED | 明示取消済み。 |
| EXPIRED | deadline超過。 |

### 11.2 Retry分類

| Class | Automatic retry | Examples | Action |
| --- | --- | --- | --- |
| TRANSIENT | yes | timeout, 429, temporary 5xx | jitter付き指数backoff。Retry-After優先。 |
| AUTH | no | 401, invalid credential | Secret/config修復。 |
| CONTRACT | no | Schema drift, required field missing | Quarantine＋fixture更新。 |
| POLICY | no | prohibited content, publication blocker | 人間修正。 |
| PERMANENT | no | not found, invalid business state | 新Input/Command。 |
| BUDGET | no | cost/runtime cap | 明示承認またはscope縮小。 |

| Job Type | Queue | Consumer | Attempts | Timeout(s) | Requirements |
| --- | --- | --- | --- | --- | --- |
| portfolio.assess_opportunity.v1 | quality | worker-general | 3 | 300 | FR-005, FR-016 |
| portfolio.generate_action_candidates.v1 | analytics | worker-general | 3 | 900 | FR-016 |
| catalog.rakuten_item_search.v1 | ingestion | worker-general | 5 | 120 | FR-002, FR-004 |
| catalog.rakuten_genre_sync.v1 | ingestion | worker-general | 5 | 600 | FR-002 |
| catalog.normalize_ingestion.v1 | ingestion | worker-general | 3 | 900 | FR-002, FR-003, FR-004 |
| catalog.group_product_candidates.v1 | ingestion | worker-general | 3 | 900 | FR-003 |
| catalog.refresh_offer.v1 | freshness | worker-general | 5 | 600 | FR-011, FR-012 |
| evidence.capture_source_snapshot.v1 | ingestion | worker-general | 3 | 180 | FR-004 |
| evidence.extract_facts.v1 | quality | worker-general | 3 | 600 | FR-004, FR-007 |
| evidence.build_source_packet.v1 | quality | worker-general | 3 | 600 | FR-006, FR-007 |
| ai.classify_search_intent.v1 | ai | worker-ai | 2 | 300 | FR-006, FR-018 |
| ai.assess_opportunity.v1 | ai | worker-ai | 2 | 300 | FR-005, FR-006, FR-018 |
| ai.generate_article_draft.v1 | ai | worker-ai | 2 | 900 | FR-006, FR-007, FR-018 |
| ai.extract_claims.v1 | ai | worker-ai | 2 | 600 | FR-007, FR-018 |
| ai.policy_assist.v1 | ai | worker-ai | 2 | 600 | FR-008, FR-018 |
| ai.evaluate_output.v1 | ai | worker-ai | 2 | 7200 | FR-018 |
| ai.generic_task.v1 | ai | worker-ai | 2 | 1800 | FR-006, FR-018 |
| quality.evaluate_article.v1 | quality | worker-general | 3 | 1200 | FR-007, FR-008 |
| quality.recheck_policy_bundle.v1 | quality | worker-general | 3 | 14400 | FR-017 |
| publishing.build_snapshot.v1 | publication | worker-publish | 3 | 600 | FR-009, FR-010 |
| publishing.publish_snapshot.v1 | publication | worker-publish | 3 | 600 | FR-010, FR-019 |
| publishing.unpublish.v1 | publication | worker-publish | 3 | 600 | FR-010, FR-019 |
| publishing.rollback.v1 | publication | worker-publish | 3 | 600 | FR-010, FR-019 |
| publishing.rebuild_public_projection.v1 | publication | worker-publish | 3 | 7200 | FR-010, FR-019 |
| freshness.run_refresh_batch.v1 | freshness | worker-general | 3 | 14400 | FR-011, FR-012 |
| freshness.check_affiliate_link.v1 | freshness | worker-general | 3 | 1800 | FR-011 |
| freshness.assess_change_impact.v1 | freshness | worker-general | 3 | 1800 | FR-012, FR-016, FR-017 |
| analytics.import_search_console.v1 | analytics | worker-general | 5 | 3600 | FR-013 |
| analytics.import_ga4.v1 | analytics | worker-general | 5 | 3600 | FR-013 |
| analytics.import_keyword_rank_csv.v1 | analytics | worker-general | 3 | 3600 | FR-013 |
| analytics.import_provider_data.v1 | analytics | worker-general | 3 | 60 | FR-013 |
| analytics.rollup_daily_metrics.v1 | analytics | worker-general | 3 | 3600 | FR-013, FR-015 |
| finance.parse_revenue_csv.v1 | analytics | worker-general | 3 | 3600 | FR-014 |
| finance.commit_revenue_import.v1 | analytics | worker-general | 3 | 3600 | FR-014, FR-020 |
| finance.calculate_unit_economics.v1 | analytics | worker-general | 3 | 3600 | FR-015 |
| ops.export_audit.v1 | analytics | worker-general | 3 | 7200 | FR-020 |
| ops.send_notification.v1 | notification | worker-general | 5 | 120 | FR-020 |
| ops.rebuild_readmodel.v1 | publication | worker-publish | 3 | 14400 | FR-010, FR-013, FR-019 |
| ops.retention_sweep.v1 | analytics | worker-general | 2 | 14400 | FR-020 |

### 11.3 `portfolio.assess_opportunity.v1`

編集可能性・事業性・Compliance Riskを分離評価する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/portfolio-assess-opportunity-v1.schema.json |
| Queue | quality |
| Producer | admin_api, scheduler |
| Consumer | worker-general |
| Idempotency basis | category_id, intent_cluster_id, keyword_id, formula_version, source_watermark |
| Lock scope | category+keyword |
| Max attempts | 3 |
| Timeout seconds | 300 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.portfolio.opportunity_assessed.v1 |
| Requirements | FR-005, FR-016 |
| Implementation Slice | SLICE-006 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.4 `portfolio.generate_action_candidates.v1`

更新・統合・削除・新規作成候補を生成する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/portfolio-generate-action-candidates-v1.schema.json |
| Queue | analytics |
| Producer | scheduler, analytics_event |
| Consumer | worker-general |
| Idempotency basis | site_id, scope_id, as_of_date, algorithm_version |
| Lock scope | site+algorithm_version |
| Max attempts | 3 |
| Timeout seconds | 900 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.portfolio.action_candidates_generated.v1 |
| Requirements | FR-016 |
| Implementation Slice | SLICE-021 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.5 `catalog.rakuten_item_search.v1`

楽天市場商品検索APIを呼び原本を不変保存する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/catalog-rakuten-item-search-v1.schema.json |
| Queue | ingestion |
| Producer | admin_api, scheduler |
| Consumer | worker-general |
| Idempotency basis | provider_endpoint_id, api_version, canonical_query_hash, purpose_context |
| Lock scope | provider+request_fingerprint |
| Max attempts | 5 |
| Timeout seconds | 120 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.catalog.ingestion_completed.v1 |
| Requirements | FR-002, FR-004 |
| Implementation Slice | SLICE-008 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.6 `catalog.rakuten_genre_sync.v1`

楽天Genre taxonomyを同期する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/catalog-rakuten-genre-sync-v1.schema.json |
| Queue | ingestion |
| Producer | scheduler, admin_api |
| Consumer | worker-general |
| Idempotency basis | provider_endpoint_id, root_genre_id, api_version, sync_date |
| Lock scope | provider+root_genre |
| Max attempts | 5 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.catalog.genre_sync_completed.v1 |
| Requirements | FR-002 |
| Implementation Slice | SLICE-008 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.7 `catalog.normalize_ingestion.v1`

Raw provider responseをProduct Candidate/Observationへ正規化する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/catalog-normalize-ingestion-v1.schema.json |
| Queue | ingestion |
| Producer | catalog.ingestion_completed |
| Consumer | worker-general |
| Idempotency basis | ingestion_request_id, normalizer_version, expected_sha256 |
| Lock scope | ingestion_request |
| Max attempts | 3 |
| Timeout seconds | 900 |
| Retry classes | TRANSIENT, DATA_ROW |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.catalog.candidates_normalized.v1 |
| Requirements | FR-002, FR-003, FR-004 |
| Implementation Slice | SLICE-009 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.8 `catalog.group_product_candidates.v1`

候補をCanonical Productへ提案Groupingする。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/catalog-group-product-candidates-v1.schema.json |
| Queue | ingestion |
| Producer | scheduler, candidate_normalized |
| Consumer | worker-general |
| Idempotency basis | sorted_candidate_ids, rule_version |
| Lock scope | candidate_set |
| Max attempts | 3 |
| Timeout seconds | 900 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.catalog.grouping_proposals_created.v1 |
| Requirements | FR-003 |
| Implementation Slice | SLICE-009 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.9 `catalog.refresh_offer.v1`

Offerの価格・在庫・集計レビュー値・Affiliate Linkを再取得する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/catalog-refresh-offer-v1.schema.json |
| Queue | freshness |
| Producer | admin_api, scheduler, staleness_event |
| Consumer | worker-general |
| Idempotency basis | sorted_offer_ids, fields, refresh_window |
| Lock scope | offer |
| Max attempts | 5 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.catalog.offer_observed.v1, jp.raos.freshness.staleness_assessed.v1 |
| Requirements | FR-011, FR-012 |
| Implementation Slice | SLICE-018 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.10 `evidence.capture_source_snapshot.v1`

Allowlistされた一次Sourceを安全に取得しSnapshot化する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/evidence-capture-source-snapshot-v1.schema.json |
| Queue | ingestion |
| Producer | admin_api |
| Consumer | worker-general |
| Idempotency basis | source_id, normalized_external_reference, capture_policy_version, capture_window |
| Lock scope | source+external_reference |
| Max attempts | 3 |
| Timeout seconds | 180 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.evidence.source_snapshot_captured.v1 |
| Requirements | FR-004 |
| Implementation Slice | SLICE-010 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.11 `evidence.extract_facts.v1`

検証済みSnapshotから型付きFact候補を抽出する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/evidence-extract-facts-v1.schema.json |
| Queue | quality |
| Producer | source_snapshot_captured, admin_api |
| Consumer | worker-general |
| Idempotency basis | source_snapshot_id, extractor_version |
| Lock scope | source_snapshot |
| Max attempts | 3 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.evidence.facts_extracted.v1 |
| Requirements | FR-004, FR-007 |
| Implementation Slice | SLICE-010 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.12 `evidence.build_source_packet.v1`

記事計画向けのVersioned Source Packetを構築する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/evidence-build-source-packet-v1.schema.json |
| Queue | quality |
| Producer | admin_api, fact_event |
| Consumer | worker-general |
| Idempotency basis | article_plan_id, packet_type, sorted_fact_ids, sorted_product_ids, builder_version |
| Lock scope | source_packet |
| Max attempts | 3 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.evidence.source_packet_ready.v1 |
| Requirements | FR-006, FR-007 |
| Implementation Slice | SLICE-010 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.13 `ai.classify_search_intent.v1`

Keyword群を検索意図へ構造化分類する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-classify-search-intent-v1.schema.json |
| Queue | ai |
| Producer | admin_api, portfolio_job |
| Consumer | worker-ai |
| Idempotency basis | source_packet_hash, keyword_ids, prompt_version, model_route, output_schema |
| Lock scope | keyword_batch |
| Max attempts | 2 |
| Timeout seconds | 300 |
| Retry classes | TRANSIENT, SCHEMA_OUTPUT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ai.job_succeeded.v1 |
| Requirements | FR-006, FR-018 |
| Implementation Slice | SLICE-011 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.14 `ai.assess_opportunity.v1`

一次情報に基づく定性的機会評価補助を生成する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-assess-opportunity-v1.schema.json |
| Queue | ai |
| Producer | portfolio_job |
| Consumer | worker-ai |
| Idempotency basis | source_packet_hash, category_id, keyword_id, prompt_version, model_route |
| Lock scope | assessment_subject |
| Max attempts | 2 |
| Timeout seconds | 300 |
| Retry classes | TRANSIENT, SCHEMA_OUTPUT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ai.job_succeeded.v1 |
| Requirements | FR-005, FR-006, FR-018 |
| Implementation Slice | SLICE-011 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.15 `ai.generate_article_draft.v1`

承認済みSource PacketからArticle AST Draftを生成する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-generate-article-draft-v1.schema.json |
| Queue | ai |
| Producer | admin_api |
| Consumer | worker-ai |
| Idempotency basis | article_plan_id, source_packet_hash, based_on_version, prompt_version, model_route, output_schema, instruction_hash |
| Lock scope | article_plan_generation |
| Max attempts | 2 |
| Timeout seconds | 900 |
| Retry classes | TRANSIENT, SCHEMA_OUTPUT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.editorial.draft_generated.v1, jp.raos.ai.job_succeeded.v1 |
| Requirements | FR-006, FR-007, FR-018 |
| Implementation Slice | SLICE-012 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.16 `ai.extract_claims.v1`

Article ASTからClaimを抽出しEvidence参照候補を返す。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-extract-claims-v1.schema.json |
| Queue | ai |
| Producer | draft_generated |
| Consumer | worker-ai |
| Idempotency basis | article_body_sha256, source_packet_hash, prompt_version, model_route |
| Lock scope | article_version_claims |
| Max attempts | 2 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT, SCHEMA_OUTPUT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.evidence.claims_extracted.v1 |
| Requirements | FR-007, FR-018 |
| Implementation Slice | SLICE-012 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.17 `ai.policy_assist.v1`

Policy Ruleの補助判定を構造化出力する。最終判定権限は持たない。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-policy-assist-v1.schema.json |
| Queue | ai |
| Producer | quality_job |
| Consumer | worker-ai |
| Idempotency basis | article_body_sha256, source_packet_hash, policy_bundle_hash, prompt_version, model_route |
| Lock scope | quality_run |
| Max attempts | 2 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT, SCHEMA_OUTPUT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ai.policy_assist_completed.v1 |
| Requirements | FR-008, FR-018 |
| Implementation Slice | SLICE-013 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.18 `ai.evaluate_output.v1`

固定Evaluation DatasetでPrompt/Model Routeを評価する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-evaluate-output-v1.schema.json |
| Queue | ai |
| Producer | admin_api, ci |
| Consumer | worker-ai |
| Idempotency basis | suite_code, suite_version, prompt_versions, route_versions |
| Lock scope | evaluation_suite |
| Max attempts | 2 |
| Timeout seconds | 7200 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ai.evaluation_completed.v1 |
| Requirements | FR-018 |
| Implementation Slice | SLICE-011 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.19 `ai.generic_task.v1`

登録済みTask Definitionを明示実行する汎用入口。allowlist taskのみ。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ai-generic-task-v1.schema.json |
| Queue | ai |
| Producer | admin_api |
| Consumer | worker-ai |
| Idempotency basis | task_code, source_packet_hash, target_refs, prompt_route, input_hash |
| Lock scope | task_defined |
| Max attempts | 2 |
| Timeout seconds | 1800 |
| Retry classes | TRANSIENT, SCHEMA_OUTPUT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ai.job_succeeded.v1 |
| Requirements | FR-006, FR-018 |
| Implementation Slice | SLICE-011 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.20 `quality.evaluate_article.v1`

Deterministic rule、Claim Evidence、AI assistを統合して品質判定する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/quality-evaluate-article-v1.schema.json |
| Queue | quality |
| Producer | admin_api, draft_generated |
| Consumer | worker-general |
| Idempotency basis | article_body_sha256, source_packet_hash, policy_bundle_hash, check_scope |
| Lock scope | article_version+policy_bundle |
| Max attempts | 3 |
| Timeout seconds | 1200 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.policy.quality_check_completed.v1 |
| Requirements | FR-007, FR-008 |
| Implementation Slice | SLICE-013 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.21 `quality.recheck_policy_bundle.v1`

新Policy Bundleの影響記事を再検査する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/quality-recheck-policy-bundle-v1.schema.json |
| Queue | quality |
| Producer | policy_bundle_activated |
| Consumer | worker-general |
| Idempotency basis | policy_bundle_hash, scope_type, scope_id |
| Lock scope | policy_bundle+scope |
| Max attempts | 3 |
| Timeout seconds | 14400 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.policy.policy_recheck_completed.v1 |
| Requirements | FR-017 |
| Implementation Slice | SLICE-013 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.22 `publishing.build_snapshot.v1`

最終承認済みArticle Versionから不変Publication Snapshotを生成する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/publishing-build-snapshot-v1.schema.json |
| Queue | publication |
| Producer | admin_api |
| Consumer | worker-publish |
| Idempotency basis | publication_candidate_id, article_body_sha256, approval_id, quality_run_id, safe_offer_projection_generation |
| Lock scope | publication_candidate |
| Max attempts | 3 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.publishing.snapshot_built.v1 |
| Requirements | FR-009, FR-010 |
| Implementation Slice | SLICE-015 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.23 `publishing.publish_snapshot.v1`

SnapshotをPublic Read Modelへ原子的に反映する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/publishing-publish-snapshot-v1.schema.json |
| Queue | publication |
| Producer | admin_api, scheduler |
| Consumer | worker-publish |
| Idempotency basis | publication_candidate_id, publication_snapshot_id, route |
| Lock scope | public_route |
| Max attempts | 3 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.publishing.article_published.v1 |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.24 `publishing.unpublish.v1`

公開ProjectionからArticleを安全に非公開化する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/publishing-unpublish-v1.schema.json |
| Queue | publication |
| Producer | admin_api, incident_flow |
| Consumer | worker-publish |
| Idempotency basis | publication_id, current_snapshot_id, reason_class |
| Lock scope | public_route |
| Max attempts | 3 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.publishing.article_unpublished.v1 |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.25 `publishing.rollback.v1`

検証済み旧SnapshotへRollbackする。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/publishing-rollback-v1.schema.json |
| Queue | publication |
| Producer | admin_api, incident_flow |
| Consumer | worker-publish |
| Idempotency basis | publication_id, from_snapshot_id, to_snapshot_id |
| Lock scope | public_route |
| Max attempts | 3 |
| Timeout seconds | 600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.publishing.article_rolled_back.v1 |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-015 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.26 `publishing.rebuild_public_projection.v1`

不変SnapshotからPublic Read Modelを再構築する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/publishing-rebuild-public-projection-v1.schema.json |
| Queue | publication |
| Producer | internal_api, ops |
| Consumer | worker-publish |
| Idempotency basis | site_id, scope_type, scope_id, snapshot_generation |
| Lock scope | projection_scope |
| Max attempts | 3 |
| Timeout seconds | 7200 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.publishing.public_projection_rebuilt.v1 |
| Requirements | FR-010, FR-019 |
| Implementation Slice | SLICE-016 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.27 `freshness.run_refresh_batch.v1`

Freshness Policyに従い対象をbatch更新する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/freshness-run-refresh-batch-v1.schema.json |
| Queue | freshness |
| Producer | admin_api, scheduler |
| Consumer | worker-general |
| Idempotency basis | site_id, scope_type, scope_id, policy_version, refresh_window |
| Lock scope | refresh_scope |
| Max attempts | 3 |
| Timeout seconds | 14400 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.freshness.refresh_completed.v1 |
| Requirements | FR-011, FR-012 |
| Implementation Slice | SLICE-018 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.28 `freshness.check_affiliate_link.v1`

Affiliate URLを改変せずdestination/reachabilityを検査する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/freshness-check-affiliate-link-v1.schema.json |
| Queue | freshness |
| Producer | admin_api, scheduler |
| Consumer | worker-general |
| Idempotency basis | offer_ids, link_observation_hashes, check_method, check_window |
| Lock scope | offer |
| Max attempts | 3 |
| Timeout seconds | 1800 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.freshness.link_check_completed.v1 |
| Requirements | FR-011 |
| Implementation Slice | SLICE-018 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.29 `freshness.assess_change_impact.v1`

商品・価格・Policy変更のClaim/公開影響を計算する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/freshness-assess-change-impact-v1.schema.json |
| Queue | freshness |
| Producer | admin_api, catalog_event |
| Consumer | worker-general |
| Idempotency basis | change_type, changed_entity_id, change_version |
| Lock scope | changed_entity |
| Max attempts | 3 |
| Timeout seconds | 1800 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.freshness.impact_detected.v1 |
| Requirements | FR-012, FR-016, FR-017 |
| Implementation Slice | SLICE-018 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.30 `analytics.import_search_console.v1`

Search Console Search Analyticsを日次取込する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/analytics-import-search-console-v1.schema.json |
| Queue | analytics |
| Producer | scheduler, admin_api |
| Consumer | worker-general |
| Idempotency basis | site_id, date_range, dimensions, data_state, adapter_version |
| Lock scope | site+date_range+source |
| Max attempts | 5 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.analytics.import_completed.v1 |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.31 `analytics.import_ga4.v1`

GA4 Data APIの非個人集計値を取込する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/analytics-import-ga4-v1.schema.json |
| Queue | analytics |
| Producer | scheduler, admin_api |
| Consumer | worker-general |
| Idempotency basis | site_id, date_range, dimensions, metrics, adapter_version |
| Lock scope | site+date_range+source |
| Max attempts | 5 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.analytics.import_completed.v1 |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.32 `analytics.import_keyword_rank_csv.v1`

許諾済み順位CSVをCanonical Observationへ取込する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/analytics-import-keyword-rank-csv-v1.schema.json |
| Queue | analytics |
| Producer | admin_api |
| Consumer | worker-general |
| Idempotency basis | source_sha256, parser_version |
| Lock scope | source_artifact |
| Max attempts | 3 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT, DATA_ROW |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.analytics.import_completed.v1 |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.33 `analytics.import_provider_data.v1`

source_typeに応じて許可済みAnalytics Adapter Jobへdispatchする。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/analytics-import-provider-data-v1.schema.json |
| Queue | analytics |
| Producer | admin_api |
| Consumer | worker-general |
| Idempotency basis | site_id, source_type, date_range, dimensions |
| Lock scope | site+source+date_range |
| Max attempts | 3 |
| Timeout seconds | 60 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ops.child_jobs_created.v1 |
| Requirements | FR-013 |
| Implementation Slice | SLICE-019 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.34 `analytics.rollup_daily_metrics.v1`

GSC、GA4、first-party clickをArticle日次指標へ集計する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/analytics-rollup-daily-metrics-v1.schema.json |
| Queue | analytics |
| Producer | scheduler, import_event |
| Consumer | worker-general |
| Idempotency basis | site_id, date_range, source_watermarks, calculation_version |
| Lock scope | site+metric_date |
| Max attempts | 3 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.analytics.daily_metrics_updated.v1 |
| Requirements | FR-013, FR-015 |
| Implementation Slice | SLICE-021 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.35 `finance.parse_revenue_csv.v1`

Revenue原本をscan・parseしDry Run Previewを作る。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/finance-parse-revenue-csv-v1.schema.json |
| Queue | analytics |
| Producer | admin_api |
| Consumer | worker-general |
| Idempotency basis | source_sha256, parser_version_id, dry_run |
| Lock scope | source_sha256 |
| Max attempts | 3 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT, DATA_ROW |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.finance.revenue_import_dry_run_ready.v1 |
| Requirements | FR-014 |
| Implementation Slice | SLICE-020 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.36 `finance.commit_revenue_import.v1`

確認値を再照合しProvider Factを不変取込する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/finance-commit-revenue-import-v1.schema.json |
| Queue | analytics |
| Producer | admin_api |
| Consumer | worker-general |
| Idempotency basis | revenue_import_id, source_sha256, preview_hash |
| Lock scope | provider+period+source_sha |
| Max attempts | 3 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.finance.revenue_import_committed.v1, jp.raos.finance.commission_status_changed.v1 |
| Requirements | FR-014, FR-020 |
| Implementation Slice | SLICE-020 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.37 `finance.calculate_unit_economics.v1`

確定成果・費用・trafficからEPC/RPM/貢献利益を算出する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/finance-calculate-unit-economics-v1.schema.json |
| Queue | analytics |
| Producer | scheduler, revenue_event, metric_event |
| Consumer | worker-general |
| Idempotency basis | scope, period_month, calculation_version, source_watermarks |
| Lock scope | scope+period_month |
| Max attempts | 3 |
| Timeout seconds | 3600 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.finance.unit_economics_calculated.v1 |
| Requirements | FR-015 |
| Implementation Slice | SLICE-021 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.38 `ops.export_audit.v1`

Audit Eventをhash付きArtifactへexportする。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ops-export-audit-v1.schema.json |
| Queue | analytics |
| Producer | admin_api, scheduler |
| Consumer | worker-general |
| Idempotency basis | date_range, format, canonical_filter_hash |
| Lock scope | audit_export_range |
| Max attempts | 3 |
| Timeout seconds | 7200 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ops.audit_export_completed.v1 |
| Requirements | FR-020 |
| Implementation Slice | SLICE-023 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.39 `ops.send_notification.v1`

通知Adapterへ非正本通知を送る。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ops-send-notification-v1.schema.json |
| Queue | notification |
| Producer | domain_event, alert |
| Consumer | worker-general |
| Idempotency basis | notification_type, target_ref, event_id, recipient_group |
| Lock scope | notification_dedup |
| Max attempts | 5 |
| Timeout seconds | 120 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ops.notification_dispatched.v1 |
| Requirements | FR-020 |
| Implementation Slice | SLICE-023 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.40 `ops.rebuild_readmodel.v1`

指定Projectionを正本から再構築する。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ops-rebuild-readmodel-v1.schema.json |
| Queue | publication |
| Producer | internal_api, ops |
| Consumer | worker-publish |
| Idempotency basis | projection, scope_type, scope_id, source_generation |
| Lock scope | projection_scope |
| Max attempts | 3 |
| Timeout seconds | 14400 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ops.readmodel_rebuilt.v1 |
| Requirements | FR-010, FR-013, FR-019 |
| Implementation Slice | SLICE-023 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

### 11.41 `ops.retention_sweep.v1`

承認済みRetention Policyに従う削除候補をdry-run/executeする。

| 項目 | 契約 |
| --- | --- |
| Schema | schemas/jobs/ops-retention-sweep-v1.schema.json |
| Queue | analytics |
| Producer | scheduler |
| Consumer | worker-general |
| Idempotency basis | retention_policy_id, mode, as_of_date |
| Lock scope | retention_policy |
| Max attempts | 2 |
| Timeout seconds | 14400 |
| Retry classes | TRANSIENT |
| Non-retry | AUTH, CONTRACT, POLICY, PERMANENT, BUDGET |
| Emits | jp.raos.ops.retention_sweep_completed.v1 |
| Requirements | FR-020 |
| Implementation Slice | SLICE-025 |

**Worker acceptance**

- Lease取得後にのみ副作用を開始する。
- Commit前後のCrashを想定し、Inputと外部RequestにIdempotency Keyを伝播する。
- Result Artifact、Domain変更、Outbox Event、Job terminal stateを可能な範囲で単一Transactionまたは再開可能なStepとして保存する。
- `CONTRACT`、`POLICY`、`AUTH`、`BUDGET`を一律Transientへ変換しない。

## 12. AI Structured Output Contract

AI Providerの自然言語Responseを直接Domain Entityへ保存しない。AI Jobは承認済みSource Packet、Prompt Version、Model Route Version、Policy Bundle Version、JSON Schema Versionを固定し、Schema適合したArtifactのみ次工程へ渡す。

### 12.1 共通Guard

- `additionalProperties: false`を原則とする。
- Claim/Product/Fact参照はInput Packet内のID allowlistと照合する。
- 架空の使用体験、レビュー本文、根拠にない数値を禁止する。
- Schema violationは限定再試行し、同一Inputで無限再生成しない。
- AI出力はApproval、Publication、Kill Switch、Finance Provider Factを作成できない。

### 12.2 `article-draft-output.schema.json`

AI article draft; no authority to approve or publish.

- `$id`: `https://schemas.raos.local/ai/article-draft-output.schema.json`
- Required: `schema_version`, `article`, `claims`, `product_recommendations`, `warnings`
- Unknown fields: rejected

### 12.3 `claim-extraction-output.schema.json`

Article text to typed claims and evidence references.

- `$id`: `https://schemas.raos.local/ai/claim-extraction-output.schema.json`
- Required: `schema_version`, `claims`
- Unknown fields: rejected

### 12.4 `opportunity-assessment-output.schema.json`

Qualitative assist; numerical business score remains deterministic/configured.

- `$id`: `https://schemas.raos.local/ai/opportunity-assessment-output.schema.json`
- Required: `schema_version`, `search_intent`, `decision_criteria`, `content_gaps`, `risks`, `source_fact_ids`
- Unknown fields: rejected

### 12.5 `policy-assist-output.schema.json`

Non-authoritative candidate findings for deterministic policy engine.

- `$id`: `https://schemas.raos.local/ai/policy-assist-output.schema.json`
- Required: `schema_version`, `candidate_findings`, `overall_notes`
- Unknown fields: rejected

## 13. Import Contract

CSV等の外部Fileは、Upload、Malware/size/hash検査、Parser、Canonical Row validation、Dry Run、Reconciliation、人間Confirm、Commitの順に処理する。原本を変更せず、CanonicalizationとReject理由を別Artifactへ保存する。

### 13.2 `affiliate-click-input.schema.json`

Public beacon input.

| Field | Type | Required |
| --- | --- | --- |
| event_id | string | yes |
| occurred_at | string | yes |
| publication_id | string | yes |
| publication_snapshot_id | string / null | no |
| article_id | string | yes |
| product_id | string | yes |
| offer_id | string | yes |
| placement_id | string | yes |
| page_path | string | yes |
| anonymous_session_id | string / null | no |
| client_event_version | integer | yes |
| consent_state | string | yes |
| user_agent_class | string / null | no |

### 13.3 `keyword-rank-row.schema.json`

Permitted provider/CSV rank observation.

| Field | Type | Required |
| --- | --- | --- |
| keyword_id | string | yes |
| locale | string | yes |
| device | string | yes |
| observation_date | string | yes |
| metric_type | string | yes |
| value | number | yes |
| unit | string / null | no |
| provider_code | string | yes |
| confidence | number | yes |
| raw_row_sha256 | string / null | no |

### 13.4 `revenue-canonical-row.schema.json`

Parser version maps provider CSV into this canonical staging contract.

| Field | Type | Required |
| --- | --- | --- |
| source_row_no | integer | yes |
| provider_code | object | yes |
| provider_event_key | string | yes |
| provider_order_id_sha256 | string / null | no |
| event_type | string | yes |
| event_at | string | yes |
| ordered_at | string / null | no |
| business_month | string / null | no |
| gross_order_amount_jpy | integer / null | no |
| confirmed_order_amount_jpy | integer / null | no |
| generated_commission_jpy | integer | yes |
| confirmed_commission_jpy | integer / null | no |
| currency | object | yes |
| provider_category_code | string / null | no |
| provider_shop_code | string / null | no |
| provider_item_code | string / null | no |
| source_row_sha256 | string | yes |
| parser_warnings | array | no |
| unmapped_columns | object | no |

### 13.9 CSV Security

- Encoding、delimiter、header、row count、byte sizeをAllowlist化する。
- `=`, `+`, `-`, `@`で始まるCellをExport時にFormulaとして解釈させない。
- URL、email、free text等へPII scannerを適用する。
- Unknown columnはParser Version方針によりRejectまたは原本保持のみとし、silent dropしない。
- Source SHA-256とProvider row keyで重複Commitを防ぐ。

## 14. State Machine Contract

### 14.SM-JOB — `ops.job`

Initial: `REQUESTED`

States: `REQUESTED`, `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED_RETRYABLE`, `RETRY_SCHEDULED`, `FAILED_TERMINAL`, `QUARANTINED`, `CANCELLED`, `EXPIRED`

| From | To | Trigger |
| --- | --- | --- |
| REQUESTED | QUEUED | dispatcher accepted outbox |
| REQUESTED | CANCELLED | user cancellation before queue |
| REQUESTED | EXPIRED | deadline exceeded |
| QUEUED | RUNNING | worker acquired lease |
| QUEUED | CANCELLED | cancel request |
| QUEUED | EXPIRED | deadline exceeded |
| RUNNING | SUCCEEDED | handler committed output and inbox receipt |
| RUNNING | FAILED_RETRYABLE | retryable attempt failure |
| RUNNING | FAILED_TERMINAL | non-retryable or max attempts |
| RUNNING | QUARANTINED | contract/policy/data isolation |
| RUNNING | CANCELLED | cooperative cancellation |
| RUNNING | EXPIRED | deadline exceeded |
| FAILED_RETRYABLE | RETRY_SCHEDULED | retry policy calculated |
| RETRY_SCHEDULED | QUEUED | available_at reached |
| FAILED_RETRYABLE | FAILED_TERMINAL | retry budget exhausted |
| QUARANTINED | QUEUED | operator released with corrected handler/input |

**Guards**

- Lease and heartbeat required for RUNNING.
- Terminal states require completed_at.
- Retry never mutates prior job_attempt.

### 14.SM-ARTICLE-PLAN — `editorial.article_plan`

Initial: `IDEA`

States: `IDEA`, `PLANNED`, `SOURCES_PENDING`, `PACKET_READY`, `GENERATING`, `DRAFT`, `IN_REVIEW`, `APPROVED`, `CANCELLED`, `ARCHIVED`

| From | To | Trigger |
| --- | --- | --- |
| IDEA | PLANNED | brief completed |
| PLANNED | SOURCES_PENDING | source work requested |
| SOURCES_PENDING | PACKET_READY | approved source packet |
| PACKET_READY | GENERATING | AI job accepted |
| GENERATING | DRAFT | draft saved |
| DRAFT | IN_REVIEW | quality pass and submit |
| IN_REVIEW | APPROVED | human final decision |
| * | CANCELLED | authorized cancellation before publication |
| APPROVED | ARCHIVED | superseded plan |

**Guards**

- GENERATING requires approved Source Packet.
- APPROVED requires human approver.

### 14.SM-ARTICLE-VERSION — `editorial.article_version`

Initial: `DRAFT`

States: `DRAFT`, `AUTO_REVIEW`, `HUMAN_REVIEW`, `APPROVED`, `REJECTED`, `SUPERSEDED`

| From | To | Trigger |
| --- | --- | --- |
| DRAFT | AUTO_REVIEW | quality job started |
| AUTO_REVIEW | DRAFT | findings require edit |
| AUTO_REVIEW | HUMAN_REVIEW | quality gate passed |
| HUMAN_REVIEW | DRAFT | changes requested creates/editable draft path |
| HUMAN_REVIEW | APPROVED | valid human approval |
| HUMAN_REVIEW | REJECTED | human rejection |
| APPROVED | SUPERSEDED | new approved version |

**Guards**

- APPROVED is immutable.
- Edit after approval creates a new version.

### 14.SM-SOURCE-PACKET-VERSION — `evidence.source_packet_version`

Initial: `BUILDING`

States: `BUILDING`, `READY`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `SUPERSEDED`, `INVALID`

| From | To | Trigger |
| --- | --- | --- |
| BUILDING | READY | artifact and hash complete |
| READY | IN_REVIEW | review assigned |
| IN_REVIEW | APPROVED | human approval |
| IN_REVIEW | REJECTED | human rejection |
| APPROVED | SUPERSEDED | new approved packet |
| * | INVALID | source invalidation/corruption |

**Guards**

- APPROVED/REJECTED require human reviewer and timestamp.
- Used packet version is never overwritten.

### 14.SM-QUALITY-RUN — `policy.quality_check_run`

Initial: `RUNNING`

States: `RUNNING`, `PASSED`, `FAILED`, `ERROR`, `CANCELLED`

| From | To | Trigger |
| --- | --- | --- |
| RUNNING | PASSED | score and blocker gates pass |
| RUNNING | FAILED | quality/policy gate fails |
| RUNNING | ERROR | engine/contract error |
| RUNNING | CANCELLED | authorized cancellation |

**Guards**

- PASSED requires total>=85, factual>=18, disclosure=5, zero tolerance clear.

### 14.SM-REVIEW-ASSIGNMENT — `publishing.review_assignment`

Initial: `ASSIGNED`

States: `ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`

| From | To | Trigger |
| --- | --- | --- |
| ASSIGNED | IN_PROGRESS | assignee starts |
| IN_PROGRESS | COMPLETED | decision recorded |
| ASSIGNED | CANCELLED | authorized reassignment |
| IN_PROGRESS | CANCELLED | authorized cancellation |

**Guards**

- COMPLETED requires immutable review_decision.

### 14.SM-PUBLICATION-CANDIDATE — `publishing.publication_candidate`

Initial: `REQUESTED`

States: `REQUESTED`, `VALIDATING`, `BLOCKED`, `SNAPSHOT_READY`, `PUBLISHED`, `FAILED`, `CANCELLED`

| From | To | Trigger |
| --- | --- | --- |
| REQUESTED | VALIDATING | snapshot job begins |
| VALIDATING | BLOCKED | guard failure |
| VALIDATING | SNAPSHOT_READY | snapshot hash verified |
| SNAPSHOT_READY | PUBLISHED | projection atomically updated |
| REQUESTED | CANCELLED | authorized cancellation |
| VALIDATING | FAILED | terminal technical error |
| BLOCKED | REQUESTED | new idempotent request after remediation |

**Guards**

- No transition bypasses human approval, policy, freshness, disclosure, link and kill-switch guards.

### 14.SM-PUBLICATION — `publishing.publication`

Initial: `UNPUBLISHED`

States: `UNPUBLISHED`, `PUBLISHED`, `SUSPENDED`, `ARCHIVED`

| From | To | Trigger |
| --- | --- | --- |
| UNPUBLISHED | PUBLISHED | valid snapshot publish |
| PUBLISHED | PUBLISHED | new snapshot or rollback |
| PUBLISHED | SUSPENDED | article/site pause |
| SUSPENDED | PUBLISHED | authorized resume with valid controls |
| PUBLISHED | UNPUBLISHED | explicit unpublish |
| UNPUBLISHED | ARCHIVED | retired route |

**Guards**

- PUBLISHED requires current_snapshot_id.
- Rollback is a new publication_event, never snapshot mutation.

### 14.SM-REVENUE-IMPORT — `finance.revenue_import`

Initial: `UPLOADED`

States: `UPLOADED`, `SCANNED`, `PARSED`, `DRY_RUN_READY`, `CONFIRMED`, `IMPORTED`, `REJECTED`, `FAILED`

| From | To | Trigger |
| --- | --- | --- |
| UPLOADED | SCANNED | malware and hash checks pass |
| SCANNED | PARSED | parser completed |
| PARSED | DRY_RUN_READY | reconciliation preview complete |
| DRY_RUN_READY | CONFIRMED | human expected hash/count/amount match |
| CONFIRMED | IMPORTED | canonical provider facts committed |
| * | REJECTED | policy/data rejection |
| * | FAILED | terminal processing error |

**Guards**

- No commission mutation before CONFIRMED.
- Duplicate source SHA is rejected.

### 14.SM-INCIDENT — `ops.incident`

Initial: `DECLARED`

States: `DECLARED`, `CONTAINING`, `CONTAINED`, `RECOVERING`, `MONITORING`, `CLOSED`, `REOPENED`

| From | To | Trigger |
| --- | --- | --- |
| DECLARED | CONTAINING | commander assigned |
| CONTAINING | CONTAINED | immediate risk stopped |
| CONTAINED | RECOVERING | recovery begins |
| RECOVERING | MONITORING | service restored |
| MONITORING | CLOSED | verification and root cause recorded |
| CLOSED | REOPENED | recurrence/new evidence |
| REOPENED | CONTAINING | response resumed |

**Guards**

- Kill switch release may require incident state and elevated approval.

## 15. External Adapter Canonical Contract

AdapterはProvider固有ResponseをRaw Artifactとして保存し、Canonical DTOへ変換する。Provider FieldをCore DomainやPublic APIへ直接通過させない。

### 15.1 楽天市場商品検索

- `applicationId`、`accessKey`、`affiliateId`はSecret/Configから注入し、Log・Event・Artifact metadataへ平文保存しない。
- Provider version、request hash、response hash、取得時刻、HTTP status、rate-limit metadataを記録する。
- `affiliateUrl`はProvider issued URLとして検証し、RAOS redirect URLへ書き換えない。
- Price、availability、shipping、review count/ratingは観測時刻付きFactとし、商品本体の不変属性へ混ぜない。
- Contract driftは`RAOS-PROVIDER-002`としてQuarantineし、missing valueで静かに上書きしない。

### 15.2 Search Console・GA4

- Import単位でsite/property、date range、dimensions、API version、source watermarkを保存する。
- Aggregate/thresholding/late dataを考慮し、再取込で旧Factを破壊更新しない。
- Search query等の個人情報・機微情報を必要以上に保存しない。

### 15.3 Revenue CSV

- Provider Factは発生、確定、取消を独立Eventとして保持する。
- Direct、Estimated、Unattributed attributionを明示区分する。
- Dry Runのhash、accepted/rejected count、金額合計がConfirm requestと一致しない場合Commitしない。

## 16. Versioning・Deprecation

- HTTP major versionはPath `/api/v1`。破壊変更は原則`/api/v2`。
- OpenAPIのoptional response field追加はClientが未知Fieldを許容する前提でも、生成SDKへの影響をContract Testする。
- Request required field追加、Enum削除、意味変更、status変更は破壊変更。
- Event/Jobはtype末尾`.vN`。破壊変更は新type。旧Consumer移行完了までdual publishを期限付きで管理する。
- Deprecated HTTP APIは`Deprecation`、`Sunset`、`Link rel=successor-version`を返す。
- Schema RegistryはFile SHA-256、owner、classification、compatibility policyを保持する。

## 17. Security・Privacy

- SSRF対策: Provider/Source AdapterはHTTPS＋host allowlist、DNS/IP再検証、private/link-local/localhost拒否、redirect上限。
- Mass assignment対策: Create/Update Schemaの許可FieldのみDomain CommandへMapする。
- Broken object authorization対策: ID lookup後にSite/Category/Role scopeを必ず評価する。
- Injection対策: SQL parameterization、safe renderer、CSV formula neutralization、URL canonicalization。
- Secret redaction: Authorization、Cookie、access key、presigned query、provider raw payloadをLogから除去する。
- Data minimization: Public response、Event、Jobへ必要最小Fieldだけを含める。

## 18. Observability

- HTTP、Job、Event、Provider callに`correlation_id`、`causation_id`、`traceparent`を伝播する。
- Metric dimensionsへ生IDや自由文字列を入れず、高CardinalityをLog/Traceへ分離する。
- Operation ID、status class、latency、idempotency replay、concurrency conflict、schema violation、queue age、attempt、DLQを計測する。
- AIはtask code、model route、token、cost、schema retry、human edit distanceを計測する。
- Finance Importはsource hash、row count、accepted/rejected、amount reconciliationを監査する。

## 19. Contract Test Strategy

### 19.1 CI必須検査

1. OpenAPI/AsyncAPI/YAML/JSON Schemaの構文。
2. Operation ID、Event Type、Job Type、Error Code、Schema `$id`の一意性。
3. 全`$ref`の解決。
4. Pydantic生成Schemaと正本Schemaの差分。
5. HTTP request/response fixtureのpositive/negative validation。
6. Provider fixtureの契約差分。
7. Event/Jobの後方互換性。
8. Public responseに禁止Field/内部Schemaが含まれないこと。
9. Idempotency、If-Match、State transition、Outbox/Inbox integration test。
10. Production-like PostgreSQL/Queue/Object StorageでE2E。

### 19.2 Consumer-driven Test

Frontend/Public renderer/Worker/Projection/Adapterごとに使用FieldをFixture化する。ただしConsumer fixtureを理由に正本契約を無断拡張しない。Breaking changeはOwner承認と移行計画を要求する。

## 20. Codex実装計画

| Slice | Name | Deliverable | Upstream slices |
| --- | --- | --- | --- |
| API-SLICE-001 | Contract repository bootstrap | OpenAPI/AsyncAPI/Schema lint、Codegen、checksum、CI。 | SLICE-001, SLICE-003 |
| API-SLICE-002 | Common HTTP kernel | Problem Details、request/trace ID、auth middleware、pagination、ETag。 | SLICE-003, SLICE-005 |
| API-SLICE-003 | Idempotency and command transaction | Idempotency record、payload canonical hash、replay response。 | SLICE-004 |
| API-SLICE-004 | Job and outbox contract | Job status alignment migration、JobAccepted、dispatcher、inbox。 | SLICE-004 |
| API-SLICE-005 | Portfolio and catalog API | Portfolio/Catalog resource view、楽天ingestion command。 | SLICE-006, SLICE-008, SLICE-009 |
| API-SLICE-006 | Evidence and editorial API | Source Packet、Article AST、Claim、draft workflow。 | SLICE-010, SLICE-012 |
| API-SLICE-007 | AI and quality API | Structured output registry、AI Job、Quality/Policy results。 | SLICE-011, SLICE-013 |
| API-SLICE-008 | Review and publication API | Review/Approval/Snapshot/Publish/Rollback state guards。 | SLICE-014, SLICE-015 |
| API-SLICE-009 | Public API and click beacon | readmodel-only renderer、runtime control、non-blocking beacon。 | SLICE-016, SLICE-017 |
| API-SLICE-010 | Freshness and analytics | refresh/link check/import contracts。 | SLICE-018, SLICE-019 |
| API-SLICE-011 | Finance import | upload、scan、dry run、confirm、provider fact。 | SLICE-020 |
| API-SLICE-012 | Operations and kill switches | Job triage、audit export、incident、two kill switches。 | SLICE-022, SLICE-023 |
| API-SLICE-013 | Compatibility and gate pack | consumer fixtures、breaking-change detector、GATE evidence。 | SLICE-025 |

### 20.1 PR Rule

- 一PRは一Contract Sliceを基本とし、無関係なEndpointを追加しない。
- OpenAPI/Schema変更を先にCommitし、生成差分と実装差分を分離する。
- Request/Response Model、Router、Service、Repository、Testの依存方向を守る。
- Generated fileを手修正しない。Source Schemaへ戻す。
- Contract Testが未実装のEndpointを`implemented`として扱わない。

## 21. Open Decisions

| ID | Decision | Due |
| --- | --- | --- |
| API-OPEN-001 | Production OIDC providerとMFA/step-up claim名。 | IAM実装前。 |
| API-OPEN-002 | Public content deliveryを同一Next.js originにするか専用Public API originにするか。 | SLICE-016前。 |
| API-OPEN-003 | Presigned uploadの最大size、MIME allowlist、malware scanner。 | Finance Import前。 |
| API-OPEN-004 | 楽天成果CSVの現行Header/Encoding/Timezone/取消表現。 | 実サンプル入手後。 |
| API-OPEN-005 | Search rank providerまたはCSV contract。 | Analytics実装前。 |
| API-OPEN-006 | Event schema compatibility checkerの製品選定。 | CI bootstrap時。 |
| API-OPEN-007 | External API quota budgetとRetry-After/circuit閾値。 | Adapter load test後。 |
| API-OPEN-008 | Idempotency record保持期間。 | リスク・コスト検討後。 |
| API-OPEN-009 | Public click beacon consent modeと保持期間。 | 法務/privacy review前。 |
| API-OPEN-010 | AsyncAPI 3.1への更新時期。 | 使用Toolchainが3.1を安定対応後。 |

## 22. Official References

| ID | Title | Use | URL |
| --- | --- | --- | --- |
| REF-OAS-311 | OpenAPI Specification v3.1.1 | HTTP API記述。実装は3.2固有機能を使用せず、FastAPI/OpenAPI 3.1互換範囲に固定する。 | https://spec.openapis.org/oas/v3.1.1.html |
| REF-OAS-SCHEMA | OpenAPI 3.1 JSON Schema revision 2025-11-23 | OpenAPI文書のCI検証基準。 | https://spec.openapis.org/oas/3.1/schema/2025-11-23 |
| REF-ASYNCAPI-310 | AsyncAPI Specification 3.1.0 | 非同期チャネル、Operation、Message契約の記述。MVP文書は3.0.0互換構文のみ利用する。 | https://www.asyncapi.com/docs/reference/specification/latest |
| REF-JSONSCHEMA-2020-12 | JSON Schema Draft 2020-12 | HTTP、Event、Job、AI Structured Output、Import行の共通Schema。 | https://json-schema.org/draft/2020-12 |
| REF-RFC9457 | RFC 9457 Problem Details for HTTP APIs | エラーレスポンス application/problem+json。 | https://www.rfc-editor.org/rfc/rfc9457.html |
| REF-RFC9110 | RFC 9110 HTTP Semantics | HTTP method、status、ETag、If-Match、Retry-After。 | https://www.rfc-editor.org/rfc/rfc9110.html |
| REF-RFC9700 | RFC 9700 Best Current Practice for OAuth 2.0 Security | 管理画面OIDC/OAuth 2.0、Authorization Code＋PKCEの安全基準。 | https://www.rfc-editor.org/rfc/rfc9700.html |
| REF-RFC9745 | RFC 9745 Deprecation HTTP Response Header | API廃止予告。 | https://www.rfc-editor.org/rfc/rfc9745.html |
| REF-RFC8594 | RFC 8594 Sunset HTTP Header | API停止日通知。 | https://www.rfc-editor.org/rfc/rfc8594.html |
| REF-W3C-TRACE | W3C Trace Context | traceparent/tracestate伝播。 | https://www.w3.org/TR/trace-context/ |
| REF-CLOUDEVENTS | CloudEvents 1.0 | Domain Event Envelopeの互換フィールド。 | https://cloudevents.io/ |
| REF-FASTAPI-OAS31 | FastAPI OpenAPI 3.1 client generation guidance | FastAPI生成OpenAPIとTypeScript SDKの基準。 | https://fastapi.tiangolo.com/advanced/generate-clients/ |
| REF-PYDANTIC-JSONSCHEMA | Pydantic v2 JSON Schema 2020-12 | PythonモデルとJSON Schemaの生成・差分検査。 | https://docs.pydantic.dev/latest/concepts/json_schema/ |
| REF-RAKUTEN-ITEM-20260701 | Rakuten Ichiba Item Search API 2026-07-01 | 楽天商品取込Adapterの現行基準。 | https://webservice.rakuten.co.jp/documentation/ichiba-item-search |
| REF-GSC-SEARCHANALYTICS | Google Search Console Search Analytics query | 検索実績取込Adapter。 | https://developers.google.com/webmaster-tools/v1/searchanalytics/query |
| REF-GA4-DATA | Google Analytics Data API v1 | 集計行動指標取込Adapter。 | https://developers.google.com/analytics/devguides/reporting/data/v1 |

---

## Appendix A. Artifact Map

- `RAOS_04_openapi_public_v0.1.yaml` — Public HTTP正本。
- `RAOS_04_openapi_admin_v0.1.yaml` — Admin HTTP正本。
- `RAOS_04_openapi_internal_v0.1.yaml` — Internal HTTP正本。
- `RAOS_04_asyncapi_v0.1.yaml` — Event/Job channel正本。
- `schemas/` — JSON Schema Registry。
- `RAOS_04_*_catalog_v0.1.yaml` — Operation/Resource/Error/Event/Job/Stateの機械可読Catalog。
- `RAOS_04_contract_test_matrix_v0.1.csv` — Contract Test要求。
- `RAOS_04_traceability_matrix_v0.1.csv` — 要求追跡。
- `RAOS_04_001_contract_alignment_patch_v0.1.sql` — Job model整合Patch。

## Appendix B. Adapter Schema Inventory

| Adapter Schema | Purpose |
| --- | --- |
| `schemas/adapters/rakuten-item-search-request.schema.json` | RAOSから楽天市場商品検索API 2026-07-01 Adapterへ渡す許可済みQuery。Credentialは含めない。 |
| `schemas/adapters/rakuten-item-search-canonical-page.schema.json` | Provider responseをDomain取込前に正規化した一Page。原本Artifact参照を必須とする。 |
| `schemas/adapters/gsc-search-analytics-request.schema.json` | Search Analytics queryの許可済みRequest。 |
| `schemas/adapters/gsc-search-analytics-row.schema.json` | Search Analytics response row with explicit dimension order and source watermark. |
| `schemas/adapters/ga4-run-report-request.schema.json` | GA4 Data API v1 runReport Adapter input. |
| `schemas/adapters/ga4-metric-row.schema.json` | GA4 runReport row normalized with reporting identity and source watermark. |
| `schemas/adapters/llm-structured-task-request.schema.json` | Provider-neutral structured output request. Secrets and raw database connections are prohibited. |
| `schemas/adapters/llm-structured-task-result.schema.json` | Provider-neutral response after provider call; output still requires schema/reference/policy validation. |

楽天市場商品検索Adapterは2026-07-01版を基準とし、`formatVersion=2`、`hits<=30`、`page<=100`を明示する。一方、編集推薦を料率で歪めないため、Providerが提供するAffiliate Rate sort/filterをRAOSの許可Requestから意図的に除外する。
