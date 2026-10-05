"""Milestone 0b troubleshooting: in t0b (run 6, @ivi) a forced single shot went
ARMED -> READY -> STOP -> ARMED -> READY and never stopped again.
Log a timestamped timeline of status and commands for consecutive single shots
with no input signal, arming with ':TRIGger:SWEep SINGle' only.

Usage: python dbg0b_shots.py [@py|@ivi]
Scope only; generator untouched. Sweep mode is restored at the end."""
import sys
import time

import iolayer as io
from common import SCOPE_PID, SCOPE_VID, find_resource, open_rm

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "@py"
rm = open_rm(BACKEND)
sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
sc.connect(build_tables=False)
sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)
print("backend", BACKEND, "tb", sc.tb, "sweep", sweep0, "status", sc.status())


def shot(i, force_at, watch_after=1.2):
    ev = []
    t0 = time.perf_counter()
    sc.write(":TRIGger:SWEep SINGle")
    ev.append((round(time.perf_counter() - t0, 2), "cmd SINGle"))
    forced, last, t_stop = False, None, None
    while True:
        st = sc.status()
        el = time.perf_counter() - t0
        if st != last:
            ev.append((round(el, 2), st))
            last = st
        if st == "STOP" and t_stop is None and forced:
            t_stop = el
        if st != "STOP":
            t_stop = None if not forced else t_stop
        if not forced and st in ("READY", "ARMED", "WAIT") and el > force_at:
            sc.write(":TRIGger:FORCe")
            forced = True
            ev.append((round(time.perf_counter() - t0, 2), "cmd FORCe"))
        if t_stop is not None and el - t_stop > watch_after:
            break
        if el > 6:
            ev.append((round(el, 2), "GAVE UP"))
            break
        time.sleep(0.01)
    print(f"  shot {i:2d} force@{force_at}: {ev}")


tb0 = sc.tb
try:
    if len(sys.argv) > 2:           # optional timebase in s/div (must be a real step)
        sc.tb = sc.set_verified(":TIMebase:SCALe", io.plain_decimal(float(sys.argv[2])), io.v_float,
                                float(sys.argv[2]))
        print("timebase set to", sc.tb)
    for force_at in (0.6, 1.0):
        sc.free_run()
        time.sleep(0.8)
        for i in range(1, 7):
            shot(i, force_at)
finally:
    sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
    sc.free_run()                  # was sc.write(":RUN") before 0c
    sc.set_verified(":TIMebase:SCALe", io.plain_decimal(tb0), io.v_float, tb0)
    print("restored sweep", sc.query(":TRIGger:SWEep?", io.V_SWEEP), "| stats", sc.stats)
    sc.close()
    rm.close()
