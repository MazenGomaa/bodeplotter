"""Step 6: generator CH1 -> scope CH1 end-to-end test.

Usage: python s06_end_to_end.py [@py|@ivi]

PRECONDITION (confirmed by the user): generator CH1 is connected to scope CH1
with a BNC cable. This is the only script that switches a generator output on.
The output is switched OFF in a finally block, and every changed setting on
both instruments is restored.
"""
import sys
import time
import traceback

import scpi
import wave
from common import (GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource,
                    num, open_inst, open_rm, save)

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "@py"
out = {"backend": BACKEND, "points": [], "log": []}

# (generator Hz, scope s/div). 14 horizontal divisions per UPO p.102-103
# (XORigin = -TimeScale*7), so each gives about 5.6 to 7 cycles on screen.
POINTS = [(1e3, 500e-6), (1e6, 500e-9), (20e6, 20e-9)]


def log(msg):
    print(msg)
    out["log"].append(msg)


class State:
    """Apply settings while remembering the originals, restore in reverse."""

    def __init__(self, inst, name):
        self.inst, self.name, self.stack = inst, name, []

    def apply(self, cmd, value, numeric, settle=0.3, suffix=""):
        orig = self.inst.query(cmd + "?").strip()
        self.stack.append((cmd, orig, numeric, suffix))
        want = num(value) if numeric else str(value)
        self.inst.write(f"{cmd} {want}{suffix}")
        time.sleep(settle)
        back = self.inst.query(cmd + "?").strip()
        ok = (abs(float(back) - float(want)) <= 1e-6 * max(abs(float(want)), 1e-12)
              if numeric else back.upper().startswith(str(value).upper()[:3]))
        log(f"  {self.name} {cmd} {want}: was {orig}, now {back} {'ok' if ok else 'MISMATCH'}")
        return ok

    def restore(self):
        res = []
        for cmd, orig, numeric, suffix in reversed(self.stack):
            # first occurrence in the stack holds the true original
            first = next(e[1] for e in self.stack if e[0] == cmd)
            want = num(first) if numeric else first
            try:
                self.inst.write(f"{cmd} {want}{suffix}")
                time.sleep(0.3)
                back = self.inst.query(cmd + "?").strip()
                ok = (abs(float(back) - float(want)) <= 1e-6 * max(abs(float(want)), 1e-12)
                      if numeric else back.upper() == first.upper())
                res.append(dict(cmd=cmd, original=first, after=back, ok=ok))
                log(f"  restore {self.name} {cmd} -> {back} {'ok' if ok else 'MISMATCH'}")
            except Exception as e:
                res.append(dict(cmd=cmd, original=first, error=str(e), ok=False))
                log(f"  restore {self.name} {cmd} FAILED {e}")
        self.stack = []
        return res


def summarize(w, f_hz):
    fit = wave.sine_fit(w["volts"], w["dt"], f_hint=f_hz)
    c = w["codes"]
    return dict(n_points=len(c), dt_s=w["dt"], t0_s=w["t0"], preamble=w["preamble"],
                code_min=min(c), code_max=max(c),
                clipped=(min(c) <= 0 or max(c) >= 255),
                mean_v=sum(w["volts"]) / len(c), tail=w["tail"], fit=fit)


