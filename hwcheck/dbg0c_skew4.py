"""Milestone 0c investigation, part 4.

Known so far (20 MHz, both 10X probes on generator CH1):
  - CH2-CH1 offset takes discrete values 2.000 ns apart: seen about +150 ps
    (aligned), +2150 ps, -1850 ps, and earlier (1X runs) about +4100 ps.
    2 ns is one sample period at 500 MSa/s.
  - Within a run it is rock steady (sd about 0.1 deg) and is NOT changed by
    timebase, V/div, coupling, BW limit, trigger source, :STOP/:RUN, channel
    display toggles by command, CH3 on/off, or a table walk (parts 1 and 2).
  - It changed at 'new session + device clear' (part 2) and between two
    separate script runs (part 3). No command tried in part 3 repaired it.

This part does not try to repair anything. From whatever state the scope is
in, it applies ONE candidate event, measures, and records the jump, several
times per event:
  a. session close + open (same ResourceManager)
  b. ResourceManager close + new one (libusb re-initialised), session reopened
  c. USBTMC device clear only
  d. generator output OFF 2 s, then ON (signal and trigger lost and regained)
  e. generator frequency 20 MHz -> 1 kHz -> 20 MHz
  f. trigger level to +0.08 V (above the 0.05 V peak: no trigger, AUTO free-runs), then 0
  g. ':RUN' while running
  h. ':WAVeform:MODE NORMal'
  i. scope settings to 'user-like' values (5 ms/div, 5 V/div) and back
Same wiring and safety rules as before."""

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
import statistics
import time
import traceback

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from dbg0c_skew import F, TB_STEPS, VD_STEPS, measure, out
from t0b_iolayer import Saver, b01
from usbclear import usbtmc_clear


