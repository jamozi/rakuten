from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Callable

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_wordpress_deployment_operator.py"
SPEC = importlib.util.spec_from_file_location("raos_release_watcher", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)
ORIGINAL_RELEASE_BATCH_STATUS = operator._release_batch_status
ORIGINAL_RELEASE_BATCH_CLAIM = operator._release_batch_claim
BATCH_TOKEN = "4" * 64
BATCH_MANIFEST_SHA256 = "5" * 64


def release_input(proposal_ids: list[str]) -> dict[str, object]:
    return {
        "batch_token": BATCH_TOKEN,
        "batch_manifest_sha256": BATCH_MANIFEST_SHA256,
        "proposal_ids": sorted(proposal_ids),
    }


@pytest.fixture(autouse=True)
def exact_approved_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        operator,
        "_release_batch_status",
        lambda batch_token, batch_manifest_sha256, proposal_ids: ("APPROVED", True),
    )
    monkeypatch.setattr(
        operator,
        "_release_batch_claim",
        lambda batch_token, batch_manifest_sha256, proposal_ids: {},
    )


def public_operation(
    proposal_id: str,
    kind: str,
    state: str,
    *,
    result_code: str | None = None,
) -> dict[str, object]:
    result_codes = {
        "PENDING": "PROPOSAL_PENDING_APPROVAL",
        "APPROVED": "PROPOSAL_APPROVED",
        "APPLYING": "BATCH_CLAIMED",
        "APPLIED": (
            "THEME_RELEASE_APPLIED"
            if kind == "THEME_RELEASE"
            else "CONTENT_RELEASE_APPLIED"
        ),
        "EXPIRED": "PROPOSAL_EXPIRED",
        "FAILED": "OPERATION_FAILED",
        "MANUAL_REQUIRED": "MANUAL_REVIEW_REQUIRED",
    }
    return {
        "kind": kind,
        "operation": {
            "schema": "OperationReceiptV1",
            "proposal_id": proposal_id,
            "operation_id": proposal_id,
            "state": state,
            "result_code": result_code or result_codes[state],
            "before_sha256": "1" * 64,
            "after_sha256": "2" * 64,
            "audit_id": "3" * 64,
        },
    }


def assert_failure(code: str, callback: Callable[[], object]) -> None:
    with pytest.raises(operator.OperatorFailure) as raised:
        callback()
    assert str(raised.value) == code


def test_release_batch_status_requires_the_exact_server_registered_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operator, "_release_batch_status", ORIGINAL_RELEASE_BATCH_STATUS
    )
    proposal_ids = ["a" * 64, "b" * 64]
    response = {
        "schema": "RAOSWordPressPublicationBatchStatusV1",
        "batch_token": BATCH_TOKEN,
        "batch_manifest_sha256": BATCH_MANIFEST_SHA256,
        "proposal_count": 2,
        "proposal_ids": proposal_ids,
        "state": "APPROVED",
        "expires_at_gmt": "2026-08-29T12:00:00Z",
        "preconditions_ready": True,
    }
    calls: list[tuple[str, str]] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        calls.append((method, path))
        return dict(response)

    monkeypatch.setattr(operator, "request_json", request_json)
    assert operator._release_batch_status(
        BATCH_TOKEN,
        BATCH_MANIFEST_SHA256,
        proposal_ids,
    ) == ("APPROVED", True)
    assert calls == [("GET", f"/publication-batches/{BATCH_TOKEN}")]

    response["state"] = "APPLIED"
    response["preconditions_ready"] = False
    assert operator._release_batch_status(
        BATCH_TOKEN,
        BATCH_MANIFEST_SHA256,
        proposal_ids,
    ) == ("APPLIED", False)

    response["proposal_ids"] = [proposal_ids[0]]
    assert_failure(
        "WORDPRESS_MCP_RELEASE_BATCH_IDENTITY_INVALID",
        lambda: operator._release_batch_status(
            BATCH_TOKEN,
            BATCH_MANIFEST_SHA256,
            proposal_ids,
        ),
    )


