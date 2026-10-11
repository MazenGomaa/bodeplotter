"""Transfer functions of ideal circuits (SPEC.md section 9.5). No Qt, no instrument.

Used twice: as the DUT of Simulation mode (drivers/mock.py adds the load on the source)
and as the theory curves of the Bode plot (traces.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..units import fmt_si

# preset -> {part: (default value, label of its entry field)}
PARAMS: dict[str, dict[str, tuple[float, str]]] = {
    "through": {},
    "rc_lpf": {"r": (1e3, "R (Ω)"), "c": (100e-9, "C (F)")},
    "rc_hpf": {"r": (1e3, "R (Ω)"), "c": (100e-9, "C (F)")},
    "rlc_bpf": {"r": (100.0, "R (Ω)"), "l": (1e-3, "L (H)"), "c": (100e-9, "C (F)")},
    "rlc_notch": {"r": (100.0, "R (Ω)"), "l": (1e-3, "L (H)"), "c": (100e-9, "C (F)")},
    "butter2_lpf": {"fc": (10e3, "Cutoff (Hz)")},
    # circuits to try the analysis and the markers on: each shows one thing they report
    "rlc_lpf": {"r": (50.0, "R (Ω)"), "l": (1e-3, "L (H)"), "c": (100e-9, "C (F)")},
    "rc_shelf": {"r": (1e3, "R (Ω)"), "r2": (10.0, "R2, in series with C (Ω)"), "c": (100e-9, "C (F)")},
    "wide_bpf": {"fl": (100.0, "Lower cutoff (Hz)"), "fh": (100e3, "Upper cutoff (Hz)")},
    "butter_lpf": {"fc": (10e3, "Cutoff (Hz)"), "n": (5.0, "Order (1 to 10)")},
    "cheby_lpf": {"fc": (10e3, "Band edge (Hz)"), "ripple": (1.0, "Ripple (dB)"), "n": (5.0, "Order (1 to 10)")},
    "two_res": {"f1": (10e3, "First resonance (Hz)"), "q1": (10.0, "Its Q"),
                "f2": (300e3, "Second resonance (Hz)"), "q2": (20.0, "Its Q")},
    "crystal": {"fs": (1e6, "Series resonance (Hz)"), "fp": (1.05e6, "Parallel resonance (Hz)"), "q": (100.0, "Q")},
    "amp": {"gain": (10.0, "Gain (V/V)"), "fp": (50e3, "Pole (Hz)")},
    "loop3": {"gain": (4.0, "Gain at DC (V/V)"), "fp": (1e3, "The three poles (Hz)")},
    "custom": {},
}
LABELS: dict[str, str] = {
    "through": "Through (wire)", "rc_lpf": "RC low-pass", "rc_hpf": "RC high-pass",
    "rlc_bpf": "RLC band-pass", "rlc_notch": "RLC notch",
    "butter2_lpf": "Butterworth low-pass, 2nd order",
    "rlc_lpf": "RLC low-pass (resonant)", "rc_shelf": "RC low-pass with a floor",
    "wide_bpf": "Band-pass, flat top", "butter_lpf": "Butterworth low-pass", "cheby_lpf": "Chebyshev low-pass",
    "two_res": "Two resonances", "crystal": "Crystal (peak and notch)", "amp": "Amplifier, one pole",
    "loop3": "Loop gain, three poles", "custom": "Custom H(s)"}
PART_UNITS = {"r": "Ω", "r2": "Ω", "l": "H", "c": "F", "fc": "Hz", "fl": "Hz", "fh": "Hz", "f1": "Hz", "f2": "Hz",
              "fs": "Hz", "fp": "Hz", "q": "", "q1": "", "q2": "", "gain": "×", "ripple": "dB", "n": "poles"}
MAX_ORDER = 10


def _w(f: float) -> float:
    return 2 * math.pi * f


def _mul(a, b) -> list:
    """The product of two polynomials (coefficients highest power first)."""
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for k, y in enumerate(b):
            out[i + k] += x * y
    return out


def _from_poles(poles) -> list[float]:
    """The real polynomial with these roots (they come in conjugate pairs)."""
    out = [1.0 + 0j]
    for p in poles:
        out = _mul(out, [1.0, -p])
    return [c.real for c in out]


def _order(n: float) -> int:
    k = int(round(n))
    if not 1 <= k <= MAX_ORDER:
        raise ValueError("the order must be 1 to %d" % MAX_ORDER)
    return k


@dataclass
class TransferFunction:
    """H(s) = num(s) / den(s), coefficients highest power first."""
    name: str = "through"
    num: tuple[float, ...] = (1.0,)
    den: tuple[float, ...] = (1.0,)
    params: dict = field(default_factory=dict)

    def h(self, freq_hz: float) -> complex:
        s = 2j * math.pi * freq_hz
        try:
            n = sum(c * s ** (len(self.num) - 1 - i) for i, c in enumerate(self.num))
            d = sum(c * s ** (len(self.den) - 1 - i) for i, c in enumerate(self.den))
            return n / d if d != 0 else complex("inf")
        except OverflowError:               # a very high order at a high frequency: no usable value
            return complex("inf")

    def label(self) -> str:
        """Name for a trace: the circuit and its part values, e.g. 'RC low-pass 1 kΩ 100 nF'."""
        parts = " ".join(fmt_si(self.params[k], PART_UNITS[k]) for k in PARAMS.get(self.name, {})
                         if k in self.params)
        return (LABELS.get(self.name, self.name) + " " + parts).strip()

    # ---- presets
    @classmethod
    def through(cls):
        return cls("through")

    @classmethod
    def rc_lpf(cls, r: float = 1e3, c: float = 100e-9):
        return cls("rc_lpf", (1.0,), (r * c, 1.0), params=dict(r=r, c=c))

    @classmethod
    def rc_hpf(cls, r: float = 1e3, c: float = 100e-9):
        return cls("rc_hpf", (r * c, 0.0), (r * c, 1.0), params=dict(r=r, c=c))

    @classmethod
    def rlc_bpf(cls, r: float = 100.0, l: float = 1e-3, c: float = 100e-9):
        """Series L-C, output across R:  H = sRC / (s^2 LC + sRC + 1).  Q = sqrt(L/C)/R."""
        return cls("rlc_bpf", (r * c, 0.0), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def rlc_notch(cls, r: float = 100.0, l: float = 1e-3, c: float = 100e-9):
        """Series R, output across series L-C:  H = (s^2 LC + 1) / (s^2 LC + sRC + 1)."""
        return cls("rlc_notch", (l * c, 0.0, 1.0), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def butter2_lpf(cls, fc: float = 10e3):
        w = 2 * math.pi * fc
        return cls("butter2_lpf", (w * w,), (1.0, math.sqrt(2.0) * w, w * w), params=dict(fc=fc))

    # ---- circuits to try the analysis and the markers on
    @classmethod
    def rlc_lpf(cls, r: float = 50.0, l: float = 1e-3, c: float = 100e-9):
        """Series R-L, output across C:  H = 1 / (s^2 LC + sRC + 1).  Q = sqrt(L/C)/R; above
        0.7 the gain has a hump before the cut-off."""
        return cls("rlc_lpf", (1.0,), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def rc_shelf(cls, r: float = 1e3, r2: float = 10.0, c: float = 100e-9):
        """RC low-pass with R2 in series with C:  H = (sR2C + 1) / (s(R+R2)C + 1). The stop band
        levels off at R2 / (R + R2)."""
        return cls("rc_shelf", (r2 * c, 1.0), ((r + r2) * c, 1.0), params=dict(r=r, r2=r2, c=c))

    @classmethod
    def wide_bpf(cls, fl: float = 100.0, fh: float = 100e3):
        """A high-pass at fl and a low-pass at fh, buffered: a flat top between two cut-offs."""
        a, b = 1 / _w(fl), 1 / _w(fh)
        return cls("wide_bpf", (a, 0.0), tuple(_mul([a, 1.0], [b, 1.0])), params=dict(fl=fl, fh=fh))

    @classmethod
    def butter_lpf(cls, fc: float = 10e3, n: float = 5):
        n = _order(n)
        den = _from_poles([_w(fc) * complex(math.cos(a), math.sin(a))
                           for a in (math.pi * (2 * k + n - 1) / (2 * n) for k in range(1, n + 1))])
        return cls("butter_lpf", (den[-1],), tuple(den), params=dict(fc=fc, n=n))

    @classmethod
    def cheby_lpf(cls, fc: float = 10e3, ripple: float = 1.0, n: float = 5):
        """Chebyshev type 1: the passband moves by ripple dB and ends at fc, where the gain
        leaves the ripple band."""
        n = _order(n)
        eps = math.sqrt(10 ** (ripple / 10) - 1)
        a = math.asinh(1 / eps) / n
        den = _from_poles([_w(fc) * complex(-math.sinh(a) * math.sin((2 * k - 1) * math.pi / (2 * n)),
                                            math.cosh(a) * math.cos((2 * k - 1) * math.pi / (2 * n)))
                           for k in range(1, n + 1)])
        return cls("cheby_lpf", (den[-1] if n % 2 else den[-1] / math.sqrt(1 + eps * eps),), tuple(den),
                   params=dict(fc=fc, ripple=ripple, n=n))

    @classmethod
    def two_res(cls, f1: float = 10e3, q1: float = 10.0, f2: float = 300e3, q2: float = 20.0):
        """Two resonant band-passes side by side (their sum), each 0 dB at its top."""
        n1, d1 = [_w(f1) / q1, 0.0], [1.0, _w(f1) / q1, _w(f1) ** 2]
        n2, d2 = [_w(f2) / q2, 0.0], [1.0, _w(f2) / q2, _w(f2) ** 2]
        num = [x + y for x, y in zip(_mul(n1, d2), _mul(n2, d1))]
        return cls("two_res", tuple(num), tuple(_mul(d1, d2)), params=dict(f1=f1, q1=q1, f2=f2, q2=q2))

    @classmethod
    def crystal(cls, fs: float = 1e6, fp: float = 1.05e6, q: float = 100.0):
        """A crystal between two resistors: a peak at its series resonance and a notch at its
        parallel resonance, close together."""
        return cls("crystal", (1.0, _w(fp) / q, _w(fp) ** 2), (1.0, _w(fs) / q, _w(fs) ** 2),
                   params=dict(fs=fs, fp=fp, q=q))

    @classmethod
    def amp(cls, gain: float = 10.0, fp: float = 50e3):
        """An amplifier with one pole: a passband above 0 dB."""
        return cls("amp", (gain,), (1 / _w(fp), 1.0), params=dict(gain=gain, fp=fp))

    @classmethod
    def loop3(cls, gain: float = 4.0, fp: float = 1e3):
        """A loop gain with three equal poles: gain / (1 + s/w)^3. It passes -180 degrees at
        fp * sqrt(3) with gain / 8, so the gain and phase margins have something to read."""
        one = [1 / _w(fp), 1.0]
        return cls("loop3", (gain,), tuple(_mul(_mul(one, one), one)), params=dict(gain=gain, fp=fp))

    @classmethod
    def custom(cls, num, den):
        num, den = [float(x) for x in num], [float(x) for x in den]
        return cls("custom", tuple(num), tuple(den), params=dict(num=num, den=den))

    PRESETS = ("through", "rc_lpf", "rc_hpf", "rlc_bpf", "rlc_notch", "butter2_lpf", "rlc_lpf", "rc_shelf",
               "wide_bpf", "butter_lpf", "cheby_lpf", "two_res", "crystal", "amp", "loop3", "custom")

    @classmethod
    def from_preset(cls, name: str, **kw):
        if name not in cls.PRESETS:
            raise ValueError(f"unknown DUT preset {name!r}")
        return getattr(cls, name)(**kw)


def build(name: str, params: dict) -> TransferFunction:
    """A transfer function from values a user entered. Raises ValueError with a text for
    the user: a part that is missing, not a number or not positive; coefficients that
    leave no transfer function."""
    if name not in TransferFunction.PRESETS:
        raise ValueError("unknown circuit %r" % name)
    try:
        if name == "custom":
            num = [float(x) for x in params.get("num", [])]
            den = [float(x) for x in params.get("den", [])]
            if not num or not den or not any(den) or not all(math.isfinite(x) for x in num + den):
                raise ValueError("numerator and denominator need at least one coefficient, and the "
                                 "denominator one that is not zero")
            return TransferFunction.custom(num, den)
        values = {k: float(params[k]) for k in PARAMS[name]}
    except KeyError as e:
        raise ValueError("a value is missing: %s" % e.args[0]) from None
    except TypeError:
        raise ValueError("every value must be a number") from None
    except ValueError as e:
        if "coefficient" in str(e):
            raise
        raise ValueError("every value must be a number") from None
    if any(not math.isfinite(v) or v <= 0 for v in values.values()):
        raise ValueError("component values must be positive")
    return TransferFunction.from_preset(name, **values)
