"""Milestone 7: does the app put the scope back when it starts from an awkward state?

Run with the APP venv:  .venv\\Scripts\\python.exe -W ignore hwcheck\\m7_restore.py

The restore after a sweep (HW_REPORT.md 13.9) was proven on the bench only from the state
the app itself had left. Two cases were covered by the simulated scope alone:
  - a channel that is switched off before the sweep (SCALe is ignored on such a channel);
  - a scope probe ratio other than 1X (SCALe? is then probe-scaled, HW_REPORT.md S2; what
    OFFSet and the trigger level do was not known).
This script puts the scope in such a state, runs a short sweep through the app's own code,
compares every setting before and after, and finally puts back what it found at the start.
Only ordinary setting commands, each followed by '*OPC?' and the driver's pacing; no table
walk, no ':RUN'. PRECONDITION: the RC low-pass is wired; nobody needs to be at the bench.
"""
import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import save                              # prints this script's hash and git commit

from bodeplot.drivers import connect, scpi
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig
from bodeplot.sweep.core import Callbacks, SweepRunner

logging.basicConfig(level=logging.WARNING, format="   . %(name)s: %(message)s")
CH_KEYS = ("DISPlay", "PROBe", "VERNier", "SCALe", "OFFSet", "COUPling", "BWLimit")           # U1K p.12-15
QUERIES = [":CHANnel%d:%s?" % (ch, k) for ch in (1, 2) for k in CH_KEYS] + [
    ":TIMebase:SCALe?", ":TRIGger:MODE?", ":TRIGger:SOURce?", ":TRIGger:EDGE:SLOPe?", ":TRIGger:LEVel?"]   # U1K p.16, 36-39
RAW = lambda r: r
out = {"cases": []}


def read(dig):
    return {q: dig.query(q, RAW) for q in QUERIES}


def same(a, b):
    try:
        return abs(float(a) - float(b)) <= 1e-9 + 1e-6 * abs(float(b))
    except ValueError:
        return a == b


def diff(before, after):
    return {q: (before[q], after[q]) for q in QUERIES if not same(before[q], after[q])}


def put(dig, cmd, arg):
    """One setting, the driver's way (write, *OPC?, pacing), then what the scope reports."""
    dig.write("%s %s" % (cmd, arg))
    time.sleep(0.3)
    rb = dig.query(cmd + "?", RAW)
    print("      %-24s %-10s -> %s" % (cmd, arg, rb), flush=True)
    return rb


def put_back(dig, state):
    """The start state, without relying on the code under test: channel on and at 1X while
    its scale and offset are set (input-referred), then the probe ratio, the display last."""
    for ch in (1, 2):
        c = ":CHANnel%d" % ch
        g = lambda k: state["%s:%s?" % (c, k)]
        ratio = float(g("PROBe"))
        dig.write(c + ":DISPlay 1")
        dig.write(c + ":PROBe 1X")
        dig.write(c + ":VERNier " + ("1" if float(g("VERNier")) else "0"))
        dig.write(c + ":SCALe " + scpi.plain_decimal(float(g("SCALe")) / ratio))
        dig.write(c + ":OFFSet " + scpi.plain_decimal(float(g("OFFSet")) / ratio))
        dig.write(c + ":COUPling " + g("COUPling"))
        dig.write(c + ":BWLimit " + g("BWLimit"))
        dig.write(c + ":PROBe " + scpi.probe_ratio(ratio))
        dig.write(c + ":DISPlay " + ("1" if float(g("DISPlay")) else "0"))
    dig.write(":TIMebase:SCALe " + scpi.plain_decimal(float(state[":TIMebase:SCALe?"])))
    dig.write(":TRIGger:MODE " + state[":TRIGger:MODE?"])
    dig.write(":TRIGger:SOURce " + state[":TRIGger:SOURce?"])
    dig.write(":TRIGger:EDGE:SLOPe " + state[":TRIGger:EDGE:SLOPe?"])
    dig.write(":TRIGger:LEVel " + scpi.plain_decimal(float(state[":TRIGger:LEVel?"])))
    time.sleep(0.5)