def test_release_batch_claim_requires_exact_identity_and_atomic_member_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operator, "_release_batch_claim", ORIGINAL_RELEASE_BATCH_CLAIM)
    proposal_ids = ["a" * 64, "b" * 64]
    claimed_operations = [
        public_operation(proposal_id, "CONTENT_RELEASE", "APPLYING")["operation"]
        for proposal_id in proposal_ids
    ]
    response = {
        "schema": "RAOSWordPressPublicationBatchClaimV1",
        "batch_token": BATCH_TOKEN,
        "batch_manifest_sha256": BATCH_MANIFEST_SHA256,
        "proposal_count": len(proposal_ids),
        "proposal_ids": proposal_ids,
        "batch_claimed_at_gmt": "2026-08-29T12:00:00Z",
        "proposals": claimed_operations,
    }
    calls: list[tuple[str, str, object]] = []

    def request_json(method, path, body=None, *args, **kwargs):
        calls.append((method, path, body))
        return dict(response)

    monkeypatch.setattr(operator, "request_json", request_json)
    claimed = operator._release_batch_claim(
        BATCH_TOKEN,
        BATCH_MANIFEST_SHA256,
        proposal_ids,
    )
    assert list(claimed) == proposal_ids
    assert calls == [
        (
            "POST",
            f"/publication-batches/{BATCH_TOKEN}/claim",
            {
                "batch_manifest_sha256": BATCH_MANIFEST_SHA256,
                "proposal_ids": proposal_ids,
            },
        )
    ]

    response["proposal_ids"] = proposal_ids[:1]
    assert_failure(
        "WORDPRESS_MCP_RELEASE_BATCH_CLAIM_INVALID",
        lambda: operator._release_batch_claim(
            BATCH_TOKEN,
            BATCH_MANIFEST_SHA256,
            proposal_ids,
        ),
    )


def test_release_waits_for_exact_batch_approval_before_reading_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = "a" * 64
    states = iter(("REGISTERED", "APPROVED"))
    events: list[str] = []

    def batch_status(batch_token, manifest_hash, proposal_ids):
        events.append("batch")
        state = next(states)
        return state, state == "APPROVED"

    def request_json(method, path, body=None, request_proposal_id=None):
        events.append(f"{method}:{path}")
        return public_operation(proposal_id, "CONTENT_RELEASE", "APPLIED")

    monkeypatch.setattr(operator, "_release_batch_status", batch_status)
    monkeypatch.setattr(
        operator,
        "_release_batch_claim",
        lambda *args: events.append("claim"),
    )
    monkeypatch.setattr(operator, "request_json", request_json)
    monkeypatch.setattr(operator.time, "sleep", lambda seconds: events.append("sleep"))

    result = operator.release_wait_and_apply(release_input([proposal_id]))
    assert result["state"] == "APPLIED"
    assert events[:5] == [
        "batch",
        "sleep",
        "batch",
        "claim",
        f"GET:/operations/{proposal_id}",
    ]


def test_terminal_applied_batch_reconstructs_receipts_without_reclaim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = "a" * 64
    events: list[str] = []
    monkeypatch.setattr(
        operator,
        "_release_batch_status",
        lambda *args: ("APPLIED", False),
    )
    monkeypatch.setattr(
        operator,
        "_release_batch_claim",
        lambda *args: events.append("unexpected-claim"),
    )

    def request_json(method, path, *args, **kwargs):
        events.append(f"{method}:{path}")
        return public_operation(proposal_id, "CONTENT_RELEASE", "APPLIED")

    monkeypatch.setattr(operator, "request_json", request_json)
    result = operator.release_wait_and_apply(release_input([proposal_id]))

    assert result["state"] == "APPLIED"
    assert events == [f"GET:/operations/{proposal_id}"]


