"""Milestone 0c troubleshooting: twice now generator CH1's output read ON some
time after a test had switched it OFF and confirmed OFF. Does one of the
setting-restore writes switch the output back on?

1. Switch both outputs OFF (verified).
2. Re-write each CH1 setting with its current value and query the output state
   after every write.
Only documented commands; no value is changed. Ends with both outputs OFF."""
import time

import iolayer as io
from common import GEN_PID, GEN_VID, find_resource, open_rm

rm = open_rm("@py")
g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
g.connect()
print("found: outputs ON?", [g.output(1), g.output(2)])
g.output(1, False)
g.output(2, False)
print("after OFF:", [g.output(1), g.output(2)])
c, num = ":CHANnel1", io.GenFmt.num
items = ((c + ":BASE:WAVe", g.V_WAVE, lambda x: x), (c + ":LOAD", io.v_float, num),
         (c + ":AMPLitude:UNIT", g.V_UNIT, lambda x: x), (c + ":BASE:FREQuency", io.v_float, num),
         (c + ":BASE:AMPLitude", io.v_float, num), (c + ":BASE:OFFSet", io.v_float, num))
try:
    for rnd in (1, 2):
        for cmd, v, fmt in items:
            val = g.query(cmd + "?", v)
            g.write(f"{cmd} {fmt(val)}")
            time.sleep(0.3)
            print(f"  round {rnd}: wrote {cmd} {fmt(val)!s:10s} -> outputs ON? {[g.output(1), g.output(2)]}")
finally:
    g.safe_off()
    time.sleep(0.5)
    print("end: outputs ON?", [g.output(1), g.output(2)])
    time.sleep(3.0)
    print("3 s later: outputs ON?", [g.output(1), g.output(2)])
    g.close()
    rm.close()
