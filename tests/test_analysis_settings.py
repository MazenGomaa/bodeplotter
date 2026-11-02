"""The numbers of the analysis as settings (measure/analysis_settings.py; design
docs/superpowers/specs/2026-11-02-classification-design.md, section 5): every threshold has a
default, a range and a tooltip, is stored only when it differs, and reaches the maths."""
import ast
import dataclasses
import math
from pathlib import Path

import pytest

from bodeplot.io.settings import AppSettings
from bodeplot.markers import MarkerSet
from bodeplot.measure import analysis_settings as A
from bodeplot.measure.metrics import analyse
from bodeplot.measure.response import curve
from bodeplot.measure.theory import TransferFunction as TF

SRC = Path(__file__).resolve().parents[1] / "src" / "bodeplot"
FC = 1 / (2 * math.pi * 1e3 * 100e-9)
FREQS = [10.0 * 1e5 ** (i / 100) for i in range(101)]          # 10 Hz to 1 MHz, 20 per decade


def rc():
    tf = TF.rc_lpf(1e3, 100e-9)
    return curve(FREQS, [tf.h(f) for f in FREQS])


def test_every_field_has_a_default_inside_its_range_and_a_tooltip():
    keys = [f.key for f in A.FIELDS]
    assert len(keys) == len(set(keys))
    for f in A.FIELDS:
        assert f.lo <= f.default <= f.hi, f.key
        assert f.group in A.GROUPS and f.label and len(f.tip) > 30, f.key
        assert f.decimals > 0 or float(f.default).is_integer(), f.key
        assert getattr(A.DEFAULTS, f.key) == f.default


CLASSIFY_KEYS = {
    "Classification": ["crystal_ratio", "crystal_q", "allpass_deg", "notch_db", "shelf_lo", "shelf_hi", "ripple_db",
                       "ripple_scatter", "peaking_db", "gain_db", "min_stop_db", "span_dec", "noise_share",
                       "scatter_db", "scatter_warn", "point_flag_share", "min_score"],
    "Score weights": ["w_wide_flag", "w_short_passband", "w_limit", "w_from_peak", "w_noise_end", "w_scatter",
                      "w_no_phase", "w_few_points", "w_little_stop", "w_short_span"],
}


def test_the_classification_has_its_groups_of_fields():
    """Design section 5: the Classification and Score weights groups of the Analysis tab."""
    for group, keys in CLASSIFY_KEYS.items():
        assert group in A.GROUPS
        assert [f.key for f in A.FIELDS if f.group == group] == keys
    for key in CLASSIFY_KEYS["Score weights"]:
        f = A.field(key)
        assert f.unit == "%" and f.lo == 0 and f.hi == 100 and f.decimals == 0


def test_stored_values_are_cleaned():
    got = A.clean({"floor_db": 20, "flat_points": 7.6, "nonsense": 1, "drop_db": "6", "prominence_db": True,
                   "noise_db": float("nan"), "slope_window": 99.0})
    assert got == {"floor_db": 20.0, "flat_points": 8, "slope_window": A.field("slope_window").hi}
    assert A.clean("not a dict") == {}


def test_only_what_differs_is_stored_and_it_comes_back():
    assert A.to_stored(A.DEFAULTS) == {}
    s = dataclasses.replace(A.DEFAULTS, floor_db=20.0, few_points=7)
    assert A.to_stored(s) == {"floor_db": 20.0, "few_points": 7}
    assert A.from_stored(A.to_stored(s)) == s
    loaded = AppSettings.from_dict({"analysis": {"floor_db": 20.0, "unknown": 3}})
    assert loaded.analysis == {"floor_db": 20.0}
    assert AppSettings.from_dict({"analysis": [1, 2]}).analysis == {}


def test_a_setting_reaches_the_analysis_and_the_marker():
    """The cut-off 6 dB down lies at fc * sqrt(10 ** 0.6 - 1) on an RC low-pass."""
    six = dataclasses.replace(A.DEFAULTS, drop_db=6.0)
    assert analyse(rc()).cutoffs[0].f == pytest.approx(FC, rel=0.01)
    assert analyse(rc(), s=six).cutoffs[0].f == pytest.approx(FC * math.sqrt(10 ** 0.6 - 1), rel=0.01)
    markers = MarkerSet()
    markers.set_kind("cutoff", True)
    markers.analysis = six
    fc = next(m for m in markers.evaluate(rc()) if m.name == "fc")
    assert fc.freq == pytest.approx(FC * math.sqrt(10 ** 0.6 - 1), rel=0.01)
    assert not analyse(rc(), s=dataclasses.replace(A.DEFAULTS, min_points=200)).ok


def _bare_numbers(path: Path) -> list[tuple[int, object]]:
    """Numbers in the code outside the module's own named constants, other than 0, 1 and 2."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    named = {id(n) for stmt in tree.body if isinstance(stmt, (ast.Assign, ast.AnnAssign))
             for n in ast.walk(stmt)}
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and type(n.value) in (int, float) and id(n) not in named
            and n.value not in (0, 1, 2)]


def test_the_maths_holds_no_threshold_of_its_own():
    """The user, 2026-11-02: 'never let values be hardcoded'. A number of metrics.py is a field of
    AnalysisSettings, or a named constant of arithmetic at the top of the module."""
    assert _bare_numbers(SRC / "measure" / "metrics.py") == []