def test_atomic_batch_claim_retries_an_ambiguous_response_before_member_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = "a" * 64
    events: list[str] = []
    attempts = 0

    def claim(*args):
        nonlocal attempts
        attempts += 1
        events.append("claim")
        if attempts == 1:
            raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED")
        return {}

    def request_json(method, path, *args, **kwargs):
        events.append(f"{method}:{path}")
        return public_operation(proposal_id, "CONTENT_RELEASE", "APPLIED")

    monkeypatch.setattr(operator, "_release_batch_claim", claim)
    monkeypatch.setattr(operator, "request_json", request_json)
    monkeypatch.setattr(operator.time, "sleep", lambda seconds: events.append("sleep"))

    result = operator.release_wait_and_apply(release_input([proposal_id]))
    assert result["state"] == "APPLIED"
    assert events == [
        "claim",
        "sleep",
        "claim",
        f"GET:/operations/{proposal_id}",
    ]


def test_approved_batch_with_any_failed_precondition_never_mutates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        operator,
        "_release_batch_status",
        lambda *args: ("APPROVED", False),
    )
    monkeypatch.setattr(
        operator,
        "request_json",
        lambda method, path, *args, **kwargs: calls.append(f"{method}:{path}"),
    )
    assert_failure(
        "WORDPRESS_MCP_RELEASE_BATCH_PRECONDITION_FAILED",
        lambda: operator.release_wait_and_apply(release_input(["a" * 64])),
    )
    assert calls == []


@pytest.mark.parametrize(
    ("batch_state", "code"),
    [
        ("EXPIRED", "WORDPRESS_MCP_RELEASE_EXPIRED"),
        ("FAILED", "WORDPRESS_MCP_RELEASE_FAILED"),
    ],
)
def test_terminal_batch_state_never_reads_or_mutates_a_member(
    monkeypatch: pytest.MonkeyPatch,
    batch_state: str,
    code: str,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        operator,
        "_release_batch_status",
        lambda *args: (batch_state, False),
    )
    monkeypatch.setattr(
        operator,
        "request_json",
        lambda method, path, *args, **kwargs: calls.append(f"{method}:{path}"),
    )
    assert_failure(
        code,
        lambda: operator.release_wait_and_apply(release_input(["a" * 64])),
    )
    assert calls == []


def test_release_waiter_orders_theme_first_and_waits_for_human_approval(
    monkeypatch,
) -> None:
    content_id = "a" * 64
    theme_id = "b" * 64
    kinds = {content_id: "CONTENT_RELEASE", theme_id: "THEME_RELEASE"}
    states = {
        content_id: ["APPLYING", "APPLIED"],
        theme_id: ["APPLYING", "APPLIED"],
    }
    calls: list[tuple[str, str, str | None]] = []
    sleeps: list[float] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        calls.append((method, path, proposal_id))
        selected = path.split("/")[2]
        if method == "POST" and "/apply" in path:
            assert proposal_id == selected
            assert batch_identity == (BATCH_TOKEN, BATCH_MANIFEST_SHA256)
        if method == "GET":
            state = states[selected].pop(0)
            return public_operation(selected, kinds[selected], state)
        return {}

    monkeypatch.setattr(operator, "request_json", request_json)
    monkeypatch.setattr(operator.time, "sleep", sleeps.append)

    result = operator.release_wait_and_apply(release_input([content_id, theme_id]))

    assert result["schema"] == "ReleaseWaitApplyReceiptV1"
    assert result["batch_token"] == BATCH_TOKEN
    assert result["batch_manifest_sha256"] == BATCH_MANIFEST_SHA256
    assert result["proposal_ids"] == sorted([content_id, theme_id])
    assert result["proposal_count"] == 2
    assert result["state"] == "APPLIED"
    assert [receipt["proposal_id"] for receipt in result["receipts"]] == [
        theme_id,
        content_id,
    ]
    apply_paths = [path for method, path, _ in calls if method == "POST"]
    assert apply_paths == [
        f"/proposals/{theme_id}/apply",
        f"/proposals/{content_id}/apply",
    ]
    assert sleeps == []
    first_post = next(index for index, call in enumerate(calls) if call[0] == "POST")
    assert [call[1] for call in calls[:first_post]].count(
        f"/operations/{content_id}"
    ) == 1
    assert [call[1] for call in calls[:first_post]].count(
        f"/operations/{theme_id}"
    ) == 1


