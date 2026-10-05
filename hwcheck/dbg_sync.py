"""Troubleshooting, part 3. After dbg_wave.py the scope's replies are one step
behind: each query returns the PREVIOUS query's answer, and a bare read just
re-sends the last reply. Find out whether the scope is answering late (stale
reply returned when the new one is not ready) and how long a reply takes.
Generator untouched. Read-only queries, plus :RUN at the end."""
import time

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm

rm = open_rm("@py")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
s.read_termination = None
s.timeout = 2000

QUERIES = [scpi.IDN, scpi.S_TRIG_STAT_Q, scpi.S_TB_SCAL + "?", scpi.S_ERR_Q,
           scpi.S_CH_SCAL.format(n=1) + "?", scpi.OPC_Q, scpi.IDN, scpi.S_TRIG_STAT_Q]


def reads(label, delays):
    out = []
    t0 = time.perf_counter()
    for d in delays:
        while time.perf_counter() - t0 < d:
            time.sleep(0.001)
        r = s.read_raw()
        out.append((round(time.perf_counter() - t0, 3), r[:28]))
    print(f"  {label:26s} {out}")


print("A: write, then read at 0 / 0.05 / 0.2 / 0.5 / 1.0 s")
for qy in QUERIES:
    s.write(qy)
    reads(qy, (0.0, 0.05, 0.2, 0.5, 1.0))

print("B: plain query() back to back (what the test scripts do)")
for qy in QUERIES:
    s.write(qy)
    print(f"  {qy:26s} {s.read_raw()[:28]!r}")

print("C: :RUN, wait 2 s, repeat B")
s.write(scpi.S_RUN)
time.sleep(2.0)
for qy in QUERIES:
    s.write(qy)
    print(f"  {qy:26s} {s.read_raw()[:28]!r}")
s.close()
rm.close()
