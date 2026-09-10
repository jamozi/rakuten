import json

import pytest

from scripts import raos_wordpress_deployment_operator as operator
from scripts import raos_wordpress_direct_publish as direct


@pytest.fixture(autouse=True)
def isolated_preview_check(monkeypatch):
    monkeypatch.setattr(direct, "verify_preview", lambda *args: None)


def test_direct_status_is_read_only_and_has_dedicated_credentials(monkeypatch):
    calls = []
    monkeypatch.setattr(
        operator, "request_json", lambda *a, **k: calls.append((a, k)) or {}
    )
    operator.run("owner-direct-status", {})
    assert calls == [(("GET", "/status"), {"owner_direct": True})]


def test_legacy_candidate_cannot_become_direct(tmp_path):
    (tmp_path / "candidate.json").write_text(
        json.dumps({"schema": "LegacyCandidateV1"})
    )
    with pytest.raises(direct.DirectFailure, match="PROFILE"):
        direct.load_candidate(tmp_path, "a" * 64)


def test_source_change_after_preview_refuses_publish(tmp_path):
    source = tmp_path / "article.html"
    source.write_text("reviewed")
    candidate = {"sources": {"article.html": direct.digest(b"reviewed")}}
    direct.validate_sources(tmp_path, candidate)
    source.write_text("unreviewed")
    with pytest.raises(direct.DirectFailure, match="SOURCE_DRIFT"):
        direct.validate_sources(tmp_path, candidate)


def test_resume_applied_publication_only_reads_back_and_syncs(tmp_path, monkeypatch):
    candidate = {"candidate_id": "a" * 64, "articles": [], "theme": None}
    journal = {
        "publication_status": "APPLIED",
        "checkpoint": {"commit": "c"},
        "proposal_ids": ["b" * 64],
    }
    calls = []
    monkeypatch.setattr(
        direct, "readback", lambda *a: calls.append("readback") or {"status": "PASS"}
    )
    monkeypatch.setattr(
        direct, "sync_git", lambda *a: calls.append("sync") or {"status": "error"}
    )
    result = direct.finish_publication(
        tmp_path, tmp_path, candidate, journal, lambda *a: pytest.fail("no write")
    )
    assert calls == ["readback", "sync"]
    assert result["publication_status"] == "PUBLISHED_AND_READBACK_VERIFIED"
    assert result["git_sync"]["status"] == "error"


def test_explicit_candidate_required_for_publish():
    with pytest.raises(SystemExit):
        direct.parser().parse_args(["publish"])


def test_initial_status_needs_no_candidate_or_write(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        direct,
        "invoke",
        lambda *args: (
            calls.append(args) or {"profile": direct.PROFILE, "enabled": False}
        ),
    )
    assert direct.main(["status"]) == 0
    assert calls == [("status", {})]
    assert json.loads(capsys.readouterr().out)["enabled"] is False


@pytest.mark.parametrize("failed", [False, True])
def test_fixed_owner_option_routes_private_context_and_resets(monkeypatch, failed):
    from pathlib import Path

    owner = Path("/home/minami/rakuten")
    observed = []

    def validate(value):
        assert value == owner
        return value

    def invoke(command, body):
        observed.append(operator._private_owner.get())
        if failed:
            raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED")
        return {"enabled": False}

    monkeypatch.setattr(operator, "validated_owner_checkout", validate)
    monkeypatch.setattr(direct, "invoke", invoke)
    previous = operator._private_owner.get()
    root = direct.ROOT
    assert direct.main(["--owner-checkout", str(owner), "status"]) == (
        69 if failed else 0
    )
    assert observed == [owner]
    assert operator._private_owner.get() == previous
    assert direct.ROOT == root


def test_owner_option_refuses_other_location_before_call(monkeypatch):
    monkeypatch.setattr(direct, "invoke", lambda *a: pytest.fail("unexpected call"))
    assert direct.main(["--owner-checkout", "/tmp/other-checkout", "status"]) == 69


