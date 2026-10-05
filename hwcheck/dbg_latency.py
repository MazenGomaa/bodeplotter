"""Troubleshooting, part 4. dbg_sync.py showed the scope returns the PREVIOUS
reply if the host reads before the new reply is ready (it does not hold off the
read as USBTMC intends). Measure how long a reply takes to become ready, as a
function of timebase, by alternating two queries with different answers and
polling reads until the answer changes.
Generator untouched. Timebase restored at the end."""
import statistics
import sys
import time

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, num, open_inst, open_rm, save

rm = open_rm("@py")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
s.read_termination = None
s.timeout = 2000


def safe_query(cmd, wait=0.15):
    s.write(cmd)
    time.sleep(wait)
    return s.read_raw().decode("ascii", "replace").strip()


def latency(cmd, expect_prefix, limit=1.0):
    """Seconds from write until a read returns a reply starting with expect_prefix.
    Returns (latency, number_of_stale_reads)."""
    s.write(cmd)
    t0 = time.perf_counter()
    stale = 0
    while True:
        r = s.read_raw()
        t = time.perf_counter() - t0
        if r.startswith(expect_prefix):
            return t, stale
        stale += 1
        if t > limit:
            return float("nan"), stale


tb0 = safe_query(scpi.S_TB_SCAL + "?")
print("timebase original:", tb0, "| status:", safe_query(scpi.S_TRIG_STAT_Q))
results = {}
try:
    for tb in (20e-9, 500e-9, 500e-6, 2e-3, 5e-3, 10e-3, 20e-3):
        s.write(f"{scpi.S_TB_SCAL} {num(tb)}")
        time.sleep(1.5)
        back = safe_query(scpi.S_TB_SCAL + "?", 0.3)
        lats, stales = [], 0
        for i in range(40):
            # alternate so consecutive replies always differ
            cmd, pre = ((scpi.IDN, b"UNI-T"), (scpi.OPC_Q, b"1\r"))[i % 2]
            t, st = latency(cmd, pre)
            lats.append(t)
            stales += 1 if st else 0
            time.sleep(0.02)
        good = [x for x in lats if x == x]
        results[num(tb)] = dict(readback=back, n=len(lats), first_read_stale=stales,
                                mean_ms=1e3 * statistics.mean(good), max_ms=1e3 * max(good),
                                min_ms=1e3 * min(good), failed=len(lats) - len(good))
        print(f"tb {tb:8.3g} s/div readback {back}: {results[num(tb)]}")
finally:
    s.write(f"{scpi.S_TB_SCAL} {num(tb0)}")
    time.sleep(1.5)
    print("timebase restored:", safe_query(scpi.S_TB_SCAL + "?", 0.3))
    s.close()
    rm.close()
    print("saved", save("dbg_latency.json", results))
