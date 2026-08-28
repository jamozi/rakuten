#!/usr/bin/env python3
"""Direct HTTP MCP and deployment E2E client for the disposable WordPress site."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any
import urllib.error
import urllib.request


ORIGIN = "https://kurashinoshirube.com"
HOST = "kurashinoshirube.com"
PROTOCOL_VERSION = "2025-11-25"
EXPECTED_TOOLS = {
    "raos-codex-site-status",
    "raos-codex-content-list",
    "raos-codex-content-get",
    "raos-codex-content-create-draft",
    "raos-codex-content-update-draft",
    "raos-codex-content-propose-release",
    "raos-codex-operation-get",
}


class HttpFailure(RuntimeError):
    def __init__(self, status: int, body: bytes):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def authorization(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def request(
    url: str,
    username: str,
    password: str,
    *,
    method: str = "GET",
    value: object | None = None,
    raw_data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, Any]:
    merged_headers = {
        "Accept": "application/json",
        "Authorization": authorization(username, password),
        "Host": HOST,
        "User-Agent": "raos-wordpress-e2e/1.0.0",
    }
    merged_headers.update(headers or {})
    if value is not None and raw_data is not None:
        raise RuntimeError("request body is ambiguous")
    data = raw_data
    if value is not None:
        data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        merged_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=merged_headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as response:
            body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                raise RuntimeError("response too large")
            return response.status, body, response.headers
    except urllib.error.HTTPError as error:
        raise HttpFailure(error.code, error.read(64 * 1024)) from None


def error_code(failure: HttpFailure) -> str | None:
    try:
        payload = json.loads(failure.body)
    except UnicodeError, json.JSONDecodeError:
        return None
    return payload.get("code") if isinstance(payload, dict) else None


def expect_http_failure(callable_, status: int, code: str) -> None:
    try:
        callable_()
    except HttpFailure as failure:
        assert failure.status == status, failure.body
        assert error_code(failure) == code, failure.body
        return
    raise AssertionError(f"expected HTTP {status} {code}")


class McpClient:
    def __init__(self, endpoint: str, username: str, password: str):
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.session_id: str | None = None
        self.next_id = 1

    def message(self, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = self.next_id
        self.next_id += 1
        headers = {"Accept": "application/json, text/event-stream"}
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
            headers["Mcp-Protocol-Version"] = PROTOCOL_VERSION
        _, body, response_headers = request(
            self.endpoint,
            self.username,
            self.password,
            method="POST",
            value={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
            headers=headers,
        )
        payload = json.loads(body)
        assert payload.get("jsonrpc") == "2.0", payload
        assert payload.get("id") == request_id, payload
        assert "error" not in payload, payload
        if method == "initialize":
            self.session_id = response_headers.get("Mcp-Session-Id")
            assert self.session_id
        result = payload.get("result")
        assert isinstance(result, dict), payload
        return result

    def initialize(self) -> dict[str, object]:
        result = self.message(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "raos-e2e", "version": "1.0.0"},
            },
        )
        assert result["protocolVersion"] == PROTOCOL_VERSION
        assert "Draft editing" in str(result.get("instructions"))
        assert self.session_id is not None
        status, body, _ = request(
            self.endpoint,
            self.username,
            self.password,
            method="POST",
            value={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={
                "Accept": "application/json, text/event-stream",
                "Mcp-Protocol-Version": PROTOCOL_VERSION,
                "Mcp-Session-Id": self.session_id,
            },
        )
        assert status == 202 and body in {b"", b"null"}
        return result

    def tools(self) -> dict[str, dict[str, object]]:
        listed = self.message("tools/list", {})["tools"]
        assert isinstance(listed, list)
        return {tool["name"]: tool for tool in listed}

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = self.message("tools/call", {"name": name, "arguments": arguments})
        assert result.get("isError") is not True, result
        structured = result.get("structuredContent")
        assert isinstance(structured, dict), result
        return structured


def full_document(post_type: str, suffix: str) -> dict[str, object]:
    return {
        "post_type": post_type,
        "title": f"RAOS E2E {post_type} {suffix}",
        "slug": f"raos-e2e-{post_type}-{suffix}",
        "excerpt": f"E2E excerpt {suffix}",
        "block_markup": (
            "<!-- wp:paragraph -->"
            f"<p>RAOS browser-independent E2E {suffix}</p>"
            "<!-- /wp:paragraph -->"
        ),
        "taxonomies": {},
        "media_ids": [],
    }


def precondition(document: dict[str, object]) -> dict[str, object]:
    return {
        "revision_id": document["revision_id"],
        "modified_gmt": document["modified_gmt"],
        "content_sha256": document["content_sha256"],
    }


def write_projection(document: dict[str, object]) -> dict[str, object]:
    return {
        key: document[key]
        for key in (
            "post_type",
            "title",
            "slug",
            "excerpt",
            "block_markup",
            "taxonomies",
            "media_ids",
        )
    }


def operator_request(
    base_url: str,
    username: str,
    password: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    value: object | None = None,
) -> dict[str, object]:
    _, body, _ = request(
        base_url + path,
        username,
        password,
        method="POST",
        value={} if value is None else value,
        headers=headers,
    )
    value = json.loads(body)
    assert isinstance(value, dict), value
    return value


def assert_route_confinement(
    site_url: str,
    editor: tuple[str, str],
    operator: tuple[str, str],
) -> None:
    for username, password in (editor, operator):
        expect_http_failure(
            lambda: request(site_url + "/wp-json/wp/v2/users/me", username, password),
            403,
            "raos_codex_rest_scope_forbidden",
        )
        xml = """<?xml version="1.0"?>
