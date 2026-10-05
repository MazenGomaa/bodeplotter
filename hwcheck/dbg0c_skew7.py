"""Milestone 0c investigation, part 7: is there a command that puts a
misaligned scope back to the aligned state every time?

Established in part 6 (25 repetitions each, 20 MHz, both 10X probes on
generator CH1):
  ':RUN' after a USB session has been reopened   -> offset slips in about half
                                                    the cases, by 2, 4, 6 or 8 ns
  ':RUN' in a session that stays open            -> 0 slips
  reopen + ':TRIGger:SWEep AUTO' (no ':RUN')     -> 0 slips, scope runs again
  device clear, *IDN?, WAVeform writes, reopen   -> 0 slips

Here the slip recipe (reopen, ':RUN') is used on purpose to get a misaligned
state, then ONE candidate is applied and the offset measured. A real fix must
return to the aligned value (about +150 ps) every time.
Candidates (all documented, all put back): memory depth change (U1K p.65),
acquire type change (p.65), timebase mode WINDow/MAIN (p.15-16), all channels
off then on with a long gap (p.13), ':STOP' then sweep AUTO.
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
import time
import traceback

import iolayer as io
import dbg0c_skew
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from dbg0c_skew import F, TB_STEPS, VD_STEPS, measure, out

dbg0c_skew.N = 2
ALIGNED = 150.0


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
    res = find_resource(rm, SCOPE_VID, SCOPE_PID)
    H = {"sc": io.ScopeIO(rm, res)}
    raw = lambda r: r
    try:
        sc = H["sc"]
        g.connect()
        sc.idn = sc.query("*IDN?", io.v_scope_idn)
        g.output(1, False)
        g.output(2, False)
        tb0 = sc.query(":TIMebase:SCALe?", io.v_float)
        v0 = [sc.query(f":CHANnel{ch}:SCALe?", io.v_float) for ch in (1, 2)]
        depth0 = sc.query(":ACQuire:MEMory:DEPTh?", raw)
        type0 = sc.query(":ACQuire:TYPE?", raw)
        g_freq0 = g.query(":CHANnel1:BASE:FREQuency?", io.v_float)
        g_unit0 = g.query(":CHANnel1:AMPLitude:UNIT?", g.V_UNIT)
        g_amp0 = g.query(":CHANnel1:BASE:AMPLitude?", io.v_float)
        print("found: depth", depth0, "type", type0, "tb", tb0)
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

        def slip_once():
            old = S()
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            n.tb, n.tb_steps, n.vdiv_steps, n.vdiv = old.tb, old.tb_steps, old.vdiv_steps, dict(old.vdiv)
            H["sc"] = n
            n.query("*IDN?", io.v_scope_idn)
            n.inst.write(":RUN")
            time.sleep(0.8)

        def make_misaligned():
            for _ in range(12):
                r = measure(S(), "   (state)")
                if abs(r["delay_ps"] - ALIGNED) > 1000:
                    return r
                slip_once()
            return None

        def sv(cmd, a, b_, wait=1.0):
            s = S()
            s.write(f"{cmd} {a}")
            time.sleep(wait)
            got = s.query(cmd + "?", raw)
            s.write(f"{cmd} {b_}")
            time.sleep(wait)
            return got, s.query(cmd + "?", raw)

        def all_off_on():
            s = S()
            s.set_verified(":CHANnel2:DISPlay", "0", io.v_bool, False); time.sleep(1.0)
            s.set_verified(":CHANnel1:DISPlay", "0", io.v_bool, False); time.sleep(3.0)
            s.set_verified(":CHANnel1:DISPlay", "1", io.v_bool, True); time.sleep(1.0)
            s.set_verified(":CHANnel2:DISPlay", "1", io.v_bool, True); time.sleep(1.5)

        def stop_auto():
            s = S()
            s.write(":STOP"); time.sleep(1.0)
            s.set_verified(":TRIGger:SWEep", "AUTO", io.V_SWEEP, "AUTO"); time.sleep(1.0)

        other_depth = "70K" if depth0.upper() != "70K" else "7K"
        cands = [("memory depth -> %s -> %s" % (other_depth, depth0),
                  lambda: sv(":ACQuire:MEMory:DEPTh", other_depth, depth0)),
                 ("memory depth -> AUTO -> %s" % depth0, lambda: sv(":ACQuire:MEMory:DEPTh", "AUTO", depth0)),
                 ("acquire type -> PEAKdetect -> NORMal", lambda: sv(":ACQuire:TYPE", "PEAKdetect", "NORMal")),
                 ("timebase mode -> WINDow -> MAIN", lambda: sv(":TIMebase:MODE", "WINDow", "MAIN")),
                 ("both channels off 3 s, then on", all_off_on),
                 (":STOP, then sweep AUTO (no :RUN)", stop_auto)]
        tally = {}
        for rnd in (1, 2, 3):
            for name, fn in cands:
                try:
                    before = make_misaligned()
                    if before is None:
                        print("could not reach a misaligned state in 12 tries")
                        continue
                    info = fn()
                    time.sleep(0.8)
                    r = measure(S(), f"r{rnd} {name}")
                    fixed = abs(r["delay_ps"] - ALIGNED) < 700
                    tally.setdefault(name, []).append(
                        f"{before['delay_ps']:+.0f} -> {r['delay_ps']:+.0f}" + (" ALIGNED" if fixed else ""))
                    if info:
                        r["readbacks"] = info
                except Exception as e:
                    print(f"{name}: ERROR {type(e).__name__}: {str(e)[:300]}")
                    tally.setdefault(name, []).append("error")
        out["tally"] = tally
        print("\nBEFORE -> AFTER (ps) PER CANDIDATE")
        for k, v in tally.items():
            print(f"  {k:42s} {v}")
        # put back
        sc = S()
        sc.write(f":ACQuire:MEMory:DEPTh {depth0}")
        sc.write(f":ACQuire:TYPE {type0}")
        sc.write(":TIMebase:MODE MAIN")
        print("put back: depth", sc.query(":ACQuire:MEMory:DEPTh?", raw), "type", sc.query(":ACQuire:TYPE?", raw),
              "tbmode", sc.query(":TIMebase:MODE?", raw))
        g.safe_off()
        if any(abs(tb0 - s) < 1e-3 * s for s in TB_STEPS):
            sc.set_timebase(tb0, "exact")
        for ch, v in zip((1, 2), v0):
            sc.set_verified(f":CHANnel{ch}:SCALe", io.plain_decimal(v), io.v_float, v)
        sc.set_verified(":TRIGger:SWEep", "AUTO", io.V_SWEEP, "AUTO")
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
        print("saved", save("dbg0c_skew7.json", out))


if __name__ == "__main__":
    main()