def sweep(session):
    logs = []
    runner = SweepRunner(session, SweepConfig(start_hz=1000.0, stop_hz=100000.0, points_per_decade=2),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(),
                         Callbacks(log=lambda e: logs.append([e.level, e.text])))
    result = runner.run()
    pts = [(p.freq_hz, round(p.gain_db, 3), p.flags.name or str(p.flags)) for p in result.points]
    return dict(error=result.meta.get("error"), points=pts, log=logs)


def case(session, label, setup):
    dig = session.digitizer
    print("\n%s\n   setting the scope up:" % label, flush=True)
    setup(dig)
    time.sleep(0.5)
    before = read(dig)
    r = sweep(session)
    after = read(dig)
    d = diff(before, after)
    print("   sweep: %d points, error %s, gains %s" % (len(r["points"]), r["error"], [p[1] for p in r["points"]]))
    for level, text in r["log"]:
        if level != "info" and "skew" not in text.lower():
            print("   [%s] %s" % (level, text))
    print("   state before the sweep:", {k.strip(":?"): v for k, v in before.items()})
    print("   NOT RESTORED:", d or "nothing: all %d settings came back" % len(QUERIES), flush=True)
    out["cases"].append(dict(label=label, before=before, after=after, not_restored=d, sweep=r))
    return d


def main():
    session = connect.open_session("py")
    dig = session.digitizer
    print("generator: %s\nscope:     %s" % (session.source_idn, session.digitizer_idn))
    start = read(dig)
    out["start_state"] = start
    print("state at the start:", {k.strip(":?"): v for k, v in start.items()})
    try:
        def ch2_off(d):
            put(d, ":CHANnel2:SCALe", "0.05")
            put(d, ":CHANnel2:OFFSet", "0.02")
            put(d, ":CHANnel1:SCALe", "0.5")
            put(d, ":TIMebase:SCALe", "0.001")
            put(d, ":CHANnel2:DISPlay", "0")
        case(session, "CASE 1: CH2 switched off (50 mV/div, offset 20 mV), CH1 500 mV/div, 1 ms/div", ch2_off)

        def probe_10x(d):
            put(d, ":CHANnel2:DISPlay", "1")
            put(d, ":CHANnel1:PROBe", "10X")
            put(d, ":CHANnel1:SCALe", "0.05")        # input-referred argument: reads back 0.5 at 10X
            put(d, ":CHANnel1:OFFSet", "0.1")
            put(d, ":CHANnel1:COUPling", "AC")
            put(d, ":CHANnel1:BWLimit", "20M")
            put(d, ":TRIGger:EDGE:SLOPe", "NEGative")
            put(d, ":TRIGger:LEVel", "0.2")
        case(session, "CASE 2: CH1 at probe 10X, AC, 20 MHz limit, offset and trigger level not zero", probe_10x)
    finally:
        try:
            print("\nputting the start state back")
            put_back(dig, start)
            end = read(dig)
            out["end_state"], out["end_differs_from_start"] = end, diff(start, end)
            print("differs from the start state:", out["end_differs_from_start"] or "nothing")
            out["outputs_at_end"] = [session.source.output(1), session.source.output(2)]
            out["panel_locked_at_end"] = dig.query(":SYSTem:LOCK?", RAW)                      # U1K p.6
            out["sweep_mode_at_end"] = dig.query(":TRIGger:SWEep?", RAW)                      # U1K p.36
            print("at the end: generator outputs ON? %s, panel lock %s, scope sweep %s" % (
                out["outputs_at_end"], out["panel_locked_at_end"], out["sweep_mode_at_end"]))
            out["scope_stats"] = dict(dig.stats)
            print("scope counters:", out["scope_stats"])
        finally:
            session.close()
            print("saved", save(os.path.join("m7", "m7_restore.json"), out))


if __name__ == "__main__":
    main()
