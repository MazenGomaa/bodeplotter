"""Milestone 0c investigation, part 3.

Part 2 reproduced the offset: after 'new session + device clear' CH2-CH1 moved
by +1992..+2000 ps (one sample at 500 MSa/s), 5 times out of 5, and a CH2
display off/on by command did NOT repair it.

A new session in iolayer does, in order: session close/open, ':RUN', USBTMC
device clear (pyusb), *IDN?/*OPC? sentinels, ':WAVeform:MODE NORMal',
':WAVeform:FORMat BYTE'. This script
  1. measures the state as found
  2. tries repair candidates one at a time until the channels are aligned
  3. from the aligned state applies each suspect on its own (3 times each),
     measuring after each, and repairs whenever the offset comes back
Same wiring (both 10X probes on generator CH1, 20 MHz 1 Vpp) and safety rules."""

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
from usbclear import usbtmc_clear

ALIGNED_MAX_PS = 700          # aligned state measured +135..+162 ps; misaligned +2143..+2154 ps


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
    res = find_resource(rm, SCOPE_VID, SCOPE_PID)
    holder = {"sc": io.ScopeIO(rm, res)}
    gs = ss = sweep0 = None
    try:
        sc = holder["sc"]
        g.connect()
        # deliberately NOT sc.connect(): no :RUN, no device clear, no WAVeform writes yet
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
        print("readout state as found:", [sc.query(q, lambda r: r) for q in
                                          (":WAVeform:SOURce?", ":WAVeform:MODE?", ":WAVeform:FORMat?")])

        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")
        for ch in (1, 2):
            sc.configure_channel(ch, "DC", False, 0.0)
        sc.tb_steps, sc.vdiv_steps = TB_STEPS, VD_STEPS
        for ch in (1, 2):
            sc.set_vdiv(ch, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.set_timebase(25e-9, "exact")
        sc.set_verified(":TRIGger:SWEep", "AUTO", io.V_SWEEP, "AUTO")
        g.output(1, True)
        time.sleep(2.0)

        S = lambda: holder["sc"]

        def disp(ch, on):
            S().set_verified(f":CHANnel{ch}:DISPlay", "1" if on else "0", io.v_bool, bool(on))

        def toggle(ch, gap=1.0):
            disp(ch, False)
            time.sleep(gap)
            disp(ch, True)
            time.sleep(1.0)

        def both_off_on():
            # CH1 is the trigger source; switch CH2 off first, then CH1, then both on
            disp(2, False); time.sleep(0.5)
            disp(1, False); time.sleep(1.0)
            disp(1, True); time.sleep(0.5)
            disp(2, True); time.sleep(1.0)

        def tb_away_back():
            S().set_timebase(5e-4, "exact"); time.sleep(0.5); S().set_timebase(25e-9, "exact")

        def stop_run():
            S().write(":STOP"); time.sleep(0.5); S().write(":RUN")

        def reopen_only():
            old = holder["sc"]
            tb, tabs = old.tb, (old.tb_steps, old.vdiv_steps)
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            n.tb, (n.tb_steps, n.vdiv_steps) = tb, tabs
            n.idn = n.query("*IDN?", io.v_scope_idn)
            holder["sc"] = n
            ss.dev = n

        def clear_only():
            old = holder["sc"]
            tb, tabs = old.tb, (old.tb_steps, old.vdiv_steps)
            old.close()
            time.sleep(0.3)
            usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False)
            time.sleep(0.3)
            n = io.ScopeIO(rm, res)
            n.tb, (n.tb_steps, n.vdiv_steps) = tb, tabs
            n.idn = n.query("*IDN?", io.v_scope_idn)
            holder["sc"] = n
            ss.dev = n

        def wav(cmd):
            return lambda: S().write(cmd)

        def src_then_mode(ch):
            def f():
                S().write(f":WAVeform:SOURce CHANnel{ch}")
                S().write(":WAVeform:MODE NORMal")
            return f

        def is_aligned(r):
            return abs(r["delay_ps"]) < ALIGNED_MAX_PS

        repairs = [("CH2 display off/on (1 s gap)", lambda: toggle(2)),
                   ("CH1 display off/on (1 s gap)", lambda: toggle(1)),
                   ("both channels off, then on", both_off_on),
                   (":STOP then :RUN", stop_run),
                   ("timebase 25n -> 500u -> 25n", tb_away_back),
                   (":WAVeform:SOURce CHANnel1 then :WAVeform:MODE NORMal", src_then_mode(1)),
                   (":WAVeform:SOURce CHANnel2 then :WAVeform:MODE NORMal", src_then_mode(2)),
                   (":WAVeform:MODE RAW then NORMal", lambda: (S().write(":WAVeform:MODE RAW"),
                                                               S().write(":WAVeform:MODE NORMal")))]
        working = []

        def repair(context):
            for name, fn in repairs:
                try:
                    fn()
                    time.sleep(0.5)
                    r = measure(S(), f"   repair try: {name}")
                    r["repair_context"] = context
                    if is_aligned(r):
                        working.append(name)
                        print(f"      -> REPAIRED by: {name}")
                        return True
                except Exception as e:
                    print(f"   repair try {name}: ERROR {type(e).__name__}: {str(e)[:200]}")
            print("      -> no repair candidate worked")
            return False

        r = measure(S(), "1. state as found (no connect(), no clear, no :RUN)")
        if not is_aligned(r):
            print("   misaligned as found")
            if not repair("as found"):
                raise RuntimeError("could not reach the aligned state by command")

        suspects = [("session close + open only", reopen_only),
                    (":RUN while running", wav(":RUN")),
                    (":WAVeform:FORMat BYTE", wav(":WAVeform:FORMat BYTE")),
                    (":WAVeform:MODE NORMal (source as left = CH2)", wav(":WAVeform:MODE NORMal")),
                    (":WAVeform:SOURce CHANnel1, then MODE NORMal", src_then_mode(1)),
                    (":WAVeform:SOURce CHANnel2, then MODE NORMal", src_then_mode(2)),
                    ("USBTMC device clear only (close, INITIATE_CLEAR, open)", clear_only)]
        tally = {}
        for rnd in (1, 2, 3):
            for name, fn in suspects:
                try:
                    fn()
                    time.sleep(0.7)
                    r = measure(S(), f"3.{rnd} {name}")
                    bad = not is_aligned(r)
                    tally.setdefault(name, []).append("MISALIGNED" if bad else "aligned")
                    if bad:
                        print("      ^^^ this action misaligned the channels")
                        if not repair(name):
                            raise RuntimeError("could not repair")
                except RuntimeError:
                    raise
                except Exception as e:
                    print(f"3.{rnd} {name}: ERROR {type(e).__name__}: {str(e)[:300]}")
                    tally.setdefault(name, []).append("error")
        out["tally"], out["working_repairs"] = tally, working
        print("\nSUSPECT TALLY")
        for k, v in tally.items():
            print(f"  {k:58s} {v}")
        print("REPAIRS THAT WORKED:", working)
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        sc = holder["sc"]
        g.safe_off()
        try:
            print("generator outputs ON at end?", [g.output(1), g.output(2)])
            print("gen restore failures:", gs.restore() if gs else "not saved")
        except Exception as e:
            print("gen end error", e)
        try:
            sc.set_verified(":TRIGger:SWEep", "AUTO", io.V_SWEEP, "AUTO")
            bad = ss.restore() if ss else ["not saved"]
            if sweep0:
                sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
            print("scope restore failures:", bad, "| stats", sc.stats)
        except Exception as e:
            print("scope end error", e)
        g.close()
        sc.close()
        rm.close()
        print("saved", save("dbg0c_skew3.json", out))


if __name__ == "__main__":
    main()
