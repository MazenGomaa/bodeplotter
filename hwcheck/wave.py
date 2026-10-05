"""Waveform fetch + decode for the UPO1002 family, and a dependency-free sine fit.

All scaling follows docs/Uni-T_UPO1002_Programming_Manual_0824.pdf:
  - :WAVeform:DATA? returns an IEEE 488.2 definite-length block (p.100-101, App. 2 p.137)
  - :WAVeform:PREamble? -> Format,Type,Points,Count,Xinc,Xor,Xref,Yinc,Yor,Yref (p.101-102)
  - Yref = "the channel zero level ADC" (fixed 128, p.104)
  - Yor  = "VerticalOffset/YINCrement" in ADC codes (p.104)
  - Yinc = volts per ADC code (p.103)
The manual gives no explicit volts formula; the one used here is
    volts = (code - Yref - Yor) * Yinc
and its sign convention for Yor is checked on hardware in s06_end_to_end.py.
"""
import math
import time

import scpi


def read_block(inst, cmd):
    """Send cmd, read one IEEE 488.2 '#' block, return the payload bytes."""
    old = inst.read_termination
    inst.read_termination = None      # payload is binary and may contain 0x0A
    try:
        inst.write(cmd)
        raw = inst.read_raw()
        if raw[:1] != b"#":
            raise ValueError(f"no '#' header, got {raw[:16]!r} (len {len(raw)})")
        nd = int(raw[1:2])
        n = int(raw[2:2 + nd])
        need = 2 + nd + n
        while len(raw) < need:
            raw += inst.read_raw()
        return raw[2 + nd:need], raw[need:]
    finally:
        inst.read_termination = old


def setup_readout(inst, ch=1):
    swrite(inst, f"{scpi.S_WAV_SRC} CHANnel{ch}")   # UPO p.99-100
    swrite(inst, f"{scpi.S_WAV_MODE} NORMal")       # UPO p.98 (screen data)
    swrite(inst, f"{scpi.S_WAV_FMT} BYTE")          # UPO p.98 (1 byte per point)


def fetch(inst):
    """Fetch the currently selected source. Returns (t0, dt, volts, codes, preamble)."""
    pre = inst.query(scpi.S_WAV_PRE_Q).strip()    # UPO p.101-102
    f = pre.split(",")
    xinc, xor = float(f[4]), float(f[5])
    yinc, yor, yref = float(f[7]), float(f[8]), float(f[9])
    data, tail = read_block(inst, scpi.S_WAV_DATA_Q)   # UPO p.100-101
    codes = list(data)
    volts = [(c - yref - yor) * yinc for c in codes]
    return dict(t0=xor, dt=xinc, volts=volts, codes=codes, preamble=pre,
                yinc=yinc, yor=yor, yref=yref, tail=repr(tail))


def swrite(inst, cmd):
    """Write, then block on *OPC? (UPO p.7).

    Found on hardware (s06 run 2): the scope silently drops a command that
    arrives while it is still applying the previous one (an OFFSet write sent
    right after a TIMebase:SCALe write was lost, with no error queued).
    """
    inst.write(cmd)
    return inst.query(scpi.OPC_Q).strip()


def wait_stopped(inst, timeout_s=2.0, poll=0.01):
    t0 = time.perf_counter()
    while True:
        st = inst.query(scpi.S_TRIG_STAT_Q).strip()   # UPO p.53
        if st.upper() == "STOP":
            return time.perf_counter() - t0
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError(f"scope did not reach STOP, status {st!r}")
        time.sleep(poll)


def guard_time(tb_s_per_div):
    """Minimum run time before :STOP so that a complete screen record exists.

    Found on hardware (dbg_wave2.py E2, 5 ms/div): a :STOP issued 0-0.2 s after
    :RUN left the scope with no screen data about 1 time in 10. In that state
    :WAVeform:DATA? answers with an empty reply (CR LF only), keeps doing so
    while stopped, and each unanswered :WAVeform:DATA? is answered LATE once
    the scope runs again, which puts every later reply one step behind.
    14 divisions per screen (UPO p.102-103), so wait two screens plus margin.
    """
    return max(0.3, 30.0 * tb_s_per_div)


def resync(inst, tries=8):
    """Bring replies back in step after an empty block: let the scope run, then
    read until *IDN? is answered by an *IDN? reply twice in a row."""
    inst.write(scpi.S_RUN)                        # UPO p.8
    time.sleep(0.5)
    good = 0
    for i in range(tries):
        r = inst.query(scpi.IDN)                  # UPO p.7
        good = good + 1 if r.startswith("UNI-T") else 0
        if good >= 2 and inst.query(scpi.OPC_Q).strip() == "1":
            return i + 1
    raise RuntimeError("scope replies still out of step after resync")


