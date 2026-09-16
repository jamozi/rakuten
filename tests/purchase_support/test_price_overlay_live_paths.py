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
import re
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
before_after = _load("ks_before_after_cli", "scripts/ks_before_after.py")
render_review = _load("ks_render_review_cli", "scripts/ks_render_review.py")
snapshot = _load(
    "raos_wordpress_incremental_snapshot_cli",
    "scripts/raos_wordpress_incremental_snapshot.py",
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


def deployment_operator_request_json(monkeypatch, calls, tmp_path):
    """The operator's own transport, not its CLI entry point.

    ``main()`` refuses every non-local command, but the publisher's ``invoke`` imports the
    module and calls ``run()`` directly, so the refusal has to stand where the connection is
    built. The credentials stub is silent on purpose: a refused call must not reach it.
    """
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", guard.OWNER_CHECKOUT)
    monkeypatch.setattr(operator, "ROOT", guard.REPOSITORY_ROOT)
    monkeypatch.setattr(operator, "credentials", lambda: ("synthetic", "x" * 24))
    monkeypatch.setattr(
        operator.urllib.request, "build_opener", recorder(calls, "operator-transport")
    )
    operator.request_json("GET", "/status")


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


def ks_before_after_cli(monkeypatch, calls, tmp_path):
    """The Before/After evidence helper: the ledger read is the first thing behind the guard."""
    monkeypatch.setattr(before_after, "ledger_rows", recorder(calls, "before-after"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ks_before_after.py",
            "--keys",
            "ks-synthetic",
            "--candidate",
            "a" * 64,
            "--candidate-root",
            str(tmp_path / "other-checkout"),
            "--out",
            str(tmp_path / "before-after"),
        ],
    )
    return _cli_outcome(before_after.main)


def ks_render_review_cli(monkeypatch, calls, tmp_path):
    """The review page renderer: reading the Before/After index is behind the guard."""
    monkeypatch.setattr(render_review, "read_index", recorder(calls, "render-review"))
    monkeypatch.setattr(
        sys, "argv", ["ks_render_review.py", str(tmp_path / "before-after")]
    )
    return _cli_outcome(render_review.main)


def incremental_snapshot_public_metadata(monkeypatch, calls, tmp_path):
    """The snapshot's own opener, refused at the fetch site and not only by call order."""
    reader = snapshot.PublicMetadataReader.__new__(snapshot.PublicMetadataReader)
    reader.opener = Opener(calls, "public-metadata")
    reader.get("posts", 1)


def _cli_outcome(main):
    """Run a refusing CLI and keep both its exit code and the refusal code it printed."""
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        try:
            code = main()
        except SystemExit as error:
            return f"exit={error.code} {buffer.getvalue()}"
    return f"exit={code} {buffer.getvalue()}"


PYTHON_PATHS = {
    "ks-before-after-cli": ks_before_after_cli,
    "ks-render-review-cli": ks_render_review_cli,
    "incremental-snapshot-public-metadata": incremental_snapshot_public_metadata,
    "editor-mcp-client-construction": editor_mcp_client_construction,
    "editor-mcp-request": editor_mcp_request,
    "public-page-readback": public_page_readback,
    "public-stylesheet-readback": public_stylesheet_readback,
    "deployment-bridge-call": deployment_bridge_call,
    "deployment-operator-request-json": deployment_operator_request_json,
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
# The one caller the operator's transport still serves while a run is live
# ---------------------------------------------------------------------------
#
# The purge is what takes published values back down: `prepare --price-overlay-purge` reads the
# live injected documents as its baseline and the purge `publish` writes the price-free bodies
# back, both through request_json. Refusing those would make the values impossible to remove,
# so exactly one in-process context is exempt - and nothing else is.


def request_json_outcome(monkeypatch, calls, bound):
    def credentials():
        calls.append("credentials")
        return ("synthetic", "x" * 24)

    monkeypatch.setattr(operator, "credentials", credentials)
    monkeypatch.setattr(
        operator.urllib.request, "build_opener", recorder(calls, "operator-transport")
    )
    context = (
        operator.price_overlay_bound_calls() if bound else contextlib.nullcontext()
    )
    try:
        with context:
            operator.request_json("GET", "/status")
    except BaseException as error:  # noqa: BLE001 - the code is what is asserted
        return f"{type(error).__name__}:{error}"
    return "RETURNED"


@pytest.mark.parametrize("state", ["live", "unreadable", "empty"])
def test_the_operator_transport_serves_only_the_run_bound_context(
    tmp_path, monkeypatch, state
):
    owner = owner_with_state(tmp_path, state)
    empty = (tmp_path / "worktree").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(operator, "ROOT", empty)
    refused = {
        "live": "WORDPRESS_MCP_PRICE_OVERLAY_LIVE",
        "unreadable": "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID",
        "empty": None,
    }[state]

    calls = []
    text = request_json_outcome(monkeypatch, calls, bound=False)
    if refused is None:
        assert calls == ["credentials", "operator-transport"], text
    else:
        assert refused in text, text
        # Refused before the application password is read, not only before the socket.
        assert calls == [], text

    # The publisher's run-bound calls reach the transport whatever the run state is.
    bound_calls = []
    bound_text = request_json_outcome(monkeypatch, bound_calls, bound=True)
    assert "PRICE_OVERLAY" not in bound_text, bound_text
    assert bound_calls == ["credentials", "operator-transport"], bound_text
    assert operator._price_overlay_bound.get() is False


def test_only_bound_invoke_enters_the_context_request_json_serves(monkeypatch):
    seen = []
    monkeypatch.setattr(
        operator, "run", lambda *_a, **_k: seen.append(operator._price_overlay_bound.get())
    )
    direct.invoke("status", {})
    direct.bound_invoke("status", {})
    assert seen == [False, True]
    assert operator._price_overlay_bound.get() is False


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"price_overlay_purge": RUN_ID}, "bound_invoke"),
        ({"price_overlay_run": RUN_ID}, "bound_invoke"),
    ],
)
def test_a_run_bound_publish_uses_the_call_the_transport_serves(
    tmp_path, monkeypatch, flags, expected
):
    """Without this the purge publish would be refused by its own operator while live."""
    seen = {}

    def record(root, directory, candidate_id, call, run=None, purge=None):
        seen["call"] = call
        return {"candidate_id": candidate_id}

    monkeypatch.setattr(direct, "_publish", record)
    directory = tmp_path / "candidate"
    directory.mkdir()
    direct.publish(tmp_path, directory, "a" * 64, **flags)
    assert seen["call"] is getattr(direct, expected)


def test_a_flag_free_publish_keeps_the_call_request_json_refuses(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        direct,
        "_publish",
        lambda root, d, cid, call, run=None, purge=None: seen.setdefault("call", call),
    )
    monkeypatch.setattr(direct, "refuse_while_price_overlay_live", lambda root: None)
    directory = tmp_path / "candidate"
    directory.mkdir()
    direct.publish(tmp_path, directory, "a" * 64)
    assert seen["call"] is direct.invoke


def test_the_run_bound_prepare_defaults_to_the_call_the_transport_serves():
    """`prepare --price-overlay-purge` reads the live injected documents as its baseline."""
    import inspect

    signature = inspect.signature(direct.prepare_price_overlay)
    assert signature.parameters["call"].default is direct.bound_invoke
    assert inspect.signature(direct.prepare).parameters["call"].default is direct.invoke


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


def write_live_check(root, owner=None):
    """The Node check with its owner checkout pointed at ``owner`` (``root`` by default).

    The destination rule is anchored to a fixed absolute path in production (the launcher is
    stubbed the same way, see ``launcher_root``), so a fixture that wants an exempt destination
    has to stand in for the owner checkout. Passing a different ``owner`` separates that anchor
    from the checkout the module itself is running in.
    """
    source = (ROOT / "scripts/raos_price_overlay_live_check.mjs").read_text(encoding="utf-8")
    pinned = "export const OWNER_CHECKOUT = '/home/minami/rakuten';"
    assert source.count(pinned) == 1, pinned
    (root / "scripts/raos_price_overlay_live_check.mjs").write_text(
        source.replace(
            pinned,
            f"export const OWNER_CHECKOUT = {json.dumps(str(owner or root))};",
            1,
        ),
        encoding="utf-8",
    )


def fake_check_root(tmp_path, answers, name="check-root"):
    """A checkout whose .venv/bin/python is the fake operator with the given answer script."""
    root = (tmp_path / name).resolve()
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/raos_wordpress_deployment_operator.py").write_text("")
    write_live_check(root)
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


