"""Abstract driver interfaces and capability records (SPEC.md section 6.1).

Capabilities are declared, never assumed: the GUI and engine adapt to them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


class DriverError(Exception):
    """Any instrument I/O failure, with the last command when known."""

    def __init__(self, message: str, last_command: str | None = None):
        super().__init__(message)
        self.last_command = last_command


class AcquireTimeout(DriverError):
    pass


@dataclass(frozen=True)
class SourceCaps:
    model: str
    channels: int
    sine_min_hz: float
    sine_max_hz: float
    amp_min_vpp: float          # into the selected load
    amp_max_vpp: float
    loads: tuple[str, ...]      # e.g. ("HIGHZ", "50")


class SignalSource(ABC):
    caps: SourceCaps

    @abstractmethod
    def open(self, resource: str, backend: str) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def idn(self) -> str: ...

    @abstractmethod
    def configure_sine(self, ch: int, freq_hz: float, amp_vpp: float,
                       offset_v: float, load: str) -> None: ...

    @abstractmethod
    def set_frequency(self, ch: int, freq_hz: float) -> None: ...

    @abstractmethod
    def set_output(self, ch: int, on: bool) -> None: ...

    @abstractmethod
    def safe_off(self) -> None:
        """All outputs off. Never raises."""


@dataclass(frozen=True)
class DigitizerCaps:
    model: str
    channels: int
    bandwidth_hz: float
    max_sample_rate: float
    vdiv_steps: tuple[float, ...]       # volts/div at the scope input (probe 1X)
    timebase_steps: tuple[float, ...]   # s/div; real steps, not assumed 1-2-5
    vertical_divs: float                # full-scale divisions used for auto-range
    horizontal_divs: float
    has_builtin_amplitude: bool
    has_builtin_phase: bool
    min_hz: float = 0.0                 # lowest frequency the timebase table can show
    max_hz: float = 0.0
    # Divisions the waveform data cover before they stop at a rail (more than the screen
    # shows on the UPO1054: 10.1 against 8). 0 = unknown.
    data_vertical_divs: float = 0.0


@dataclass
class Waveform:
    dt: float                 # seconds per sample
    t0: float
    volts: np.ndarray         # volts at the probe tip (probe ratio applied)
    clipped: bool             # any sample at an ADC rail
    rail_fraction: float = 0.0    # share of the samples sitting on a rail (0 when not clipped)

    @property
    def t(self) -> np.ndarray:
        return self.t0 + self.dt * np.arange(self.volts.size)


class Digitizer(ABC):
    caps: DigitizerCaps
    # Incremented on connect and on every driver resync. A channel skew check is only
    # valid for the epoch it was taken in (SPEC.md section 8.6).
    alignment_epoch: int = 0

    @abstractmethod
    def open(self, resource: str, backend: str) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def idn(self) -> str: ...

    @abstractmethod
    def configure_channel(self, ch: int, coupling: str, probe_atten: float,
                          bw_limit: bool, offset_v: float) -> None: ...

    @abstractmethod
    def set_vdiv(self, ch: int, vdiv: float) -> float:
        """vdiv is volts/div at the scope input. Returns the value actually set."""

    @abstractmethod
    def set_timebase(self, s_per_div: float) -> float:
        """Returns the value actually set."""

    @abstractmethod
    def set_trigger_edge(self, ch: int, level_v: float = 0.0) -> None: ...

    @abstractmethod
    def acquire(self, chans: list[int], timeout_s: float) -> dict[int, Waveform]:
        """One acquisition; every channel in chans is read from that same record."""

    def set_offset(self, ch: int, offset_v: float) -> float:
        """Vertical offset of a channel in volts at the scope input; positive moves the
        trace up. Returns the value actually set. Optional: auto-range works without it,
        but then cannot use the sensitive steps on a signal that carries DC."""
        raise NotImplementedError

    def lock_panel(self, on: bool) -> None:
        """Lock or release the front-panel keys, where the instrument can. Optional."""

    def free_run(self) -> None:
        """Leave the instrument running for the user after a sweep. Optional."""

    def save_setup(self) -> None:
        """Remember the user's settings before a measurement changes them. Optional."""

    def restore_setup(self) -> list[str]:
        """Put back what save_setup() remembered; returns what could not be restored."""
        return []

    def builtin_amplitude(self, ch: int) -> float:          # optional, volts peak
        raise NotImplementedError

    def builtin_phase(self, ch_ref: int, ch_dut: int) -> float:   # optional, degrees
        raise NotImplementedError
