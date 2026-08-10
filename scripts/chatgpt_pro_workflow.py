#!/usr/bin/env python3
"""Fail-closed ST-0101 state machine and evidence writer for ChatGPT Pro.

This module never drives a browser directly. Codex supplies normalized
observations from the allowlisted Playwright tools, while this module validates
the known-UI sequence and creates a hash-chained local run record. ``fixture``
executes the same state machine without an external side effect.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


STORY_ID = "ST-0101"
SCHEMA_VERSION = 1
EXACT_ORIGIN = "https://chatgpt.com"
ZERO_HASH = "0" * 64
MAX_TEXT_BYTES = 1_048_576
MAX_JSON_BYTES = 1_048_576
MAX_RECORD_BYTES = 4_194_304
REF_PATTERN = re.compile(r"e[1-9][0-9]*\Z")
RUN_ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\Z")

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPOSITORY_ROOT / "changes/st-0101/chatgpt-pro-known-ui.v1.json"
DEFAULT_SECRET_ROOT = REPOSITORY_ROOT / ".secrets/chatgpt-pro"
DEFAULT_RUN_ROOT = REPOSITORY_ROOT / ".secrets/chatgpt-pro-runs"

EXPECTED_OBSERVATION_KEYS = frozenset(
    {
        "state",
        "url",
        "authenticated",
        "stop_state",
        "model_label",
        "effort_label",
        "option_labels",
        "refs",
        "generating",
        "response_complete",
    }
)
EXPECTED_STOP_STATES = frozenset(
    {
        "account_ambiguity",
        "captcha",
        "login",
        "rate_limit",
        "reauthentication",
        "selector_drift",
        "unknown_ui",
    }
)
EXPECTED_PROFILE_KEYS = frozenset(
    {
        "effort_mode",
        "states",
        "model_option_labels",
        "target_model",
        "target_effort",
        "effort_option_labels",
    }
)
ADVANCED_PROFILE_ID = "gpt-5.6-sol-pro-advanced-v1"
EXPECTED_ADVANCED_PROFILE: dict[str, Any] = {
    "effort_mode": "advanced",
    "states": [
        "landing",
        "model_menu",
        "effort_menu",
        "ready",
        "send_ready",
        "submitted",
        "complete",
    ],
    "model_option_labels": ["GPT-5.6 Sol", "GPT-5.5", "GPT-5.3", "o3"],
    "target_model": "GPT-5.6 Sol",
    "target_effort": "Pro",
    "effort_option_labels": [
        "Instant 5.5",
        "Medium",
        "High",
        "Extra High",
        "Pro",
    ],
}

SENSITIVE_PATTERNS = (
    re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(
        r"(?im)^\s*(?:cookie|set-cookie|authorization)\s*:\s*(?!<redacted>)[^\r\n]{12,}"
    ),
    re.compile(
        r"(?i)(?:session[_-]?token|cf_clearance)\s*[=:]\s*(?!<redacted>)[^\s,;]{12,}"
    ),
    re.compile(
        r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])"
    ),
)


class WorkflowRefusal(RuntimeError):
    """A sanitized fail-closed workflow refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _read_regular(path: Path, limit: int, code: str) -> bytes:
    if not path.is_absolute():
        path = path.resolve()
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise WorkflowRefusal(code) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise WorkflowRefusal(code)
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > limit:
            raise WorkflowRefusal(code)
        return data
    finally:
        os.close(descriptor)


def _read_text(path: Path, limit: int, code: str) -> str:
    try:
        return _read_regular(path, limit, code).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise WorkflowRefusal(code) from error


def _read_json(path: Path, code: str) -> Any:
    try:
        return json.loads(_read_text(path, MAX_JSON_BYTES, code))
    except json.JSONDecodeError as error:
        raise WorkflowRefusal(code) from error


def _reject_sensitive_text(text: str, code: str) -> None:
    if not text.strip() or "\x00" in text:
        raise WorkflowRefusal(code)
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            raise WorkflowRefusal(code)
    lowered = text.lower()
    if '"cookies"' in lowered and '"origins"' in lowered:
        raise WorkflowRefusal(code)
    if "playwright/.auth" in lowered or "user-data-dir" in lowered:
        raise WorkflowRefusal(code)


