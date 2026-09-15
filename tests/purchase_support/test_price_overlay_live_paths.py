"""Contract §8: every path from this repository to the live site refuses while values may be live.

Offline only. The run state is synthetic (a recorded publish in a temporary owner checkout),
every network primitive is replaced by a recorder, and the MCP proxy, the operator and the
browser probes are fakes: nothing here starts the real proxy or opens a socket.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tomllib
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from raos.adapters import price_overlay_live_guard as guard
from raos.adapters.rakuten_price_refresh_client import live_run_ids
from raos.domain.editorial.rakuten_price_refresh import RefreshError
from scripts import codex_harness as harness
from scripts import raos_rakuten_price_refresh as refresh_cli
from scripts import raos_wordpress_deployment_operator as operator
from scripts import raos_wordpress_direct_preview as preview_cli
from scripts import raos_wordpress_direct_publish as direct
from scripts import raos_wordpress_publication_request as publication
from scripts import raos_wordpress_seo_audit as seo

ROOT = Path(__file__).resolve().parents[2]
LIVE = "PRICE_OVERLAY_LIVE"
STATE_INVALID = "PRICE_OVERLAY_STATE_INVALID"
NODE = shutil.which("node")


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The KS-020 publisher suite owns the synthetic run fixtures; only its helpers are reused
# (loaded by path so its tests are not collected twice).
ks020 = _load(
    "ks020_price_overlay_publish_helpers",
    "tests/purchase_support/test_rakuten_price_overlay_publish.py",
)
packet = _load(
    "raos_full_redesign_audit_packet", "scripts/prepare_full_redesign_audit_packet.py"
)
successor = _load(
    "raos_v2_successor_validator", "scripts/validate_raos_v2_successor.py"
)
RUN_ID = ks020.RUN_ID


@pytest.fixture(autouse=True)
def keep_process_umask():
    """The legacy CLIs set the process umask; leave it as this session found it."""
    previous = os.umask(0o077)
    os.umask(previous)
    yield
    os.umask(previous)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*_args, **_keywords):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def owner_with_state(tmp_path, state):
    """A temporary owner checkout whose run state is live, unreadable or empty."""
    owner = ks020.plain_owner_checkout(tmp_path)
    if state == "live":
        ks020.record_live_publish(owner)
    elif state == "unreadable":
        (owner / ".secrets/rakuten-price-refresh").write_text("")
    return owner


@pytest.fixture(params=["live", "unreadable"])
def refused(request, tmp_path, monkeypatch):
    """Point every fixed checkout the guard looks at to a refusing owner checkout."""
    owner = owner_with_state(tmp_path, request.param)
    empty = (tmp_path / "worktree").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", empty)
    return LIVE if request.param == "live" else STATE_INVALID


@pytest.fixture
def not_live(tmp_path, monkeypatch):
    owner = owner_with_state(tmp_path, "empty")
    empty = (tmp_path / "worktree").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", empty)
    return owner


# ---------------------------------------------------------------------------
# One fixed owner checkout, one live check
# ---------------------------------------------------------------------------


def test_every_component_uses_the_same_fixed_owner_checkout():
    fixed = Path("/home/minami/rakuten")
    assert guard.OWNER_CHECKOUT == fixed
    assert operator.OWNER_CHECKOUT == fixed
    assert refresh_cli.OWNER_CHECKOUT == fixed
    assert guard.REPOSITORY_ROOT == ROOT
    assert (guard.LIVE, guard.STATE_INVALID) == (LIVE, STATE_INVALID)


@pytest.mark.parametrize("state", ["live", "unreadable", "empty"])
def test_the_guard_answers_for_every_run_state(tmp_path, monkeypatch, state):
    owner = owner_with_state(tmp_path, state)
    empty = (tmp_path / "worktree").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", empty)
    expected = {"live": LIVE, "unreadable": STATE_INVALID, "empty": None}[state]
    assert guard.price_overlay_refusal() == expected
    if expected is None:
        guard.refuse_while_price_overlay_live()
        return
    with pytest.raises(guard.PriceOverlayLive) as error:
        guard.refuse_while_price_overlay_live()
    assert error.value.code == expected


@pytest.mark.parametrize("unsafe", ["symlink", "file"])
def test_an_unsafe_run_entry_refuses_instead_of_counting_as_not_live(
    tmp_path, monkeypatch, unsafe
):
    """A run entry that is a symlink or a file cannot be read, so it must not pass as
    'nothing is live' (contract §8, §10.1-10)."""
    owner = owner_with_state(tmp_path, "live")
    second = tmp_path / "second"
    second.mkdir()
    other = ks020.plain_owner_checkout(second)
    runs = other / ".secrets/rakuten-price-refresh"
    runs.mkdir(mode=0o700)
    if unsafe == "symlink":
        (runs / RUN_ID).symlink_to(owner / ".secrets/rakuten-price-refresh" / RUN_ID)
    else:
        (runs / RUN_ID).write_text("")
    with pytest.raises(RefreshError, match="PRIVATE_PATH_UNSAFE"):
        live_run_ids([other])

    monkeypatch.setattr(guard, "OWNER_CHECKOUT", other)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", other)
    assert guard.price_overlay_refusal() == STATE_INVALID

    monkeypatch.setattr(operator, "OWNER_CHECKOUT", other)
    monkeypatch.setattr(operator, "ROOT", other)
    with pytest.raises(
        operator.OperatorFailure, match="WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID"
    ):
        operator.refuse_while_price_overlay_live(None)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_PRIVATE_PATH_UNSAFE"):
        direct.refuse_while_price_overlay_live(other)


# ---------------------------------------------------------------------------
# Every Python path to the live site
# ---------------------------------------------------------------------------


class Reached(Exception):
    """The call reached the transport the guard is in front of."""


def recorder(calls, label):
    def call(*_args, **_keywords):
        calls.append(label)
        raise Reached(label)

    return call


class Opener:
    def __init__(self, calls, label):
        self._calls = calls
        self._label = label

    def open(self, *_args, **_keywords):
        self._calls.append(self._label)
        raise Reached(self._label)


def editor_mcp_request(monkeypatch, calls, tmp_path):
    client = publication.EditorMcpClient.__new__(publication.EditorMcpClient)
    client.endpoint = publication.EDITOR_ENDPOINT
    client.owner_checkout = None
    client.username = "synthetic-editor"
    client._basic_auth_value = "synthetic-application-password"
    client.session_id = None
    client.next_id = 1
    monkeypatch.setattr(
        publication.urllib.request, "build_opener", recorder(calls, "editor")
    )
    client.message("tools/list", {})


def editor_mcp_client_construction(monkeypatch, calls, tmp_path):
    monkeypatch.setattr(
        publication, "_secure_credential", recorder(calls, "credential")
    )
    publication.EditorMcpClient(owner_checkout=None)


def public_page_readback(monkeypatch, calls, tmp_path):
    article = SimpleNamespace(production_slug="synthetic-comparison")
    publication._public_page_evidence(article, Opener(calls, "public-page"))


def public_stylesheet_readback(monkeypatch, calls, tmp_path):
    publication._fetch_public_stylesheet_sentinels(
        "/wp-content/themes/synthetic/style.css",
        Opener(calls, "public-stylesheet"),
        {},
        authorization=None,
    )


def deployment_bridge_call(monkeypatch, calls, tmp_path):
    publication._deployment_mcp_call(
        "deployment-status", {}, timeout=30, runner=recorder(calls, "bridge")
    )


def seo_audit_transport(monkeypatch, calls, tmp_path):
    transport = seo.BoundedHttpsTransport.__new__(seo.BoundedHttpsTransport)
    transport._contract = SimpleNamespace(
        connect_timeout=5, read_timeout=5, maximum_bytes=4096, origin=publication.ORIGIN
    )
    transport._origin_parts = urlsplit(publication.ORIGIN)
    transport._ssl_context = ssl.create_default_context()
    transport._allowed_resource_urls = frozenset()
    monkeypatch.setattr(seo.http.client, "HTTPSConnection", recorder(calls, "seo"))
    transport.get(publication.ORIGIN + "/")


def full_redesign_capture(monkeypatch, calls, tmp_path):
    monkeypatch.setattr(
        packet.http.client, "HTTPSConnection", recorder(calls, "packet")
    )
    packet._capture_public({"public_urls": [{"url": publication.ORIGIN + "/"}]})


def raos_v2_public_capture(monkeypatch, calls, tmp_path):
    monkeypatch.setattr(successor, "build_opener", recorder(calls, "successor"))
    successor._fetch(publication.ORIGIN + "/")


def harness_wordpress_status(monkeypatch, calls, tmp_path):
    monkeypatch.setattr(harness.subprocess, "Popen", recorder(calls, "harness"))
    monkeypatch.setattr(
        harness, "controller_command", lambda *a, **k: ["/usr/bin/false"]
    )
    settings = {
        "command": "/usr/bin/false",
        "args": [],
        "cwd": str(tmp_path),
        "enabled": True,
    }
    rows = harness.wordpress_status(
        tmp_path,
        {
            "wordpressEditor": {
                **settings,
                "enabled_tools": ["raos-codex-site-status"],
            },
            "wordpressDeployment": {**settings, "enabled_tools": ["deployment-status"]},
        },
    )
    return json.dumps(rows)


def direct_preview_cli(monkeypatch, calls, tmp_path):
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({"candidate_id": "a" * 64}))
    monkeypatch.setattr(
        preview_cli, "prepare_candidate_preview", recorder(calls, "preview")
    )
    monkeypatch.setattr(
        sys, "argv", ["raos_wordpress_direct_preview.py", "--candidate", str(candidate)]
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = preview_cli.main()
    return f"exit={code} {buffer.getvalue()}"


PYTHON_PATHS = {
    "editor-mcp-client-construction": editor_mcp_client_construction,
    "editor-mcp-request": editor_mcp_request,
    "public-page-readback": public_page_readback,
    "public-stylesheet-readback": public_stylesheet_readback,
    "deployment-bridge-call": deployment_bridge_call,
    "seo-audit-transport": seo_audit_transport,
    "full-redesign-public-capture": full_redesign_capture,
    "raos-v2-public-capture": raos_v2_public_capture,
    "harness-wordpress-status": harness_wordpress_status,
    "direct-preview-cli": direct_preview_cli,
}


def outcome(name, monkeypatch, calls, tmp_path):
    try:
        return str(PYTHON_PATHS[name](monkeypatch, calls, tmp_path) or "RETURNED")
    except Reached as error:
        return f"REACHED:{error}"
    except BaseException as error:  # noqa: BLE001 - the refusal code is what is asserted
        return f"{type(error).__name__}:{error}"


@pytest.mark.parametrize("name", sorted(PYTHON_PATHS))
def test_every_python_path_to_the_live_site_is_refused(
    name, refused, monkeypatch, tmp_path
):
    calls = []
    text = outcome(name, monkeypatch, calls, tmp_path)
    assert refused in text, text
    assert calls == [], text


@pytest.mark.parametrize("name", sorted(PYTHON_PATHS))
def test_every_python_path_reaches_its_transport_when_nothing_is_live(
    name, not_live, monkeypatch, tmp_path
):
    calls = []
    text = outcome(name, monkeypatch, calls, tmp_path)
    assert "PRICE_OVERLAY" not in text, text
    assert len(calls) == 1, text


# ---------------------------------------------------------------------------
# The editor MCP server: startup, every message, every answer
# ---------------------------------------------------------------------------

FAKE_OPERATOR = '''#!/usr/bin/python3
"""Stands in for the deployment operator's local live check; answers from answers.json."""
import json, pathlib, sys

