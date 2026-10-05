"""Shared helpers for the Milestone 0 hardware gate scripts."""
import json
import os
import time

import pyvisa

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
os.makedirs(RESULTS, exist_ok=True)

# VID:PID as reported by Windows PnP on this machine (step 2).
SCOPE_VID, SCOPE_PID = 0x5656, 0x0832   # bus-reported name "UPO-1000X"
GEN_VID, GEN_PID = 0x6656, 0x0834       # bus-reported name "UTG900E"


def save(name, data):
    path = os.path.join(RESULTS, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return path


def open_rm(backend):
    """backend: '@py' or '@ivi' ('' means pyvisa default = IVI library)."""
    return pyvisa.ResourceManager("" if backend == "@ivi" else backend)


def find_resource(rm, vid, pid):
    """Return the USB INSTR resource string matching vid:pid, or None."""
    for r in rm.list_resources("?*"):
        parts = r.split("::")
        if not r.upper().startswith("USB") or len(parts) < 3:
            continue
        try:
            v = int(parts[1], 0)
            p = int(parts[2], 0)
        except ValueError:
            continue
        if (v, p) == (vid, pid):
            return r
    return None


def open_inst(rm, resource, timeout_ms=5000):
    inst = rm.open_resource(resource)
    inst.timeout = timeout_ms
    # Both manuals, "Instruction/Commands Format": "The command string must
    # end with a <Newline> (<NL>) character."
    inst.write_termination = "\n"
    inst.read_termination = "\n"
    # Found on hardware: the generator ends its replies with no terminator at
    # all (raw *IDN? reply ends b'1.09'), relying on the USBTMC end-of-message
    # flag. pyvisa-py tolerates read_termination='\n' there, but NI-VISA then
    # times out on every generator query (s04_s05_basic_ivi_run1.json). With
    # no read termination both backends work. The scope ends replies with CR LF.
    parts = resource.split("::")
    if len(parts) > 2 and int(parts[1], 0) == GEN_VID and int(parts[2], 0) == GEN_PID:
        inst.read_termination = None
    return inst


def num(x):
    """Plain-decimal number for SCPI arguments.

    Found on hardware (dbg_vdiv.py): the UPO scope silently ignores
    ':CHANnel1:SCALe 2.000000e-01' (no error, value unchanged) but accepts
    ':CHANnel1:SCALe 0.2'. So never send exponent notation.
    """
    s = f"{float(x):.12f}".rstrip("0").rstrip(".")
    return s or "0"


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0
