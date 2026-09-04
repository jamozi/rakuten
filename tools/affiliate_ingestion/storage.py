from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .client import FetchBatch
from .normalize import normalize_record


class StorageError(RuntimeError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _safe_component(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )
    return safe.strip("._") or "unknown"


def persist_batch(
    batch: FetchBatch, storage_config: Mapping[str, Any]
) -> dict[str, Any]:
    root = (
        Path(str(storage_config.get("root", "var/affiliate_ingestion")))
        .expanduser()
        .resolve()
    )
    stamp = _safe_component(batch.fetched_at.replace(":", "")) + "-" + uuid4().hex
    provider = _safe_component(batch.provider)
    resource = _safe_component(batch.resource)
    run_dir = root / "raw" / provider / resource / stamp
    raw_files: list[dict[str, Any]] = []
    for page in batch.pages:
        body_hash = hashlib.sha256(page.body).hexdigest()
        raw_path = run_dir / f"page-{page.index:05d}-{body_hash[:12]}.bin"
        _atomic_write(raw_path, page.body)
        raw_files.append(
            {
                "page": page.index,
                "path": str(raw_path.relative_to(root)),
                "sha256": body_hash,
                "bytes": len(page.body),
                "status": page.status,
                "content_type": page.content_type,
                "request_url": page.request_url,
                "etag": page.etag,
                "last_modified": page.last_modified,
            }
        )
    normalized = [
        normalize_record(
            batch.provider,
            batch.resource,
            record,
            fetched_at=batch.fetched_at,
        )
        for record in batch.records
    ]
    normalized_path = root / "normalized" / provider / resource / f"{stamp}.ndjson"
    normalized_payload = b"".join(
        (
            json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        ).encode("utf-8")
        for record in normalized
    )
    _atomic_write(normalized_path, normalized_payload)
    manifest = {
        "schema_version": 1,
        "provider": batch.provider,
        "resource": batch.resource,
        "fetched_at": batch.fetched_at,
        "page_count": len(batch.pages),
        "record_count": len(batch.records),
        "warnings": batch.warnings,
        "raw_files": raw_files,
        "normalized_path": str(normalized_path.relative_to(root)),
        "normalized_sha256": hashlib.sha256(normalized_payload).hexdigest(),
    }
    manifest_path = run_dir / "manifest.json"
    _atomic_write(
        manifest_path,
        (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    )
    state_path = root / "state" / provider / f"{resource}.json"
    _atomic_write(
        state_path,
        (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    )
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "state_path": str(state_path),
    }
