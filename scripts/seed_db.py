"""Build data/tracker.db (the ORIGINAL) from the CSV files in data/seed/, then copy it
to data/tracker_working.db. All data is synthetic and fictional.

The original is committed to the repo, so you only need this if you edit the CSVs.
Usage: .venv/bin/python scripts/seed_db.py --force
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from tracker import db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite an existing data/tracker.db")
    args = parser.parse_args()
    if settings.ORIGINAL_DB.exists() and not args.force:
        parser.error("data/tracker.db already exists; pass --force to rebuild it from the CSVs")
    counts = db.build_database(settings.ORIGINAL_DB, settings.SEED_DIR)
    shutil.copyfile(settings.ORIGINAL_DB, settings.WORKING_DB)
    print(json.dumps({"original": settings.ORIGINAL_DB.name, "working": settings.WORKING_DB.name, "rows": counts}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
