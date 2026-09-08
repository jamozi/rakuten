"""Freeze approved WordPress source bytes and synchronize their Git record.

The checkpoint path deliberately uses an isolated index and Git plumbing.  It
does not move HEAD or change the caller's index/worktree.  ``sync`` is a
post-publication operation: retrying it only pushes or merges the frozen commit
and never invokes WordPress.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
from typing import Any, Final


SCHEMA: Final = "RAOS_WORDPRESS_PUBLISH_GIT_V1"
SYNC_SCHEMA: Final = "RAOS_WORDPRESS_PUBLISH_GIT_SYNC_V1"
WORKFLOW: Final = ".github/workflows/ci.yml"
BRANCH_PREFIX: Final = "codex/publish-"
FIXTURE_PREFIX: Final = "changes/wordpress-local-preview-v1/fixtures/"
THEME_PREFIX: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/"
)
EDITORIAL_PREFIX: Final = "changes/editorial-portfolio-v3/"
DIRECT_PREFIX: Final = "changes/wordpress-direct-publish-v1/"
FIXTURE_REGISTRIES: Final = frozenset(
    {
        FIXTURE_PREFIX + "pages.json",
        FIXTURE_PREFIX + "posts.json",
        FIXTURE_PREFIX + "production-pages.json",
        FIXTURE_PREFIX + "reader-guides.v1.json",
    }
)
EDITORIAL_SOURCES: Final = frozenset(
    {
        EDITORIAL_PREFIX + "editorial-identities.v1.json",
        EDITORIAL_PREFIX + "local-reader-guides.v1.json",
        EDITORIAL_PREFIX + "market-candidate-audit.v1.json",
        EDITORIAL_PREFIX + "rakuten-parser-boundary.v1.json",
        EDITORIAL_PREFIX + "reader-experience.v1.json",
        EDITORIAL_PREFIX + "reader-measurement-privacy.html",
    }
)
THEME_SUFFIXES: Final = frozenset(
    {
        ".css",
        ".gif",
        ".html",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".php",
        ".png",
        ".svg",
        ".webp",
        ".woff",
        ".woff2",
    }
)
SECRET_NAMES: Final = frozenset(
    {".env", ".secrets", "credential", "credentials", "secret", "secrets"}
)
Runner = Callable[..., subprocess.CompletedProcess[Any]]
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024


class GitFailure(RuntimeError):
    """An internal command failed without exposing its stderr or credentials."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _git(
    root: Path,
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    index: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
    )
    if index is not None:
        environment["GIT_INDEX_FILE"] = os.fspath(index)
    try:
        completed = subprocess.run(
            (
                "git",
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                os.fspath(root),
                *arguments,
            ),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=None if input_bytes is not None else subprocess.DEVNULL,
            check=False,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitFailure("git command unavailable") from exc
    if check and completed.returncode != 0:
        raise GitFailure("git command failed")
    if len(completed.stdout) > 16 * 1024 * 1024:
        raise GitFailure("git output exceeded the bounded limit")
    return completed


def _repository_root(root: Path) -> Path:
    candidate = Path(root).resolve(strict=True)
    if not candidate.is_dir():
        raise ValueError("REPOSITORY_INVALID")
    top = _git(candidate, ("rev-parse", "--show-toplevel")).stdout
    try:
        observed = Path(top.decode("utf-8", errors="strict").strip()).resolve(
            strict=True
        )
    except (OSError, UnicodeError) as exc:
        raise ValueError("REPOSITORY_INVALID") from exc
    if observed != candidate:
        raise ValueError("REPOSITORY_INVALID")
    return candidate


def _snapshot(value: object) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value) is None
    ):
        raise ValueError("SNAPSHOT_ID_INVALID")
    if ".." in value or value.endswith(".lock"):
        raise ValueError("SNAPSHOT_ID_INVALID")
    return value


def _normalized_path(value: object) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 500:
        raise ValueError("PATH_INVALID")
    if "\0" in value or "\\" in value or value.startswith("/"):
        raise ValueError("PATH_INVALID")
    path = PurePosixPath(value)
    if value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("PATH_INVALID")
    folded = {part.casefold() for part in path.parts}
    if folded & SECRET_NAMES or any(part.startswith(".env") for part in folded):
        raise ValueError("PATH_NOT_ALLOWED")
    return value