def frozen(tmp_path, new=False):
    source = tmp_path / "article.html"
    source.write_text("reviewed")
    document = {
        "post_type": "post",
        "title": "Reviewed",
        "slug": "reviewed",
        "excerpt": "",
        "block_markup": "reviewed",
        "taxonomies": {},
        "media_ids": [],
    }
    baseline = {
        **document,
        "id": 11,
        "status": "draft" if new else "publish",
        "revision_id": 5,
        "modified_gmt": "2026-09-08T01:00:00Z",
        "content_sha256": "f" * 64,
    }
    sources = {"article.html": direct.digest(b"reviewed")}
    candidate = {
        "schema": direct.SCHEMA,
        "profile": direct.PROFILE,
        "sources": sources,
        "source_sha256": direct.digest(direct.encoded(sources)),
        "articles": [
            {
                "article_key": "reviewed",
                "post_id": None if new else 11,
                "body_file": "sources/article.html",
                "slug": "reviewed",
                "document": document,
                "baseline": None if new else baseline,
            }
        ],
        "theme": None,
        "baseline_theme_tree_sha256": "d" * 64,
        "profile_sha256": "e" * 64,
        "publication_ready": True,
        "checkpoint": {"commit": "c"},
    }
    candidate["candidate_id"] = direct.digest(direct.encoded(candidate))
    directory = tmp_path / "candidate"
    (directory / "sources").mkdir(parents=True)
    (directory / "sources/article.html").write_text("reviewed")
    direct.save(directory / "candidate.json", candidate)
    direct.save(
        directory / "preview.json",
        {
            "status": "PASS",
            "candidate_id": candidate["candidate_id"],
            "source_sha256": candidate["source_sha256"],
        },
    )
    return directory, candidate, baseline


def test_lost_apply_response_resumes_without_republishing(tmp_path, monkeypatch):
    directory, candidate, baseline = frozen(tmp_path)
    writes = []
    applied = False

    def call(command, body):
        nonlocal applied
        if command == "status":
            return {
                "profile": direct.PROFILE,
                "enabled": True,
                "profile_sha256": "e" * 64,
                "theme": {"tree_sha256": "d" * 64},
            }
        if command == "document":
            return {**baseline, "status": "publish"}
        if command == "operation-status":
            return {"operation": {"state": "APPLIED" if applied else "PENDING"}}
        writes.append(command)
        if command == "content-propose":
            return {
                "proposal_id": "b" * 64,
                "after_sha256": direct.content_after_sha256(
                    body["document"], body["id"]
                ),
            }
        if command == "authorize":
            return {"batch_token": "c" * 64, "batch_manifest_sha256": "d" * 64}
        if command == "apply":
            applied = True
            raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED")
        if command == "finish":
            assert body["action"] == "finalize"
            return {
                "schema": "RAOSOwnerDirectBatchResultV1",
                "profile": direct.PROFILE,
                "batch_token": body["batch_token"],
                "batch_manifest_sha256": body["batch_manifest_sha256"],
                "members": [],
                "state": "FINALIZED",
            }
        pytest.fail(command)

    monkeypatch.setattr(direct, "sync_git", lambda *a: {"status": "error"})
    with pytest.raises(operator.OperatorFailure):
        direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    result = direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    assert result["publication_status"] == "PUBLISHED_AND_READBACK_VERIFIED"
    assert writes == ["content-propose", "authorize", "apply", "finish"]


def test_lost_draft_response_reuses_identical_idempotency_key(tmp_path, monkeypatch):
    directory, candidate, baseline = frozen(tmp_path, new=True)
    keys = []

    def call(command, body):
        if command == "status":
            return {
                "profile": direct.PROFILE,
                "enabled": True,
                "profile_sha256": "e" * 64,
                "theme": {"tree_sha256": "d" * 64},
            }
        if command == "ensure-draft":
            keys.append(body["idempotency_key"])
            if len(keys) == 1:
                raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED")
            return {"id": 11, "document": baseline}
        if command == "document":
            return baseline
        if command == "content-propose":
            raise operator.OperatorFailure("STOP_BEFORE_PUBLISH")
        pytest.fail(command)

    for _ in range(2):
        with pytest.raises(operator.OperatorFailure):
            direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    assert len(keys) == 2 and keys[0] == keys[1]
    assert direct.read_json(directory / "journal.json")["post_ids"] == {"reviewed": 11}


