"""Owner-generated ST-0901 V2 recorded fixture bytes."""

from typing import Final

REVIEW_COMPLETION_PASS_V2_JSON: Final = b'{"schema_version":2,"profile":"ST0901_REVIEW_COMPLETION_RECORDED_LOCAL_V2","local_status":"LOCAL_IMPLEMENTATION_COMPLETE","fixture_id":"018f3e90-7b00-7000-8000-000000000900","assignment":{"assignment_id":"018f3e90-7b00-7000-8000-000000000901","article_version_id":"018f3e90-7b00-7000-8000-000000000806","assigned_by":"018f3e90-7b00-7000-8000-000000000902","assigned_to":"018f3e90-7b00-7000-8000-000000000903","review_type":"EDITORIAL","priority":50,"created_at":"2026-08-24T01:00:00Z","started_at":"2026-08-24T01:15:00Z"},"decision":{"decision_id":"018f3e90-7b00-7000-8000-000000000904","audit_event_id":"018f3e90-7b00-7000-8000-000000000905","decided_at":"2026-08-24T01:30:00Z","decision":"APPROVE","summary":"Recorded local human review checklist passed.","checklist_version":"1.0.0","checklist_sha256":"8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63","checklist_status":"ALL_PASS","idempotency_key":"st0901-v2-review-completion-0001"},"policy":{"fixture_sha256":"7c0c7d1eda772d501c7278ba045c32c599153ed5bd63063673e0b5cf67d45849","report_sha256":"4222b076411f165967b5802f5b2057fc8635c0f0e94aadf6bcd7462e9ffa4fec","receipt_sequence":1,"finding_snapshot_sha256":"fb27894da7a6bc68b65b383cd3af03029bbb0688d3b553a7d36f2286c9976967"},"authority":{"recorded_synthetic_only":true,"final_approval_authorized":false,"publication_snapshot_authorized":false,"publication_authorized":false,"release_authorized":false,"production_authorized":false}}\n'
REVIEW_COMPLETION_PASS_V2_SHA256: Final = (
    "57587322562eae4a2b58bebfc6b917e39fb05f077cf7268deb4056563950a361"
)

__all__ = (
    "REVIEW_COMPLETION_PASS_V2_JSON",
    "REVIEW_COMPLETION_PASS_V2_SHA256",
)
