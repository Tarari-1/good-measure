"""Small JSON-file stores that sit beside the tracker database.

- proposals.json  every proposed cell change, with its defense results and status
- nudges.json     drafted chase emails (drafts only; nothing is ever sent)
- selection.json  the emails ticked in the Inbox

Each store is a JSON array. Writes are safe: an exclusive lock file, a temp file,
fsync, then os.replace. A store that cannot be parsed is renamed aside
(<name>.corrupt-<ts>.json) and never deleted. TRACKER_STATE_DIR moves the
directory (tests only). Pattern reused from homework-5/mcp_server/stores.py.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config.settings import STATE_DIR as STORE_DIR

PROPOSALS = "proposals.json"
NUDGES = "nudges.json"
SELECTION = "selection.json"
ALL_STORES = (PROPOSALS, NUDGES, SELECTION)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path(name: str) -> Path:
    return STORE_DIR / name


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("store is not a JSON array")
        return data
    except (json.JSONDecodeError, ValueError):
        os.replace(path, path.with_name(f"{path.stem}.corrupt-{int(time.time())}.json"))
        return []


def _write(path: Path, data: list[dict[str, Any]]) -> None:
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


@contextmanager
def locked(name: str) -> Iterator[list[dict[str, Any]]]:
    """Lock a store, yield its records, and write them back on clean exit.

    Mutate the yielded list in place. If the block raises, nothing is written.
    """
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(name)
    with open(path.with_name(path.name + ".lock"), "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            records = _read(path)
            yield records
            _write(path, records)
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def read_all(name: str) -> list[dict[str, Any]]:
    """Read a store without changing it (takes the lock so reads are consistent).

    A store that does not exist yet reads as empty and nothing is created on disk,
    so read-only callers never leave files behind.
    """
    path = _path(name)
    if not path.exists():
        return []
    with open(path.with_name(path.name + ".lock"), "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            return _read(path)
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def next_id(records: list[dict[str, Any]], prefix: str) -> str:
    nums = [int(r["id"].split("-")[1]) for r in records if str(r.get("id", "")).startswith(prefix + "-")]
    return f"{prefix}-{(max(nums) + 1) if nums else 1:04d}"
