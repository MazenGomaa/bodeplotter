"""Milestone 0c investigation: channel-to-channel time offset that depends on
scope state.

Observation (user, 2026-10-05): the CH1/CH2 phase offset is visible when a test
starts, and switching a scope channel off and on makes it disappear, with the
wiring untouched.

Both probes (10X) are on generator CH1. Generator: 20 MHz, 1 Vpp, High-Z.
Each measurement = 6 single-shot two-channel captures through iolayer; the
CH2-CH1 phase is converted to a delay in ps (360 deg = 50 ns at 20 MHz).

Plan:
  1. measure the state the normal setup leaves
  2. toggle :CHANnel2:DISPlay off/on (U1K p.13) by command, measure
  3. apply one setup action at a time, measure after each; whenever the offset
     moves by more than 300 ps, toggle CH2 and measure again
  4. repeat the toggle several times to see whether it always lands aligned
Only documented commands. Output OFF in finally; changed settings restored.
"""
import cmath
import math
import statistics
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

F = 20e6
N = 6
TB_STEPS = [1e-9, 2e-9, 5e-9, 1e-8, 2.5e-8, 5e-8, 1e-7, 2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5,
            1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2]            # read from the scope in 0b
VD_STEPS = [5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]
out = {"rows": [], "log": []}


def log(m):
    out["log"].append(m)


