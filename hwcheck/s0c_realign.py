"""Milestone 0c: check the scope's CH1/CH2 alignment and, if it is off by whole
samples, re-roll it until it is aligned.

REQUIRES both probes on the SAME node (generator CH1). 20 MHz, 1 Vpp, High-Z.

No documented command was found that undoes a shift (dbg0c_skew7.py). The only
thing known to change the alignment is the fault itself: ':RUN' sent after the
USB session has been reopened (ScopeIO.NO_RUN). So this tool measures the
CH2-CH1 delay and, while it is more than 1 ns from zero, reopens the session and
sends ':RUN' (raw, bypassing the layer's block), then measures again.
Output OFF in finally; generator and scope settings read at the start are put back."""
import sys
import time
import traceback

import iolayer as io
import dbg0c_skew
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from dbg0c_skew import F, TB_STEPS, VD_STEPS, measure, out

dbg0c_skew.N = 3
CHECK_ONLY = "--check" in sys.argv


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
    res = find_resource(rm, SCOPE_VID, SCOPE_PID)
    H = {"sc": io.ScopeIO(rm, res)}
    try:
        sc = H["sc"]
        g.connect()
        sc.connect(build_tables=False)
        g.output(1, False)
        g.output(2, False)
        tb0 = sc.query(":TIMebase:SCALe?", io.v_float)
        v0 = [sc.query(f":CHANnel{ch}:SCALe?", io.v_float) for ch in (1, 2)]
        g_freq0 = g.query(":CHANnel1:BASE:FREQuency?", io.v_float)
        g_unit0 = g.query(":CHANnel1:AMPLitude:UNIT?", g.V_UNIT)
        g_amp0 = g.query(":CHANnel1:BASE:AMPLitude?", io.v_float)
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

        r = measure(H["sc"], "alignment check")
        history = [round(r["delay_ps"])]
        tries = 0
        while abs(r["delay_ps"]) > 1000 and not CHECK_ONLY and tries < 40:
            tries += 1
            old = H["sc"]
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            n.tb, n.tb_steps, n.vdiv_steps, n.vdiv = old.tb, old.tb_steps, old.vdiv_steps, dict(old.vdiv)
            H["sc"] = n
            n.query("*IDN?", io.v_scope_idn)
            n.inst.write(":RUN")                    # deliberate: the re-roll
            time.sleep(0.8)
            r = measure(n, f"after re-roll {tries}")
            history.append(round(r["delay_ps"]))
        out["history_ps"], out["rerolls"] = history, tries
        ok = abs(r["delay_ps"]) <= 1000
        print(f"\nALIGNMENT: {'OK' if ok else 'NOT ALIGNED'}  CH2-CH1 = {r['delay_ps']:+.0f} ps "
              f"({r['phase_deg']:+.2f} deg at 20 MHz) after {tries} re-rolls; history {history}")
        sc = H["sc"]
        g.safe_off()
        if any(abs(tb0 - s) < 1e-3 * s for s in TB_STEPS):
            sc.set_timebase(tb0, "exact")
        for ch, v in zip((1, 2), v0):
            sc.set_verified(f":CHANnel{ch}:SCALe", io.plain_decimal(v), io.v_float, v)
        sc.free_run()
        g.set_verified(":CHANnel1:BASE:FREQuency", io.GenFmt.num(g_freq0), io.v_float, g_freq0)
        g.set_verified(":CHANnel1:AMPLitude:UNIT", g_unit0, g.V_UNIT, g_unit0)
        g.set_verified(":CHANnel1:BASE:AMPLitude", io.GenFmt.num(g_amp0), io.v_float, g_amp0)
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        g.safe_off()
        try:
            print("generator outputs ON at end?", [g.output(1), g.output(2)])
        except Exception as e:
            print("gen end error", e)
        g.close()
        H["sc"].close()
        rm.close()
        print("saved", save("s0c_realign.json", out))


if __name__ == "__main__":
    main()
