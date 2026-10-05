"""Probe tool: check both instruments command by command (SPEC.md section 9.4).

    python -m bodeplot.tools.probe                 identify, query every documented command,
                                                   one test acquisition on scope CH1
    python -m bodeplot.tools.probe --no-acquire    queries only
    python -m bodeplot.tools.probe --unlock        release the scope's front-panel lock, nothing else
    python -m bodeplot.tools.probe --walk-tables   measure this scope's timebase and V/div steps
                                                   (see the warning it prints first)

Rules it keeps, the same as the app:
  - generator outputs are switched OFF at the start and at the end, and never switched on;
  - only queries are sent, apart from: outputs OFF, the waveform read-out format, one
    single-shot acquisition and the sweep mode put back to AUTO afterwards;
  - ':RUN' is never sent (the driver refuses it);
  - the step tables are NOT walked unless --walk-tables is given.
It prints its own file hash first, so it is always clear which version ran.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..drivers import connect, scpi, step_tables
from ..drivers.base import DriverError
from ..drivers.uni_t_upo1000 import UniTUPO1000
from ..drivers.uni_t_utg900e import UniTUTG900E

WALK_WARNING = """\
WARNING: --walk-tables steps the scope through every timebase and V/div setting.
  * On 2026-10-06 the UPO1054 froze during such a walk (HW_REPORT.md 12.13): its screen
    stopped, it took no more commands, and only switching it off and on brought it back.
  * The walk is therefore paced (%.0f ms after every step) and can take a few minutes.
  * Do not touch the scope's front panel while it runs.
  * It changes the timebase and CH1 V/div and puts both back at the end.
