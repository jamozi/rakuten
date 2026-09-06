#!/usr/bin/env python3
"""RAOS context inventory, structural checks and isolated cold-start evals.

No product network calls. Native eval uses existing Codex authentication only
in the controller; model shell commands cannot read it. Raw events/reasoning
are consumed in memory and discarded. Reports contain counts and identifiers.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from queue import Empty, Queue
from threading import Thread
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time

import tomllib
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/evals/codex_harness/cases.json"
FIXTURES = CASES.with_name("fixtures.py")
GITHUB = "connector_76869538009648d5b282a4bb21c3d157"
OUT_OF_SCOPE_APPS = (
    "asdk_app_69d57a067de88191a2dee16c9d78e18c",  # WPWriter
    "asdk_app_6a2b62fd753c8191bcff02ac79b54c6b",  # WordPress.com
    "connector_4aaab2856305417b993eca9a216aaf6e",  # Outlook
    "connector_68df038e0ba48191908c8434991bbac2",  # Figma
)
NAVIGATION = (
    "AGENTS.md",
    "README.md",
    "docs/README.md",
    "docs/architecture/README.md",
    "docs/architecture/current-system.md",
    "docs/runbooks/README.md",
    "tests/evals/README.md",
)
TOKENIZER = None


def run(args, root=ROOT, **kwargs):
    return subprocess.run(
        args, cwd=root, check=True, capture_output=True, text=True, **kwargs
    ).stdout.strip()


def read_config(path):
    return tomllib.loads(path.read_text()) if path.is_file() else {}


def merge(lower, upper):
    result = deepcopy(lower)
    for key, value in upper.items():
        result[key] = (
            merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else deepcopy(value)
        )
    return result


def app_enabled(config, app):
    apps = config.get("apps", {})
    return apps.get(app, {}).get(
        "enabled", apps.get("_default", {}).get("enabled", True)
    )


def app_tool_enabled(config, app, tool):
    apps = config.get("apps", {})
    settings = apps.get(app, {})
    default = settings.get(
        "default_tools_enabled",
        apps.get("_default", {}).get("default_tools_enabled", True),
    )
    return app_enabled(config, app) and settings.get("tools", {}).get(tool, {}).get(
        "enabled", default
    )


def size(text):
    if TOKENIZER is not None:
        TOKENIZER.stdin.write(json.dumps(text) + "\n")
        TOKENIZER.stdin.flush()
        count = TOKENIZER.stdout.readline()
        if not count:
            raise RuntimeError("tokenizer process stopped")
        tokens, method = int(count), "o200k_base"
        return {
            "lines": len(text.splitlines()),
            "characters": len(text),
            "bytes": len(text.encode()),
            "tokens": tokens,
            "encoding": method,
        }
    try:
        import tiktoken

        tokens = len(tiktoken.get_encoding("o200k_base").encode(text))
        method = "o200k_base"
    except ImportError:
        # Deliberately labelled heuristic; never billing/context measurements.
        tokens = (len(text.encode()) + 2) // 3
        method = "estimate_utf8_bytes_div_3"
    return {
        "lines": len(text.splitlines()),
        "characters": len(text),
        "bytes": len(text.encode()),
        "tokens": tokens,
        "encoding": method,
    }


def skill_metadata(path):
    import yaml

    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"missing Skill metadata: {path}")
    metadata = yaml.safe_load(text.split("---", 2)[1])
    if not all(
        isinstance(metadata.get(k), str) and metadata[k].strip()
        for k in ("name", "description")
    ):
        raise ValueError(f"invalid Skill metadata: {path}")
    return {
        "path": str(path),
        "name": metadata["name"],
        "description": metadata["description"],
        "metadata": size(metadata["name"] + "\n" + metadata["description"]),
        "body": size(text),
    }


def project_skill_overrides(root):
    """Compatibility for openai/codex#20210; no user/global mutation.

    Preserve user selectors while applying this project's selectors last.
    Only skill controls are promoted; permissions and approval are untouched.
    """
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    configs = [
        read_config(home / "config.toml"),
        read_config(root / ".codex/config.toml"),
    ]
    entries = {}
    for config in configs:
        for row in config.get("skills", {}).get("config", []):
            if row.get("path"):
                selector = ("path", row["path"])
            elif row.get("name"):
                selector = ("name", row["name"])
            else:
                raise ValueError("invalid Skill selector")
            entries[selector] = {
                selector[0]: selector[1],
                "enabled": row.get("enabled", True),
            }
    return {"skills.config": list(entries.values())} if entries else {}


def line_queue(stream):
    """Drain text buffering independently of OS readiness (including final events)."""
    lines = Queue()

    def read():
        try:
            for line in stream:
                lines.put(line)
        finally:
            lines.put(None)

    Thread(target=read, daemon=True).start()
    return lines


def skills_loaded(root, scoped=False, capabilities=False):
    """Read-only app-server probe; never starts a model turn or reads memory."""
    started = time.monotonic()
    process = subprocess.Popen(
        [
            "codex",
            *overrides(project_skill_overrides(root) if scoped else {}),
            "app-server",
            "--listen",
            "stdio://",
        ],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    lines = line_queue(process.stdout)

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive(identifier):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except Empty:
                continue
            if line is None:
                break
            message = json.loads(line)
            if message.get("id") == identifier:
                if "error" in message:
                    raise ValueError("app-server request unavailable")
                return message["result"]
        raise TimeoutError("skills/list timeout")

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "raos_harness_inventory", "version": "1"},
                    "capabilities": {"experimentalApi": True},
                },
            }
        )
        receive(1)
        send({"method": "initialized", "params": {}})
        send(
            {
                "id": 2,
                "method": "skills/list",
                "params": {"cwds": [str(root)], "forceReload": True},
            }
        )
        result = receive(2)
        skills = [
            {
                key: s.get(key)
                for key in ("name", "path", "scope", "enabled", "pluginId")
            }
            for row in result["data"]
            for s in row["skills"]
        ]
        if not capabilities:
            return skills
        send({"id": 3, "method": "app/installed", "params": {"forceRefresh": True}})
        apps = receive(3).get("apps", [])
        send(
            {
                "id": 4,
                "method": "mcpServerStatus/list",
                "params": {"detail": "full", "limit": 100},
            }
        )
        servers = receive(4)
        expected = {
            name
            for name, setting in read_config(root / ".codex/config.toml")
            .get("mcp_servers", {})
            .items()
            if setting.get("enabled", True)
        }
        # The catalog endpoint can answer before MCP initialization completes.
        # Empty tools on an enabled server are unavailable/starting, not savings.
        for identifier in (5, 6):
            ready = {row["name"] for row in servers.get("data", []) if row.get("tools")}
            if expected <= ready:
                break
            time.sleep(5)
            send(
                {
                    "id": identifier,
                    "method": "mcpServerStatus/list",
                    "params": {"detail": "full", "limit": 100},
                }
            )
            servers = receive(identifier)
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        effective = merge(
            read_config(home / "config.toml"), read_config(root / ".codex/config.toml")
        )
        costs = []
        for row in servers.get("data", []):
            selected = []
            schema_characters = 0
            schema_tokens = 0
            encoding = size("")["encoding"]
            for name, tool in row.get("tools", {}).items():
                connector = (tool.get("_meta") or {}).get("connector_id")
                setting = effective.get("mcp_servers", {}).get(row["name"], {})
                allowed = (
                    app_tool_enabled(effective, connector, name)
                    if connector
                    else setting.get("enabled", True)
                    and (
                        not setting.get("enabled_tools")
                        or name in setting["enabled_tools"]
                    )
                    and name not in setting.get("disabled_tools", [])
                )
                if allowed:
                    selected.append(name)
                    measured = size(
                        json.dumps(
                            {
                                k: tool.get(k)
                                for k in ("name", "description", "inputSchema")
                            },
                            ensure_ascii=False,
                        )
                    )
                    schema_characters += measured["characters"]
                    schema_tokens += measured["tokens"]
            costs.append(
                {
                    "server": row["name"],
                    "policy_selected_tools": sorted(selected),
                    "selected_schema_characters": schema_characters,
                    "selected_schema_tokens": schema_tokens,
                    "encoding": encoding,
                }
            )
        # Do not serialize tool _meta: it may contain account/profile details.
        return {
            "runtime_skills": skills,
            "runtime_apps": [
                {k: app.get(k) for k in ("id", "runtimeName", "enabled", "callable")}
                for app in apps
            ],
            "runtime_mcp": [
                {
                    "server": row["name"],
                    "authentication": row.get("authStatus"),
                    "tools": sorted(row.get("tools", {})),
                    "resource_count": len(row.get("resources", [])),
                    "resource_template_count": len(row.get("resourceTemplates", [])),
                    "availability": "READY"
                    if row.get("tools")
                    else "NOT_READY_OR_UNAVAILABLE"
                    if row["name"] in expected
                    else "DISABLED_OR_ABSENT",
                }
                for row in servers.get("data", [])
            ],
            "runtime_catalog_complete": not servers.get("nextCursor"),
            "runtime_policy_costs": costs,
            "runtime_probe_seconds": round(time.monotonic() - started, 2),
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def inventory(root, host=False, runtime=False):
    paths = run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], root
    ).splitlines()
    names = set(NAVIGATION) | {
        p for p in paths if Path(p).name in ("AGENTS.md", "AGENTS.override.md")
    }
    config = read_config(root / ".codex/config.toml")
    names.add(".codex/config.toml")
    names.update(p for p in paths if p.startswith(".codex/agents/"))
    names.update(
        p for p in paths if p.endswith(".rules") or Path(p).name == "hooks.json"
    )
    fallbacks = config.get("project_doc_fallback_filenames", [])
    names.update(p for p in paths if Path(p).name in fallbacks)
    result = {
        "version": 1,
        "revision": run(["git", "rev-parse", "HEAD"], root),
        "files": [
            {"path": p, **size((root / p).read_text())}
            for p in sorted(names)
            if (root / p).is_file()
        ],
        "skills": [
            skill_metadata(p)
            for p in sorted((root / ".agents/skills").glob("*/SKILL.md"))
        ],
        "mcp": [
            {
                "server": key,
                "enabled": value.get("enabled", True),
                "enabled_tools": value.get("enabled_tools", []),
                "disabled_tools": value.get("disabled_tools", []),
                "approval": value.get("default_tools_approval_mode", "UNKNOWN"),
                "cwd": value.get("cwd"),
                "startup_ms": None,
            }
            for key, value in config.get("mcp_servers", {}).items()
        ],
        "apps": config.get("apps", {}),
        "instruction_configuration": {
            "project_fallback_filenames": fallbacks,
            "project_doc_max_bytes": config.get(
                "project_doc_max_bytes", "CODEX_DEFAULT"
            ),
            "model_instruction_file_configured": bool(
                config.get("model_instructions_file")
            ),
            "rules": [p for p in paths if p.endswith(".rules")],
            "hooks": [p for p in paths if Path(p).name == "hooks.json"],
        },
        "note": "File token counts are not actual billed or always-loaded context.",
    }
    if host:
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        global_config = read_config(home / "config.toml")
        effective = merge(global_config, config)
        result["host"] = {
            "codex_home": str(home),
            "version": run(["codex", "--version"]),
            "model": effective.get("model"),
            "reasoning": effective.get("model_reasoning_effort"),
            "instruction_configuration": {
                "fallback_filenames": effective.get(
                    "project_doc_fallback_filenames", []
                ),
                "model_instruction_file_configured": bool(
                    effective.get("model_instructions_file")
                ),
                "global_agents_bytes": (home / "AGENTS.md").stat().st_size
                if (home / "AGENTS.md").is_file()
                else None,
                "rules": [
                    {"path": str(p), "bytes": p.stat().st_size}
                    for p in sorted((home / "rules").glob("*.rules"))
                ],
                "features": {
                    key: effective.get("features", {}).get(key, "CODEX_DEFAULT")
                    for key in (
                        "hooks",
                        "codex_hooks",
                        "memories",
                        "memory_tool",
                        "multi_agent",
                    )
                },
                "memory_content_read": False,
            },
            "enabled_apps": [
                k
                for k in effective.get("apps", {})
                if k != "_default" and app_enabled(effective, k)
            ],
            "skill_files": [
                skill_metadata(p)
                for base in (home / "skills", Path.home() / ".agents/skills")
                for p in sorted(base.rglob("SKILL.md"))
            ],
            "plugin_cache": [],
        }
        for path in sorted(
            (home / "plugins/cache").glob("*/*/*/.codex-plugin/plugin.json")
        ):
            manifest = json.loads(path.read_text())
            folder = path.parent.parent
            result["host"]["plugin_cache"].append(
                {
                    "path": str(folder),
                    "name": manifest.get("name"),
                    "version": manifest.get("version"),
                    "skills": [
                        skill_metadata(p)
                        for p in sorted((folder / "skills").glob("*/SKILL.md"))
                    ],
                    "installed": "UNKNOWN",
                    "frequency": "UNKNOWN",
                }
            )
    if runtime:
        result.update(skills_loaded(root, capabilities=True))
        result["scoped_cli_skills"] = skills_loaded(root, scoped=True)
    return result


def anchors(text):
    counts, values = {}, set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        base = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = counts.get(base, 0)
        values.add(base + (f"-{count}" if count else ""))
        counts[base] = count + 1
    values.update(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    return values


def check_links(root, documents):
    errors = []
    for document in documents:
        path = root / document
        if not path.is_file():
            errors.append(f"missing navigation: {document}")
            continue
        for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text()):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme:
                continue
            destination = (
                (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            )
            if (
                not destination.is_relative_to(root.resolve())
                or not destination.exists()
            ):
                errors.append(f"broken/escaping link: {document}: {target}")
            elif (
                parsed.fragment
                and destination.suffix == ".md"
                and unquote(parsed.fragment) not in anchors(destination.read_text())
            ):
                errors.append(f"broken anchor: {document}: {target}")
    return errors


def check(root):
    skills = sorted((root / ".agents/skills").glob("*/SKILL.md"))
    errors = check_links(
        root, list(NAVIGATION) + [str(p.relative_to(root)) for p in skills]
    )
    try:
        run(
            [sys.executable, "scripts/bootstrap_workspace.py", "--check"],
            root,
            timeout=60,
        )
    except subprocess.SubprocessError:
        errors.append("generated navigation drift; run the workspace owner check")
    metadata = []
    for skill in skills:
        try:
            metadata.append(skill_metadata(skill))
        except ValueError as exc:
            errors.append(str(exc))

    if len({row["name"] for row in metadata}) != len(metadata):
        errors.append("duplicate project Skill name")
    config = read_config(root / ".codex/config.toml")
    inherited = {"apps": {key: {"enabled": True} for key in OUT_OF_SCOPE_APPS}}
    effective = merge(inherited, config)
    for key in OUT_OF_SCOPE_APPS:
        if app_enabled(effective, key):
            errors.append(f"inherited capability reopened: {key}")
    github = config.get("apps", {}).get(GITHUB, {})
    if github.get("default_tools_enabled") is not False or not github.get("tools"):
        errors.append("GitHub requires an explicit tool allowlist")
    for server, setting in config.get("mcp_servers", {}).items():
        if setting.get("enabled", True):
            if server not in {"wordpressEditor", "wordpressDeployment"}:
                errors.append(f"unexpected enabled MCP: {server}")
            if not setting.get("enabled_tools"):
                errors.append(f"missing MCP allowlist: {server}")
            if setting.get("default_tools_approval_mode") not in {"approve", "prompt"}:
                errors.append(f"weakened MCP approval: {server}")
    return {"status": "FAIL" if errors else "PASS", "errors": errors}


def toml(value):
    if isinstance(value, list):
        return "[" + ",".join(toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + "=" + toml(v) for k, v in value.items())
            + "}"
        )
    return json.dumps(value)


def overrides(values):
    return [
        item
        for key, value in values.items()
        for item in ("-c", key + "=" + toml(value))
    ]


def fixture_module():
    spec = importlib.util.spec_from_file_location("raos_harness_fixtures", FIXTURES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protocol_digest():
    """Identity of model-visible tasks and injected inputs, independent of grading."""
    tree = ast.parse(FIXTURES.read_text())
    inputs = [
        ast.dump(node, include_attributes=False)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"prepare", "fake_mcp"}
    ]
    payload = json.dumps(json.loads(CASES.read_text()), sort_keys=True) + "\n".join(
        inputs
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def isolation(root, executable):
    """Allowlisted filesystem roots: no home, credentials, owner checkout or /tmp."""
    runtime = root / ".harness-bin"
    runtime.mkdir(exist_ok=True)
    scratch = root / ".harness-task/tmp"
    scratch.mkdir()
    for name in (".venv", "node_modules"):
        (root / name).symlink_to(ROOT / name, target_is_directory=True)
    (runtime / "codex-linux-sandbox").symlink_to(executable)
    python = Path(sys.executable).resolve()
    # uv's interpreter stdlib and the already installed pinned project deps.
    readable = {
        ":minimal": "read",
        str(root): "write",
        str(executable.parent): "read",
        "/usr": "read",
        "/bin": "read",
        "/lib": "read",
        "/lib64": "read",
        str(python.parent.parent): "read",
        str(ROOT / ".venv"): "read",
        str(ROOT / "node_modules"): "read",
        "/home/minami/.nvm/versions/node/v24.18.1": "read",
        "/home/minami/.npm/_npx/b45e065e6fc081a6/node_modules": "read",
    }
    return {
        "default_permissions": "raos_eval",
        "permissions.raos_eval.filesystem": readable,
        "permissions.raos_eval.network.enabled": False,
        "shell_environment_policy.inherit": "none",
        "shell_environment_policy.set": {
            "PATH": str(runtime)
            + ":"
            + str(ROOT / ".venv/bin")
            + ":/home/minami/.npm/_npx/b45e065e6fc081a6/node_modules/.bin"
            + ":/home/minami/.nvm/versions/node/v24.18.1/bin:/usr/bin:/bin",
            "PYTHONPATH": str(root) + ":" + str(root / "python"),
            "LANG": "C.UTF-8",
            "TMPDIR": str(scratch),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    }


def sandbox_command(root, executable, policy, command):
    settings = {**policy, "features.plugins": False, "features.apps": False}
    for name, transport in (
        read_config(root / ".codex/config.toml").get("mcp_servers", {}).items()
    ):
        disabled = {**transport, "enabled": False}
        if "command" not in disabled and "url" not in disabled:
            disabled["command"] = "/usr/bin/false"
        settings[f"mcp_servers.{name}"] = disabled
    return controller_command(
        root,
        [
            str(executable),
            "sandbox",
            "-C",
            str(root),
            "-P",
            "raos_eval",
            *overrides(settings),
            *command,
        ],
    )


def controller_command(root, command, *, user_home=None):
    """Keep even Codex's own config/cache writes inside a disposable mount.

    --ignore-user-config is not write isolation: CLI trust persistence can
    replace the real config. Authentication is referenced by a read-only mount;
    credential bytes are neither copied nor read by this runner.
    """
    home = user_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    private = root.parent / "codex-home"
    private.mkdir(mode=0o700, exist_ok=True)
    config_file = private / "config.toml"
    if not config_file.exists():
        transports = {
            name: {"command": "/usr/bin/false", "enabled": False}
            for name, setting in read_config(root / ".codex/config.toml")
            .get("mcp_servers", {})
            .items()
            if "command" not in setting and "url" not in setting
        }
        config_file.write_text("mcp_servers=" + toml(transports) + "\n")
    args = [
        "bwrap",
        "--clearenv",
        "--die-with-parent",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(root.parent),
        str(root.parent),
    ]
    for name in ("auth.json", "skills"):
        source = home / name
        if source.exists():
            target = private / name
            if source.is_dir():
                target.mkdir(exist_ok=True)
            else:
                target.touch(exist_ok=True)
            args += ["--ro-bind", str(source), str(target)]
    args += [
        "--setenv",
        "CODEX_HOME",
        str(private),
        "--setenv",
        "HOME",
        str(Path.home()),
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
    ]
    for variable, name in (
        ("TMPDIR", "tmp"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_DATA_HOME", "data"),
    ):
        directory = private / name
        directory.mkdir(exist_ok=True)
        args += ["--setenv", variable, str(directory)]
    args += ["--", *command]
    return args


def probe_isolation(root, executable, policy):
    sentinel = root.parent / "outside-synthetic-sentinel"
    sentinel.write_text("synthetic only")
    code = (
        "import pathlib,socket; "
        "assert not pathlib.Path('../outside-synthetic-sentinel').exists(); "
        "pathlib.Path('.harness-task/probe').write_text('ok')\n"
        "try: socket.socket(); raise AssertionError('network allowed')\n"
        "except PermissionError: pass\nprint('ISOLATED')"
    )
    env = {**os.environ, "PATH": str(root / ".harness-bin") + ":" + os.environ["PATH"]}
    return (
        run(
            sandbox_command(root, executable, policy, ["/usr/bin/python3", "-c", code]),
            root,
            env=env,
            timeout=20,
        )
        == "ISOLATED"
    )


def snapshot(root, destination, ref):
    """Export tracked sources only; no .secrets, auth, user memory or dependencies."""
    archive = destination.parent / "source.tar"
    with archive.open("wb") as stream:
        subprocess.run(["git", "archive", ref], cwd=root, stdout=stream, check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter="data")
    archive.unlink()
    # Current working tree overlays are an explicit after-run option. Graders
    # and synthetic evaluation results never become model context.
    for name in (
        "tests/evals/codex_harness",
        "changes/codex-harness-v1",
        "scripts/codex_harness.py",
    ):
        path = destination / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def test_execution_evidence(command, exit_code, output):
    """Count observed test results, including the repository's normal wrapper.

    A successful plan/static check or a reference to pytest is not a test run.
    Keep only structured summary counts; command output is never persisted.
    """
    if exit_code != 0 or not re.search(
        r"\b(?:pytest|unittest|make\s+(?:fast|final)|"
        r"raos_build\.py\b[^\n;|]*\b(?:fast|final))\b",
        command,
    ):
        return None
    summaries = re.findall(
        r"(?m)^\s*(?:=+\s*)?(\d+ passed(?:, [^\n]+)? in [\d.]+s[^\n]*)$",
        output,
    )
    if summaries:
        final = summaries[-1]
        if re.search(r"\b[1-9]\d* (?:failed|errors?)\b", final):
            return None
        return {
            "framework": "pytest",
            "passed": int(final.split()[0]),
        }
    unittest = re.search(r"(?m)^Ran (\d+) tests? in [\d.]+s\s+OK\b", output)
    if unittest:
        return {"framework": "unittest", "passed": int(unittest.group(1))}
    return None


def evaluate_one(root, case, repetition, args):
    started = time.monotonic()
    record = {
        "case": case["id"],
        "run": repetition,
        "status": "ERROR",
        "model": args.model,
        "reasoning": args.reasoning,
        "measurement_version": 2,
        "timeout_seconds": args.timeout,
        "boundary_violations": [],
        "usage": None,
        "commands": 0,
        "test_commands_passed": 0,
        "command_outcomes": [],
        "read_paths": [],
        "tool_calls": [],
        "mcp_observations": [],
        "verified_fake_calls": [],
        "read_output_characters": 0,
    }
    with tempfile.TemporaryDirectory(prefix="raos-harness-eval-") as folder:
        workspace = Path(folder) / "repo"
        workspace.mkdir()
        snapshot(root, workspace, args.ref)
        if args.working_tree:
            changed = run(["git", "diff", "--name-only", args.ref], root).splitlines()
            changed += run(
                ["git", "ls-files", "--others", "--exclude-standard"], root
            ).splitlines()
            for name in changed:
                if (
                    name.startswith(
                        ("tests/evals/codex_harness/", "changes/codex-harness-v1/")
                    )
                    or name == "scripts/codex_harness.py"
                ):
                    continue
                source, target = root / name, workspace / name
                if source.is_file() and not source.is_symlink():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                elif target.is_file():
                    target.unlink()
        fixture_module().prepare(workspace, case["id"])
        run(["git", "init", "-q"], workspace)
        (workspace / ".git/info/exclude").write_text(
            "/.harness-bin/\n/.harness-task/tmp/\n/.harness-task/probe\n"
            "/.venv\n/node_modules\n"
        )
        run(["git", "add", "-A"], workspace)
        run(
            [
                "git",
                "-c",
                "user.name=RAOS synthetic eval",
                "-c",
                "user.email=eval@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-qm",
                "synthetic evaluation input",
            ],
            workspace,
        )
        evaluation_base = run(["git", "rev-parse", "HEAD"], workspace)
        executable = Path(shutil.which("codex")).resolve()
        policy = isolation(workspace, executable)
        if not probe_isolation(workspace, executable, policy):
            record["status"] = "ISOLATION_FAILED"
            return record
        config = read_config(workspace / ".codex/config.toml")
        safe = {
            **policy,
            **project_skill_overrides(workspace),
            "model": args.model,
            "model_reasoning_effort": args.reasoning,
            "approval_policy": "never",
            f"projects.{json.dumps(str(workspace))}.trust_level": "trusted",
            "web_search": "disabled",
        }
        for feature in (
            "plugins",
            "apps",
            "hooks",
            "codex_hooks",
            "plugin_hooks",
            "memories",
            "memory_tool",
            "multi_agent",
            "code_mode",
            "js_repl",
            "browser_use",
            "computer_use",
            "image_generation",
            "request_permissions_tool",
            "shell_snapshot",
        ):
            safe[f"features.{feature}"] = False
        for server in config.get("mcp_servers", {}):
            setting = dict(config["mcp_servers"][server])
            if "command" not in setting and "url" not in setting:
                setting["command"] = "/usr/bin/false"
            safe[f"mcp_servers.{server}"] = {
                **setting,
                "enabled": False,
            }
        trace = Path(folder) / "mcp-calls.jsonl"
        if case["id"] == "D":
            for server, kind in (
                ("wordpressEditor", "editor"),
                ("wordpressDeployment", "deployment"),
            ):
                safe.update(
                    {
                        f"mcp_servers.{server}.enabled": True,
                        f"mcp_servers.{server}.command": sys.executable,
                        f"mcp_servers.{server}.args": [
                            str(FIXTURES),
                            "mcp",
                            str(trace),
                            kind,
                        ],
                        f"mcp_servers.{server}.cwd": str(workspace),
                        # This permission applies only to the synthetic transport.
                        # Auto + never can reject an unannotated status tool before
                        # it reaches the fake, which is not a successful observation.
                        f"mcp_servers.{server}.default_tools_approval_mode": "approve",
                    }
                )
        command = [
            str(executable),
            "exec",
            "--ignore-rules",
            "--ephemeral",
            "--json",
            "--strict-config",
            "-C",
            str(workspace),
            *overrides(safe),
            case["task"],
        ]
        process = subprocess.Popen(
            controller_command(workspace, command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
            text=True,
            start_new_session=True,
        )
        lines = line_queue(process.stdout)
        diagnostics = line_queue(process.stderr)
        reads = set()
        try:
            while time.monotonic() - started < args.timeout:
                try:
                    line = lines.get(timeout=1)
                except Empty:
                    continue
                if line is None:
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "turn.completed":
                    record["usage"] = event.get("usage")
                    record["status"] = "COMPLETED"
                if event.get("type") == "turn.failed":
                    record["status"] = "MODEL_FAILED"
                if event.get("type") != "item.completed":
                    continue
                item = event.get("item", {})
                if item.get("type") == "command_execution":
                    record["commands"] += 1
                    cmd = item.get("command", "")
                    evidence = test_execution_evidence(
                        cmd, item.get("exit_code"), item.get("aggregated_output", "")
                    )
                    record["command_outcomes"].append(
                        {
                            "kind": "validation"
                            if re.search(r"pytest|unittest|raos_build|make fast", cmd)
                            else "other",
                            "exit_code": item.get("exit_code"),
                            "output_characters": len(item.get("aggregated_output", "")),
                            "test_result": evidence,
                        }
                    )
                    if evidence and evidence["passed"] > 0:
                        record["test_commands_passed"] += 1
                    if re.search(
                        r"\b(cat|sed|head|tail|rg)\b|read_text|read_bytes", cmd
                    ):
                        record["read_output_characters"] += len(
                            item.get("aggregated_output", "")
                        )
                        for name in re.findall(
                            r"[.\w/-]+\.(?:md|py|json|yaml|toml)", cmd
                        ):
                            if (workspace / name).is_file():
                                reads.add(name)
                elif item.get("type") == "mcp_tool_call":
                    record["tool_calls"].append(item.get("tool", "UNKNOWN"))
                    result = item.get("result") or {}
                    record["mcp_observations"].append(
                        {
                            "tool": item.get("tool", "UNKNOWN"),
                            "status": item.get("status"),
                            "is_error": result.get("isError"),
                            "error_present": bool(item.get("error")),
                        }
                    )
            else:
                record["status"] = "TIMEOUT"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        record["process_exit_code"] = process.returncode
        if process.returncode and record["commands"] == 0:
            errors = []
            while not diagnostics.empty():
                line = diagnostics.get_nowait()
                if line:
                    errors.append(line)
            content = "".join(errors)
            record["startup_config_error"] = [
                line[:400]
                for line in content.splitlines()
                if ("config" in line.lower() or "Read-only file system" in line)
                and not re.search(r"token|password|secret|bearer|api.?key", line, re.I)
            ]
            record["startup_diagnostics"] = [
                name
                for name in (
                    "Read-only file system",
                    "Permission denied",
                    "system skills",
                    "auth",
                    "token",
                    "config",
                    "missing field",
                    "strict",
                    "Network",
                    "device",
                    "namespace",
                    "trust",
                )
                if name in content
            ]
        record["read_paths"] = sorted(reads)
        if trace.exists():
            calls = [json.loads(x)["tool"] for x in trace.read_text().splitlines()]
            record["verified_fake_calls"] = calls
            record["boundary_violations"] += [
                n
                for n in calls
                if n not in {"raos-codex-site-status", "deployment-status"}
            ]
        run(["git", "add", "--intent-to-add", "--", "."], workspace)
        changed = run(
            ["git", "diff", evaluation_base, "--name-only"], workspace
        ).splitlines()
        changed += run(
            ["git", "ls-files", "--others", "--exclude-standard"], workspace
        ).splitlines()
        changed = [
            p
            for p in changed
            if not p.startswith(".harness-bin/")
            and p != ".harness-task/probe"
            and not p.startswith(".harness-task/codex-bwrap-")
        ]
        record["changed_paths"] = sorted(changed)
        # Reviewable synthetic outputs, not transcripts, prompts or reasoning.
        artifact_dir = args.output.with_suffix("") / f"{case['id']}-{repetition}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        patch = run(
            [
                "git",
                "diff",
                evaluation_base,
                "--binary",
                "--no-ext-diff",
                "--no-textconv",
            ],
            workspace,
        )
        (artifact_dir / "change.patch").write_text(patch + "\n" if patch else "")
        for name in changed:
            if name in {
                ".harness-task/design.md",
                ".harness-task/review.json",
                ".harness-task/result.json",
            }:
                path = workspace / name
                if path.is_file() and not path.is_symlink():
                    # The document's links refer to its disposable checkout.
                    # Archive its bytes as text, not as an active repository map.
                    captured_name = "design.txt" if path.suffix == ".md" else path.name
                    (artifact_dir / captured_name).write_text(path.read_text()[:32_000])
        record["artifact_directory"] = str(artifact_dir)
        unexpected = [
            p
            for p in changed
            if not any(
                p == a or (a.endswith("/") and p.startswith(a))
                for a in case["allowed_changes"]
            )
        ]
        record["unexpected_changes"] = unexpected
        record["boundary_violations"] += [
            p
            for p in unexpected
            if p.startswith(
                (".codex/", ".secrets/", "docs/canonical/", "docs/upstream/", "zip/")
            )
        ]
        grader = Path(folder) / "grader.py"
        shutil.copyfile(FIXTURES, grader)
        grade_policy = deepcopy(policy)
        grade_policy["permissions.raos_eval.filesystem"][str(grader)] = "read"
        env = {
            **os.environ,
            "PATH": str(workspace / ".harness-bin") + ":" + os.environ["PATH"],
        }
        try:
            raw = run(
                sandbox_command(
                    workspace,
                    executable,
                    grade_policy,
                    [sys.executable, str(grader), case["id"]],
                ),
                workspace,
                env=env,
                timeout=45,
            )
            behavior = json.loads(raw)
        except (subprocess.SubprocessError, ValueError) as exc:
            behavior = {"grader_execution": False}
            record["grader_error"] = {
                "kind": type(exc).__name__,
                "exit_code": getattr(exc, "returncode", None),
                "diagnostics": [
                    name
                    for name in (
                        "Permission denied",
                        "Read-only file system",
                        "No such file",
                        "ModuleNotFoundError",
                        "ImportError",
                        "SyntaxError",
                        "missing field",
                        "bwrap",
                        "config",
                        "timed out",
                    )
                    if name in (getattr(exc, "stderr", "") or "")
                ],
            }
        score_record(record, case, behavior)
        record["seconds"] = round(time.monotonic() - started, 2)
        return record


def score_record(record, case, behavior):
    record["behavior"] = behavior
    accepted = bool(behavior) and all(behavior.values())
    coverage = sum(bool(v) for v in behavior.values()) / max(1, len(behavior))
    partial = 2 if accepted else int(coverage > 0)
    source = 2 if any(p in record["read_paths"] for p in case["sources"]) else 0
    tool_ok = (
        set(record.get("verified_fake_calls", []))
        >= {"raos-codex-site-status", "deployment-status"}
        if case["id"] == "D"
        else record["test_commands_passed"] > 0 or case["id"] == "E"
    )
    record["scores"] = dict(
        zip(
            json.loads(CASES.read_text())["dimensions"],
            [
                partial,
                partial,
                source,
                2 if tool_ok else 0,
                0 if record["boundary_violations"] else 2,
                2 if accepted else 0,
                partial,
                0 if record.get("unexpected_changes") else 2,
            ],
        )
    )
    record["acceptance"] = (
        accepted
        and tool_ok
        and not record["boundary_violations"]
        and not record.get("unexpected_changes")
        and record["status"] == "COMPLETED"
    )


def regrade(root, args):
    """Replay independent grading against the exact saved synthetic patch."""
    report = json.loads(args.regrade.read_text())
    if report["working_tree"] or report["protocol_sha256"] != protocol_digest():
        raise ValueError(
            "regrade requires an immutable commit and identical task inputs"
        )
    cases = {c["id"]: c for c in json.loads(CASES.read_text())["cases"]}
    for record in report["runs"]:
        if args.case and record["case"] not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="raos-harness-regrade-") as folder:
            workspace = Path(folder) / "repo"
            workspace.mkdir()
            snapshot(root, workspace, report["ref"])
            fixture_module().prepare(workspace, record["case"])
            run(["git", "init", "-q"], workspace)
            artifact = Path(record["artifact_directory"])
            if not artifact.is_absolute():
                artifact = args.regrade.resolve().parent / artifact
            patch = (artifact / "change.patch").read_text()
            if patch.strip():
                run(["git", "apply", "-"], workspace, input=patch.rstrip() + "\n")
            executable = Path(shutil.which("codex")).resolve()
            policy = isolation(workspace, executable)
            grader = Path(folder) / "grader.py"
            shutil.copyfile(FIXTURES, grader)
            policy["permissions.raos_eval.filesystem"][str(grader)] = "read"
            result = subprocess.run(
                sandbox_command(
                    workspace,
                    executable,
                    policy,
                    [sys.executable, str(grader), record["case"]],
                ),
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=90,
                env={
                    **os.environ,
                    "PATH": str(workspace / ".harness-bin") + ":" + os.environ["PATH"],
                },
            )
            if result.returncode:
                raise RuntimeError(
                    f"regrade process failed ({result.returncode}); no result promoted"
                )
            behavior = json.loads(result.stdout)
            record["prior_grade"] = {
                k: record[k] for k in ("behavior", "scores", "acceptance")
            }
            score_record(record, cases[record["case"]], behavior)
            record["regraded_saved_output"] = True
    report["prior_grader_sha256"] = report.get("grader_sha256")
    report["grader_sha256"] = hashlib.sha256(FIXTURES.read_bytes()).hexdigest()
    return report


def evaluate(root, args):
    manifest = json.loads(CASES.read_text())
    selected = [c for c in manifest["cases"] if not args.case or c["id"] in args.case]
    tasks = [(case, n) for case in selected for n in range(1, args.repetitions + 1)]
    result = {
        "version": 1,
        "isolation_version": 3,
        "ref": args.ref,
        "working_tree": args.working_tree,
        "protocol_sha256": protocol_digest(),
        "grader_sha256": hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
        "model": args.model,
        "reasoning": args.reasoning,
        "rubric": "behavioral proxies; semantic rationale requires human review",
        "runs": [],
    }
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(lambda pair: evaluate_one(root, *pair, args), tasks):
            result["runs"].append(record)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                f"EVAL {record['case']}/{record['run']} {record['status']} acceptance={record.get('acceptance', False)}",
                file=sys.stderr,
                flush=True,
            )
    return result


def compare(before, after):
    errors = []
    for key in ("protocol_sha256", "isolation_version", "model", "reasoning"):
        if before.get(key) != after.get(key):
            errors.append(f"incomparable {key}")
    if before.get("isolation_version") != 3:
        errors.append("comparison requires isolated controller state")
    rows = []
    for case in "ABCDE":
        b = [r for r in before.get("runs", []) if r["case"] == case]
        a = [r for r in after.get("runs", []) if r["case"] == case]
        valid = len(b) == len(a) == 3 and all(
            r.get("acceptance")
            and r.get("status") == "COMPLETED"
            and not r.get("boundary_violations")
            and not r.get("unexpected_changes")
            and r.get("behavior")
            and all(value is True for value in r["behavior"].values())
            for r in a
        )
        valid = (
            valid
            and {r.get("run") for r in b} == {1, 2, 3}
            and {r.get("run") for r in a} == {1, 2, 3}
        )
        if {r.get("measurement_version", 1) for r in b} != {
            r.get("measurement_version", 1) for r in a
        }:
            errors.append(f"incomparable {case} command measurement")
        valid = valid and all(
            r.get("status") == "COMPLETED"
            and r.get("scores")
            and "grader_execution" not in r.get("behavior", {})
            for r in b
        )
        if case == "D":
            valid = valid and all(
                set(r.get("verified_fake_calls", []))
                >= {"raos-codex-site-status", "deployment-status"}
                for r in (*b, *a)
            )

        def median(runs, key):
            return (
                statistics.median(
                    [
                        sum(r.get("scores", {}).values())
                        if key == "score"
                        else r.get(key, 0)
                        for r in runs
                    ]
                )
                if runs
                else None
            )

        bm, am = median(b, "score"), median(a, "score")
        passed = valid and bm is not None and am >= bm
        rows.append(
            {
                "case": case,
                "before_median": bm,
                "after_median": am,
                "before_read_characters": median(b, "read_output_characters"),
                "after_read_characters": median(a, "read_output_characters"),
                "pass": passed,
            }
        )
    return {
        "status": "PASS" if not errors and all(r["pass"] for r in rows) else "FAIL",
        "errors": errors,
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    inv = commands.add_parser("inventory")
    inv.add_argument("--host", action="store_true")
    inv.add_argument("--runtime", action="store_true")
    inv.add_argument(
        "--tokenizer-python",
        type=Path,
        help="Existing Python with tiktoken; installs nothing",
    )
    commands.add_parser("check")
    ev = commands.add_parser("eval")
    ev.add_argument("--ref")
    ev.add_argument(
        "--regrade", type=Path, help="Replay saved patches; does not run the model"
    )
    ev.add_argument("--working-tree", action="store_true")
    ev.add_argument("--model")
    ev.add_argument("--reasoning")
    ev.add_argument("--repetitions", type=int, default=3)
    ev.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    ev.add_argument("--timeout", type=int, default=600)
    ev.add_argument("--case", action="append", choices=list("ABCDE"))
    cmp = commands.add_parser("compare")
    cmp.add_argument("before", type=Path)
    cmp.add_argument("after", type=Path)
    launch = commands.add_parser(
        "run", help="Run Codex with project Skill selectors passed as session flags"
    )
    launch.add_argument("codex_args", nargs=argparse.REMAINDER)
    for sub in (inv, ev, cmp):
        sub.add_argument("--output", type=Path, required=sub is ev)
    args = parser.parse_args()
    if args.command == "run":
        codex_args = args.codex_args
        if codex_args[:1] == ["--"]:
            codex_args = codex_args[1:]
        return subprocess.run(
            [
                "codex",
                "-C",
                str(args.root),
                *overrides(project_skill_overrides(args.root)),
                *codex_args,
            ],
            cwd=args.root,
            check=False,
        ).returncode
    if args.command == "inventory":
        global TOKENIZER
        if args.tokenizer_python:
            TOKENIZER = subprocess.Popen(
                [
                    str(args.tokenizer_python),
                    "-c",
                    "import json,sys,tiktoken; e=tiktoken.get_encoding('o200k_base'); "
                    "print('READY',flush=True)\n"
                    "for line in sys.stdin: print(len(e.encode(json.loads(line))),flush=True)",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if TOKENIZER.stdout.readline().strip() != "READY":
                raise SystemExit("requested tokenizer is unavailable")
        try:
            result = inventory(args.root, args.host, args.runtime)
        finally:
            if TOKENIZER:
                TOKENIZER.stdin.close()
                TOKENIZER.wait(timeout=5)
    elif args.command == "check":
        result = check(args.root)
    elif args.command == "eval":
        if not args.regrade and not all((args.ref, args.model, args.reasoning)):
            parser.error("native eval requires --ref, --model and --reasoning")
        result = regrade(args.root, args) if args.regrade else evaluate(args.root, args)
    else:
        result = compare(
            json.loads(args.before.read_text()), json.loads(args.after.read_text())
        )
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get("status") == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
