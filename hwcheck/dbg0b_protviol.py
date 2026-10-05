"""Milestone 0b troubleshooting: ScopeIO.connect() failed with
VI_ERROR_INP_PROT_VIOL on every read (t0b_iolayer first two runs, @ivi).
Step through clear / flush / read variants to find what triggers it.
Scope only; sends *IDN?, *OPC?, :RUN and nothing else."""

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

import pyvisa

from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm

rm = open_rm("@ivi")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), timeout_ms=3000)


def t(label, fn):
    try:
        print(f"{label:28s} -> {fn()!r}"[:110])
    except Exception as e:
        print(f"{label:28s} -> ERR {getattr(e, 'abbreviation', type(e).__name__)} {str(e)[:50]}")


def ask():
    s.write("*IDN?")
    return s.read_raw()


t("idn, term LF", lambda: s.query("*IDN?"))
t("clear", s.clear)
time.sleep(0.5)
t("idn, term LF, after clear", lambda: s.query("*IDN?"))
t("opc", lambda: s.query("*OPC?"))
s.read_termination = None
t("idn, term None", ask)
t("write :RUN", lambda: s.write(":RUN"))
time.sleep(0.5)
t("idn after :RUN", ask)
t("clear", s.clear)
time.sleep(0.3)
t("idn after clear", ask)
t("flush host read buffer", lambda: s.flush(pyvisa.constants.BufferOperation.discard_read_buffer))
t("idn after flush", ask)
t("clear", s.clear)
time.sleep(0.3)
t("idn after clear", ask)
t("idn again", ask)
s.close()
rm.close()
