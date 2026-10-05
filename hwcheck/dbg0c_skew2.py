"""Milestone 0c investigation, part 2.

Part 1 (dbg0c_skew.py) did NOT reproduce the offset: after setup the channels
were aligned (+1.1 deg = 150 ps at 20 MHz) and stayed so through timebase and
V/div changes, coupling, BW limit, trigger source, STOP/RUN, channel toggles
at 25 ns/div and two full table walks. (Its first capture was garbage only
because the generator had just been switched on and the shot was force-triggered.)

The offsets seen earlier were about 2.1 ns and 4.1 ns, i.e. close to one sample
period at 500 MSa/s and 250 MSa/s. Hypothesis: the alignment is fixed at the
moment a channel is ENABLED, and depends on the scope's state at that moment.
My tests end by restoring the user's settings (which can switch CH2 off) and
the next test's setup switches it on again in whatever state the scope is in.

So here a channel is toggled under different conditions, then the scope is
brought back to 25 ns/div and CH2-CH1 is measured at 20 MHz:
  A. CH2 toggled at each of several timebases
  B. CH1 toggled at several timebases
  C. CH2 toggled while stopped after a single shot / while :STOP
  D. CH3 switched on and off (changes how the ADC is shared)
  E. new session with device clear, five times
Whenever the offset is more than 500 ps from the aligned value, CH2 is toggled
at 25 ns/div to see whether that repairs it.
Same wiring and safety rules as part 1."""

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
import traceback

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from dbg0c_skew import F, TB_STEPS, VD_STEPS, measure, out
from t0b_iolayer import Saver, b01


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
    sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
    gs = ss = sweep0 = None
    try:
        g.connect()
        sc.connect(build_tables=False)
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
        ss.save(":CHANnel3:DISPlay", io.v_bool, b01)
        ss.save(":TIMebase:SCALe", io.v_float, num)
        ss.save(":TRIGger:LEVel", io.v_float, num)
        ss.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
        ss.save(":TRIGger:SOURce", io.V_TRIGSRC)
        ss.save(":TRIGger:MODE", io.V_TRIGMODE)
        sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)
        print("scope as found:", [(c_, v_) for c_, _, v_, _ in ss.items if "DISPlay" in c_ or "TIMebase" in c_])

        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")
        for ch in (1, 2):
            sc.configure_channel(ch, "DC", False, 0.0)
        sc.tb_steps, sc.vdiv_steps = TB_STEPS, VD_STEPS
        for ch in (1, 2):
            sc.set_vdiv(ch, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.set_timebase(25e-9, "exact")
        sc.free_run()
        g.output(1, True)
        time.sleep(2.0)

        def disp(ch, on):
            sc.set_verified(f":CHANnel{ch}:DISPlay", "1" if on else "0", io.v_bool, bool(on))   # U1K p.13

        def toggle(ch, gap=0.3):
            disp(ch, False)
            time.sleep(gap)
            disp(ch, True)
            time.sleep(0.5)

        def toggle_at(ch, tb):
            sc.set_timebase(tb, "exact")
            time.sleep(0.5)
            toggle(ch)
            sc.set_timebase(25e-9, "exact")

        def toggle_after_single(ch):
            sc.acquire([1])                       # leaves the scope stopped in single mode
            toggle(ch)
            sc.free_run()

        def toggle_while_stopped(ch):
            sc.write(":STOP")                     # U1K p.6
            time.sleep(0.3)
            toggle(ch)
            sc.write(":RUN")                      # U1K p.5

        def ch3(on):
            disp(3, on)
            time.sleep(0.5)

        def reconnect():
            nonlocal sc
            tables = (sc.tb_steps, sc.vdiv_steps)
            sc.close()
            time.sleep(0.5)
            sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
            sc.connect(build_tables=False)        # resync: :RUN + device clear + sentinel
            sc.tb_steps, sc.vdiv_steps = tables
            sc.tb = sc.query(":TIMebase:SCALe?", io.v_float)
            ss.dev = sc

        ref = measure(sc, "0. reference (as set up)")
        aligned = ref["delay_ps"]
        actions = []
        for tb in (1e-9, 1e-8, 2.5e-8, 5e-8, 5e-7, 5e-6, 5e-4, 5e-3, 2e-2):
            actions.append((f"A. CH2 toggled at {tb:g} s/div", lambda tb=tb: toggle_at(2, tb)))
        for tb in (1e-9, 5e-8, 5e-4, 2e-2):
            actions.append((f"B. CH1 toggled at {tb:g} s/div", lambda tb=tb: toggle_at(1, tb)))
        actions += [("C. CH2 toggled while stopped after a single shot", lambda: toggle_after_single(2)),
                    ("C. CH1 toggled while stopped after a single shot", lambda: toggle_after_single(1)),
                    ("C. CH2 toggled while :STOP", lambda: toggle_while_stopped(2)),
                    ("C. CH1 toggled while :STOP", lambda: toggle_while_stopped(1)),
                    ("D. CH3 switched ON (CH1+CH2+CH3 active)", lambda: ch3(True)),
                    ("D. CH3 switched OFF again", lambda: ch3(False)),
                    ("D. CH3 ON", lambda: ch3(True)),
                    ("D. CH3 OFF", lambda: ch3(False))]
        actions += [(f"E. new session + device clear #{i}", reconnect) for i in range(1, 6)]
        for name, fn in actions:
            try:
                fn()
                time.sleep(0.5)
                r = measure(sc, name)
                if abs(r["delay_ps"] - aligned) > 500:
                    r["misaligned"] = True
                    print(f"      ^^^ MISALIGNED by {r['delay_ps'] - aligned:+.0f} ps; toggling CH2 at 25 ns/div")
                    toggle(2)
                    r2 = measure(sc, "   repair: CH2 display off/on")
                    r2["repair_of"] = name
            except Exception as e:
                print(f"{name}: ERROR {type(e).__name__}: {str(e)[:300]}")
                out["rows"].append(dict(label=name, error=str(e)))
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        g.safe_off()
        try:
            print("generator outputs ON at end?", [g.output(1), g.output(2)])
            print("gen restore failures:", gs.restore() if gs else "not saved")
        except Exception as e:
            print("gen end error", e)
        try:
            sc.free_run()
            bad = ss.restore() if ss else ["not saved"]
            if sweep0:
                sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
            print("scope restore failures:", bad, "| stats", sc.stats)
        except Exception as e:
            print("scope end error", e)
        g.close()
        sc.close()
        rm.close()
        print("saved", save("dbg0c_skew2.json", out))


if __name__ == "__main__":
    main()