def main():
    rm = open_rm(BACKEND)
    scope = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
    gen = open_inst(rm, find_resource(rm, GEN_VID, GEN_PID))
    out["scope_idn"] = scope.query(scpi.IDN).strip()
    out["gen_idn"] = gen.query(scpi.IDN).strip()
    ss, gs = State(scope, "scope"), State(gen, "gen")
    out1 = scpi.G_OUT.format(n=1)
    try:
        log("generator setup (output still OFF)")
        gen.write(out1 + " OFF")                                  # UTG p.9
        gs.apply(scpi.G_WAVE.format(n=1), "SINe", False)          # UTG p.11-12
        gs.apply(scpi.G_LOAD.format(n=1), 10000, True)            # UTG p.11, 10000 = High-Z
        gs.apply(scpi.G_AMP_UNIT.format(n=1), "VPP", False)       # UTG p.11
        gs.apply(scpi.G_FREQ.format(n=1), 1000, True)             # UTG p.12
        gs.apply(scpi.G_AMP.format(n=1), 1.0, True)               # UTG p.13
        gs.apply(scpi.G_OFFS.format(n=1), 0, True)                # UTG p.13

        log("scope setup")
        ss.apply(scpi.S_CH_DISP.format(n=1), 1, True)             # UPO p.18
        ss.apply(scpi.S_CH_COUP.format(n=1), "DC", False)         # UPO p.18
        # "X" suffix is mandatory: a bare number is misread (dbg_probe.py:
        # "PROBe 1" -> 10X, "PROBe 10" -> 100X). Manual example: ":CHAN1:PROB 10X".
        ss.apply(scpi.S_CH_PROBE.format(n=1), 1, True, suffix="X")  # UPO p.19-20
        ss.apply(scpi.S_CH_BWL.format(n=1), "FULL", False)        # UPO p.17-18
        ss.apply(scpi.S_CH_SCAL.format(n=1), 0.2, True)           # UPO p.20-21
        ss.apply(scpi.S_CH_OFFS.format(n=1), 0, True)             # UPO p.20
        ss.apply(scpi.S_ACQ_TYPE, "NORMal", False)                # UPO p.92
        ss.apply(scpi.S_TB_OFFS, 0, True)                         # UPO p.22-23
        ss.apply(scpi.S_TB_SCAL, POINTS[0][1], True)              # UPO p.23-24
        ss.apply(scpi.S_TRIG_MODE, "EDGE", False)                 # UPO p.52
        ss.apply(scpi.S_TRIG_SRC, "CHANnel1", False)              # UPO p.54-55
        ss.apply(scpi.S_TRIG_SLOPE, "POSitive", False)            # UPO p.55-56
        ss.apply(scpi.S_TRIG_LEV, 0, True)                        # UPO p.53-54
        ss.apply(scpi.S_TRIG_SWEEP, "AUTO", False)                # UPO p.52-53
        scope.write(scpi.S_RUN)                                   # UPO p.8
        wave.setup_readout(scope, 1)
        out["wav_points_q"] = scope.query(scpi.S_WAV_POINTS_Q).strip()   # UPO p.100
        out["wav_start_stop_q"] = [scope.query(scpi.S_WAV_START_Q).strip(),
                                   scope.query(scpi.S_WAV_STOP_Q).strip()]  # UPO p.99

        log("generator CH1 output ON")
        gen.write(out1 + " ON")                                   # UTG p.9
        time.sleep(0.5)
        out["gen_output_on_readback"] = gen.query(out1 + "?").strip()

        for f_hz, tb in POINTS:
            log(f"--- {f_hz:g} Hz, {tb:g} s/div")
            p = {"freq_set_hz": f_hz, "timebase_set": tb}
            gen.write(f"{scpi.G_FREQ.format(n=1)} {num(f_hz)}")   # UTG p.12
            wave.swrite(scope, f"{scpi.S_TB_SCAL} {num(tb)}")     # UPO p.23-24
            time.sleep(1.5)
            p["gen_freq_readback"] = gen.query(scpi.G_FREQ.format(n=1) + "?").strip()
            p["gen_amp_readback"] = gen.query(scpi.G_AMP.format(n=1) + "?").strip()
            p["gen_output_readback"] = gen.query(out1 + "?").strip()
            p["timebase_readback"] = scope.query(scpi.S_TB_SCAL + "?").strip()
            p["scope_meas_vpp"] = scope.query(scpi.S_MEAS_VPP_Q.format(n=1)).strip()    # UPO p.44
            p["scope_meas_freq"] = scope.query(scpi.S_MEAS_FREQ_Q.format(n=1)).strip()  # UPO p.48
            p["xinc_q"] = scope.query(scpi.S_WAV_XINC_Q).strip()  # UPO p.102
            p["yinc_q"] = scope.query(scpi.S_WAV_YINC_Q).strip()  # UPO p.103
            p["yor_q"] = scope.query(scpi.S_WAV_YOR_Q).strip()    # UPO p.104
            p["yref_q"] = scope.query(scpi.S_WAV_YREF_Q).strip()  # UPO p.104
            try:
                t0 = time.perf_counter()
                w = wave.acquire_stop(scope)
                p["stop_fetch_s"] = time.perf_counter() - t0
                p["stop"] = summarize(w, f_hz)
                p["stop"]["attempts"] = w["attempts"]
                if f_hz == 1e3:
                    out["sample_codes_1khz_first40"] = w["codes"][:40]
                fit = p["stop"]["fit"]
                log(f"  STOP fetch: {p['stop']['n_points']} pts dt={w['dt']:g}s "
                    f"fit f={fit['freq_hz']:.6g} Hz vpp={fit['vpp']:.4f} V "
                    f"offs={fit['offset_v']:.4f} V snr={fit['snr_db']:.1f} dB "
                    f"codes {p['stop']['code_min']}..{p['stop']['code_max']}")
                log(f"  scope MEAS: vpp={p['scope_meas_vpp']} freq={p['scope_meas_freq']}")
            except Exception:
                p["stop_error"] = traceback.format_exc()
                log(p["stop_error"])
            try:
                time.sleep(0.5)
                w = wave.acquire_single(scope)
                p["single"] = summarize(w, f_hz)
                p["single"]["states"] = w["single_states"]
                p["single"]["wait_s"] = w["single_wait_s"]
                fit = p["single"]["fit"]
                log(f"  SINGLE: states {w['single_states']} in {w['single_wait_s']:.3f}s "
                    f"fit f={fit['freq_hz']:.6g} Hz vpp={fit['vpp']:.4f} V")
            except Exception:
                p["single_error"] = traceback.format_exc()
                log(p["single_error"])
            finally:
                scope.write(f"{scpi.S_TRIG_SWEEP} AUTO")          # UPO p.52-53
                scope.write(scpi.S_RUN)                           # UPO p.8
            out["points"].append(p)

        # Sign convention of Yor: with a known 0 V-mean signal and a +0.2 V
        # channel offset, the correct formula must still decode a ~0 V mean.
        log("--- Yor sign check at 1 kHz with CH1 offset +0.2 V")
        gen.write(f"{scpi.G_FREQ.format(n=1)} 1000")
        wave.swrite(scope, f"{scpi.S_TB_SCAL} {num(500e-6)}")
        wave.swrite(scope, f"{scpi.S_CH_OFFS.format(n=1)} 0.2")   # UPO p.20
        time.sleep(1.5)
        w = wave.acquire_stop(scope)
        c = w["codes"]
        mean_code = sum(c) / len(c)
        out["yor_check"] = dict(
            offset_readback=scope.query(scpi.S_CH_OFFS.format(n=1) + "?").strip(),
            preamble=w["preamble"], mean_code=mean_code,
            mean_v_minus_yor=(mean_code - w["yref"] - w["yor"]) * w["yinc"],
            mean_v_plus_yor=(mean_code - w["yref"] + w["yor"]) * w["yinc"],
            mean_v_no_yor=(mean_code - w["yref"]) * w["yinc"])
        log(f"  {out['yor_check']}")
        wave.swrite(scope, f"{scpi.S_CH_OFFS.format(n=1)} 0")
    except Exception:
        out["error"] = traceback.format_exc()
        log(out["error"])
    finally:
        # Output OFF first, whatever happened.
        for ch in (1, 2):
            try:
                gen.write(scpi.G_OUT.format(n=ch) + " OFF")       # UTG p.9
            except Exception as e:
                log(f"OUTPUT OFF write failed ch{ch}: {e}")
        time.sleep(0.3)
        try:
            out["gen_output_final"] = [gen.query(scpi.G_OUT.format(n=ch) + "?").strip()
                                       for ch in (1, 2)]
            log(f"generator outputs final: {out['gen_output_final']}")
        except Exception as e:
            out["gen_output_final_error"] = str(e)
        out["gen_restore"] = gs.restore()
        try:
            scope.write(f"{scpi.S_TRIG_SWEEP} AUTO")
            scope.write(scpi.S_RUN)
        except Exception:
            pass
        out["scope_restore"] = ss.restore()
        try:
            out["scope_err_final"] = scope.query(scpi.S_ERR_Q).strip()   # UPO p.9
        except Exception as e:
            out["scope_err_final"] = str(e)
        scope.close()
        gen.close()
        rm.close()
        print("saved", save(f"s06_end_to_end_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
