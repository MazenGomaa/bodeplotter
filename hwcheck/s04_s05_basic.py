"""Steps 4 and 5: identity, basic SCPI query / set / read back / restore.

Usage: python s04_s05_basic.py [@py|@ivi]

Non-destructive: every changed setting is restored. Generator outputs are
never switched on here.
"""
import sys
import time
import traceback

import scpi
from common import (GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource,
                    num, open_inst, open_rm, save)

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "@py"
rows = []          # one row per command exercised
info = {"backend": BACKEND}


def rec(inst_name, cmd, ref, action, ok, sent=None, resp=None, err=None, dt=None):
    rows.append(dict(instrument=inst_name, command=cmd, ref=ref, action=action,
                     ok=bool(ok), sent=sent, response=resp, error=err,
                     seconds=None if dt is None else round(dt, 4)))
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {inst_name:5s} {action:8s} {sent or cmd!s:42s} -> {resp!r} {err or ''}")


def q(inst, name, cmd, ref, action="query"):
    """Query and record. Returns the stripped response or None."""
    t0 = time.perf_counter()
    try:
        r = inst.query(cmd).strip()
        rec(name, cmd, ref, action, r != "", cmd, r, dt=time.perf_counter() - t0)
        return r
    except Exception as e:
        rec(name, cmd, ref, action, False, cmd, err=f"{type(e).__name__}: {e}",
            dt=time.perf_counter() - t0)
        return None


def same(a, b, numeric):
    if a is None or b is None:
        return False
    if numeric:
        try:
            fa, fb = float(a), float(b)
        except ValueError:
            return False
        return abs(fa - fb) <= 1e-6 * max(abs(fa), abs(fb), 1e-12)
    a, b = a.upper(), b.upper()
    return a == b or a.startswith(b) or b.startswith(a)


def set_readback_restore(inst, name, cmd, ref, new_value, numeric, settle=0.3):
    """Query original, set new_value, read back, restore original, verify."""
    orig = q(inst, name, cmd + "?", ref)
    if orig is None:
        return None
    if numeric:
        # plain decimals only, see common.num()
        new_value, orig = num(new_value), num(orig)
    try:
        inst.write(f"{cmd} {new_value}")
        time.sleep(settle)
        back = inst.query(cmd + "?").strip()
        rec(name, cmd, ref, "set", same(back, str(new_value), numeric),
            f"{cmd} {new_value}", back)
    except Exception as e:
        rec(name, cmd, ref, "set", False, f"{cmd} {new_value}",
            err=f"{type(e).__name__}: {e}")
    finally:
        try:
            inst.write(f"{cmd} {orig}")
            time.sleep(settle)
            back = inst.query(cmd + "?").strip()
            rec(name, cmd, ref, "restore", same(back, orig, numeric),
                f"{cmd} {orig}", back)
        except Exception as e:
            rec(name, cmd, ref, "restore", False, f"{cmd} {orig}",
                err=f"{type(e).__name__}: {e}")
    return orig


def termination_probe(inst, name):
    """Read *IDN? raw to see exactly which terminator bytes the instrument sends."""
    old = inst.read_termination
    try:
        inst.read_termination = None
        inst.write(scpi.IDN)
        raw = inst.read_raw()
        info[f"{name}_idn_raw_tail"] = repr(raw[-4:])
        info[f"{name}_idn_raw_len"] = len(raw)
        print(name, "raw *IDN? tail bytes:", repr(raw[-4:]))
    except Exception as e:
        info[f"{name}_idn_raw_error"] = f"{type(e).__name__}: {e}"
    finally:
        inst.read_termination = old


def pick(orig, a, b):
    """Return a, unless the instrument is already at a, then b."""
    try:
        return b if abs(float(orig) - float(a)) < 1e-9 * max(1.0, abs(float(a))) else a
    except (TypeError, ValueError):
        return a


