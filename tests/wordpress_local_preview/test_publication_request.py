from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_wordpress_publication_request.py"
SPEC = importlib.util.spec_from_file_location("wordpress_publication_request", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
publication = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publication
SPEC.loader.exec_module(publication)


def test_mapping_is_closed_numeric_and_exact_slug_conversion() -> None:
    mapping = json.loads(
        (
            ROOT / "changes/wordpress-local-preview-v1/production-mapping.v1.json"
        ).read_text(encoding="utf-8")
    )
    articles = publication.load_articles("all")

    assert mapping["origin"] == publication.ORIGIN
    assert mapping["editor_endpoint"] == publication.EDITOR_ENDPOINT
    assert mapping["review_url"] == publication.REVIEW_URL
    assert len(articles) == 5
    for row in mapping["articles"]:
        assert row["production_slug"] == row["local_slug"].removeprefix(
            "local-preview-"
        )
        assert row["taxonomies"] == {
            "category": [5],
            "post_format": [],
            "post_tag": [],
        }
        assert all(type(term_id) is int for term_id in row["taxonomies"]["category"])


def test_tracked_theme_hash_matches_the_bounded_operator_manifest() -> None:
    operator_path = ROOT / "scripts/raos_wordpress_deployment_operator.py"
    specification = importlib.util.spec_from_file_location(
        "wordpress_deployment_operator_for_publication_test", operator_path
    )
    assert specification is not None and specification.loader is not None
    operator = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = operator
    specification.loader.exec_module(operator)
    _, descriptor = operator.theme_package()
    assert publication.tracked_theme_tree_sha256() == descriptor["file_manifest_sha256"]


def test_article_selection_is_exact_production_slug_csv() -> None:
    selected = publication.load_articles(
        "roomba-mini-vs-switchbot-k11-pro,solota-vs-rakua-mini-plus"
    )
    assert [article.production_slug for article in selected] == [
        "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus",
    ]
    for invalid in (
        "",
        "local-preview-roomba-mini-vs-switchbot-k11-pro",
        "unknown-slug",
        "roomba-mini-vs-switchbot-k11-pro,roomba-mini-vs-switchbot-k11-pro",
        "roomba-mini-vs-switchbot-k11-pro, solota-vs-rakua-mini-plus",
    ):
        with pytest.raises(
            publication.PublicationFailure,
            match="RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID",
        ):
            publication.load_articles(invalid)


def _document(
    article: Any, post_id: int = 82, *, status: str = "draft"
) -> dict[str, Any]:
    value = article.document() | {
        "schema": "ContentDocumentV1",
        "id": post_id,
        "status": status,
        "revision_id": post_id,
        "modified_gmt": "2026-08-29T00:00:00Z",
        "content_sha256": f"{post_id:064x}",
    }
    return value


class ReconcileClient:
    def __init__(self, readback: dict[str, Any]) -> None:
        self.readback = readback
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "raos-codex-content-get":
            return self.readback
        if name == "raos-codex-content-update-draft":
            return self.readback
        raise AssertionError(name)


def _private_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    os.chmod(tmp_path, 0o700)
    directory = tmp_path / "publication-requests"
    monkeypatch.setattr(publication, "PRIVATE_REQUEST_DIRECTORY", directory)
    publication._ensure_private_directory()
    return directory / "request.json"


def test_exact_draft_is_reused_and_read_back_without_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    document = _document(article)
    client = ReconcileClient(document)
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)

    result = publication.reconcile_drafts(client, [article], [document], receipt, path)

    assert result[article.production_slug] == document
    assert [name for name, _ in client.calls] == ["raos-codex-content-get"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_known_draft_is_cas_replaced_but_unknown_drift_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    drifted = _document(article)
    drifted["title"] = "prior workflow title"
    updated = _document(article)
    client = ReconcileClient(updated)
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)

    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_UNKNOWN_DRAFT_DRIFT",
    ):
        publication.reconcile_drafts(client, [article], [drifted], receipt, path)

    receipt["drafts"] = {
        article.production_slug: {
            "id": drifted["id"],
            "content_sha256": drifted["content_sha256"],
        }
    }
    client.calls.clear()
    publication.reconcile_drafts(client, [article], [drifted], receipt, path)
    update = next(arguments for name, arguments in client.calls if "update" in name)
    assert update["mode"] == "replace"
    assert update["precondition"]["content_sha256"] == drifted["content_sha256"]


def test_published_slug_conflict_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    published = _document(article, status="publish")
    path = _private_path(monkeypatch, tmp_path)
    receipt = publication._fresh_receipt([article], path)
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PUBLISHED_CONFLICT",
    ):
        publication.reconcile_drafts(
            ReconcileClient(published), [article], [published], receipt, path
        )