def _manifest_outputs(root: Path) -> frozenset[str]:
    path = root / "changes/build/manifest.v2.json"
    if not path.is_file() or path.is_symlink():
        return frozenset()
    try:
        document = json.loads(path.read_bytes())
        owners = document["owners"]
        if not isinstance(owners, list):
            return frozenset()
        outputs = {
            row["uri"].removeprefix("repo://")
            for owner in owners
            if isinstance(owner, dict)
            for row in owner.get("outputs", [])
            if isinstance(row, dict)
            and isinstance(row.get("uri"), str)
            and row["uri"].startswith("repo://")
        }
    except KeyError, OSError, TypeError, ValueError, json.JSONDecodeError:
        return frozenset()
    return frozenset(outputs)


def _source_allowed(path: str) -> bool:
    pure = PurePosixPath(path)
    if path == DIRECT_PREFIX + "articles.v1.json":
        return True
    if path.startswith(DIRECT_PREFIX + "articles/"):
        return len(pure.parts) == 4 and pure.suffix == ".html"
    if path in FIXTURE_REGISTRIES or path in EDITORIAL_SOURCES:
        return True
    if path.startswith(FIXTURE_PREFIX + "articles/"):
        return len(pure.parts) == 5 and pure.suffix == ".html"
    if path.startswith(FIXTURE_PREFIX + "pages/"):
        return len(pure.parts) == 5 and pure.suffix == ".html"
    if path.startswith(FIXTURE_PREFIX + "production-pages/"):
        return len(pure.parts) == 5 and pure.suffix == ".html"
    if path.startswith(THEME_PREFIX):
        relative = PurePosixPath(path.removeprefix(THEME_PREFIX))
        return (
            bool(relative.parts)
            and not any(part.startswith(".") for part in relative.parts)
            and relative.suffix.casefold() in THEME_SUFFIXES
        )
    return False


def _path_allowed(path: str, generated: frozenset[str]) -> bool:
    if _source_allowed(path):
        return True
    return path in generated and path.startswith((EDITORIAL_PREFIX, THEME_PREFIX))


def _read_source(root: Path, relative: str) -> tuple[bytes, int]:
    source = root / relative
    try:
        if source.resolve(strict=True) != source:
            raise ValueError("PATH_INVALID")
        descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ValueError("PATH_INVALID") from exc
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_SOURCE_BYTES
        ):
            raise ValueError("PATH_INVALID")
        payload = stream.read(MAX_SOURCE_BYTES + 1)
        after = os.fstat(stream.fileno())
    if (
        len(payload) > MAX_SOURCE_BYTES
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or after.st_size != len(payload)
    ):
        raise ValueError("PATH_CHANGED_DURING_CHECKPOINT")
    return payload, before.st_mode


def _paths(root: Path, values: Sequence[str], *, inspect_files: bool) -> list[str]:
    if isinstance(values, (str, bytes)) or not values:
        raise ValueError("PATHS_REQUIRED")
    generated = _manifest_outputs(root)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        path = _normalized_path(value)
        if path.casefold() in seen:
            raise ValueError("PATH_DUPLICATE")
        seen.add(path.casefold())
        if not _path_allowed(path, generated):
            raise ValueError("PATH_NOT_ALLOWED")
        if inspect_files:
            try:
                _read_source(root, path)
            except FileNotFoundError:
                tracked = _git(
                    root,
                    ("cat-file", "-e", f"HEAD:{path}"),
                    check=False,
                )
                if tracked.returncode != 0:
                    raise ValueError("PATH_MISSING")
        result.append(path)
    return sorted(result)