def test_changed_existing_baseline_refuses_content_proposal(tmp_path):
    directory, candidate, baseline = frozen(tmp_path)

    def call(command, body):
        if command == "status":
            return {
                "profile": direct.PROFILE,
                "enabled": True,
                "profile_sha256": "e" * 64,
                "theme": {"tree_sha256": "d" * 64},
            }
        if command == "document":
            return {**baseline, "revision_id": 6}
        pytest.fail("write attempted: " + command)

    with pytest.raises(direct.DirectFailure, match="CONTENT_CONFLICT"):
        direct.publish(tmp_path, directory, candidate["candidate_id"], call)


def test_changed_snapshot_is_rejected_even_if_current_source_matches(tmp_path):
    directory, candidate, _ = frozen(tmp_path)
    (directory / "sources/article.html").write_text("changed")
    with pytest.raises(direct.DirectFailure, match="SNAPSHOT_DRIFT"):
        direct.load_candidate(directory, candidate["candidate_id"])


@pytest.mark.parametrize(
    "relative",
    [
        "a/../article.html",
        "./article.html",
        "a//article.html",
        ".secrets/file",
        "a\\file",
    ],
)
def test_noncanonical_or_private_source_is_refused(tmp_path, relative):
    with pytest.raises(direct.DirectFailure, match="SOURCE_PATH_INVALID"):
        direct.source_bytes(tmp_path, relative)


def test_source_symlink_ancestor_and_hardlink_are_refused(tmp_path):
    import os

    (tmp_path / "real").mkdir()
    (tmp_path / "real/article.html").write_text("content")
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(direct.DirectFailure, match="SOURCE_PATH_INVALID"):
        direct.source_bytes(tmp_path, "alias/article.html")
    os.link(tmp_path / "real/article.html", tmp_path / "copy.html")
    with pytest.raises(direct.DirectFailure, match="SOURCE_PATH_INVALID"):
        direct.source_bytes(tmp_path, "copy.html")


def test_parallel_publish_is_rejected_before_server(tmp_path):
    import fcntl

    directory, candidate, _ = frozen(tmp_path)
    with (directory / "operation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(direct.DirectFailure, match="OPERATION_BUSY"):
            direct.publish(
                tmp_path,
                directory,
                candidate["candidate_id"],
                lambda *a: pytest.fail("server contacted"),
            )


def test_prepare_new_article_offline_freezes_exact_git_source_without_writes(tmp_path):
    import subprocess

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, check=True
        ).stdout

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "README.md").write_text("seed")
    git("add", "README.md")
    git("commit", "-m", "seed")
    source = "changes/wordpress-direct-publish-v1/articles/new-article.html"
    (tmp_path / source).parent.mkdir(parents=True)
    (tmp_path / source).write_text("reviewed body")
    direct.save(
        tmp_path / direct.REGISTRY,
        {
            "schema": "RAOSOwnerDirectArticlesV1",
            "profile": direct.PROFILE,
            "articles": [
                {
                    "article_key": "new-article",
                    "mode": "new",
                    "post_id": None,
                    "post_type": "post",
                    "title": "New",
                    "slug": "new-article",
                    "body_source": source,
                }
            ],
        },
    )
    calls = []

    def unavailable(command, body):
        calls.append(command)
        raise operator.OperatorFailure("WORDPRESS_MCP_PRIVATE_FILE_UNAVAILABLE")

    candidate, directory = direct.prepare(tmp_path, ["new-article"], call=unavailable)
    repeated, repeated_dir = direct.prepare(tmp_path, ["new-article"], call=unavailable)
    assert calls == ["status", "status"]
    assert candidate["publication_ready"] is False
    assert candidate["baseline_theme_tree_sha256"] is None
    assert candidate["candidate_id"] == repeated["candidate_id"]
    assert directory == repeated_dir
    assert (
        directory / candidate["articles"][0]["body_file"]
    ).read_text() == "reviewed body"
    assert (
        git("show", candidate["checkpoint"]["commit"] + ":" + source)
        == b"reviewed body"
    )
    assert git("symbolic-ref", "--short", "HEAD").strip() == b"main"