def exact_origin(url: str) -> bool:
    """Return true only for URLs whose serialized origin is exact."""

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except TypeError, ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.netloc == "chatgpt.com"
        and parsed.hostname == "chatgpt.com"
        and port is None
        and parsed.username is None
        and parsed.password is None
    )


def _ensure_no_symlink_ancestors(path: Path) -> None:
    if not path.is_absolute():
        raise WorkflowRefusal("PATH_NOT_ABSOLUTE")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise WorkflowRefusal("PATH_SYMLINK")


def _ensure_private_directory(path: Path) -> None:
    _ensure_no_symlink_ancestors(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise WorkflowRefusal("PRIVATE_DIRECTORY_MODE")


def _write_exclusive(path: Path, payload: bytes, mode: int = 0o600) -> None:
    _ensure_no_symlink_ancestors(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, mode)
    except OSError as error:
        raise WorkflowRefusal("ARTIFACT_EXISTS_OR_UNSAFE") from error
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise WorkflowRefusal("ARTIFACT_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_contract(path: Path) -> dict[str, Any]:
    value = _read_json(path, "CONTRACT_INVALID")
    if not isinstance(value, dict):
        raise WorkflowRefusal("CONTRACT_INVALID")
    if value.get("origin") != EXACT_ORIGIN:
        raise WorkflowRefusal("CONTRACT_ORIGIN_INVALID")
    if value.get("entry_url") != f"{EXACT_ORIGIN}/":
        raise WorkflowRefusal("CONTRACT_ENTRY_INVALID")
    if value.get("prompt_secret_name") != "RAOS_CHATGPT_PROMPT":
        raise WorkflowRefusal("CONTRACT_SECRET_NAME_INVALID")
    stop_states = value.get("stop_states")
    profiles = value.get("profiles")
    if not isinstance(stop_states, list) or (
        not all(isinstance(item, str) for item in stop_states)
        or set(stop_states) != EXPECTED_STOP_STATES
    ):
        raise WorkflowRefusal("CONTRACT_INVALID")
    if not isinstance(profiles, dict) or not profiles:
        raise WorkflowRefusal("CONTRACT_INVALID")
    advanced_profiles: list[tuple[str, dict[str, Any]]] = []
    for profile_id, profile in profiles.items():
        if not isinstance(profile_id, str):
            raise WorkflowRefusal("CONTRACT_INVALID")
        if not isinstance(profile, dict) or set(profile) != EXPECTED_PROFILE_KEYS:
            raise WorkflowRefusal("CONTRACT_INVALID")
        if (
            profile.get("effort_mode") not in {"advanced", "combined", "split"}
            or not isinstance(profile.get("states"), list)
            or not profile["states"]
            or not all(isinstance(item, str) for item in profile["states"])
            or len(profile["states"]) != len(set(profile["states"]))
            or not isinstance(profile.get("model_option_labels"), list)
            or not profile["model_option_labels"]
            or not all(isinstance(item, str) for item in profile["model_option_labels"])
            or not isinstance(profile.get("effort_option_labels"), list)
            or not all(
                isinstance(item, str) for item in profile["effort_option_labels"]
            )
            or not isinstance(profile.get("target_model"), str)
            or not profile["target_model"]
            or not isinstance(profile.get("target_effort"), str)
            or not profile["target_effort"]
        ):
            raise WorkflowRefusal("CONTRACT_INVALID")
        if profile["effort_mode"] == "advanced":
            advanced_profiles.append((profile_id, profile))
    if advanced_profiles != [(ADVANCED_PROFILE_ID, EXPECTED_ADVANCED_PROFILE)]:
        raise WorkflowRefusal("CONTRACT_INVALID")
    return value


def _event_without_hash(
    *,
    sequence: int,
    previous_hash: str,
    run_id: str,
    event_type: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "story_id": STORY_ID,
        "run_id": run_id,
        "sequence": sequence,
        "recorded_at": _utc_now(),
        "event_type": event_type,
        "previous_event_sha256": previous_hash,
        "payload": dict(payload),
    }


def _verify_events(lines: Sequence[str], run_id: str) -> tuple[int, str]:
    previous_hash = ZERO_HASH
    for sequence, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise WorkflowRefusal("RUN_RECORD_INVALID") from error
        if not isinstance(event, dict):
            raise WorkflowRefusal("RUN_RECORD_INVALID")
        event_hash = event.pop("event_sha256", None)
        if (
            event.get("run_id") != run_id
            or event.get("sequence") != sequence
            or event.get("previous_event_sha256") != previous_hash
            or event_hash != _sha256(_canonical_json(event))
        ):
            raise WorkflowRefusal("RUN_RECORD_INVALID")
        previous_hash = event_hash
    return len(lines), previous_hash


def _append_event(
    record_path: Path,
    run_id: str,
    event_type: str,
    payload: Mapping[str, Any],
) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise WorkflowRefusal("RUN_ID_INVALID")
    if record_path.exists():
        text = _read_text(record_path, MAX_RECORD_BYTES, "RUN_RECORD_INVALID")
        if text and not text.endswith("\n"):
            raise WorkflowRefusal("RUN_RECORD_INVALID")
        lines = text.splitlines()
        count, previous_hash = _verify_events(lines, run_id)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC
    else:
        count, previous_hash = 0, ZERO_HASH
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    event = _event_without_hash(
        sequence=count + 1,
        previous_hash=previous_hash,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
    )
    event_hash = _sha256(_canonical_json(event))
    event["event_sha256"] = event_hash
    line = _canonical_json(event) + b"\n"
    try:
        descriptor = os.open(record_path, flags, 0o600)
    except OSError as error:
        raise WorkflowRefusal("RUN_RECORD_UNSAFE") from error
    try:
        view = memoryview(line)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise WorkflowRefusal("RUN_RECORD_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return event_hash


def _dotenv_secret(prompt: str) -> bytes:
    escaped = (
        prompt.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'RAOS_CHATGPT_PROMPT="{escaped}"\n'.encode("utf-8")


def _new_run_id() -> str:
    prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{secrets.token_hex(6)}"


def prepare_run(
    *,
    prompt_path: Path,
    contract_path: Path,
    secret_root: Path,
    run_root: Path,
) -> dict[str, str]:
    contract_bytes = _read_regular(contract_path, MAX_JSON_BYTES, "CONTRACT_INVALID")
    contract = _load_contract(contract_path)
    prompt = _read_text(prompt_path, MAX_TEXT_BYTES, "PROMPT_INVALID")
    _reject_sensitive_text(prompt, "PROMPT_SENSITIVE_OR_INVALID")
    if secret_root.parts[-2:] != (".secrets", "chatgpt-pro"):
        raise WorkflowRefusal("SECRET_ROOT_SCOPE")
    if run_root.parts[-2:] != (".secrets", "chatgpt-pro-runs"):
        raise WorkflowRefusal("RUN_ROOT_SCOPE")
    _ensure_private_directory(secret_root.parent)
    _ensure_private_directory(secret_root)
    _ensure_private_directory(run_root.parent)
    _ensure_private_directory(run_root)
    run_id = _new_run_id()
    run_dir = run_root / run_id
    _ensure_private_directory(run_dir)
    secret_file = secret_root / f"{run_id}.env"
    _write_exclusive(secret_file, _dotenv_secret(prompt))
    record_path = run_dir / "run-record.v1.jsonl"
    prompt_hash = _sha256(prompt.encode("utf-8"))
    _append_event(
        record_path,
        run_id,
        "RUN_PREPARED",
        {
            "status": "PREPARED",
            "origin": contract["origin"],
            "prompt_sha256": prompt_hash,
            "contract_sha256": _sha256(contract_bytes),
            "prompt_secret_name": contract["prompt_secret_name"],
        },
    )
    _append_event(
        record_path,
        run_id,
        "ACTION_REQUIRED",
        {
            "tool": "browser_navigate",
            "arguments": {"url": contract["entry_url"]},
        },
    )
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "record_path": str(record_path),
        "secrets_file": str(secret_file),
        "prompt_sha256": prompt_hash,
    }


def _one_ref(observation: Mapping[str, Any], name: str) -> str:
    refs = observation.get("refs")
    if not isinstance(refs, dict) or set(refs) != {name}:
        raise WorkflowRefusal("SELECTOR_AMBIGUITY")
    values = refs.get(name)
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], str)
        or not REF_PATTERN.fullmatch(values[0])
    ):
        raise WorkflowRefusal("SELECTOR_AMBIGUITY")
    return values[0]


