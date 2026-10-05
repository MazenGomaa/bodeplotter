"""Milestone 0b: identity check through the I/O layer after a power cycle.

Usage: python s0b_identity.py [@py|@ivi]
Scope: resync (restart with :TRIGger:SWEep AUTO, never :RUN), *IDN?, timebase / sweep / status / channel queries.
Generator: *IDN?, output state query. Nothing else is changed.
"""
import sys

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "@py"
rm = open_rm(BACKEND)
print("resources:", list(rm.list_resources("?*")))
g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
print("gen  :", g.connect(), "| outputs ON?", [g.output(1), g.output(2)])
g.close()
sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
sc.inst.timeout = 5000
# connect() without touching the readout settings
sc.resync(run_wait=0.3)
print("scope:", sc.query("*IDN?", io.v_scope_idn))
print("  timebase", sc.query(":TIMebase:SCALe?", io.v_float), "| sweep", sc.query(":TRIGger:SWEep?", io.V_SWEEP),
      "| status", sc.status(), "| error queue", sc.error_queue())
for ch in (1, 2):
    c = f":CHANnel{ch}"
    print(f"  CH{ch}: display", sc.query(c + ":DISPlay?", io.v_bool), "probe", sc.query(c + ":PROBe?", io.v_float),
          "V/div", sc.query(c + ":SCALe?", io.v_float), "coupling", sc.query(c + ":COUPling?", io.V_COUPLING))
print("  resync:", sc.last_resync, "| stats", sc.stats)
sc.close()
rm.close()
