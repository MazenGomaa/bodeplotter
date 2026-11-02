"""The Analysis table as text (analysis.py): rows, limits, the difference to a second trace,
the notes and the clipboard text."""
import math
import random

import pytest

from bodeplot.analysis import AT_LEAST, FLAG, GROUPS, NONE, notes, rows, table
from bodeplot.measure.metrics import analyse
from bodeplot.measure.response import curve
from bodeplot.measure.theory import TransferFunction as TF
from bodeplot.units import parse_si

FC = 1 / (2 * math.pi * 1e3 * 100e-9)
RC = TF.rc_lpf(1e3, 100e-9)
BPF = TF.rlc_bpf(100.0, 1e-3, 100e-9)


def grid(lo=50.0, hi=2e7, ppd=20):
    n = int(round(math.log10(hi / lo) * ppd)) + 1
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def m_of(tf, freqs=None, flagged=None, phase=True):
    freqs = freqs or grid()
    return analyse(curve(freqs, [tf.h(f) for f in freqs], [flagged(f) for f in freqs] if flagged else None), phase)


def cell(table_rows, group, name):
    (row,) = [r for r in table_rows if r.group == group and r.name == name]
    return row


def freq(text):
    return parse_si(text, "Hz")


def bp(f0, q):
    w = 2 * math.pi * f0
    return TF.custom([w / q, 0.0], [1.0, w / q, w * w])


def test_rows_of_an_rc_low_pass():
    t = rows(m_of(RC))
    assert [r.group for r in t] == ["Passband"] * 4 + ["Cut-off"] + ["Roll-off"] * 2 + ["Stopband"]
    assert [r.name for r in t] == ["Level", "Ripple", "Flat from", "Flat to", "fc", "Slope, fc", "Order, fc", "Beyond fc"]
    assert cell(t, "Passband", "Level").value in ("-0.01 dB", "-0.02 dB")
    assert cell(t, "Passband", "Flat from").value == "50 Hz" and cell(t, "Passband", "Flat to").value.endswith(" Hz")
    assert cell(t, "Stopband", "Beyond fc").value.startswith("≥ ") and AT_LEAST == "≥ "
    assert freq(cell(t, "Cut-off", "fc").value) == pytest.approx(FC, rel=0.005) and cell(t, "Cut-off", "fc").value.endswith(" kHz")
    assert cell(t, "Roll-off", "Slope, fc").value == "-20.0 dB/dec" and cell(t, "Roll-off", "Order, fc").value == "1"
    assert cell(t, "Stopband", "Beyond fc").value.startswith(AT_LEAST)                    # a limit says so
    assert all(r.compare == "" and r.diff == "" for r in t)
    assert all(r.tip == GROUPS[r.group] and len(r.tip) > 60 for r in t)


def test_rows_of_a_band_pass_with_its_resonance():
    t = rows(m_of(BPF))
    assert cell(t, "Passband", "Level (peak)").value == "+0.00 dB"       # never "-0.00"
    assert [r.name for r in t if r.group == "Cut-off"] == ["fL", "fH"]
    assert [r.name for r in t if r.group == "Band"] == ["Centre", "Bandwidth", "Q"]
    assert cell(t, "Band", "Q").value == "1"
    group = [r for r in t if r.group.startswith("Peak at ")]
    assert group[0].group == "Peak at 15.91 kHz"
    assert [r.name for r in group] == ["f0", "Gain at f0", "Height", "Q (width)", "Q (phase)", "Points"]
    assert group[3].value == "1" and group[5].value == "9" and all(r.tip == GROUPS["Peak"] for r in group)
    assert "Q (phase)" not in [r.name for r in rows(m_of(BPF, phase=False), phase=False)]
    notch = rows(m_of(TF.rlc_notch(100.0, 1e-3, 100e-9)))
    assert [r.name for r in notch if r.group.startswith("Notch at ")] == ["f0", "Gain at f0", "Depth", "Q (width)", "Points"]
    assert "Roll-off" not in [r.group for r in notch]            # into a notch there is no slope