def test_release_waiter_recovers_applying_operation(monkeypatch) -> None:
    proposal_id = "c" * 64
    states = ["APPLYING", "APPLIED"]
    posts: list[str] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        if method == "GET":
            return public_operation(
                path.split("/")[2],
                "CONTENT_RELEASE",
                states.pop(0),
                result_code="OPERATION_APPLYING",
            )
        posts.append(path)
        return {}

    monkeypatch.setattr(operator, "request_json", request_json)
    monkeypatch.setattr(operator, "RELEASE_RECOVERY_GRACE_SECONDS", 0)
    result = operator.release_wait_and_apply(release_input([proposal_id]))
    assert result["state"] == "APPLIED"
    assert posts == [f"/operations/{proposal_id}/recover"]


@pytest.mark.parametrize(
    "retryable_code",
    ["RAOS_CODEX_OPERATION_IN_FLIGHT", "RAOS_CODEX_RECOVERY_GRACE_ACTIVE"],
)
def test_live_apply_is_polled_through_grace_and_retryable_recovery(
    monkeypatch, retryable_code
) -> None:
    proposal_id = "5" * 64
    states = ["APPLYING", "APPLYING", "APPLYING", "APPLIED"]
    clock = [0.0]
    recovery_times: list[float] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        if method == "GET":
            return public_operation(
                path.split("/")[2],
                "CONTENT_RELEASE",
                states.pop(0),
                result_code="OPERATION_APPLYING",
            )
        recovery_times.append(clock[0])
        raise operator.OperatorFailure(retryable_code)

    monkeypatch.setattr(operator, "request_json", request_json)
    monkeypatch.setattr(operator, "RELEASE_RECOVERY_GRACE_SECONDS", 4)
    monkeypatch.setattr(operator.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        operator.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )

    result = operator.release_wait_and_apply(release_input([proposal_id]))
    assert result["state"] == "APPLIED"
    assert recovery_times == [4.0]


def test_unclaimed_member_state_is_refused_without_member_mutation(monkeypatch) -> None:
    proposal_id = "d" * 64
    calls: list[tuple[str, str]] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        calls.append((method, path))
        return public_operation(path.split("/")[2], "CONTENT_RELEASE", "PENDING")

    monkeypatch.setattr(operator, "request_json", request_json)
    assert_failure(
        "WORDPRESS_MCP_RELEASE_BATCH_CLAIM_INVALID",
        lambda: operator.release_wait_and_apply(release_input([proposal_id])),
    )
    assert calls == [("GET", f"/operations/{proposal_id}")]


def test_readiness_barrier_fails_before_mutation_when_a_sibling_fails(
    monkeypatch,
) -> None:
    first = "1" * 64
    second = "2" * 64
    calls: list[str] = []
    monkeypatch.setattr(
        operator,
        "_release_batch_claim",
        lambda *args: (_ for _ in ()).throw(
            operator.OperatorFailure("WORDPRESS_MCP_RELEASE_FAILED")
        ),
    )
    monkeypatch.setattr(
        operator,
        "request_json",
        lambda method, *args, **kwargs: calls.append(method),
    )
    assert_failure(
        "WORDPRESS_MCP_RELEASE_FAILED",
        lambda: operator.release_wait_and_apply(release_input([first, second])),
    )
    assert calls == []


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("EXPIRED", "WORDPRESS_MCP_RELEASE_EXPIRED"),
        ("FAILED", "WORDPRESS_MCP_RELEASE_FAILED"),
        ("MANUAL_REQUIRED", "WORDPRESS_MCP_RELEASE_MANUAL_REQUIRED"),
    ],
)
def test_terminal_states_fail_closed_before_apply(monkeypatch, state, code) -> None:
    proposal_id = "e" * 64
    calls: list[str] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        calls.append(method)
        return public_operation(path.split("/")[2], "CONTENT_RELEASE", state)

    monkeypatch.setattr(operator, "request_json", request_json)
    assert_failure(
        code,
        lambda: operator.release_wait_and_apply(release_input([proposal_id])),
    )
    assert calls == ["GET"]


