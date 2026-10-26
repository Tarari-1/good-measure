"""Restore the working tracker from the original. Shared by POST /api/reset and the CLI.

- Copies data/tracker.db over data/tracker_working.db (temp file, fsync, os.replace)
  and verifies that the SHA-256 of the copy equals the original's.
- Empties the proposal, nudge and selection stores, and removes pasted/imported
  emails (data/local_mail/). The bundled sample mailbox is never touched.
- Never deletes the audit trail or run records; it APPENDS one audit note.

Usage: .venv/bin/python scripts/reset_db.py --confirm
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from tracker import audit, db, store  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def reset_database(source: str = "cli") -> dict[str, Any]:
    original, working = settings.ORIGINAL_DB, settings.WORKING_DB
    if working == original:
        raise RuntimeError("Refusing to reset: the working database path points at the original.")
    if not original.is_file():
        raise FileNotFoundError("Original database data/tracker.db not found.")
    original_sha = sha256(original)
    tmp = working.with_name(f"{working.name}.reset-tmp-{os.getpid()}")
    shutil.copyfile(original, tmp)
    with open(tmp, "rb+") as fh:
        os.fsync(fh.fileno())
    os.replace(tmp, working)
    working_sha = sha256(working)
    if working_sha != original_sha:
        raise RuntimeError("Reset copy does not match the original checksum.")
    cleared = {}
    for name in store.ALL_STORES:
        with store.locked(name) as records:
            cleared[name] = len(records)
            records.clear()
    local = sorted(settings.LOCAL_MAIL_DIR.glob("*.eml")) if settings.LOCAL_MAIL_DIR.exists() else []
    for f in local:  # pasted / imported emails are local test data, removed by a reset
        f.unlink()
    cleared["local_mail"] = len(local)
    counts = {"budget_lines": len(db.budget_lines()), "activities": len(db.activities()),
              "change_log": len(db.change_log())}
    audit.event(run_id="reset", step="note", name="tracker_reset", arguments={"source": source},
                result={"sha256": working_sha[:12], "cleared": json.dumps(cleared)})
    return {"ok": True, "original_sha256": original_sha, "working_sha256": working_sha, "checksums_match": True,
            "row_counts": counts, "cleared": cleared}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm", action="store_true", help="required: really reset the working data")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("refusing to reset without --confirm")
    print(json.dumps(reset_database(source="cli"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