def _branch_commit(root: Path, branch: str) -> str | None:
    completed = _git(
        root,
        ("show-ref", "--verify", "--hash", f"refs/heads/{branch}"),
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        commit = completed.stdout.decode("ascii", errors="strict").strip()
    except UnicodeError as exc:
        raise GitFailure("invalid branch ref") from exc
    if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
        raise GitFailure("invalid branch ref")
    return commit


def _commit_record(
    root: Path,
    *,
    status: str,
    snapshot_id: str,
    branch: str,
    commit: str,
    tree: str,
    base_commit: str,
    paths: Sequence[str],
    reason: str | None = None,
    checkpoint_action: str | None = None,
) -> dict[str, Any]:
    source = _git(root, ("symbolic-ref", "--quiet", "--short", "HEAD"), check=False)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "snapshot_id": snapshot_id,
        "branch": branch,
        "source_branch": (
            source.stdout.decode("utf-8", errors="replace").strip()
            if source.returncode == 0
            else None
        ),
        "base_commit": base_commit,
        "commit": commit,
        "tree": tree,
        "paths": list(paths),
        "paths_sha256": _digest(list(paths)),
        "publication_authority": False,
    }
    if reason is not None:
        record["reason"] = reason
    if checkpoint_action is not None:
        record["checkpoint_action"] = checkpoint_action
    return record


def _error(
    snapshot_id: object,
    reason: str,
    *,
    branch: str | None = None,
    commit: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "error",
        "snapshot_id": snapshot_id if type(snapshot_id) is str else None,
        "reason": reason,
        "publication_authority": False,
    }
    if branch is not None:
        result["branch"] = branch
    if commit is not None:
        result["commit"] = commit
    return result


def checkpoint(root: Path, paths: Sequence[str], snapshot_id: str) -> dict[str, Any]:
    """Create an immutable selected-path commit without changing HEAD or the index."""
    try:
        repository = _repository_root(Path(root))
        snapshot = _snapshot(snapshot_id)
        branch = BRANCH_PREFIX + snapshot
        selected = _paths(repository, paths, inspect_files=True)
        head = (
            _git(repository, ("rev-parse", "--verify", "HEAD")).stdout.decode().strip()
        )
        head_tree = (
            _git(repository, ("rev-parse", f"{head}^{{tree}}")).stdout.decode().strip()
        )

        with tempfile.TemporaryDirectory(prefix="raos-wordpress-git-") as directory:
            index = Path(directory) / "index"
            _git(repository, ("read-tree", head), index=index)
            index_rows = bytearray()
            for relative in selected:
                source = repository / relative
                if not source.exists():
                    index_rows.extend(f"0 {'0' * 40}\t".encode())
                    index_rows.extend(os.fsencode(relative))
                    index_rows.append(0)
                    continue
                payload, mode_bits = _read_source(repository, relative)
                blob = (
                    _git(
                        repository,
                        ("hash-object", "-w", "--no-filters", "--stdin"),
                        input_bytes=payload,
                    )
                    .stdout.decode("ascii", errors="strict")
                    .strip()
                )
                mode = "100755" if mode_bits & stat.S_IXUSR else "100644"
                index_rows.extend(f"{mode} {blob}\t".encode())
                index_rows.extend(os.fsencode(relative))
                index_rows.append(0)
            _git(
                repository,
                ("update-index", "-z", "--index-info"),
                input_bytes=bytes(index_rows),
                index=index,
            )
            tree = (
                _git(repository, ("write-tree",), index=index)
                .stdout.decode("ascii", errors="strict")
                .strip()
            )

        existing = _branch_commit(repository, branch)
        if existing is not None:
            existing_tree = (
                _git(repository, ("rev-parse", f"{existing}^{{tree}}"))
                .stdout.decode()
                .strip()
            )
            parent = _git(repository, ("rev-parse", f"{existing}^"), check=False)
            body = _git(
                repository, ("show", "-s", "--format=%B", existing)
            ).stdout.decode("utf-8", errors="strict")
            expected_trailer = f"RAOS-WordPress-Paths-SHA256: {_digest(selected)}"
            if (
                parent.returncode != 0
                or parent.stdout.decode().strip() != head
                or existing_tree != tree
                or expected_trailer not in body.splitlines()
            ):
                return _commit_record(
                    repository,
                    status="conflict",
                    snapshot_id=snapshot,
                    branch=branch,
                    commit=existing,
                    tree=existing_tree,
                    base_commit=head,
                    paths=selected,
                    reason="SNAPSHOT_DRIFT",
                )
            return _commit_record(
                repository,
                status="created",
                snapshot_id=snapshot,
                branch=branch,
                commit=existing,
                tree=tree,
                base_commit=head,
                paths=selected,
                checkpoint_action="reused",
            )

        if tree == head_tree:
            return _commit_record(
                repository,
                status="noop",
                snapshot_id=snapshot,
                branch=branch,
                commit=head,
                tree=head_tree,
                base_commit=head,
                paths=selected,
            )

        name = _git(repository, ("config", "--get", "user.name"), check=False)
        email = _git(repository, ("config", "--get", "user.email"), check=False)
        if (
            name.returncode != 0
            or email.returncode != 0
            or not name.stdout.strip()
            or not email.stdout.strip()
        ):
            return _error(snapshot, "GIT_IDENTITY_MISSING", branch=branch)
        message = (
            f"WordPress publication snapshot {snapshot}\n\n"
            f"RAOS-WordPress-Snapshot: {snapshot}\n"
            f"RAOS-WordPress-Paths-SHA256: {_digest(selected)}\n"
        ).encode()
        commit = (
            _git(repository, ("commit-tree", tree, "-p", head), input_bytes=message)
            .stdout.decode("ascii", errors="strict")
            .strip()
        )
        updated = _git(
            repository,
            ("update-ref", f"refs/heads/{branch}", commit, "0" * 40),
            check=False,
        )
        if updated.returncode != 0:
            raced = _branch_commit(repository, branch)
            if raced != commit:
                return _error(snapshot, "BRANCH_CONFLICT", branch=branch, commit=raced)
            commit = raced
        return _commit_record(
            repository,
            status="created",
            snapshot_id=snapshot,
            branch=branch,
            commit=commit,
            tree=tree,
            base_commit=head,
            paths=selected,
        )
    except ValueError as exc:
        return _error(snapshot_id, str(exc))
    except GitFailure, OSError, subprocess.SubprocessError, UnicodeError:
        return _error(snapshot_id, "GIT_OPERATION_FAILED")


