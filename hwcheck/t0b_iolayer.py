"""Milestone 0b step 2: tests of iolayer.py on the real instruments.

Usage: python t0b_iolayer.py [@ivi|@py] [--skip-scan]

Generator outputs stay OFF throughout (verified at start and end). Every scope
and generator setting touched here is recorded first and restored at the end.
"""
import json
import random
import sys
import time
import traceback

import pyvisa

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
# Restart command for the fault-injection parts. This used to be ":RUN"; it must not be, because
# ":RUN" after a session reopen shifts the scope's channels (HW_REPORT.md 12.11).
RESTART = ":TRIGger:SWEep AUTO"


def restart(sc):
    """Restart acquisition without ':RUN'. From a :STOP with the sweep already AUTO, writing
    AUTO again is a no-op (first run after the :RUN removal: 7 of 12 forcing rounds could not
    produce an empty block), so go through SINGle first: the change back to AUTO restarts it."""
    sc.inst.write(":TRIGger:SWEep SINGle")
    time.sleep(0.05)
    sc.inst.write(RESTART)
results, logs = [], []
out = {"backend": BACKEND, "results": results, "log": logs}


def log(msg):
    logs.append(msg)
    print("   .", msg)


def rec(name, ok, detail=""):
    results.append(dict(test=name, ok=bool(ok), detail=str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def expect_raises(name, exc, fn):
    try:
        fn()
        rec(name, False, "no exception")
    except exc as e:
        rec(name, True, f"{type(e).__name__}: {str(e)[:110]}")
    except Exception as e:
        rec(name, False, f"wrong exception {type(e).__name__}: {e}")


# ------------------------------------------------------------------ T1 offline
def t1_offline():
    cases = {1e-9: "0.000000001", 2.5e-8: "0.000000025", 2e7: "20000000", 0.2: "0.2",
             0.0005: "0.0005", 5.0: "5", 0: "0", -0.2: "-0.2", 1234.5: "1234.5",
             0.1 + 0.2: "0.3", 1e-12: "0.000000000001", 10000: "10000"}
    bad = {k: io.plain_decimal(k) for k, v in cases.items() if io.plain_decimal(k) != v}
    rec("T1 formatter: plain decimals, no exponent", not bad, bad or f"{len(cases)} cases")
    rec("T1 formatter: probe ratio has X suffix", io.ScopeFmt.probe(1) == "1X" and io.ScopeFmt.probe(10) == "10X")
    expect_raises("T1 formatter: rejects NaN", ValueError, lambda: io.plain_decimal(float("nan")))
    expect_raises("T1 formatter: rejects scope channel 5", ValueError, lambda: io.ScopeFmt.channel(5))
    expect_raises("T1 formatter: rejects generator channel 3", ValueError, lambda: io.GenFmt.channel(3))
    good = [(io.v_float, "5.000000e-03"), (io.v_bool, "1"), (io.v_opc, "1"), (io.v_err, '0,"No error"'),
            (io.V_WAVFMT, "BYTE"), (io.V_WAVFMT, "BYT"), (io.V_STATUS, "TRIGED"), (io.V_COUPLING, "DC"),
            (io.v_scope_idn, "UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047"),
            (io.v_gen_idn, "UNI-T Technologies,UTG900E,69746177,1.09"),
            (io.v_preamble, "0,0,1000,1,1.000000e-05 ,-3.500000e-03,0,8.000000e-03 ,2.500000e+01 ,128")]
    fails = []
    for v, s in good:
        try:
            v(s)
        except io.ReplyError as e:
            fails.append(str(e))
    rec("T1 validators: accept real replies", not fails, fails or f"{len(good)} replies")
    wrong = [(io.v_float, "AUTO"), (io.v_float, ""), (io.v_bool, "5.0e-3"), (io.v_opc, "0"),
             (io.v_err, "1"), (io.V_STATUS, "1.000000e+00"), (io.V_COUPLING, "CHANnel1"),
             (io.v_scope_idn, '0,"No error"'), (io.v_scope_idn, "UNI-T Technologies,UTG900E,1,1"),
             (io.v_preamble, "1"), (io.v_float, "UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047")]
    passed_through = []
    for v, s in wrong:
        try:
            v(s)
            passed_through.append(s)
        except io.ReplyError:
            pass
    rec("T1 validators: reject wrong-format replies", not passed_through,
        passed_through or f"{len(wrong)} replies")


# ------------------------------------------------------------------ helpers
class Saver:
    """Remember originals, restore in reverse order with set_verified."""

    def __init__(self, dev):
        self.dev, self.items = dev, []

    def save(self, cmd, validate, fmt=lambda v: v):
        v = self.dev.query(cmd + "?", validate)
        self.items.append((cmd, validate, v, fmt))
        return v

    def restore(self):
        bad = []
        saved = {c: v for c, _, v, _ in self.items}
        for cmd, validate, v, fmt in reversed(self.items):
            try:
                arg = fmt(v)
                if cmd.endswith(":SCALe") and cmd.startswith(":CHANnel"):
                    # M0 finding S2: the SCALe argument is input-referred but the
                    # read-back is probe-scaled, so divide by the saved probe ratio
                    arg = fmt(v / saved[cmd.replace(":SCALe", ":PROBe")])
                if cmd.endswith(":OFFSet") or cmd.endswith(":LEVel"):
                    self.dev.set_verified(cmd, arg, validate, v, tol_abs=1.0)
                    continue
                self.dev.set_verified(cmd, arg, validate, v)
            except Exception as e:
                bad.append(f"{cmd}: {e}")
        return bad


def b01(v):
    return "1" if v else "0"


# ------------------------------------------------------------------ scope tests
def scope_tests(sc):
    sv = Saver(sc)
    num, probe = io.ScopeFmt.num, io.ScopeFmt.probe
    for ch in (1, 2):
        c = f":CHANnel{ch}"
        sv.save(c + ":SCALe", io.v_float, num)      # restored after probe/vernier (reverse order)
        sv.save(c + ":OFFSet", io.v_float, num)
        sv.save(c + ":BWLimit", io.V_BWL)
        sv.save(c + ":COUPling", io.V_COUPLING)
        sv.save(c + ":VERNier", io.v_bool, b01)
        sv.save(c + ":PROBe", io.v_float, probe)
        sv.save(c + ":DISPlay", io.v_bool, b01)
    sv.save(":TIMebase:SCALe", io.v_float, num)
    sv.save(":TRIGger:LEVel", io.v_float, num)
    sv.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
    sv.save(":TRIGger:SOURce", io.V_TRIGSRC)
    sv.save(":TRIGger:MODE", io.V_TRIGMODE)
    sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)
    out["scope_originals"] = [(c, v) for c, _, v, _ in sv.items] + [(":TRIGger:SWEep", sweep0)]
    try:
        # NOTE: with probe 10X the scale read-back is probe-scaled, so originals
        # of a 10X channel are restored after the probe ratio is back (reverse order).
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        rec("T2 scope: channels 1+2 and edge trigger configured with read-back", True)

        tb, vd = sc.build_tables(1)
        out["tb_steps"], out["vdiv_steps"] = tb, vd
        rec("T2 scope: timebase step table built", len(tb) >= 10, [f"{x:g}" for x in tb])
        rec("T2 scope: V/div step table built", len(vd) >= 10, [f"{x:g}" for x in vd])

        # T3 every step: set + read back
        bad = []
        for s in tb:
            try:
                sc.set_timebase(s, "exact")
            except io.SetError as e:
                bad.append(str(e))
        rec(f"T3 scope: all {len(tb)} timebase steps set and read back", not bad, bad)
        for ch in (1, 2):
            bad = []
            for s in vd:
                try:
                    sc.set_vdiv(ch, s, "exact")
                except io.SetError as e:
                    bad.append(str(e))
            rec(f"T3 scope: all {len(vd)} V/div steps set and read back on CH{ch}", not bad, bad)
        expect_raises("T3 scope: 20 ns/div refused, not a real step", io.SetError,
                      lambda: sc.set_timebase(20e-9, "exact"))
        got = sc.set_timebase(20e-9, "ceil")
        rec("T3 scope: 20 ns/div request rounds up to the next real step", abs(got - 25e-9) < 1e-12, f"{got:g}")
        expect_raises("T3 scope: read-back catches a value the scope did not take", io.SetError,
                      lambda: sc.set_verified(":TIMebase:SCALe", "0.00000002", io.v_float, 2e-8, timeout_s=0.6))
        sc.set_vdiv(1, 0.2, "exact")
        sc.set_vdiv(2, 0.2, "exact")
        bad = []
        for cmd, arg, v, exp in ((":CHANnel1:COUPling", "AC", io.V_COUPLING, "AC"),
                                 (":CHANnel1:COUPling", "DC", io.V_COUPLING, "DC"),
                                 (":CHANnel1:BWLimit", "20M", io.V_BWL, "20M"),
                                 (":CHANnel1:BWLimit", "FULL", io.V_BWL, "FULL"),
                                 (":CHANnel1:OFFSet", "0.2", io.v_float, 0.2),
                                 (":CHANnel1:OFFSet", "0", io.v_float, 0.0),
                                 (":TRIGger:LEVel", "0.1", io.v_float, 0.1),
                                 (":TRIGger:LEVel", "0", io.v_float, 0.0),
                                 (":TRIGger:EDGE:SLOPe", "NEGative", io.V_SLOPE, "NEGative"),
                                 (":TRIGger:EDGE:SLOPe", "POSitive", io.V_SLOPE, "POSitive"),
                                 (":TRIGger:SOURce", "CHANnel2", io.V_TRIGSRC, "CHANnel2"),
                                 (":TRIGger:SOURce", "CHANnel1", io.V_TRIGSRC, "CHANnel1")):
            try:
                # offset and trigger level are quantised to one code (0.2 V/div / 25 = 8 mV)
                sc.set_verified(cmd, arg, v, exp, tol_abs=0.008 if isinstance(exp, float) else 1e-12)
            except Exception as e:
                bad.append(f"{cmd} {arg}: {e}")
        rec("T3 scope: coupling, BW limit, offset, trigger level/slope/source set and read back", not bad, bad)

        sc.set_timebase(500e-6, "exact")
        sc.set_vdiv(1, 0.2, "exact")
        sc.set_vdiv(2, 0.2, "exact")

        # T6 acquisition-complete polling (no input signal -> forced trigger path)
        n_ok, waits, states = 0, [], set()
        for i in range(20):
            a = sc.acquire([1, 2], force_after_s=0.6)
            ok = all(len(a["waves"][ch]["codes"]) == 700 for ch in (1, 2)) and a["states"][-1] == "STOP"
            n_ok += ok
            waits.append(a["wait_s"])
            states.update(a["states"])
        rec("T6 scope: 20 polled single acquisitions, both channels, 700 points each", n_ok == 20,
            f"{n_ok}/20, wait {min(waits):.2f}-{max(waits):.2f}s, states seen {sorted(states)}, "
            f"forced triggers {sc.stats['forced_triggers']}")
        sc.free_run()

        # T5 forced out-of-step, method A: ask for data when no screen record exists
        # Forcing is not deterministic (the stray reply shows up in roughly half
        # the rounds), so each round is checked for 'scope in step afterwards'
        # and the summaries require at least one PROVEN case of each kind.
        rounds = []
        for rnd in range(1, 13):
            who = "unchecked" if rnd % 2 else "layer"
            r = force_out_of_step_a(sc, who)
            rounds.append(r)
            rec(f"T5 scope: round {rnd} ({who}): in step afterwards "
                f"(went out of step: {r.get('was_out_of_step', False)})", r.get("recovered", False),
                {k: v for k, v in r.items() if k != "pass"})
        out["forced_rounds"] = rounds
        un = [r for r in rounds if r["who_meets_it"] == "unchecked" and r.get("was_out_of_step")]
        ly = [r for r in rounds if r["who_meets_it"] == "layer" and r.get("was_out_of_step")]
        rec("T5 scope: out-of-step PROVEN by an unchecked query receiving a wrong-format reply",
            len(un) > 0, f"{len(un)} of 6 rounds: {[r['unchecked_wrong_reply'] for r in un]}")
        rec("T5 scope: layer met the stray reply itself, detected it, resynced, and stayed in step",
            len(ly) > 0 and all(r["pass"] and r["layer_counters"]["resyncs"] >= 1 for r in ly),
            f"{len(ly)} of 6 rounds; counters {[r['layer_counters'] for r in ly]}")

        rounds_c = []
        for rnd in range(1, 4):
            r = force_out_of_step_bare_read(sc)
            rounds_c.append(r)
            # On @py run 8 a bare read did NOT put the scope out of step (it just
            # re-sent the last reply), so this check is 'in step afterwards'.
            rec(f"T5 scope: bare-read round {rnd}: in step afterwards "
                f"(went out of step: {r['was_out_of_step']})", r["recovered"],
                {k: v for k, v in r.items() if k != "pass"})
        out["forced_bare_read"] = rounds_c

        if "--skip-scan" not in sys.argv:
            r = force_out_of_step_scan(sc)
            out["forced_scan"] = r
            rec("T5 scope: SCAN-mode route (the one that needed a power cycle in M0), detected and resynced",
                r["pass"], {k: v for k, v in r.items() if k != "pass"})
    finally:
        try:
            sc.free_run()
        except Exception as e:
            log(f"free_run failed: {e}")
        bad = sv.restore()
        try:
            sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
        except Exception as e:
            bad.append(str(e))
        rec("scope: all changed settings restored and read back", not bad, bad)
        out["scope_stats"] = dict(sc.stats)
        try:
            out["scope_error_queue"] = sc.error_queue()
        except Exception as e:
            out["scope_error_queue"] = str(e)


def naive(sc, cmd):
    """One query with NO checking, as Milestone 0's scripts did it."""
    try:
        return sc._ask_raw(cmd)[:24]
    except pyvisa.errors.VisaIOError as e:
        return f"VISA {e.abbreviation}".encode()
    except Exception as e:                      # pyvisa-py can raise plain ValueError
        return f"{type(e).__name__} {e}".encode()


def verify_in_step(sc, n=20):
    """n validated queries of alternating reply formats plus one acquisition."""
    tb = sc.query(":TIMebase:SCALe?", io.v_float)
    for i in range(n):
        sc.query("*IDN?", io.v_scope_idn)
        sc.query("*OPC?", io.v_opc)
        if not io._close(sc.query(":TIMebase:SCALe?", io.v_float), tb):
            return False, "timebase reply changed"
        sc.query(":SYSTem:ERRor?", io.v_err)
        sc.status()
    a = sc.acquire([1, 2], force_after_s=0.6)
    sc.free_run()
    pts = [len(a["waves"][ch]["codes"]) for ch in (1, 2)]
    return pts == [700, 700], f"{n * 5} validated queries, acquisition points {pts}"


def force_out_of_step_a(sc, who="unchecked"):
    r = {"method": "RUN then immediate STOP, then :WAVeform:DATA? x3 with no screen record",
         "who_meets_it": who}
    sc.set_timebase(5e-3, "exact")          # slow enough that an immediate STOP finds no record
    sc.free_run()
    time.sleep(0.5)
    before = dict(sc.stats)
    empties = 0
    for attempt in range(1, 41):
        restart(sc)
        time.sleep(random.uniform(0.0, 0.03))
        sc.inst.write(":STOP")
        time.sleep(0.25)
        raw = naive(sc, ":WAVeform:DATA?")
        if len(raw) <= 2:
            empties = 1
            for _ in range(2):
                empties += len(naive(sc, ":WAVeform:DATA?")) <= 2
            r["stop_attempts_needed"] = attempt
            break
    r["empty_data_replies"] = empties
    if not empties:
        r["pass"] = False
        r["note"] = "could not produce an empty block in 40 attempts"
        restart(sc)
        return r
    restart(sc)
    if who == "layer":
        return layer_meets_it(sc, r, before)
    return evidence_and_recover(sc, r, before)


def layer_meets_it(sc, r, before):
    """No unchecked probing: the layer's own validated queries run back to back
    for 4 s, so the layer is the one that receives the stray reply. Evidence is
    the layer's own log line naming the query and the wrong reply it got."""
    n0 = len(logs)
    t0 = time.perf_counter()
    n = 0
    try:
        while time.perf_counter() - t0 < 4.0:
            sc.query("*IDN?", io.v_scope_idn)
            sc.query("*OPC?", io.v_opc)
            sc.query(":SYSTem:ERRor?", io.v_err)
            n += 3
        d = {k: sc.stats.get(k, 0) - before.get(k, 0)
             for k in ("resyncs", "out_of_step", "reply_errors", "device_restarts")}
        r["layer_queries"] = n
        r["layer_counters"] = d
        r["layer_log"] = [l[:260] for l in logs[n0:]]
        r["was_out_of_step"] = d["out_of_step"] + d["reply_errors"] > 0
        ok, why = verify_in_step(sc)
        r["after"] = why
        r["recovered"] = ok
    except Exception as e:
        r["recovered"] = False
        r["error"] = f"{type(e).__name__}: {e}"
        r["layer_log"] = [l[:260] for l in logs[n0:]]
    r["pass"] = r.get("was_out_of_step", False) and r["recovered"]
    return r


PROBES =[("*IDN?", b"UNI-T Tech"), ("*OPC?", b"1\r"), (":SYSTem:ERRor?", b"0,"),
          ("*IDN?", b"UNI-T Tech"), ("*OPC?", b"1\r"), (":SYSTem:ERRor?", b"0,")]


def evidence_and_recover(sc, r, before):
    """1. Unchecked queries, sent at once, until one gets a reply of the wrong
          format: that is the proof the scope is out of step. Probing stops
          there, leaving the scope out of step.
       2. One ordinary layer query. The layer must notice and repair by itself.
       3. 100 validated queries and one two-channel acquisition.
    A round only PASSES if step 1 really found the scope out of step."""
    # The reply owed for an unanswered :WAVeform:DATA? turns up roughly a second
    # after :RUN (run 8 of this test: probing for only 0.2 s missed it and the
    # layer then met it later). So probe for up to 4 s.
    n_ok, wrong, t0 = 0, None, time.perf_counter()
    while time.perf_counter() - t0 < 4.0 and wrong is None:
        for cmd, pre in PROBES:
            raw = naive(sc, cmd)
            if not raw.startswith(pre):
                wrong = dict(query=cmd, reply=repr(raw), after_s=round(time.perf_counter() - t0, 2))
                break
            n_ok += 1               # no pause: run 9 with a 30 ms pause between probes never caught it
    r["unchecked_probes_ok_before"] = n_ok
    r["unchecked_wrong_reply"] = wrong
    r["was_out_of_step"] = wrong is not None or r.get("was_out_of_step", False)
    try:
        tb = sc.query(":TIMebase:SCALe?", io.v_float)
        r["layer_timebase_reply"] = tb
        ok, why = verify_in_step(sc)
        d = {k: sc.stats.get(k, 0) - before.get(k, 0)
             for k in ("resyncs", "out_of_step", "reply_errors", "device_restarts")}
        r["layer_counters"] = d
        r["resync_detail"] = getattr(sc, "last_resync", None) if d["resyncs"] else None
        r["after"] = why
        r["recovered"] = ok and io._close(tb, 5e-3)
    except Exception as e:
        r["recovered"] = False
        r["error"] = f"{type(e).__name__}: {e}"
    r["pass"] = r["was_out_of_step"] and r["recovered"]
    return r


def force_out_of_step_bare_read(sc):
    """Read from the scope with no query pending. In M0 (my 'drain' loop) and in
    0b (my first 'flush') this left the scope one reply behind for good; under
    NI-VISA every later read failed with VI_ERROR_INP_PROT_VIOL."""
    r = {"method": "one device read with no query pending"}
    sc.set_timebase(5e-3, "exact")
    sc.free_run()
    time.sleep(0.5)
    before = dict(sc.stats)
    old = sc.inst.timeout
    sc.inst.timeout = 300
    try:
        r["bare_read"] = repr(sc.inst.read_raw()[:24])
    except Exception as e:
        r["bare_read"] = f"{getattr(e, 'abbreviation', type(e).__name__)}"
    finally:
        sc.inst.timeout = old
    return evidence_and_recover(sc, r, before)


def force_out_of_step_scan(sc):
    """50 ms/div puts the scope in SCAN status where :WAVeform:DATA? is empty.
    In M0 this sequence (plus my script dying mid-read) left the scope one reply
    behind until it was power-cycled."""
    r = {"method": "50 ms/div SCAN, :WAVeform:DATA? x3, :STOP, back to 5 ms/div, :RUN"}
    before = dict(sc.stats)
    sc.free_run()
    sc.inst.write(":TIMebase:SCALe 0.05")       # deliberately outside the step table
    time.sleep(1.5)
    r["status_at_50ms"] = repr(naive(sc, ":TRIGger:STATus?"))
    r["data_replies"] = [repr(naive(sc, ":WAVeform:DATA?")) for _ in range(3)]
    sc.inst.write(":STOP")
    time.sleep(0.3)
    r["naive_status_after_stop"] = repr(naive(sc, ":TRIGger:STATus?"))
    r["naive_idn_after_stop"] = repr(naive(sc, "*IDN?"))
    r["was_out_of_step"] = not r["naive_status_after_stop"].startswith("b'STOP")
    sc.inst.write(":TIMebase:SCALe 0.005")
    time.sleep(0.5)
    restart(sc)
    sc.tb = 5e-3
    return evidence_and_recover(sc, r, before)


# ------------------------------------------------------------------ generator tests
def gen_tests(g):
    num = io.GenFmt.num
    o = [g.output(1), g.output(2)]
    rec("T4 gen: both outputs OFF at start", o == [False, False], o)
    if o != [False, False]:
        g.output(1, False)
        g.output(2, False)
    sv = Saver(g)
    c = ":CHANnel1"
    sv.save(c + ":BASE:OFFSet", io.v_float, num)
    sv.save(c + ":BASE:AMPLitude", io.v_float, num)      # restored after the unit (reverse order)
    sv.save(c + ":BASE:FREQuency", io.v_float, num)
    sv.save(c + ":AMPLitude:UNIT", g.V_UNIT)
    sv.save(c + ":LOAD", io.v_float, num)
    sv.save(c + ":BASE:WAVe", g.V_WAVE)
    out["gen_originals"] = [(k, v) for k, _, v, _ in sv.items]
    try:
        g.configure_sine(1, 1000.0, 1.0, 0.0, "HIGHZ")
        rec("T4 gen: sine 1 kHz 1 Vpp High-Z configured, every setting read back", True)
        bad = []
        for f in (50, 123.456, 1000, 15915.5, 1e6, 12345678, 2e7):
            try:
                g.set_frequency(1, f)
            except Exception as e:
                bad.append(f"{f}: {e}")
        rec("T4 gen: 7 frequencies 50 Hz to 20 MHz set and read back", not bad, bad)
        bad = []
        for cmd, arg, v, exp in ((c + ":BASE:AMPLitude", "0.5", io.v_float, 0.5),
                                 (c + ":BASE:AMPLitude", "1", io.v_float, 1.0),
                                 (c + ":BASE:OFFSet", "0.1", io.v_float, 0.1),
                                 (c + ":BASE:OFFSet", "0", io.v_float, 0.0),
                                 (c + ":LOAD", "50", io.v_float, 50.0),
                                 (c + ":LOAD", "10000", io.v_float, 10000.0)):
            try:
                g.set_verified(cmd, arg, v, exp)
            except Exception as e:
                bad.append(f"{cmd} {arg}: {e}")
        rec("T4 gen: amplitude, offset, load set and read back", not bad, bad)

        # blocked commands: nothing may reach the instrument
        q0 = g.stats["queries"]
        for cmd in ("*OPC?", "*RST", ":SYSTem:LOCK OFF", ":CHANnel3:OUTPut ON", ":CHANnel1:OUTPut 1 ",
                    ":CHAN1:OUTP ON", ":CHANnel1:BASE:FREQuency 1e3", ":SYSTem:ERRor?"):
            expect_raises(f"T5 gen: blocked before sending: {cmd!r}", io.BlockedCommand,
                          lambda cmd=cmd: g.query(cmd, io.v_float) if cmd.endswith("?") else g.write(cmd))
        rec("T5 gen: no I/O happened for blocked commands", g.stats["queries"] == q0,
            f"blocked count {g.stats['blocked']}")
        rec("T5 gen: still answering after the blocked attempts", bool(g.query("*IDN?", io.v_gen_idn)))

        # timeout -> device clear -> single retry
        rounds = []
        for i in range(5):
            b = dict(g.stats)
            g.inject_timeout_once = True
            try:
                f = g.query(c + ":BASE:FREQuency?", io.v_float)
                d = {k: g.stats[k] - b[k] for k in ("timeouts", "clears", "retries")}
                # nothing stale may be left behind: alternate formats 10 times
                clean = True
                for _ in range(10):
                    clean &= bool(g.query("*IDN?", io.v_gen_idn))
                    clean &= io._close(g.query(c + ":BASE:FREQuency?", io.v_float), f)
                    g.query(c + ":AMPLitude:UNIT?", g.V_UNIT)
                rounds.append(dict(reply=f, counters=d, clean_after=clean,
                                   ok=d == {"timeouts": 1, "clears": 1, "retries": 1} and clean))
            except Exception as e:
                rounds.append(dict(ok=False, error=f"{type(e).__name__}: {e}"))
        out["gen_timeout_rounds"] = rounds
        rec("T5 gen: 5 injected timeouts, each recovered by device clear + one retry",
            all(r["ok"] for r in rounds), rounds)
    finally:
        g.safe_off()
        bad = sv.restore()
        rec("gen: all changed settings restored and read back", not bad, bad)
        o = [g.output(1), g.output(2)]
        rec("gen: both outputs OFF at end", o == [False, False], o)
        out["gen_stats"] = dict(g.stats)


def main():
    t1_offline()
    rm = open_rm(BACKEND)
    sc = g = None
    try:
        g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID), log=log)
        out["gen_idn"] = g.connect()
        sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=log)
        out["scope_idn"] = sc.connect(build_tables=False)
        rec("T2 connect: both instruments identified through the layer", True,
            f"{out['scope_idn']} | {out['gen_idn']}")
        try:
            gen_tests(g)
        except Exception:
            rec("generator tests crashed", False, traceback.format_exc())
        try:
            scope_tests(sc)
        except Exception:
            rec("scope tests crashed", False, traceback.format_exc())
    except Exception:
        rec("setup crashed", False, traceback.format_exc())
    finally:
        if g is not None:
            g.safe_off()
            g.close()
        if sc is not None:
            sc.close()
        rm.close()
    fails = [r for r in results if not r["ok"]]
    out["summary"] = f"{len(results) - len(fails)}/{len(results)} passed"
    print(out["summary"])
    print("saved", save(f"t0b_iolayer_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