def test_the_difference_to_a_second_trace():
    measured = m_of(TF.rc_lpf(1e3, 110e-9))                     # the capacitor is 10 % larger than the design says
    t = rows(measured, m_of(RC))
    fc = cell(t, "Cut-off", "fc")
    assert freq(fc.value) == pytest.approx(FC / 1.1, rel=0.005) and freq(fc.compare) == pytest.approx(FC, rel=0.005)
    assert float(fc.diff.rstrip(" %")) == pytest.approx(-9.1, abs=0.2) and fc.diff.endswith(" %")
    assert cell(t, "Passband", "Level").diff.endswith(" dB") and cell(t, "Roll-off", "Slope, fc").diff.endswith(" dB/dec")
    assert cell(t, "Roll-off", "Order, fc").diff == "0"
    assert cell(t, "Stopband", "Beyond fc").diff == ""                 # two limits have no difference
    assert cell(t, "Passband", "Ripple").diff == "+0.00 dB"            # never "-0.00"


def test_a_quantity_only_one_trace_has_keeps_its_row():
    t = rows(m_of(RC), m_of(BPF))
    assert cell(t, "Cut-off", "fc").compare == "" and cell(t, "Cut-off", "fL").value == ""
    assert cell(t, "Cut-off", "fL").compare != "" and cell(t, "Band", "Q").value == ""
    peak = [r for r in t if r.group.startswith("Peak at ")]
    assert peak and all(r.value == "" and r.compare != "" and r.diff == "" for r in peak)
    groups = [r.group for r in t]
    assert groups == sorted(groups, key=lambda g: (list(GROUPS) + [g]).index(g) if g in GROUPS else 99)


def test_resonances_pair_up_when_they_are_close():
    t = rows(m_of(bp(1.1e4, 10), grid(ppd=200)), m_of(bp(1e4, 10), grid(ppd=200)))
    group = [r for r in t if r.group.startswith("Peak at ")]
    assert len({r.group for r in group}) == 1                   # one resonance, seen in both traces
    assert float(group[0].diff.rstrip(" %")) == pytest.approx(10.0, abs=0.3)
    assert float(cell(group, group[0].group, "Q (width)").diff.rstrip(" %")) == pytest.approx(0.0, abs=2.0)
    t = rows(m_of(bp(2e4, 10), grid(ppd=200)), m_of(bp(1e4, 10), grid(ppd=200)))
    titles = []
    for r in t:
        if r.group.startswith("Peak at ") and r.group not in titles:
            titles.append(r.group)
    assert titles == ["Peak at 10 kHz", "Peak at 20 kHz"]       # too far apart: two resonances, in ascending order
    assert all(r.value == "" for r in t if r.group == titles[0]) and all(r.compare == "" for r in t if r.group == titles[1])


def test_flagged_numbers_are_marked_and_a_missing_q_says_none():
    t = rows(m_of(RC, flagged=lambda f: 1000.0 < f < 2000.0))
    assert cell(t, "Cut-off", "fc").value.endswith(FLAG) and not cell(t, "Passband", "Level").value.endswith(FLAG)
    hump = TF.custom([(2 * math.pi * 1e4) ** 2 * 1.0], [1.0, 2 * math.pi * 1e4 / 1.2, (2 * math.pi * 1e4) ** 2])
    peak = [r for r in rows(m_of(hump)) if r.group.startswith("Peak at ")]
    assert peak and peak[3].name == "Q (width)" and peak[3].value == NONE      # a 2 dB hump has no -3 dB width


