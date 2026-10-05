"""Troubleshooting: CH1 V/div restore failed in s04_s05 (set 1.0 ok, restore
2.000000e-01 read back 1.0). Find out whether it is number format or timing.
Ends with CH1 at 0.2 V/div (the value found before any test ran)."""
import time

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm

rm = open_rm("@py")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
CMD = scpi.S_CH_SCAL.format(n=1)   # UPO p.20-21


def poll(label, secs=3.0):
    t0 = time.perf_counter()
    last = None
    while time.perf_counter() - t0 < secs:
        r = s.query(CMD + "?").strip()
        if r != last:
            print(f"  {label}: t={time.perf_counter() - t0:.3f}s -> {r}")
            last = r
        time.sleep(0.02)
    return last


print("now:", s.query(CMD + "?").strip(), "| err:", s.query(scpi.S_ERR_Q).strip())
for val in ("2.000000e-01", "0.5", "0.2", "200mV", "1.0", "2.000000e-01", "0.2"):
    s.write(f"{CMD} {val}")
    got = poll(f"sent {val!r}", 1.5)
    print(f"sent {val!r:16} final {got} | err: {s.query(scpi.S_ERR_Q).strip()} | opc: {s.query(scpi.OPC_Q).strip()}")

print("final:", s.query(CMD + "?").strip())
s.close()
rm.close()
