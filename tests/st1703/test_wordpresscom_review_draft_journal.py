"""Durable intent, committed replay, and private-state tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import dataclasses
import json
import os
from pathlib import Path
import stat
from threading import Lock

import pytest

import raos.adapters.wordpresscom_review_draft_journal as journal_module
from raos.adapters.wordpresscom_review_draft_journal import (
    DurableWordPressComReviewDraftAdapter,
)
from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    ReviewDraftDisposition,
    WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
    WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
    WORDPRESSCOM_REVIEW_DRAFT_STATUS,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftFailureCode,
    WordPressComReviewDraftReceipt,
)
from raos.ports.wordpresscom_review_draft import WordPressComReviewDraftPort


ROOT = Path(__file__).resolve().parents[2]


def _candidate() -> WordPressComReviewDraft:
    return build_bound_review_draft(
        article_bytes=(
            ROOT / "changes/st-1703/first-article-review-draft.v1.md"
        ).read_bytes(),
        source_packet_bytes=(
            ROOT / "changes/st-1703/source-packet-candidate.first-article.v1.yaml"
        ).read_bytes(),
        base_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml"
        ).read_bytes(),
        amendment_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml"
        ).read_bytes(),
        activation_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml"
        ).read_bytes(),
    )


def _receipt(candidate: WordPressComReviewDraft) -> WordPressComReviewDraftReceipt:
    return WordPressComReviewDraftReceipt(
        schema=WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
        authority=WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
        network_status=WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
        target_origin=candidate.target_origin,
        draft_id=1703,
        status=WORDPRESSCOM_REVIEW_DRAFT_STATUS,
        operation_binding_sha256=candidate.operation_binding_sha256,
        content_sha256=candidate.content_sha256,
        response_body_sha256="c" * 64,
        disposition=ReviewDraftDisposition.CREATED,
        publication_authorized=False,
        production_eligible=False,
    )


class CountingCreator:
    def __init__(self, *, fail: bool = False) -> None:
        self.preflights = 0
        self.attempts = 0
        self.fail = fail
        self.lock = Lock()

    def require_create_capability(self, candidate: WordPressComReviewDraft) -> None:
        assert type(candidate) is WordPressComReviewDraft
        with self.lock:
            self.preflights += 1

    def attempt_create_review_draft(
        self, candidate: WordPressComReviewDraft
    ) -> WordPressComReviewDraftReceipt:
        with self.lock:
            self.attempts += 1
        if self.fail:
            raise TimeoutError("provider detail must be hidden")
        return _receipt(candidate)


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "wordpresscom-review-draft-state"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def test_intent_is_durable_before_creator_and_commit_is_exact(
    private_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    events: list[str] = []
    real_fsync = journal_module.os.fsync

    def observed_fsync(descriptor: int) -> None:
        real_fsync(descriptor)
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            state = json.loads(
                (private_root / "review-draft-state.v1.json").read_text(
                    encoding="ascii"
                )
            )
            events.append(f"fsync-directory-{state['state']}")
        else:
            events.append("fsync-file")

    monkeypatch.setattr(journal_module.os, "fsync", observed_fsync)

    class InspectingCreator:
        preflights = 0
        attempts = 0

        def require_create_capability(self, received: WordPressComReviewDraft) -> None:
            self.preflights += 1
            events.append("preflight")
            assert received is candidate
            assert not (private_root / "review-draft-state.v1.json").exists()

        def attempt_create_review_draft(
            self, received: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            self.attempts += 1
            events.append("attempt-post")
            path = private_root / "review-draft-state.v1.json"
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            state = json.loads(path.read_text(encoding="ascii"))
            assert state == {
                "content_sha256": received.content_sha256,
                "operation_binding_sha256": received.operation_binding_sha256,
                "schema": "WORDPRESSCOM_REVIEW_DRAFT_STATE_V1",
                "state": "INTENT",
                "target_origin": received.target_origin,
            }
            return _receipt(received)

    creator = InspectingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )

    receipt = adapter.create_review_draft(candidate)
    state_path = private_root / "review-draft-state.v1.json"
    state = json.loads(state_path.read_text(encoding="ascii"))

    assert creator.preflights == creator.attempts == 1
    assert receipt.disposition is ReviewDraftDisposition.CREATED
    assert set(state) == {
        "content_sha256",
        "exact_status_on_success",
        "operation_binding_sha256",
        "positive_draft_id_on_success",
        "response_body_sha256_on_success",
        "schema",
        "state",
        "target_origin",
    }
    assert state["state"] == "COMMITTED"
    assert state["positive_draft_id_on_success"] == 1703
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert events == [
        "preflight",
        "fsync-file",
        "fsync-directory-INTENT",
        "attempt-post",
        "fsync-file",
        "fsync-directory-COMMITTED",
    ]
    assert (
        stat.S_IMODE((private_root / ".review-draft-state.v1.lock").stat().st_mode)
        == 0o600
    )
    persisted = state_path.read_text(encoding="ascii")
    assert candidate.title not in persisted
    assert candidate.rendered_content not in persisted


def test_preflight_failure_leaves_no_intent_and_makes_no_attempt(
    private_root: Path,
) -> None:
    candidate = _candidate()

    class RefusingPreflight:
        preflights = 0
        attempts = 0

        def require_create_capability(self, received: WordPressComReviewDraft) -> None:
            assert received is candidate
            self.preflights += 1
            raise WordPressComReviewDraftFailure(
                WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID
            )

        def attempt_create_review_draft(
            self, received: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            del received
            self.attempts += 1
            raise AssertionError("attempt must remain unreachable")

    creator = RefusingPreflight()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
    assert creator.preflights == 1
    assert creator.attempts == 0
    assert not (private_root / "review-draft-state.v1.json").exists()


def test_durable_adapter_is_the_application_facing_create_or_replay_port(
    private_root: Path,
) -> None:
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root,
        creator=CountingCreator(),
    )

    assert isinstance(adapter, WordPressComReviewDraftPort)


def test_committed_repeat_replays_without_creator_call(private_root: Path) -> None:
    creator = CountingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    candidate = _candidate()

    created = adapter.create_review_draft(candidate)
    replayed = adapter.create_review_draft(candidate)

    assert creator.preflights == creator.attempts == 1
    assert created.draft_id == replayed.draft_id == 1703
    assert replayed.disposition is ReviewDraftDisposition.COMMITTED_REPLAY


def test_concurrent_exact_calls_create_once_and_replay(private_root: Path) -> None:
    creator = CountingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    candidate = _candidate()

    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(
            pool.map(lambda _: adapter.create_review_draft(candidate), range(8))
        )

    assert creator.preflights == creator.attempts == 1
    assert [item.disposition for item in receipts].count(
        ReviewDraftDisposition.CREATED
    ) == 1
    assert [item.disposition for item in receipts].count(
        ReviewDraftDisposition.COMMITTED_REPLAY
    ) == 7


def test_creator_failure_leaves_intent_and_never_calls_again(
    private_root: Path,
) -> None:
    creator = CountingCreator(fail=True)
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    candidate = _candidate()

    with pytest.raises(WordPressComReviewDraftFailure) as first:
        adapter.create_review_draft(candidate)
    with pytest.raises(WordPressComReviewDraftFailure) as second:
        adapter.create_review_draft(candidate)

    assert str(first.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert str(second.value) == "REVIEW_DRAFT_JOURNAL_AMBIGUOUS"
    assert creator.preflights == creator.attempts == 1
    assert (
        json.loads(
            (private_root / "review-draft-state.v1.json").read_text(encoding="ascii")
        )["state"]
        == "INTENT"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda state: state.update(extra="forbidden"),
        lambda state: state.update(state="PUBLISHED"),
        lambda state: state.update(positive_draft_id_on_success=0),
        lambda state: state.update(response_body_sha256_on_success="not-a-hash"),
    ],
)
def test_tampered_committed_state_stops_without_creator(
    private_root: Path, mutation: object
) -> None:
    creator = CountingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    candidate = _candidate()
    adapter.create_review_draft(candidate)
    path = private_root / "review-draft-state.v1.json"
    state = json.loads(path.read_text(encoding="ascii"))
    mutation(state)  # type: ignore[operator]
    path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    path.chmod(0o600)

    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.create_review_draft(candidate)

    assert creator.preflights == creator.attempts == 1


def test_changed_binding_in_committed_state_stops_without_second_creator_call(
    private_root: Path,
) -> None:
    creator = CountingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    candidate = _candidate()
    adapter.create_review_draft(candidate)
    path = private_root / "review-draft-state.v1.json"
    state = json.loads(path.read_text(encoding="ascii"))
    state["operation_binding_sha256"] = "0" * 64
    path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    path.chmod(0o600)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_JOURNAL_MISMATCH"
    assert creator.preflights == creator.attempts == 1


@pytest.mark.parametrize("state_name", ["INTENT", "COMMITTED"])
def test_wave_2a_state_mismatch_stops_before_secret_or_network_boundary(
    private_root: Path,
    state_name: str,
) -> None:
    candidate = _candidate()
    wave_2a_binding = "2a29e77b52207d67c6be5017564d113657880b2f67a9e74d38d47e7538ff3e23"
    state: dict[str, object] = {
        "content_sha256": candidate.content_sha256,
        "operation_binding_sha256": wave_2a_binding,
        "schema": "WORDPRESSCOM_REVIEW_DRAFT_STATE_V1",
        "state": state_name,
        "target_origin": candidate.target_origin,
    }
    if state_name == "COMMITTED":
        state.update(
            {
                "exact_status_on_success": "draft",
                "positive_draft_id_on_success": 1703,
                "response_body_sha256_on_success": "c" * 64,
            }
        )
    state_path = private_root / "review-draft-state.v1.json"
    state_path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    state_path.chmod(0o600)

    class NetworkTrap:
        def require_create_capability(self, received: WordPressComReviewDraft) -> None:
            del received
            pytest.fail("Wave 2A state mismatch reached preflight or secret access")

        def attempt_create_review_draft(
            self, received: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            del received
            pytest.fail("Wave 2A state mismatch reached POST")

    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root,
        creator=NetworkTrap(),
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_JOURNAL_MISMATCH"
    assert json.loads(state_path.read_text(encoding="ascii")) == state


def test_direct_candidate_rejects_tampered_content_or_operation_binding() -> None:
    candidate = _candidate()
    values = {
        field.name: getattr(candidate, field.name)
        for field in dataclasses.fields(candidate)
    }

    for changes in (
        {"rendered_content": "<p>tampered</p>"},
        {"operation_binding_sha256": "0" * 64},
    ):
        with pytest.raises(WordPressComReviewDraftFailure):
            WordPressComReviewDraft(**(values | changes))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publication_authorized", True),
        ("production_eligible", True),
        ("status", "publish"),
        ("draft_id", 0),
    ],
)
def test_mutated_outward_receipt_is_ambiguous_and_never_committed(
    private_root: Path,
    field: str,
    value: object,
) -> None:
    candidate = _candidate()

    class MutatingCreator:
        preflights = 0
        attempts = 0

        def require_create_capability(self, received: WordPressComReviewDraft) -> None:
            assert received is candidate
            self.preflights += 1

        def attempt_create_review_draft(
            self, received: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            self.attempts += 1
            receipt = _receipt(received)
            object.__setattr__(receipt, field, value)
            return receipt

    creator = MutatingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root,
        creator=creator,
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert creator.preflights == creator.attempts == 1
    state = json.loads(
        (private_root / "review-draft-state.v1.json").read_text(encoding="ascii")
    )
    assert state["state"] == "INTENT"


def test_root_or_state_symlink_and_wrong_modes_stop_without_creator(
    tmp_path: Path, private_root: Path
) -> None:
    candidate = _candidate()
    creator = CountingCreator()
    private_root.chmod(0o755)
    with pytest.raises(WordPressComReviewDraftFailure):
        DurableWordPressComReviewDraftAdapter(
            private_root=private_root, creator=creator
        )
    private_root.chmod(0o700)
    real_root = tmp_path / "real-private"
    real_root.mkdir(mode=0o700)
    linked_root = tmp_path / "linked-private"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(WordPressComReviewDraftFailure):
        DurableWordPressComReviewDraftAdapter(private_root=linked_root, creator=creator)
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    target = tmp_path / "foreign-state"
    target.write_text("{}\n", encoding="ascii")
    target.chmod(0o600)
    (private_root / "review-draft-state.v1.json").symlink_to(target)
    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.create_review_draft(candidate)
    assert creator.preflights == creator.attempts == 0


def test_wrong_state_mode_or_owner_stops_without_creator(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate()
    creator = CountingCreator()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=creator
    )
    path = private_root / "review-draft-state.v1.json"
    path.write_text("{}\n", encoding="ascii")
    path.chmod(0o644)
    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.create_review_draft(candidate)
    assert creator.preflights == creator.attempts == 0
    path.unlink()
    real_euid = os.geteuid()
    monkeypatch.setattr(journal_module.os, "geteuid", lambda: real_euid + 1)
    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.create_review_draft(candidate)
    assert creator.preflights == creator.attempts == 0


def test_failures_and_repr_never_expose_candidate_or_provider_details(
    private_root: Path,
) -> None:
    secret = "provider-secret-sentinel"

    class LeakingCreator:
        def require_create_capability(self, candidate: WordPressComReviewDraft) -> None:
            del candidate

        def attempt_create_review_draft(
            self, candidate: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            del candidate
            raise RuntimeError(secret)

    candidate = _candidate()
    adapter = DurableWordPressComReviewDraftAdapter(
        private_root=private_root, creator=LeakingCreator()
    )
    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.create_review_draft(candidate)

    rendered = " ".join((str(caught.value), repr(caught.value), repr(adapter)))
    assert secret not in rendered
    assert candidate.rendered_content not in rendered
