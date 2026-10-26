"""Run the real agent team once on selected emails (default: the whole sample mailbox).

Uses the same runner as POST /api/runs, so the run record lands in output/runs/
and shows up in the dashboard. This CALLS THE MODEL: use sparingly.

Usage:
  .venv/bin/python scripts/live_run.py [--emails e01,e02] [--out output/my_run.json]
  TRACKER_MEASURES_OFF=prefilter_emails,batch_intake .venv/bin/python scripts/live_run.py ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import runner  # noqa: E402
from backend.report import build_report  # noqa: E402
from tracker.email_source import SampleMailboxSource  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emails", help="comma-separated email ids (default: the 20 sample emails)")
    parser.add_argument("--out", help="also write the report to this file")
    args = parser.parse_args()
    if runner.STUB:
        parser.error("TRACKER_STUB_RUNNER=1 is set; unset it for a live run")
    ids = args.emails.split(",") if args.emails else SampleMailboxSource().list_ids()
    rec = runner.start(ids)
    asyncio.run(runner.execute(rec))
    report = build_report(rec)
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if rec["status"] == "finished" else 1


if __name__ == "__main__":
    sys.exit(main())