def _advanced_evidence_refs(observation: Mapping[str, Any], name: str) -> None:
    """Accept new ref-free evidence and predecessor non-action transcripts."""

    if observation.get("refs") == {}:
        return
    _one_ref(observation, name)


def _validate_common_observation(
    observation: Mapping[str, Any], stop_states: set[str]
) -> None:
    if set(observation) != EXPECTED_OBSERVATION_KEYS:
        raise WorkflowRefusal("OBSERVATION_SCHEMA")
    url = observation.get("url")
    if not isinstance(url, str) or not exact_origin(url):
        raise WorkflowRefusal("ORIGIN_MISMATCH")
    stop_state = observation.get("stop_state")
    if stop_state is not None:
        if not isinstance(stop_state, str) or stop_state not in stop_states:
            raise WorkflowRefusal("UNKNOWN_STOP_STATE")
        raise WorkflowRefusal(f"STOP_{stop_state.upper()}")
    if observation.get("authenticated") is not True:
        raise WorkflowRefusal("STOP_LOGIN")


def _action(tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "arguments": dict(arguments)}


def validate_transcript(
    transcript: Mapping[str, Any], contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if set(transcript) != {"schema_version", "profile_id", "observations"}:
        raise WorkflowRefusal("TRANSCRIPT_SCHEMA")
    if transcript.get("schema_version") != SCHEMA_VERSION:
        raise WorkflowRefusal("TRANSCRIPT_SCHEMA")
    profile_id = transcript.get("profile_id")
    profiles = contract["profiles"]
    if not isinstance(profile_id, str) or profile_id not in profiles:
        raise WorkflowRefusal("UNKNOWN_UI_PROFILE")
    profile = profiles[profile_id]
    effort_mode = profile.get("effort_mode")
    observations = transcript.get("observations")
    states = profile.get("states")
    if not isinstance(observations, list) or not isinstance(states, list):
        raise WorkflowRefusal("TRANSCRIPT_SCHEMA")
    if [
        item.get("state") if isinstance(item, dict) else None for item in observations
    ] != states:
        raise WorkflowRefusal("STATE_SEQUENCE")
    stop_states = set(contract["stop_states"])
    actions: list[dict[str, Any]] = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise WorkflowRefusal("OBSERVATION_SCHEMA")
        _validate_common_observation(observation, stop_states)
        state = observation["state"]
        option_labels = observation["option_labels"]
        if not isinstance(option_labels, list) or not all(
            isinstance(label, str) for label in option_labels
        ):
            raise WorkflowRefusal("OBSERVATION_SCHEMA")
        if state == "landing":
            target = _one_ref(observation, "model_picker")
            actions.append(
                _action("browser_click", {"element": "model picker", "target": target})
            )
        elif state == "model_menu":
            if option_labels != profile["model_option_labels"]:
                raise WorkflowRefusal("MODEL_OPTIONS_AMBIGUOUS")
            if effort_mode == "advanced":
                _advanced_evidence_refs(observation, "target_model")
            else:
                target = _one_ref(observation, "target_model")
                actions.append(
                    _action(
                        "browser_click",
                        {"element": "Pro model option", "target": target},
                    )
                )
        elif state == "model_selected":
            if (
                effort_mode != "split"
                or observation["model_label"] != profile["target_model"]
            ):
                raise WorkflowRefusal("PRO_NOT_VERIFIED")
            target = _one_ref(observation, "effort_picker")
            actions.append(
                _action(
                    "browser_click", {"element": "Pro effort picker", "target": target}
                )
            )
        elif state == "effort_menu":
            if option_labels != profile["effort_option_labels"]:
                raise WorkflowRefusal("EFFORT_OPTIONS_AMBIGUOUS")
            if effort_mode == "advanced":
                _advanced_evidence_refs(observation, "target_effort")
            else:
                target = _one_ref(observation, "target_effort")
                actions.append(
                    _action(
                        "browser_click",
                        {"element": "maximum Pro effort", "target": target},
                    )
                )
        elif state == "ready":
            if (
                observation["model_label"] != profile["target_model"]
                or observation["effort_label"] != profile["target_effort"]
            ):
                raise WorkflowRefusal("PRO_OR_MAX_EFFORT_NOT_VERIFIED")
            refs = observation.get("refs")
            expected_refs = (
                {"composer"} if effort_mode == "advanced" else {"composer", "send"}
            )
            if not isinstance(refs, dict) or set(refs) != expected_refs:
                raise WorkflowRefusal("SELECTOR_AMBIGUITY")
            composer = refs["composer"]
            if (
                not isinstance(composer, list)
                or len(composer) != 1
                or not isinstance(composer[0], str)
                or not REF_PATTERN.fullmatch(composer[0])
            ):
                raise WorkflowRefusal("SELECTOR_AMBIGUITY")
            actions.append(
                _action(
                    "browser_type",
                    {
                        "element": "ChatGPT composer",
                        "target": composer[0],
                        "text": contract["prompt_secret_name"],
                        "submit": False,
                    },
                )
            )
            if effort_mode != "advanced":
                send = refs["send"]
                if (
                    not isinstance(send, list)
                    or len(send) != 1
                    or not isinstance(send[0], str)
                    or not REF_PATTERN.fullmatch(send[0])
                ):
                    raise WorkflowRefusal("SELECTOR_AMBIGUITY")
                actions.append(
                    _action("browser_click", {"element": "send", "target": send[0]})
                )
        elif state == "send_ready":
            if (
                effort_mode != "advanced"
                or observation["model_label"] != profile["target_model"]
                or observation["effort_label"] != profile["target_effort"]
            ):
                raise WorkflowRefusal("PRO_OR_MAX_EFFORT_NOT_VERIFIED")
            send = _one_ref(observation, "send")
            actions.append(
                _action("browser_click", {"element": "send prompt", "target": send})
            )
        elif state == "submitted":
            if observation["generating"] is not True:
                raise WorkflowRefusal("SUBMISSION_NOT_CONFIRMED")
            if (
                observation["model_label"] != profile["target_model"]
                or observation["effort_label"] != profile["target_effort"]
            ):
                raise WorkflowRefusal("POST_SUBMIT_MODEL_DRIFT")
            if observation["refs"] != {}:
                raise WorkflowRefusal("OBSERVATION_SCHEMA")
            actions.append(_action("browser_wait_for", {"time": 5}))
        elif state == "complete":
            if (
                observation["generating"] is not False
                or observation["response_complete"] is not True
            ):
                raise WorkflowRefusal("RESPONSE_INCOMPLETE")
            _one_ref(observation, "assistant_response")
            actions.append(
                _action("capture_response", {"status": "UNAPPROVED_PROPOSAL"})
            )
        else:
            raise WorkflowRefusal("UNKNOWN_UI_STATE")
    return actions


def _proposal_bytes(
    *, run_id: str, prompt_hash: str, response: str, response_hash: str
) -> bytes:
    header = (
        "# UNAPPROVED PROPOSAL\n\n"
        "Status: `UNAPPROVED_PROPOSAL`  \n"
        f"Story: `{STORY_ID}`  \n"
        f"Run ID: `{run_id}`  \n"
        f"Prompt SHA-256: `{prompt_hash}`  \n"
        f"Response SHA-256: `{response_hash}`\n\n"
        "> This browser-captured output is untrusted proposal material. It is not a\n"
        "> approved design handoff, cannot resolve an Open Decision, and cannot authorize\n"
        "> implementation without separate human review and canonical reconciliation.\n\n"
        "## Captured response\n\n"
    )
    return (header + response.rstrip() + "\n").encode("utf-8")


def execute_fixture(
    *,
    prepared: Mapping[str, str],
    transcript_path: Path,
    response_path: Path,
    contract_path: Path,
) -> dict[str, str]:
    run_id = prepared["run_id"]
    run_dir = Path(prepared["run_dir"])
    record_path = Path(prepared["record_path"])
    contract = _load_contract(contract_path)
    transcript = _read_json(transcript_path, "TRANSCRIPT_INVALID")
    if not isinstance(transcript, dict):
        raise WorkflowRefusal("TRANSCRIPT_INVALID")
    response = _read_text(response_path, MAX_TEXT_BYTES, "RESPONSE_INVALID")
    _reject_sensitive_text(response, "RESPONSE_SENSITIVE_OR_INVALID")
    try:
        actions = validate_transcript(transcript, contract)
    except WorkflowRefusal as refusal:
        _append_event(
            record_path,
            run_id,
            "WORKFLOW_ABORTED",
            {"status": "REFUSED", "reason_code": refusal.code},
        )
        raise
    for observation in transcript["observations"]:
        _append_event(
            record_path,
            run_id,
            "OBSERVATION_VERIFIED",
            {
                "state": observation["state"],
                "url": observation["url"],
                "model_label": observation["model_label"],
                "effort_label": observation["effort_label"],
            },
        )
    # Fixture observations do not necessarily map one-to-one to actions (the
    # ready state emits type and send), so bind the full plan as one event.
    _append_event(
        record_path,
        run_id,
        "FIXTURE_ACTION_PLAN_VERIFIED",
        {"actions": actions},
    )
    response_hash = _sha256(response.encode("utf-8"))
    proposal_path = run_dir / "unapproved-proposal.md"
    proposal = _proposal_bytes(
        run_id=run_id,
        prompt_hash=prepared["prompt_sha256"],
        response=response,
        response_hash=response_hash,
    )
    _write_exclusive(proposal_path, proposal)
    proposal_hash = _sha256(proposal)
    final_event_hash = _append_event(
        record_path,
        run_id,
        "UNAPPROVED_PROPOSAL_CAPTURED",
        {
            "status": "UNAPPROVED_PROPOSAL",
            "prompt_sha256": prepared["prompt_sha256"],
            "response_sha256": response_hash,
            "proposal_sha256": proposal_hash,
            "proposal_file": proposal_path.name,
        },
    )
    return {
        "run_id": run_id,
        "record_path": str(record_path),
        "proposal_path": str(proposal_path),
        "prompt_sha256": prepared["prompt_sha256"],
        "response_sha256": response_hash,
        "proposal_sha256": proposal_hash,
        "final_event_sha256": final_event_hash,
    }


def _path(value: str) -> Path:
    return Path(value).absolute()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--prompt-file", required=True, type=_path)
    prepare.add_argument("--contract", type=_path, default=DEFAULT_CONTRACT)
    prepare.add_argument("--secret-root", type=_path, default=DEFAULT_SECRET_ROOT)
    prepare.add_argument("--run-root", type=_path, default=DEFAULT_RUN_ROOT)
    fixture = subparsers.add_parser("fixture")
    fixture.add_argument("--prompt-file", required=True, type=_path)
    fixture.add_argument("--transcript", required=True, type=_path)
    fixture.add_argument("--response-file", required=True, type=_path)
    fixture.add_argument("--contract", type=_path, default=DEFAULT_CONTRACT)
    fixture.add_argument("--secret-root", type=_path, default=DEFAULT_SECRET_ROOT)
    fixture.add_argument("--run-root", type=_path, default=DEFAULT_RUN_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    os.umask(0o077)
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        prepared = prepare_run(
            prompt_path=arguments.prompt_file,
            contract_path=arguments.contract,
            secret_root=arguments.secret_root,
            run_root=arguments.run_root,
        )
        if arguments.command == "prepare":
            result = {"status": "PREPARED", "story_id": STORY_ID, **prepared}
        else:
            evidence = execute_fixture(
                prepared=prepared,
                transcript_path=arguments.transcript,
                response_path=arguments.response_file,
                contract_path=arguments.contract,
            )
            result = {
                "status": "PASS",
                "mode": "fixture",
                "story_id": STORY_ID,
                **evidence,
            }
    except WorkflowRefusal as refusal:
        result = {
            "status": "REFUSED",
            "story_id": STORY_ID,
            "reason_code": refusal.code,
        }
        sys.stderr.write(
            json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
        )
        return 2
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
