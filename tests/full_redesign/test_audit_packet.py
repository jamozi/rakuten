from __future__ import annotations

import io
from pathlib import Path
import tarfile

import pytest

from scripts import prepare_full_redesign_audit_packet as packet


def test_archive_generation_is_deterministic_and_normalized() -> None:
    payload = {
        "README.md": b"packet\n",
        "repository/AGENTS.md": b"rules\n",
    }

    first = packet._archive_bytes(payload)
    second = packet._archive_bytes(payload)

    assert first == second
    with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [
            "README.md",
            "repository/AGENTS.md",
        ]
        assert all(member.isfile() for member in members)
        assert all(member.mtime == 0 for member in members)
        assert all(member.mode == 0o644 for member in members)
        assert all(member.uid == 0 and member.gid == 0 for member in members)


def test_manifest_is_exact_and_rejects_duplicates() -> None:
    payload = {"README.md": b"packet\n", "context/state.json": b"{}\n"}
    manifest = packet._manifest_bytes(payload)

    parsed = packet._parse_manifest(manifest)

    assert set(parsed) == set(payload)
    assert parsed["README.md"] == packet._sha256(payload["README.md"])
    with pytest.raises(packet.PacketError, match="MANIFEST_INVALID"):
        packet._parse_manifest(manifest + manifest.splitlines(keepends=True)[0])


@pytest.mark.parametrize(
    "member",
    [
        "../secret",
        "/absolute",
        ".secrets/token",
        "repository/../../secret",
        "repository//file",
    ],
)
def test_archive_member_path_rejects_unsafe_names(member: str) -> None:
    with pytest.raises(packet.PacketError):
        packet._safe_member(member)


def test_sensitive_scan_rejects_credentials_but_allows_public_affiliate_url() -> None:
    packet._scan_sensitive(
        "public/article.html",
        b"https://hb.afl.rakuten.co.jp/hgc/public-affiliate-link",
    )

    with pytest.raises(packet.PacketError, match="SENSITIVE_CONTENT_DETECTED"):
        packet._scan_sensitive(
            "repository/example.md",
            b"Authorization: Bearer this-is-a-secret-token-value",
        )


def test_current_config_selects_prompt_without_private_or_dependency_paths() -> None:
    config = packet._load_config(packet.CONFIG_PATH)

    selected = packet._repository_inputs(config)
    values = {path.as_posix() for path in selected}

    assert "changes/full-redesign-v2/PRO_FULL_REDESIGN_PROMPT.md" in values
    assert "tests/full_redesign/test_audit_packet.py" in values
    assert "docs/canonical/START_HERE.md" in values
    assert all(".secrets" not in path.parts for path in selected)
    assert all("node_modules" not in path.parts for path in selected)
    assert all("__pycache__" not in path.parts for path in selected)


def test_public_payload_removes_body_encoding_from_index() -> None:
    body = b"<html><title>Public</title></html>"
    capture = {
        "responses": [
            {
                "id": "home",
                "url": "https://kurashinoshirube.com/",
                "captured_at": "2026-08-27T00:00:00Z",
                "status": 200,
                "reason": "OK",
                "content_type": "text/html; charset=UTF-8",
                "location": None,
                "body_sha256": packet._sha256(body),
                "body_base64": "PGh0bWw+PHRpdGxlPlB1YmxpYzwvdGl0bGU+PC9odG1sPg==",
            }
        ]
    }

    payload = packet._public_payload(capture)

    assert payload["public/home.html"] == body
    assert b"body_base64" not in payload["public/index.json"]


def test_read_archive_rejects_link_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        info = tarfile.TarInfo("repository/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../secret"
        archive.addfile(info)
    config = {
        "max_member_bytes": 1024,
        "max_total_bytes": 4096,
    }

    with pytest.raises(packet.PacketError, match="ARCHIVE_MEMBER_INVALID"):
        packet._read_archive(archive_path, config)
