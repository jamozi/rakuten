"""Static trust-boundary evidence for the versioned durable ST-0706 seam."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

import yaml

from .support import REPOSITORY_ROOT
from raos.adapters.recorded_durable_ai_job_queue_v2 import (
    RecordedDurableAiJobStateAdapterV2,
)
from raos.application.ai.durable_job_queue_v2 import (
    RecordedDurableAiJobQueueServiceV2,
)
from raos.domain.ai.durable_job_queue_v2 import (
    CONTRACT_SHA256,
    DurableLeaseClaim,
    DurableQueueSnapshot,
    RecordedAttemptOutcome,
    POLICY_SHA256,
)
from raos.ports.durable_ai_job_queue_v2 import DurableAiJobStateCasPort


RUNTIME_PATHS = (
    REPOSITORY_ROOT / "python/raos/domain/ai/durable_job_queue_v2.py",
    REPOSITORY_ROOT / "python/raos/ports/durable_ai_job_queue_v2.py",
    REPOSITORY_ROOT / "python/raos/application/ai/durable_job_queue_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_durable_ai_job_queue_v2.py",
)
CONTRACT_PATH = (
    REPOSITORY_ROOT / "changes/st-0706/contracts/durable-ai-job-queue.v2.yaml"
)
BANNED_IMPORT_ROOTS = frozenset(
    {
        "asyncio",
        "boto3",
        "celery",
        "fastapi",
        "http",
        "httpx",
        "logging",
        "multiprocessing",
        "openai",
        "os",
        "pathlib",
        "random",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "time",
        "urllib",
    }
)
BANNED_CALLS = frozenset(
    {
        "create_task",
        "getenv",
        "monotonic",
        "now",
        "open",
        "publish",
        "send",
        "sleep",
        "spawn",
        "start",
        "system",
        "ThreadPoolExecutor",
        "uuid4",
        "utcnow",
    }
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _public_methods(candidate: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(candidate)
        if not name.startswith("_") and callable(member)
    }


def test_v2_runtime_is_isolated_from_st1404_and_external_runtime_surfaces() -> None:
    imported: set[str] = set()
    called: set[str] = set()
    combined = ""
    for path in RUNTIME_PATHS:
        combined += path.read_text(encoding="utf-8")
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
            assert not isinstance(node, (ast.AsyncFunctionDef, ast.While))

    assert "st1404" not in combined.lower()
    assert not any(name.split(".")[0] in BANNED_IMPORT_ROOTS for name in imported)
    assert not (called & BANNED_CALLS)
    assert "except BaseException" not in combined
    assert "pickle" not in combined


def test_public_inventory_has_cas_and_recorded_transition_surfaces_but_no_dispatch() -> (
    None
):
    assert _public_methods(DurableAiJobStateCasPort) == {"compare_and_swap", "load"}
    assert _public_methods(RecordedDurableAiJobQueueServiceV2) == {
        "claim",
        "complete",
        "enqueue",
        "outbox_intents",
        "recover_next",
        "view",
    }
    assert _public_methods(RecordedDurableAiJobStateAdapterV2) == {
        "arm_commit_uncertain_once",
        "compare_and_swap",
        "export_snapshot",
        "from_snapshot",
        "load",
    }
    assert _public_methods(DurableLeaseClaim) == set()
    assert _public_methods(DurableQueueSnapshot) == set()
    assert _public_methods(RecordedAttemptOutcome) == set()
    assert all(
        forbidden not in _public_methods(RecordedDurableAiJobQueueServiceV2)
        for forbidden in {"dispatch", "publish", "redrive", "run", "start"}
    )


def test_persisted_dataclass_fields_exclude_arbitrary_or_sensitive_material() -> None:
    forbidden = {
        "body",
        "content",
        "credential",
        "exception",
        "message",
        "metadata",
        "payload",
        "prompt",
        "response",
        "secret",
        "traceback",
    }
    declared: set[str] = set()
    for node in ast.walk(_tree(RUNTIME_PATHS[0])):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared.add(node.target.id)
    assert not (declared & forbidden)


def test_contract_declares_every_semantic_source() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    bindings = document["source_bindings"]
    assert len(bindings) == 17
    for binding in bindings:
        source = REPOSITORY_ROOT / binding["path"]
        assert source.is_file()
    assert len(CONTRACT_SHA256) == 64


def test_contract_preserves_disabled_recorded_only_and_generic_owner_boundaries() -> (
    None
):
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert document["document"] == {
        "id": "RAOS-ST0706-DURABLE-AI-JOB-QUEUE-002",
        "version": "2.0.0",
        "story_id": "ST-0706",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "RECORDED_SYNTHETIC_DURABLE_STATE_CONTRACT",
        "enabled_by_default": False,
        "authority": "NONE",
        "production_eligible": False,
        "publication_authorized": False,
    }
    assert document["authority"]["generic_runtime_owner"] == "ST-1404"
    policy = dict(document["recorded_policy"])
    claimed_policy_sha256 = policy.pop("policy_sha256")
    canonical_policy = json.dumps(
        policy,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert claimed_policy_sha256 == POLICY_SHA256
    assert hashlib.sha256(canonical_policy).hexdigest() == POLICY_SHA256
    assert policy["retry_backoff_seconds_after_attempt"] == [7, 31]
    assert policy["retry_backoff_strictly_increasing"] is True
    assert policy["maximum_attempts_cap"] == 3
    assert policy["maximum_cumulative_retry_backoff_seconds"] == 38
    assert sum(policy["retry_backoff_seconds_after_attempt"]) == 38
    assert policy["clock_source"] == "CALLER_SUPPLIED_EXPLICIT_UTC"
    assert policy["jitter_runtime_selection"] is False
    assert policy["automatic_redrive"] is False
    assert policy["automatic_loop"] is False
    assert policy["sleep"] is False
    assert document["durability_boundary"]["storage"] == "CALLER_OWNED_CAS_ATOMIC_PORT"
    assert document["outbox_boundary"]["dispatch"] == "NOT_IMPLEMENTED"
    assert document["safe_defaults"]["activation"] == "DISABLED"
    assert document["safe_defaults"]["recorded_fixture_activation_only"] is True
    assert not any(
        value
        for key, value in document["safe_defaults"].items()
        if key not in {"activation", "recorded_fixture_activation_only"}
    )
