"""Recorded, network-free tests for the bounded ST-0107 ruleset operator."""

from __future__ import annotations

import json
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import github_ruleset_operator as operator


COMMIT = "a" * 40
RUN_ID = "20260821T000000Z-0123456789abcdef01234567"
APP_ID = 15368


def _repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    (root / operator.CONTRACT_PATH.parent).mkdir(parents=True)
    (root / operator.POLICY_PATH.parent).mkdir(parents=True, exist_ok=True)
    (root / operator.CODEOWNERS_PATH.parent).mkdir(parents=True, exist_ok=True)
    (root / operator.CONTRACT_PATH).write_bytes(
        (operator.REPOSITORY_ROOT / operator.CONTRACT_PATH).read_bytes()
    )
    policy = json.loads(
        (operator.REPOSITORY_ROOT / operator.POLICY_PATH).read_text(encoding="utf-8")
    )
    policy["ruleset"]["pull_request"].update(
        {
            "require_code_owner_review": True,
            "require_last_push_approval": False,
            "required_approving_review_count": 0,
        }
    )
    (root / operator.POLICY_PATH).write_text(
        json.dumps(policy, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    (root / operator.GOVERNANCE_SOURCE_PATH).write_bytes(
        (operator.REPOSITORY_ROOT / operator.GOVERNANCE_SOURCE_PATH).read_bytes()
    )
    (root / operator.CODEOWNERS_PATH).write_bytes(
        (operator.REPOSITORY_ROOT / operator.CODEOWNERS_PATH).read_bytes()
    )
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    return root


class FakeTransport:
    """Stateful fake that applies at most the mutation explicitly requested."""

    def __init__(self) -> None:
        self.main_sha = "b" * 40
        self.ruleset_id = 401
        self.target: dict[str, Any] | None = None
        self.extra_inventory: list[dict[str, Any]] = []
        self.check_runs = [
            {
                "name": context,
                "app": {"slug": "github-actions", "id": APP_ID},
            }
            for context in operator.REQUIRED_CONTEXTS
        ]
        self.calls: list[tuple[str, str, object | None]] = []
        self.mutation_count = 0
        self.ambiguous_once = False
        self.readback_mismatch_once = False

    def _inventory(self) -> list[dict[str, Any]]:
        rows = deepcopy(self.extra_inventory)
        if self.target is not None:
            rows.append(
                {
                    "id": self.ruleset_id,
                    "name": self.target["name"],
                    "source": operator.REPOSITORY_FULL_NAME,
                    "source_type": "Repository",
                    "enforcement": self.target["enforcement"],
                }
            )
        return rows

    def _detail(self) -> dict[str, Any]:
        assert self.target is not None
        return {
            "id": self.ruleset_id,
            "source": operator.REPOSITORY_FULL_NAME,
            "source_type": "Repository",
            **deepcopy(self.target),
        }

    def request(self, method: str, path: str, body: object | None = None) -> object:
        self.calls.append((method, path, deepcopy(body)))
        if method == "GET" and path == operator.REPOSITORY_API_PATH:
            return {
                "id": 99,
                "full_name": operator.REPOSITORY_FULL_NAME,
                "default_branch": operator.DEFAULT_BRANCH,
            }
        if method == "GET" and path == operator.MAIN_COMMIT_PATH:
            return {"sha": self.main_sha}
        if method == "GET" and path == operator.CHECK_RUNS_PATH:
            return {"check_runs": deepcopy(self.check_runs)}
        if method == "GET" and path == operator.RULESET_INVENTORY_PATH:
            return self._inventory()
        if method == "GET" and path == operator.EFFECTIVE_RULES_PATH:
            if self.target is None or self.target["enforcement"] != "active":
                return []
            return deepcopy(self.target["rules"])
        if (
            method == "GET"
            and path == f"{operator.RULESETS_API_PATH}/{self.ruleset_id}"
        ):
            return self._detail()
        if method == "POST" and path == operator.RULESETS_API_PATH:
            self.mutation_count += 1
            self.target = deepcopy(body)
            if self.readback_mismatch_once:
                self.readback_mismatch_once = False
                self.target["rules"] = [
                    row
                    for row in self.target["rules"]
                    if row["type"] != "required_linear_history"
                ]
            if self.ambiguous_once:
                self.ambiguous_once = False
                raise operator.AmbiguousMutationError("MUTATION_RESULT_AMBIGUOUS")
            return self._detail()
        if (
            method == "PUT"
            and path == f"{operator.RULESETS_API_PATH}/{self.ruleset_id}"
        ):
            self.mutation_count += 1
            self.target = deepcopy(body)
            if self.ambiguous_once:
                self.ambiguous_once = False
                raise operator.AmbiguousMutationError("MUTATION_RESULT_AMBIGUOUS")
            return self._detail()
        raise AssertionError(f"unexpected fake request: {method} {path}")


def _plan(tmp_path: Path, fake: FakeTransport) -> tuple[Path, Path, dict[str, Any]]:
    root = _repository_root(tmp_path)
    private_root = tmp_path / "private"
    result = operator.create_plan(
        fake,
        root=root,
        private_root=private_root,
        policy_commit=COMMIT,
        run_id=RUN_ID,
    )
    return root, private_root, result


def test_routes_are_fixed_and_delete_or_other_repository_is_impossible() -> None:
    with pytest.raises(operator.OperatorError, match="REQUEST_ROUTE_FORBIDDEN"):
        operator._validate_route("DELETE", f"{operator.RULESETS_API_PATH}/1")
    with pytest.raises(operator.OperatorError, match="REQUEST_ROUTE_FORBIDDEN"):
        operator._validate_route("GET", "/repos/other/repository/rulesets")
    assert operator.API_ORIGIN == "https://api.github.com"
    assert operator.REPOSITORY_FULL_NAME == "jamozi/rakuten"


def test_token_requires_current_owner_mode_0600_and_no_symlink_ancestor(
    tmp_path: Path,
) -> None:
    token = tmp_path / "token"
    secret = "github_pat_" + "x" * 48
    token.write_text(secret + "\n", encoding="ascii")
    token.chmod(0o600)
    assert (
        operator.read_token_from_environment(
            {operator.TOKEN_FILE_ENVIRONMENT: str(token)}
        )
        == secret
    )
    token.chmod(0o640)
    with pytest.raises(operator.OperatorError, match="TOKEN_FILE_INVALID"):
        operator.read_token_from_environment(
            {operator.TOKEN_FILE_ENVIRONMENT: str(token)}
        )
    token.chmod(0o600)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(operator.OperatorError, match="TOKEN_FILE_INVALID"):
        operator.read_token_from_environment(
            {operator.TOKEN_FILE_ENVIRONMENT: str(linked_parent / "token")}
        )


def test_plan_is_private_and_fails_on_duplicate_or_missing_check_binding(
    tmp_path: Path,
) -> None:
    fake = FakeTransport()
    root, private_root, result = _plan(tmp_path, fake)
    run_directory = private_root / RUN_ID
    assert stat.S_IMODE(run_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_directory / "plan.v1.json").stat().st_mode) == 0o600
    assert result["status"] == "PLANNED"
    record = json.loads((run_directory / "plan.v1.json").read_text())
    assert record["plan"]["policy"]["commit"] == COMMIT
    assert record["plan"]["live_before_sha256"]
    assert record["plan"]["desired_sha256"]
    assert record["plan"]["rollback"]["kind"] == "disable_created"
    assert record["plan"]["operation"]["method"] == "POST"
    assert operator.load_operator_contract(root)["github"]["owner"] == "jamozi"

    duplicate = FakeTransport()
    duplicate.extra_inventory = [
        {
            "id": 1,
            "name": operator.RULESET_NAME,
            "source": operator.REPOSITORY_FULL_NAME,
            "source_type": "Repository",
            "enforcement": "active",
        },
        {
            "id": 2,
            "name": operator.RULESET_NAME,
            "source": operator.REPOSITORY_FULL_NAME,
            "source_type": "Repository",
            "enforcement": "active",
        },
    ]
    with pytest.raises(operator.OperatorError, match="RULESET_DUPLICATE"):
        operator.status_operation(duplicate)

    missing = FakeTransport()
    missing.check_runs.pop()
    with pytest.raises(operator.OperatorError, match="CHECK_BINDING_MISSING"):
        operator.status_operation(missing)


def test_status_validates_operator_contract_before_transport(tmp_path: Path) -> None:
    root = _repository_root(tmp_path)
    (root / operator.CONTRACT_PATH).write_text("{}\n", encoding="utf-8")
    fake = FakeTransport()
    with pytest.raises(operator.OperatorError, match="CONTRACT_INVALID"):
        operator.status_operation(fake, root=root)
    assert fake.calls == []


def test_apply_refuses_plan_hash_and_live_main_drift_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTransport()
    root, private_root, plan = _plan(tmp_path, fake)
    monkeypatch.setattr(operator, "current_policy_commit", lambda _root: COMMIT)
    monkeypatch.setattr(
        operator, "_require_verified_owner_bindings", lambda _root: None
    )
    with pytest.raises(operator.OperatorError, match="PLAN_HASH_MISMATCH"):
        operator.apply_plan(
            fake,
            run_id=RUN_ID,
            plan_sha256="0" * 64,
            root=root,
            private_root=private_root,
        )
    assert fake.mutation_count == 0
    fake.main_sha = "c" * 40
    with pytest.raises(operator.OperatorError, match="LIVE_BEFORE_DRIFT"):
        operator.apply_plan(
            fake,
            run_id=RUN_ID,
            plan_sha256=plan["plan_sha256"],
            root=root,
            private_root=private_root,
        )
    assert fake.mutation_count == 0


def test_ambiguous_apply_is_not_retried_and_uses_get_only_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTransport()
    root, private_root, plan = _plan(tmp_path, fake)
    monkeypatch.setattr(operator, "current_policy_commit", lambda _root: COMMIT)
    monkeypatch.setattr(
        operator, "_require_verified_owner_bindings", lambda _root: None
    )
    fake.ambiguous_once = True
    result = operator.apply_plan(
        fake,
        run_id=RUN_ID,
        plan_sha256=plan["plan_sha256"],
        root=root,
        private_root=private_root,
    )
    assert result["status"] == "RECONCILED"
    assert fake.mutation_count == 1
    mutation_index = next(
        index for index, call in enumerate(fake.calls) if call[0] in {"POST", "PUT"}
    )
    assert all(call[0] == "GET" for call in fake.calls[mutation_index + 1 :])
    apply_record = json.loads((private_root / RUN_ID / "apply.v1.json").read_text())
    assert apply_record["mutation_retried"] is False


def test_readback_mismatch_fails_after_one_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTransport()
    root, private_root, plan = _plan(tmp_path, fake)
    monkeypatch.setattr(operator, "current_policy_commit", lambda _root: COMMIT)
    monkeypatch.setattr(
        operator, "_require_verified_owner_bindings", lambda _root: None
    )
    fake.readback_mismatch_once = True
    with pytest.raises(operator.OperatorError, match="READBACK_MISMATCH"):
        operator.apply_plan(
            fake,
            run_id=RUN_ID,
            plan_sha256=plan["plan_sha256"],
            root=root,
            private_root=private_root,
        )
    assert fake.mutation_count == 1
    apply_record = json.loads((private_root / RUN_ID / "apply.v1.json").read_text())
    assert apply_record["status"] == "READBACK_MISMATCH"
    assert apply_record["mutation_retried"] is False


def test_apply_rejects_current_placeholder_owner_bindings_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTransport()
    root, private_root, plan = _plan(tmp_path, fake)
    monkeypatch.setattr(operator, "current_policy_commit", lambda _root: COMMIT)
    with pytest.raises(operator.OperatorError, match="OWNER_BINDINGS_UNVERIFIED"):
        operator.apply_plan(
            fake,
            run_id=RUN_ID,
            plan_sha256=plan["plan_sha256"],
            root=root,
            private_root=private_root,
        )
    assert fake.mutation_count == 0


def test_new_ruleset_rollback_uses_put_to_disable_and_never_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTransport()
    root, private_root, plan = _plan(tmp_path, fake)
    monkeypatch.setattr(operator, "current_policy_commit", lambda _root: COMMIT)
    monkeypatch.setattr(
        operator, "_require_verified_owner_bindings", lambda _root: None
    )
    operator.apply_plan(
        fake,
        run_id=RUN_ID,
        plan_sha256=plan["plan_sha256"],
        root=root,
        private_root=private_root,
    )
    result = operator.rollback_plan(
        fake,
        run_id=RUN_ID,
        root=root,
        private_root=private_root,
    )
    assert result["rollback_kind"] == "disable_created"
    assert fake.target is not None
    assert fake.target["enforcement"] == "disabled"
    assert fake.mutation_count == 2
    assert [call[0] for call in fake.calls if call[0] != "GET"] == ["POST", "PUT"]


def test_cli_error_is_closed_and_does_not_echo_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "token"
    secret = "github_pat_" + "z" * 48
    token.write_text(secret, encoding="ascii")
    token.chmod(0o640)
    monkeypatch.setenv(operator.TOKEN_FILE_ENVIRONMENT, str(token))
    assert operator.main(["status"]) == 2
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert "TOKEN_FILE_INVALID" in captured.out