def test_notes():
    assert notes(m_of(TF.through())) == ["No cut-off inside the sweep."]
    n = notes(m_of(RC))
    assert n == ["Beyond fc the sweep ends before the stop band levels off."]
    assert notes(m_of(BPF))[1] == "Beyond fL and fH the sweep ends before the stop band levels off."
    n = notes(m_of(RC, grid(200.0, 1e6)))                       # the sweep starts 0.9 decades below the cut-off
    assert n[0].startswith("The flat part runs to the low end of the sweep and spans less than a decade")
    assert n[0].endswith("start the sweep lower.") and len(n) == 2
    n = notes(m_of(TF.rc_hpf(1e3, 100e-9), grid(50.0, 1e4)))
    assert n[0].endswith("start the sweep higher.")
    n = notes(m_of(bp(1e4, 50)))
    assert n[0].startswith("No flat stretch") and any(s.startswith("Too few points on the peak at ") for s in n)
    assert any("sweep finer" in s for s in n)
    n = notes(m_of(RC, flagged=lambda f: f < 100.0))
    assert n[-1].endswith("is marked.") and " % of the points are flagged" in n[-1]
    assert notes(m_of(RC, [100.0, 1e3, 1e4])) == ["No analysis: fewer than 5 usable points."]
    assert rows(m_of(RC, [100.0, 1e3, 1e4])) == []


def test_a_note_says_where_the_noise_starts():
    rnd = random.Random(1)
    freqs = grid(20.0, 5e6)
    c = curve(freqs, [RC.h(f) + complex(rnd.gauss(0, 1e-4), rnd.gauss(0, 1e-4)) for f in freqs])
    n = notes(analyse(c))
    (noise,) = [s for s in n if "noise" in s]
    assert noise.startswith("Above ") and "the gain is lost in the noise (about -" in noise
    assert not any("levels off" in s for s in n)


def test_table_for_the_clipboard():
    m = m_of(RC)
    text = table("Analysis of: Sweep", rows(m), notes(m))
    lines = text.splitlines()
    assert lines[0] == "Analysis of: Sweep" and lines[1] == "Quantity\tValue"
    assert lines[2] == "Passband" and lines[3].split("\t")[0] == "Level" and "Flat from\t50 Hz" in lines
    fc = cell(rows(m), "Cut-off", "fc").value
    assert "fc\t" + fc in lines and lines[-2] == "" and lines[-1].startswith("Beyond fc")
    assert text.endswith("\n")
    both = table("Analysis of: Sweep, compared with: RC", rows(m, m), [], compare=True).splitlines()
    assert both[1] == "Quantity\tValue\tCompare\tDifference"
    assert "fc\t%s\t%s\t+0.0 %%" % (fc, fc) in both


def _elliptic():
    """A 5th-order Butterworth low-pass at 10 kHz with notches at 16 and 25 kHz."""
    w = lambda f: 2 * math.pi * f
    poles = [w(10e3) * complex(math.cos(math.pi * (2 * k + 4) / 10), math.sin(math.pi * (2 * k + 4) / 10))
             for k in range(1, 6)]
    den = [1.0 + 0j]
    for p in poles:
        den = [a - p * b for a, b in zip(den + [0j], [0j] + den)]
    den = [d.real for d in den]
    k = den[-1] / (w(16e3) * w(25e3)) ** 2
    num = [k, 0.0, k * (w(16e3) ** 2 + w(25e3) ** 2), 0.0, k * (w(16e3) * w(25e3)) ** 2]
    return TF.custom(num, den)


def test_beyond_a_notch_the_stopband_is_a_plain_number_and_a_band_stop_has_none():
    t = rows(m_of(_elliptic()))
    assert cell(t, "Stopband", "Beyond fc").value == "41.50 dB"         # the worst case, not "≥ 59"
    assert not [x for x in notes(m_of(_elliptic())) if x.startswith("Beyond")]
    notch = rows(m_of(TF.rlc_notch(100.0, 1e-3, 100e-9)))
    assert not [r for r in notch if r.group == "Stopband"] and [r for r in notch if r.group.startswith("Notch at ")]


def test_a_sweep_that_ends_while_the_gain_beyond_a_notch_rises_has_a_note():
    n = notes(m_of(_elliptic(), grid(50.0, 18e3)))
    assert [x for x in n if x.startswith("Beyond")] == ["Beyond fc the gain still rises where the sweep ends, past the notch: the stop band may come "
                 "back higher than the sweep shows."]


# ---------------------------------------------------------------------- the type (classification design, section 6)
def mk_of(tf, freqs=None, phase=True, wide=None):
    from bodeplot.measure.classify import classify
    freqs = freqs or grid()
    c = curve(freqs, [tf.h(f) for f in freqs], wide_flags=wide)
    m = analyse(c, phase)
    return m, classify(m, c, phase)


