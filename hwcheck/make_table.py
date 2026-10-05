"""Build the per-command pass/fail markdown table for HW_REPORT.md from the
saved s04_s05 result files. Usage: python make_table.py > results/cmd_table.md"""
import json
import os
import sys

from common import RESULTS

sys.stdout.reconfigure(encoding="utf-8")


def load(tag):
    p = os.path.join(RESULTS, f"s04_s05_basic_{tag}.json")
    return json.load(open(p, encoding="utf-8"))["rows"] if os.path.exists(p) else None


def keyed(rows):
    d = {}
    for r in rows or []:
        key = (r["instrument"], r["sent"] if r["action"] in ("set", "restore") else r["command"], r["action"])
        d.setdefault(key, r)
    return d


py, ivi = load("py"), load("ivi")
kp, ki = keyed(py), keyed(ivi)
print("| Instrument | Command sent | Action | Manual ref | Reply (@py) | @py | @ivi |")
print("|---|---|---|---|---|---|---|")
for key, r in kp.items():
    other = ki.get(key)
    mark = lambda x: "n/a" if x is None else ("PASS" if x["ok"] else "FAIL")
    reply = (r["response"] or r["error"] or "").replace("|", "\\|")
    print(f"| {r['instrument']} | `{key[1]}` | {r['action']} | {r['ref']} | `{reply}` | {mark(r)} | {mark(other)} |")
