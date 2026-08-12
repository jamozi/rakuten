"""Exact reviewed ST-0805 catalog inventory tests."""

from __future__ import annotations

from decimal import Decimal

from raos.domain.editorial.policy_engine import (
    CONTENT_TEST_MATRIX_SHA256,
    FindingTargetType,
    POLICY_BUNDLE_CODE,
    POLICY_CATALOG_ID,
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
    POLICY_DEFINITIONS,
    PUBLISH_THRESHOLD,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_CATALOG_ID,
    QUALITY_CATALOG_SHA256,
    QUALITY_CATALOG_VERSION,
    QUALITY_GATE_DEFINITIONS,
    QUALITY_MODEL_VERSION,
    REVIEW_CHECKLIST_ID,
    REVIEW_CHECKLIST_SHA256,
    REVIEW_CHECKLIST_VERSION,
    ZERO_TOLERANCE_LABELS,
)


EXPECTED_POLICIES = (
    (
        "POL-CONT-001",
        "BLOCKER",
        "all",
        "approved_source_packet_required",
        "deterministic",
    ),
    ("POL-CONT-002", "BLOCKER", "draft", "major_claim_evidence", "deterministic"),
    ("POL-CONT-003", "BLOCKER", "draft", "fabricated_experience", "hybrid"),
    ("POL-CONT-004", "BLOCKER", "ingest", "rakuten_review_body", "deterministic"),
    ("POL-CONT-005", "BLOCKER", "recommendation", "affiliate_bias", "deterministic"),
    ("POL-CONT-006", "BLOCKER", "content_ast", "raw_html", "schema"),
    ("POL-CONT-007", "BLOCKER", "content_ast", "manual_affiliate_url", "schema"),
    ("POL-CONT-008", "BLOCKER", "render", "disclosure_top", "deterministic"),
    ("POL-CONT-009", "BLOCKER", "render", "cta_destination", "deterministic"),
    ("POL-CONT-010", "BLOCKER", "render", "paid_link_rel", "deterministic"),
    ("POL-CONT-011", "BLOCKER", "render", "direct_affiliate_link", "deterministic"),
    ("POL-CONT-012", "BLOCKER", "render", "rakuten_api_credit", "deterministic"),
    ("POL-CONT-013", "BLOCKER", "media", "rakuten_image_integrity", "hybrid"),
    ("POL-CONT-014", "BLOCKER", "draft", "unsupported_superlative", "hybrid"),
    ("POL-CONT-015", "BLOCKER", "publication", "stale_critical_fact", "deterministic"),
    ("POL-CONT-016", "BLOCKER", "draft", "product_identity", "deterministic"),
    ("POL-CONT-017", "BLOCKER", "scope", "high_risk_claim", "hybrid"),
    ("POL-CONT-018", "BLOCKER", "publication", "human_approval", "deterministic"),
    ("POL-CONT-019", "MAJOR", "plan", "one_primary_intent", "human"),
    ("POL-CONT-020", "MAJOR", "plan", "scaled_thin_pages", "hybrid"),
    ("POL-CONT-021", "MAJOR", "draft", "competitor_copy", "hybrid"),
    ("POL-CONT-022", "MAJOR", "draft", "balanced_tradeoffs", "human"),
    ("POL-CONT-023", "MAJOR", "draft", "uncertainty_disclosure", "hybrid"),
    ("POL-CONT-024", "MAJOR", "seo", "unique_metadata", "deterministic"),
    ("POL-CONT-025", "BLOCKER", "seo", "index_state", "deterministic"),
    ("POL-CONT-026", "BLOCKER", "structured_data", "visible_match", "deterministic"),
    (
        "POL-CONT-027",
        "MAJOR",
        "structured_data",
        "multi_product_product_markup",
        "deterministic",
    ),
    ("POL-CONT-028", "MAJOR", "structured_data", "faqpage_disabled", "deterministic"),
    (
        "POL-CONT-029",
        "MAJOR",
        "structured_data",
        "rakuten_rating_markup",
        "deterministic",
    ),
    ("POL-CONT-030", "MAJOR", "seo", "query_variant_consolidation", "human"),
    ("POL-CONT-031", "MAJOR", "links", "internal_link_quality", "deterministic"),
    ("POL-CONT-032", "BLOCKER", "accessibility", "non_text_alternative", "hybrid"),
    ("POL-CONT-033", "MAJOR", "accessibility", "semantic_structure", "hybrid"),
    ("POL-CONT-034", "MAJOR", "metadata", "substantive_lastmod", "deterministic"),
    ("POL-CONT-035", "BLOCKER", "publication", "kill_switch", "deterministic"),
    ("POL-CONT-036", "BLOCKER", "publication", "snapshot_integrity", "deterministic"),
    ("POL-CONT-037", "MAJOR", "draft", "review_aggregate_inference", "hybrid"),
    ("POL-CONT-038", "MAJOR", "draft", "price_language", "hybrid"),
    ("POL-CONT-039", "BLOCKER", "media", "ai_product_depiction", "hybrid"),
    ("POL-CONT-040", "MAJOR", "publication", "safe_degradation", "deterministic"),
)


