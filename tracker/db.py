"""SQLite access for the two trackers (budget and work plan).

- data/tracker.db is the ORIGINAL. Nothing in the app ever opens it for writing;
  only scripts/seed_db.py creates it and scripts/reset_db.py copies it.
- data/tracker_working.db is the working copy every read and every approved write
  uses. If it is missing (fresh clone) it is created from the original.

Reads open the working copy read-only (mode=ro). The single write path is
apply_change(), called only by backend/approvals.py after a human approves.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from config import settings

SCHEMA = """
CREATE TABLE programs (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lead_email TEXT NOT NULL
);
CREATE TABLE people (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    program TEXT NOT NULL,
    role TEXT NOT NULL
);
CREATE TABLE budget_lines (
    line_id TEXT PRIMARY KEY,
    program TEXT NOT NULL REFERENCES programs(code),
    category TEXT NOT NULL,
    annual_budget REAL NOT NULL CHECK (annual_budget >= 0),
    spent_to_date REAL NOT NULL CHECK (spent_to_date >= 0),
    committed REAL NOT NULL CHECK (committed >= 0),
    owner TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT ''  -- '|'-separated words an email must use to be booked to this line
);
CREATE TABLE activities (
    id TEXT PRIMARY KEY,
    program TEXT NOT NULL REFERENCES programs(code),
    activity TEXT NOT NULL,
    owner TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('not_started','in_progress','complete','at_risk','blocked')),
    percent_complete INTEGER NOT NULL CHECK (percent_complete BETWEEN 0 AND 100),
    notes TEXT NOT NULL DEFAULT '',
    depends_on TEXT
);
CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracker TEXT NOT NULL CHECK (tracker IN ('budget','workplan')),
    row_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    proposal_id TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""

BUDGET_FIELDS = ("spent_to_date", "committed")  # the only budget cells a proposal may change
ACTIVITY_FIELDS = ("status", "percent_complete", "due_date", "notes")  # the only work-plan cells
ACTIVITY_STATUSES = ("not_started", "in_progress", "complete", "at_risk", "blocked")


def ensure_working_db() -> Path:
    """Create the working copy from the original if it does not exist yet."""
    if settings.WORKING_DB == settings.ORIGINAL_DB:
        raise RuntimeError("The working database path must not be the original database.")
    if not settings.WORKING_DB.exists():
        if not settings.ORIGINAL_DB.exists():
            raise FileNotFoundError("data/tracker.db is missing; run scripts/seed_db.py")
        settings.WORKING_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(settings.ORIGINAL_DB, settings.WORKING_DB)
    return settings.WORKING_DB


def connect_ro() -> sqlite3.Connection:
    path = ensure_working_db()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_rw() -> sqlite3.Connection:
    path = ensure_working_db()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with closing(connect_ro()) as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def programs() -> list[dict[str, Any]]:
    return _rows("SELECT * FROM programs ORDER BY code")


def people() -> list[dict[str, Any]]:
    return _rows("SELECT * FROM people ORDER BY program, name")


def person_by_email(email: str) -> dict[str, Any] | None:
    rows = _rows("SELECT * FROM people WHERE lower(email) = lower(?)", (email.strip(),))
    return rows[0] if rows else None


def budget_lines(program: str | None = None) -> list[dict[str, Any]]:
    if program:
        return _rows("SELECT * FROM budget_lines WHERE program = ? ORDER BY line_id", (program,))
    return _rows("SELECT * FROM budget_lines ORDER BY line_id")


def budget_line(line_id: str) -> dict[str, Any] | None:
    rows = _rows("SELECT * FROM budget_lines WHERE line_id = ?", (line_id,))
    return rows[0] if rows else None


def activities(program: str | None = None) -> list[dict[str, Any]]:
    if program:
        return _rows("SELECT * FROM activities WHERE program = ? ORDER BY id", (program,))
    return _rows("SELECT * FROM activities ORDER BY id")


def activity(activity_id: str) -> dict[str, Any] | None:
    rows = _rows("SELECT * FROM activities WHERE id = ?", (activity_id,))
    return rows[0] if rows else None


def change_log() -> list[dict[str, Any]]:
    return _rows("SELECT * FROM change_log ORDER BY id")


def changed_cells() -> dict[str, dict[str, list[str]]]:
    """{"budget": {"READ-02": ["spent_to_date"]}, "workplan": {...}} for highlighting."""
    out: dict[str, dict[str, list[str]]] = {"budget": {}, "workplan": {}}
    for c in change_log():
        fields = out[c["tracker"]].setdefault(c["row_id"], [])
        if c["field"] not in fields:
            fields.append(c["field"])
    return out


def apply_change(*, tracker: str, row_id: str, field: str, expected_old: Any, new_value: Any,
                 proposal_id: str, approved_by: str, applied_at: str) -> dict[str, Any]:
    """Write one approved cell change in a single transaction, plus its change_log row.

    Only called by backend/approvals.py. Refuses if the cell no longer holds the
    value the approval was validated against (someone changed it meanwhile).
    """
    if tracker == "budget":
        table, key, allowed = "budget_lines", "line_id", BUDGET_FIELDS
    elif tracker == "workplan":
        table, key, allowed = "activities", "id", ACTIVITY_FIELDS
    else:
        raise ValueError(f"unknown tracker {tracker!r}")
    if field not in allowed:
        raise ValueError(f"field {field!r} may not be changed in the {tracker} tracker")
    conn = connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(f"SELECT {field} FROM {table} WHERE {key} = ?", (row_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"ok": False, "reason": f"{row_id} no longer exists"}
        if str(row[0]) != str(expected_old):
            conn.execute("ROLLBACK")
            return {"ok": False, "reason": f"{row_id}.{field} changed since validation ({expected_old} -> {row[0]})"}
        conn.execute(f"UPDATE {table} SET {field} = ? WHERE {key} = ?", (new_value, row_id))
        conn.execute(
            "INSERT INTO change_log (tracker, row_id, field, old_value, new_value, proposal_id, approved_by, applied_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tracker, row_id, field, str(row[0]), str(new_value), proposal_id, approved_by, applied_at),
        )
        conn.execute("COMMIT")
        return {"ok": True, "old_value": row[0], "new_value": new_value}
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def build_database(path: Path, seed_dir: Path) -> dict[str, int]:
    """Create a fresh tracker database at `path` from the CSV files in `seed_dir`."""
    import csv

    if path.exists():
        path.unlink()
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)

        def load(name: str) -> list[dict[str, str]]:
            with open(seed_dir / name, newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))

        conn.executemany("INSERT INTO programs VALUES (:code, :name, :lead_email)", load("programs.csv"))
        conn.executemany("INSERT INTO people VALUES (:email, :name, :program, :role)", load("people.csv"))
        conn.executemany(
            "INSERT INTO budget_lines VALUES (:line_id, :program, :category, :annual_budget, :spent_to_date,"
            " :committed, :owner, :keywords)",
            [{**r, "annual_budget": float(r["annual_budget"]), "spent_to_date": float(r["spent_to_date"]),
              "committed": float(r["committed"])} for r in load("budget.csv")],
        )
        conn.executemany(
            "INSERT INTO activities VALUES (:id, :program, :activity, :owner, :due_date, :status,"
            " :percent_complete, :notes, :depends_on)",
            [{**r, "percent_complete": int(r["percent_complete"]), "depends_on": r["depends_on"] or None}
             for r in load("workplan.csv")],
        )
        conn.commit()
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("programs", "people", "budget_lines", "activities", "change_log")}
