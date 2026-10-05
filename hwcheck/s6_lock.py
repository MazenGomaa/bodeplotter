"""Milestone 6 bench check: ':SYSTem:LOCK' on the scope (U1K p.6).

The manual contradicts itself: "Query returns full keyboard locked status, 0 represents
locked, 1 represents unlock", but its example says ":SYSTem:LOCK? Query returns 1, it
represents locked". This script finds out which, in steps the user can watch:

Usage: python s6_lock.py [@py] query      read the state only
       python s6_lock.py [@py] on         ':SYSTem:LOCK ON', read back, leave it like that
       python s6_lock.py [@py] off        ':SYSTem:LOCK OFF', read back, leave it like that
       python s6_lock.py [@py] hold-on N  lock, keep the USB session open N seconds, unlock

After 'on' and after 'off' the user presses a front-panel key and says whether the scope
reacted. The last step run must be 'off' so the keyboard is never left locked.
Whether remote control still works while locked is checked with two queries and one
set-and-restore of the trigger level. Generator outputs are not touched. No ':RUN'.
"""
import sys
import time
import traceback

import iolayer as io
from common import SCOPE_PID, SCOPE_VID, find_resource, open_rm, save

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
ARGS = [a for a in sys.argv[1:] if not a.startswith("@")]
STEP = ARGS[0] if ARGS else "query"
HOLD = float(ARGS[1]) if len(ARGS) > 1 else 0.0
out = {"backend": BACKEND, "step": STEP, "log": []}
LOCK = ":SYSTem:LOCK"                                               # U1K p.6


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def raw(r):
    return r


def remote_still_works(sc):
    """Two queries and one harmless set-and-restore while in the current lock state."""
    r = {"timebase": sc.query(":TIMebase:SCALe?", io.v_float),                  # U1K p.16
         "status": sc.query(":TRIGger:STATus?", io.V_STATUS)}                   # U1K p.37
    lvl = sc.query(":TRIGger:LEVel?", io.v_float)                               # U1K p.37
    vd = sc.query(":CHANnel1:SCALe?", io.v_float)                               # U1K p.14
    step = vd / sc.CODES_PER_DIV
    try:
        sc.set_verified(":TRIGger:LEVel", io.ScopeFmt.num(lvl + 5 * step), io.v_float, lvl + 5 * step,
                        tol_abs=step)
        r["set_while_in_this_state"] = "ok"
    except Exception as e:
        r["set_while_in_this_state"] = f"{type(e).__name__}: {e}"
    finally:
        sc.set_verified(":TRIGger:LEVel", io.ScopeFmt.num(lvl), io.v_float, lvl, tol_abs=step)
    return r


def main():
    rm = open_rm(BACKEND)
    sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=log)
    try:
        out["scope_idn"] = sc.connect(build_tables=False)
        out["lock_before"] = sc.query(LOCK + "?", raw)
        print("':SYSTem:LOCK?' before:", repr(out["lock_before"]))
        if STEP in ("on", "hold-on"):
            sc.write(LOCK + " ON")
        elif STEP == "off":
            sc.write(LOCK + " OFF")
        elif STEP != "query":
            raise SystemExit("step must be query, on, off or hold-on")
        time.sleep(0.3)
        out["lock_after"] = sc.query(LOCK + "?", raw)
        print(f"':SYSTem:LOCK?' after '{STEP}':", repr(out["lock_after"]))
        out["remote"] = remote_still_works(sc)
        print("remote control in this state:", out["remote"])
        out["error_queue"] = sc.error_queue()
        print("':SYSTem:ERRor?':", out["error_queue"])
        if STEP == "hold-on":
            print(f"keyboard lock command sent; holding the session open for {HOLD:g} s ...", flush=True)
            time.sleep(HOLD)
            out["lock_end_of_hold"] = sc.query(LOCK + "?", raw)
            sc.write(LOCK + " OFF")
            time.sleep(0.3)
            out["lock_after_off"] = sc.query(LOCK + "?", raw)
            print("after the hold:", repr(out["lock_end_of_hold"]), " after OFF:", repr(out["lock_after_off"]))
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        out["scope_stats"] = dict(sc.stats)
        sc.close()
        rm.close()
        print("saved", save(f"s6_lock_{STEP}_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