def acquire_stop(inst, guard_s=0.0):
    """Let the scope run for guard_s, freeze with :STOP, wait for
    :TRIGger:STATus? == STOP, read the screen record, then :RUN again.

    An empty block is NOT retried here (see guard_time): the ValueError is
    raised to the caller, who must call resync().
    """
    if guard_s:
        time.sleep(guard_s)
    inst.write(scpi.S_STOP)                       # UPO p.8
    try:
        wait_stopped(inst)
        w = fetch(inst)
        w["attempts"] = 1
        return w
    finally:
        inst.write(scpi.S_RUN)                    # UPO p.8


def acquire_single(inst, timeout_s=5.0, poll=0.02):
    """Single-shot: :TRIGger:SWEep SINGle, poll :TRIGger:STATus? until STOP."""
    seen = []
    t0 = time.perf_counter()
    inst.write(f"{scpi.S_TRIG_SWEEP} SINGle")     # UPO p.52-53; this alone arms the shot (0b)
    while True:
        st = inst.query(scpi.S_TRIG_STAT_Q).strip()   # UPO p.53
        if not seen or seen[-1] != st:
            seen.append(st)
        if st.upper() == "STOP":
            break
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError(f"single acquisition did not stop, states {seen}")
        time.sleep(poll)
    w = fetch(inst)
    w["single_states"] = seen
    w["single_wait_s"] = time.perf_counter() - t0
    return w


# ------------------------------------------------------------------ sine fit
def _fit3(v, dt, f):
    """3-parameter least squares at known f: a*cos + b*sin + c. Returns
    (a, b, c, rss)."""
    w = 2 * math.pi * f * dt
    n = len(v)
    scc = scs = sss = sc = ss = 0.0
    yc = ys = y1 = 0.0
    for i, y in enumerate(v):
        c, s = math.cos(w * i), math.sin(w * i)
        scc += c * c; scs += c * s; sss += s * s
        sc += c; ss += s
        yc += y * c; ys += y * s; y1 += y
    m = [[scc, scs, sc, yc], [scs, sss, ss, ys], [sc, ss, float(n), y1]]
    for i in range(3):                       # Gauss-Jordan with pivoting
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        for r in range(3):
            if r != i:
                k = m[r][i] / m[i][i]
                m[r] = [x - k * z for x, z in zip(m[r], m[i])]
    a, b, c0 = (m[i][3] / m[i][i] for i in range(3))
    rss = 0.0
    for i, y in enumerate(v):
        e = y - (a * math.cos(w * i) + b * math.sin(w * i) + c0)
        rss += e * e
    return a, b, c0, rss


def _f_guess(v, dt):
    """Frequency estimate from rising mean-crossings (linear interpolation)."""
    mean = sum(v) / len(v)
    xs = []
    for i in range(1, len(v)):
        y0, y1 = v[i - 1] - mean, v[i] - mean
        if y0 < 0 <= y1 and y1 != y0:
            xs.append(i - 1 + (-y0) / (y1 - y0))
    if len(xs) < 2:
        return None
    # crude noise rejection: use the median spacing
    gaps = sorted(b - a for a, b in zip(xs, xs[1:]))
    return 1.0 / (gaps[len(gaps) // 2] * dt)


def sine_fit(v, dt, f_hint=None):
    """Fit a sine with frequency as a free parameter (1-D golden-section search
    over f around a guess, 3-parameter linear fit inside). Pure Python."""
    f0 = _f_guess(v, dt) or f_hint
    if f0 is None:
        raise ValueError("no frequency estimate")
    # if the crossing estimate is wildly off the hint (noise), trust the hint
    if f_hint and not (0.5 * f_hint < f0 < 2 * f_hint):
        f0 = f_hint
    lo, hi = 0.9 * f0, 1.1 * f0
    g = (math.sqrt(5) - 1) / 2
    x1, x2 = hi - g * (hi - lo), lo + g * (hi - lo)
    r1, r2 = _fit3(v, dt, x1)[3], _fit3(v, dt, x2)[3]
    for _ in range(40):
        if r1 < r2:
            hi, x2, r2 = x2, x1, r1
            x1 = hi - g * (hi - lo)
            r1 = _fit3(v, dt, x1)[3]
        else:
            lo, x1, r1 = x1, x2, r2
            x2 = lo + g * (hi - lo)
            r2 = _fit3(v, dt, x2)[3]
    f = (lo + hi) / 2
    a, b, c, rss = _fit3(v, dt, f)
    amp = math.hypot(a, b)
    rms_res = math.sqrt(rss / len(v))
    snr = 20 * math.log10((amp / math.sqrt(2)) / rms_res) if rms_res > 0 else float("inf")
    return dict(freq_hz=f, amp_v=amp, vpp=2 * amp, offset_v=c,
                phase_deg=math.degrees(math.atan2(-b, a)),
                resid_rms_v=rms_res, snr_db=snr, f_guess=f0)
