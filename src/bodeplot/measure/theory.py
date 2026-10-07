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
    "custom": {},
}
LABELS: dict[str, str] = {
    "through": "Through (wire)", "rc_lpf": "RC low-pass", "rc_hpf": "RC high-pass",
    "rlc_bpf": "RLC band-pass", "rlc_notch": "RLC notch",
    "butter2_lpf": "Butterworth low-pass, 2nd order", "custom": "Custom H(s)"}
PART_UNITS = {"r": "Ω", "l": "H", "c": "F", "fc": "Hz"}


@dataclass
class TransferFunction:
    """H(s) = num(s) / den(s), coefficients highest power first."""
    name: str = "through"
    num: tuple[float, ...] = (1.0,)
    den: tuple[float, ...] = (1.0,)
    params: dict = field(default_factory=dict)

    def h(self, freq_hz: float) -> complex:
        s = 2j * math.pi * freq_hz
        n = sum(c * s ** (len(self.num) - 1 - i) for i, c in enumerate(self.num))
        d = sum(c * s ** (len(self.den) - 1 - i) for i, c in enumerate(self.den))
        return n / d if d != 0 else complex("inf")

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

    @classmethod
    def custom(cls, num, den):
        num, den = [float(x) for x in num], [float(x) for x in den]
        return cls("custom", tuple(num), tuple(den), params=dict(num=num, den=den))

    PRESETS = ("through", "rc_lpf", "rc_hpf", "rlc_bpf", "rlc_notch", "butter2_lpf", "custom")

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
