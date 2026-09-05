"""Original check results and reuse decisions; never approval or a new audit ledger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import stat
import subprocess
from typing import Any

SCHEMA = "RAOS_WORDPRESS_CHECK_RESULT_V2"
REPOSITORY = "jamozi/rakuten"
WORKFLOW = ".github/workflows/ci.yml"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode()


def source_fingerprint(root: Path) -> str:
    paths = subprocess.run(
        ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"),
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    rows = []
    for encoded in sorted(set(paths)):
        if not encoded:
            continue
        name = encoded.decode()
        if name.startswith(
            (".secrets/", "output/", "docs/canonical/", "docs/upstream/", "zip/")
        ):
            continue
        path = root / name
        if not path.exists():
            rows.append((name, "DELETED"))
        elif path.is_symlink():
            raise ValueError("verification input is a symlink")
        else:
            rows.append((name, digest(path.read_bytes())))
    return digest(canonical(rows))


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
        raise ValueError("verification output is not a regular file")
    return path.read_bytes()


def reusable(
    result: Mapping[str, Any],
    *,
    check_id: str,
    inputs: Mapping[str, Any],
    root: Path,
    now: datetime,
    max_age: timedelta = timedelta(hours=24),
) -> bool:
    try:
        started = datetime.fromisoformat(result["started_at"])
        captured = datetime.fromisoformat(result["captured_at"])
        output = root / result["output"]
        return bool(
            result.get("schema") == SCHEMA
            and result.get("check_id") == check_id
            and result.get("inputs") == dict(inputs)
            and type(result.get("exit_code")) is int
            and result["exit_code"] == 0
            and started.tzinfo is not None
            and captured.tzinfo is not None
            and started <= captured <= now <= captured + max_age
            and output.resolve().is_relative_to((root / "output").resolve())
            and digest(read_regular(output)) == result["output_sha256"]
        )
    except OSError, KeyError, TypeError, ValueError:
        return False


def run_check(
    root: Path,
    command: Sequence[str],
    *,
    check_id: str,
    inputs: Mapping[str, Any],
    directory: Path,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    output = directory / f"{check_id}-{started.strftime('%Y%m%dT%H%M%S%f')}.log"
    with output.open("xb") as stream:
        result = subprocess.run(
            command,
            cwd=root,
            env=dict(environment),
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    record = {
        "schema": SCHEMA,
        "check_id": check_id,
        "inputs": dict(inputs),
        "command": list(command),
        "exit_code": result.returncode,
        "started_at": started.isoformat(),
        "captured_at": datetime.now(UTC).isoformat(),
        "output": output.relative_to(root).as_posix(),
        "output_sha256": digest(read_regular(output)),
    }
    result_path = output.with_suffix(".result.json")
    record["result_file"] = result_path.relative_to(root).as_posix()
    with result_path.open("xb") as stream:
        stream.write(canonical(record))
    return record


def required_ci(root: Path) -> dict[str, Any]:
    """Read the trusted workflow; squash merges require proven tree equality."""
    if subprocess.run(
        ("git", "diff", "--quiet", "HEAD"), cwd=root, check=False
    ).returncode:
        raise ValueError("required CI cannot verify uncommitted source changes")
    if subprocess.run(
        ("git", "ls-files", "-z", "--others", "--exclude-standard"),
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout:
        raise ValueError("required CI cannot verify untracked source files")

    def api(path: str) -> Any:
        return json.loads(
            subprocess.run(
                ("gh", "api", f"repos/{REPOSITORY}/{path}"),
                cwd=root,
                capture_output=True,
                check=True,
            ).stdout
        )

    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tested_head = head
    raw = api(f"actions/runs?head_sha={head}&per_page=100")
    runs = [
        row
        for row in raw["workflow_runs"]
        if row.get("head_sha") == head
        and row.get("path") == WORKFLOW
        and row.get("event") in {"pull_request", "push", "workflow_dispatch"}
    ]
    if not runs:
        # GitHub squash merging changes the commit ID, not necessarily its tree.
        # Only a merged PR whose exact head has the same entire tree can supply CI.
        pulls = api(f"commits/{head}/pulls?per_page=100")
        tree = api(f"git/commits/{head}")["tree"]["sha"]
        for pull in pulls:
            if not pull.get("merged_at") or pull.get("merge_commit_sha") != head:
                continue
            candidate = pull["head"]["sha"]
            if api(f"git/commits/{candidate}")["tree"]["sha"] != tree:
                continue
            candidates = api(f"actions/runs?head_sha={candidate}&per_page=100")[
                "workflow_runs"
            ]
            runs = [
                row
                for row in candidates
                if row.get("head_sha") == candidate
                and row.get("path") == WORKFLOW
                and row.get("event") == "pull_request"
            ]
            if runs:
                tested_head = candidate
                break
        if not runs:
            raise ValueError("required CI has not executed for this source tree")
    latest = max(runs, key=lambda row: (row["run_number"], row.get("run_attempt", 1)))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ValueError("required CI is not successful for this commit")
    pages = json.loads(
        subprocess.run(
            (
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{REPOSITORY}/actions/runs/{latest['id']}/attempts/{latest.get('run_attempt', 1)}/jobs?per_page=100",
            ),
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
    )
    jobs = [
        job
        for page in (pages if isinstance(pages, list) else [pages])
        for job in page["jobs"]
    ]
    final = [row for row in jobs if row.get("name") == "Final Integration"]
    if len(final) != 1 or final[0].get("conclusion") != "success":
        raise ValueError("Final Integration has not succeeded")
    return {
        "schema": "RAOS_WORDPRESS_REQUIRED_CI_V2",
        "repository": REPOSITORY,
        "head_sha": head,
        "tested_head_sha": tested_head,
        "binding": "EXACT_COMMIT" if tested_head == head else "MERGED_IDENTICAL_TREE",
        "workflow": WORKFLOW,
        "run_id": latest["id"],
        "run_attempt": latest.get("run_attempt", 1),
        "conclusion": "success",
        "final_integration": "success",
        "url": latest["html_url"],
    }