@pytest.mark.parametrize("rollback_state", ["ROLLED_BACK", "PARTIAL_CONFLICT"])
def test_partial_failure_uses_bounded_rollback_and_preserves_conflicts(
    tmp_path, rollback_state
):
    directory, candidate, _ = frozen(tmp_path)
    journal = {
        "candidate_id": candidate["candidate_id"],
        "publication_status": "PREPARED",
        "proposals": {"article": "a" * 64, "@theme": "b" * 64},
        "batch": {"batch_token": "c" * 64, "batch_manifest_sha256": "d" * 64},
        "pending_operation": "apply",
    }
    direct.save(directory / "journal.json", journal)
    calls = []

    def call(command, body):
        calls.append((command, body))
        if command == "operation-status":
            return {
                "operation": {
                    "state": "FAILED" if body["operation_id"] == "a" * 64 else "APPLIED"
                }
            }
        assert command == "finish" and body["action"] == "rollback"
        return {
            "schema": "RAOSOwnerDirectBatchResultV1",
            "profile": direct.PROFILE,
            "batch_token": body["batch_token"],
            "batch_manifest_sha256": body["batch_manifest_sha256"],
            "state": rollback_state,
            "members": [
                {
                    "proposal_id": "b" * 64,
                    "state": "CONFLICT"
                    if rollback_state == "PARTIAL_CONFLICT"
                    else "ROLLED_BACK",
                }
            ],
        }

    direct.record_failure(
        directory,
        candidate["candidate_id"],
        operator.OperatorFailure("WORDPRESS_MCP_RELEASE_FAILED"),
        call,
    )
    result = direct.read_json(directory / "journal.json")
    assert result["publication_status"] == rollback_state
    assert [c[0] for c in calls] == ["operation-status", "operation-status", "finish"]
    with pytest.raises(direct.DirectFailure, match="BATCH_CLOSED_REPREPARE"):
        direct.publish(
            tmp_path,
            directory,
            candidate["candidate_id"],
            lambda *a: pytest.fail("closed batch attempted write"),
        )


def test_ambiguous_apply_never_blindly_rolls_back(tmp_path):
    directory, candidate, _ = frozen(tmp_path)
    direct.save(
        directory / "journal.json",
        {
            "candidate_id": candidate["candidate_id"],
            "publication_status": "PREPARED",
            "proposals": {"article": "a" * 64},
            "batch": {},
            "pending_operation": "apply",
        },
    )

    def call(command, body):
        assert command == "operation-status"
        return {"operation": {"state": "APPLYING"}}

    direct.record_failure(
        directory,
        candidate["candidate_id"],
        operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED"),
        call,
    )
    assert (
        direct.read_json(directory / "journal.json")["publication_status"] == "UNKNOWN"
    )


def test_mismatched_proposal_does_not_authorize(tmp_path):
    directory, candidate, baseline = frozen(tmp_path)

    def call(command, body):
        if command == "status":
            return {
                "profile": direct.PROFILE,
                "enabled": True,
                "profile_sha256": "e" * 64,
                "theme": {"tree_sha256": "d" * 64},
            }
        if command == "document":
            return baseline
        if command == "content-propose":
            return {"proposal_id": "b" * 64, "after_sha256": "0" * 64}
        pytest.fail("unexpected write: " + command)

    with pytest.raises(direct.DirectFailure, match="PROPOSAL_CONTENT_MISMATCH"):
        direct.publish(tmp_path, directory, candidate["candidate_id"], call)


