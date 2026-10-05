"""Milestone 0c investigation, part 5.

Part 4: session reopen, new ResourceManager, device clear, generator off/on,
frequency change, trigger loss, ':RUN', ':WAVeform:MODE NORMal' and a
5 ms / 5 V excursion each left the offset unchanged (0 jumps in 29 events).

The only jump seen under script control (part 2) came at a full reconnect
(iolayer connect(): ':RUN', device clear, sentinels, WAVeform MODE + FORMat)
that directly followed CH3 being switched on and off. Hypothesis: changing
WHICH channels are enabled (which changes how the ADC is shared) arms a
re-alignment that takes effect at a later step of the reconnect.

Each cycle here:  CH3 ON -> CH3 OFF -> one follow-up step, with a measurement
after every step. Follow-up steps are tried separately:
    full connect() | ':RUN' | device clear | WAVeform MODE+FORMat (verified)
and a control cycle with the follow-up but WITHOUT the CH3 toggle.
Also: CH2 OFF/ON and CH1 OFF/ON followed by a full connect().
Nobody should touch the scope during this run.
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


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
    res = find_resource(rm, SCOPE_VID, SCOPE_PID)
    H = {"sc": io.ScopeIO(rm, res)}
    gs = ss = sweep0 = None
    try:
        sc = H["sc"]
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
        ss.save(":CHANnel3:DISPlay", io.v_bool, b01)
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

        S = lambda: H["sc"]

        def carry(new, old):
            new.tb, new.tb_steps, new.vdiv_steps, new.vdiv = old.tb, old.tb_steps, old.vdiv_steps, dict(old.vdiv)
            H["sc"] = new
            ss.dev = new

        def disp(ch, on):
            S().set_verified(f":CHANnel{ch}:DISPlay", "1" if on else "0", io.v_bool, bool(on))
            time.sleep(0.6)

        def full_connect():
            old = S()
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            n.connect(build_tables=False)
            carry(n, old)
            n.tb = n.query(":TIMebase:SCALe?", io.v_float)

        def clear_only():
            old = S()
            old.close()
            time.sleep(0.3)
            usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False)
            time.sleep(0.3)
            n = io.ScopeIO(rm, res)
            n.idn = n.query("*IDN?", io.v_scope_idn)
            carry(n, old)

        def wav_verified():
            S().set_verified(":WAVeform:MODE", "NORMal", io.V_WAVMODE, "NORMal")
            S().set_verified(":WAVeform:FORMat", "BYTE", io.V_WAVFMT, "BYTE")

        followups = [("full connect()", full_connect), (":RUN", lambda: S().write(":RUN")),
                     ("device clear", clear_only), ("WAVeform MODE+FORMat verified", wav_verified)]
        state = {"last": measure(S(), "start: state as found")}
        tally = {}

        def step(label, fn, key):
            try:
                fn()
                time.sleep(0.7)
                r = measure(S(), label)
                jump = r["delay_ps"] - state["last"]["delay_ps"]
                j = round(jump / 1000.0) * 1000 if abs(jump) > 500 else 0
                tally.setdefault(key, []).append(j)
                if j:
                    print(f"      ^^^ JUMP {jump:+.0f} ps")
                state["last"] = r
            except Exception as e:
                print(f"{label}: ERROR {type(e).__name__}: {str(e)[:300]}")
                tally.setdefault(key, []).append("error")

        for rnd in (1, 2, 3):
            for fname, ffn in followups:
                step(f"r{rnd} CH3 ON", lambda: disp(3, True), "CH3 ON")
                step(f"r{rnd} CH3 OFF", lambda: disp(3, False), "CH3 OFF")
                step(f"r{rnd}   then {fname}", ffn, f"after CH3 on/off: {fname}")
            step(f"r{rnd} control: full connect() with no channel change", full_connect, "control: full connect()")
            step(f"r{rnd} CH2 OFF", lambda: disp(2, False), "CH2 OFF (CH1 only)") if False else None
            # CH2 off/on then full connect (CH1 keeps triggering)
            try:
                disp(2, False)
                disp(2, True)
            except Exception as e:
                print("CH2 toggle error", e)
            step(f"r{rnd} CH2 OFF/ON", lambda: None, "CH2 OFF/ON")
            step(f"r{rnd}   then full connect()", full_connect, "after CH2 off/on: full connect()")
        out["tally"] = tally
        print("\nJUMPS PER STEP (ps, 0 = no change)")
        for k, v in tally.items():
            print(f"  {k:48s} {v}")
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        sc = H["sc"]
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
        rm.close()
        print("saved", save("dbg0c_skew5.json", out))


if __name__ == "__main__":
    main()
