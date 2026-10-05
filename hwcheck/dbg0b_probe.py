"""Milestone 0b exploration (scope only, generator untouched, @ivi).

Answers needed before writing iolayer.py:
  a) does viClear (inst.clear()) upset the scope?
  b) real timebase steps via :TIMebase:SCALe UP/DOWN (UPO1000 p.16), capped at 20 ms/div
  c) which argument format sets 20 ns/div (M0 finding S6: 0.00000002 gave 10 ns)
  d) real V/div steps via :CHANnel1:SCALe UP/DOWN (UPO1000 p.14)
  e) CH3 / CH4 queries (UPO1000 documents <n> = 1..4)
  f) :WAVeform:SOURce? / :WAVeform:MODE? / :WAVeform:FORMat? replies
  g) single-shot with no signal, and :TRIGger:FORCe (UPO1000 p.36)
Every query is followed by a *IDN? sentinel so an out-of-step reply is caught.
Original timebase, CH1 V/div and sweep mode are restored at the end.
"""
import sys
import time

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, num, open_inst, open_rm, save

rm = open_rm("@ivi")
s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID))
out = {}


EMPTY = []      # (command, attempt) for every empty reply seen


def q(cmd):
    # First run of this script: ':TIMebase:SCALe?' sent 0.3 s after a timebase
    # change answered with an EMPTY reply while the sentinel stayed in step.
    # So an empty reply is retried here, and counted.
    for attempt in range(1, 21):
        r = s.query(cmd).strip()
        i = s.query(scpi.IDN)
        if not i.startswith("UNI-T"):
            raise RuntimeError(f"OUT OF STEP after {cmd!r}: reply {r!r}, sentinel {i[:30]!r}")
        if r != "":
            return r
        EMPTY.append((cmd, attempt, round(time.perf_counter(), 3)))
        time.sleep(0.1)
    raise RuntimeError(f"20 empty replies to {cmd!r}")


def w(cmd, settle=0.0):
    s.write(cmd)
    o = s.query(scpi.OPC_Q).strip()
    if o != "1":
        raise RuntimeError(f"*OPC? after {cmd!r} -> {o!r}")
    if settle:
        time.sleep(settle)