The app does not need this: it ships with measured tables. Only walk a scope model or
firmware the app warned about."""


@dataclass
class Row:
    instrument: str
    command: str
    page: str
    verified: bool
    result: str         # PASS | FAIL | INFO
    detail: str


def file_hashes() -> dict[str, str]:
    here = Path(__file__).resolve()
    files = [here] + sorted((here.parents[1] / "drivers").glob("*.py"))
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in files}


def _expand(text: str, channels) -> list[str]:
    q = text if text.endswith("?") else text + "?"
    return [q.replace("<n>", str(n)) for n in channels] if "<n>" in q else [q]


# ---------------------------------------------------------------------- generator
def probe_generator(gen: UniTUTG900E, say=print) -> list[Row]:
    rows = []
    gen.safe_off()
    for c in gen.COMMANDS:
        if not c.query:
            continue
        for q in _expand(c.text, (1, 2)):
            try:
                rows.append(Row("generator", q, c.page, c.verified, "PASS", str(gen.query(q, scpi.v_text))))
            except DriverError as e:
                rows.append(Row("generator", q, c.page, c.verified, "FAIL", "%s: %s" % (type(e).__name__, e)))
            say("  %-4s %-34s %-9s %s" % (rows[-1].result, q, c.page, rows[-1].detail))
    gen.safe_off()
    try:
        outs = [gen.output(1), gen.output(2)]
        rows.append(Row("generator", "outputs at the end", "UTG p.9", True, "PASS" if not any(outs) else "FAIL",
                        "CH1 %s, CH2 %s" % tuple("ON" if o else "OFF" for o in outs)))
    except DriverError as e:
        rows.append(Row("generator", "outputs at the end", "UTG p.9", True, "FAIL", str(e)))
    say("  %-4s %-34s %s" % (rows[-1].result, rows[-1].command, rows[-1].detail))
    return rows


# ---------------------------------------------------------------------- scope
def probe_scope(scope: UniTUPO1000, acquire: bool = True, say=print) -> list[Row]:
    rows = []
    rows.append(Row("scope", "step tables", "-", scope.tables_exact, "INFO",
                    ("stored tables for this model and firmware (%s)" % scope.tables.source)
                    if scope.tables_exact else "NO stored tables for this model and firmware: fallback in use"))
    say("  INFO step tables: " + rows[-1].detail)
    for c in scope.COMMANDS:
        if not c.query or c.text in ("*IDN?", "*OPC?"):
            continue
        for q in _expand(c.text, range(1, scope.caps.channels + 1)):
            try:
                rows.append(Row("scope", q, c.page, c.verified, "PASS", str(scope.query(q, scpi.v_text))))
            except DriverError as e:
                rows.append(Row("scope", q, c.page, c.verified, "FAIL", "%s: %s" % (type(e).__name__, e)))
            say("  %-4s %-34s %-9s %s" % (rows[-1].result, q, c.page, rows[-1].detail))
    if acquire:
        try:
            t0 = time.perf_counter()
            w = scope.acquire([1], 8.0)[1]
            detail = ("%d points, dt %.3g s, %.4g to %.4g V at the input, clipped %s, forced trigger %s, %.2f s"
                      % (w.volts.size, w.dt, float(w.volts.min()), float(w.volts.max()), w.clipped,
                         "yes" if scope.stats["forced_triggers"] else "no", time.perf_counter() - t0))
            rows.append(Row("scope", "single-shot acquisition CH1", "U1K p.36, 70", True, "PASS", detail))
        except DriverError as e:
            rows.append(Row("scope", "single-shot acquisition CH1", "U1K p.36, 70", True, "FAIL",
                            "%s: %s" % (type(e).__name__, e)))
        say("  %-4s %-34s %s" % (rows[-1].result, rows[-1].command, rows[-1].detail))
        try:
            scope.free_run()                    # leave it running, never ':RUN'
        except DriverError as e:
            rows.append(Row("scope", "sweep back to AUTO", "U1K p.36", True, "FAIL", str(e)))
    return rows


def walk_tables(scope: UniTUPO1000, gap_s: float, say=print, sleep=None) -> tuple[list[float], list[float]]:
    """Walk the real steps with UP / DOWN (U1K p.16 and p.14), paced, and return them.
    Restores timebase and CH1 V/div. Raises DriverError on an implausible result."""
    sleep = sleep or scope._sleep
    tb_cmd, v_cmd = ":TIMebase:SCALe", ":CHANnel1:SCALe"
    tb0, v0 = scope.query(tb_cmd + "?", scpi.v_float), scope.query(v_cmd + "?", scpi.v_float)
    if scope.query(":CHANnel1:VERNier?", scpi.v_bool) or not scpi.close(
            scope.query(":CHANnel1:PROBe?", scpi.v_float), 1.0):
        raise DriverError("the walk needs CH1 at coarse V/div (fine adjust off) and probe 1X; "
                          "set that on the scope first: this tool does not change it")
    top_tb = max(step_tables.FALLBACK.timebase)         # never into 50 ms/div and slower (SCAN)

    def nudge(cmd, direction, cur):
        for k in range(3):                              # 'no change' must repeat before it counts
            scope.write("%s %s" % (cmd, direction))
            sleep(gap_s * (k + 1))
            nxt = scope.query(cmd + "?", scpi.v_float)
            if not scpi.close(nxt, cur):
                return nxt
        return cur

    def walk(cmd, start, stop_at):
        cur = scope.set_verified(cmd, scpi.plain_decimal(start), scpi.v_float, float(start))
        sleep(gap_s)
        for _ in range(60):
            nxt = nudge(cmd, "DOWN", cur)
            if scpi.close(nxt, cur):
                break
            cur = nxt
        steps = [cur]
        for _ in range(80):
            if stop_at is not None and cur >= stop_at * 0.999:
                break
            nxt = nudge(cmd, "UP", cur)
            if scpi.close(nxt, cur):
                break
            cur = nxt
            steps.append(cur)
            say("    %s %g" % (cmd, cur))
        return steps

    def check(name, steps):
        ratios = [b / a for a, b in zip(steps, steps[1:])]
        if len(steps) < 10 or not all(1.9 <= r <= 2.6 for r in ratios):
            raise DriverError("%s step table is implausible: %s" % (name, ["%g" % s for s in steps]))

    try:
        tb = walk(tb_cmd, 0.001, top_tb)
        check("timebase", tb)
        vd = walk(v_cmd, 0.2, None)
        check("V/div", vd)
    finally:
        scope.set_verified(tb_cmd, scpi.plain_decimal(tb0), scpi.v_float, tb0)
        sleep(gap_s)
        scope.set_verified(v_cmd, scpi.plain_decimal(v0), scpi.v_float, v0)
    return tb, vd


# ---------------------------------------------------------------------- main
def main(argv=None, session_opener=None, say=print, confirm=input) -> int:
    ap = argparse.ArgumentParser(prog="python -m bodeplot.tools.probe", description=__doc__.split("\n")[0])
    ap.add_argument("--backend", default="py", choices=("py", "auto", "ivi"))
    ap.add_argument("--gen", default="", help="generator resource string (default: find it)")
    ap.add_argument("--scope", default="", help="scope resource string (default: find it)")
    ap.add_argument("--no-acquire", action="store_true", help="queries only, no test acquisition")
    ap.add_argument("--unlock", action="store_true", help="release the scope's front-panel lock and exit")
    ap.add_argument("--walk-tables", action="store_true", help="measure the scope's step tables (see warning)")
    ap.add_argument("--gap-ms", type=float, default=250.0, help="pause after every step of the walk (min 100)")
    ap.add_argument("--yes", action="store_true", help="do not ask before --walk-tables")
    ap.add_argument("--json", default="", help="write the report to this file")
    args = ap.parse_args(argv)

    hashes = file_hashes()
    say("bodeplot probe %s   probe.py sha256 %s" % (__version__, hashes["probe.py"]))
    say("drivers: " + "  ".join("%s %s" % (k, v) for k, v in hashes.items() if k != "probe.py"))
    gap_s = max(args.gap_ms, 100.0) / 1000.0
    if args.walk_tables:
        say(WALK_WARNING % (gap_s * 1000))
        if not args.yes and confirm("Type WALK to go on, anything else to stop: ").strip() != "WALK":
            say("Stopped. Nothing was sent to the instruments.")
            return 2

    from ..io.settings import config_dir
    opener = session_opener or (lambda: connect.open_session(args.backend, args.gen, args.scope,
                                                             scope_min_gap_s=max(0.1, gap_s if args.walk_tables else 0.1)))
    report = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "version": __version__,
              "hashes": hashes, "args": vars(args), "rows": []}
    try:
        session = opener()
    except Exception as e:
        say("Could not connect: %s" % e)
        return 1
    gen, scope = session.source, session.digitizer
    code = 0
    try:
        say("generator: %s\nscope:     %s" % (session.source_idn, session.digitizer_idn))
        report.update(generator_idn=session.source_idn, scope_idn=session.digitizer_idn)
        for w in session.take_warnings():
            say("WARNING: " + w)
        if args.unlock:
            scope.lock_panel(False)
            say("Front-panel lock released (:SYSTem:LOCK? = %s)." % scope.query(":SYSTem:LOCK?", scpi.v_text))
            return 0
        if args.walk_tables:
            gen.safe_off()
            tb, vd = walk_tables(scope, gap_s, say)
            path = config_dir() / step_tables.USER_FILE
            step_tables.save_user(path, scope.model, scope.firmware, tb, vd,
                                  "walked with the probe tool, %s" % report["time"])
            report["walked"] = {"timebase": tb, "vdiv": vd, "saved_to": str(path)}
            say("timebase steps: %s\nV/div steps:    %s\nSaved to %s" % (
                ", ".join("%g" % x for x in tb), ", ".join("%g" % x for x in vd), path))
        else:
            say("\nGenerator (outputs stay OFF):")
            rows = probe_generator(gen, say)
            say("\nScope:")
            rows += probe_scope(scope, acquire=not args.no_acquire, say=say)
            report["rows"] = [asdict(r) for r in rows]
            fails = [r for r in rows if r.result == "FAIL"]
            say("\n%d checks, %d failed." % (len([r for r in rows if r.result != "INFO"]), len(fails)))
            code = 1 if fails else 0
        report["scope_stats"], report["generator_stats"] = dict(scope.stats), dict(gen.stats)
    except DriverError as e:
        say("STOPPED: %s%s" % (e, (" " + e.advice) if getattr(e, "advice", "") else ""))
        report["error"] = str(e)
        code = 1
    finally:
        gen.safe_off()
        session.close()
        say("Generator outputs switched off; connections closed.")
        if args.json:
            Path(args.json).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            say("Report written to %s" % args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
