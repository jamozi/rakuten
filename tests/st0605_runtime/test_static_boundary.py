from __future__ import annotations

import ast
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from raos.domain.evidence.claim_evidence import ClaimEvidenceCoverageReport


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATHS = (
    Path("python/raos/domain/evidence/claim_evidence.py"),
    Path("python/raos/ports/evidence/claim_evidence.py"),
    Path("python/raos/application/evidence/claim_evidence.py"),
    Path("python/raos/adapters/recorded_claim_evidence.py"),
)
FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "boto3",
    "http",
    "httpx",
    "openai",
    "requests",
    "socket",
    "sqlalchemy",
    "subprocess",
    "urllib",
}
FORBIDDEN_PROVIDER_IMPORT_ROOTS = {
    "aiohttp",
    "boto3",
    "httpx",
    "openai",
    "requests",
    "sqlalchemy",
}
RUNTIME_IMPORT_TARGETS = (
    "raos.domain.evidence.claim_evidence",
    "raos.ports.evidence.claim_evidence",
    "raos.application.evidence.claim_evidence",
    "raos.adapters.recorded_claim_evidence",
)
MANIFEST_PATH = ROOT / "changes/st-0605/runtime-manifest.v1.yaml"


def test_runtime_has_no_network_provider_database_or_subprocess_import() -> None:
    for relative in RUNTIME_PATHS:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module.split(".", 1)[0])
        assert imports.isdisjoint(FORBIDDEN_IMPORT_ROOTS), relative


def test_fresh_runtime_import_closure_is_provider_free_and_manifest_bound() -> None:
    child_program = """
import importlib
import json
import sys

sys.path.insert(0, SOURCE_ROOT)

for target in TARGETS:
    importlib.import_module(target)

loaded = {}
for name, module in sorted(sys.modules.items()):
    if name != "raos" and not name.startswith("raos."):
        continue
    source_path = getattr(module, "__file__", None)
    if source_path is not None:
        loaded[name] = source_path

print(json.dumps({
    "loaded": loaded,
    "loaded_roots": sorted({name.split(".", 1)[0] for name in sys.modules}),
}, sort_keys=True, separators=(",", ":")))
""".replace("SOURCE_ROOT", repr(str(ROOT / "python"))).replace(
        "TARGETS", repr(RUNTIME_IMPORT_TARGETS)
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "python")
    completed = subprocess.run(
        [sys.executable, "-I", "-c", child_program],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads(completed.stdout)
    assert type(observed) is dict
    loaded = observed["loaded"]
    loaded_roots = observed["loaded_roots"]
    assert type(loaded) is dict
    assert type(loaded_roots) is list
    assert set(loaded_roots).isdisjoint(FORBIDDEN_PROVIDER_IMPORT_ROOTS)
    assert all(not name.startswith("raos.generated") for name in loaded)

    manifest = yaml.safe_load(MANIFEST_PATH.read_bytes())
    assert type(manifest) is dict
    source_artifacts = manifest["source_artifacts"]
    assert type(source_artifacts) is list
    manifest_hashes = {
        artifact["uri"].removeprefix("repo://"): artifact["sha256"]
        for artifact in source_artifacts
    }
    loaded_relative_paths: set[str] = set()
    for module_name, raw_path in loaded.items():
        assert type(module_name) is str
        assert type(raw_path) is str
        source = Path(raw_path).resolve()
        relative = source.relative_to(ROOT).as_posix()
        assert relative.startswith("python/raos/"), module_name
        assert (
            manifest_hashes.get(relative)
            == hashlib.sha256(source.read_bytes()).hexdigest()
        ), module_name
        loaded_relative_paths.add(relative)
    assert loaded_relative_paths


def test_report_schema_has_no_raw_text_url_secret_or_publication_authority() -> None:
    names = {field.name for field in fields(ClaimEvidenceCoverageReport)}
    for prohibited_part in (
        "claim_text",
        "source_text",
        "url",
        "credential",
        "secret",
        "token",
        "api_key",
    ):
        assert all(prohibited_part not in name for name in names)
    assert {"publication_authorized", "production_eligible"}.issubset(names)


def test_ports_expose_only_read_and_append_methods() -> None:
    source = (ROOT / "python/raos/ports/evidence/claim_evidence.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {"get_snapshot", "append_report"}