def test_plugin_and_multiple_theme_sets_are_refused_before_apply(monkeypatch) -> None:
    plugin_id = "f" * 64
    calls: list[str] = []

    def plugin_request(method, path, body=None, proposal_id=None):
        calls.append(method)
        return public_operation(path.split("/")[2], "PLUGIN_CHANGE", "APPLYING")

    monkeypatch.setattr(operator, "request_json", plugin_request)
    assert_failure(
        "WORDPRESS_MCP_RELEASE_PLUGIN_REFUSED",
        lambda: operator.release_wait_and_apply(release_input([plugin_id])),
    )
    assert calls == ["GET"]

    first = "7" * 64
    second = "8" * 64
    calls.clear()

    def theme_request(method, path, body=None, proposal_id=None):
        calls.append(method)
        return public_operation(path.split("/")[2], "THEME_RELEASE", "APPLYING")

    monkeypatch.setattr(operator, "request_json", theme_request)
    assert_failure(
        "WORDPRESS_MCP_RELEASE_THEME_LIMIT_EXCEEDED",
        lambda: operator.release_wait_and_apply(release_input([first, second])),
    )
    assert calls == ["GET", "GET"]


def test_malformed_public_operation_fails_with_a_redacted_code(monkeypatch) -> None:
    proposal_id = "6" * 64
    malformed = public_operation(proposal_id, "CONTENT_RELEASE", "PENDING")
    malformed["operation"]["state"] = []
    monkeypatch.setattr(operator, "request_json", lambda *args, **kwargs: malformed)
    assert_failure(
        "WORDPRESS_MCP_OPERATION_STATUS_INVALID",
        lambda: operator.release_wait_and_apply(release_input([proposal_id])),
    )


@pytest.mark.parametrize(
    "proposal_ids",
    [[], ["0" * 64, "0" * 64], ["0" * 64] * 21],
)
def test_release_set_must_contain_one_to_twenty_unique_ids(proposal_ids) -> None:
    assert_failure(
        "WORDPRESS_MCP_RELEASE_PROPOSALS_INVALID",
        lambda: operator.release_wait_and_apply(release_input(proposal_ids)),
    )


def test_theme_proposal_passes_optional_idempotency_key(monkeypatch) -> None:
    idempotency_key = "9" * 64
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        operator, "theme_package", lambda: (b"zip", {"old_version": None})
    )

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        if path == "/status":
            return {"theme": {"version": "1.2.3"}}
        captured.append(dict(body))
        return {"operation": {}}

    monkeypatch.setattr(operator, "request_json", request_json)
    operator.run("theme-propose-release", {"idempotency_key": idempotency_key})
    assert captured[0]["idempotency_key"] == idempotency_key
    assert captured[0]["code_package"]["old_version"] == "1.2.3"


