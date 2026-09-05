from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from scripts import raos_wordpress_deployment_operator as operator


ROOT = Path(__file__).resolve().parents[2]
OPERATION_ID = "a" * 64
KINDS = ("CONTENT_RELEASE", "THEME_RELEASE", "PLUGIN_CHANGE")
STATES = (
    "PENDING",
    "MANUAL_REQUIRED",
    "APPROVED",
    "APPLYING",
    "APPLIED",
    "EXPIRED",
    "FAILED",
)


def receipt(kind: str = "CONTENT_RELEASE", state: str = "PENDING") -> dict:
    return {
        "kind": kind,
        "operation": {
            "schema": "OperationReceiptV1",
            "proposal_id": OPERATION_ID,
            "operation_id": OPERATION_ID,
            "state": state,
            "result_code": "SYNTHETIC_OPERATION_STATUS",
            "before_sha256": "b" * 64,
            "after_sha256": None,
            "audit_id": "c" * 64,
        },
    }


def test_public_contract_preserves_existing_expiry_without_apply_or_recovery() -> None:
    contract = json.loads(
        (ROOT / "changes/wordpress-mcp-v1/contracts/wordpress-mcp.v1.json").read_text()
    )
    assert contract["operation_status"] == {
        "command": "operation-status",
        "input_fields": ["operation_id"],
        "operation_id_pattern": "^[0-9a-f]{64}$",
        "method": "GET",
        "path_template": "/operations/{operation_id}",
        "response_fields": ["kind", "operation"],
        "kinds": list(KINDS),
        "receipt_schema": "OperationReceiptV1",
        "receipt_ids_match_request": True,
        "existing_server_expiry_reconciliation": True,
        "expired_approval_lease_cleanup": True,
        "lists_operations": False,
        "accepts_arbitrary_url": False,
        "starts_publication": False,
        "waits_for_approval": False,
        "applies": False,
        "recovers": False,
        "finalizes": False,
    }
    readme = (ROOT / "changes/wordpress-mcp-v1/README.md").read_text()
    assert "expiry reconciliation is preserved" in readme
    assert "status does not promise zero server" in readme


@pytest.fixture(autouse=True)
def refuse_live_or_mutating_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        pytest.fail("status must not access credentials, wait, claim, or finalize")

    for name in (
        "credentials",
        "release_wait_and_apply",
        "_release_batch_claim",
        "_finalize_applied_operation",
        "_finalize_failed_operation",
    ):
        # The transport itself is replaced per test before an operator call.
        monkeypatch.setattr(operator, name, forbidden)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("state", STATES)
def test_operation_status_reads_exactly_one_public_receipt_in_every_state(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    state: str,
) -> None:
    expected = receipt(kind, state)
    original = deepcopy(expected)
    calls = []

    def request(method, path, body=None, proposal_id=None, **kwargs):
        calls.append((method, path, body, proposal_id, kwargs))
        return expected

    monkeypatch.setattr(operator, "request_json", request)
    assert operator.run("operation-status", {"operation_id": OPERATION_ID}) == original
    assert expected == original
    assert calls == [
        ("GET", f"/operations/{OPERATION_ID}", None, None, {"deadline": None})
    ]
    assert (
        operator.parser().parse_args(["operation-status"]).command == "operation-status"
    )


INVALID_INPUTS = (
    {},
    {"operation_ids": [OPERATION_ID]},
    {"operation_id": OPERATION_ID, "url": "https://example.test"},
    {"operation_id": OPERATION_ID, "recover": True},
    {"operation_id": OPERATION_ID, "proposal_id": OPERATION_ID},
    *(
        {"operation_id": value}
        for value in (
            "",
            "a" * 63,
            "a" * 65,
            "A" * 64,
            "g" * 64,
            "../operations",
            "https://example.test/operations/" + OPERATION_ID,
            OPERATION_ID + "/recover",
            OPERATION_ID + "?list=1",
            OPERATION_ID + "\n",
            [OPERATION_ID],
            1,
            True,
            None,
        )
    ),
)


