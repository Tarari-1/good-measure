"""Compare run reports for the cost experiment: tokens, requests, cost and quality score.

Usage:
  .venv/bin/python scripts/cost_experiment.py A=output/run_A_all_measures_on.json B=output/run_B_measures_off.json
Writes output/cost_experiment.json and prints a comparison table. Costs use config/pricing.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import pricing  # noqa: E402

_spec = importlib.util.spec_from_file_location("score_run", ROOT / "scripts" / "score_run.py")
score_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score_run)


def summarize(label: str, path: Path) -> dict:
    rep = json.loads(path.read_text())
    t = rep["usage"]["total"]
    s = score_run.score(rep)
    cost = pricing.cost_usd(t["input_tokens"], t["cached_input_tokens"], t["output_tokens"], t.get("cache_write_tokens", 0))
    off = [k for k, on in (rep.get("measures") or {}).items() if not on]
    return {
        "label": label, "file": str(path.relative_to(ROOT)), "run_id": rep["run_id"], "status": rep["status"],
        "measures_off": off, "requests": t["requests"], "tool_calls": t["tool_calls"],
        "input_tokens": t["input_tokens"], "cached_input_tokens": t["cached_input_tokens"],
        "cache_write_tokens": t.get("cache_write_tokens", 0), "output_tokens": t["output_tokens"],
        "cached_share": round(t["cached_input_tokens"] / t["input_tokens"], 3) if t["input_tokens"] else 0,
        "cost_usd": cost, "per_agent_cost_usd": {a: pricing.cost_usd(u["input_tokens"], u["cached_input_tokens"],
                                                                     u["output_tokens"], u.get("cache_write_tokens", 0))
                                                 for a, u in rep["usage"]["per_agent"].items()},
        "score": {k: s[k] for k in ("precision", "recall", "f1", "exact_match", "emails", "false_actions",
                                    "false_action_list", "missed", "wrong_emails")},
    }


def main() -> int:
    pairs = [a.split("=", 1) for a in sys.argv[1:]]
    if not pairs:
        print(__doc__)
        return 2
    rows = [summarize(label, ROOT / p) for label, p in pairs]
    base = rows[0]
    for r in rows:
        r["cost_vs_first"] = round(r["cost_usd"] / base["cost_usd"], 3) if base["cost_usd"] else None
    out = {"pricing": pricing.as_dict(), "runs": rows}
    (ROOT / "output" / "cost_experiment.json").write_text(json.dumps(out, indent=2))
    print(f"{'run':4} {'measures off':44} {'req':>4} {'input':>8} {'cached':>8} {'output':>7} {'cost $':>9} "
          f"{'prec':>5} {'recall':>6} {'exact':>6} {'false':>5}")
    for r in rows:
        s = r["score"]
        print(f"{r['label']:4} {(', '.join(r['measures_off']) or 'none (all on)')[:44]:44} {r['requests']:>4} "
              f"{r['input_tokens']:>8,} {r['cached_input_tokens']:>8,} {r['output_tokens']:>7,} {r['cost_usd']:>9.5f} "
              f"{s['precision']:>5.3f} {s['recall']:>6.3f} {s['exact_match']:>3}/{s['emails']:<2} {s['false_actions']:>5}")
    print("wrote output/cost_experiment.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
