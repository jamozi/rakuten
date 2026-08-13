"""Offline CLI and Make capability tests for ST-1703 Wave 3."""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from types import ModuleType

import pytest

from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftAffiliateState,
    MvpDraftBaseState,
    MvpDraftManualReviewState,
    MvpDraftObservation,
    MvpDraftOperationPreview,
    MvpDraftPreview,
    MvpDraftReasonCode,
    WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER,
    WordPressComMvpDraftFailure,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/wordpresscom_review_draft.py"


def _load_script() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "st1703_wordpresscom_mvp_cli", SCRIPT
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _preview() -> MvpDraftPreview:
    return MvpDraftPreview(
        operations=tuple(
            MvpDraftOperationPreview(
                operation_id=operation_id,
                observation=MvpDraftObservation.EXACT,
                reason_code=MvpDraftReasonCode.EXACT_DESIRED,
            )
            for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
        ),
        base_state=MvpDraftBaseState.PREPARED,
        affiliate_state=MvpDraftAffiliateState.SLOTS_PENDING,
        affiliate_slot_count=0,
        manual_review_state=MvpDraftManualReviewState.NOT_READY,
    )


def _copy_sources(module: ModuleType, repository: Path) -> None:
    for relative, _, _ in module._MVP_FIXED_SOURCES:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())


def test_wave3a_authority_sources_are_exact_and_runtime_bound() -> None:
    module = _load_script()
    sources = {path: (size, sha256) for path, size, sha256 in module._MVP_FIXED_SOURCES}
    expected = {
        module._MVP_WAVE3A_HANDOFF_PATH: (
            12_741,
            "1c0d50faedd3c76d18101afb1032d82da21a6daf0a01e9c687371d20519926aa",
        ),
        module._MVP_WAVE3A_APPROVAL_PATH: (
            1_852,
            "c1002959dda0de0ba0c0535697a814fa3221fcb05c7947f543452ef99232afb0",
        ),
    }
    for path, binding in expected.items():
        value = (ROOT / path).read_bytes()
        assert sources[path] == binding
        assert len(value) == binding[0]
        assert hashlib.sha256(value).hexdigest() == binding[1]
        assert path.as_posix() in module._MVP_RUNTIME_PATHS


def test_wave3_cli_commands_are_argument_free_and_closed() -> None:
    module = _load_script()
    choices = module._parser()._subparsers._group_actions[0].choices
    assert set(choices) == {
        "oauth-setup",
        "create-review-draft",
        "prepare-mvp-drafts",
        "preview-mvp",
    }
    for command in ("prepare-mvp-drafts", "preview-mvp"):
        assert choices[command]._actions[0].dest == "help"
        with pytest.raises(SystemExit) as failure:
            module._parser().parse_args([command, "--site-id", "256699520"])
        assert failure.value.code == 2


def test_make_exposes_the_two_exact_argument_free_wave3_recipes() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert (
        "wordpresscom-prepare-mvp-drafts:\n"
        '\t"$(WORDPRESSCOM_REVIEW_DRAFT_LAUNCHER)" prepare-mvp-drafts\n'
    ) in makefile
    assert (
        "wordpresscom-preview-mvp:\n"
        '\t"$(WORDPRESSCOM_REVIEW_DRAFT_LAUNCHER)" preview-mvp\n'
    ) in makefile
    for forbidden in ("publish", "schedule", "delete", "retry", "SITE_ID="):
        assert (
            forbidden
            not in makefile[
                makefile.index("wordpresscom-prepare-mvp-drafts:") : makefile.index(
                    "pro-runtime-install:"
                )
            ]
        )


def test_quiescence_affirmation_requires_one_exact_closed_phrase() -> None:
    module = _load_script()
    prompts: list[str] = []

    def exact_reader(prompt: str) -> bytes:
        prompts.append(prompt)
        return b"AFFIRM REMOTE WRITERS QUIESCED UNTIL FINAL READBACK"

    assert module._affirm_mvp_remote_writer_quiescence(reader=exact_reader) is True
    assert prompts == ["Type AFFIRM REMOTE WRITERS QUIESCED UNTIL FINAL READBACK: "]
    for value in (
        b"",
        b"AFFIRM REMOTE WRITERS QUIESCED",
        b"AFFIRM REMOTE WRITERS QUIESCED UNTIL FINAL READBACK ",
        b"affirm remote writers quiesced until final readback",
    ):
        assert (
            module._affirm_mvp_remote_writer_quiescence(
                reader=lambda _prompt, value=value: value
            )
            is False
        )


