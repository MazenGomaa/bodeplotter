"""Step 8b: after the user unplugs and replugs each USB cable, confirm that a
fresh session opens, answers in step, and can still fetch a waveform.

Usage: python s08b_reconnect.py [@py|@ivi] [label]
Generator outputs are only queried (and forced OFF if found ON).
"""
import sys
import time
import traceback

import scpi
import wave
from common import (GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource,
                    open_inst, open_rm, save)

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "@py"
LABEL = sys.argv[2] if len(sys.argv) > 2 else "reconnect"
out = {"backend": BACKEND, "label": LABEL}

rm = open_rm(BACKEND)
out["resources"] = list(rm.list_resources("?*"))
print("resources:", out["resources"])

# ---- scope
try:
    s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
    seq = [(scpi.IDN, "UNI-T"), (scpi.OPC_Q, "1"), (scpi.S_ERR_Q, "0,"), (scpi.IDN, "UNI-T")]
    replies = [s.query(c).strip() for c, _ in seq]
    out["scope_replies"] = replies
    out["scope_in_step"] = all(r.startswith(p) for r, (_, p) in zip(replies, seq))
    tb = float(s.query(scpi.S_TB_SCAL + "?"))            # UPO p.23-24
    wave.setup_readout(s, 1)
    s.write(scpi.S_RUN)                                  # UPO p.8
    w = wave.acquire_stop(s, wave.guard_time(tb))
    out["scope_wave_points"] = len(w["codes"])
    out["scope_ok"] = out["scope_in_step"] and len(w["codes"]) > 0
    print("scope:", replies[0], "| in step:", out["scope_in_step"], "| points:", len(w["codes"]))
    s.close()
except Exception:
    out["scope_ok"] = False
    out["scope_error"] = traceback.format_exc()
    print(out["scope_error"])

# ---- generator
try:
    g = open_inst(rm, find_resource(rm, GEN_VID, GEN_PID))
    out["gen_idn"] = g.query(scpi.IDN).strip()                               # UTG p.5
    outs = [g.query(scpi.G_OUT.format(n=c) + "?").strip() for c in (1, 2)]   # UTG p.9
    out["gen_outputs"] = outs
    for c, st in zip((1, 2), outs):
        if st not in ("0", "OFF"):
            g.write(scpi.G_OUT.format(n=c) + " OFF")
            time.sleep(0.3)
    out["gen_freq"] = g.query(scpi.G_FREQ.format(n=1) + "?").strip()         # UTG p.12
    out["gen_idn_again"] = g.query(scpi.IDN).strip()
    out["gen_ok"] = out["gen_idn"].startswith("UNI-T") and out["gen_idn_again"] == out["gen_idn"]
    print("gen:", out["gen_idn"], "| outputs:", outs, "| ok:", out["gen_ok"])
    g.close()
except Exception:
    out["gen_ok"] = False
    out["gen_error"] = traceback.format_exc()
    print(out["gen_error"])

rm.close()
print("saved", save(f"s08b_{LABEL}_{BACKEND.strip('@')}.json", out))