def scope_tests(inst):
    n = "scope"
    info["scope_idn"] = q(inst, n, scpi.IDN, "UPO p.7")
    termination_probe(inst, n)
    q(inst, n, scpi.OPC_Q, "UPO p.7")
    q(inst, n, scpi.S_VERS_Q, "UPO p.13")
    q(inst, n, scpi.S_ERR_Q, "UPO p.9")
    q(inst, n, scpi.S_TRIG_STAT_Q, "UPO p.53")
    q(inst, n, scpi.S_TRIG_MODE + "?", "UPO p.52")
    q(inst, n, scpi.S_TRIG_SWEEP + "?", "UPO p.52-53")
    q(inst, n, scpi.S_TRIG_SRC + "?", "UPO p.54-55")
    q(inst, n, scpi.S_TRIG_LEV + "?", "UPO p.53-54")
    q(inst, n, scpi.S_TRIG_SLOPE + "?", "UPO p.55-56")
    q(inst, n, scpi.S_TB_MODE_Q, "UPO p.22")
    q(inst, n, scpi.S_TB_OFFS + "?", "UPO p.22-23")
    q(inst, n, scpi.S_ACQ_TYPE + "?", "UPO p.92")
    q(inst, n, scpi.S_ACQ_DEPTH_Q, "UPO p.93")
    for ch in (1, 2):
        q(inst, n, scpi.S_CH_DISP.format(n=ch) + "?", "UPO p.18")
        q(inst, n, scpi.S_CH_PROBE.format(n=ch) + "?", "UPO p.19-20")
        q(inst, n, scpi.S_CH_OFFS.format(n=ch) + "?", "UPO p.20")
        q(inst, n, scpi.S_CH_BWL.format(n=ch) + "?", "UPO p.17-18")
        q(inst, n, scpi.S_CH_VERN.format(n=ch) + "?", "UPO p.21")
        q(inst, n, scpi.S_CH_SCAL.format(n=ch) + "?", "UPO p.20-21")
        q(inst, n, scpi.S_CH_COUP.format(n=ch) + "?", "UPO p.18")

    # set / read back / restore
    tb = inst.query(scpi.S_TB_SCAL + "?").strip()
    set_readback_restore(inst, n, scpi.S_TB_SCAL, "UPO p.23-24", pick(tb, 1e-3, 2e-3), True)
    cmd = scpi.S_CH_SCAL.format(n=1)
    vd = inst.query(cmd + "?").strip()
    set_readback_restore(inst, n, cmd, "UPO p.20-21", pick(vd, 1.0, 2.0), True)
    cmd = scpi.S_CH_COUP.format(n=1)
    cp = inst.query(cmd + "?").strip()
    set_readback_restore(inst, n, cmd, "UPO p.18",
                         "AC" if cp.upper().startswith("DC") else "DC", False)
    q(inst, n, scpi.OPC_Q, "UPO p.7", action="query2")
    q(inst, n, scpi.S_ERR_Q, "UPO p.9", action="query2")


