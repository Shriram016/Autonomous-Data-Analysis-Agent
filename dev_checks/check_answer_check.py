"""
check_answer_check.py — Runs the B2 number check over every saved eval result
(eval/results/eval_*.json). Free: no LLM and no API calls.

Prints verdict counts per file and every flagged answer (unsupported numbers)
so a human can review them. Run from the project root:

    python dev_checks/check_answer_check.py            # flagged answers only
    python dev_checks/check_answer_check.py --derived  # also show answers relying on derived numbers
"""

import glob
import json
from collections import Counter
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.answer_check import check_answer

show_derived = "--derived" in sys.argv
total = Counter()

for path in sorted(glob.glob(str(ROOT / "eval/results/eval_*.json"))):
    data = json.load(open(path, encoding="utf-8"))
    counts = Counter()
    flagged, derived = [], []
    for r in data["records"]:
        table = pd.DataFrame(r["pipeline_data"]) if r.get("pipeline_data") else None
        res = check_answer(r.get("answer"), r["query"], table)
        counts[res["verdict"]] += 1
        if res["verdict"] == "fail":
            flagged.append((r, res, table))
        elif res["derived"]:
            derived.append((r, res))
    total.update(counts)
    print(f"\n{Path(path).name}: {dict(counts)}")
    for r, res, table in flagged:
        print(f"  FLAG {r['id']} unsupported={res['unsupported']}")
        print(f"       answer: {r['answer'][:230]!r}")
        print(f"       table : {table.head(3).to_dict(orient='records')}")
    if show_derived:
        for r, res in derived:
            print(f"  derived {r['id']}: {res['derived']}  <- {r['answer'][:120]!r}")

print(f"\nALL FILES: {dict(total)}")