EXPECTED_POLICY_RULES = (
    "承認済みSource Packetがない記事生成・公開を禁止する",
    "主要ClaimのEvidence Coverageは100%",
    "実施記録のない使用・検証・愛用表現を禁止する",
    "楽天レビュー本文の取得・保存・要約・変形・依拠を禁止する",
    "料率・EPC・RPM・報酬・利益を推薦入力へ含めない",
    "任意HTML、Script、iframe、Style、Event Handlerを禁止する",
    "Affiliate URLの手入力を禁止し、Offer/Link Resourceから解決する",
    "広告・アフィリエイト関係を記事上部の初回表示範囲で明示する",
    "CTAは楽天市場への遷移であることを明示する",
    "Affiliate Linkへrel=sponsoredを付与する",
    "自社RedirectでAffiliate URLを中継・改変しない",
    "楽天API利用時の指定クレジットを共通Rendererへ表示する",
    "楽天提供画像の改変、文字重畳、切り抜き、縦横比破壊を禁止する",
    "母集団・範囲・時点がない最上級・唯一性を禁止する",
    "鮮度期限を超えた価格・在庫・リンク・主要仕様を最新として表示しない",
    "商品、型番、容量、色、セット、ショップOfferの同定不一致を禁止する",
    "MVPで医療・法務・金融・安全性の高リスク助言を扱わない",
    "人間の明示承認なしに公開しない",
    "一記事一主要意思決定・一主要Intent Clusterを維持する",
    "検索語、Tag、条件の組合せだけで低価値ページを量産しない",
    "競合記事は発見専用とし、根拠・転載・近似言い換えに使用しない",
    "推薦候補の不向き条件・制約・トレードオフを隠さない",
    "不明・競合・欠損を推測で埋めず、表示またはClaim除外する",
    "Title、H1、Meta Descriptionをページ固有かつ内容一致にする",
    "Draft/Preview/noindexページをSitemapへ含めず、公開CanonicalのみIndexableにする",
    "JSON-LDと可視本文の不一致、存在しないRating/Review/Offer補完を禁止する",
    "複数商品記事にProduct Product Snippet用Markupを出さない",
    "可視FAQは許可するがFAQPage JSON-LDを生成しない",
    "楽天の平均評価・件数からReview/AggregateRating JSON-LDを生成しない",
    "意味が同じ検索語Variantは単一Canonical記事へ統合する",
    "公開済み関連Routeだけへ説明的AnchorでLinkし、過剰Exact Matchを避ける",
    "情報画像・図表に同等目的の代替テキストまたは詳細説明を付与する",
    "見出し階層、表見出し、Keyboard操作、色以外の区別を維持する",
    "lastmod/Updated Atは実質的変更時のみ更新する",
    "Publication/Affiliate Link Kill Switchが有効な場合は該当出力をFail Closedする",
    "承認Version・Methodology・Policy・Evidence・SEO・Schema HashをPublication Snapshotへ固定する",
    "レビュー平均・件数だけから品質・満足・長所短所・代表意見を推定しない",
    "価格は取得時点の事実として書き、常時価格・最安保証を暗示しない",
    "実在商品の外観・仕様をAI生成画像で代替しない",
    "変動Factが失効した場合は該当Field/CTAを縮退し、推薦順位を自動変更しない",
)


