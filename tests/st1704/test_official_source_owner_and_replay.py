"""Synthetic owner-root and non-HTML capture roundtrips; never live evidence."""

from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat

import pytest

from raos.adapters import self_hosted_editorial_source_capture as capture
from raos.adapters import self_hosted_editorial_pilot_json as reader
from raos.application.editorial import verified_incremental_sources_v1 as replay
from raos.domain.editorial.self_hosted_editorial_pilot import EditorialPilotFailure
from tests.st1704 import test_self_hosted_editorial_source_capture as examples


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts/st1704_official_source_capture.py"
FIXED_OWNER = "/home/minami/rakuten"
JSON_BODY = b'{"model":"synthetic-test","weight_kg":3.3}'
JSON_FRAGMENT = '"model":"synthetic-test"'
PDF_BODY = b"%PDF-1.7\nsynthetic compressed page fixture\n%%EOF\n"
PDF_FRAGMENT = "Reviewed page text absent from raw PDF bytes"


def cli_namespace():
    return runpy.run_path(str(CLI_PATH))


@pytest.mark.parametrize(
    "command,option,identifier",
    [
        ("capture-source", "--source-ref", "SRC-ANKER-SOLIX-C300"),
        ("capture-article", "--article-id", "st1703-first-suitcase-comparison"),
    ],
)
def test_cli_accepts_only_the_fixed_owner_checkout(command, option, identifier):
    parser = cli_namespace()["_parser"]()
    parsed = parser.parse_args(
        [command, option, identifier, "--owner-checkout", FIXED_OWNER]
    )
    assert parsed.owner_checkout == FIXED_OWNER
    assert parser.parse_args([command, option, identifier]).owner_checkout is None
    for root in ("/tmp/other", ".", FIXED_OWNER + "/../other", FIXED_OWNER + "/"):
        with pytest.raises(SystemExit):
            parser.parse_args([command, option, identifier, "--owner-checkout", root])


@pytest.fixture
def bound_owner(tmp_path, monkeypatch):
    repository = tmp_path / "worktree"
    owner = tmp_path / "owner"
    repository.mkdir(mode=0o700)
    owner.mkdir(mode=0o700)
    namespace = cli_namespace()
    globals_ = namespace["_bind_verified_source_documents"].__globals__
    monkeypatch.setitem(globals_, "REPOSITORY_ROOT", repository)
    monkeypatch.setitem(globals_, "OWNER_CHECKOUT", owner)
    # Record the originals for teardown before the CLI installs its verified closures.
    monkeypatch.setattr(capture, "_read_tracked_file", capture._read_tracked_file)
    monkeypatch.setattr(capture, "_source_directory", capture._source_directory)
    verified = {
        path: (ROOT / path).read_bytes() for path in namespace["_TRACKED_SOURCE_PATHS"]
    }
    identity = (repository.stat().st_dev, repository.stat().st_ino)
    namespace["_bind_verified_source_documents"](
        capture, verified, identity, owner_checkout=owner
    )
    return repository, owner, namespace, identity, verified


