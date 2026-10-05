"""Troubleshooting: :WAVeform:DATA? answers with an empty reply (CR LF only)
in some conditions (s06 run 2 at 1 MHz once; s07 at 5 ms/div every time).
Probe when the block is empty: running vs stopped, delay after STOP, timebase.
Generator untouched. Timebase restored at the end."""
import time

import scpi
import wave
from common import SCOPE_PID, SCOPE_VID, find_resource, num, open_inst, open_rm

rm = open_rm("@py")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))


def raw_data():
    old = s.read_termination
    s.read_termination = None
    try:
        s.write(scpi.S_WAV_DATA_Q)
        r = s.read_raw()
        return len(r), r[:12]
    finally:
        s.read_termination = old


def show(label):
    print(f"  {label:34s} stat={s.query(scpi.S_TRIG_STAT_Q).strip():6s} data={raw_data()}")


tb0 = s.query(scpi.S_TB_SCAL + "?").strip()
print("timebase original:", tb0)
print("readout before:", [s.query(c + "?").strip() for c in (scpi.S_WAV_SRC, scpi.S_WAV_MODE, scpi.S_WAV_FMT)],
      "points:", s.query(scpi.S_WAV_POINTS_Q).strip())
for c in (f"{scpi.S_WAV_SRC} CHANnel1", f"{scpi.S_WAV_MODE} NORMal", f"{scpi.S_WAV_FMT} BYTE"):
    print("  swrite", c, "->", wave.swrite(s, c))
print("readout after:", [s.query(c + "?").strip() for c in (scpi.S_WAV_SRC, scpi.S_WAV_MODE, scpi.S_WAV_FMT)])

try:
    for tb in (5e-3, 500e-6, 50e-3, 5e-3):
        print(f"timebase {tb:g} s/div ->", wave.swrite(s, f"{scpi.S_TB_SCAL} {num(tb)}"),
              s.query(scpi.S_TB_SCAL + "?").strip())
        time.sleep(1.0)
        for i in range(3):
            show(f"running #{i}")
        s.write(scpi.S_STOP)
        t0 = time.perf_counter()
        for i in range(6):
            show(f"stopped +{time.perf_counter() - t0:.3f}s")
            time.sleep(0.1)
        s.write(scpi.S_RUN)
        t0 = time.perf_counter()
        for i in range(8):
            show(f"after RUN +{time.perf_counter() - t0:.3f}s")
            time.sleep(0.05)
finally:
    s.write(scpi.S_RUN)
    wave.swrite(s, f"{scpi.S_TB_SCAL} {num(tb0)}")
    print("timebase restored:", s.query(scpi.S_TB_SCAL + "?").strip(), "err:", s.query(scpi.S_ERR_Q).strip())
    s.close()
    rm.close()