def test_exact_policy_contract_identity_and_all_forty_mappings() -> None:
    assert POLICY_CATALOG_ID == "RAOS-CONTENT-POLICY-001"
    assert POLICY_CATALOG_VERSION == "0.1"
    assert POLICY_BUNDLE_CODE == "content-editorial-policy.jp.v1"
    assert POLICY_CATALOG_SHA256 == (
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a"
    )
    assert (
        tuple(
            (
                item.policy_id,
                item.severity.value,
                item.stage,
                item.code,
                item.enforcement.value,
            )
            for item in POLICY_DEFINITIONS
        )
        == EXPECTED_POLICIES
    )
    assert len({item.policy_id for item in POLICY_DEFINITIONS}) == 40
    assert tuple(item.rule for item in POLICY_DEFINITIONS) == EXPECTED_POLICY_RULES


def test_exact_quality_contract_identity_axes_weights_floors_and_threshold() -> None:
    assert QUALITY_CATALOG_ID == "RAOS-CONTENT-QG-001"
    assert QUALITY_CATALOG_VERSION == "0.1"
    assert QUALITY_MODEL_VERSION == "1.0.0"
    assert QUALITY_CATALOG_SHA256 == (
        "90ab554aa55dda335ba69bbb306772306494e2e4ba899c3d22af4a9d9a030efb"
    )
    assert PUBLISH_THRESHOLD == Decimal("85")
    assert tuple(
        (
            item.axis_id,
            item.code,
            item.name_ja,
            item.weight,
            item.blocking_floor,
        )
        for item in QUALITY_AXIS_DEFINITIONS
    ) == (
        ("QAX-001", "intent_fit", "検索意図への適合", Decimal("15"), Decimal("10")),
        ("QAX-002", "decision_value", "購買意思決定価値", Decimal("20"), Decimal("14")),
        ("QAX-003", "original_value", "独自価値", Decimal("15"), Decimal("9")),
        (
            "QAX-004",
            "evidence_accuracy",
            "事実正確性・根拠",
            Decimal("20"),
            Decimal("16"),
        ),
        (
            "QAX-005",
            "fairness_explainability",
            "公平性・説明可能性",
            Decimal("10"),
            Decimal("7"),
        ),
        ("QAX-006", "freshness", "鮮度", Decimal("10"), Decimal("7")),
        ("QAX-007", "readability_ux", "読みやすさ・UX", Decimal("5"), Decimal("3")),
        (
            "QAX-008",
            "compliance_disclosure",
            "広告・規約表示",
            Decimal("5"),
            Decimal("5"),
        ),
    )
    assert sum(
        (item.weight for item in QUALITY_AXIS_DEFINITIONS), Decimal("0")
    ) == Decimal("100")


def test_exact_thirteen_zero_tolerance_labels_are_unmapped_inventory() -> None:
    assert ZERO_TOLERANCE_LABELS == (
        "重大な事実誤り",
        "主要Claimの根拠欠落",
        "架空の使用・検証体験",
        "楽天レビュー本文の不正利用",
        "料率・収益による推薦Bias",
        "不正・不明瞭なAffiliate Link",
        "広告表示欠落",
        "商品/Variant/Offer同定ミス",
        "期限切れ価格・在庫の最新断定",
        "Prompt Injection追随",
        "Structured Dataと可視本文の重大不一致",
        "Affiliate/Public Kill Switch無視",
        "Secret/Restricted Dataの公開",
    )
    assert len(set(ZERO_TOLERANCE_LABELS)) == 13


