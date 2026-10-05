"""Read-only state check: generator outputs, scope lock state, scope sweep and status.

Usage: python s6_state.py [@py]

No setting is changed and no ':RUN' is sent. (Connecting through the layer does send
':TRIGger:SWEep AUTO' and a device clear, as every script does.)
"""
import sys

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")


def text(reply):
    return reply


out = {}
rm = open_rm(BACKEND)
g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
try:
    out["gen_idn"] = g.connect()
    out["gen_outputs"] = [g.output(1), g.output(2)]                              # UTG p.9
    out["scope_idn"] = sc.connect(build_tables=False)
    for q in (":SYSTem:LOCK?", ":TRIGger:SWEep?", ":TRIGger:STATus?", ":TIMebase:SCALe?",       # U1K p.6, 36, 37, 16
              ":CHANnel1:SCALe?", ":CHANnel2:SCALe?", ":CHANnel1:PROBe?", ":CHANnel2:PROBe?",   # U1K p.14
              ":SYSTem:ERRor?"):                                                                # U1K p.6
        out[q] = sc.query(q, text)
finally:
    g.close()
    sc.close()
    rm.close()
for k, v in out.items():
    print(f"{k:22s} {v}")
save("s6_state_py.json", out)