def gen_tests(inst):
    n = "gen"
    info["gen_idn"] = q(inst, n, scpi.IDN, "UTG p.5")
    termination_probe(inst, n)
    # Safety first: outputs must be OFF. Record what we found.
    for ch in (1, 2):
        cmd = scpi.G_OUT.format(n=ch)
        st = q(inst, n, cmd + "?", "UTG p.9")
        info[f"gen_ch{ch}_output_found"] = st
        if st is not None and st.strip() not in ("0", "OFF"):
            inst.write(cmd + " OFF")
            time.sleep(0.3)
            q(inst, n, cmd + "?", "UTG p.9", action="forceoff")
    # *OPC? is NOT in the UTG manual. It was probed in runs 1 and 2 of this
    # script (results/s04_s05_basic_py_run1.json, _run2.json): it times out, and
    # in run 2 it left the generator deaf to every later command until a USBTMC
    # INITIATE_CLEAR was sent (dbg_gen_recover.py). So it is only probed on
    # request now.
    if "--probe-gen-opc" in sys.argv:
        old = inst.timeout
        inst.timeout = 1500
        r = q(inst, n, scpi.OPC_Q, "not in UTG manual (UPO p.7 form)")
        inst.timeout = old
        if r is None:
            time.sleep(0.5)
            q(inst, n, scpi.IDN, "UTG p.5", action="recover")

    q(inst, n, scpi.G_LOCK_Q, "UTG p.5")
    for ch in (1, 2):
        q(inst, n, scpi.G_MODE.format(n=ch) + "?", "UTG p.15-16")
        q(inst, n, scpi.G_WAVE.format(n=ch) + "?", "UTG p.11-12")
        q(inst, n, scpi.G_AMP_UNIT.format(n=ch) + "?", "UTG p.11")
        q(inst, n, scpi.G_OFFS.format(n=ch) + "?", "UTG p.13")
        q(inst, n, scpi.G_PHASE.format(n=ch) + "?", "UTG p.12-13")
        q(inst, n, scpi.G_FREQ.format(n=ch) + "?", "UTG p.12")
        q(inst, n, scpi.G_AMP.format(n=ch) + "?", "UTG p.13")
        q(inst, n, scpi.G_LOAD.format(n=ch) + "?", "UTG p.11")

    cmd = scpi.G_FREQ.format(n=1)
    f0 = inst.query(cmd + "?").strip()
    set_readback_restore(inst, n, cmd, "UTG p.12", pick(f0, 1234, 2345), True)
    cmd = scpi.G_AMP.format(n=1)
    a0 = inst.query(cmd + "?").strip()
    set_readback_restore(inst, n, cmd, "UTG p.13", pick(a0, 0.5, 0.25), True)
    # Load last: changing load can rescale the displayed amplitude, so re-check
    # amplitude afterwards.
    cmd = scpi.G_LOAD.format(n=1)
    l0 = inst.query(cmd + "?").strip()
    set_readback_restore(inst, n, cmd, "UTG p.11", pick(l0, 50, 10000), True)
    a1 = q(inst, n, scpi.G_AMP.format(n=1) + "?", "UTG p.13", action="recheck")
    info["gen_amp_before_after_load_toggle"] = [a0, a1]
    if a1 is not None and not same(a0, a1, True):
        inst.write(f"{scpi.G_AMP.format(n=1)} {num(a0)}")
        time.sleep(0.3)
        q(inst, n, scpi.G_AMP.format(n=1) + "?", "UTG p.13", action="restore")
    for ch in (1, 2):
        q(inst, n, scpi.G_OUT.format(n=ch) + "?", "UTG p.9", action="final")


def main():
    rm = open_rm(BACKEND)
    info["visalib"] = str(rm.visalib)
    info["resources"] = list(rm.list_resources("?*"))
    print("resources:", info["resources"])
    for name, vid, pid, fn in (("scope", SCOPE_VID, SCOPE_PID, scope_tests),
                               ("gen", GEN_VID, GEN_PID, gen_tests)):
        res = find_resource(rm, vid, pid)
        info[f"{name}_resource"] = res
        if res is None:
            print(f"{name}: no resource for {vid:04x}:{pid:04x}")
            info[f"{name}_error"] = "resource not found"
            continue
        inst = None
        try:
            inst = open_inst(rm, res)
            fn(inst)
        except Exception:
            info[f"{name}_error"] = traceback.format_exc()
            print(info[f"{name}_error"])
        finally:
            if inst is not None:
                if name == "gen":
                    for ch in (1, 2):
                        try:
                            inst.write(scpi.G_OUT.format(n=ch) + " OFF")  # UTG p.9
                        except Exception:
                            pass
                inst.close()
    rm.close()
    tag = BACKEND.strip("@")
    print("saved", save(f"s04_s05_basic_{tag}.json", {"info": info, "rows": rows}))
    fails = [r for r in rows if not r["ok"]]
    print(f"{len(rows) - len(fails)}/{len(rows)} passed")


if __name__ == "__main__":
    main()
