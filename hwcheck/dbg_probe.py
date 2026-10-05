"""Troubleshooting: in s06 ':CHANnel1:PROBe 1' read back 10, and SCALe values
set while the probe ratio was 10X read back scaled. Work out the PROBe argument
format and how SCALe set/query relate to the probe ratio.
Generator is not touched. Ends with CH1 at probe 1X, 0.2 V/div (the values
found by s04_s05_basic.py before the end-to-end test)."""
import time

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm

rm = open_rm("@py")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
P = scpi.S_CH_PROBE.format(n=1)    # UPO p.19-20, example ":CHAN1:PROB 10X"
V = scpi.S_CH_SCAL.format(n=1)     # UPO p.20-21
O = scpi.S_CH_OFFS.format(n=1)     # UPO p.20


def state():
    return (s.query(P + "?").strip(), s.query(V + "?").strip(), s.query(O + "?").strip(),
            s.query(scpi.S_WAV_YINC_Q).strip())


def send(cmd, watch=1.5):
    s.write(cmd)
    t0 = time.perf_counter()
    last = None
    while time.perf_counter() - t0 < watch:
        st = state()
        if st != last:
            print(f"    t={time.perf_counter() - t0:5.2f}s probe={st[0]} scale={st[1]} offs={st[2]} yinc={st[3]}")
            last = st
        time.sleep(0.05)
    print(f"  {cmd!r:32} err={s.query(scpi.S_ERR_Q).strip()}")


s.write(f"{scpi.S_WAV_SRC} CHANnel1")
print("start:", state())
for cmd in (f"{P} 1X", f"{V} 0.2", f"{P} 10X", f"{V} 0.2", f"{V} 2", f"{V} 5",
            f"{P} 1", f"{P} 10", f"{P} 1X", f"{V} 0.5", f"{P} 100X", f"{P} 1X",
            f"{O} 0", f"{V} 0.2"):
    send(cmd)
print("end:", state(), "timebase:", s.query(scpi.S_TB_SCAL + "?").strip())
s.close()
rm.close()
