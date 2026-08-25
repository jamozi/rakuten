"""Owner-generated ST-0901 V2 recorded fixture bytes."""

from typing import Final

REVIEW_COMPLETION_PASS_V2_JSON: Final = b'{"schema_version":2,"profile":"ST0901_REVIEW_COMPLETION_RECORDED_LOCAL_V2","local_status":"LOCAL_IMPLEMENTATION_COMPLETE","fixture_id":"018f3e90-7b00-7000-8000-000000000900","assignment":{"assignment_id":"018f3e90-7b00-7000-8000-000000000901","article_version_id":"018f3e90-7b00-7000-8000-000000000806","assigned_by":"018f3e90-7b00-7000-8000-000000000902","assigned_to":"018f3e90-7b00-7000-8000-000000000903","review_type":"EDITORIAL","priority":50,"created_at":"2026-08-24T01:00:00Z","started_at":"2026-08-24T01:15:00Z"},"decision":{"decision_id":"018f3e90-7b00-7000-8000-000000000904","audit_event_id":"018f3e90-7b00-7000-8000-000000000905","decided_at":"2026-08-24T01:30:00Z","decision":"APPROVE","summary":"Recorded local human review checklist passed.","checklist_version":"1.0.0","checklist_sha256":"8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63","checklist_status":"ALL_PASS","idempotency_key":"st0901-v2-review-completion-0001"},"policy":{"fixture_sha256":"75797ab838b37b482ecfd30312101e4103dc7301a4ee57e0f6ce544a845300b9","report_sha256":"c878a107d845aa9df4c30ce1b990fb3c814dc10d1a21ea6ac3074e6885c007c7","receipt_sequence":1,"finding_snapshot_sha256":"29a2fa3d208022de73f4e2b67bd778a56987b187570d3ae4ac0c4cf7765ee1fa"},"authority":{"recorded_synthetic_only":true,"final_approval_authorized":false,"publication_snapshot_authorized":false,"publication_authorized":false,"release_authorized":false,"production_authorized":false}}\n'
REVIEW_COMPLETION_PASS_V2_SHA256: Final = (
    "84778adfb038bbd8665dbcf3fcf9bce9e23e0afe248f11a2f8bd10846cde32ec"
)

__all__ = (
    "REVIEW_COMPLETION_PASS_V2_JSON",
    "REVIEW_COMPLETION_PASS_V2_SHA256",
)
