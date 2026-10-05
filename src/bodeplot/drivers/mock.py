"""Mock instruments and simulated DUT (SPEC.md section 9.5).

MockSource feeds MockScope. MockScope synthesises both channels:
  ref = stimulus x source-impedance divider
  dut = H(jw) x ref
then adds noise, an 8-bit ADC with clipping, trigger jitter, a first-order
50 MHz roll-off, and the UPO1054's channel skew fault (section 8.6).
"""
from __future__ import annotations

import cmath
import math
import random
import time
from dataclasses import dataclass, field

import numpy as np

from .base import (AcquireTimeout, Digitizer, DigitizerCaps, DriverError, SignalSource,
                   SourceCaps, Waveform)

# Real step tables of the UPO1054 (HW_REPORT.md 12.2). Note 25 ns, and no 20 ns.
TB_STEPS = (1e-9, 2e-9, 5e-9, 1e-8, 2.5e-8, 5e-8, 1e-7, 2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5,
            5e-5, 1e-4, 1e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2)
VDIV_STEPS = (5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)
SKEW_STATES_S = (-1.85e-9, 0.15e-9, 2.15e-9, 4.15e-9)
POINTS = 700
HDIVS = 14.0
CODES_PER_DIV = 25.0


# ---------------------------------------------------------------------- DUT
@dataclass
class SimulatedDUT:
    """Transfer function H(s) = num(s) / den(s), coefficients highest power first."""
    name: str = "through"
    num: tuple[float, ...] = (1.0,)
    den: tuple[float, ...] = (1.0,)
    input_impedance_ohm: float = 1e9        # loads the source (50 ohm) at the ref node
    params: dict = field(default_factory=dict)

    def h(self, freq_hz: float) -> complex:
        s = 2j * math.pi * freq_hz
        n = sum(c * s ** (len(self.num) - 1 - i) for i, c in enumerate(self.num))
        d = sum(c * s ** (len(self.den) - 1 - i) for i, c in enumerate(self.den))
        return n / d if d != 0 else complex("inf")

    # ---- presets
    @classmethod
    def through(cls) -> "SimulatedDUT":
        return cls("through")

    @classmethod
    def rc_lpf(cls, r: float = 1e3, c: float = 100e-9) -> "SimulatedDUT":
        return cls("rc_lpf", (1.0,), (r * c, 1.0), params=dict(r=r, c=c))

    @classmethod
    def rc_hpf(cls, r: float = 1e3, c: float = 100e-9) -> "SimulatedDUT":
        return cls("rc_hpf", (r * c, 0.0), (r * c, 1.0), params=dict(r=r, c=c))

    @classmethod
    def rlc_bpf(cls, r: float = 100.0, l: float = 1e-3, c: float = 100e-9) -> "SimulatedDUT":
        """Series L-C, output across R:  H = sRC / (s^2 LC + sRC + 1).  Q = sqrt(L/C)/R."""
        return cls("rlc_bpf", (r * c, 0.0), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def rlc_notch(cls, r: float = 100.0, l: float = 1e-3, c: float = 100e-9) -> "SimulatedDUT":
        """Series R, output across series L-C:  H = (s^2 LC + 1) / (s^2 LC + sRC + 1)."""
        return cls("rlc_notch", (l * c, 0.0, 1.0), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def butter2_lpf(cls, fc: float = 10e3) -> "SimulatedDUT":
        w = 2 * math.pi * fc
        return cls("butter2_lpf", (w * w,), (1.0, math.sqrt(2.0) * w, w * w), params=dict(fc=fc))

    @classmethod
    def custom(cls, num, den) -> "SimulatedDUT":
        return cls("custom", tuple(float(x) for x in num), tuple(float(x) for x in den))

    PRESETS = ("through", "rc_lpf", "rc_hpf", "rlc_bpf", "rlc_notch", "butter2_lpf", "custom")

    @classmethod
    def from_preset(cls, name: str, **kw) -> "SimulatedDUT":
        if name not in cls.PRESETS:
            raise ValueError(f"unknown DUT preset {name!r}")
        return getattr(cls, name)(**kw)


# ---------------------------------------------------------------------- source
class MockSource(SignalSource):
    caps = SourceCaps(model="MOCK-GEN", channels=2, sine_min_hz=1e-6, sine_max_hz=30e6,
                      amp_min_vpp=1e-3, amp_max_vpp=20.0, loads=("HIGHZ", "50"))
    SOURCE_IMPEDANCE = 50.0

    def __init__(self, latency_s: float = 0.0):
        self.latency_s = latency_s
        self.is_open = False
        self.freq_hz = 1000.0
        self.amp_vpp = 1.0
        self.offset_v = 0.0
        self.load = "HIGHZ"
        self.active_channel = 1
        self.output = {1: False, 2: False}
        self.safe_off_calls = 0
        self.fail_next: str | None = None       # test hook: raise DriverError on next command

    def _cmd(self, what: str):
        if not self.is_open:
            raise DriverError("generator is not open", what)
        if self.fail_next:
            msg, self.fail_next = self.fail_next, None
            raise DriverError(msg, what)
        if self.latency_s:
            time.sleep(self.latency_s)

    def open(self, resource: str = "SIM::GEN", backend: str = "sim") -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def idn(self) -> str:
        self._cmd("*IDN?")
        return "MOCK,UTG9SIM,0,1.0"

    def configure_sine(self, ch, freq_hz, amp_vpp, offset_v, load) -> None:
        self._cmd("configure_sine")
        if load not in self.caps.loads:
            raise DriverError(f"unsupported load {load!r}", "configure_sine")
        if not (self.caps.amp_min_vpp <= amp_vpp <= self.caps.amp_max_vpp):
            raise DriverError(f"amplitude {amp_vpp} Vpp out of range", "configure_sine")
        self.active_channel, self.amp_vpp, self.offset_v, self.load = ch, amp_vpp, offset_v, load
        self.set_frequency(ch, freq_hz)

    def set_frequency(self, ch, freq_hz) -> None:
        self._cmd("set_frequency")
        if not (self.caps.sine_min_hz <= freq_hz <= self.caps.sine_max_hz):
            raise DriverError(f"frequency {freq_hz} Hz out of range", "set_frequency")
        self.freq_hz = float(freq_hz)

    def set_output(self, ch, on) -> None:
        self._cmd("set_output")
        self.output[ch] = bool(on)

    def safe_off(self) -> None:
        self.safe_off_calls += 1
        for ch in self.output:
            self.output[ch] = False

    @property
    def is_on(self) -> bool:
        return self.output.get(self.active_channel, False)


# ---------------------------------------------------------------------- scope
class MockScope(Digitizer):
    def __init__(self, source: MockSource, dut: SimulatedDUT | None = None, *, ref_channel: int = 1,
                 dut_channel: int = 2, noise_vrms: float = 1e-4, jitter_s: float = 0.0,
                 latency_s: float = 0.0, seed: int | None = None, skew_enabled: bool = True):
        self.source = source
        self.dut = dut or SimulatedDUT.through()
        self.ref_channel, self.dut_channel = ref_channel, dut_channel
        self.noise_vrms = noise_vrms            # at the scope input, per sample
        self.jitter_s = jitter_s
        self.latency_s = latency_s
        self.rng = np.random.default_rng(seed)
        self._pyrng = random.Random(seed)
        self.caps = DigitizerCaps(
            model="MOCK-SCOPE", channels=4, bandwidth_hz=50e6, max_sample_rate=1e9,
            vdiv_steps=VDIV_STEPS, timebase_steps=TB_STEPS, vertical_divs=8.0, horizontal_divs=HDIVS,
            has_builtin_amplitude=True, has_builtin_phase=True, min_hz=20.0, max_hz=50e6)
        self.is_open = False
        self.alignment_epoch = 0
        self.skew_enabled = skew_enabled
        self._forced_state: int | None = None
        self.skew_s = 0.0
        self.extra_delay_s = 0.0                # test hook: off-grid delay on the DUT channel
        self.dut_gain_error_db = 0.0            # test hook: channel gain mismatch
        self.same_node = False                  # skew wizard in sim: DUT probe on the ref node
        self.timebase = 1e-3
        self.trigger = (ref_channel, 0.0)
        self.chan = {ch: dict(vdiv=1.0, coupling="DC", probe=1.0, bw_limit=False, offset=0.0)
                     for ch in range(1, 5)}
        self.acquire_count = 0
        self.fail_next: str | None = None       # test hook
        self.timeout_next = 0                   # test hook: this many acquisitions time out

    # ---- skew fault simulation
    def _roll_skew(self):
        if not self.skew_enabled:
            self.skew_s = 0.0
        elif self._forced_state is not None:
            self.skew_s = SKEW_STATES_S[self._forced_state]
        else:
            self.skew_s = self._pyrng.choice(SKEW_STATES_S)

    def force_skew_state(self, index: int | None) -> None:
        """Pin the skew to SKEW_STATES_S[index]; None returns to random draws."""
        self._forced_state = index
        self._roll_skew()

    def simulate_resync(self) -> None:
        """What a driver resync does to the real scope's alignment: a new epoch and,
        in the simulation, a new random state."""
        self.alignment_epoch += 1
        self._roll_skew()

    def sim_set_same_node(self, on: bool) -> None:
        self.same_node = bool(on)

    # ---- plumbing
    def _cmd(self, what: str):
        if not self.is_open:
            raise DriverError("scope is not open", what)
        if self.fail_next:
            msg, self.fail_next = self.fail_next, None
            raise DriverError(msg, what)
        if self.latency_s:
            time.sleep(self.latency_s)

    def open(self, resource: str = "SIM::SCOPE", backend: str = "sim") -> None:
        self.is_open = True
        self.alignment_epoch += 1
        self._roll_skew()

    def close(self) -> None:
        self.is_open = False

    def idn(self) -> str:
        self._cmd("*IDN?")
        return "MOCK,UPO1SIM,0,1.0"

    def configure_channel(self, ch, coupling, probe_atten, bw_limit, offset_v) -> None:
        self._cmd("configure_channel")
        if coupling not in ("DC", "AC"):
            raise DriverError(f"unsupported coupling {coupling!r}", "configure_channel")
        self.chan[ch].update(coupling=coupling, probe=float(probe_atten), bw_limit=bool(bw_limit),
                             offset=float(offset_v))

    def set_vdiv(self, ch, vdiv) -> float:
        self._cmd("set_vdiv")
        step = min(self.caps.vdiv_steps, key=lambda s: abs(s - vdiv))
        self.chan[ch]["vdiv"] = step
        return step

    def set_timebase(self, s_per_div) -> float:
        self._cmd("set_timebase")
        # like the real scope: a value between steps lands on the step below it
        lower = [s for s in self.caps.timebase_steps if s <= s_per_div * (1 + 1e-9)]
        self.timebase = max(lower) if lower else self.caps.timebase_steps[0]
        return self.timebase

    def set_trigger_edge(self, ch, level_v=0.0) -> None:
        self._cmd("set_trigger_edge")
        self.trigger = (ch, float(level_v))

    # ---- signal model
    def _rolloff(self, f: float, ch: int) -> complex:
        h = 1.0 / (1.0 + 1j * f / self.caps.bandwidth_hz)
        if self.chan[ch]["bw_limit"]:
            h *= 1.0 / (1.0 + 1j * f / 20e6)
        return h

    def _node_phasors(self) -> tuple[complex, complex, float, float]:
        """(ref, dut) phasors at the probe tips in volts peak, and their DC levels."""
        src = self.source
        if not src.is_on:
            return 0j, 0j, 0.0, 0.0
        zs, zin = src.SOURCE_IMPEDANCE, self.dut.input_impedance_ohm
        # the generator's amplitude setting is what appears across the load it is set for
        emf = 1.0 if src.load == "HIGHZ" else 2.0
        div = emf * zin / (zs + zin)
        ref = (src.amp_vpp / 2.0) * div
        h = 1.0 if self.same_node else self.dut.h(src.freq_hz)
        dc_gain = 1.0 if self.same_node else abs(self.dut.h(1e-9))
        dut = ref * h * 10 ** (self.dut_gain_error_db / 20.0)
        return complex(ref), complex(dut), src.offset_v * div, src.offset_v * div * dc_gain

    def acquire(self, chans, timeout_s) -> dict[int, Waveform]:
        self._cmd("acquire")
        if self.timeout_next > 0:
            self.timeout_next -= 1
            raise AcquireTimeout("acquisition not complete (simulated)", "acquire")
        self.acquire_count += 1
        f = self.source.freq_hz
        dt = self.timebase / 50.0
        t = -7.0 * self.timebase + dt * np.arange(POINTS)
        ref, dut, ref_dc, dut_dc = self._node_phasors()
        jitter = float(self.rng.normal(0.0, self.jitter_s)) if self.jitter_s else 0.0
        # edge trigger at 0 V rising on the reference channel puts its zero crossing at t = 0
        ref_seen = ref * self._rolloff(f, self.ref_channel)
        trig_phase = -math.pi / 2 - cmath.phase(ref_seen) if abs(ref_seen) else 0.0
        w = 2 * math.pi * f
        out = {}
        for ch in chans:
            c = self.chan[ch]
            if ch == self.ref_channel:
                ph, dc, delay = ref, ref_dc, 0.0
            elif ch == self.dut_channel:
                ph, dc, delay = dut, dut_dc, self.skew_s + self.extra_delay_s
            else:
                ph, dc, delay = 0j, 0.0, 0.0
            ph = ph * self._rolloff(f, ch)
            tip = abs(ph) * np.cos(w * (t + jitter + delay) + cmath.phase(ph) + trig_phase) if abs(ph) else \
                np.zeros(POINTS)
            if c["coupling"] == "DC":
                tip = tip + dc
            v_in = tip / c["probe"] + self.rng.normal(0.0, self.noise_vrms, POINTS)
            yinc = c["vdiv"] / CODES_PER_DIV
            codes = np.rint(v_in / yinc + c["offset"] / c["probe"] / yinc) + 128
            clipped = bool(np.any(codes <= 0) or np.any(codes >= 255))
            codes = np.clip(codes, 0, 255)
            volts = ((codes - 128) * yinc - c["offset"] / c["probe"]) * c["probe"]
            out[ch] = Waveform(dt=dt, t0=float(t[0]), volts=volts, clipped=clipped)
        return out

    def builtin_amplitude(self, ch) -> float:
        self._cmd("builtin_amplitude")
        ref, dut, _, _ = self._node_phasors()
        ph = ref if ch == self.ref_channel else dut if ch == self.dut_channel else 0j
        return abs(ph * self._rolloff(self.source.freq_hz, ch)) * (1 + float(self.rng.normal(0, 0.005)))

    def builtin_phase(self, ch_ref, ch_dut) -> float:
        self._cmd("builtin_phase")
        ref, dut, _, _ = self._node_phasors()
        if abs(ref) == 0 or abs(dut) == 0:
            raise DriverError("no signal for the built-in phase measurement", "builtin_phase")
        f = self.source.freq_hz
        deg = math.degrees(cmath.phase(dut / ref)) + 360.0 * f * (self.skew_s + self.extra_delay_s)
        return (deg + float(self.rng.normal(0, 0.3)) + 180.0) % 360.0 - 180.0


def make_sim(dut: SimulatedDUT | None = None, *, latency_s: float = 0.0, seed: int | None = None,
             noise_vrms: float = 1e-4, skew_enabled: bool = True,
             ref_channel: int = 1, dut_channel: int = 2) -> tuple[MockSource, MockScope]:
    src = MockSource(latency_s=latency_s)
    scope = MockScope(src, dut, latency_s=latency_s, seed=seed, noise_vrms=noise_vrms,
                      skew_enabled=skew_enabled, ref_channel=ref_channel, dut_channel=dut_channel)
    return src, scope