def test_type_group_first():
    m, k = mk_of(RC)
    t = rows(m, k=k)
    assert [(r.group, r.name) for r in t[:3]] == [("Type", "Type"), ("Type", "Shape"), ("Type", "Confidence")]
    assert [r.value for r in t[:3]] == ["Low-pass", "order 1", "100 %"]
    assert t[3].group == "Passband" and all(r.tip == GROUPS["Type"] for r in t[:3])
    assert list(GROUPS)[0] == "Type"
    assert [r.group for r in rows(m)][0] == "Passband"                  # without a type, as before


def test_refused_type_row():
    m, k = mk_of(RC, grid(10e3, 50e3))                                   # a slice of a slope
    t = rows(m, k=k)
    assert [r.value for r in t[:3]] == ["Not classified", "", ""]
    n = notes(m, k=k)
    assert n[0] == k.refused and n[0].startswith("Not classified: ")


def test_reasons_lead_the_notes():
    m, k = mk_of(RC, wide=["skew unchecked"])
    n = notes(m, k=k)
    assert n[0].startswith("−10 % Skew unchecked") and n[1:] == notes(m)
    assert cell(rows(m, k=k), "Type", "Confidence").value == "90 %"


def test_type_rows_compare():
    m, k = mk_of(RC)
    mb, kb = mk_of(BPF)
    mw, kw = mk_of(RC, wide=["skew unchecked"])
    t = rows(m, mb, k=k, ko=kb)
    assert (cell(t, "Type", "Type").compare, cell(t, "Type", "Type").diff) == ("Band-pass", "differs")
    assert cell(t, "Type", "Shape").compare == ", ".join(kb.words) and cell(t, "Type", "Shape").diff == ""
    t = rows(m, mw, k=k, ko=kw)
    assert cell(t, "Type", "Type").diff == "same" and cell(t, "Type", "Confidence").diff == "+10 points"
    assert cell(rows(mw, m, k=kw, ko=k), "Type", "Confidence").diff == "−10 points"
    mr, kr = mk_of(RC, grid(10e3, 50e3))
    t = rows(m, mr, k=k, ko=kr)
    assert cell(t, "Type", "Type").compare == "Not classified"
    assert cell(t, "Type", "Type").diff == "" and cell(t, "Type", "Confidence").diff == ""


def test_unknown_shows_no_confidence():
    """'Unknown, 100 %' reads as a contradiction: an unknown type has no confidence shown, and
    none to compare."""
    m, k = mk_of(TF.two_res())
    assert k.kind == "Unknown"
    t = rows(m, k=k)
    assert cell(t, "Type", "Confidence").value == ""
    mr, kr = mk_of(RC)
    assert cell(rows(m, mr, k=k, ko=kr), "Type", "Confidence").diff == ""


def test_the_type_tip_holds_the_crystal_rule():
    from bodeplot.analysis import group_tips
    from bodeplot.measure.analysis_settings import DEFAULTS
    tip = group_tips(DEFAULTS)["Type"]
    assert "a peak of Q 10 or more with a notch less than 1.2 times its frequency above it" in tip


def test_clipboard_has_the_type():
    m, k = mk_of(RC)
    lines = table("Analysis of: Sweep", rows(m, k=k), notes(m, k=k)).splitlines()
    assert lines[2:6] == ["Type", "Type\tLow-pass", "Shape\torder 1", "Confidence\t100 %"]


def test_a_type_refused_for_its_score_still_shows_the_score():
    """Design section 6: Confidence is the score when there is one."""
    import dataclasses
    from bodeplot.measure.analysis_settings import DEFAULTS
    from bodeplot.measure.classify import classify
    freqs = grid(100.0)
    c = curve(freqs, [RC.h(f) for f in freqs])
    s = dataclasses.replace(DEFAULTS, min_score=95)
    m = analyse(c, s=s)
    k = classify(m, c, True, s)
    assert [r.value for r in rows(m, s=s, k=k)[:3]] == ["Not classified", "", "80 %"]
