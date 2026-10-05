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


def _sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def script_identity():
    """What exactly is running: the hash of the started script and of every hwcheck module
    it can import, plus the git commit. Printed at start-up (below) and stored with every
    result, so a stale or half-edited script cannot run unnoticed (2026-10-06: an edit that
    silently failed to apply let the old version of a script run on the bench again)."""
    import subprocess
    import sys
    main = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    ident = {"script": os.path.basename(main), "sha256": _sha(main) if os.path.isfile(main) else None,
             "modules": {n: _sha(os.path.join(HERE, n))[:12] for n in sorted(os.listdir(HERE))
                         if n.endswith(".py") and os.path.join(HERE, n) != main}}
    try:
        run = lambda *a: subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True, timeout=10)
        ident["git_commit"] = run("rev-parse", "--short", "HEAD").stdout.strip() or None
        ident["git_dirty"] = [l for l in run("status", "--porcelain", "--", ".").stdout.splitlines() if l.strip()]
    except Exception as e:
        ident["git_error"] = str(e)
    return ident


IDENTITY = script_identity()
if IDENTITY["sha256"]:
    _d = IDENTITY.get("git_dirty")
    print("[hwcheck] %s  sha256 %s  iolayer %s  git %s%s" % (
        IDENTITY["script"], IDENTITY["sha256"][:16], IDENTITY["modules"].get("iolayer.py"),
        IDENTITY.get("git_commit"), "" if not _d else "  UNCOMMITTED: " + ", ".join(x.strip() for x in _d)),
        flush=True)


def save(name, data):
    path = os.path.join(RESULTS, name)
    if isinstance(data, dict):
        data.setdefault("_identity", IDENTITY)
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