def probe_arguments(root, script, origin="https://kurashinoshirube.com", out=None):
    out = root / "out" if out is None else Path(out)
    if script == "ks_before_capture.mjs":
        request = root / "input.json"
        request.write_text(
            json.dumps(
                {
                    "origin": origin,
                    "widths": [390],
                    "surfaces": [{"kind": "home", "path": "/"}],
                    "screenshots": str(out),
                }
            )
        )
        return [str(request)]
    if script in {"site_improvements_audit.mjs", "site_improvements_consent_lab.mjs"}:
        return ["--origin", origin, "--output", str(out / "baseline.json")]
    return ["--origin", origin, "--out", str(out)]


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


def test_the_two_before_after_clis_exit_69_with_the_refusal_code(tmp_path, monkeypatch):
    """Contract §8: the same exit code as the Node probes and the legacy CLIs."""
    owner = owner_with_state(tmp_path, "live")
    empty = (tmp_path / "worktree").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", empty)
    for module, argv in (
        (
            before_after,
            ["ks_before_after.py", "--keys", "ks-synthetic", "--out", str(tmp_path / "o")],
        ),
        (render_review, ["ks_render_review.py", str(tmp_path / "o")]),
    ):
        monkeypatch.setattr(sys, "argv", argv)
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer), pytest.raises(SystemExit) as error:
            module.main()
        assert error.value.code == 69, module.__name__
        assert buffer.getvalue().strip() == LIVE, module.__name__
    assert not (tmp_path / "o").exists()


def test_the_before_after_helper_checks_the_candidate_root_it_was_given(
    tmp_path, monkeypatch
):
    """``--candidate-root`` may point at another checkout, so that checkout is checked too."""
    other = owner_with_state(tmp_path, "live")
    empty = (tmp_path / "worktree").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", empty)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", empty)
    assert guard.price_overlay_refusal() is None
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ks_before_after.py",
            "--keys",
            "ks-synthetic",
            "--candidate-root",
            str(other),
            "--out",
            str(tmp_path / "o"),
        ],
    )
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer), pytest.raises(SystemExit) as error:
        before_after.main()
    assert error.value.code == 69
    assert buffer.getvalue().strip() == LIVE


# ---------------------------------------------------------------------------
# The standalone candidate preview CLI: what a run-bound candidate may print
# ---------------------------------------------------------------------------
#
# Contract §8 leaves this one route unrefused while a run is live (the publisher drives it for
# the run-bound candidate), so the redaction has to happen in what it prints: stdout is a
# terminal scrollback, an agent transcript and a CI log, none of which the §5 purge reaches.

PREVIEW_RESULT = {
    "schema": "RAOSOwnerDirectPreviewV1",
    "status": "FAIL",
    "candidate_id": "b" * 64,
    "source_sha256": "c" * 64,
    "runtime_sha256": "d" * 64,
    "checked_at": "2026-09-16T00:00:00+00:00",
    "urls": [
        "http://127.0.0.1:41398/",
        "http://127.0.0.1:41398/carry-on-suitcase-comparison/",
    ],
    "screenshots": [
        {
            "path": "/home/minami/rakuten/.secrets/wordpress-mcp/owner-direct-v1/"
            + "b" * 64
            + "/screenshots/0-home-390.png",
            "sha256": "e" * 64,
        }
    ],
    "failures": ["/carry-on-suitcase-comparison/:390:horizontal-overflow"],
}


PREVIEW_CANDIDATE_ID = "b" * 64
BOUND = {
    "schema": "RAOS_OWNER_DIRECT_PRICE_OVERLAY_V1",
    "mode": "PUBLISH",
    "run_id": RUN_ID,
}


def prepared_owner_checkout(tmp_path, monkeypatch, *, state="live", prepared=True):
    """An owner checkout whose approval record prepared ``PREVIEW_CANDIDATE_ID``.

    The run-bound preview resolves the candidate's ``price_overlay`` claim against this
    record, so the fixture has to be the real thing: the run the publisher wrote, and the id
    ``prepare`` recorded under ``prepared_candidates``.
    """
    from scripts import raos_wordpress_price_overlay as price_overlay
    from raos.adapters.rakuten_price_refresh_client import PrivateStore

    owner = owner_with_state(tmp_path, state)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", owner)
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(preview_cli, "ROOT", owner)
    if state == "empty":
        ks020.write_run(owner)
    if prepared:
        price_overlay._remember_prepared(
            PrivateStore(owner), RUN_ID, "PUBLISH", PREVIEW_CANDIDATE_ID
        )
    return owner


def bound_candidate_path(owner, candidate, name=PREVIEW_CANDIDATE_ID):
    directory = owner / ".secrets/wordpress-mcp/owner-direct-v1" / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "candidate.json"
    path.write_text(json.dumps(candidate))
    return path


