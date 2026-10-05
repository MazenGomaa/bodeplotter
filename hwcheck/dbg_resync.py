"""Troubleshooting, part 5. The scope's replies are one read behind
(dbg_latency.py: every query needed exactly two reads, whatever the delay).
Check the offset, try a USBTMC clear, check again, then put the timebase back
to 5 ms/div (dbg_latency.py could not restore it). Generator untouched."""
import time

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm
from usbclear import usbtmc_clear

PAIRS = [(scpi.IDN, "UNI-T"), (scpi.OPC_Q, "1"), (scpi.S_ERR_Q, "0,"), (scpi.IDN, "UNI-T"),
         (scpi.OPC_Q, "1")]


def check(label):
    rm = open_rm("@py")
    s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
    ok = 0
    try:
        for cmd, pre in PAIRS:
            r = s.query(cmd).strip()
            good = r.startswith(pre)
            ok += good
            print(f"  [{label}] {cmd:16s} -> {r[:40]!r} {'ok' if good else 'OUT OF STEP'}")
    finally:
        s.close()
        rm.close()
    return ok == len(PAIRS)


in_step = check("before")
if not in_step:
    usbtmc_clear(SCOPE_VID, SCOPE_PID)
    time.sleep(1.0)
    in_step = check("after usbtmc_clear")
print("in step:", in_step)
if in_step:
    rm = open_rm("@py")
    s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
    print("timebase:", s.query(scpi.S_TB_SCAL + "?").strip(), "status:", s.query(scpi.S_TRIG_STAT_Q).strip())
    s.write(f"{scpi.S_TB_SCAL} 0.005")
    time.sleep(1.5)
    print("timebase now:", s.query(scpi.S_TB_SCAL + "?").strip(), "| CH1 scale:",
          s.query(scpi.S_CH_SCAL.format(n=1) + "?").strip(), "| probe:",
          s.query(scpi.S_CH_PROBE.format(n=1) + "?").strip(), "| err:", s.query(scpi.S_ERR_Q).strip())
    s.close()
    rm.close()