class PaginatedClient:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.pages: list[int] = []

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "raos-codex-content-list"
        page = arguments["page"]
        assert isinstance(page, int)
        self.pages.append(page)
        start = (page - 1) * publication.LIST_PER_PAGE
        return {
            "schema": "ContentDocumentListV1",
            "page": page,
            "per_page": publication.LIST_PER_PAGE,
            "total": len(self.documents),
            "documents": self.documents[start : start + publication.LIST_PER_PAGE],
        }


def test_content_list_fetches_every_page() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    documents = [_document(article, post_id=index) for index in range(1, 24)]
    client = PaginatedClient(documents)
    assert publication.list_all_documents(client) == documents
    assert client.pages == [1, 2, 3]


def _tools() -> dict[str, dict[str, object]]:
    result = {name: {} for name in publication.EXPECTED_TOOLS}
    result["raos-codex-content-propose-release"] = {
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "precondition", "document"],
            "properties": {
                "idempotency_key": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            },
        }
    }
    result["raos-codex-publication-batch-register"] = {
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["proposal_ids"],
            "properties": {
                "proposal_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                }
            },
        }
    }
    return result


def _deployment_tools() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name in sorted(publication.EXPECTED_DEPLOYMENT_TOOLS):
        schema: dict[str, object] = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        if name == "theme-propose-release":
            schema["properties"] = {
                "idempotency_key": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                }
            }
        if name == "release-wait-and-apply":
            schema["required"] = ["proposal_ids"]
            schema["properties"] = {
                "proposal_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                }
            }
        result.append(
            {
                "name": name,
                "inputSchema": schema,
                "annotations": {
                    "readOnlyHint": name == "deployment-status",
                    "destructiveHint": name
                    in {
                        "release-wait-and-apply",
                        "content-apply-release",
                        "theme-apply-release",
                        "plugin-apply-change",
                        "operation-recover",
                    },
                    "idempotentHint": name
                    not in {"theme-propose-release", "plugin-propose-change"},
                    "openWorldHint": name == "plugin-propose-change",
                },
            }
        )
    return result


class WorkflowClient:
    def __init__(self, article: Any, events: list[str]) -> None:
        self.article = article
        self.events = events
        self.document = _document(article)
        self.published = False

    def initialize(self) -> None:
        self.events.append("remote-initialize")

    def tools(self) -> dict[str, dict[str, object]]:
        return _tools()

    def status(self) -> dict[str, object]:
        return {
            "schema": "RAOSWordPressSiteStatusV1",
            "origin": publication.ORIGIN,
            "wordpress_version_compatible": True,
            "mcp_adapter_version": "0.6.1",
            "mcp_adapter_version_compatible": True,
            "plugin_version": publication.EXPECTED_PLUGIN_VERSION,
            "writes_enabled": {
                "global": True,
                "draft": True,
                "content_apply": True,
                "theme_apply": True,
            },
            "theme": {
                "slug": "kurashinoshirube-child",
                "exists": True,
                "active": True,
                "version": publication.theme_version(),
            },
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
                "ttl_seconds": 900,
            },
            "server": {
                "endpoint": publication.EDITOR_ENDPOINT,
                "publish_tool_exposed": False,
                "delete_tool_exposed": False,
                "media_write_tool_exposed": False,
                "proposal_ttl_seconds": 900,
            },
        }

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        self.events.append(name)
        if name == "raos-codex-site-status":
            return self.status()
        if name == "raos-codex-content-list":
            return {
                "schema": "ContentDocumentListV1",
                "page": 1,
                "per_page": publication.LIST_PER_PAGE,
                "total": 1,
                "documents": [self.document],
            }
        if name == "raos-codex-content-get":
            return self.document | {"status": "publish" if self.published else "draft"}
        if name == "raos-codex-content-propose-release":
            assert publication.SHA256_RE.fullmatch(str(arguments["idempotency_key"]))
            return {
                "schema": "ContentReleaseProposalV1",
                "proposal_id": "a" * 64,
                "after_sha256": publication._content_after_sha256(
                    self.article.document(), self.document["id"]
                ),
                "expires_at_gmt": "2099-08-29T00:15:00Z",
            }
        if name == "raos-codex-publication-batch-register":
            proposal_ids = arguments["proposal_ids"]
            assert isinstance(proposal_ids, list)
            assert proposal_ids == sorted(proposal_ids)
            return {
                "schema": "RAOSWordPressPublicationBatchV1",
                "batch_token": "c" * 64,
                "batch_manifest_sha256": "d" * 64,
                "proposal_count": len(proposal_ids),
                "proposal_ids": proposal_ids,
                "expires_at_gmt": "2099-08-29T00:15:00Z",
                "review_url": publication.REVIEW_URL,
            }
        raise AssertionError(name)


