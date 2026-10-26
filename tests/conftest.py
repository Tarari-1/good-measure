"""Point the whole app at scratch copies BEFORE any project module is imported.

The real data/ and output/ folders are never touched by the tests, and no test
calls the model.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(tempfile.mkdtemp(prefix="good-measure-tests-"))
(SCRATCH / "state").mkdir()
shutil.copyfile(ROOT / "data" / "tracker.db", SCRATCH / "tracker.db")
os.environ.update({
    "TRACKER_ORIGINAL_DB": str(SCRATCH / "tracker.db"),
    "TRACKER_DB": str(SCRATCH / "tracker_working.db"),
    "TRACKER_STATE_DIR": str(SCRATCH / "state"),
    "TRACKER_MAILBOX_DIR": str(ROOT / "data" / "mailbox"),
    "AUDIT_TRAIL_PATH": str(SCRATCH / "audit_trail.json"),
    "TRACKER_RUNS_DIR": str(SCRATCH / "runs"),
    "TRACKER_STUB_RUNNER": "1",  # the API smoke test never calls the model
})
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def fresh_data():
    """Every test starts from the original tracker and empty stores."""
    shutil.copyfile(SCRATCH / "tracker.db", SCRATCH / "tracker_working.db")
    for f in (SCRATCH / "state").glob("*.json"):
        f.unlink()
    for f in (SCRATCH / "state" / "local_mail").glob("*.eml"):
        f.unlink()
    yield


@pytest.fixture
def scratch() -> Path:
    return SCRATCH