def test_exact_twelve_gate_definitions() -> None:
    assert tuple(
        (
            item.gate_id,
            item.stage,
            item.name,
            item.pass_condition,
            item.failure_action.value,
        )
        for item in QUALITY_GATE_DEFINITIONS
    ) == (
        (
            "QG-CONT-001",
            "article_plan",
            "Article Plan Freeze",
            "Primary Intent、Decision、Article Type、Candidate Universe、対象外が明確",
            "BLOCK",
        ),
        (
            "QG-CONT-002",
            "source_packet",
            "Evidence Readiness",
            "承認済みSource Packet、商品同定、主要Fact、鮮度、欠損が条件を満たす",
            "BLOCK",
        ),
        (
            "QG-CONT-003",
            "content_schema",
            "Content AST Contract",
            "Schema、Block順序、許可Node、未知Field、URL禁止が合格",
            "BLOCK",
        ),
        (
            "QG-CONT-004",
            "claim_evidence",
            "Claim–Evidence",
            "主要Claim 100%、全検証可能Claim 95%以上、競合・期限切れなし",
            "BLOCK",
        ),
        (
            "QG-CONT-005",
            "recommendation",
            "Recommendation Integrity",
            "Methodology、Hard Constraint、Coverage、Bias、Tradeoff、Overrideを検査",
            "BLOCK",
        ),
        (
            "QG-CONT-006",
            "editorial_quality",
            "Editorial Quality",
            "100点中85点以上かつ各軸Floor以上",
            "BLOCK",
        ),
        (
            "QG-CONT-007",
            "compliance",
            "Compliance",
            "広告表示、楽天規約、体験、レビュー、画像、CTA、Policy Findingを検査",
            "BLOCK",
        ),
        (
            "QG-CONT-008",
            "seo_accessibility",
            "SEO & Accessibility",
            "Metadata、Canonical、Structured Data、Link、Heading、Alt、表を検査",
            "BLOCK",
        ),
        (
            "QG-CONT-009",
            "freshness_link",
            "Freshness & Link",
            "Critical Fact、Offer、Affiliate Link、確認時刻、Safe Degradationを検査",
            "BLOCK",
        ),
        (
            "QG-CONT-010",
            "human_review",
            "Human Approval",
            "ReviewerがEvidenceへアクセスし、Finding解消と明示承認を実施",
            "BLOCK",
        ),
        (
            "QG-CONT-011",
            "publication_snapshot",
            "Publication Snapshot",
            "Version、Hash、Policy、Methodology、SEO、Disclosure、Kill Switchを再確認",
            "BLOCK",
        ),
        (
            "QG-CONT-012",
            "post_publication",
            "Post-publication Verification",
            "公開HTML、CTA、JSON-LD、Canonical、robots、RUM、Cacheを実URLで検査",
            "ROLLBACK_OR_PAUSE",
        ),
    )


def test_review_and_content_matrix_source_contracts_are_exactly_bound() -> None:
    assert REVIEW_CHECKLIST_ID == "RAOS-CONTENT-REVIEW-001"
    assert REVIEW_CHECKLIST_VERSION == "1.0.0"
    assert REVIEW_CHECKLIST_SHA256 == (
        "8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63"
    )
    assert CONTENT_TEST_MATRIX_SHA256 == (
        "9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564"
    )


def test_finding_target_vocabulary_matches_the_closed_data_contract() -> None:
    assert tuple(item.value for item in FindingTargetType) == (
        "ARTICLE_VERSION",
        "BLOCK",
        "CLAIM",
        "PRODUCT",
        "OFFER",
        "LINK",
        "SOURCE_PACKET",
    )