here = pathlib.Path(__file__).parent
if sys.argv[-1] != "price-overlay-live-check":
    sys.stderr.write("UNEXPECTED_OPERATOR_COMMAND\\n")
    raise SystemExit(2)
sys.stdin.read()
log = here / "checks.log"
index = len(log.read_text().splitlines()) if log.exists() else 0
with log.open("a") as handle:
    handle.write("check\\n")
answers = json.loads((here / "answers.json").read_text())
code, out, err = answers[min(index, len(answers) - 1)]
sys.stdout.write(out)
sys.stderr.write(err)
raise SystemExit(code)
'''

FAKE_PROXY = """const fs = require("node:fs");
const path = require("node:path");
const log = path.join(__dirname, "received.jsonl");
let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf("\\n")) >= 0) {
    const line = buffer.slice(0, index);
    buffer = buffer.slice(index + 1);
    if (!line.trim()) continue;
    fs.appendFileSync(log, line + "\\n");
    const message = JSON.parse(line);
    if (message.id !== undefined) {
      process.stdout.write(
        JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { synthetic: true } }) + "\\n",
      );
    }
  }
});
process.stdin.on("end", () => process.exit(0));
"""

NOT_LIVE = [0, '{"price_overlay_live":false}\n', ""]
ANSWER_LIVE = [69, "", "WORDPRESS_MCP_PRICE_OVERLAY_LIVE\n"]
ANSWER_STATE_INVALID = [69, "", "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID\n"]
UNUSABLE_ANSWERS = {
    "true": [0, '{"price_overlay_live":true}\n', ""],
    "empty": [0, "{}\n", ""],
    "extra-key": [0, '{"price_overlay_live":false,"run_ids":[]}\n', ""],
    "not-json": [0, "not json\n", ""],
    "silent-failure": [1, "", ""],
    # The answer is negative but the check itself failed: the exit code decides.
    "negative-answer-after-failure": [
        69,
        '{"price_overlay_live":false}\n',
        "WORDPRESS_MCP_PRICE_OVERLAY_LIVE\n",
    ],
}
EDITOR_ENDPOINT_TOOLS = tuple(
    tomllib.loads((ROOT / ".codex/config.toml").read_bytes().decode("utf-8"))[
        "mcp_servers"
    ]["wordpressEditor"]["enabled_tools"]
)


def fake_check_root(tmp_path, answers, name="check-root"):
    """A checkout whose .venv/bin/python is the fake operator with the given answer script."""
    root = (tmp_path / name).resolve()
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/raos_wordpress_deployment_operator.py").write_text("")
    shutil.copy2(ROOT / "scripts/raos_price_overlay_live_check.mjs", root / "scripts")
    binary = root / ".venv/bin"
    binary.mkdir(parents=True)
    (binary / "python").write_text(FAKE_OPERATOR)
    (binary / "python").chmod(0o700)
    (binary / "answers.json").write_text(json.dumps(answers))
    return root


def checks_run(root):
    log = root / ".venv/bin/checks.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


def launcher_root(tmp_path, answers):
    root = fake_check_root(tmp_path, answers, name="editor-root")
    launcher = (ROOT / "scripts/raos_wordpress_editor_mcp_launcher.mjs").read_text()
    for old, new in (
        ("const root = '/home/minami/rakuten';", f"const root = '{root}';"),
        (
            "const node = '/home/minami/.nvm/versions/node/v24.18.1/bin/node';",
            f"const node = '{NODE}';",
        ),
    ):
        assert launcher.count(old) == 1, old
        launcher = launcher.replace(old, new, 1)
    (root / "scripts/raos_wordpress_editor_mcp_launcher.mjs").write_text(launcher)
    package = root / "node_modules/@automattic/mcp-wordpress-remote"
    (package / "dist").mkdir(parents=True)
    (package / "dist/proxy.js").write_text(FAKE_PROXY)
    (package / "package.json").write_text(json.dumps({"version": "0.4.0"}))
    secret = root / ".secrets/wordpress-mcp"
    secret.mkdir(parents=True)
    credential = secret / "editor-application-password.v1.json"
    credential.write_text(
        json.dumps(
            {
                "schema": "RAOS_WORDPRESS_APPLICATION_PASSWORD_V1",
                "origin": "https://kurashinoshirube.com",
                "purpose": "editor_mcp",
                "username": "synthetic-editor",
                "application_password": "synthetic-application-password",
            }
        )
    )
    credential.chmod(0o600)
    secret.chmod(0o700)
    (root / ".secrets").chmod(0o700)
    return root


def run_launcher(root, messages):
    assert NODE is not None
    completed = subprocess.run(
        [NODE, "scripts/raos_wordpress_editor_mcp_launcher.mjs"],
        cwd=root,
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        text=True,
        capture_output=True,
        timeout=300,
    )
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    received_path = (
        root / "node_modules/@automattic/mcp-wordpress-remote/dist/received.jsonl"
    )
    received = (
        [
            json.loads(line)
            for line in received_path.read_text().splitlines()
            if line.strip()
        ]
        if received_path.exists()
        else []
    )
    return completed, responses, received


def tool_calls():
    return [
        {
            "jsonrpc": "2.0",
            "id": index + 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": {}},
        }
        for index, name in enumerate(EDITOR_ENDPOINT_TOOLS)
    ]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (ANSWER_LIVE, "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"),
        (ANSWER_STATE_INVALID, "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID"),
        *(
            (
                answer,
                "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"
                if name == "negative-answer-after-failure"
                else "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID",
            )
            for name, answer in UNUSABLE_ANSWERS.items()
        ),
    ],
    ids=["live", "state-invalid", *UNUSABLE_ANSWERS],
)
def test_the_editor_mcp_launcher_refuses_before_starting_the_proxy(
    tmp_path, answer, expected
):
    """Nothing but the exact negative answer starts the proxy: no credential is read and no
    request reaches the endpoint (contract §8)."""
    root = launcher_root(tmp_path, [answer])
    completed, responses, received = run_launcher(root, tool_calls())
    assert (completed.returncode, completed.stdout) == (69, "")
    assert completed.stderr == expected + "\n"
    assert (responses, received) == ([], [])
    assert not (root / ".secrets/wordpress-mcp/proxy-state").exists()
    assert checks_run(root) == 1


def test_the_editor_mcp_launcher_forwards_every_tool_when_nothing_is_live(tmp_path):
    root = launcher_root(tmp_path, [NOT_LIVE])
    messages = [
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
        *tool_calls(),
    ]
    completed, responses, received = run_launcher(root, messages)
    assert completed.returncode == 0, completed.stderr
    assert [message["id"] for message in received] == list(range(len(messages)))
    assert [response["result"] for response in responses] == [
        {"synthetic": True}
    ] * len(messages)
    # startup, then one check for each message and one for each answer.
    assert checks_run(root) == 1 + 2 * len(messages)


def test_the_editor_mcp_launcher_refuses_every_message_once_a_run_goes_live(tmp_path):
    """The proxy is long lived: a run that goes live after startup stops the next message."""
    root = launcher_root(tmp_path, [NOT_LIVE, ANSWER_LIVE])
    completed, responses, received = run_launcher(root, tool_calls())
    assert completed.returncode == 0, completed.stderr
    assert received == []
    assert [response["error"]["message"] for response in responses] == [
        "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"
    ] * len(EDITOR_ENDPOINT_TOOLS)
    assert [response["id"] for response in responses] == [
        index + 1 for index, _name in enumerate(EDITOR_ENDPOINT_TOOLS)
    ]


def test_the_editor_mcp_launcher_holds_back_an_answer_that_arrives_after_a_run_goes_live(
    tmp_path,
):
    """Startup and the request pass, the run goes live while the request is in flight: the
    proxy's answer (live injected body) is replaced by the refusal."""
    root = launcher_root(tmp_path, [NOT_LIVE, NOT_LIVE, ANSWER_LIVE])
    message = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "raos-codex-content-get", "arguments": {"id": 101}},
    }
    completed, responses, received = run_launcher(root, [message])
    assert completed.returncode == 0, completed.stderr
    assert [row["id"] for row in received] == [7]
    assert responses == [
        {
            "jsonrpc": "2.0",
            "id": 7,
            "error": {"code": -32001, "message": "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"},
        }
    ]


def real_operator_root(tmp_path, owner):
    """A checkout whose .venv/bin/python runs the real operator against a temporary owner."""
    root = launcher_root(tmp_path, [NOT_LIVE])
    shutil.copy2(
        ROOT / "scripts/raos_wordpress_deployment_operator.py",
        root / "scripts/raos_wordpress_deployment_operator.py",
    )
    (root / "python").symlink_to(ROOT / "python", target_is_directory=True)
    (root / ".venv/bin/python").write_text(
        f"""#!{sys.executable}
import importlib.util, pathlib, sys
sys.dont_write_bytecode = True
flag, operator_path, *arguments = sys.argv[1:]
assert flag == "-B"
sys.path.insert(0, str(pathlib.Path(operator_path).parent))
spec = importlib.util.spec_from_file_location(
    "raos_wordpress_deployment_operator", operator_path
)
operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = operator
spec.loader.exec_module(operator)
operator.OWNER_CHECKOUT = pathlib.Path({str(owner)!r})
raise SystemExit(operator.main(arguments))
"""
    )
    (root / ".venv/bin/python").chmod(0o700)
    return root


def test_the_editor_mcp_launcher_with_the_real_operator_refuses_while_live(tmp_path):
    owner = owner_with_state(tmp_path, "live")
    root = real_operator_root(tmp_path, owner)
    completed, responses, received = run_launcher(root, tool_calls())
    assert (completed.returncode, completed.stdout) == (69, "")
    assert completed.stderr == "WORDPRESS_MCP_PRICE_OVERLAY_LIVE\n"
    assert received == []

    # Control: with the run store gone the same harness reaches the proxy.
    shutil.rmtree(owner / ".secrets/rakuten-price-refresh")
    completed, responses, received = run_launcher(root, tool_calls())
    assert completed.returncode == 0, completed.stderr
    assert [row["params"]["name"] for row in received] == list(EDITOR_ENDPOINT_TOOLS)


def test_every_enabled_codex_mcp_server_refuses_while_values_may_be_live():
    """A new enabled server, or a new editor tool, fails this test until it is covered."""
    config = tomllib.loads((ROOT / ".codex/config.toml").read_bytes().decode("utf-8"))
    enabled = {
        name
        for name, server in config["mcp_servers"].items()
        if server.get("enabled") is True
    }
    assert enabled == {"wordpressEditor", "wordpressDeployment"}
    launcher = (ROOT / "scripts/raos_wordpress_editor_mcp_launcher.mjs").read_text()
    assert "priceOverlayRefusal" in launcher
    bridge = (ROOT / "packages/wordpress-mcp-bridge/src/index.ts").read_text()
    assert "price-overlay-live-check" in bridge
    assert config["mcp_servers"]["wordpressEditor"]["args"] == [
        "/home/minami/rakuten/scripts/raos_wordpress_editor_mcp_launcher.mjs"
    ]
    assert set(EDITOR_ENDPOINT_TOOLS) == set(
        config["mcp_servers"]["wordpressEditor"]["enabled_tools"]
    )


# ---------------------------------------------------------------------------
# The legacy self-hosted CLIs (ST-1506 / ST-1704 v2 / ST-1703 / ST-1704 pilot)
# ---------------------------------------------------------------------------

st1506_cli = _load("ks020_st1506_operator_cli", "scripts/st1506_wordpress_operator.py")
publication_v2_cli = _load(
    "ks020_st1704_publication_operator_v2_cli",
    "scripts/st1704_wordpress_publication_operator_v2.py",
)
self_hosted_cli = _load(
    "ks020_self_hosted_wordpress_cli", "scripts/self_hosted_wordpress.py"
)
pilot_cli = _load(
    "ks020_st1704_editorial_pilot_cli", "scripts/st1704_self_hosted_editorial_pilot.py"
)


def invoke_st1506(module, monkeypatch):
    monkeypatch.setattr(
        module, "OfficialSelfHostedWordPressOperatorAdapter", recorder([], "adapter")
    )
    return module._run(argparse.Namespace(command="status"))


def invoke_publication_v2(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "OfficialSelfHostedWordPressPublicationOperatorV2Adapter",
        recorder([], "adapter"),
    )
    return module._run(argparse.Namespace(command="status"))


def invoke_self_hosted(module, monkeypatch):
    return module.main(["doctor"])


def invoke_pilot(module, monkeypatch):
    monkeypatch.setattr(module, "_rebind_root", recorder([], "pilot"))
    return module._run("verify-review-draft", "synthetic-article")


STAGE_CLIS = {
    "st1506-wordpress-operator": (
        st1506_cli,
        "ST1506_WORDPRESS_OPERATOR_PRICE_OVERLAY_LIVE",
        invoke_st1506,
    ),
    "st1704-publication-operator-v2": (
        publication_v2_cli,
        "ST1704_PUBLICATION_OPERATOR_V2_PRICE_OVERLAY_LIVE",
        invoke_publication_v2,
    ),
    "st1703-self-hosted-wordpress": (
        self_hosted_cli,
        "SELF_HOSTED_WORDPRESS_PRICE_OVERLAY_LIVE",
        invoke_self_hosted,
    ),
    "st1704-editorial-pilot": (
        pilot_cli,
        "ST1704_SELF_HOSTED_EDITORIAL_PILOT_PRICE_OVERLAY_LIVE",
        invoke_pilot,
    ),
}


def guard_block(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    start = source.index("def _price_overlay_root(")
    end = source.index("raise SystemExit(69) from None", start)
    return source[start:end]


def test_every_legacy_cli_shares_one_live_check_implementation():
    blocks = {
        name: guard_block(module) for name, (module, _r, _i) in STAGE_CLIS.items()
    }
    assert len(set(blocks.values())) == 1, sorted(blocks)
    assert "price-overlay-live-check" in next(iter(blocks.values()))


@pytest.mark.parametrize(
    ("answers", "live"),
    [
        ([NOT_LIVE], False),
        ([ANSWER_LIVE], True),
        ([ANSWER_STATE_INVALID], True),
        *((list([answer]), True) for answer in UNUSABLE_ANSWERS.values()),
    ],
    ids=["not-live", "live", "state-invalid", *UNUSABLE_ANSWERS],
)
@pytest.mark.parametrize("name", sorted(STAGE_CLIS))
def test_the_legacy_cli_live_check_fails_closed(tmp_path, name, answers, live):
    module, _refusal, _invoke = STAGE_CLIS[name]
    root = fake_check_root(tmp_path, answers)
    assert module._price_overlay_live(root) is live
    assert checks_run(root) == 1
    # A checkout without the check refuses too.
    assert module._price_overlay_live(tmp_path / "missing") is True


@pytest.mark.parametrize("name", sorted(STAGE_CLIS))
def test_every_legacy_cli_refuses_before_its_dispatch_while_live(
    tmp_path, monkeypatch, capsys, name
):
    module, refusal, invoke = STAGE_CLIS[name]
    root = fake_check_root(tmp_path, [ANSWER_LIVE])
    monkeypatch.setattr(module, "_price_overlay_root", lambda fallback: root)
    capsys.readouterr()
    with pytest.raises(SystemExit) as error:
        invoke(module, monkeypatch)
    captured = capsys.readouterr()
    assert error.value.code == 69
    assert captured.err == refusal + "\n"
    assert captured.out == ""
    assert checks_run(root) == 1


@pytest.mark.parametrize("name", sorted(STAGE_CLIS))
def test_every_legacy_cli_reaches_its_dispatch_when_nothing_is_live(
    tmp_path, monkeypatch, capsys, name
):
    module, refusal, invoke = STAGE_CLIS[name]
    root = fake_check_root(tmp_path, [NOT_LIVE])
    monkeypatch.setattr(module, "_price_overlay_root", lambda fallback: root)
    capsys.readouterr()
    try:
        invoke(module, monkeypatch)
    except BaseException as error:  # noqa: BLE001 - only the refusal matters here
        assert not isinstance(error, SystemExit) or error.code != 69, error
        assert refusal not in str(error)
    captured = capsys.readouterr()
    assert refusal not in captured.err + captured.out
    assert checks_run(root) == 1


# ---------------------------------------------------------------------------
# Anonymous browser probes and the public UI shell
# ---------------------------------------------------------------------------


def probe_root(tmp_path, answers, script):
    root = fake_check_root(tmp_path, answers, name="probe-root")
    shutil.copy2(ROOT / "scripts" / script, root / "scripts" / script)
    return root


def probe_arguments(root, script):
    if script == "ks_before_capture.mjs":
        request = root / "input.json"
        request.write_text(
            json.dumps(
                {
                    "origin": "https://kurashinoshirube.com",
                    "widths": [390],
                    "surfaces": [{"kind": "home", "path": "/"}],
                    "screenshots": str(root / "screens"),
                }
            )
        )
        return [str(request)]
    return ["--origin", "https://kurashinoshirube.com", "--out", str(root / "out")]


PROBES = (
    "ks_before_capture.mjs",
    "ks_public_performance_probe.mjs",
    "ks_viewport_matrix.mjs",
    "site_improvements_audit.mjs",
    "site_improvements_consent_lab.mjs",
)


@pytest.mark.parametrize("script", PROBES)
def test_every_anonymous_probe_refuses_before_opening_a_browser(tmp_path, script):
    assert NODE is not None
    root = probe_root(tmp_path, [ANSWER_LIVE], script)
    completed = subprocess.run(
        [NODE, f"scripts/{script}", *probe_arguments(root, script)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 69, completed.stderr
    assert completed.stderr.strip().endswith("WORDPRESS_MCP_PRICE_OVERLAY_LIVE")
    assert "playwright" not in completed.stderr
    assert checks_run(root) == 1


@pytest.mark.parametrize("script", PROBES)
def test_every_anonymous_probe_continues_when_nothing_is_live(tmp_path, script):
    """The control stops at the missing browser package, after the check has answered."""
    assert NODE is not None
    root = probe_root(tmp_path, [NOT_LIVE], script)
    completed = subprocess.run(
        [NODE, f"scripts/{script}", *probe_arguments(root, script)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "PRICE_OVERLAY" not in completed.stderr
    assert completed.returncode != 69
    assert checks_run(root) == 1


@pytest.mark.parametrize("state", ["live", "not-live"])
def test_the_public_ui_shell_checks_before_opening_the_browser(tmp_path, state):
    assert NODE is not None
    answers = [ANSWER_LIVE] if state == "live" else [NOT_LIVE]
    root = fake_check_root(tmp_path, answers, name="ui-root")
    shutil.copy2(
        ROOT / "scripts/check_wordpress_public_ui_playwright.sh",
        root / "scripts/check_wordpress_public_ui_playwright.sh",
    )
    (root / "scripts/check_wordpress_public_ui_playwright.sh").chmod(0o755)
    completed = subprocess.run(
        ["/usr/bin/busybox", "sh", "scripts/check_wordpress_public_ui_playwright.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "RAOS_NODE": NODE, "PWD": str(root)},
        timeout=300,
    )
    assert completed.returncode == 69
    assert checks_run(root) == 1
    if state == "live":
        assert completed.stderr.strip() == "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"
    else:
        # The check passed; the run stops at the missing pinned Playwright CLI.
        assert "PRICE_OVERLAY" not in completed.stderr
        assert "WORDPRESS_PUBLIC_UI_PLAYWRIGHT_REFUSED" in completed.stderr