class DeploymentRunner:
    def __init__(
        self,
        client: WorkflowClient,
        events: list[str],
        *,
        fail_first_wait: bool = False,
    ) -> None:
        self.client = client
        self.events = events
        self.fail_first_wait = fail_first_wait
        self.watcher_calls = 0
        self.theme_proposed = False
        self.local_tree = publication.tracked_theme_tree_sha256()
        self.live_tree = "9" * 64

    def status(self) -> dict[str, object]:
        return {
            "schema": "RAOSWordPressDeploymentStatusV1",
            "origin": publication.ORIGIN,
            "php_version": "8.3.0",
            "wordpress_version": "7.1.0",
            "theme": {
                "slug": "kurashinoshirube-child",
                "version": publication.theme_version(),
                "active": True,
                "tree_sha256": self.live_tree,
            },
            "gates": {
                "global": True,
                "content_apply": True,
                "theme_apply": True,
                "plugin_apply": True,
            },
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
                "ttl_seconds": 900,
            },
            "private_directory_ready": True,
        }

    def __call__(
        self, arguments: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert arguments == (
            publication.NODE_BIN.as_posix(),
            "--experimental-strip-types",
            publication.DEPLOYMENT_BRIDGE.as_posix(),
        )
        messages = [
            json.loads(line)
            for line in bytes(kwargs["input"]).decode("utf-8").splitlines()
        ]
        assert [message["method"] for message in messages] == [
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/call",
        ]
        call = messages[3]["params"]
        name = call["name"]
        tool_arguments = call["arguments"]
        self.events.append(f"deployment:{name}")
        if name == "deployment-status":
            value = self.status()
        elif name == "theme-propose-release":
            self.theme_proposed = True
            assert publication.SHA256_RE.fullmatch(tool_arguments["idempotency_key"])
            value = {
                "proposal": {
                    "proposal_id": "b" * 64,
                    "after_tree_sha256": self.local_tree,
                    "expires_at_gmt": "2099-08-29T00:15:00Z",
                }
            }
        elif name == "release-wait-and-apply":
            self.watcher_calls += 1
            expected_ids = ["a" * 64]
            if self.theme_proposed:
                expected_ids.append("b" * 64)
            assert tool_arguments == {"proposal_ids": sorted(expected_ids)}
            if self.fail_first_wait and self.watcher_calls == 1:
                value = {"code": "WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT"}
                return self._response(arguments, value, is_error=True)
            self.client.published = True
            if self.theme_proposed:
                self.live_tree = self.local_tree
            receipts: list[dict[str, object]] = []
            if self.theme_proposed:
                receipts.append(
                    {
                        "schema": "OperationReceiptV1",
                        "proposal_id": "b" * 64,
                        "operation_id": "b" * 64,
                        "state": "APPLIED",
                        "result_code": "THEME_RELEASE_APPLIED",
                        "before_sha256": "9" * 64,
                        "after_sha256": self.local_tree,
                        "audit_id": "2" * 64,
                    }
                )
            receipts.append(
                {
                    "schema": "OperationReceiptV1",
                    "proposal_id": "a" * 64,
                    "operation_id": "a" * 64,
                    "state": "APPLIED",
                    "result_code": "CONTENT_RELEASE_APPLIED",
                    "before_sha256": "0" * 64,
                    "after_sha256": publication._content_after_sha256(
                        self.client.article.document(), self.client.document["id"]
                    ),
                    "audit_id": "3" * 64,
                }
            )
            value = {
                "schema": "ReleaseWaitApplyReceiptV1",
                "state": "APPLIED",
                "receipts": receipts,
            }
        else:
            raise AssertionError(name)
        return self._response(arguments, value)

    @staticmethod
    def _response(
        arguments: tuple[str, ...], value: dict[str, object], *, is_error: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        responses = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": publication.PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": "raos-wordpress-bridge",
                        "version": "1.1.0",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": _deployment_tools()},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(value)}],
                    "structuredContent": value,
                    **({"isError": True} if is_error else {}),
                },
            },
        ]
        output = b"".join(
            json.dumps(response).encode("utf-8") + b"\n" for response in responses
        )
        return subprocess.CompletedProcess(arguments, 0, output, b"")


