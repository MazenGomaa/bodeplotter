"""Milestone 0b troubleshooting: ScopeIO.acquire() timed out with the status
stuck at AUTO after ':TRIGger:SWEep SINGle' + ':RUN' (t0b runs 4 and 5), while
the same two commands in dbg0b_probe.py reached READY after 0.47 s.
Print status timelines for several arming sequences and polling rates.
Scope only, no input signal needed, generator untouched."""

def _run_guard():
    """This script deliberately sends ':RUN' to the scope. Since Milestone 0c that
    is known to shift the scope's channels against each other (HW_REPORT.md 12.11),
    so it refuses to start unless that is explicitly accepted."""
    import sys
    if "--allow-run" not in sys.argv:
        raise SystemExit(__file__ + ": historical script that sends ':RUN' (shifts the scope's channel "
                         "alignment). Not run. Pass --allow-run to run it anyway, then use s0c_realign.py.")
    sys.argv.remove("--allow-run")


_run_guard()
import time

import iolayer as io
from common import SCOPE_PID, SCOPE_VID, find_resource, open_rm

rm = open_rm("@ivi")
sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
sc.connect(build_tables=False)
sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)
print("tb", sc.tb, "sweep", sweep0, "status", sc.status(),
      "| CH1/CH2 display", sc.query(":CHANnel1:DISPlay?", io.v_bool), sc.query(":CHANnel2:DISPlay?", io.v_bool))


def timeline(label, secs, poll):
    seen, t0 = [], time.perf_counter()
    while time.perf_counter() - t0 < secs:
        st = sc.status()
        if not seen or seen[-1][1] != st:
            seen.append((round(time.perf_counter() - t0, 2), st))
        time.sleep(poll)
    print(f"  {label:44s} {seen}")
    return seen[-1][1]


def reset():
    sc.set_verified(":TRIGger:SWEep", "AUTO", io.V_SWEEP, "AUTO")
    sc.write(":RUN")
    time.sleep(0.8)


try:
    for poll in (0.02, 0.2):
        print(f"poll interval {poll}s")
        reset()
        sc.write(":TRIGger:SWEep SINGle")
        sc.write(":RUN")
        timeline("A: write SINGle, :RUN", 2.5, poll)
        sc.write(":TRIGger:FORCe")
        timeline("   then :TRIGger:FORCe", 1.0, poll)

        reset()
        sc.write(":TRIGger:SWEep SINGle")
        timeline("B: write SINGle only (no :RUN)", 2.5, poll)
        sc.write(":TRIGger:FORCe")
        timeline("   then :TRIGger:FORCe", 1.0, poll)

        reset()
        sc.set_verified(":TRIGger:SWEep", "SINGle", io.V_SWEEP, "SINGle")
        sc.write(":RUN")
        timeline("C: set_verified SINGle (read back), :RUN", 2.5, poll)
        sc.write(":TRIGger:FORCe")
        timeline("   then :TRIGger:FORCe", 1.0, poll)

        reset()
        sc.write(":STOP")
        time.sleep(0.3)
        sc.write(":TRIGger:SWEep SINGle")
        sc.write(":RUN")
        timeline("D: :STOP first, write SINGle, :RUN", 2.5, poll)
        sc.write(":TRIGger:FORCe")
        st = timeline("   then :TRIGger:FORCe", 1.0, poll)
        # second shot from the stopped single state
        sc.write(":RUN")
        timeline("D2: second shot: :RUN only", 2.5, poll)
        sc.write(":TRIGger:FORCe")
        timeline("   then :TRIGger:FORCe", 1.0, poll)
finally:
    sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
    sc.write(":RUN")
    print("restored sweep", sc.query(":TRIGger:SWEep?", io.V_SWEEP), "stats", sc.stats)
    sc.close()
    rm.close()