def measure(sc, label):
    ph, gn, v1 = [], [], []
    for _ in range(N):
        a = sc.acquire([1, 2])
        w1, w2 = a["waves"][1], a["waves"][2]
        ff = wave.sine_fit(w1["volts"], w1["dt"], f_hint=F)["freq_hz"]
        if abs(ff - F) > 0.02 * F:
            ff = F
        a1, b1, _, _ = wave._fit3(w1["volts"], w1["dt"], ff)
        a2, b2, _, _ = wave._fit3(w2["volts"], w2["dt"], ff)
        H = complex(a2, -b2) / complex(a1, -b1)
        ph.append(math.degrees(cmath.phase(H)))
        gn.append(20 * math.log10(abs(H)))
        v1.append(2 * math.hypot(a1, b1) * 10)
    m, sd = statistics.mean(ph), statistics.stdev(ph)
    row = dict(label=label, phase_deg=m, sd=sd, delay_ps=m / 360 / F * 1e12, gain_db=statistics.mean(gn),
               vpp1=statistics.mean(v1), phases=[round(x, 2) for x in ph])
    out["rows"].append(row)
    print(f"{label:58s} phase {m:+7.2f} deg (sd {sd:.2f})  = {row['delay_ps']:+6.0f} ps   "
          f"gain {row['gain_db']:+.2f} dB  Vpp {row['vpp1']:.2f}")
    return row


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID), log=log)
    sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=log)
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
        ss.save(":TIMebase:SCALe", io.v_float, num)
        ss.save(":TRIGger:LEVel", io.v_float, num)
        ss.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
        ss.save(":TRIGger:SOURce", io.V_TRIGSRC)
        ss.save(":TRIGger:MODE", io.V_TRIGMODE)
        sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)

        # the same setup the 0c test does, but WITHOUT the table walk (tables preset)
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
        time.sleep(0.8)

        def toggle(ch):
            k = f":CHANnel{ch}:DISPlay"
            sc.set_verified(k, "0", io.v_bool, False)                # U1K p.13
            time.sleep(0.3)
            sc.set_verified(k, "1", io.v_bool, True)
            time.sleep(0.5)

        def tb_away_back(other):
            sc.set_timebase(other, "exact")
            time.sleep(0.3)
            sc.set_timebase(25e-9, "exact")

        def vd_away_back(ch, other):
            sc.set_vdiv(ch, other, "exact")
            time.sleep(0.3)
            sc.set_vdiv(ch, 0.02, "exact")

        def sv(cmd, a, v, e, b_, eb):
            sc.set_verified(cmd, a, v, e)
            time.sleep(0.3)
            sc.set_verified(cmd, b_, v, eb)

        def stop_run():
            sc.write(":STOP")                                        # U1K p.6
            time.sleep(0.3)
            sc.write(":RUN")                                         # U1K p.5

        def walk():
            sc.build_tables(1)
            sc.set_timebase(25e-9, "exact")
            for ch in (1, 2):
                sc.set_vdiv(ch, 0.02, "exact")

        base = measure(sc, "1. after normal setup (no table walk)")
        toggle(2)
        ref = measure(sc, "2. after CH2 display off/on")

        actions = [
            ("nothing (repeat measurement)", lambda: None),
            ("timebase 25n -> 50n -> 25n", lambda: tb_away_back(5e-8)),
            ("timebase 25n -> 10n -> 25n", lambda: tb_away_back(1e-8)),
            ("timebase 25n -> 500n -> 25n", lambda: tb_away_back(5e-7)),
            ("timebase 25n -> 500u -> 25n", lambda: tb_away_back(5e-4)),
            ("CH1 V/div 20m -> 50m -> 20m", lambda: vd_away_back(1, 0.05)),
            ("CH2 V/div 20m -> 50m -> 20m", lambda: vd_away_back(2, 0.05)),
            ("CH1 V/div 20m -> 200m -> 20m", lambda: vd_away_back(1, 0.2)),
            ("CH2 V/div 20m -> 1m -> 20m", lambda: vd_away_back(2, 0.001)),
            ("CH1 coupling DC -> AC -> DC", lambda: sv(":CHANnel1:COUPling", "AC", io.V_COUPLING, "AC", "DC", "DC")),
            ("CH2 coupling DC -> AC -> DC", lambda: sv(":CHANnel2:COUPling", "AC", io.V_COUPLING, "AC", "DC", "DC")),
            ("CH1 BW limit FULL -> 20M -> FULL", lambda: sv(":CHANnel1:BWLimit", "20M", io.V_BWL, "20M", "FULL", "FULL")),
            ("CH2 BW limit FULL -> 20M -> FULL", lambda: sv(":CHANnel2:BWLimit", "20M", io.V_BWL, "20M", "FULL", "FULL")),
            ("trigger source CH1 -> CH2 -> CH1",
             lambda: sv(":TRIGger:SOURce", "CHANnel2", io.V_TRIGSRC, "CHANnel2", "CHANnel1", "CHANnel1")),
            (":STOP then :RUN", stop_run),
            ("free_run (sweep AUTO + :RUN) and wait 1 s", lambda: (sc.free_run(), time.sleep(1.0))),
            ("CH1 display off/on", lambda: toggle(1)),
            ("CH2 display off/on", lambda: toggle(2)),
            ("CH2 display off/on", lambda: toggle(2)),
            ("CH1 display off/on", lambda: toggle(1)),
            ("full table walk (build_tables), then back to 25n / 20m", walk),
            ("CH2 display off/on", lambda: toggle(2)),
            ("full table walk again", walk),
            ("CH1 display off/on", lambda: toggle(1)),
        ]
        last = ref
        for name, fn in actions:
            try:
                fn()
                time.sleep(0.5)
                r = measure(sc, "3. " + name)
                moved = abs(r["delay_ps"] - last["delay_ps"]) > 300
                r["moved_from_previous"] = moved
                if moved:
                    print(f"      ^^^ offset MOVED by {r['delay_ps'] - last['delay_ps']:+.0f} ps")
                last = r
            except Exception as e:
                print(f"3. {name}: ERROR {type(e).__name__}: {str(e)[:200]}")
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
        print("saved", save("dbg0c_skew.json", out))


if __name__ == "__main__":
    if "--allow-run" not in sys.argv:
        raise SystemExit("dbg0c_skew.py: historical script that sends ':RUN'. Pass --allow-run to run it.")
    main()