def test_full_workflow_checks_local_before_remote_and_runs_foreground_watcher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events)

    def preview() -> None:
        events.append("local-preview")

    path = publication.execute(
        article.production_slug,
        preview=preview,
        client_factory=lambda: client,
        deployment_runner=deployment,
    )

    assert events[0:2] == ["local-preview", "remote-initialize"]
    assert "deployment:theme-propose-release" in events
    assert "deployment:release-wait-and-apply" in events
    assert events.count("deployment:deployment-status") == 2
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["state"] == "APPLIED"
    assert receipt["desired_theme_tree_sha256"] == deployment.local_tree
    assert receipt["batch_registration"]["proposal_ids"] == ["a" * 64, "b" * 64]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    output = capsys.readouterr().out
    assert "承認対象バッチtoken末尾12文字: cccccccccccc" in output
    assert "入力するbatch manifest hash末尾8文字: dddddddd" in output
    assert publication.REVIEW_URL in output


def test_rerun_resumes_the_same_proposal_after_wait_response_loss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)

    with pytest.raises(
        publication.PublicationFailure,
        match="WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    receipt_path = next(publication.PRIVATE_REQUEST_DIRECTORY.glob("request-*.json"))
    interrupted = json.loads(receipt_path.read_text(encoding="utf-8"))
    interrupted["proposals"][0]["expires_at_gmt"] = "2026-08-29T00:00:00Z"
    publication._atomic_receipt(receipt_path, interrupted)

    path = publication.execute(
        article.production_slug,
        preview=lambda: events.append("local-preview"),
        client_factory=lambda: client,
        deployment_runner=deployment,
    )
    assert deployment.watcher_calls == 2
    assert events.count("raos-codex-content-propose-release") == 1
    assert events.count("raos-codex-content-list") == 1
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "APPLIED"


def test_content_only_resume_stops_before_apply_if_exact_live_theme_drifted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    events: list[str] = []
    client = WorkflowClient(article, events)
    _private_path(monkeypatch, tmp_path)
    deployment = DeploymentRunner(client, events, fail_first_wait=True)
    deployment.live_tree = deployment.local_tree

    with pytest.raises(
        publication.PublicationFailure,
        match="WORDPRESS_MCP_RELEASE_WAIT_TIMEOUT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    deployment.live_tree = "9" * 64
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_PENDING_THEME_DRIFT",
    ):
        publication.execute(
            article.production_slug,
            preview=lambda: events.append("local-preview"),
            client_factory=lambda: client,
            deployment_runner=deployment,
        )

    assert deployment.watcher_calls == 1
    assert client.published is False
    assert events.count("raos-codex-content-propose-release") == 1


def test_missing_idempotency_schema_stops_before_mutation() -> None:
    tools = _tools()
    del tools["raos-codex-content-propose-release"]["inputSchema"]["properties"]
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED",
    ):
        publication.validate_tool_contract(tools)


def test_site_status_requires_plugin_1_2_and_scoped_approval_lease() -> None:
    article = publication.load_articles("roomba-mini-vs-switchbot-k11-pro")[0]
    client = WorkflowClient(article, [])
    status = client.status()
    status["plugin_version"] = "1.1.0"
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)
    status = client.status()
    status["apply_authorization"] = {
        "mode": "approval_scoped_lease",
        "default": True,
        "single_use": True,
        "ttl_seconds": 900,
    }
    with pytest.raises(
        publication.PublicationFailure,
        match="RAOS_WORDPRESS_REQUEST_SITE_NOT_READY",
    ):
        publication.validate_site_status(status)


def test_stale_docker_group_uses_only_fixed_sg_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publication, "_docker_group_membership_is_stale", lambda: True)
    commands: list[tuple[str, ...]] = []

    def runner(
        command: tuple[str, ...], **_: object
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    publication.run_preview_checks(runner)
    assert commands == [
        (
            "/usr/bin/sg",
            "docker",
            "-c",
            f"/usr/bin/make {target}",
        )
        for target in (
            "wordpress-preview-up",
            "wordpress-preview-sync",
            "wordpress-preview-check",
        )
    ]
    assert all("ARTICLES" not in part for command in commands for part in command)


def test_make_target_passes_articles_via_environment_without_shell_expansion() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "wordpress-production-request:" in makefile
    recipe = makefile[makefile.index("wordpress-production-request:") :]
    assert "$(ARTICLES)" not in recipe
    assert 'os.environ.get("ARTICLES", "all")' in SCRIPT.read_text(encoding="utf-8")


def test_seed_uses_the_production_markup_sanitizers() -> None:
    seed = (ROOT / "changes/wordpress-local-preview-v1/seed.php").read_text(
        encoding="utf-8"
    )
    assert "wp_strip_all_tags($post['title']) !== $post['title']" in seed
    assert "wp_kses_post($post['excerpt']) !== $post['excerpt']" in seed
    assert "wp_kses_post($content) !== $content" in seed