<methodCall><methodName>wp.getUsersBlogs</methodName><params>
<param><value><string>{}</string></value></param>
<param><value><string>{}</string></value></param>
</params></methodCall>""".format(username, password)
        try:
            _, body, _ = request(
                site_url + "/xmlrpc.php",
                username,
                password,
                method="POST",
                headers={"Content-Type": "text/xml"},
                raw_data=xml.encode("utf-8"),
            )
        except HttpFailure as failure:
            body = failure.body
        assert b"<name>blogName</name>" not in body


def phase_propose(
    state_path: Path,
    site_url: str,
    editor: tuple[str, str],
    operator: tuple[str, str],
) -> None:
    mcp = McpClient(site_url + "/wp-json/raos-codex-mcp/v1/editor", *editor)
    initialized = mcp.initialize()
    assert initialized["serverInfo"]["version"] == "1.0.2"
    tools = mcp.tools()
    assert set(tools) == EXPECTED_TOOLS
    for tool in tools.values():
        annotations = tool.get("annotations")
        assert isinstance(annotations, dict)
        assert annotations["destructiveHint"] is False
        assert annotations["openWorldHint"] is False

    status = mcp.call("raos-codex-site-status", {})
    assert status["origin"] == ORIGIN
    assert status["wordpress_version"].startswith("7.1")
    assert status["mcp_adapter_version"] == "0.6.1"
    assert status["writes_enabled"] == {
        "global": True,
        "draft": True,
        "content_apply": True,
        "theme_apply": True,
        "plugin_apply": True,
    }

    deploy_base = site_url + "/wp-json/raos-codex-deploy/v1"
    _, deploy_status_body, _ = request(deploy_base + "/status", *operator)
    deploy_status = json.loads(deploy_status_body)
    assert deploy_status["origin"] == ORIGIN
    assert deploy_status["private_directory_ready"] is True
    assert_route_confinement(site_url, editor, operator)

    proposals: list[dict[str, object]] = []
    for post_type in ("post", "page"):
        created = mcp.call(
            "raos-codex-content-create-draft", full_document(post_type, "created")
        )
        assert created["status"] == "draft"
        partially_updated = mcp.call(
            "raos-codex-content-update-draft",
            {
                "id": created["id"],
                "mode": "partial",
                "precondition": precondition(created),
                "changes": {"excerpt": "E2E partial update"},
            },
        )
        replacement = full_document(post_type, "replacement")
        replacement["slug"] = created["slug"]
        replaced = mcp.call(
            "raos-codex-content-update-draft",
            {
                "id": created["id"],
                "mode": "replace",
                "precondition": precondition(partially_updated),
                "changes": replacement,
            },
        )
        release = write_projection(replaced)
        release["title"] = f"Published RAOS E2E {post_type}"
        release["block_markup"] = (
            "<!-- wp:paragraph -->"
            f"<p>Approved {post_type} release</p>"
            "<!-- /wp:paragraph -->"
        )
        proposal = mcp.call(
            "raos-codex-content-propose-release",
            {
                "id": replaced["id"],
                "precondition": precondition(replaced),
                "document": release,
            },
        )
        readback = mcp.call("raos-codex-content-get", {"id": replaced["id"]})
        assert readback["status"] == "draft"
        assert readback["content_sha256"] == replaced["content_sha256"]
        proposals.append(
            {
                "proposal_id": proposal["proposal_id"],
                "post_id": replaced["id"],
                "after_sha256": proposal["after_sha256"],
            }
        )

    first_id = proposals[0]["proposal_id"]
    assert isinstance(first_id, str)
    expect_http_failure(
        lambda: operator_request(
            deploy_base,
            *operator,
            f"/proposals/{first_id}/apply",
            headers={
                "If-Match": f'"{first_id}"',
                "Idempotency-Key": first_id,
            },
        ),
        409,
        "raos_codex_apply_precondition_failed",
    )
    expect_http_failure(
        lambda: operator_request(
            deploy_base,
            *operator,
            f"/proposals/{first_id}/apply",
            headers={"If-Match": '"' + ("0" * 64) + '"', "Idempotency-Key": first_id},
        ),
        412,
        "raos_codex_apply_headers_invalid",
    )

    drift = mcp.call("raos-codex-content-create-draft", full_document("post", "drift"))
    drift_release = write_projection(drift)
    drift_release["title"] = "This proposal must drift"
    drift_proposal = mcp.call(
        "raos-codex-content-propose-release",
        {
            "id": drift["id"],
            "precondition": precondition(drift),
            "document": drift_release,
        },
    )

    artifact_path = Path(required_environment("RAOS_WORDPRESS_E2E_ARTIFACTS"))
    artifacts = json.loads(artifact_path.read_text(encoding="ascii"))
    assert artifacts["schema"] == "RAOS_WORDPRESS_E2E_CODE_ARTIFACTS_V1"
    code_proposals: list[dict[str, object]] = []
    expected = (
        ("theme", "THEME_RELEASE_APPLIED", False),
        ("plugin_success", "PLUGIN_CHANGE_APPLIED", False),
        ("plugin_rollback", "raos_codex_code_readback_failed", True),
    )
    for name, result_code, should_fail in expected:
        created = operator_request(
            deploy_base,
            *operator,
            "/proposals",
            value=artifacts[name],
        )
        operation = created["operation"]
        proposal = created["proposal"]
        assert operation["state"] == "PENDING"
        assert proposal["proposal_id"] == operation["proposal_id"]
        code_proposals.append(
            {
                "name": name,
                "proposal_id": proposal["proposal_id"],
                "after_sha256": operation["after_sha256"],
                "result_code": result_code,
                "should_fail": should_fail,
            }
        )
    state = {
        "schema": "RAOS_WORDPRESS_E2E_STATE_V1",
        "proposals": proposals,
        "code_proposals": code_proposals,
        "drift": {
            "proposal_id": drift_proposal["proposal_id"],
            "post_id": drift["id"],
        },
    }
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    state_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def phase_apply(
    state_path: Path,
    site_url: str,
    editor: tuple[str, str],
    operator: tuple[str, str],
) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema"] == "RAOS_WORDPRESS_E2E_STATE_V1"
    mcp = McpClient(site_url + "/wp-json/raos-codex-mcp/v1/editor", *editor)
    mcp.initialize()
    deploy_base = site_url + "/wp-json/raos-codex-deploy/v1"
    first_receipt: dict[str, object] | None = None
    for item in state["proposals"]:
        proposal_id = item["proposal_id"]
        headers = {
            "If-Match": f'"{proposal_id}"',
            "Idempotency-Key": proposal_id,
        }
        receipt = operator_request(
            deploy_base,
            *operator,
            f"/proposals/{proposal_id}/apply",
            headers=headers,
        )
        assert receipt["schema"] == "OperationReceiptV1"
        assert receipt["state"] == "APPLIED"
        assert receipt["result_code"] == "CONTENT_RELEASE_APPLIED"
        assert receipt["after_sha256"] == item["after_sha256"]
        recovered = operator_request(
            deploy_base,
            *operator,
            f"/operations/{proposal_id}/recover",
        )
        assert recovered == receipt
        document = mcp.call("raos-codex-content-get", {"id": item["post_id"]})
        assert document["status"] == "publish"
        assert document["content_sha256"] == item["after_sha256"]
        operation = mcp.call("raos-codex-operation-get", {"operation_id": proposal_id})
        assert operation["state"] == "APPLIED"
        if first_receipt is None:
            first_receipt = receipt
            assert (
                operator_request(
                    deploy_base,
                    *operator,
                    f"/proposals/{proposal_id}/apply",
                    headers=headers,
                )
                == receipt
            )

    drift_id = state["drift"]["proposal_id"]
    expect_http_failure(
        lambda: operator_request(
            deploy_base,
            *operator,
            f"/proposals/{drift_id}/apply",
            headers={
                "If-Match": f'"{drift_id}"',
                "Idempotency-Key": drift_id,
            },
        ),
        412,
        "raos_codex_content_hash_drift",
    )
    drift_operation = operator_request(
        deploy_base,
        *operator,
        f"/operations/{drift_id}/recover",
    )
    assert drift_operation["state"] == "FAILED"

    for item in state["code_proposals"]:
        proposal_id = item["proposal_id"]
        headers = {
            "If-Match": f'"{proposal_id}"',
            "Idempotency-Key": proposal_id,
        }
        if item["should_fail"]:
            expect_http_failure(
                lambda: operator_request(
                    deploy_base,
                    *operator,
                    f"/proposals/{proposal_id}/apply",
                    headers=headers,
                ),
                500,
                item["result_code"],
            )
            failed = operator_request(
                deploy_base,
                *operator,
                f"/operations/{proposal_id}/recover",
            )
            assert failed["state"] == "FAILED"
            continue
        receipt = operator_request(
            deploy_base,
            *operator,
            f"/proposals/{proposal_id}/apply",
            headers=headers,
        )
        assert receipt["state"] == "APPLIED"
        assert receipt["result_code"] == item["result_code"]
        assert receipt["after_sha256"] == item["after_sha256"]
        assert (
            operator_request(
                deploy_base,
                *operator,
                f"/proposals/{proposal_id}/apply",
                headers=headers,
            )
            == receipt
        )
        assert (
            operator_request(
                deploy_base,
                *operator,
                f"/operations/{proposal_id}/recover",
            )
            == receipt
        )
        if item["name"] == "theme":
            _, status_body, _ = request(deploy_base + "/status", *operator)
            status = json.loads(status_body)
            assert status["theme"]["tree_sha256"] == item["after_sha256"]
            assert status["theme"]["active"] is True
    assert_route_confinement(site_url, editor, operator)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("propose", "apply"))
    parser.add_argument("state_path", type=Path)
    arguments = parser.parse_args()
    port = required_environment("RAOS_WORDPRESS_E2E_PORT")
    site_url = f"http://127.0.0.1:{port}"
    editor = (
        required_environment("RAOS_WORDPRESS_E2E_EDITOR_USER"),
        required_environment("RAOS_WORDPRESS_E2E_EDITOR_PASSWORD"),
    )
    operator = (
        required_environment("RAOS_WORDPRESS_E2E_OPERATOR_USER"),
        required_environment("RAOS_WORDPRESS_E2E_OPERATOR_PASSWORD"),
    )
    if arguments.phase == "propose":
        phase_propose(arguments.state_path, site_url, editor, operator)
    else:
        phase_apply(arguments.state_path, site_url, editor, operator)
    print(f"RAOS_WORDPRESS_E2E_{arguments.phase.upper()}_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, OSError, ValueError) as error:
        print(f"RAOS_WORDPRESS_E2E_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from None