TB, V1 = ":TIMebase:SCALe", ":CHANnel1:SCALe"
tb0, v0, sw0 = q(TB + "?"), q(V1 + "?"), q(":TRIGger:SWEep?")
print("original: tb", tb0, "v/div", v0, "sweep", sw0, "status", q(":TRIGger:STATus?"))
try:
    # a) device clear
    try:
        s.clear()
        time.sleep(0.3)
        out["clear"] = "ok, then IDN " + q(scpi.IDN)[:30]
    except Exception as e:
        out["clear"] = f"{type(e).__name__}: {e}"
    print("a) clear:", out["clear"])

    # b) timebase steps: go to 1 ms, walk DOWN to the minimum, then UP to 20 ms
    w(f"{TB} 0.001", 0.3)
    steps, last = [], None
    for _ in range(40):
        cur = float(q(TB + "?"))
        if cur == last:
            break
        last = cur
        w(f"{TB} DOWN", 0.15)
    tb_min = last
    cur = tb_min
    for _ in range(60):
        steps.append(cur)
        if cur >= 0.02:
            break
        w(f"{TB} UP", 0.15)
        nxt = float(q(TB + "?"))
        if nxt == cur:
            break
        cur = nxt
    out["timebase_steps"] = steps
    print("b) timebase steps:", [f"{x:g}" for x in steps])

    # c) formats for 20 ns/div (start from 1 us each time)
    fm = {}
    for arg in ("0.00000002", "20ns", "20 ns", "2e-8", "0.000000020001", "0.0000000201"):
        w(f"{TB} 0.000001", 0.2)
        s.write(f"{TB} {arg}")
        o = s.query(scpi.OPC_Q).strip()
        time.sleep(0.3)
        fm[arg] = q(TB + "?")
    out["tb_20ns_formats"] = fm
    print("c) 20 ns formats:", fm)
    # same question for a few other steps with the plain-decimal formatter
    chk = {}
    for x in steps:
        w(f"{TB} 0.000001", 0.1) if x != 1e-6 else w(f"{TB} 0.00001", 0.1)
        w(f"{TB} {num(x)}", 0.2)
        chk[num(x)] = q(TB + "?")
    out["tb_plain_decimal_roundtrip"] = chk
    bad = {k: v for k, v in chk.items() if abs(float(v) - float(k)) > 1e-3 * float(k)}
    print("c) plain-decimal round trip mismatches:", bad)

    # d) V/div steps on CH1 (probe ratio must be 1X to read input-referred values)
    out["ch1_probe"] = q(":CHANnel1:PROBe?")
    out["ch1_vernier"] = q(":CHANnel1:VERNier?")
    w(f"{V1} 0.2", 0.3)
    last = None
    for _ in range(30):
        cur = float(q(V1 + "?"))
        if cur == last:
            break
        last = cur
        w(f"{V1} DOWN", 0.25)
    vsteps, cur = [], last
    for _ in range(30):
        vsteps.append(cur)
        w(f"{V1} UP", 0.25)
        nxt = float(q(V1 + "?"))
        if nxt == cur:
            break
        cur = nxt
    out["vdiv_steps"] = vsteps
    print("d) V/div steps (probe", out["ch1_probe"], "vernier", out["ch1_vernier"], "):", [f"{x:g}" for x in vsteps])
    vchk = {}
    for x in vsteps:
        w(f"{V1} {num(x)}", 0.25)
        vchk[num(x)] = q(V1 + "?")
    out["vdiv_plain_decimal_roundtrip"] = vchk
    print("d) V/div round trip mismatches:",
          {k: v for k, v in vchk.items() if abs(float(v) - float(k)) > 1e-3 * float(k)})

    # e) CH3 / CH4
    e = {}
    for ch in (2, 3, 4):
        e[ch] = {k: q(f":CHANnel{ch}:{k}?") for k in ("DISPlay", "PROBe", "SCALe", "OFFSet", "COUPling", "BWLimit")}
    out["channels"] = e
    print("e)", e)

    # f) readout queries
    out["wav"] = {c: q(c) for c in (":WAVeform:SOURce?", ":WAVeform:MODE?", ":WAVeform:FORMat?")}
    print("f)", out["wav"])

    # g) single shot with no signal
    w(f"{TB} 0.0005", 0.3)
    w(":TRIGger:SWEep SINGle")
    w(":TRIGger:SWEep AUTO")      # was ":RUN" before 0c; never sent now
    seen, t0 = [], time.perf_counter()
    while time.perf_counter() - t0 < 2.0:
        st = q(":TRIGger:STATus?")
        if not seen or seen[-1][1] != st:
            seen.append((round(time.perf_counter() - t0, 3), st))
        time.sleep(0.02)
    out["single_no_signal_2s"] = seen
    print("g) single, no signal, 2 s:", seen)
    w(":TRIGger:FORCe")
    seen, t0 = [], time.perf_counter()
    while time.perf_counter() - t0 < 1.5:
        st = q(":TRIGger:STATus?")
        if not seen or seen[-1][1] != st:
            seen.append((round(time.perf_counter() - t0, 3), st))
        time.sleep(0.02)
    out["after_force"] = seen
    print("g) after :TRIGger:FORCe:", seen)
    out["err"] = q(scpi.S_ERR_Q)
finally:
    try:
        s.write(f":TRIGger:SWEep {sw0}"); s.query(scpi.OPC_Q)
        s.write(":TRIGger:SWEep AUTO"); s.query(scpi.OPC_Q)   # was ":RUN" before 0c
        s.write(f"{TB} {num(tb0)}"); s.query(scpi.OPC_Q)
        s.write(f"{V1} {num(v0)}"); s.query(scpi.OPC_Q)
        time.sleep(0.5)
        print("restored: tb", s.query(TB + "?").strip(), "v/div", s.query(V1 + "?").strip(),
              "sweep", s.query(":TRIGger:SWEep?").strip(), "err", s.query(scpi.S_ERR_Q).strip())
    except Exception as e:
        print("restore failed:", e)
    s.close()
    rm.close()
    out["empty_replies"] = EMPTY
    print("empty replies:", len(EMPTY), EMPTY[:30])
    print("saved", save("dbg0b_probe.json", out))
