"""Steps 7 and 8a: timing and 200-cycle robustness. Generator outputs stay OFF.

Usage: python s07_s08_timing_robust.py [@py|@ivi] [cycles]
"""
import statistics
import sys
import time
import traceback

import scpi
import wave
from common import (GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource,
                    open_inst, open_rm, save)

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "@py"
CYCLES = int(sys.argv[2]) if len(sys.argv) > 2 else 200
out = {"backend": BACKEND, "cycles_requested": CYCLES}


def stats(xs):
    return dict(n=len(xs), mean_ms=1e3 * statistics.mean(xs), min_ms=1e3 * min(xs),
                max_ms=1e3 * max(xs),
                stdev_ms=1e3 * statistics.stdev(xs) if len(xs) > 1 else 0.0)


def main():
    rm = open_rm(BACKEND)
    scope = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
    gen = open_inst(rm, find_resource(rm, GEN_VID, GEN_PID))
    saved = {}
    try:
        out["gen_outputs_start"] = [gen.query(scpi.G_OUT.format(n=c) + "?").strip() for c in (1, 2)]
        for cmd in (scpi.S_WAV_SRC, scpi.S_WAV_MODE, scpi.S_WAV_FMT):
            saved[cmd] = scope.query(cmd + "?").strip()
        out["timebase"] = scope.query(scpi.S_TB_SCAL + "?").strip()
        wave.setup_readout(scope, 1)
        guard = wave.guard_time(float(out["timebase"]))
        out["guard_s"] = guard
        scope.write(scpi.S_RUN)
        time.sleep(guard)

        # ---- step 7: *IDN? round trip, 20 runs each
        for name, inst in (("scope", scope), ("gen", gen)):
            ts = []
            for _ in range(20):
                t0 = time.perf_counter()
                inst.query(scpi.IDN)                 # UPO p.7 / UTG p.5
                ts.append(time.perf_counter() - t0)
            out[f"idn_{name}"] = stats(ts)
            print(f"IDN {name}: {out[f'idn_{name}']}")

        # ---- step 7: waveform fetch + decode, 10 runs
        total, fetch_only, pts = [], [], []
        for _ in range(10):
            time.sleep(guard)                        # not timed, see wave.guard_time
            t0 = time.perf_counter()
            w = wave.acquire_stop(scope)             # STOP, wait, preamble, data, decode, RUN
            total.append(time.perf_counter() - t0)
            pts.append(len(w["codes"]))
        # fetch without the STOP/RUN bracket (screen data while running)
        time.sleep(guard)
        for _ in range(10):
            t0 = time.perf_counter()
            w = wave.fetch(scope)
            fetch_only.append(time.perf_counter() - t0)
        out["wave_stop_fetch_decode_run"] = stats(total)
        out["wave_fetch_decode_running"] = stats(fetch_only)
        out["wave_points"] = sorted(set(pts))
        print("waveform STOP+fetch+decode+RUN:", out["wave_stop_fetch_decode_run"])
        print("waveform fetch+decode (running):", out["wave_fetch_decode_running"])

        # ---- step 8a: consecutive query/acquire cycles
        errors, retries, cyc, resyncs = [], 0, [], []
        t_start = time.perf_counter()
        for i in range(CYCLES):
            t0 = time.perf_counter()
            try:
                a = gen.query(scpi.IDN).strip()
                b = gen.query(scpi.G_FREQ.format(n=1) + "?").strip()   # UTG p.12
                c = scope.query(scpi.IDN).strip()
                d = scope.query(scpi.S_TB_SCAL + "?").strip()          # UPO p.23-24
                w = wave.acquire_stop(scope, guard)
                if w["attempts"] > 1:
                    retries += w["attempts"] - 1
                if "UTG" not in a or "UPO" not in c or len(w["codes"]) == 0:
                    raise ValueError(f"bad data: {a!r} {c!r} n={len(w['codes'])}")
                float(b), float(d)
            except Exception as e:
                errors.append(dict(cycle=i, error=f"{type(e).__name__}: {e}",
                                   trace=traceback.format_exc()))
                print(f"cycle {i} ERROR {type(e).__name__}: {e}")
                try:
                    resyncs.append(dict(cycle=i, queries_needed=wave.resync(scope)))
                except Exception as e2:
                    resyncs.append(dict(cycle=i, failed=str(e2)))
                    print(f"cycle {i} RESYNC FAILED {e2}")
                    break
            cyc.append(time.perf_counter() - t0)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{CYCLES} cycles, errors={len(errors)}, block retries={retries}")
        out["robust"] = dict(cycles=CYCLES, errors=len(errors), error_detail=errors[:20],
                             empty_block_retries=retries, resyncs=resyncs,
                             guard_s_included_in_cycle=guard, cycle=stats(cyc),
                             total_s=time.perf_counter() - t_start)
        print("robustness:", {k: v for k, v in out["robust"].items() if k != "error_detail"})
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        try:
            for c in (1, 2):
                gen.write(scpi.G_OUT.format(n=c) + " OFF")      # UTG p.9
            out["gen_outputs_end"] = [gen.query(scpi.G_OUT.format(n=c) + "?").strip() for c in (1, 2)]
        except Exception as e:
            out["gen_off_error"] = str(e)
        try:
            scope.write(scpi.S_RUN)
            for cmd, val in saved.items():
                wave.swrite(scope, f"{cmd} {val}")
            out["scope_readout_restored"] = {c: scope.query(c + "?").strip() for c in saved}
            out["scope_readout_original"] = saved
            out["scope_err_final"] = scope.query(scpi.S_ERR_Q).strip()
        except Exception as e:
            out["scope_restore_error"] = str(e)
        scope.close()
        gen.close()
        rm.close()
        print("saved", save(f"s07_s08_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
