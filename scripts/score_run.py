"""Score a run against the answer key (data/gold_answers.json).

Usage:
  .venv/bin/python scripts/score_run.py output/run1_before_fix.json [more reports ...]
  .venv/bin/python scripts/score_run.py --run-id <id>        (a run in output/runs/ + data/proposals.json)

Definitions (one "change" = one tracker cell):
  action         a proposal that passed every defense (pending, approved, or later rejected by a human):
                 it WOULD be applied if the approver said yes. Blocked proposals are not actions.
  true positive  an action that matches an expected change in the key (email, row, field, value).
  precision      true positives / actions
  recall         true positives / expected changes in the key (for the emails in the run)
  false actions  actions that are not in the key: wrong changes that would be applied if approved
  exact match    emails whose result is exactly right: for "propose", the set of actions equals the
                 expected set; otherwise no action at all (plus, for must_be_blocked, any proposal
                 blocked by the expected defense; for quarantine, the email flagged by defense 1)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLD = ROOT / "data" / "gold_answers.json"


def _key(p: dict[str, Any]) -> tuple:
    tracker = p.get("tracker") or ("budget" if p.get("amount") is not None else "workplan")
    if tracker == "budget":
        return (p["row_id"], p["field"], round(float(p["amount"]), 2))
    return (p["row_id"], p["field"], str(p.get("new_value")).strip().lower())


def score(report: dict[str, Any], gold: dict[str, Any] | None = None) -> dict[str, Any]:
    gold = gold or json.loads(GOLD.read_text())["emails"]
    emails = report.get("email_ids") or sorted(gold)
    flagged = set(report.get("email_flags") or [])
    props = [p for p in report["proposals"] if p["email_id"] in gold]
    actions = [p for p in props if p["status"] != "blocked"]
    expected = {e: {_key(c) for c in gold[e].get("changes", [])} for e in emails if e in gold}
    tp = [p for p in actions if _key(p) in expected.get(p["email_id"], set())]
    false_actions = [p for p in actions if _key(p) not in expected.get(p["email_id"], set())]
    per_email = {}
    for e in emails:
        g = gold.get(e)
        if g is None:
            continue
        mine = [p for p in props if p["email_id"] == e]
        acts = {_key(p) for p in mine if p["status"] != "blocked"}
        kind = g["expected"]
        if kind == "propose":
            ok = acts == expected[e]
        elif kind == "must_be_blocked":
            ok = not acts and all(g["defense"] in p.get("blocked_by", []) for p in mine)
        elif kind == "quarantine":
            ok = not acts and e in flagged
        else:
            ok = not acts
        per_email[e] = {"expected": kind, "ok": ok, "actions": sorted(map(str, acts)),
                        "blocked": [f"{p['row_id']}.{p['field']} by {','.join(p.get('blocked_by', []))}"
                                    for p in mine if p["status"] == "blocked"]}
    n_expected = sum(len(v) for v in expected.values())
    precision = len(tp) / len(actions) if actions else 1.0
    recall = len(tp) / n_expected if n_expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"run_id": report.get("run_id"), "emails": len(per_email), "expected_changes": n_expected,
            "actions": len(actions), "true_positives": len(tp), "precision": round(precision, 3),
            "recall": round(recall, 3), "f1": round(f1, 3),
            "exact_match": sum(v["ok"] for v in per_email.values()),
            "false_actions": len(false_actions),
            "false_action_list": [f"{p['email_id']}: {p['row_id']}.{p['field']} -> "
                                  f"{p.get('amount') if p.get('amount') is not None else p.get('new_value')}"
                                  for p in false_actions],
            "missed": [f"{e}: {c}" for e, cs in expected.items() for c in cs
                       if c not in {_key(p) for p in tp if p['email_id'] == e}],
            "wrong_emails": [e for e, v in per_email.items() if not v["ok"]],
            "per_email": per_email}


def report_from_run_id(run_id: str) -> dict[str, Any]:
    from backend.report import build_report
    from config import settings

    rec = json.loads((settings.RUNS_DIR / f"{run_id}.json").read_text())
    return build_report(rec)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="*", help="run report JSON files (scripts/live_run.py output)")
    ap.add_argument("--run-id", action="append", default=[])
    ap.add_argument("--json", action="store_true", help="print full JSON instead of a table")
    args = ap.parse_args()
    results = [score(json.loads(Path(r).read_text())) | {"label": Path(r).stem} for r in args.reports]
    results += [score(report_from_run_id(r)) | {"label": r} for r in args.run_id]
    if not results:
        ap.error("give at least one report file or --run-id")
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    print(f"{'run':28} {'prec':>6} {'recall':>6} {'F1':>6} {'exact':>7} {'false actions':>13}")
    for r in results:
        print(f"{r['label'][:28]:28} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['f1']:>6.3f} "
              f"{r['exact_match']:>3}/{r['emails']:<3} {r['false_actions']:>13}")
        for fa in r["false_action_list"]:
            print(f"    false action  {fa}")
        for m in r["missed"]:
            print(f"    missed        {m}")
        if r["wrong_emails"]:
            print(f"    not exact     {', '.join(r['wrong_emails'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