def main():
    H = {"rm": open_rm("@py")}
    H["g"] = io.GenIO(H["rm"], find_resource(H["rm"], GEN_VID, GEN_PID))
    H["res"] = find_resource(H["rm"], SCOPE_VID, SCOPE_PID)
    H["sc"] = io.ScopeIO(H["rm"], H["res"])
    gs = ss = sweep0 = None
    try:
        g, sc = H["g"], H["sc"]
        g.connect()
        sc.idn = sc.query("*IDN?", io.v_scope_idn)
        sc.tb = sc.query(":TIMebase:SCALe?", io.v_float)
        g.output(1, False)
        g.output(2, False)
        num, probe = io.GenFmt.num, io.ScopeFmt.probe
        gs = Saver(g)
        c = ":CHANnel1"
        for k, v, f in ((c + ":BASE:OFFSet", io.v_float, num), (c + ":BASE:AMPLitude", io.v_float, num),
                        (c + ":BASE:FREQuency", io.v_float, num), (c + ":AMPLitude:UNIT", g.V_UNIT, lambda x: x),
                        (c + ":LOAD", io.v_float, num), (c + ":BASE:WAVe", g.V_WAVE, lambda x: x)):
            gs.save(k, v, f)
        ss = Saver(sc)
        for ch in (1, 2):
            k = f":CHANnel{ch}"
            ss.save(k + ":SCALe", io.v_float, num)
            ss.save(k + ":OFFSet", io.v_float, num)
            ss.save(k + ":BWLimit", io.V_BWL)
            ss.save(k + ":COUPling", io.V_COUPLING)
            ss.save(k + ":VERNier", io.v_bool, b01)
            ss.save(k + ":PROBe", io.v_float, probe)
            ss.save(k + ":DISPlay", io.v_bool, b01)
        ss.save(":TIMebase:SCALe", io.v_float, num)
        ss.save(":TRIGger:LEVel", io.v_float, num)
        ss.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
        ss.save(":TRIGger:SOURce", io.V_TRIGSRC)
        ss.save(":TRIGger:MODE", io.V_TRIGMODE)
        sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)

        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")
        for ch in (1, 2):
            sc.configure_channel(ch, "DC", False, 0.0)
        sc.tb_steps, sc.vdiv_steps = TB_STEPS, VD_STEPS
        for ch in (1, 2):
            sc.set_vdiv(ch, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.set_timebase(25e-9, "exact")
        g.output(1, True)
        time.sleep(2.0)

        def carry(new, old):
            new.tb, new.tb_steps, new.vdiv_steps, new.vdiv = old.tb, old.tb_steps, old.vdiv_steps, dict(old.vdiv)
            new.idn = new.query("*IDN?", io.v_scope_idn)
            H["sc"] = new
            ss.dev = new

        def reopen():
            old = H["sc"]
            old.close()
            time.sleep(0.5)
            carry(io.ScopeIO(H["rm"], H["res"]), old)

        def new_rm():
            old, og = H["sc"], H["g"]
            old.close()
            og.inst.close()
            H["rm"].close()
            time.sleep(1.0)
            H["rm"] = open_rm("@py")
            ng = io.GenIO(H["rm"], find_resource(H["rm"], GEN_VID, GEN_PID))
            ng.connect()
            H["g"] = ng
            gs.dev = ng
            n = io.ScopeIO(H["rm"], H["res"])
            n.rm = H["rm"]
            carry(n, old)

        def clear_only():
            old = H["sc"]
            old.close()
            time.sleep(0.3)
            usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False)
            time.sleep(0.3)
            carry(io.ScopeIO(H["rm"], H["res"]), old)

        def out_off_on():
            H["g"].output(1, False)
            time.sleep(2.0)
            H["g"].output(1, True)
            time.sleep(1.5)

        def freq_away_back():
            H["g"].set_frequency(1, 1000.0)
            time.sleep(1.5)
            H["g"].set_frequency(1, F)
            time.sleep(1.5)

        def trig_lost():
            H["sc"].set_verified(":TRIGger:LEVel", "0.08", io.v_float, 0.08, tol_abs=0.001)
            time.sleep(2.0)
            H["sc"].set_verified(":TRIGger:LEVel", "0", io.v_float, 0.0, tol_abs=0.001)
            time.sleep(1.0)

        def user_like():
            s = H["sc"]
            s.set_timebase(5e-3, "exact")
            s.set_vdiv(1, 5.0, "exact")
            s.set_vdiv(2, 5.0, "exact")
            time.sleep(1.0)
            s.set_vdiv(1, 0.02, "exact")
            s.set_vdiv(2, 0.02, "exact")
            s.set_timebase(25e-9, "exact")

        events = [("a. session close + open", reopen, 4),
                  ("b. new ResourceManager (libusb re-init)", new_rm, 3),
                  ("c. USBTMC device clear only", clear_only, 4),
                  ("d. generator output OFF 2 s then ON", out_off_on, 4),
                  ("e. generator 20 MHz -> 1 kHz -> 20 MHz", freq_away_back, 3),
                  ("f. trigger level 0.08 V (no trigger) then 0", trig_lost, 3),
                  ("g. :RUN while running", lambda: H["sc"].write(":RUN"), 3),
                  ("h. :WAVeform:MODE NORMal", lambda: H["sc"].write(":WAVeform:MODE NORMal"), 3),
                  ("i. 5 ms/div + 5 V/div and back", user_like, 2)]
        last = measure(H["sc"], "start: state as found")
        tally = {}
        for name, fn, reps in events:
            for i in range(1, reps + 1):
                try:
                    fn()
                    time.sleep(0.7)
                    r = measure(H["sc"], f"{name} #{i}")
                    jump = r["delay_ps"] - last["delay_ps"]
                    r["jump_ps"] = jump
                    tally.setdefault(name, []).append(round(jump / 1000.0) * 1000 if abs(jump) > 500 else 0)
                    if abs(jump) > 500:
                        print(f"      ^^^ JUMP {jump:+.0f} ps")
                    last = r
                except Exception as e:
                    print(f"{name} #{i}: ERROR {type(e).__name__}: {str(e)[:300]}")
                    tally.setdefault(name, []).append("error")
        out["tally"] = tally
        print("\nJUMPS PER EVENT (ps, 0 = no change)")
        for k, v in tally.items():
            print(f"  {k:46s} {v}")
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        g, sc = H["g"], H["sc"]
        g.safe_off()
        try:
            print("generator outputs ON at end?", [g.output(1), g.output(2)])
            print("gen restore failures:", gs.restore() if gs else "not saved")
        except Exception as e:
            print("gen end error", e)
        try:
            bad = ss.restore() if ss else ["not saved"]
            if sweep0:
                sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
            print("scope restore failures:", bad, "| stats", sc.stats)
        except Exception as e:
            print("scope end error", e)
        g.close()
        sc.close()
        H["rm"].close()
        print("saved", save("dbg0c_skew4.json", out))


if __name__ == "__main__":
    main()
