"""Static, denied-network, sensitive-data, and scope boundaries for ST-0604 V2."""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
import socket

from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    SourcePacketCommandIdV2,
    SourcePacketReviewDecisionV2,
)
from tests.st0604.runtime_v2_fixtures import (
    ARTICLE_PLAN_ID,
    EDITOR_FINGERPRINT,
    PACKET_ID,
    REVIEW_ASSIGNMENT_ID,
    SITE_ID,
    authorization_fixture_v2,
    source_content_v2,
    source_packet_runtime_v2,
    source_packet_store_v2,
)


RUNTIME_FILES = (
    Path("python/raos/domain/evidence/source_packet_lifecycle_runtime_v2.py"),
    Path("python/raos/ports/source_packet_lifecycle_runtime_v2.py"),
    Path("python/raos/application/evidence/source_packet_lifecycle_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_source_packet_lifecycle_runtime_v2.py"),
)


def test_runtime_has_no_network_provider_ai_or_publication_import() -> None:
    forbidden_roots = {
        "aiohttp",
        "boto3",
        "botocore",
        "httpx",
        "openai",
        "requests",
        "socket",
        "urllib",
    }
    for path in RUNTIME_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(forbidden_roots), (path, imported & forbidden_roots)


def test_runtime_contains_no_url_or_business_metric_vocabulary() -> None:
    forbidden_names = {
        "affiliate_rate",
        "commission",
        "epc",
        "profit",
        "revenue",
        "reward",
        "rpm",
    }
    for path in RUNTIME_FILES:
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        assert "http://" not in lowered and "https://" not in lowered
        tree = ast.parse(source, filename=str(path))
        executable_names = (
            {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
            | {node.arg.lower() for node in ast.walk(tree) if isinstance(node, ast.arg)}
            | {
                node.attr.lower()
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            }
        )
        assert executable_names.isdisjoint(forbidden_names)


def test_recorded_pipeline_succeeds_with_socket_and_dns_denied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SECRET_NETWORK_CANARY")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    content = source_content_v2(tmp_path / "evidence")
    now = content.conflict_scan.committed_at + timedelta(minutes=1)
    authorization = authorization_fixture_v2(tmp_path / "authorization", now=now)
    store = source_packet_store_v2(tmp_path / "store")
    runtime = source_packet_runtime_v2(authorization=authorization, store=store)
    runtime.create_packet(
        command_id=SourcePacketCommandIdV2("RECORDED:DENIED-NETWORK:CREATE"),
        packet_id=PACKET_ID,
        site_id=SITE_ID,
        article_plan_id=ARTICLE_PLAN_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        creator_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=now - timedelta(seconds=3),
    )
    runtime.create_version(
        command_id=SourcePacketCommandIdV2("RECORDED:DENIED-NETWORK:VERSION"),
        packet_id=PACKET_ID,
        expected_revision=1,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        content=content,
        occurred_at=now - timedelta(seconds=2),
    )
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2("RECORDED:DENIED-NETWORK:SUBMIT"),
        packet_id=PACKET_ID,
        expected_revision=2,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=now - timedelta(seconds=1),
    )
    runtime.record_review(
        command_id=SourcePacketCommandIdV2("RECORDED:DENIED-NETWORK:APPROVE"),
        packet_id=PACKET_ID,
        expected_revision=3,
        decision=SourcePacketReviewDecisionV2.APPROVE,
        site_id=SITE_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        session_id=authorization.session.session_id,
        authorization_command=authorization.command,
        authorization_result=authorization.result,
        authorization_checked_at=now,
    )
    runtime.lock_version(
        command_id=SourcePacketCommandIdV2("RECORDED:DENIED-NETWORK:LOCK"),
        packet_id=PACKET_ID,
        expected_revision=4,
        actor_fingerprint=authorization.result.session_fingerprint,
        occurred_at=now + timedelta(seconds=1),
    )
    generation = runtime.read_generation_input(
        command_id=SourcePacketCommandIdV2("RECORDED:DENIED-NETWORK:READ"),
        packet_id=PACKET_ID,
        expected_revision=5,
        actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=now + timedelta(seconds=2),
    ).generation_input
    assert generation is not None
    assert generation.content.conflict_scan.batch.conflicts == ()


def test_owner_private_database_has_no_urls_or_forbidden_business_metrics(
    tmp_path: Path,
) -> None:
    content = source_content_v2(tmp_path / "evidence")
    now = content.conflict_scan.committed_at + timedelta(minutes=1)
    authorization = authorization_fixture_v2(tmp_path / "authorization", now=now)
    store = source_packet_store_v2(tmp_path / "store")
    runtime = source_packet_runtime_v2(authorization=authorization, store=store)
    runtime.create_packet(
        command_id=SourcePacketCommandIdV2("RECORDED:STORAGE:CREATE"),
        packet_id=PACKET_ID,
        site_id=SITE_ID,
        article_plan_id=ARTICLE_PLAN_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        creator_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=now,
    )
    raw = store.database_path.read_bytes().lower()
    for token in (
        b"http://",
        b"https://",
        b"affiliate_rate",
        b"commission",
        b"profit",
        b"revenue",
        b"reward",
    ):
        assert token not in raw


def test_v2_module_basenames_are_unique_repository_wide() -> None:
    matches = {
        candidate
        for candidate in Path(".").rglob(RUNTIME_FILES[0].name)
        if ".worktrees" not in candidate.parts
    }
    assert matches == set(RUNTIME_FILES[:3])
    adapter_matches = {
        candidate
        for candidate in Path(".").rglob(RUNTIME_FILES[3].name)
        if ".worktrees" not in candidate.parts
    }
    assert adapter_matches == {RUNTIME_FILES[3]}