def test_prepare_refuses_unaffirmed_after_source_binding_before_state_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repository = tmp_path / "repository"
    repository.mkdir()
    _copy_sources(module, repository)
    monkeypatch.setattr(module, "_verify_mvp_runtime_identity", lambda _root: None)

    def forbidden_state(_root: Path) -> Path:
        raise AssertionError("journal setup must not run")

    monkeypatch.setattr(module, "_ensure_mvp_journal_roots", forbidden_state)
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        module._run_prepare_mvp_drafts(repository, affirmer=lambda: False)
    assert failure.value.code.value == "MVP_DRAFT_LIVE_MUTATION_NOT_AUTHORIZED"
    assert not (repository / ".secrets").exists()


@pytest.mark.parametrize(
    "path_attribute",
    ["_MVP_HANDOFF_PATH", "_MVP_WAVE3A_HANDOFF_PATH", "_MVP_WAVE3A_APPROVAL_PATH"],
)
def test_invalid_source_refuses_before_quiescence_affirmer(
    path_attribute: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    repository = tmp_path / "repository"
    repository.mkdir()
    _copy_sources(module, repository)
    monkeypatch.setattr(module, "_verify_mvp_runtime_identity", lambda _root: None)
    (repository / getattr(module, path_attribute)).write_bytes(b"changed")
    calls = 0

    def affirmer() -> bool:
        nonlocal calls
        calls += 1
        return True

    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        module._run_prepare_mvp_drafts(repository, affirmer=affirmer)
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"
    assert calls == 0
    assert not (repository / ".secrets").exists()


def test_runtime_identity_failure_precedes_source_affirmer_secret_and_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    calls: list[str] = []

    def identity(_root: Path) -> None:
        calls.append("identity")
        raise WordPressComMvpDraftFailure(
            module.WordPressComMvpDraftFailureCode.BINDING_INVALID
        )

    def forbidden_bundle(_root: Path) -> object:
        raise AssertionError("source binding must not run")

    monkeypatch.setattr(module, "_verify_mvp_runtime_identity", identity)
    monkeypatch.setattr(module, "_build_mvp_bundle", forbidden_bundle)
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        module._run_prepare_mvp_drafts(ROOT, affirmer=lambda: True)
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"
    assert calls == ["identity"]


def test_runtime_identity_refuses_nonisolated_or_wrong_python_before_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    calls: list[str] = []

    def forbidden_read(*_args: object, **_kwargs: object) -> bytes:
        calls.append("manifest")
        raise AssertionError("manifest must not be read")

    monkeypatch.setattr(module, "_valid_mvp_python_runtime", lambda: False)
    monkeypatch.setattr(module, "_read_mvp_runtime_file", forbidden_read)
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        module._verify_mvp_runtime_identity(ROOT)
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"
    assert calls == []


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["/usr/bin/git", *arguments],
        cwd=repository,
        env={
            "GIT_AUTHOR_EMAIL": "wave3@example.invalid",
            "GIT_AUTHOR_NAME": "Wave3 Test",
            "GIT_COMMITTER_EMAIL": "wave3@example.invalid",
            "GIT_COMMITTER_NAME": "Wave3 Test",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


def _identity_repository(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str]:
    repository = tmp_path / "identity-repository"
    runtime = repository / "runtime.py"
    manifest = repository / "runtime-manifest.json"
    (repository / "scripts").mkdir(parents=True)
    runtime.write_bytes(b"runtime-v1\n")
    (repository / "scripts/wordpresscom_review_draft.py").write_bytes(
        SCRIPT.read_bytes()
    )
    manifest_value = {
        "approved_base_commit": "PLACEHOLDER",
        "generated_by": "python3 scripts/build_wordpresscom_mvp_runtime_manifest.py",
        "paths": [
            {
                "bytes": len(runtime.read_bytes()),
                "path": "runtime.py",
                "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
            }
        ],
        "schema": "WORDPRESSCOM_MVP_DRAFT_RUNTIME_MANIFEST_V1",
        "slice_id": "WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3",
        "story_id": "ST-1703",
    }
    assert _git(repository, "init", "-q").returncode == 0
    manifest.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    assert _git(repository, "add", ".").returncode == 0
    assert _git(repository, "commit", "-qm", "base").returncode == 0
    base = _git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    manifest_value["approved_base_commit"] = base
    manifest.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    assert _git(repository, "add", ".").returncode == 0
    assert _git(repository, "commit", "-qm", "manifest").returncode == 0
    monkeypatch.setattr(module, "_EXPECTED_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(
        module, "_MVP_RUNTIME_MANIFEST_PATH", Path("runtime-manifest.json")
    )
    monkeypatch.setattr(module, "_MVP_RUNTIME_PATHS", ("runtime.py",))
    monkeypatch.setattr(module, "_MVP_APPROVED_BASE_COMMIT", base)
    monkeypatch.setattr(module, "_MVP_EXPECTED_VENV", Path(module.sys.prefix))
    monkeypatch.setattr(
        module, "_MVP_EXPECTED_PYTHON_BASE", Path(module.sys.base_prefix)
    )
    monkeypatch.setattr(
        module, "_MVP_EXPECTED_PYTHON", Path(module.sys.executable).resolve()
    )
    monkeypatch.setattr(
        module, "__file__", repository / "scripts/wordpresscom_review_draft.py"
    )
    monkeypatch.setattr(module, "_valid_mvp_python_runtime", lambda: True)
    return repository, runtime, base


@pytest.mark.parametrize(
    "case",
    [
        "untracked-manifest",
        "dirty",
        "staged",
        "manifest-mismatch",
        "non-ancestor",
        "skip-worktree",
    ],
)
def test_runtime_identity_fake_repository_failure_matrix_precedes_affirmer(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    repository, runtime, base = _identity_repository(module, tmp_path, monkeypatch)
    manifest = repository / "runtime-manifest.json"
    if case == "untracked-manifest":
        assert (
            _git(repository, "rm", "--cached", "runtime-manifest.json").returncode == 0
        )
    elif case == "dirty":
        runtime.write_bytes(b"runtime-dirty\n")
    elif case == "staged":
        runtime.write_bytes(b"runtime-staged\n")
        assert _git(repository, "add", "runtime.py").returncode == 0
    elif case == "manifest-mismatch":
        value = json.loads(manifest.read_text(encoding="ascii"))
        value["paths"][0]["sha256"] = "0" * 64
        manifest.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="ascii",
        )
    elif case == "non-ancestor":
        monkeypatch.setattr(module, "_MVP_APPROVED_BASE_COMMIT", "f" * 40)
    else:
        assert (
            _git(repository, "update-index", "--skip-worktree", "runtime.py").returncode
            == 0
        )
        runtime.write_bytes(b"runtime-hidden-dirty\n")
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        module._verify_mvp_runtime_identity(repository)
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"
    assert not (repository / ".secrets").exists()
    assert base


def test_runtime_identity_fake_repository_exact_head_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repository, _, _ = _identity_repository(module, tmp_path, monkeypatch)
    module._verify_mvp_runtime_identity(repository)


def test_runtime_manifest_generator_check_is_deterministic_and_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_wordpresscom_mvp_runtime_manifest.py"),
            "--check",
        ],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout == b""
    assert result.stderr == b""


def test_runtime_identity_is_rebound_to_exact_v3_target_and_manifest() -> None:
    module = _load_script()
    target = "acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d"
    assert module._MVP_APPROVED_BASE_COMMIT == target

    path = (
        ROOT / "changes/st-1703/"
        "wordpresscom-mvp-draft-preparation.wave3.runtime-manifest.v1.json"
    )
    content = path.read_bytes()
    assert len(content) == 5656
    assert (
        hashlib.sha256(content).hexdigest()
        == "b9ccd47c40b9bc9a7595f9e9de2d807232e2b084851b2057007d37b8c98b3c6e"
    )
    manifest = json.loads(content)
    assert manifest["approved_base_commit"] == target
    assert len(manifest["paths"]) == 27
    script_row = next(
        row
        for row in manifest["paths"]
        if row["path"] == "scripts/wordpresscom_review_draft.py"
    )
    assert script_row == {
        "bytes": 43402,
        "path": "scripts/wordpresscom_review_draft.py",
        "sha256": "2303866f94aa3aae45c2d4b3162335eb7e60afd25ed18e42a3d7c30bd0debf01",
    }


def test_wave3_runners_never_touch_exact_old_wave2_journal_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    repository = tmp_path / "repository"
    repository.mkdir()
    old_journal = (
        repository
        / ".secrets/wordpresscom-review-draft/state/review-draft-state.v1.json"
    )
    observed: list[tuple[str, Path]] = []

    def observe(name: str, *values: object) -> None:
        for value in values:
            if isinstance(value, bytes):
                value = os.fsdecode(value)
            if isinstance(value, (str, os.PathLike)):
                candidate = Path(value)
                observed.append((name, candidate))
                if candidate == old_journal:
                    raise AssertionError(f"old Wave 2 journal touched by {name}")

    def guarded(name: str, function: object):
        def wrapper(*args: object, **kwargs: object):
            observe(name, *args, *kwargs.values())
            return function(*args, **kwargs)

        return wrapper

    # Trap the low-level primitives used by the production modules and every
    # common higher-level path/file/copy entrypoint.  This is deliberately an
    # executable sentinel, not merely a source scan: either Wave 3 runner must
    # fail this test if it ever tries to open, read, write, stat, hash via a
    # file handle, copy, move, rename, or delete the exact Wave 2 journal.
    for name in (
        "open",
        "stat",
        "lstat",
        "rename",
        "replace",
        "unlink",
        "remove",
    ):
        function = getattr(module.os, name)
        monkeypatch.setattr(module.os, name, guarded(name, function))

    monkeypatch.setattr(builtins, "open", guarded("builtins.open", builtins.open))
    monkeypatch.setattr(io, "open", guarded("io.open", io.open))
    for name in (
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "stat",
        "lstat",
        "unlink",
        "rename",
        "replace",
    ):
        function = getattr(Path, name)
        monkeypatch.setattr(Path, name, guarded(f"Path.{name}", function))
    for name in (
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "move",
        "rmtree",
    ):
        function = getattr(shutil, name)
        monkeypatch.setattr(shutil, name, guarded(f"shutil.{name}", function))

    original_file_digest = hashlib.file_digest

    def guarded_file_digest(fileobj: object, *args: object, **kwargs: object):
        observe("hashlib.file_digest", getattr(fileobj, "name", None))
        return original_file_digest(fileobj, *args, **kwargs)

    monkeypatch.setattr(hashlib, "file_digest", guarded_file_digest)

    class FakeService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def prepare(self) -> MvpDraftPreview:
            return _preview()

        def preview(self) -> MvpDraftPreview:
            return _preview()

    wave3_root = repository / ".secrets/wordpresscom-review-draft/mvp-wave3-state"
    monkeypatch.setattr(module, "_verify_mvp_runtime_identity", lambda _root: None)
    monkeypatch.setattr(module, "_build_mvp_bundle", lambda _root: object())
    monkeypatch.setattr(module, "_ensure_mvp_journal_roots", lambda _root: wave3_root)
    monkeypatch.setattr(
        module, "WordPressComOAuthSecretStore", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        module, "OfficialWordPressComMvpDraftAdapter", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        module, "ImmutableWordPressComMvpDraftJournal", lambda **_kwargs: object()
    )
    monkeypatch.setattr(module, "WordPressComMvpDraftPreparationService", FakeService)
    assert (
        module._run_prepare_mvp_drafts(repository, affirmer=lambda: True)["command"]
        == "prepare-mvp-drafts"
    )
    assert module._run_preview_mvp(repository)["command"] == "preview-mvp"
    assert all(path != old_journal for _, path in observed)
    assert not (repository / ".secrets").exists()


def test_preview_missing_journal_is_read_only_and_creates_nothing(
    tmp_path: Path,
) -> None:
    module = _load_script()
    repository = tmp_path / "repository"
    repository.mkdir()
    journal = module._mvp_preview_journal(repository)
    assert journal.inspect() == ()
    assert not (repository / ".secrets").exists()


def test_wave3_cli_output_is_exact_sanitized_schema() -> None:
    module = _load_script()
    output = module._mvp_preview_output("preview-mvp", _preview())
    assert set(output) == {
        "affiliate_slot_count",
        "affiliate_state",
        "base_state",
        "command",
        "manual_review_state",
        "operations",
        "publication_authority",
    }
    assert output["publication_authority"] == "NONE"
    assert output["affiliate_slot_count"] == 0
    rendered = json.dumps(output, ensure_ascii=True, sort_keys=True)
    for forbidden in (
        "kurashierabinote",
        "public-api",
        "wordpresscom_oauth_access_token",
        "<a ",
        "href=",
        "283672805",
        "256699520",
        "184a6214",
    ):
        assert forbidden not in rendered


def test_cli_projects_preview_diagnostic_only_in_existing_reason_code_key() -> None:
    module = _load_script()
    operations = (
        MvpDraftOperationPreview(
            operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
            observation=MvpDraftObservation.DRIFT,
            reason_code=MvpDraftReasonCode.FULL_GET_DISCUSSION_TYPE_INVALID,
        ),
        *(
            MvpDraftOperationPreview(
                operation_id=operation_id,
                observation=MvpDraftObservation.EXACT,
                reason_code=MvpDraftReasonCode.EXACT_DESIRED,
            )
            for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[1:]
        ),
    )
    preview = MvpDraftPreview(
        operations=operations,
        base_state=MvpDraftBaseState.DRIFT,
        affiliate_state=MvpDraftAffiliateState.NOT_EVALUATED,
        affiliate_slot_count=0,
        manual_review_state=MvpDraftManualReviewState.NOT_READY,
    )
    output = module._mvp_preview_output("preview-mvp", preview)
    assert set(output) == {
        "affiliate_slot_count",
        "affiliate_state",
        "base_state",
        "command",
        "manual_review_state",
        "operations",
        "publication_authority",
    }
    assert output["operations"][0]["reason_code"] == (
        "FULL_GET_DISCUSSION_TYPE_INVALID"
    )
    rendered = json.dumps(output, ensure_ascii=True, sort_keys=True)
    for forbidden in (
        "https://",
        "kurashierabinote",
        "provider-body",
        "provider-value",
        "synthetic-opaque-extension",
        "opaque-value",
        "renamed-value",
        "comments_open",
        "pings_open",
        "256699520",
        "283672805",
        "<a ",
        "sha256",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "reason",
    [
        MvpDraftReasonCode.ARTICLE_APPROVED_BASELINE,
        MvpDraftReasonCode.ARTICLE_MIXED_DESIRED_BASELINE_DRIFT,
        MvpDraftReasonCode.ARTICLE_AUTHOR_NAME_DRIFT,
    ],
)
def test_cli_projects_object_drift_diagnostic_in_unchanged_sanitized_schema(
    reason: MvpDraftReasonCode,
) -> None:
    module = _load_script()
    operations = (
        MvpDraftOperationPreview(
            operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
            observation=MvpDraftObservation.DRIFT,
            reason_code=reason,
        ),
        *(
            MvpDraftOperationPreview(
                operation_id=operation_id,
                observation=MvpDraftObservation.EXACT,
                reason_code=MvpDraftReasonCode.EXACT_DESIRED,
            )
            for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[1:]
        ),
    )
    preview = MvpDraftPreview(
        operations=operations,
        base_state=MvpDraftBaseState.DRIFT,
        affiliate_state=MvpDraftAffiliateState.NOT_EVALUATED,
        affiliate_slot_count=0,
        manual_review_state=MvpDraftManualReviewState.NOT_READY,
    )
    output = module._mvp_preview_output("preview-mvp", preview)
    assert set(output) == {
        "affiliate_slot_count",
        "affiliate_state",
        "base_state",
        "command",
        "manual_review_state",
        "operations",
        "publication_authority",
    }
    assert set(output["operations"][0]) == {
        "operation",
        "reason_code",
        "state",
    }
    assert output["operations"][0]["reason_code"] == reason.value
    assert output["publication_authority"] == "NONE"
    rendered = json.dumps(output, ensure_ascii=True, sort_keys=True)
    for forbidden in (
        "https://",
        "kurashierabinote",
        "provider-body",
        "provider-value",
        "remote-title",
        "remote-content",
        "256699520",
        "283672805",
        "184a6214",
        "<a ",
        "href=",
    ):
        assert forbidden not in rendered


def test_cli_projection_revalidates_mutated_preview_without_raw_type_error() -> None:
    module = _load_script()
    preview = _preview()
    object.__setattr__(preview, "affiliate_slot_count", "0")
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        module._mvp_preview_output("preview-mvp", preview)
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"

    object.__setattr__(preview, "affiliate_slot_count", 0)
    object.__setattr__(
        preview.operations[0], "reason_code", MvpDraftReasonCode.OBJECT_MISSING
    )
    with pytest.raises(WordPressComMvpDraftFailure) as operation_failure:
        module._mvp_preview_output("preview-mvp", preview)
    assert operation_failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"


def test_wave3_cli_call_graph_has_no_old_journal_access_primitive() -> None:
    module = _load_script()
    functions = (
        module._build_mvp_bundle,
        module._ensure_mvp_journal_roots,
        module._mvp_preview_journal,
        module._run_prepare_mvp_drafts,
        module._run_preview_mvp,
    )
    names: set[str] = set()
    literals: set[str] = set()
    for function in functions:
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
        literals.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert "_STATE_ROOT" not in names
    assert "DurableWordPressComReviewDraftAdapter" not in names
    assert "_run_create_review_draft" not in names
    assert "review-draft-state.v1.json" not in literals
    assert ".review-draft-state.v1.lock" not in literals