def test_deployment_status_is_an_exact_read_only_operator_command(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def request_json(method, path, body=None, proposal_id=None, *batch_identity):
        calls.append((method, path))
        return {"schema": "RAOSWordPressDeploymentStatusV1"}

    monkeypatch.setattr(operator, "request_json", request_json)
    assert operator.run("deployment-status", {}) == {
        "schema": "RAOSWordPressDeploymentStatusV1"
    }
    assert calls == [("GET", "/status")]
    assert_failure(
        "WORDPRESS_MCP_INPUT_INVALID",
        lambda: operator.run("deployment-status", {"url": "https://example.test"}),
    )


@pytest.mark.parametrize("command", ["content-apply-release", "theme-apply-release"])
def test_individual_release_apply_commands_are_not_exposed(command: str) -> None:
    assert_failure(
        "WORDPRESS_MCP_COMMAND_REFUSED",
        lambda: operator.run(command, {}),
    )


def test_operator_php_route_returns_only_kind_and_public_operation() -> None:
    deployment = (
        ROOT
        / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-deployment.php"
    ).read_text()
    assert "'/operations/(?P<operation_id>[0-9a-f]{64})'" in deployment
    get_operation = deployment.split("public function get_operation", 1)[1].split(
        "public function", 1
    )[0]
    assert "'kind' => $row['kind']" in get_operation
    assert (
        "'operation' => RAOS_Codex_MCP_Store::public_operation($row)" in get_operation
    )
    for private_field in ("payload", "created_by", "approved_by", "approval_reason"):
        assert private_field not in get_operation


def test_apply_and_recovery_share_the_authoritative_nonblocking_lock() -> None:
    deployment = (
        ROOT
        / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-deployment.php"
    ).read_text()
    apply = deployment.split("public function apply_proposal", 1)[1].split(
        "public function recover_operation", 1
    )[0]
    recover = deployment.split("public function recover_operation", 1)[1].split(
        "private function apply_content", 1
    )[0]
    assert apply.index("acquire_operation_lock") < apply.index("claim_apply")
    assert recover.index("acquire_operation_lock") < recover.index(
        "recovery_grace_elapsed"
    )
    assert "release_operation_lock" in apply
    assert "release_operation_lock" in recover
    assert "LOCK_EX | LOCK_NB" in deployment
    assert "raos_codex_operation_in_flight" in deployment


def test_bridge_advertises_bounds_and_rejects_duplicate_ids() -> None:
    messages = "\n".join(
        (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "1.0.0"},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            ),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "release-wait-and-apply",
                        "arguments": {
                            "batch_token": BATCH_TOKEN,
                            "batch_manifest_sha256": BATCH_MANIFEST_SHA256,
                            "proposal_ids": ["0" * 64, "0" * 64],
                        },
                    },
                }
            ),
            "",
        )
    )
    completed = subprocess.run(
        [
            "/home/minami/.nvm/versions/node/v24.18.1/bin/node",
            "--experimental-strip-types",
            "packages/wordpress-mcp-bridge/src/index.ts",
        ],
        cwd=ROOT,
        input=messages,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=20,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    listed = next(response for response in responses if response.get("id") == 2)
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert tools["deployment-status"]["inputSchema"]["properties"] == {}
    assert tools["deployment-status"]["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert tools["release-wait-and-apply"]["annotations"]["destructiveHint"] is True
    wait_schema = tools["release-wait-and-apply"]["inputSchema"]
    assert wait_schema["required"] == [
        "batch_token",
        "batch_manifest_sha256",
        "proposal_ids",
    ]
    assert wait_schema["properties"]["batch_token"] == {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$",
    }
    assert wait_schema["properties"]["batch_manifest_sha256"] == {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$",
    }
    schema = wait_schema["properties"]["proposal_ids"]
    assert schema["minItems"] == 1
    assert schema["maxItems"] == 20
    theme_schema = tools["theme-propose-release"]["inputSchema"]
    assert theme_schema["properties"]["idempotency_key"] == {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$",
    }
    assert "idempotency_key" not in theme_schema.get("required", [])
    refused = next(response for response in responses if response.get("id") == 3)
    assert refused["result"]["isError"] is True
    assert "unique" in json.dumps(refused["result"]).lower()


def test_bridge_rejects_unknown_fields_before_invoking_operator(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    bridge = tmp_path / "packages/wordpress-mcp-bridge/src/index.ts"
    bridge.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "packages/wordpress-mcp-bridge/src/index.ts", bridge)
    (tmp_path / "node_modules").symlink_to(
        ROOT / "node_modules", target_is_directory=True
    )
    fake_python = tmp_path / ".venv/bin/python"
    fake_python.parent.mkdir(parents=True)
    marker = fake_python.parent / "operator-invoked"
    fake_python.write_text(
        "#!/bin/sh\n"
        'marker="${0%/*}/operator-invoked"\n'
        ': > "$marker"\n'
        "printf '%s\\n' '{}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    messages = "\n".join(
        (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "1.0.0"},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "deployment-status",
                        "arguments": {"unexpected_field": True},
                    },
                }
            ),
            "",
        )
    )
    completed = subprocess.run(
        [node, "--experimental-strip-types", bridge.as_posix()],
        cwd=tmp_path,
        input=messages,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=20,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    refused = next(response for response in responses if response.get("id") == 2)
    assert refused["result"]["isError"] is True
    serialized = json.dumps(refused["result"])
    assert "unexpected_field" in serialized
    assert "Unrecognized key" in serialized
    assert not marker.exists()
