"""Milestone 0b troubleshooting: s0b_dual.py read 0.99 Vpp on CH1 but only
noise on CH2. Is CH2's input really without signal, or is the CH2 readout
wrong? Compare the layer's waveform read-out with the scope's own
:MEASure:VPP? (U1K p.30) and :MEASure:FREQuency? (U1K p.33) on both channels,
free-running, with the generator at 1 kHz 1 Vpp.

Output ON for a few seconds only, OFF in finally. Generator and scope settings
changed here are restored."""
import time

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm
from t0b_iolayer import Saver, b01

rm = open_rm("@py")
g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
g.connect()
sc.connect(build_tables=False)
num, probe = io.GenFmt.num, io.ScopeFmt.probe
gs, ss = Saver(g), Saver(sc)
c = ":CHANnel1"
for k, v, f in ((c + ":BASE:OFFSet", io.v_float, num), (c + ":BASE:AMPLitude", io.v_float, num),
                (c + ":BASE:FREQuency", io.v_float, num), (c + ":AMPLitude:UNIT", g.V_UNIT, lambda x: x),
                (c + ":LOAD", io.v_float, num), (c + ":BASE:WAVe", g.V_WAVE, lambda x: x)):
    gs.save(k, v, f)
for ch in (1, 2):
    k = f":CHANnel{ch}"
    ss.save(k + ":SCALe", io.v_float, num)
    ss.save(k + ":OFFSet", io.v_float, num)
    ss.save(k + ":COUPling", io.V_COUPLING)
    ss.save(k + ":PROBe", io.v_float, probe)
    ss.save(k + ":DISPlay", io.v_bool, b01)
ss.save(":TIMebase:SCALe", io.v_float, num)
try:
    g.configure_sine(1, 1000.0, 1.0, 0.0, "HIGHZ")
    for ch in (1, 2):
        sc.configure_channel(ch, "DC", False, 0.0)
        sc.set_verified(f":CHANnel{ch}:SCALe", "0.2", io.v_float, 0.2)
    sc.tb = sc.set_verified(":TIMebase:SCALe", "0.0005", io.v_float, 0.0005)
    sc.free_run()
    g.output(1, True)
    time.sleep(2.0)
    for ch in (1, 2, 3, 4):
        k = f":CHANnel{ch}"
        print(f"CH{ch}: display {sc.query(k + ':DISPlay?', io.v_bool)}  coupling {sc.query(k + ':COUPling?', io.V_COUPLING)}  "
              f"V/div {sc.query(k + ':SCALe?', io.v_float)}  "
              f"scope MEAS VPP {sc.query(f':MEASure:VPP? CHANnel{ch}', lambda r: r)!r}  "
              f"FREQ {sc.query(f':MEASure:FREQuency? CHANnel{ch}', lambda r: r)!r}")
    # second run of this script: CH2 waveform showed 0.61 Vpp while MEAS said 0,
    # so repeat 12 times to see whether CH2 is stable (intermittent contact?)
    for i in range(12):
        a = sc.acquire([1, 2])
        line = []
        for ch in (1, 2):
            w = a["waves"][ch]
            v = w["volts"]
            mean = sum(v) / len(v)
            line.append(f"CH{ch} codes {min(w['codes']):3d}..{max(w['codes']):3d} "
                        f"Vpp {(max(v) - min(v)):.3f} mean {mean:+.3f}")
        sc.free_run()
        time.sleep(0.6)
        m = [sc.query(f":MEASure:VPP? CHANnel{ch}", lambda r: r) for ch in (1, 2)]
        print(f"  #{i:2d} " + " | ".join(line) + f" | scope MEAS VPP {m}")
finally:
    g.safe_off()
    print("outputs ON at end?", [g.output(1), g.output(2)])
    sc.free_run()
    print("restore failures:", gs.restore(), ss.restore())
    g.close()
    sc.close()
    rm.close()