def test_verified_contracts_stay_in_worktree_but_capture_writes_only_to_owner(
    bound_owner,
):
    repository, owner, _namespace, _identity, _verified = bound_owner
    # Neither physical directory contains contract files: reads use the verified bytes.
    assert capture.load_source_capture_plan(repository).target(
        "SRC-ANKER-SOLIX-C300"
    ).url == ("https://www.ankerjapan.com/products/a1722")
    target = examples._target(locator_status="READY")
    factory = examples._Factory(examples._Response())
    result = capture._capture_targets(
        repository,
        (target,),
        connection_factory=factory,
        clock=lambda: examples.FIXED_NOW,
        environment={},
    )
    assert result[0].status == "CAPTURED_WITH_VERIFIED_LOCATORS"
    body = owner / reader.source_body_relative_path(target.source_ref)
    metadata = owner / reader.source_evidence_relative_path(target.source_ref)
    assert body.read_bytes() == examples.HTML_BODY
    assert not (repository / ".secrets").exists()
    for path in (body, metadata):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stat().st_uid == os.getuid() and path.stat().st_nlink == 1
    for path in (body.parent, body.parent.parent, owner / ".secrets"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    evidence = reader.read_official_source_capture_evidence(
        owner, source_ref=target.source_ref
    )
    assert evidence.body_sha256 == result[0].body_sha256
    assert evidence.final_url == target.url


def test_owner_cannot_supply_contracts_or_redirect_persistence(bound_owner):
    repository, owner, namespace, _identity, _verified = bound_owner
    with pytest.raises(namespace["_RuntimeFailure"]):
        capture._read_tracked_file(
            owner, capture.LOCATOR_CONTRACT_RELATIVE_PATH, 1_000_000
        )
    with pytest.raises(namespace["_RuntimeFailure"]):
        capture._source_directory(owner)
    with pytest.raises(namespace["_RuntimeFailure"]):
        capture._source_directory(repository / "other")


@pytest.mark.parametrize(
    "change", ["owner_swap", "worktree_swap", "owner_symlink", "owner_mode"]
)
def test_bound_directory_identity_and_permissions_are_rechecked(bound_owner, change):
    repository, owner, namespace, _identity, _verified = bound_owner
    if change == "owner_mode":
        owner.chmod(0o777)
    else:
        path = repository if change == "worktree_swap" else owner
        moved = path.with_name(path.name + "-old")
        path.rename(moved)
        if change == "owner_symlink":
            path.symlink_to(moved, target_is_directory=True)
        else:
            path.mkdir(mode=0o700)
    with pytest.raises(namespace["_RuntimeFailure"]):
        capture._source_directory(repository)


def test_arbitrary_owner_rejected_before_binding_or_private_writes(tmp_path):
    namespace = cli_namespace()
    with pytest.raises(namespace["_RuntimeFailure"]):
        namespace["_bind_verified_source_documents"](
            capture, {}, (0, 0), owner_checkout=tmp_path
        )
    assert not (tmp_path / ".secrets").exists()


def target_for(media_type):
    if media_type == "application/pdf":
        return examples._target(
            locator_status="READY",
            fragment=PDF_FRAGMENT,
            media_type="application/pdf",
            locator_mode="PINNED_PDF_BODY_AND_REVIEWED_PAGE_TEXT",
            expected_body_sha256=hashlib.sha256(PDF_BODY).hexdigest(),
            reviewed_page_number=10,
        )
    return examples._target(
        locator_status="READY",
        fragment=JSON_FRAGMENT,
        media_type="text/javascript",
        charset="utf-8",
    )


def fetch_and_persist(root, media_type):
    target = target_for(media_type)
    body = PDF_BODY if media_type == "application/pdf" else JSON_BODY
    header = (
        media_type
        if media_type == "application/pdf"
        else media_type + "; charset=utf-8"
    )
    fetched, _factory = examples._fetch(
        examples._Response(
            body,
            headers=[
                ("Content-Type", header),
                ("Content-Length", str(len(body))),
            ],
        ),
        target=target,
    )
    result = capture._persist_capture(root, fetched)
    return target, fetched, result


@pytest.mark.parametrize(
    "media_type", ["application/json", "application/javascript", "text/javascript"]
)
def test_json_response_mime_and_provenance_survive_fetch_persist_read_replay(
    tmp_path, media_type
):
    target, fetched, result = fetch_and_persist(tmp_path, media_type)
    evidence = reader.read_official_source_capture_evidence(
        tmp_path, source_ref=target.source_ref
    )
    assert fetched.content_type == evidence.content_type == media_type
    assert evidence.final_url == target.url
    assert evidence.body_sha256 == hashlib.sha256(JSON_BODY).hexdigest()
    assert evidence.response_sha256 == result.response_sha256
    receipt = replay._replay(
        tmp_path,
        target,
        {"source_registry": "a" * 64, "locator_contract": "b" * 64},
        examples.FIXED_NOW + timedelta(minutes=1),
    )
    assert receipt.body_file_sha256 == evidence.body_sha256
    assert receipt.response_sha256 == evidence.response_sha256
    assert (
        tmp_path / reader.source_body_relative_path(target.source_ref)
    ).read_bytes() == JSON_BODY


def test_pinned_pdf_reviewed_page_text_roundtrips_without_raw_utf8_claim(tmp_path):
    target, fetched, result = fetch_and_persist(tmp_path, "application/pdf")
    assert PDF_FRAGMENT.encode() not in fetched.body
    evidence = reader.read_official_source_capture_evidence(
        tmp_path, source_ref=target.source_ref, reviewed_pdf_target=target
    )
    assert evidence.content_type == "application/pdf"
    assert evidence.locators[0][2][0][0] == PDF_FRAGMENT
    assert evidence.body_sha256 == target.expected_body_sha256 == result.body_sha256
    receipt = replay._replay(
        tmp_path,
        target,
        {"source_registry": "a" * 64, "locator_contract": "b" * 64},
        examples.FIXED_NOW + timedelta(minutes=1),
    )
    assert receipt.body_file_sha256 == result.body_sha256
    with pytest.raises(EditorialPilotFailure):
        reader.read_official_source_capture_evidence(
            tmp_path, source_ref=target.source_ref
        )


@pytest.mark.parametrize("change", ["hash", "url", "claim", "fragment", "source_ref"])
def test_pdf_replay_rejects_current_pin_or_locator_identity_drift(tmp_path, change):
    target, _fetched, _result = fetch_and_persist(tmp_path, "application/pdf")
    if change == "hash":
        changed = replace(target, expected_body_sha256="f" * 64)
    elif change == "url":
        changed = replace(target, url="https://official.example/other", path="/other")
    elif change == "source_ref":
        changed = replace(target, source_ref="SRC-WRONG-IDENTITY")
    else:
        locator = target.locators[0]
        changed = replace(
            target,
            locators=(
                replace(
                    locator,
                    **(
                        {"claim_statement_sha256": "b" * 64}
                        if change == "claim"
                        else {"exact_utf8_fragments": ("wrong reviewed text",)}
                    ),
                ),
            ),
        )
    with pytest.raises(EditorialPilotFailure):
        reader.read_official_source_capture_evidence(
            tmp_path, source_ref=target.source_ref, reviewed_pdf_target=changed
        )


def test_pdf_body_cannot_be_replaced_even_with_self_consistent_metadata_hashes(
    tmp_path,
):
    target, _fetched, _result = fetch_and_persist(tmp_path, "application/pdf")
    body = PDF_BODY.replace(b"compressed", b"substituted")
    path = tmp_path / reader.source_evidence_relative_path(target.source_ref)
    document = json.loads(path.read_bytes())
    document["body_sha256"] = hashlib.sha256(body).hexdigest()
    material = {
        key: value
        for key, value in document.items()
        if key not in {"locators", "response_sha256"}
    }
    document["response_sha256"] = capture.canonical_sha256(material)
    path.write_bytes(capture.canonical_json_bytes(document))
    (tmp_path / reader.source_body_relative_path(target.source_ref)).write_bytes(body)
    with pytest.raises(EditorialPilotFailure):
        reader.read_official_source_capture_evidence(
            tmp_path, source_ref=target.source_ref, reviewed_pdf_target=target
        )


@pytest.mark.parametrize(
    "body",
    [
        b'{"model":"synthetic-test","model":"duplicate"}',
        b'{"weight":NaN}',
        b'{"weight":Infinity}',
        b'callback({"model":"synthetic-test"})',
        b"<html>not JSON</html>",
        b"\xff",
        b"",
    ],
)
@pytest.mark.parametrize(
    "media_type", ["application/json", "application/javascript", "text/javascript"]
)
def test_json_reader_rejects_invalid_or_executable_bodies(body, media_type):
    with pytest.raises(EditorialPilotFailure):
        reader._validate_source_capture_body(body, content_type=media_type)


def test_current_machine_readable_targets_keep_their_tracked_contract_types():
    targets = [
        target
        for target in capture.load_source_capture_plan(ROOT).targets
        if target.media_type == "text/javascript"
    ]
    assert {target.source_ref for target in targets} == {
        "SRC-INNOVATOR-INV50",
        "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS",
        "SRC-SWITCHBOT-K11-SETUP",
    }
    assert all(target.locator_mode == "RAW_BODY_EXACTLY_ONCE" for target in targets)


@pytest.mark.parametrize("unsafe_private", [False, True])
def test_execute_routes_fixed_owner_and_checks_private_modes_before_get(
    tmp_path, monkeypatch, unsafe_private
):
    repository = tmp_path / "worktree"
    owner = tmp_path / "owner"
    repository.mkdir(mode=0o700)
    owner.mkdir(mode=0o700)
    namespace = cli_namespace()
    globals_ = namespace["_execute"].__globals__
    monkeypatch.setitem(globals_, "REPOSITORY_ROOT", repository)
    monkeypatch.setitem(globals_, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(capture, "_read_tracked_file", capture._read_tracked_file)
    monkeypatch.setattr(capture, "_source_directory", capture._source_directory)
    monkeypatch.setitem(
        globals_,
        "_load_verified_modules",
        lambda _: {
            "raos.adapters.self_hosted_editorial_source_capture": capture,
        },
    )
    factory = examples._Factory(examples._Response())
    selected_ref = "SRC-ANKER-SOLIX-C300"
    target = replace(examples._target(locator_status="READY"), source_ref=selected_ref)

    def recorded_capture(root, *, source_ref, clock):
        assert root == repository and source_ref == selected_ref
        return capture._capture_targets(
            root, (target,), connection_factory=factory, clock=clock, environment={}
        )

    monkeypatch.setattr(capture, "capture_source_ref", recorded_capture)
    if unsafe_private:
        (owner / ".secrets").mkdir(mode=0o755)
    verified = {
        path: (ROOT / path).read_bytes() for path in namespace["_TRACKED_SOURCE_PATHS"]
    }
    arguments = dict(
        source_ref=selected_ref,
        article_id=None,
        sources=verified,
        root_identity=(repository.stat().st_dev, repository.stat().st_ino),
        owner_checkout=owner,
    )
    if unsafe_private:
        with pytest.raises(namespace["_CommandFailure"], match="STORE_UNSAFE"):
            namespace["_execute"]("capture-source", **arguments)
        assert factory.opens == []
    else:
        document = namespace["_execute"]("capture-source", **arguments)
        assert document["status"] == "CAPTURE_COMPLETED"
        assert document["network_requests"] == 1
        assert document["publication_authority"] is False
        assert (
            owner / reader.source_body_relative_path(selected_ref)
        ).read_bytes() == examples.HTML_BODY
        assert not (repository / ".secrets").exists()
