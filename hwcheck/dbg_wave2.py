"""Troubleshooting, part 2. dbg_wave.py showed:
  - at 50 ms/div the scope is in SCAN (roll) status and :WAVeform:DATA? answers
    with an empty reply; after :STOP the replies came back out of step (a
    waveform block arrived as the answer to :TRIGger:STATus?).
This script first drains any stale replies, checks the scope is in step again
and that the timebase is back at 5 ms/div, then tries to reproduce the empty
block seen in s07 at 5 ms/div:
  E1: :WAVeform:MODE write followed by :STOP after a varying delay
  E2: 40 x STOP/fetch/RUN with no MODE write, random phase
Generator untouched."""
import random
import time

import scpi
import wave
from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm

rm = open_rm("@py")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))


def drain():
    old_t, old_rt = s.timeout, s.read_termination
    s.timeout, s.read_termination = 300, None
    n = 0
    try:
        # Bounded: the first version of this loop never ended, because the
        # scope answers every bare read by re-sending its last reply
        # (b'0,"No error"\r\n' over and over) instead of timing out.
        for _ in range(3):
            try:
                r = s.read_raw()
                n += 1
                print(f"  drained stale reply: {len(r)} bytes {r[:16]!r}")
            except Exception:
                break
    finally:
        s.timeout, s.read_termination = old_t, old_rt
    return n


def raw_data():
    old = s.read_termination
    s.read_termination = None
    try:
        s.write(scpi.S_WAV_DATA_Q)
        return len(s.read_raw())
    finally:
        s.read_termination = old


print("drained:", drain())
print("IDN:", s.query(scpi.IDN).strip())
print("status:", s.query(scpi.S_TRIG_STAT_Q).strip(), "| timebase:", s.query(scpi.S_TB_SCAL + "?").strip(),
      "| err:", s.query(scpi.S_ERR_Q).strip())
if abs(float(s.query(scpi.S_TB_SCAL + "?")) - 5e-3) > 1e-9:
    print("timebase not 5 ms/div, setting ->", wave.swrite(s, f"{scpi.S_TB_SCAL} 0.005"),
          s.query(scpi.S_TB_SCAL + "?").strip())
s.write(scpi.S_RUN)
time.sleep(1.0)
print("status after RUN:", s.query(scpi.S_TRIG_STAT_Q).strip())

print("E1: MODE write then STOP after delay")
for delay in (0.0, 0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0):
    s.write(f"{scpi.S_WAV_SRC} CHANnel1")
    s.write(f"{scpi.S_WAV_MODE} NORMal")
    s.write(f"{scpi.S_WAV_FMT} BYTE")
    time.sleep(delay)
    s.write(scpi.S_STOP)
    wave.wait_stopped(s)
    sizes = []
    t0 = time.perf_counter()
    for _ in range(4):
        sizes.append((round(time.perf_counter() - t0, 3), raw_data()))
        time.sleep(0.15)
    s.write(scpi.S_RUN)
    time.sleep(0.4)
    print(f"  delay {delay:4.2f}s -> (t, bytes) {sizes} | running again: {raw_data()} bytes")

print("E2: 40 x STOP at random phase, no MODE write")
empty = 0
for i in range(40):
    time.sleep(random.uniform(0.0, 0.2))
    s.write(scpi.S_STOP)
    wave.wait_stopped(s)
    n = raw_data()
    if n <= 2:
        empty += 1
        later = []
        for _ in range(3):
            time.sleep(0.2)
            later.append(raw_data())
        print(f"  cycle {i}: EMPTY, retries while stopped -> {later}")
    s.write(scpi.S_RUN)
print("  empty first reads:", empty, "/ 40")
print("final: status", s.query(scpi.S_TRIG_STAT_Q).strip(), "timebase", s.query(scpi.S_TB_SCAL + "?").strip(),
      "err", s.query(scpi.S_ERR_Q).strip())
s.close()
rm.close()