def _external(
    root: Path, runner: Runner, command: Sequence[str]
) -> subprocess.CompletedProcess[Any]:
    environment = os.environ.copy()
    environment["GH_PROMPT_DISABLED"] = "1"
    try:
        result = runner(
            tuple(command),
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitFailure("external command unavailable") from exc
    if result.returncode != 0:
        raise GitFailure("external command failed")
    raw = result.stdout.encode() if isinstance(result.stdout, str) else result.stdout
    if not isinstance(raw, bytes) or len(raw) > 16 * 1024 * 1024:
        raise GitFailure("external output invalid")
    return result


def _json_external(root: Path, runner: Runner, command: Sequence[str]) -> Any:
    result = _external(root, runner, command)
    raw = result.stdout.encode() if isinstance(result.stdout, str) else result.stdout
    try:
        return json.loads(raw)
    except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise GitFailure("external JSON invalid") from exc


def _sync_result(
    checkpoint_record: Mapping[str, Any],
    *,
    status: str,
    phase: str,
    reason: str | None = None,
    **values: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": SYNC_SCHEMA,
        "status": status,
        "phase": phase,
        "snapshot_id": checkpoint_record.get("snapshot_id"),
        "branch": checkpoint_record.get("branch"),
        "commit": checkpoint_record.get("commit"),
        "tree": checkpoint_record.get("tree"),
        "publication": "ALREADY_COMPLETED_NO_REPUBLISH",
    }
    if reason is not None:
        result["reason"] = reason
    result.update(values)
    if status in {"pending", "ci_failed", "error"}:
        result["resume"] = "CALL_SYNC_WITH_SAME_CHECKPOINT"
    return result


def _validate_checkpoint(root: Path, value: Mapping[str, Any]) -> None:
    if value.get("schema") != SCHEMA or value.get("publication_authority") is not False:
        raise ValueError("CHECKPOINT_INVALID")
    snapshot = _snapshot(value.get("snapshot_id"))
    if value.get("branch") != BRANCH_PREFIX + snapshot:
        raise ValueError("CHECKPOINT_INVALID")
    raw_paths = value.get("paths")
    if not isinstance(raw_paths, Sequence) or isinstance(raw_paths, (str, bytes)):
        raise ValueError("CHECKPOINT_INVALID")
    selected = _paths(root, raw_paths, inspect_files=False)
    if value.get("paths_sha256") != _digest(selected):
        raise ValueError("CHECKPOINT_INVALID")
    for key in ("base_commit", "commit", "tree"):
        if (
            type(value.get(key)) is not str
            or re.fullmatch(r"[0-9a-f]{40,64}", value[key]) is None
        ):
            raise ValueError("CHECKPOINT_INVALID")
    commit = value["commit"]
    tree = _git(root, ("rev-parse", f"{commit}^{{tree}}"), check=False)
    if tree.returncode != 0 or tree.stdout.decode().strip() != value["tree"]:
        raise ValueError("CHECKPOINT_INVALID")
    if value.get("status") == "noop":
        if commit != value["base_commit"]:
            raise ValueError("CHECKPOINT_INVALID")
        return
    if value.get("status") != "created":
        raise ValueError("CHECKPOINT_INVALID")
    if _branch_commit(root, value["branch"]) != commit:
        raise ValueError("CHECKPOINT_BRANCH_DRIFT")
    parent = _git(root, ("rev-parse", f"{commit}^"), check=False)
    if parent.returncode != 0 or parent.stdout.decode().strip() != value["base_commit"]:
        raise ValueError("CHECKPOINT_INVALID")
    changed_raw = _git(
        root,
        (
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            value["base_commit"],
            commit,
        ),
    ).stdout
    try:
        changed = {
            row.decode("utf-8", errors="strict")
            for row in changed_raw.split(b"\0")
            if row
        }
    except UnicodeError as exc:
        raise ValueError("CHECKPOINT_INVALID") from exc
    if not changed or not changed.issubset(set(selected)):
        raise ValueError("CHECKPOINT_SCOPE_INVALID")
    body = _git(root, ("show", "-s", "--format=%B", commit)).stdout.decode(
        "utf-8", errors="strict"
    )
    if f"RAOS-WordPress-Paths-SHA256: {_digest(selected)}" not in body.splitlines():
        raise ValueError("CHECKPOINT_INVALID")


def _pr_fields() -> str:
    return "number,url,state,isDraft,headRefOid,baseRefName,mergedAt"


def sync(
    root: Path,
    checkpoint: Mapping[str, Any],
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Push and merge the frozen snapshot, or return a safe resumable state."""
    external_runner = subprocess.run if runner is None else runner
    try:
        repository_root = _repository_root(Path(root))
        if not isinstance(checkpoint, Mapping):
            raise ValueError("CHECKPOINT_INVALID")
        _validate_checkpoint(repository_root, checkpoint)
        if checkpoint["status"] == "noop":
            return _sync_result(checkpoint, status="noop", phase="complete")

        remote = _git(repository_root, ("remote", "get-url", "origin"), check=False)
        if remote.returncode != 0 or not remote.stdout.strip():
            return _sync_result(
                checkpoint, status="error", phase="push", reason="ORIGIN_UNAVAILABLE"
            )
        pushed = _git(
            repository_root,
            (
                "push",
                "--porcelain",
                "origin",
                f"{checkpoint['commit']}:refs/heads/{checkpoint['branch']}",
            ),
            check=False,
        )
        if pushed.returncode != 0:
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="push",
                reason="REMOTE_BRANCH_CONFLICT",
            )
        remote_ref = _git(
            repository_root,
            ("ls-remote", "--heads", "origin", f"refs/heads/{checkpoint['branch']}"),
            check=False,
        )
        if (
            remote_ref.returncode != 0
            or not remote_ref.stdout
            or remote_ref.stdout.split(None, 1)[0].decode() != checkpoint["commit"]
        ):
            return _sync_result(
                checkpoint,
                status="error",
                phase="push",
                reason="REMOTE_HEAD_UNVERIFIED",
            )

        repository = _json_external(
            repository_root,
            external_runner,
            (
                "gh",
                "repo",
                "view",
                "--json",
                "nameWithOwner,url,defaultBranchRef",
            ),
        )
        if not isinstance(repository, dict):
            raise ValueError("REPOSITORY_IDENTITY_INVALID")
        name = repository.get("nameWithOwner")
        default = repository.get("defaultBranchRef")
        base = default.get("name") if isinstance(default, dict) else None
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) is None
            or not isinstance(base, str)
            or re.fullmatch(r"[A-Za-z0-9._/-]+", base) is None
            or base == checkpoint["branch"]
        ):
            raise ValueError("REPOSITORY_IDENTITY_INVALID")

        pull_requests = _json_external(
            repository_root,
            external_runner,
            (
                "gh",
                "pr",
                "list",
                "--repo",
                name,
                "--head",
                checkpoint["branch"],
                "--state",
                "all",
                "--json",
                _pr_fields(),
            ),
        )
        if not isinstance(pull_requests, list) or len(pull_requests) > 1:
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="pull_request",
                reason="PR_AMBIGUOUS",
            )
        if not pull_requests:
            title = f"Record WordPress publication {checkpoint['snapshot_id']}"
            body = (
                "Records the exact Git tree used by the approved WordPress publication.\n\n"
                f"Snapshot: `{checkpoint['snapshot_id']}`\n"
                f"Commit: `{checkpoint['commit']}`\n"
                f"Tree: `{checkpoint['tree']}`\n\n"
                "Publication already completed. Retrying Git synchronization must not republish.\n"
            )
            with tempfile.TemporaryDirectory(prefix="raos-wordpress-pr-") as directory:
                body_file = Path(directory) / "body.md"
                body_file.write_text(body, encoding="utf-8")
                created = _external(
                    repository_root,
                    external_runner,
                    (
                        "gh",
                        "pr",
                        "create",
                        "--repo",
                        name,
                        "--base",
                        base,
                        "--head",
                        checkpoint["branch"],
                        "--title",
                        title,
                        "--body-file",
                        os.fspath(body_file),
                    ),
                )
                raw_url = (
                    created.stdout.encode()
                    if isinstance(created.stdout, str)
                    else created.stdout
                )
                url = raw_url.decode("utf-8", errors="strict").strip()
            pull = _json_external(
                repository_root,
                external_runner,
                ("gh", "pr", "view", url, "--repo", name, "--json", _pr_fields()),
            )
        else:
            pull = pull_requests[0]
        if not isinstance(pull, dict) or type(pull.get("number")) is not int:
            raise ValueError("PR_INVALID")
        pr_result = {"number": pull["number"], "url": pull.get("url")}
        if pull.get("headRefOid") != checkpoint["commit"]:
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="pull_request",
                reason="PR_HEAD_MISMATCH",
                pr=pr_result,
            )
        if pull.get("baseRefName") != base:
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="pull_request",
                reason="PR_BASE_MISMATCH",
                pr=pr_result,
            )
        if pull.get("mergedAt") is not None or pull.get("state") == "MERGED":
            return _sync_result(
                checkpoint,
                status="merged",
                phase="complete",
                pr=pr_result,
                final_integration="previously_verified",
            )
        if pull.get("state") != "OPEN" or pull.get("isDraft") is not False:
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="pull_request",
                reason="PR_NOT_READY",
                pr=pr_result,
            )

        runs_payload = _json_external(
            repository_root,
            external_runner,
            (
                "gh",
                "api",
                f"repos/{name}/actions/runs?head_sha={checkpoint['commit']}&per_page=100",
            ),
        )
        runs = (
            [
                row
                for row in runs_payload.get("workflow_runs", [])
                if isinstance(row, dict)
                and row.get("head_sha") == checkpoint["commit"]
                and row.get("path") == WORKFLOW
                and row.get("event") == "pull_request"
            ]
            if isinstance(runs_payload, dict)
            else []
        )
        if not runs:
            return _sync_result(
                checkpoint,
                status="pending",
                phase="final_integration",
                pr=pr_result,
                final_integration="not_started",
            )
        latest = max(
            runs,
            key=lambda row: (row.get("run_number", 0), row.get("run_attempt", 0)),
        )
        ci = {
            "run_id": latest.get("id"),
            "run_attempt": latest.get("run_attempt"),
            "url": latest.get("html_url"),
        }
        if latest.get("status") != "completed":
            return _sync_result(
                checkpoint,
                status="pending",
                phase="final_integration",
                pr=pr_result,
                ci=ci,
                final_integration="pending",
            )
        if latest.get("conclusion") != "success":
            return _sync_result(
                checkpoint,
                status="ci_failed",
                phase="final_integration",
                reason="CI_FAILED",
                pr=pr_result,
                ci=ci,
                final_integration=latest.get("conclusion"),
            )
        run_id = latest.get("id")
        attempt = latest.get("run_attempt", 1)
        if type(run_id) is not int or type(attempt) is not int:
            raise ValueError("CI_RESULT_INVALID")
        pages = _json_external(
            repository_root,
            external_runner,
            (
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{name}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100",
            ),
        )
        jobs = [
            job
            for page in (pages if isinstance(pages, list) else [])
            if isinstance(page, dict) and isinstance(page.get("jobs"), list)
            for job in page["jobs"]
            if isinstance(job, dict)
        ]
        final = [job for job in jobs if job.get("name") == "Final Integration"]
        if len(final) != 1:
            return _sync_result(
                checkpoint,
                status="pending",
                phase="final_integration",
                reason="FINAL_INTEGRATION_UNAVAILABLE",
                pr=pr_result,
                ci=ci,
                final_integration="unavailable",
            )
        gate = final[0]
        if (
            gate.get("run_id") != run_id
            or gate.get("run_attempt") != attempt
            or gate.get("head_sha") != checkpoint["commit"]
        ):
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="final_integration",
                reason="FINAL_INTEGRATION_IDENTITY_MISMATCH",
                pr=pr_result,
                ci=ci,
            )
        if gate.get("status") != "completed":
            return _sync_result(
                checkpoint,
                status="pending",
                phase="final_integration",
                pr=pr_result,
                ci=ci,
                final_integration="pending",
            )
        if gate.get("conclusion") != "success":
            return _sync_result(
                checkpoint,
                status="ci_failed",
                phase="final_integration",
                reason="FINAL_INTEGRATION_FAILED",
                pr=pr_result,
                ci=ci,
                final_integration=gate.get("conclusion"),
            )

        current = _json_external(
            repository_root,
            external_runner,
            (
                "gh",
                "pr",
                "view",
                str(pull["number"]),
                "--repo",
                name,
                "--json",
                _pr_fields(),
            ),
        )
        if (
            not isinstance(current, dict)
            or current.get("headRefOid") != checkpoint["commit"]
            or current.get("baseRefName") != base
            or current.get("state") != "OPEN"
            or current.get("isDraft") is not False
        ):
            return _sync_result(
                checkpoint,
                status="conflict",
                phase="merge",
                reason="PR_CHANGED_BEFORE_MERGE",
                pr=pr_result,
                ci=ci,
            )
        _external(
            repository_root,
            external_runner,
            (
                "gh",
                "pr",
                "merge",
                str(pull["number"]),
                "--repo",
                name,
                "--squash",
                "--match-head-commit",
                checkpoint["commit"],
            ),
        )
        merged = _json_external(
            repository_root,
            external_runner,
            (
                "gh",
                "pr",
                "view",
                str(pull["number"]),
                "--repo",
                name,
                "--json",
                _pr_fields(),
            ),
        )
        if not isinstance(merged, dict) or merged.get("mergedAt") is None:
            return _sync_result(
                checkpoint,
                status="pending",
                phase="merge",
                pr=pr_result,
                ci=ci,
                final_integration="success",
            )
        return _sync_result(
            checkpoint,
            status="merged",
            phase="complete",
            pr=pr_result,
            ci=ci,
            final_integration="success",
        )
    except ValueError as exc:
        return _sync_result(
            checkpoint, status="error", phase="validation", reason=str(exc)
        )
    except GitFailure, OSError, subprocess.SubprocessError, UnicodeError:
        return _sync_result(
            checkpoint, status="error", phase="external", reason="GIT_SYNC_FAILED"
        )