@pytest.mark.parametrize("inputs", INVALID_INPUTS)
def test_operation_status_rejects_unbounded_input_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    inputs: dict,
) -> None:
    calls = []
    monkeypatch.setattr(
        operator, "request_json", lambda *args, **kwargs: calls.append(args)
    )
    with pytest.raises(operator.OperatorFailure, match="^WORDPRESS_MCP_INPUT_INVALID$"):
        operator.run("operation-status", inputs)
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("kind", "UNKNOWN"),
        ("kind", "content_release"),
        ("kind", None),
        ("operation.schema", "OperationReceiptV2"),
        ("operation.proposal_id", "d" * 64),
        ("operation.operation_id", "d" * 64),
        ("operation.state", "COMPLETE"),
        ("operation.state", None),
        ("operation.result_code", "secret\nbody"),
        ("operation.before_sha256", "invalid"),
        ("operation.after_sha256", "invalid"),
        ("operation.audit_id", None),
    ),
)
def test_operation_status_rejects_invalid_receipt_without_followup(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    response = receipt()
    target = response
    if field.startswith("operation."):
        target = response["operation"]
    target[field.split(".")[-1]] = value
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr(operator, "request_json", request)
    with pytest.raises(
        operator.OperatorFailure, match="^WORDPRESS_MCP_OPERATION_STATUS_INVALID$"
    ):
        operator.run("operation-status", {"operation_id": OPERATION_ID})
    assert len(calls) == 1
    assert calls[0][0] == ("GET", f"/operations/{OPERATION_ID}")


@pytest.mark.parametrize("location", ("envelope", "operation"))
@pytest.mark.parametrize(
    "field", ("payload", "approved_by", "approval_reason", "created_by")
)
def test_operation_status_does_not_forward_private_or_unknown_fields(
    monkeypatch: pytest.MonkeyPatch,
    location: str,
    field: str,
) -> None:
    response = receipt()
    target = response if location == "envelope" else response["operation"]
    target[field] = "synthetic private field"
    monkeypatch.setattr(operator, "request_json", lambda *args, **kwargs: response)
    with pytest.raises(operator.OperatorFailure, match="^WORDPRESS_MCP_INPUT_INVALID$"):
        operator.run("operation-status", {"operation_id": OPERATION_ID})


@pytest.mark.parametrize(
    "code", ("RAOS_CODEX_OPERATION_NOT_FOUND", "WORDPRESS_MCP_TRANSPORT_FAILED")
)
def test_operation_status_transport_failure_never_retries_or_recovers(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        raise operator.OperatorFailure(code)

    monkeypatch.setattr(operator, "request_json", request)
    with pytest.raises(operator.OperatorFailure, match=f"^{code}$"):
        operator.run("operation-status", {"operation_id": OPERATION_ID})
    assert len(calls) == 1


def bridge_calls(tmp_path: Path, inputs: list[dict]) -> tuple[list[dict], Path]:
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
    marker = fake_python.parent / "operator-invoked.json"
    fake_python.write_text(
        "#!/usr/bin/python3\n"
        "import json, pathlib, sys\n"
        "record = {'argv': sys.argv[1:], 'inputs': json.load(sys.stdin)}\n"
        "pathlib.Path(__file__).with_name('operator-invoked.json').write_text(json.dumps(record))\n"
        f"print({json.dumps(receipt())!r})\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    messages.extend(
        {
            "jsonrpc": "2.0",
            "id": index + 2,
            "method": "tools/call",
            "params": {"name": "operation-status", "arguments": arguments},
        }
        for index, arguments in enumerate(inputs)
    )
    completed = subprocess.run(
        [node, "--experimental-strip-types", bridge.as_posix()],
        cwd=tmp_path,
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=20,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    return [response for response in responses if response.get("id", 0) >= 2], marker


def test_bridge_operation_status_routes_only_the_exact_command_and_single_id(
    tmp_path: Path,
) -> None:
    responses, marker = bridge_calls(tmp_path, [{"operation_id": OPERATION_ID}])
    assert responses[0]["result"]["structuredContent"] == receipt()
    captured = json.loads(marker.read_text())
    assert set(captured) == {"argv", "inputs"}
    assert len(captured["argv"]) == 3
    assert captured["argv"][0] == "-B"
    assert (
        Path(captured["argv"][1])
        == tmp_path / "scripts/raos_wordpress_deployment_operator.py"
    )
    assert captured["argv"][2] == "operation-status"
    assert captured["inputs"] == {"operation_id": OPERATION_ID}


def test_bridge_rejects_all_unbounded_operation_status_inputs_before_operator(
    tmp_path: Path,
) -> None:
    responses, marker = bridge_calls(tmp_path, list(INVALID_INPUTS))
    assert len(responses) == len(INVALID_INPUTS)
    assert all(response["result"]["isError"] is True for response in responses)
    assert not marker.exists()
