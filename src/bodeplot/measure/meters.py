"""ResponseMeter implementations (SPEC.md section 6.2).

The sweep engine depends on a ResponseMeter, not on a scope, so other instrument
types (e.g. a magnitude-only receiver) stay possible.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ..drivers.base import AcquireTimeout, Digitizer, DriverError, Waveform
from ..models import (Flag, MeasureSettings, Method, PointResult, ScopeConfig, WaveformPair)
from ..sweep import autorange
from . import sinefit
from .builtin import builtin_transfer


@dataclass(frozen=True)
class MeterCaps:
    has_phase: bool
    min_hz: float
    max_hz: float


@dataclass
class MeterState:
    """Carried from point to point: the previous point's ranges are the next one's start."""
    vdiv: dict[int, float] = field(default_factory=dict)    # volts/div at the scope input
    timebase: float | None = None


class MeasureCancelled(Exception):
    """The caller asked to stop before a capture was available. Not an error."""


class ResponseMeter(ABC):
    caps: MeterCaps

    @abstractmethod
    def prepare(self, expected_vpp: float, offset_v: float = 0.0) -> None: ...

    @abstractmethod
    def measure(self, freq_hz: float, settings: MeasureSettings,
                state: MeterState) -> tuple[PointResult, WaveformPair | None]: ...


class ScalarReceiverMeter(ResponseMeter):
    """Gain-only meter (e.g. a spectrum analyser used as a receiver). Interface only in v1."""
    caps = MeterCaps(has_phase=False, min_hz=0.0, max_hz=0.0)

    def prepare(self, expected_vpp, offset_v=0.0):
        raise NotImplementedError("ScalarReceiverMeter is not implemented in v1")

    def measure(self, freq_hz, settings, state):
        raise NotImplementedError("ScalarReceiverMeter is not implemented in v1")


class DualChannelScopeMeter(ResponseMeter):
    """Gain and phase from two scope channels read out of one acquisition."""

    def __init__(self, digitizer: Digitizer, cfg: ScopeConfig,
                 should_stop: Callable[[], bool] = lambda: False,
                 sleep: Callable[[float], None] = time.sleep):
        self.dig, self.cfg = digitizer, cfg
        self.should_stop, self.sleep = should_stop, sleep
        c = digitizer.caps
        self.caps = MeterCaps(True, c.min_hz, c.max_hz or c.bandwidth_hz)

    def _probe(self, ch: int) -> float:
        return float(self.cfg.probe_atten.get(ch, 1.0)) or 1.0

    @property
    def chans(self) -> list[int]:
        return [self.cfg.ref_channel, self.cfg.dut_channel]

    def prepare(self, expected_vpp: float, offset_v: float = 0.0) -> None:
        d, c = self.dig, self.cfg
        for ch in self.chans:
            d.configure_channel(ch, c.coupling, self._probe(ch), c.bw_limit, 0.0)
        level = offset_v if c.coupling == "DC" else 0.0
        d.set_trigger_edge(c.ref_channel, level)
        self._expected_vpp = expected_vpp

    def initial_state(self) -> MeterState:
        """Start from the step the stimulus amplitude predicts (a coarse acquisition
        then corrects it: SPEC.md 8.2)."""
        st = MeterState()
        caps = self.dig.caps
        for ch in self.chans:
            vpp_in = max(self._expected_vpp, 1e-6) / self._probe(ch)
            st.vdiv[ch] = self.dig.set_vdiv(ch, autorange.choose_vdiv(vpp_in, caps.vdiv_steps,
                                                                      caps.vertical_divs))
        return st

    # ------------------------------------------------------------------
    def _set_timebase(self, freq_hz: float, state: MeterState) -> float:
        caps = self.dig.caps
        want = autorange.choose_timebase(freq_hz, caps.timebase_steps, caps.horizontal_divs,
                                         self.cfg.target_cycles)
        # points per screen are fixed, so too many cycles on screen starves samples/cycle
        steps = sorted(caps.timebase_steps)
        pts_per_div = 50.0
        while (autorange.samples_per_cycle(freq_hz, want / pts_per_div) < self.cfg.min_samples_per_cycle
               and steps.index(want) > 0
               and caps.horizontal_divs * steps[steps.index(want) - 1] * freq_hz >= 1.0):
            want = steps[steps.index(want) - 1]
        if state.timebase is None or abs(state.timebase - want) > 1e-12 * want:
            state.timebase = self.dig.set_timebase(want)      # use what the scope reports
        return state.timebase

    def _acquire(self, settings: MeasureSettings) -> dict[int, Waveform]:
        return self.dig.acquire(self.chans, settings.acquire_timeout_s)

    def _autorange(self, settings: MeasureSettings, state: MeterState):
        """Returns (waves, flags, retries). An acquisition timeout counts as one retry."""
        caps = self.dig.caps
        flags, retries, last_good, waves = Flag.NONE, 0, None, None
        while True:
            if self.should_stop():
                break
            try:
                waves = self._acquire(settings)
            except AcquireTimeout:
                retries += 1
                if retries > settings.autorange_max_retries:
                    raise
                continue
            changes, floor = {}, False
            for ch in self.chans:
                w = waves[ch]
                vpp_in = float(np.ptp(w.volts)) / self._probe(ch)
                dec = autorange.decide(vpp_in, w.clipped, state.vdiv[ch], caps.vdiv_steps,
                                       caps.vertical_divs, settings.autorange_target,
                                       settings.floor_fraction)
                if dec.action == "change":
                    changes[ch] = dec.vdiv
                elif dec.action == "floor":
                    floor = True
            if not any(waves[ch].clipped for ch in self.chans):
                last_good = waves
            if not changes:
                if floor:
                    flags |= Flag.BELOW_FLOOR
                break
            if retries >= settings.autorange_max_retries:
                flags |= Flag.AUTORANGE_FAILED
                if last_good is not None:
                    waves = last_good
                break
            for ch, v in changes.items():
                state.vdiv[ch] = self.dig.set_vdiv(ch, v)
            retries += 1
            self.sleep(settings.vdiv_settle_ms / 1000.0)
        if waves is not None and any(waves[ch].clipped for ch in self.chans):
            flags |= Flag.CLIPPED
        return waves, flags, retries

    def measure(self, freq_hz, settings, state):
        t_start = time.perf_counter()
        ref_ch, dut_ch = self.cfg.ref_channel, self.cfg.dut_channel
        if not state.vdiv:
            state.vdiv.update(self.initial_state().vdiv)
        tb = self._set_timebase(freq_hz, state)
        waves, flags, retries = self._autorange(settings, state)
        if waves is None:
            raise MeasureCancelled()
        hs, snr_ref, snr_dut, amps_ref, amps_dut = [], [], [], [], []
        pair = None
        n_avg = max(1, int(settings.averages))
        if settings.method is Method.BUILTIN:
            flags |= Flag.BUILTIN
            for _ in range(n_avg):
                if self.should_stop() and hs:
                    break
                h, a_ref, a_dut = builtin_transfer(self.dig, ref_ch, dut_ch)
                hs.append(h); amps_ref.append(a_ref); amps_dut.append(a_dut)
            w_ref, w_dut = waves[ref_ch], waves[dut_ch]
            pair = WaveformPair(freq_hz, w_ref.t, w_ref.volts, w_dut.volts)
        else:
            for i in range(n_avg):
                if i > 0:
                    if self.should_stop():
                        break
                    try:
                        waves = self._acquire(settings)        # a fresh acquisition per average
                    except AcquireTimeout:
                        retries += 1
                        continue
                w_ref, w_dut = waves[ref_ch], waves[dut_ch]
                f_ref = sinefit.fit3(w_ref.volts, w_ref.dt, freq_hz, w_ref.t0)
                f_dut = sinefit.fit3(w_dut.volts, w_dut.dt, freq_hz, w_dut.t0)
                if f_ref.amp <= 0:
                    continue
                hs.append(sinefit.transfer(f_ref, f_dut))
                snr_ref.append(f_ref.snr_db); snr_dut.append(f_dut.snr_db)
                amps_ref.append(f_ref.amp); amps_dut.append(f_dut.amp)
                pair = WaveformPair(freq_hz, w_ref.t, w_ref.volts, w_dut.volts,
                                    f_ref.evaluate(w_ref.t), f_dut.evaluate(w_dut.t))
            if snr_ref and min(float(np.mean(snr_ref)), float(np.mean(snr_dut))) < settings.low_snr_db:
                flags |= Flag.LOW_SNR
        if not hs:
            raise DriverError("no usable capture at %g Hz (reference amplitude is zero)" % freq_hz)
        h = complex(np.mean(hs))                                # complex mean across captures
        gain, phase = sinefit.gain_phase(h)
        point = PointResult(
            freq_hz=freq_hz, h=h, gain_db=gain, phase_deg=phase,
            vref_amp=float(np.mean(amps_ref)), vdut_amp=float(np.mean(amps_dut)),
            vdiv_ref=state.vdiv[ref_ch], vdiv_dut=state.vdiv[dut_ch], timebase=tb, n_avg=len(hs),
            snr_ref_db=float(np.mean(snr_ref)) if snr_ref else None,
            snr_dut_db=float(np.mean(snr_dut)) if snr_dut else None,
            flags=flags, duration_s=time.perf_counter() - t_start, retries=retries)
        return point, pair