def preview_cli_for(monkeypatch, path):
    """Run the CLI on an existing candidate file with the renderer replaced."""
    monkeypatch.setattr(
        preview_cli, "prepare_candidate_preview", lambda *a, **k: dict(PREVIEW_RESULT)
    )
    monkeypatch.setattr(
        sys, "argv", ["raos_wordpress_direct_preview.py", "--candidate", str(path)]
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = preview_cli.main()
    return code, buffer.getvalue()


def preview_cli_stdout(monkeypatch, tmp_path, candidate):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))
    monkeypatch.setattr(
        preview_cli, "prepare_candidate_preview", lambda *a, **k: dict(PREVIEW_RESULT)
    )
    monkeypatch.setattr(
        sys, "argv", ["raos_wordpress_direct_preview.py", "--candidate", str(path)]
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = preview_cli.main()
    return code, buffer.getvalue()


def test_the_preview_cli_redacts_a_verified_run_bound_candidate(tmp_path, monkeypatch):
    """The publisher's own redaction, plus counts for the fields that carry paths and hashes."""
    owner = prepared_owner_checkout(tmp_path, monkeypatch)
    path = bound_candidate_path(
        owner, {"candidate_id": PREVIEW_CANDIDATE_ID, "price_overlay": BOUND}
    )
    code, printed = preview_cli_for(monkeypatch, path)
    assert code == 1
    assert json.loads(printed) == {
        "candidate": f"price-overlay:{RUN_ID}:publish",
        "candidate_id": "REDACTED_PRICE_OVERLAY",
        "price_overlay": {"mode": "PUBLISH", "run_id": RUN_ID},
        "status": "FAIL",
        "failures": ["/carry-on-suitcase-comparison/:390:horizontal-overflow"],
        "screenshots": 1,
        "urls": 2,
    }
    assert re.search(r"[0-9a-f]{64}", printed) is None, printed
    assert ".secrets" not in printed


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("forged-key", "DIRECT_PREVIEW_PRICE_OVERLAY_BINDING_INVALID"),
        ("not-an-object", "DIRECT_PREVIEW_PRICE_OVERLAY_BINDING_INVALID"),
        ("wrong-schema", "DIRECT_PREVIEW_PRICE_OVERLAY_BINDING_INVALID"),
        ("unknown-mode", "DIRECT_PREVIEW_PRICE_OVERLAY_FLAG_REQUIRED"),
        ("unknown-run", "DIRECT_PREVIEW_PRICE_OVERLAY_APPROVAL_MISSING"),
        ("not-prepared", "DIRECT_PREVIEW_PRICE_OVERLAY_CANDIDATE_HANDLE_UNKNOWN"),
        ("other-candidate-id", "DIRECT_PREVIEW_PRICE_OVERLAY_CANDIDATE_UNKNOWN"),
        ("wrong-directory", "DIRECT_PREVIEW_PRICE_OVERLAY_CANDIDATE_UNKNOWN"),
        ("outside-the-candidate-base", "DIRECT_PREVIEW_OWNER_CHECKOUT_REQUIRED"),
        ("symlinked-candidate-directory", "DIRECT_PREVIEW_OWNER_CHECKOUT_REQUIRED"),
    ],
)
def test_the_preview_cli_refuses_a_price_overlay_claim_that_does_not_resolve(
    tmp_path, monkeypatch, change, code
):
    """`price_overlay` is a claim resolved against the approval record, not a flag.

    Without this, one hand-written key switched the live refusal off for any candidate file
    (round 8 review, finding 2) and let the run-bound branch freeze the injected theme.
    """
    owner = prepared_owner_checkout(
        tmp_path, monkeypatch, prepared=change != "not-prepared"
    )
    candidate = {"candidate_id": PREVIEW_CANDIDATE_ID, "price_overlay": dict(BOUND)}
    name = PREVIEW_CANDIDATE_ID
    if change == "forged-key":
        candidate["price_overlay"] = {"mode": "publish", "run_id": RUN_ID}
    elif change == "not-an-object":
        candidate["price_overlay"] = f"price-overlay:{RUN_ID}:publish"
    elif change == "wrong-schema":
        candidate["price_overlay"]["schema"] = "RAOS_OWNER_DIRECT_PRICE_OVERLAY_V2"
    elif change == "unknown-mode":
        candidate["price_overlay"]["mode"] = "PREVIEW"
    elif change == "unknown-run":
        candidate["price_overlay"]["run_id"] = "ks020-synthetic-9999"
    elif change == "other-candidate-id":
        candidate["candidate_id"] = "c" * 64
    elif change == "wrong-directory":
        name = "c" * 64
    if change == "outside-the-candidate-base":
        path = tmp_path / "loose-candidate.json"
        path.write_text(json.dumps(candidate))
    elif change == "symlinked-candidate-directory":
        # The containment check resolves the candidate path. Without that `.resolve()` the
        # parent is the base and the name is the recorded id, so the renderer would run with
        # `candidate_dir` pointing through the link and write the injected theme and the
        # screenshots outside the owner checkout - where the §5 sweep never looks, because
        # `owner_direct_candidates_containing` skips a symlinked directory.
        outside = (tmp_path / "outside-the-owner-checkout").resolve()
        outside.mkdir()
        (outside / "candidate.json").write_text(json.dumps(candidate))
        base = owner / ".secrets/wordpress-mcp/owner-direct-v1"
        base.mkdir(parents=True, exist_ok=True)
        (base / PREVIEW_CANDIDATE_ID).symlink_to(outside)
        path = base / PREVIEW_CANDIDATE_ID / "candidate.json"
    else:
        path = bound_candidate_path(owner, candidate, name=name)
    calls = []
    monkeypatch.setattr(
        preview_cli, "prepare_candidate_preview", recorder(calls, "preview")
    )
    monkeypatch.setattr(
        sys, "argv", ["raos_wordpress_direct_preview.py", "--candidate", str(path)]
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert preview_cli.main() == 1
    assert json.loads(buffer.getvalue()) == {"status": "FAIL", "code": code}
    assert calls == []


@pytest.mark.parametrize("state", ["live", "empty"])
def test_the_preview_cli_refuses_a_run_bound_candidate_outside_the_owner_checkout(
    tmp_path, monkeypatch, state
):
    """The frozen theme copy is written under the *running* checkout.

    ``prepare_candidate_preview`` copies the injected theme to
    ``<ROOT>/.secrets/wordpress-direct-preview/theme-<tree sha256>``, and the §5 sweep walks
    that directory in the owner checkout only, so a run-bound preview from a worktree would
    leave injected bytes - in a directory named after a price-recoverable hash - where no
    purge looks. Refused whether or not anything is live.
    """
    owner = prepared_owner_checkout(tmp_path, monkeypatch, state=state)
    path = bound_candidate_path(
        owner, {"candidate_id": PREVIEW_CANDIDATE_ID, "price_overlay": BOUND}
    )
    worktree = (tmp_path / "worktree").resolve()
    worktree.mkdir()
    monkeypatch.setattr(preview_cli, "ROOT", worktree)
    calls = []
    monkeypatch.setattr(
        preview_cli, "prepare_candidate_preview", recorder(calls, "preview")
    )
    monkeypatch.setattr(
        sys, "argv", ["raos_wordpress_direct_preview.py", "--candidate", str(path)]
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert preview_cli.main() == 1
    assert json.loads(buffer.getvalue()) == {
        "status": "FAIL",
        "code": "DIRECT_PREVIEW_OWNER_CHECKOUT_REQUIRED",
    }
    assert calls == []


def test_the_preview_cli_renders_a_verified_candidate_when_nothing_is_live(
    tmp_path, monkeypatch
):
    """The blessed route still works: a prepared candidate previewed from the owner checkout."""
    owner = prepared_owner_checkout(tmp_path, monkeypatch, state="empty")
    path = bound_candidate_path(
        owner, {"candidate_id": PREVIEW_CANDIDATE_ID, "price_overlay": BOUND}
    )
    code, printed = preview_cli_for(monkeypatch, path)
    assert code == 1
    assert json.loads(printed)["candidate"] == f"price-overlay:{RUN_ID}:publish"


def test_the_preview_cli_renders_the_directory_it_verified(tmp_path, monkeypatch):
    """The renderer is handed ``candidate_path.resolve().parent``, not ``--candidate``'s parent.

    The named path here walks out of the candidate directory and back in, so the two differ:
    the unresolved parent is the candidate *base*, which would put the screenshots and the
    frozen theme one level above the directory the purge deletes.
    """
    owner = prepared_owner_checkout(tmp_path, monkeypatch, state="empty")
    path = bound_candidate_path(
        owner, {"candidate_id": PREVIEW_CANDIDATE_ID, "price_overlay": BOUND}
    )
    named = path.parent / ".." / PREVIEW_CANDIDATE_ID / "candidate.json"
    assert named.parent != path.parent
    calls = []
    monkeypatch.setattr(
        preview_cli,
        "prepare_candidate_preview",
        lambda candidate, directory: calls.append(directory) or dict(PREVIEW_RESULT),
    )
    monkeypatch.setattr(
        sys, "argv", ["raos_wordpress_direct_preview.py", "--candidate", str(named)]
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert preview_cli.main() == 1
    assert calls == [path.parent.resolve()]


def test_the_preview_cli_prints_a_flag_free_candidate_unchanged(tmp_path, monkeypatch):
    """Nothing about the flag-free shape changes: it still prints the whole report."""
    empty = (tmp_path / "empty-checkout").resolve()
    (empty / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", empty)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", empty)
    code, printed = preview_cli_stdout(monkeypatch, tmp_path, {"candidate_id": "b" * 64})
    assert code == 1
    assert json.loads(printed) == PREVIEW_RESULT


def test_the_preview_cli_still_refuses_a_flag_free_candidate_while_live(
    tmp_path, monkeypatch
):
    owner = owner_with_state(tmp_path, "live")
    monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(guard, "REPOSITORY_ROOT", owner)
    code, printed = preview_cli_stdout(monkeypatch, tmp_path, {"candidate_id": "b" * 64})
    assert code == 1
    assert json.loads(printed) == {
        "status": "FAIL",
        "code": "DIRECT_PREVIEW_" + LIVE,
    }


# ---------------------------------------------------------------------------
# The destination rule: only a candidate directory the run itself deletes
# ---------------------------------------------------------------------------
#
# Round 9 decided this from the destination's *name*; the §5 sweep deletes by content, so an
# invented or needle-free directory of the right shape was accepted and never deleted (round 9
# review). The exemption is gone for every caller but the run-bound preview, and that one is
# proved from the candidate's own binding.


def bound_candidate_destination(module_root, destination):
    """``boundCandidateDestination`` as the module copied into ``module_root`` answers it."""
    assert NODE is not None
    module = (Path(module_root) / "scripts/raos_price_overlay_live_check.mjs").as_uri()
    program = (
        f"import {{ boundCandidateDestination }} from {json.dumps(module)};"
        "process.stdout.write(JSON.stringify(boundCandidateDestination("
        f"{json.dumps(str(destination))})));"
    )
    completed = subprocess.run(
        [NODE, "--input-type=module", "-e", program],
        cwd=module_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def stub_owner_checkout(tmp_path, name="stub-owner-checkout"):
    """A checkout the copied Node check treats as the owner checkout (no operator answers)."""
    root = (tmp_path / name).resolve()
    (root / "scripts").mkdir(parents=True)
    write_live_check(root)
    return root


CANDIDATE_RELATIVE = ".secrets/wordpress-mcp/owner-direct-v1"
PREVIEW_RELATIVE = ".secrets/wordpress-direct-preview"
CANDIDATE_ID = "a" * 64
BINDING = {
    "schema": "RAOS_OWNER_DIRECT_PRICE_OVERLAY_V1",
    "mode": "PUBLISH",
    "run_id": RUN_ID,
}


def write_candidate(root, name=CANDIDATE_ID, candidate=None, relative=CANDIDATE_RELATIVE):
    """One owner-direct candidate directory, with the candidate.json the rule reads."""
    directory = root / relative / name
    directory.mkdir(parents=True, exist_ok=True)
    if candidate is not None:
        (directory / "candidate.json").write_text(json.dumps(candidate))
    return directory


def bound_candidate(root, name=CANDIDATE_ID, mode="PUBLISH"):
    return write_candidate(
        root,
        name=name,
        candidate={"candidate_id": name, "price_overlay": {**BINDING, "mode": mode}},
    )


# shape -> (build the fixture, pick the destination from it, accepted)
DESTINATION_SHAPES = {
    # The one exemption: the publisher's run-bound preview writes its screenshots into the
    # candidate directory the purge publish deletes by the id the approval record holds.
    "bound-publish-candidate-screenshots": (
        lambda root: bound_candidate(root) / "screenshots",
        True,
    ),
    "bound-publish-candidate-png": (
        lambda root: bound_candidate(root) / "screenshots/0-home-390.png",
        True,
    ),
    "bound-publish-candidate-directory": (lambda root: bound_candidate(root), True),
    # The purge candidate froze the live injected documents as its baseline; `_finish_purge`
    # deletes it by its own id.
    "bound-purge-candidate": (
        lambda root: bound_candidate(root, mode="PURGE") / "screenshots",
        True,
    ),
    # Everything below outlives the purge, or cannot be shown not to.
    "invented-candidate-directory": (
        lambda root: root / CANDIDATE_RELATIVE / ("c" * 64) / "screenshots/x.png",
        False,
    ),
    "candidate-directory-without-candidate-json": (
        lambda root: write_candidate(root) / "screenshots/x.png",
        False,
    ),
    "flag-free-candidate": (
        lambda root: write_candidate(root, candidate={"candidate_id": CANDIDATE_ID})
        / "screenshots",
        False,
    ),
    "binding-not-an-object": (
        lambda root: write_candidate(
            root, candidate={"price_overlay": f"price-overlay:{RUN_ID}:publish"}
        )
        / "screenshots",
        False,
    ),
    "binding-wrong-schema": (
        lambda root: write_candidate(
            root,
            candidate={"price_overlay": {**BINDING, "schema": "RAOS_V2"}},
        )
        / "screenshots",
        False,
    ),
    "binding-unknown-mode": (
        lambda root: write_candidate(
            root, candidate={"price_overlay": {**BINDING, "mode": "PREVIEW"}}
        )
        / "screenshots",
        False,
    ),
    "binding-invalid-run-id": (
        lambda root: write_candidate(
            root, candidate={"price_overlay": {**BINDING, "run_id": "short"}}
        )
        / "screenshots",
        False,
    ),
    "candidate-json-not-json": (
        lambda root: _unparsable_candidate(root) / "screenshots",
        False,
    ),
    "candidate-json-is-a-directory": (
        lambda root: _candidate_json_directory(root) / "screenshots",
        False,
    ),
    # The rule reads a file under `.secrets` in a browser-driving process: it reads at most
    # 4 MiB, and a candidate.json larger than that is refused rather than read.
    "oversized-candidate-json": (
        lambda root: _oversized_candidate(root) / "screenshots",
        False,
    ),
    # `.staging-*` is reported by the sweep unconditionally, but nothing writes a rendering
    # there and it carries no binding to read: not a shape this rule accepts any more.
    "staging-sibling": (
        lambda root: bound_candidate(root, name=".staging-derive-1") / "theme/x.png",
        False,
    ),
    # The frozen preview theme is written by prepare_candidate_preview itself, never by a
    # browser, and holds no candidate.json.
    "frozen-preview-theme": (
        lambda root: root / PREVIEW_RELATIVE / ("theme-" + CANDIDATE_ID) / "x.png",
        False,
    ),
    "preview-fixtures": (
        lambda root: root / PREVIEW_RELATIVE / "fixtures/home-390.png",
        False,
    ),
    "caller-named-directory": (
        lambda root: _beside_a_bound_candidate(root, "perf-shots/home-390.png"),
        False,
    ),
    "loose-file-under-the-base": (
        lambda root: _beside_a_bound_candidate(root, "loose-capture.png"),
        False,
    ),
    "the-base-itself": (lambda root: _beside_a_bound_candidate(root, ""), False),
    "another-private-directory": (
        lambda root: root / ".secrets/wordpress-mcp/incremental-snapshots/x",
        False,
    ),
    "output": (lambda root: root / "output/ks-20260915/x.png", False),
    "escape-with-dot-dot": (
        lambda root: bound_candidate(root) / "../../../../output/x.png",
        False,
    ),
    "symlinked-candidate-directory": (lambda root: _symlinked_unit(root), False),
    # The rule anchors at the *start* of the path, not anywhere in it.
    "the-base-at-a-non-zero-offset": (
        lambda root: _padded_to_the_base_length(root),
        False,
    ),
}


def _unparsable_candidate(root):
    directory = write_candidate(root)
    (directory / "candidate.json").write_text("{not json")
    return directory


def _oversized_candidate(root):
    """A bound candidate whose candidate.json is larger than the rule will read."""
    directory = write_candidate(
        root,
        candidate={
            "candidate_id": CANDIDATE_ID,
            "price_overlay": BINDING,
            "filler": "0" * (4 * 1024 * 1024 + 1024),
        },
    )
    assert (directory / "candidate.json").stat().st_size > 4 * 1024 * 1024
    return directory


def _candidate_json_directory(root):
    directory = write_candidate(root)
    (directory / "candidate.json").mkdir()
    return directory


def _beside_a_bound_candidate(root, relative):
    """A real bound candidate exists; the destination is somewhere else under the base."""
    base = bound_candidate(root).parent
    return base / relative if relative else base


def _padded_to_the_base_length(root):
    """Outside the checkout, but holding the base at a non-zero offset (round 10 review).

    ``posix.startsWith(base)`` is load-bearing: the unit is taken from ``posix.slice(
    base.length)``, so a substring test would read that slice from the wrong place. The prefix
    here is padded to exactly the base's length, so the slice lands on a real bound candidate's
    64-hex name and the binding read succeeds - a capture written entirely outside the owner
    checkout, where the §5 sweep never looks, would be granted the exemption.
    """
    base = f"{bound_candidate(root).parent}/"
    prefix = f"{root.parent}/{'p' * (len(base) - len(str(root.parent)) - 2)}/"
    assert len(prefix) == len(base) and not prefix.startswith(base)
    return f"{prefix}{CANDIDATE_ID}{base}outside.png"


def _symlinked_unit(root):
    """A unit that is a symlink out of the checkout: the sweep skips it (`is_symlink()`)."""
    outside = root.parent / "outside-the-owner-checkout"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "candidate.json").write_text(
        json.dumps({"candidate_id": "b" * 64, "price_overlay": BINDING})
    )
    base = root / CANDIDATE_RELATIVE
    base.mkdir(parents=True, exist_ok=True)
    link = base / ("b" * 64)
    if not link.is_symlink():
        link.symlink_to(outside)
    return link / "screenshots/x.png"


@pytest.mark.parametrize("shape", sorted(DESTINATION_SHAPES))
def test_the_node_destination_rule_answers_for_every_shape(tmp_path, shape):
    build, accepted = DESTINATION_SHAPES[shape]
    root = stub_owner_checkout(tmp_path, name="shape-owner")
    destination = build(root)
    answer = bound_candidate_destination(root, destination)
    if not accepted:
        assert answer is None, (shape, answer)
        return
    # Accepted answers with the *resolved* path, which is what the caller writes into.
    assert answer == str(Path(destination).resolve()), (shape, answer)


@pytest.mark.parametrize(
    ("destination", "accepted"),
    [
        ("", False),
        ("output/ks-20260915/x.png", False),
        (f"/tmp/anything/{CANDIDATE_RELATIVE}/{CANDIDATE_ID}/x", False),
    ],
)
def test_the_node_destination_rule_refuses_these_against_the_real_owner_checkout(
    destination, accepted
):
    """The production module, with its production `/home/minami/rakuten` anchor."""
    assert (bound_candidate_destination(ROOT, destination) is not None) is accepted


def test_a_relative_destination_is_refused_even_from_the_owner_checkout(tmp_path):
    """The absolute-path requirement is the check's, not the caller's working directory.

    ``bound_candidate_destination`` runs node with cwd set to the stubbed owner checkout, so
    this relative path resolves into the bound candidate directory. It must still be refused:
    the documented guarantee is that a relative destination runs the live check.
    """
    root = stub_owner_checkout(tmp_path, name="relative-destination-owner")
    inside = bound_candidate(root) / "screenshots"
    inside.mkdir(parents=True, exist_ok=True)
    relative = f"{CANDIDATE_RELATIVE}/{CANDIDATE_ID}/screenshots/x.png"
    assert bound_candidate_destination(root, inside / "x.png") is not None
    assert bound_candidate_destination(root, relative) is None


def test_a_symlink_cannot_make_a_destination_look_bound(tmp_path):
    """The deepest existing ancestor is resolved, so `.secrets/...` -> output/ still refuses."""
    root = stub_owner_checkout(tmp_path)
    real = root / "output/ks-20260915"
    real.mkdir(parents=True)
    (real / "candidate.json").write_text(
        json.dumps({"candidate_id": "b" * 64, "price_overlay": BINDING})
    )
    base = root / CANDIDATE_RELATIVE
    base.mkdir(parents=True)
    (base / ("b" * 64)).symlink_to(real)
    assert bound_candidate_destination(root, base / ("b" * 64) / "s/a.png") is None
    kept = bound_candidate(root) / "screenshots"
    kept.mkdir(parents=True, exist_ok=True)
    assert bound_candidate_destination(root, kept / "0-home-390.png") is not None


def test_the_same_directory_outside_the_owner_checkout_is_not_accepted(tmp_path):
    """Only the owner checkout's own candidate directory is swept (§5)."""
    root = stub_owner_checkout(tmp_path)
    relative = f"{CANDIDATE_RELATIVE}/{CANDIDATE_ID}/screenshots/x.png"
    bound_candidate(root)
    assert bound_candidate_destination(root, root / relative) is not None
    for other in (tmp_path / "another-clone", root / "output", root / ".worktrees/w"):
        directory = other / CANDIDATE_RELATIVE / CANDIDATE_ID
        directory.mkdir(parents=True)
        (directory / "candidate.json").write_text(
            json.dumps({"candidate_id": CANDIDATE_ID, "price_overlay": BINDING})
        )
        assert bound_candidate_destination(root, other / relative) is None, other


def test_the_anchor_is_the_owner_checkout_not_the_running_repository(tmp_path):
    """§5 walks the owner checkout only, so a worktree's own candidate directory is not it.

    The module runs from ``worktree`` and is pinned to ``owner``: the identical bound candidate
    under the checkout it is running in must still answer null.
    """
    owner = (tmp_path / "owner-checkout").resolve()
    worktree = (tmp_path / "worktree").resolve()
    for root in (owner, worktree):
        (root / "scripts").mkdir(parents=True)
        bound_candidate(root)
    write_live_check(worktree, owner=owner)
    inside = f"{CANDIDATE_RELATIVE}/{CANDIDATE_ID}/screenshots"
    assert bound_candidate_destination(worktree, owner / inside) is not None
    assert bound_candidate_destination(worktree, worktree / inside) is None


def refuse_unless_bound(root, destination):
    """Run ``refuseWhilePriceOverlayLiveUnlessBoundCandidate`` against the copy in ``root``."""
    assert NODE is not None
    module = (root / "scripts/raos_price_overlay_live_check.mjs").as_uri()
    program = (
        f"import {{ refuseWhilePriceOverlayLiveUnlessBoundCandidate }} from {json.dumps(module)};"
        "process.stdout.write(await refuseWhilePriceOverlayLiveUnlessBoundCandidate("
        f"{json.dumps(str(destination))}));"
    )
    return subprocess.run(
        [NODE, "--input-type=module", "-e", program],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.parametrize(
    "shape", ["bound-candidate", "unbound-candidate", "output", "relative"]
)
def test_the_one_exemption_is_the_bound_candidate_and_nothing_else(tmp_path, shape):
    """While live: the run-bound preview's destination passes, everything else refuses."""
    root = fake_check_root(tmp_path, [ANSWER_LIVE], name="destination-root")
    destination = {
        "bound-candidate": lambda: bound_candidate(root) / "screenshots",
        "unbound-candidate": lambda: write_candidate(
            root, candidate={"candidate_id": CANDIDATE_ID}
        )
        / "screenshots",
        "output": lambda: root / "output/ks-20260915",
        "relative": lambda: f"{CANDIDATE_RELATIVE}/{CANDIDATE_ID}/screenshots",
    }[shape]()
    completed = refuse_unless_bound(root, destination)
    if shape == "bound-candidate":
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "PRICE_OVERLAY" not in completed.stderr
        assert completed.stdout == str(Path(destination).resolve())
        assert checks_run(root) == 0
    else:
        assert completed.returncode == 69, completed.stdout + completed.stderr
        assert completed.stderr.strip() == "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"
        assert checks_run(root) == 1


def test_the_exemption_answers_with_the_path_it_verified(tmp_path):
    """The verified destination is returned, so it cannot be proved safe and then swapped.

    A caller that names a path through a symlink gets the resolved one back; the pinned write
    below is what makes that structural for the only caller.
    """
    root = fake_check_root(tmp_path, [ANSWER_LIVE], name="verified-path-root")
    directory = bound_candidate(root)
    real = directory / "screenshots"
    real.mkdir()
    (directory / "link").symlink_to(real)
    completed = refuse_unless_bound(root, directory / "link/0-home-390.png")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == str(real / "0-home-390.png")


def test_the_run_bound_preview_writes_into_the_path_the_check_returned():
    """The one caller keeps the checked argument and the written path the same object."""
    source = (
        ROOT / "changes/wordpress-direct-publish-v1/preview-browser.mjs"
    ).read_text(encoding="utf-8")
    assert (
        "const screenshotsDirectory = await refuseWhilePriceOverlayLiveUnlessBoundCandidate("
        in source
    )
    assert "path.join(screenshotsDirectory," in source
    assert "path.join(input.screenshots" not in source


@pytest.mark.parametrize("script", ["ks_before_capture.mjs"])
def test_a_probe_writing_into_the_candidate_directory_is_refused_as_well(
    tmp_path, script
):
    """The destination is no exemption for an anonymous probe any more (round 10): only the
    publisher's run-bound preview may capture while values are published."""
    assert NODE is not None
    root = probe_root(tmp_path, [ANSWER_LIVE], script)
    inside = bound_candidate(root) / "screenshots"
    inside.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            NODE,
            f"scripts/{script}",
            *probe_arguments(
                root, script, origin="http://127.0.0.1:41398", out=inside
            ),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 69, completed.stdout + completed.stderr
    assert completed.stderr.strip().endswith("WORDPRESS_MCP_PRICE_OVERLAY_LIVE")
    assert "playwright" not in completed.stderr
    assert checks_run(root) == 1


# ---------------------------------------------------------------------------
# Every other browser capture of a WordPress page
# ---------------------------------------------------------------------------

CAPTURE_SCRIPTS = {
    # relative path -> (extra files to copy, arguments builder, keeps the one exemption)
    "changes/wordpress-direct-publish-v1/preview-browser.mjs": ((), "preview-browser", True),
    "changes/wordpress-local-preview-v1/browser/reader_experience_audit.mjs": (
        (),
        "origin-output",
        False,
    ),
    "changes/wordpress-local-preview-v1/browser/local_running_cost_audit.mjs": (
        (),
        "origin-output",
        False,
    ),
    "tests/purchase_support/purchase_paths_browser.mjs": ((), "purchase-paths", False),
    "tests/raos_v2/phase3-public-validation.mjs": (
        ("tests/raos_v2/browser-validation.mjs",),
        "phase3",
        False,
    ),
}


def capture_root(tmp_path, answers, relative, extra):
    root = fake_check_root(tmp_path, answers, name="capture-root")
    for name in (relative, *extra):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    return root


def capture_arguments(root, shape, destination):
    if shape == "preview-browser":
        request = root / "input.json"
        request.write_text(
            json.dumps(
                {
                    "origin": "http://127.0.0.1:41398",
                    "widths": [390],
                    "surfaces": [{"kind": "home", "path": "/"}],
                    "screenshots": str(destination),
                }
            )
        )
        return [str(request)]
    if shape == "origin-output":
        return ["http://127.0.0.1:41398/", str(destination)]
    if shape == "purchase-paths":
        for name in ("input.json", "runtime.json"):
            (root / name).write_text(
                json.dumps({"origin": "http://127.0.0.1:41398", "articles": []})
            )
        return [str(root / "input.json"), str(root / "runtime.json")]
    return [
        "--browser-executable",
        "/usr/bin/busybox",
        "--output",
        "output/playwright/synthetic.json",
    ]


@pytest.mark.parametrize("relative", sorted(CAPTURE_SCRIPTS))
def test_every_browser_capture_of_a_wordpress_page_refuses(tmp_path, relative):
    assert NODE is not None
    extra, shape, _ = CAPTURE_SCRIPTS[relative]
    root = capture_root(tmp_path, [ANSWER_LIVE], relative, extra)
    completed = subprocess.run(
        [NODE, relative, *capture_arguments(root, shape, root / "out")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 69, completed.stdout + completed.stderr
    assert completed.stderr.strip().endswith("WORDPRESS_MCP_PRICE_OVERLAY_LIVE")
    assert "playwright" not in completed.stderr
    assert checks_run(root) == 1
    assert not (root / "out").exists()


@pytest.mark.parametrize("relative", sorted(CAPTURE_SCRIPTS))
def test_every_browser_capture_continues_when_nothing_is_live(tmp_path, relative):
    """The control stops at the missing browser package, after the check has answered."""
    assert NODE is not None
    extra, shape, _ = CAPTURE_SCRIPTS[relative]
    root = capture_root(tmp_path, [NOT_LIVE], relative, extra)
    completed = subprocess.run(
        [NODE, relative, *capture_arguments(root, shape, root / "out")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "PRICE_OVERLAY" not in completed.stderr
    assert completed.returncode != 69
    assert checks_run(root) == 1


@pytest.mark.parametrize("relative", sorted(CAPTURE_SCRIPTS))
def test_only_the_run_bound_preview_captures_into_a_bound_candidate_while_live(
    tmp_path, relative
):
    """One exemption, and only into a candidate whose candidate.json carries a binding.

    Round 9 exempted any destination of the right *name* for five of these scripts; the sweep
    deletes by content, so the rest now refuse wherever they write.
    """
    assert NODE is not None
    extra, shape, exempt = CAPTURE_SCRIPTS[relative]
    root = capture_root(tmp_path, [ANSWER_LIVE], relative, extra)
    inside = bound_candidate(root) / "screenshots"
    inside.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [NODE, relative, *capture_arguments(root, shape, inside)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if exempt:
        assert completed.returncode != 69, completed.stdout + completed.stderr
        assert "PRICE_OVERLAY" not in completed.stderr
        assert checks_run(root) == 0
    else:
        assert completed.returncode == 69, completed.stdout + completed.stderr
        assert completed.stderr.strip().endswith("WORDPRESS_MCP_PRICE_OVERLAY_LIVE")
        assert checks_run(root) == 1


def test_the_run_bound_preview_refuses_a_candidate_directory_with_no_binding(tmp_path):
    """The one exemption is the binding, not the shape of the directory it writes into."""
    assert NODE is not None
    relative = "changes/wordpress-direct-publish-v1/preview-browser.mjs"
    root = capture_root(tmp_path, [ANSWER_LIVE], relative, ())
    inside = (
        write_candidate(root, candidate={"candidate_id": CANDIDATE_ID}) / "screenshots"
    )
    inside.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [NODE, relative, *capture_arguments(root, "preview-browser", inside)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 69, completed.stdout + completed.stderr
    assert completed.stderr.strip().endswith("WORDPRESS_MCP_PRICE_OVERLAY_LIVE")
    assert checks_run(root) == 1


# ---------------------------------------------------------------------------
# The local preview shell recipes (make wordpress-preview-check)
# ---------------------------------------------------------------------------

PREVIEW_SHELL = (
    "changes/wordpress-local-preview-v1/browser/check.sh",
    "changes/wordpress-local-preview-v1/browser/lighthouse_check.sh",
)


@pytest.mark.parametrize("relative", PREVIEW_SHELL)
def test_the_local_preview_shell_checks_before_opening_a_browser(tmp_path, relative):
    """`RAOS_WORDPRESS_PREVIEW_ORIGIN` can name the candidate preview docker, so the recipe
    refuses while values may be published (contract §8)."""
    assert NODE is not None
    root = fake_check_root(tmp_path, [ANSWER_LIVE], name="preview-shell-root")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / relative, target)
    target.chmod(0o755)
    completed = subprocess.run(
        ["/usr/bin/busybox", "sh", relative],
        cwd=root,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PWD": str(root),
            "RAOS_NODE": NODE,
            "RAOS_WORDPRESS_PREVIEW_NODE_BIN": NODE,
            "RAOS_WORDPRESS_PREVIEW_ORIGIN": "http://127.0.0.1:41398",
        },
        timeout=300,
    )
    assert completed.returncode == 69, completed.stdout + completed.stderr
    assert completed.stderr.strip().endswith("WORDPRESS_MCP_PRICE_OVERLAY_LIVE")
    assert checks_run(root) == 1
    assert not (root / "output").exists()


# ---------------------------------------------------------------------------
# The inventory is the repository, not a hand-written list
# ---------------------------------------------------------------------------
#
# Rounds 1-6 kept the guarded paths in literal dicts, so scripts/ks_before_after.py,
# scripts/ks_render_review.py, tests/raos_v2/phase3-public-validation.mjs and three more capture
# scripts survived six sweeps unnoticed. This walk enumerates the repository instead: a file that
# opens a browser, or that reads the owner-direct candidate directory, must either reference a
# guard or carry a reviewed reason here.

# Every extension a capture or fetch tool can be written in, not only the ones in use today:
# a new `.cjs` or `.mts` entry point must be seen by this walk on the day it is added.
SOURCE_SUFFIXES = frozenset(
    {".py", ".mjs", ".js", ".cjs", ".ts", ".mts", ".cts", ".sh", ".bash"}
)
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".secrets",
        ".venv",
        ".worktrees",
        "__pycache__",
        "node_modules",
        "output",
    }
)
# A browser can be reached without importing playwright by name: a persistent context, an
# attach to an already open browser over CDP or its websocket, a pipe, or the packaged CLIs.
BROWSER_MARKERS = re.compile(
    r"require\('playwright'\)|require\(\"playwright\"\)"
    r"|from 'playwright'|from \"playwright\""
    r"|import\('playwright'\)|import\(\"playwright\"\)"
    r"|require\('puppeteer'\)|from 'puppeteer'"
    r"|playwright-core|@playwright/mcp|@playwright/test"
    r"|npx[^\n]{0,80}playwright"
    r"|\b(?:chromium|firefox|webkit)\.launch\("
    r"|launchPersistentContext|connectOverCDP|puppeteer\.connect\("
    r"|remote-debugging-port|remote-debugging-pipe|webSocketDebuggerUrl"
    r"|node_modules/@playwright/cli|node_modules/lighthouse/cli"
)
# The candidate directory is also reached through the publisher's own constants
# (`direct.PRIVATE`, `audit.PRIVATE`) and through the frozen preview themes.
CANDIDATE_MARKERS = re.compile(
    r"\.secrets/wordpress-mcp/owner-direct-v1|OWNER_DIRECT_CANDIDATE_RELATIVE"
    r"|\.secrets/wordpress-direct-preview|PREVIEW_PRIVATE_RELATIVE"
    r"|\.PRIVATE\b"
)
# A page-driving fragment reaches a browser without opening one: it is `eval`ed with a
# Playwright `page` handed in, so it matches none of the markers above while navigating to a
# URL and writing full-page screenshots wherever its caller points it.
PAGE_MARKERS = re.compile(r"page\.screenshot\(|page\.goto\(|context\.newPage\(")
# The third class: a tool that fetches the live site over HTTP and keeps the body or its
# sha256. Both halves are required - naming the site, and a fetch primitive (the repository's
# own bounded transport included) - so the walk sees the readers, not every file that mentions
# the origin. Round 8 left this class to the hand-written table below; it now has its own
# tripwire, and scripts/raos_wordpress_runtime_audit.py is a reader that table never listed.
LIVE_SITE_MARKERS = re.compile(
    r"kurashinoshirube\.com"
    r"|SELF_HOSTED_WORDPRESS_HOST|WORDPRESS_OPERATOR_HOST|PUBLICATION_OPERATOR_HOST"
    r"|PILOT_ORIGIN|publication\.ORIGIN"
)
FETCH_MARKERS = re.compile(
    r"\burlopen\(|build_opener\(|HTTPSConnection\(|HTTPConnection\("
    r"|requests\.(?:get|post)\(|BoundedHttpsTransport"
    r"|\bfetch\(|\bcurl\b|wp_remote_(?:get|post)\("
)
GUARD_MARKERS = re.compile(
    r"refuseWhilePriceOverlayLive|raos_price_overlay_live_check|price_overlay_live_guard"
    r"|refuse_while_price_overlay_live|price_overlay_refusal|price-overlay-live-check"
    r"|price_overlay_live_run_ids"
)

# Reviewed: each of these cannot render or read a live overlay value (contract §8).
UNGUARDED_BY_REVIEW = {
    "python/raos/adapters/rakuten_price_refresh_client.py": (
        "the §5 purge sweep itself: it deletes the candidate directories and never opens a "
        "browser or reaches the site"
    ),
    "scripts/raos_wordpress_price_overlay.py": (
        "the run-bound candidate materializer; every flag-free publisher command that could "
        "call it is refused first (scripts/raos_wordpress_direct_publish.py)"
    ),
    "scripts/check_st1001_public_shell_browser.mjs": (
        "serves its own fixture from a loopback server it started and aborts anything off "
        "that origin"
    ),
    "scripts/check_st1002_public_article_browser.mjs": "same own-fixture loopback server",
    "scripts/check_st1007_public_accessibility_browser.mjs": "same own-fixture loopback server",
    "scripts/check_st1105_admin_acceptance_browser.mjs": "same own-fixture loopback server",
    "tests/purchase_support/reference_price_browser.mjs": (
        "setContent of a synthetic document; it never navigates to an origin"
    ),
    "tests/purchase_support/test_rakuten_price_refresh.py": (
        "the suite that owns the synthetic run and candidate fixtures"
    ),
    "tests/raos_v2/browser-validation.mjs": (
        "CDP helper library with no entry point of its own; the harnesses that use it are "
        "guarded"
    ),
    "tests/reader_measurement_v1/browser.mjs": (
        "every request is fulfilled or aborted locally behind a closed loopback proxy"
    ),
    "tests/reader_measurement_v1/browser_views.mjs": "same fully intercepted simulation",
    "tests/site_editorial_pages/consent_controls.mjs": (
        "setContent of a literal fragment; no navigation"
    ),
    "tests/st1704/test_decision_list_text_resize.py": "renders a tracked theme asset, no origin",
    "tests/st1704/test_header_text_resize.py": "renders a tracked theme asset, no origin",
    "tests/st1704/test_header_without_javascript.py": "renders a tracked theme asset, no origin",
    "tests/st1704/test_home_fragment_navigation.py": "renders a tracked theme asset, no origin",
    "tests/st1704/test_toc_saved_css_compatibility.py": "renders a tracked theme asset, no origin",
    "tests/wordpress_mcp_v1/test_contract.py": "pins a package version string only",
    "tests/purchase_support/purchase_ui_harness.cjs": (
        "setContent of a document the harness builds itself; it never navigates to an origin"
    ),
    "scripts/chatgpt_pro_mcp.sh": (
        "the ChatGPT Pro Playwright MCP launcher: --allowed-origins https://chatgpt.com, so "
        "the browser it starts can reach neither the site nor the candidate preview docker"
    ),
    "scripts/chatgpt_pro_orchestrator.py": (
        "drives that launcher and only that launcher (a wrapper other than "
        "scripts/chatgpt_pro_mcp.sh is refused before the process starts)"
    ),
    "scripts/chatgpt_pro_mcp_runtime/verify_runtime.py": (
        "verifies the pinned @playwright/mcp package tree on disk; it has no subprocess and "
        "starts nothing"
    ),
    "tests/st0101/test_chatgpt_pro_private_runtime.py": (
        "pins that package tree and its lockfile; the browser is never started"
    ),
    "tests/st0101/test_chatgpt_pro_workflow.py": (
        "pins the launcher's configuration (the playwright MCP server stays disabled)"
    ),
    "changes/st-0005/evidence/artifacts/"
    "ff0afaf837c18131a5edc05670f8eb16910cd8a7473524f63e12d593e17b9644-chatgpt_pro_mcp.sh": (
        "a frozen evidence copy of the launcher above; nothing executes it"
    ),
    "changes/st-0005/evidence/artifacts/"
    "742ee4c7d8efda914f75c7851e407558952b77d832f481ee2779af6f72d77446-"
    "test_chatgpt_pro_workflow.py": "a frozen evidence copy of the test above",
    "tests/raos_v2/test_browser_contract.py": (
        "replaces globalThis.fetch with a stub and asserts on the CDP helper's retry; no "
        "browser and no socket"
    ),
    "tests/wordpress_mcp_v1/test_owner_direct_client.py": (
        "asserts the candidate directory is absent under a temporary root; the client it "
        "exercises is a fake"
    ),
    "tests/wordpress_seo_audit_v1/test_incremental.py": (
        "writes its own incremental-preview directory beside PRIVATE under a temporary root; "
        "it never reads the owner-direct candidates"
    ),
    "tests/wordpress_seo_audit_v1/test_incremental_preserved_theme_images.py": (
        "same temporary incremental-preview directory"
    ),
    "changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js": (
        "a page-driving fragment with no entry point of its own: it is evaluated only by "
        "browser/check.sh and browser/lighthouse_check.sh, both of which refuse "
        "unconditionally while values may be live"
    ),
    "scripts/wordpress_public_ui_audit.function.js": (
        "the same shape: evaluated only by scripts/check_wordpress_public_ui_playwright.sh, "
        "which runs the blanket refusal before the browser is started"
    ),
    "tests/wordpress_local_preview/test_contract.py": (
        "asserts on the preview recipe's source text (page.goto('about:blank')); it starts "
        "no browser"
    ),
    "tests/wordpress_local_preview/test_public_ui_audit_contract.py": (
        "asserts on the audit fragment's source text, including its screenshot call"
    ),
    "changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/assets/"
    "reader-measurement.js": (
        "a plugin asset that runs in the reader's own browser and posts to the site's own "
        "endpoint, refusing unless location.origin matches; nothing in this repository "
        "starts it and it reads no rendering"
    ),
    "packages/web-ui/src/decision-support-v2/preview/render_preview.py": (
        "its `fetch(` is an entry in the forbidden-token list it scans rendered HTML for, "
        "and the site name is a netloc equality check; the only urllib import is urlsplit"
    ),
    "python/raos/adapters/self_hosted_editorial_rakuten_capture.py": (
        "refuses any host outside the Rakuten API and image hosts: it reads the price "
        "source, never an injected page"
    ),
    "python/raos/adapters/self_hosted_editorial_source_capture.py": (
        "connects only to a validated target host with a fixed allowed-query table; the site "
        "name is the User-Agent's comparison-policy URL"
    ),
    "python/raos/application/editorial/product_safety_manufacturer_capture.py": (
        "its reviewed endpoint table is empty today, so it fetches nothing; the site name is "
        "again the User-Agent"
    ),
    "python/raos/application/editorial/product_safety_query_capture.py": (
        "refuses any host outside www.recall.caa.go.jp and safe-lite.nite.go.jp"
    ),
    "tests/editorial_measurement_v1/measurement_client_harness.mjs": (
        "defines fetch() as a stub that records the call and resolves {ok:true}"
    ),
    "tests/raos_v2/test_source_import.py": (
        "replaces build_opener with a recorder and asserts the validator's own refusals; no "
        "socket is opened"
    ),
    "tests/raos_v2/test_ui_contracts.py": (
        "`fetch(` is a forbidden token the renderer must strip, and the canonical URLs are "
        "assertions on generated HTML"
    ),
    "tests/st1506_operator/test_client_surface.py": (
        "asserts the launcher script contains neither curl nor wget"
    ),
    "tests/st1506_operator/test_contract.py": "asserts the makefile names no curl",
    "tests/verified_incremental_v1/test_baseline_media.py": (
        "its fetch() is a local fixture function handed to the baseline media planner"
    ),
    "tests/wordpress_local_preview/test_direct_preview.py": (
        "its fetch() are local stubs passed to the product image mirror"
    ),
    "tests/wordpress_mcp_v1/e2e/client.py": (
        "loopback only: main builds site_url as http://127.0.0.1:$RAOS_WORDPRESS_E2E_PORT "
        "and every request goes there; the site name is a Host header for the disposable "
        "container and three assertions on what that container reports"
    ),
    "tests/wordpress_mcp_v1/e2e/run.sh": (
        "curl only against that same loopback port; the site name is the container's own "
        "--url configuration"
    ),
    "tests/wordpress_mcp_v1/e2e/run_owner_direct.py": (
        "its one urlopen is the pinned wordpress-seo plugin zip from downloads.wordpress.org, "
        "sha256-checked before use; the site name is the throwaway container's WP_HOME"
    ),
    "tests/wordpress_seo_audit_v1/test_reader_measurement_runtime.py": (
        "monkeypatches seo.BoundedHttpsTransport with a fake; the fetch( strings are HTML "
        "fixtures the runtime check has to reject"
    ),
    "tests/wordpress_seo_audit_v1/test_runtime_resources.py": (
        "the same: fetch( appears only inside HTML fixtures the resource check must reject"
    ),
}


def files_that_can_reach_an_overlay_value():
    found = {}
    for path in sorted(ROOT.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIPPED_DIRECTORIES for part in relative.parts):
            continue
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        reasons = []
        if BROWSER_MARKERS.search(text):
            reasons.append("browser")
        if CANDIDATE_MARKERS.search(text):
            reasons.append("candidate")
        if PAGE_MARKERS.search(text):
            reasons.append("page")
        if LIVE_SITE_MARKERS.search(text) and FETCH_MARKERS.search(text):
            reasons.append("fetch")
        if reasons:
            found[relative.as_posix()] = (reasons, bool(GUARD_MARKERS.search(text)))
    return found


def test_every_browser_and_candidate_reader_is_guarded_or_reviewed():
    found = files_that_can_reach_an_overlay_value()
    # The page-driving and live-fetch classes take the walk from 50 files to 82; a floor well
    # above the round 8 count catches a marker that stops matching as much as a missing guard.
    assert len(found) >= 78, sorted(found)
    unreviewed = sorted(
        name
        for name, (_, guarded) in found.items()
        if not guarded and name not in UNGUARDED_BY_REVIEW
    )
    assert unreviewed == [], (
        "a file opens a browser or reads the owner-direct candidate directory without the "
        f"contract §8 check: {unreviewed}"
    )


def test_the_reviewed_exceptions_are_all_still_present_and_still_unguarded():
    """A reason left behind after its file was guarded or deleted would hide the next gap."""
    found = files_that_can_reach_an_overlay_value()
    stale = sorted(name for name in UNGUARDED_BY_REVIEW if name not in found)
    assert stale == [], stale
    now_guarded = sorted(
        name for name in UNGUARDED_BY_REVIEW if found[name][1]
    )
    assert now_guarded == [], now_guarded


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/ks_before_after.py",
        "scripts/ks_render_review.py",
        "tests/raos_v2/phase3-public-validation.mjs",
        "changes/wordpress-direct-publish-v1/preview-browser.mjs",
        "changes/wordpress-local-preview-v1/browser/reader_experience_audit.mjs",
        "changes/wordpress-local-preview-v1/browser/local_running_cost_audit.mjs",
        "tests/purchase_support/purchase_paths_browser.mjs",
        "changes/wordpress-local-preview-v1/browser/check.sh",
        "changes/wordpress-local-preview-v1/browser/lighthouse_check.sh",
    ],
)
def test_the_round_seven_additions_stay_guarded(relative):
    """The six paths round 6 missed, plus the local preview recipes, named one by one."""
    assert GUARD_MARKERS.search((ROOT / relative).read_text(encoding="utf-8")), relative


# ---------------------------------------------------------------------------
# The HTTP readers of the live site the walk now sees
# ---------------------------------------------------------------------------
#
# The legacy self-hosted adapters were refused by their CLI's main() only, so an in-process
# importer reached the site unchecked; the two seo-transport audits carried no refusal of their
# own and relied on BoundedHttpsTransport.get. Both are now closed at the point the connection
# is built, where every caller passes.

SYSTEM_TRANSPORTS = {
    "st1703-self-hosted-wordpress": (
        "raos.adapters.self_hosted_wordpress_https",
        "SystemSelfHostedWordPressHttpsConnectionFactory",
        "SELF_HOSTED_WORDPRESS_HOST",
        "SELF_HOSTED_WORDPRESS_PORT",
    ),
    "st1506-wordpress-operator": (
        "raos.adapters.self_hosted_wordpress_operator_https",
        "SystemWordPressOperatorHttpsConnectionFactory",
        "WORDPRESS_OPERATOR_HOST",
        "WORDPRESS_OPERATOR_PORT",
    ),
    "st1704-publication-operator-v2": (
        "raos.adapters.self_hosted_wordpress_publication_operator_https_v2",
        "SystemPublicationOperatorHttpsConnectionFactory",
        "PUBLICATION_OPERATOR_HOST",
        "PUBLICATION_OPERATOR_PORT",
    ),
}


def open_system_transport(name, monkeypatch, calls):
    """Open the production connection factory, with the socket replaced by a recorder."""
    import importlib

    module_name, factory_name, host_name, port_name = SYSTEM_TRANSPORTS[name]
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module.http.client, "HTTPSConnection", recorder(calls, name))
    getattr(module, factory_name)().open(
        host=getattr(module, host_name),
        port=getattr(module, port_name),
        connect_timeout_seconds=module.CONNECT_TIMEOUT_SECONDS,
        tls_context=ssl.create_default_context(),
    )


@pytest.mark.parametrize("name", sorted(SYSTEM_TRANSPORTS))
def test_every_legacy_system_transport_refuses_before_the_socket(
    name, refused, monkeypatch
):
    """The adapter itself refuses, not only the CLI that usually drives it.

    The adapters keep their own failure protocol, so the refusal surfaces as their
    TRANSPORT_REFUSED; what matters here is that no connection is opened.
    """
    calls = []
    with pytest.raises(Exception) as error:  # noqa: PT011 - each adapter's own failure type
        open_system_transport(name, monkeypatch, calls)
    assert calls == [], error.value
    assert "TRANSPORT_REFUSED" in str(error.value), error.value


@pytest.mark.parametrize("name", sorted(SYSTEM_TRANSPORTS))
def test_every_legacy_system_transport_reaches_its_socket_when_nothing_is_live(
    name, not_live, monkeypatch
):
    calls = []
    with pytest.raises(Reached):
        open_system_transport(name, monkeypatch, calls)
    assert calls == [name]


SEO_TRANSPORT_AUDITS = (
    "scripts/raos_wordpress_incremental_seo_audit.py",
    "scripts/raos_wordpress_runtime_audit.py",
)


@pytest.mark.parametrize("relative", SEO_TRANSPORT_AUDITS)
def test_the_seo_transport_audits_refuse_before_they_build_a_transport(relative):
    """Ordering, so deleting the call is caught even though the helper would still match."""
    source = (ROOT / relative).read_text(encoding="utf-8")
    call = "    _refuse_while_price_overlay_live()\n"
    assert source.count(call) == 1, relative
    assert source.index(call) < source.index("seo.BoundedHttpsTransport("), relative


@pytest.mark.parametrize("relative", SEO_TRANSPORT_AUDITS)
def test_the_seo_transport_audits_answer_for_every_run_state(
    relative, tmp_path, monkeypatch
):
    module = _load("raos_seo_transport_audit_" + Path(relative).stem, relative)
    for state, expected in (("live", LIVE), ("unreadable", STATE_INVALID), ("empty", None)):
        directory = tmp_path / state
        directory.mkdir()
        owner = owner_with_state(directory, state)
        monkeypatch.setattr(guard, "OWNER_CHECKOUT", owner)
        monkeypatch.setattr(guard, "REPOSITORY_ROOT", owner)
        if expected is None:
            assert module._refuse_while_price_overlay_live() is None
            continue
        with pytest.raises(module.seo.AuditError) as error:
            module._refuse_while_price_overlay_live()
        assert str(error.value) == expected


# ---------------------------------------------------------------------------
# The paths that carry no price, pinned so they stay that way
# ---------------------------------------------------------------------------


def test_the_baseline_media_fetch_cannot_reach_the_site():
    """Contract §8: it only fetches Rakuten thumbnails, so it has no overlay value to leak."""
    media = _load("raos_wordpress_baseline_media_cli", "scripts/raos_wordpress_baseline_media.py")
    for url in (
        publication.ORIGIN + "/carry-on-suitcase-comparison/",
        publication.ORIGIN + "/wp-json/wp/v2/posts/1",
        "https://thumbnail.image.rakuten.co.jp.evil.invalid/@0_mall/x.jpg",
    ):
        with pytest.raises(Exception) as error:  # noqa: PT011 - the module's own failure type
            media.validate_url(url)
        assert "kurashinoshirube" not in str(error.value)
    media.validate_url("https://thumbnail.image.rakuten.co.jp/@0_mall/a/b.jpg")


def test_the_public_acceptance_report_never_fetches_anything():
    """Contract §8: it reads an export the caller supplies; it has no network primitive."""
    source = (ROOT / "scripts/raos_public_acceptance.py").read_text(encoding="utf-8")
    for primitive in ("urlopen", "build_opener", "HTTPSConnection", "socket", "requests."):
        assert primitive not in source, primitive


def test_the_raos_v2_adversarial_harness_serves_its_own_fixture():
    """It starts a loopback HTTP server and navigates to that; the live site never appears."""
    source = (ROOT / "tests/raos_v2/phase3-public-adversarial.mjs").read_text(encoding="utf-8")
    assert "kurashinoshirube" not in source
    assert "createServer" in source
