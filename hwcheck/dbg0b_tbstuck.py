"""Milestone 0b troubleshooting: in the swapped-probe run of s0b_dual.py the
timebase table came out as [0.005] only, i.e. ':TIMebase:SCALe 0.001', 'DOWN'
and 'UP' all left the timebase at 5 ms/div. Read the scope's state and try a
timebase change again. Scope only, generator untouched; timebase restored."""
import time

import iolayer as io
from common import SCOPE_PID, SCOPE_VID, find_resource, open_rm

rm = open_rm("@py")
sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=lambda m: print("   .", m))
sc.resync(run_wait=0.3)
raw = lambda r: r
for cmd, v in ((":TIMebase:SCALe?", io.v_float), (":TIMebase:MODE?", raw), (":TIMebase:OFFSet?", io.v_float),
               (":TRIGger:SWEep?", io.V_SWEEP), (":TRIGger:STATus?", io.V_STATUS), (":TRIGger:MODE?", raw),
               (":TRIGger:SOURce?", raw), (":TRIGger:LEVel?", io.v_float), (":ACQuire:TYPE?", raw),
               (":ACQuire:MEMory:DEPTh?", raw), (":SYSTem:ERRor?", io.v_err),
               (":CHANnel1:SCALe?", io.v_float), (":CHANnel2:SCALe?", io.v_float),
               (":CHANnel1:PROBe?", io.v_float), (":CHANnel2:PROBe?", io.v_float)):
    print(f"{cmd:26s} {sc.query(cmd, v)!r}")
tb0 = sc.query(":TIMebase:SCALe?", io.v_float)
for arg in ("0.001", "DOWN", "DOWN", "UP", "0.0005", io.plain_decimal(tb0)):
    sc.write(f":TIMebase:SCALe {arg}")
    seen, t0 = [], time.perf_counter()
    while time.perf_counter() - t0 < 1.0:
        v = sc.query(":TIMebase:SCALe?", io.v_float)
        if not seen or seen[-1][1] != v:
            seen.append((round(time.perf_counter() - t0, 2), v))
        time.sleep(0.05)
    print(f"  :TIMebase:SCALe {arg:8s} -> {seen}  status {sc.status()}  err {sc.error_queue()}")
print("stats", sc.stats)
sc.close()
rm.close()