def test_interrupted_finalize_replays_without_apply_and_git_failure_stays_separate(
    tmp_path, monkeypatch
):
    directory, candidate, baseline = frozen(tmp_path)
    journal = {
        "candidate_id": candidate["candidate_id"],
        "publication_status": "APPLIED",
        "proposals": {"reviewed": "b" * 64},
        "post_ids": {"reviewed": 11},
        "batch": {"batch_token": "c" * 64, "batch_manifest_sha256": "d" * 64},
        "checkpoint": candidate["checkpoint"],
    }
    direct.save(directory / "journal.json", journal)
    finish_calls = []
    sync_calls = []
    monkeypatch.setattr(
        direct, "sync_git", lambda *a: sync_calls.append(a) or {"status": "error"}
    )

    def call(command, body):
        if command == "document":
            return baseline
        if command == "operation-status":
            return {"operation": {"state": "APPLIED"}}
        assert command == "finish"
        finish_calls.append(body)
        if len(finish_calls) == 1:
            raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED")
        return {
            "schema": "RAOSOwnerDirectBatchResultV1",
            "profile": direct.PROFILE,
            **journal["batch"],
            "state": "FINALIZED",
            "members": [],
        }

    with pytest.raises(operator.OperatorFailure):
        direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    assert sync_calls == []
    result = direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    assert result["publication_status"] == "PUBLISHED_AND_READBACK_VERIFIED"
    assert result["git_sync"]["status"] == "error"
    direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    assert len(finish_calls) == 2 and finish_calls[0] == finish_calls[1]
    assert len(sync_calls) == 2


def test_interrupted_rollback_replays_only_identical_batch_action(tmp_path):
    directory, candidate, _ = frozen(tmp_path)
    journal = {
        "candidate_id": candidate["candidate_id"],
        "publication_status": "PREPARED",
        "proposals": {"article": "a" * 64, "@theme": "b" * 64},
        "batch": {"batch_token": "c" * 64, "batch_manifest_sha256": "d" * 64},
        "pending_operation": "apply",
    }
    direct.save(directory / "journal.json", journal)
    finishes = []

    def call(command, body):
        if command == "operation-status":
            return {
                "operation": {
                    "state": "FAILED" if body["operation_id"] == "a" * 64 else "APPLIED"
                }
            }
        assert command == "finish"
        finishes.append(body)
        if len(finishes) == 1:
            raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED")
        return {
            "schema": "RAOSOwnerDirectBatchResultV1",
            "profile": direct.PROFILE,
            **journal["batch"],
            "state": "ROLLED_BACK",
            "members": [],
        }

    failure = operator.OperatorFailure("WORDPRESS_MCP_RELEASE_FAILED")
    direct.record_failure(directory, candidate["candidate_id"], failure, call)
    assert direct.read_json(directory / "journal.json")["rollback_status"] == "UNKNOWN"
    direct.record_failure(directory, candidate["candidate_id"], failure, call)
    assert (
        direct.read_json(directory / "journal.json")["publication_status"]
        == "ROLLED_BACK"
    )
    assert finishes[0] == finishes[1] and finishes[0]["action"] == "rollback"


def test_finalize_preflight_conflict_requests_bounded_rollback_without_git(
    tmp_path, monkeypatch
):
    directory, candidate, baseline = frozen(tmp_path)
    batch = {"batch_token": "c" * 64, "batch_manifest_sha256": "d" * 64}
    direct.save(
        directory / "journal.json",
        {
            "candidate_id": candidate["candidate_id"],
            "publication_status": "APPLIED",
            "proposals": {"reviewed": "b" * 64},
            "post_ids": {"reviewed": 11},
            "batch": batch,
            "checkpoint": candidate["checkpoint"],
        },
    )
    actions = []
    monkeypatch.setattr(
        direct, "sync_git", lambda *a: pytest.fail("must not sync failed publication")
    )

    def call(command, body):
        if command == "document":
            return baseline
        if command == "operation-status":
            return {"operation": {"state": "APPLIED"}}
        assert command == "finish"
        actions.append(body["action"])
        return {
            "schema": "RAOSOwnerDirectBatchResultV1",
            "profile": direct.PROFILE,
            **batch,
            "state": "PARTIAL_CONFLICT",
            "members": [],
        }

    with pytest.raises(direct.DirectFailure):
        direct.publish(tmp_path, directory, candidate["candidate_id"], call)
    assert actions == ["finalize", "rollback"]
    assert (
        direct.read_json(directory / "journal.json")["publication_status"]
        == "PARTIAL_CONFLICT"
    )


