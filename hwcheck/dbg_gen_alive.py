"""Troubleshooting: is the generator still responsive after the undocumented
*OPC? probe timed out? Fresh session, *IDN? and output state only."""
import time

import scpi
from common import GEN_PID, GEN_VID, find_resource, open_inst, open_rm

rm = open_rm("@py")
res = find_resource(rm, GEN_VID, GEN_PID)
print("resource:", res)
g = open_inst(rm, res, timeout_ms=3000)
for attempt in range(1, 4):
    try:
        t0 = time.perf_counter()
        print(attempt, "IDN:", g.query(scpi.IDN).strip(), f"{time.perf_counter() - t0:.3f}s")
        print(attempt, "OUT1/OUT2:", g.query(scpi.G_OUT.format(n=1) + "?").strip(),
              g.query(scpi.G_OUT.format(n=2) + "?").strip())
        break
    except Exception as e:
        print(attempt, "FAILED:", type(e).__name__, e)
        try:
            g.clear()
            print("  clear() ok")
        except Exception as e2:
            print("  clear() failed:", type(e2).__name__, e2)
        time.sleep(1.0)
g.close()
rm.close()
