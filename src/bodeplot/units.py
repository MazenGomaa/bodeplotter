"""SI prefixes for display and input: 20000000 Hz <-> "20 MHz", 0.0005 V <-> "500 µV"."""
from __future__ import annotations

import math
import re

_PREFIXES = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"),
             (1e-9, "n"), (1e-12, "p")]
# Input is case-sensitive, as in SI: "M" is mega and "m" is milli. "meg" is also mega
# (SPICE habit); "u" stands in for the micro sign; "K" is accepted for kilo.
_MULT = {"G": 1e9, "M": 1e6, "meg": 1e6, "MEG": 1e6, "Meg": 1e6, "k": 1e3, "K": 1e3, "": 1.0, "m": 1e-3,
         "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12}
_NUM = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$")


def split_si(value: float, digits: int = 6) -> tuple[str, str]:
    """('20', 'M') for 2e7. digits = significant digits kept."""
    if value == 0 or not math.isfinite(value):
        return ("0" if value == 0 else str(value)), ""
    a = abs(value)
    scale, prefix = _PREFIXES[-1]
    for s, p in _PREFIXES:
        if a >= s * (1 - 1e-12):
            scale, prefix = s, p
            break
    text = "%.*g" % (digits, value / scale)
    if "e" in text or "E" in text:                  # beyond the prefix table: plain %g
        return "%.*g" % (digits, value), ""
    if float(text) >= 1000 and scale != _PREFIXES[0][0]:    # rounding pushed 999.9996 k to 1000 k
        i = [s for s, _ in _PREFIXES].index(scale)
        scale, prefix = _PREFIXES[i - 1]
        text = "%.*g" % (digits, value / scale)
    return text, prefix


def fmt_si(value, unit: str = "", digits: int = 6) -> str:
    """'20 MHz', '1.5 kHz', '500 µV', '50 Hz'. None or NaN gives ''."""
    if value is None:
        return ""
    value = float(value)
    if math.isnan(value):
        return ""
    num, prefix = split_si(value, digits)
    tail = prefix + unit
    return "%s %s" % (num, tail) if tail else num


def parse_si(text: str, unit: str = "") -> float:
    """'20M', '20 MHz', '1.5k', '100n', '2e7', '20meg' -> float. Raises ValueError."""
    m = _NUM.match(text or "")
    if not m:
        raise ValueError("not a number: %r" % text)
    number, tail = float(m.group(1)), m.group(2)
    if unit and tail.lower().endswith(unit.lower()):
        tail = tail[:len(tail) - len(unit)].strip()
    if tail not in _MULT:
        raise ValueError("unknown multiplier %r in %r (use p, n, u, m, k, M, G)" % (tail, text))
    return number * _MULT[tail]