def test_wrong_preview_candidate_does_not_invoke_server(tmp_path):
    directory, candidate, _ = frozen(tmp_path)
    direct.save(
        directory / "preview.json",
        {
            "status": "PASS",
            "candidate_id": "0" * 64,
            "source_sha256": candidate["source_sha256"],
        },
    )
    with pytest.raises(direct.DirectFailure, match="PREVIEW_REQUIRED"):
        direct.publish(
            tmp_path,
            directory,
            candidate["candidate_id"],
            lambda *a: pytest.fail("server contacted"),
        )


@pytest.mark.parametrize(
    "mismatch",
    [
        "missing",
        "article_key",
        "post_id",
        "post_type",
        "slug",
        "matched",
        "disabled",
        "offline",
    ],
)
def test_prepare_undelegated_existing_target_keeps_local_candidate_and_continues(
    tmp_path, mismatch
):
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "README.md").write_text("seed")
    git("add", "README.md")
    git("commit", "-m", "seed")
    rows = []
    for index, key in enumerate(("undelegated", "delegated"), 10):
        source = f"changes/wordpress-direct-publish-v1/articles/{key}.html"
        (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / source).write_text(f"reviewed {key} body")
        rows.append(
            {
                "article_key": key,
                "mode": "existing",
                "post_id": index,
                "post_type": "page",
                "title": key,
                "slug": key,
                "body_source": source,
            }
        )
    direct.save(
        tmp_path / direct.REGISTRY,
        {
            "schema": "RAOSOwnerDirectArticlesV1",
            "profile": direct.PROFILE,
            "articles": rows,
        },
    )
    targets = [
        {key: row[key] for key in ("article_key", "post_id", "post_type", "slug")}
        for row in rows
    ]
    if mismatch == "missing":
        targets.pop(0)
    elif mismatch not in {"matched", "disabled", "offline"}:
        targets[0][mismatch] = 99 if mismatch == "post_id" else "different"
    calls = []
    baseline = {"excerpt": "", "taxonomies": {}, "media_ids": []}

    def call(command, body):
        calls.append((command, body))
        if command == "status":
            if mismatch == "offline":
                raise operator.OperatorFailure("WORDPRESS_MCP_PRIVATE_FILE_UNAVAILABLE")
            return {
                "schema": "RAOSOwnerDirectStatusV1",
                "profile": direct.PROFILE,
                "enabled": mismatch != "disabled",
                "profile_sha256": "a" * 64,
                "theme": {"tree_sha256": "b" * 64},
                "targets": targets,
            }
        return baseline

    candidate, directory = direct.prepare(
        tmp_path, ["undelegated", "delegated"], call=call
    )
    if mismatch == "matched":
        assert calls == [
            ("status", {}),
            ("document", {"id": 10}),
            ("document", {"id": 11}),
        ]
        assert candidate["publication_ready"] is True
        assert all(article["baseline"] == baseline for article in candidate["articles"])
    elif mismatch in {"disabled", "offline"}:
        assert calls == [("status", {})]
        assert candidate["publication_ready"] is False
        assert all(article["baseline"] is None for article in candidate["articles"])
    else:
        assert calls == [("status", {}), ("document", {"id": 11})]
        assert candidate["publication_ready"] is False
        assert candidate["articles"][0]["baseline"] is None
        assert candidate["articles"][0]["baseline_unavailable_reason"].startswith(
            "TARGET_"
        )
        assert candidate["articles"][1]["baseline"] == baseline
    assert candidate["status_unavailable_reason"] == (
        "WORDPRESS_MCP_PRIVATE_FILE_UNAVAILABLE" if mismatch == "offline" else None
    )
    assert len(candidate["articles"]) == 2
    assert (
        directory / candidate["articles"][0]["body_file"]
    ).read_text() == "reviewed undelegated body"


def test_content_hash_uses_server_utf8_json_without_changing_candidate_encoding():
    document = {"title": "ホーム", "block_markup": "<p>選び方 / 使い方</p>", "taxonomies": []}
    material = {"schema": "ContentDocumentV1", "id": 15, "status": "publish", **document}
    import hashlib
    import json
    expected = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    assert direct.content_after_sha256(document, 15) == expected
    assert b"\\u30db" in direct.encoded(document)
