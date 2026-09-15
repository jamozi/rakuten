"""Owner-private I/O for the Rakuten price refresh (KS-020).

Contains the only network call (one itemCode GET per plan entry, behind an
injected transport), the credential reader, the 0600 private store under the
owner checkout ``.secrets`` directory, and the tracked-file leak scan. Nothing
here prints or returns credential values.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import ssl
import stat
import subprocess
import time
from typing import Any, Final, Protocol
from urllib.parse import quote

from raos.domain.editorial.rakuten_price_refresh import (
    API_HOST,
    CREDENTIAL_PROFILE,
    CREDENTIAL_RELATIVE,
    MAX_CACHE_AGE,
    MAX_RESPONSE_BYTES,
    MIN_REQUEST_INTERVAL_SECONDS,
    OBSERVATION_SCHEMA,
    PRIVATE_ROOT_RELATIVE,
    PURGED_SCHEMA,
    RUN_ID_PATTERN,
    UTC,
    RefreshError,
    contextual_leaks,
    fail,
    iso,
    leak_needles,
    parse_time,
    redact_approval,
    request_path,
    require_run_id,
    sha256_hex,
    validate_approval,
    validate_overlay,
)

USER_AGENT: Final = "RAOS-KS020-price-refresh/1"
CONNECT_TIMEOUT_SECONDS: Final = 10.0
MAX_CREDENTIAL_BYTES: Final = 4096
MAX_PRIVATE_JSON_BYTES: Final = 8_000_000
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
# scripts/raos_wordpress_direct_publish.py PRIVATE: candidate directories named by candidate_id.
OWNER_DIRECT_CANDIDATE_RELATIVE: Final = ".secrets/wordpress-mcp/owner-direct-v1"


@dataclass(frozen=True, slots=True, repr=False)
class RefreshCredentials:
    application_id: str
    access_key: str

    def __post_init__(self) -> None:
        for value in (self.application_id, self.access_key):
            if (
                type(value) is not str
                or not 1 <= len(value) <= 256
                or any(ord(c) < 0x21 or ord(c) > 0x7E for c in value)
            ):
                fail("CREDENTIAL_UNSAFE")

    def __repr__(self) -> str:
        return "RefreshCredentials(<redacted>)"

    __str__ = __repr__

    def reflections(self) -> tuple[bytes, ...]:
        forms = set()
        for value in (self.application_id, self.access_key):
            forms.add(value.encode())
            forms.add(quote(value, safe="").encode())
        return tuple(sorted(forms))


def _read_private_bytes(path: Path, maximum: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        fail("PRIVATE_FILE_UNAVAILABLE")
    except OSError:
        fail("PRIVATE_FILE_UNSAFE")
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != PRIVATE_FILE_MODE
            or info.st_nlink != 1
            or not 1 <= info.st_size <= maximum
        ):
            fail("PRIVATE_FILE_UNSAFE")
        raw = os.read(descriptor, info.st_size + 1)
        if len(raw) != info.st_size:
            fail("PRIVATE_FILE_UNSAFE")
        return raw
    finally:
        os.close(descriptor)


def read_refresh_credentials(owner_checkout: Path) -> RefreshCredentials:
    """Read application_id / access_key only; affiliate_id is never loaded into use."""
    try:
        raw = _read_private_bytes(
            owner_checkout / CREDENTIAL_RELATIVE, MAX_CREDENTIAL_BYTES
        )
    except ValueError as error:
        code = getattr(error, "code", "")
        fail(
            "CREDENTIAL_UNAVAILABLE"
            if code == "PRIVATE_FILE_UNAVAILABLE"
            else "CREDENTIAL_UNSAFE"
        )
    try:
        document = json.loads(raw)
    except ValueError:
        fail("CREDENTIAL_UNSAFE")
    if (
        not isinstance(document, dict)
        or document.get("profile") != CREDENTIAL_PROFILE
        or not isinstance(document.get("application_id"), str)
        or not isinstance(document.get("access_key"), str)
    ):
        fail("CREDENTIAL_UNSAFE")
    return RefreshCredentials(document["application_id"], document["access_key"])


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpResult:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class Transport(Protocol):
    def get(
        self, *, host: str, path: str, headers: Mapping[str, str], max_bytes: int
    ) -> HttpResult: ...


class SystemHttpsTransport:
    """TLS >= 1.2, certificate and hostname verified, no proxy, never follows redirects."""

    def get(
        self, *, host: str, path: str, headers: Mapping[str, str], max_bytes: int
    ) -> HttpResult:
        if host != API_HOST:
            fail("HOST_NOT_ALLOWED")
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        connection = http.client.HTTPSConnection(
            host, 443, timeout=CONNECT_TIMEOUT_SECONDS, context=context
        )
        try:
            connection.request("GET", path, headers=dict(headers))
            response = connection.getresponse()
            body = response.read(max_bytes + 1)
            return HttpResult(response.status, tuple(response.getheaders()), body)
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class FetchedObservation:
    http_status: int
    body: str | None
    observed_at: datetime


class PriceRefreshClient:
    def __init__(
        self,
        transport: Transport,
        credentials: RefreshCredentials,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._credentials = credentials
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._last: float | None = None

    def __repr__(self) -> str:
        return "PriceRefreshClient(<redacted>)"

    def fetch(self, item_code: str) -> FetchedObservation:
        path = request_path(item_code, self._credentials.application_id)
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
            "User-Agent": USER_AGENT,
            "accessKey": self._credentials.access_key,
        }
        if self._last is not None:
            wait = MIN_REQUEST_INTERVAL_SECONDS - (self._monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._monotonic()
        observed_at = self._clock()
        try:
            result = self._transport.get(
                host=API_HOST, path=path, headers=headers, max_bytes=MAX_RESPONSE_BYTES
            )
        except BaseException as error:  # noqa: BLE001 - never surface transport text (may echo the URL)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            return FetchedObservation(0, None, observed_at)
        self._last = self._monotonic()
        lowered = {k.lower(): v for k, v in result.headers}
        if 300 <= result.status < 400 or "location" in lowered:
            fail("RAKUTEN_REDIRECT_REFUSED")
        if len(result.body) > MAX_RESPONSE_BYTES:
            fail("RAKUTEN_RESPONSE_TOO_LARGE")
        header_bytes = "\n".join(v for _k, v in result.headers).encode(
            "utf-8", "replace"
        )
        if any(
            secret in result.body or secret in header_bytes
            for secret in self._credentials.reflections()
        ):
            fail("RAKUTEN_CREDENTIAL_REFLECTED")
        if result.status != 200:
            # Error bodies (and 429/5xx in particular) are never persisted.
            return FetchedObservation(result.status, None, observed_at)
        content_type = lowered.get("content-type", "")
        if not content_type.split(";")[0].strip().lower() == "application/json":
            return FetchedObservation(200, None, observed_at)
        try:
            text = result.body.decode("utf-8")
        except UnicodeDecodeError:
            return FetchedObservation(200, None, observed_at)
        return FetchedObservation(200, text, observed_at)


def observation_record(
    run_id: str, offer_id: str, item_code: str, fetched: FetchedObservation
) -> dict[str, Any]:
    return {
        "schema": OBSERVATION_SCHEMA,
        "run_id": require_run_id(run_id),
        "offer_id": offer_id,
        "item_code": item_code,
        "http_status": fetched.http_status,
        "observed_at": iso(fetched.observed_at),
        "body_sha256": sha256_hex(fetched.body.encode("utf-8"))
        if fetched.body is not None
        else None,
        "body": fetched.body,
    }


# ---------------------------------------------------------------------------
# Private store
# ---------------------------------------------------------------------------

GitRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def _git(
    root: Path, *args: str, runner: GitRunner = subprocess.run
) -> subprocess.CompletedProcess[bytes]:
    return runner(["git", "-C", str(root), *args], capture_output=True, check=False)


class PrivateStore:
    """``<owner checkout>/.secrets/rakuten-price-refresh/<run_id>/`` (dirs 0700, files 0600)."""

    def __init__(
        self, owner_checkout: Path, *, runner: GitRunner = subprocess.run
    ) -> None:
        self._runner = runner
        try:
            valid = (
                owner_checkout.is_absolute()
                and owner_checkout.is_dir()
                and not owner_checkout.is_symlink()
                and owner_checkout.resolve(strict=True) == owner_checkout
                and (owner_checkout / ".secrets").is_dir()
                and not (owner_checkout / ".secrets").is_symlink()
            )
        except OSError:
            valid = False
        if not valid:
            fail("OWNER_CHECKOUT_INVALID")
        self.owner_checkout = owner_checkout
        self.root = owner_checkout / PRIVATE_ROOT_RELATIVE

    def run_directory(self, run_id: str) -> Path:
        return self.root / require_run_id(run_id)

    def require_untracked_ignored(self, path: Path) -> None:
        relative = path.relative_to(self.owner_checkout).as_posix()
        ignored = _git(
            self.owner_checkout,
            "check-ignore",
            "-q",
            "--no-index",
            "--",
            relative,
            runner=self._runner,
        )
        tracked = _git(
            self.owner_checkout,
            "ls-files",
            "--error-unmatch",
            "--",
            relative,
            runner=self._runner,
        )
        if ignored.returncode != 0 or tracked.returncode == 0:
            fail("PRIVATE_PATH_NOT_GIT_IGNORED")

    def _ensure_directory(self, directory: Path) -> None:
        current = self.owner_checkout / ".secrets"
        for part in directory.relative_to(current).parts:
            current = current / part
            if current.is_symlink():
                fail("PRIVATE_PATH_UNSAFE")
            if not current.exists():
                current.mkdir(mode=PRIVATE_DIRECTORY_MODE)
            if (
                not current.is_dir()
                or stat.S_IMODE(current.stat().st_mode) != PRIVATE_DIRECTORY_MODE
            ):
                fail("PRIVATE_PATH_UNSAFE")

    def write_json(self, path: Path, value: object, *, replace: bool = False) -> None:
        if self.root not in path.parents:
            fail("PRIVATE_PATH_UNSAFE")
        self.require_untracked_ignored(path)
        self._ensure_directory(path.parent)
        payload = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        target = path.with_name(path.name + ".tmp") if replace else path
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(target, flags, PRIVATE_FILE_MODE)
        except FileExistsError:
            fail("PRIVATE_FILE_EXISTS")
        try:
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if replace:
            os.replace(target, path)

    def read_json(self, path: Path) -> Any:
        if self.root not in path.parents:
            fail("PRIVATE_PATH_UNSAFE")
        return json.loads(_read_private_bytes(path, MAX_PRIVATE_JSON_BYTES))

    def raw_records(self, run_id: str) -> list[dict[str, Any]]:
        directory = self.run_directory(run_id) / "raw"
        if not directory.is_dir() or directory.is_symlink():
            fail("RAW_OBSERVATIONS_MISSING")
        return [self.read_json(p) for p in sorted(directory.glob("*.json"))]

    def delete_raw(self, run_id: str) -> int:
        directory = self.run_directory(run_id) / "raw"
        if not directory.exists():
            return 0
        if directory.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        count = len(list(directory.iterdir()))
        shutil.rmtree(directory)
        return count

    def run_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            p.name for p in self.root.iterdir() if p.is_dir() and not p.is_symlink()
        )

    def owner_direct_candidates_containing(self, needles: Sequence[str]) -> list[str]:
        """Candidate ids whose candidate.json or journal.json carries any needle (raw or JSON-escaped)."""
        base = self.owner_checkout / OWNER_DIRECT_CANDIDATE_RELATIVE
        if base.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        if not base.is_dir() or not needles:
            return []
        variants = {n.encode("utf-8") for n in needles} | {
            json.dumps(n)[1:-1].encode("ascii") for n in needles
        }
        found = []
        for directory in sorted(base.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                continue
            for name in ("candidate.json", "journal.json"):
                path = directory / name
                if path.is_file() and not path.is_symlink():
                    payload = path.read_bytes()
                    if any(v in payload for v in variants):
                        found.append(directory.name)
                        break
        return found

    def delete_owner_direct_candidate(self, candidate_id: object) -> bool:
        """Delete one publisher candidate directory (injected bodies, runtime, theme, journal)."""
        if not isinstance(candidate_id, str) or len(candidate_id) != 64:
            return False
        if any(c not in "0123456789abcdef" for c in candidate_id):
            return False
        base = self.owner_checkout / OWNER_DIRECT_CANDIDATE_RELATIVE
        current = self.owner_checkout
        for part in PurePosixPath(OWNER_DIRECT_CANDIDATE_RELATIVE).parts:
            current = current / part
            if current.is_symlink():
                fail("PRIVATE_PATH_UNSAFE")
        directory = base / candidate_id
        if directory.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True


# Local values are purged but the run is not finished: WordPress still serves the injected
# values (no purge publish recorded), or the approval still names price-recoverable
# candidate ids (a purge publish recorded after purge-expired). Both block fetch and gate.
UNFINISHED_PURGE_STATUSES: Final = frozenset({"PUBLISHED_NOT_PURGED", "REDACTION_PENDING"})
# The only other way out of PUBLISHED_NOT_PURGED: the owner records, after purge-expired,
# that WordPress no longer serves the run's values although no purge publish was recorded
# (for example the post was restored or withdrawn by hand). Contract §5.
INCIDENT_RESOLUTION_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_OVERLAY_INCIDENT_RESOLUTION_V1"
INCIDENT_RESOLUTION_FILE: Final = "incident-resolution.v1.json"
INCIDENT_RESOLUTIONS: Final = frozenset(
    {"WORDPRESS_RESTORED_OUTSIDE_PUBLISHER", "WORDPRESS_POSTS_WITHDRAWN"}
)


def incident_resolution(store: PrivateStore, run_id: str) -> dict[str, Any] | None:
    path = store.run_directory(run_id) / INCIDENT_RESOLUTION_FILE
    if not path.exists():
        return None
    record = store.read_json(path)
    if (
        not isinstance(record, dict)
        or set(record) != {"schema", "run_id", "resolution", "recorded_at"}
        or record["schema"] != INCIDENT_RESOLUTION_SCHEMA
        or record["run_id"] != run_id
        or record["resolution"] not in INCIDENT_RESOLUTIONS
    ):
        fail("INCIDENT_RESOLUTION_INVALID")
    parse_time(record["recorded_at"])
    return record


def run_status(store: PrivateStore, run_id: str) -> tuple[str, datetime | None]:
    """PURGED / PUBLISHED_NOT_PURGED / REDACTION_PENDING / EMPTY / DATED (with the earliest
    expiry) / UNDATED (records unreadable or invalid)."""
    directory = store.run_directory(run_id)
    has_raw = (directory / "raw").exists()
    overlay_path, approval_path = (
        directory / "overlay.v1.json",
        directory / "approval.v1.json",
    )
    try:
        overlay = store.read_json(overlay_path) if overlay_path.exists() else None
        approval = store.read_json(approval_path) if approval_path.exists() else None
        if isinstance(overlay, dict) and overlay.get("schema") == PURGED_SCHEMA:
            if has_raw:
                return "UNDATED", None
            if isinstance(approval, dict):
                if (
                    approval.get("publish") is not None
                    and approval.get("purge_publish") is None
                    and incident_resolution(store, run_id) is None
                ):
                    return "PUBLISHED_NOT_PURGED", None
                if redact_approval(approval) != approval:
                    return "REDACTION_PENDING", None
            return "PURGED", None
        if overlay is not None:
            validate_overlay(overlay)
            return "DATED", parse_time(overlay["cache_expires_at"])
        if approval is not None:
            # No overlay yet: every observation is later than approval, so this expiry is earlier.
            return "DATED", parse_time(
                validate_approval(approval, run_id)["approved_at"]
            ) + MAX_CACHE_AGE
    except RefreshError, OSError, ValueError, KeyError, TypeError:
        return "UNDATED", None
    return ("UNDATED", None) if has_raw else ("EMPTY", None)


def expired_unpurged_runs(
    store: PrivateStore, now: datetime, *, exclude: str | None = None
) -> list[str]:
    stale = []
    for run_id in store.run_ids():
        if run_id == exclude or RUN_ID_PATTERN.fullmatch(run_id) is None:
            continue
        status, expires = run_status(store, run_id)
        if status == "UNDATED" or status in UNFINISHED_PURGE_STATUSES or (
            status == "DATED" and expires is not None and now >= expires
        ):
            stale.append(run_id)
    return stale


# ---------------------------------------------------------------------------
# Tracked-file leak scan
# ---------------------------------------------------------------------------


HISTORY_REVISION_CHUNK: Final = 200


def _grep_paths(
    repository: Path,
    patterns: Iterable[str],
    mode: str,
    runner: GitRunner,
    revisions: Sequence[str] = (),
) -> list[str]:
    arguments = ["grep", "-z", "-l", "-I", "-F"]
    if mode == "worktree":
        arguments.append("--untracked")
    elif mode == "index":
        arguments.append("--cached")
    for pattern in patterns:
        arguments.extend(["-e", pattern])
    if mode == "history":
        arguments.extend([*revisions, "--"])
    result = _git(repository, *arguments, runner=runner)
    if result.returncode not in (0, 1):
        fail("GIT_GREP_FAILED")
    return sorted(
        {p.decode("utf-8", "surrogateescape") for p in result.stdout.split(b"\0") if p}
    )


def scan_repository_for_overlay(
    repository: Path,
    overlay: Mapping[str, Any],
    approval: Mapping[str, Any] | None = None,
    *,
    runner: GitRunner = subprocess.run,
) -> list[str]:
    """Return ``<code>:<mode>:<path>`` for tracked or untracked-not-ignored files (and the index)."""
    if (
        _git(repository, "rev-parse", "--is-inside-work-tree", runner=runner).returncode
        != 0
    ):
        fail("REPOSITORY_INVALID")
    exact = leak_needles(overlay, approval)
    offers: Sequence[str] = sorted(
        {
            str(e["offer_id"])
            for e in overlay.get("entries", [])
            if isinstance(e, Mapping) and e.get("price_yen") is not None
        }
    )
    findings: set[str] = set()
    for mode in ("worktree", "index"):
        for path in _grep_paths(repository, exact, mode, runner):
            findings.add(f"OVERLAY_EXACT_VALUE:{mode}:{path}")
        if not offers:
            continue
        for path in _grep_paths(repository, offers, mode, runner):
            if mode == "worktree":
                try:
                    text = (repository / path).read_text(encoding="utf-8")
                except OSError, UnicodeDecodeError:
                    continue
            else:
                shown = _git(repository, "show", f":{path}", runner=runner)
                if shown.returncode != 0:
                    continue
                text = shown.stdout.decode("utf-8", "replace")
            for code in contextual_leaks(text, overlay):
                findings.add(f"{code}:{mode}:{path}")
    # Commits not yet on any remote would be pushed by the publisher's sync step.
    if (
        _git(
            repository, "rev-parse", "--verify", "-q", "HEAD", runner=runner
        ).returncode
        == 0
    ):
        listed = _git(
            repository, "rev-list", "HEAD", "--not", "--remotes", runner=runner
        )
        if listed.returncode != 0:
            fail("GIT_REV_LIST_FAILED")
        revisions = listed.stdout.decode("ascii").split()
        for start in range(0, len(revisions), HISTORY_REVISION_CHUNK):
            chunk = revisions[start : start + HISTORY_REVISION_CHUNK]
            for hit in _grep_paths(repository, exact, "history", runner, chunk):
                revision, _separator, path = hit.partition(":")
                findings.add(f"OVERLAY_EXACT_VALUE:history:{revision[:12]}:{path}")
    return sorted(findings)


def scan_revision_for_overlay(
    repository: Path,
    revision: str,
    overlay: Mapping[str, Any],
    approval: Mapping[str, Any] | None = None,
    *,
    runner: GitRunner = subprocess.run,
) -> list[str]:
    """Scan one commit (the publisher checkpoint) with exact and contextual needles."""
    if (
        len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
        or _git(
            repository, "cat-file", "-e", f"{revision}^{{commit}}", runner=runner
        ).returncode
        != 0
    ):
        fail("REVISION_INVALID")
    short = revision[:12]
    findings: set[str] = set()
    for hit in _grep_paths(
        repository, leak_needles(overlay, approval), "history", runner, [revision]
    ):
        findings.add(f"OVERLAY_EXACT_VALUE:revision:{short}:{hit.partition(':')[2]}")
    offers = sorted(
        {
            str(e["offer_id"])
            for e in overlay.get("entries", [])
            if isinstance(e, Mapping) and e.get("price_yen") is not None
        }
    )
    if offers:
        for hit in _grep_paths(repository, offers, "history", runner, [revision]):
            path = hit.partition(":")[2]
            shown = _git(repository, "show", f"{revision}:{path}", runner=runner)
            if shown.returncode != 0:
                continue
            for code in contextual_leaks(
                shown.stdout.decode("utf-8", "replace"), overlay
            ):
                findings.add(f"{code}:revision:{short}:{path}")
    return sorted(findings)
