"""Data models (SPEC.md section 7)."""
from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any


class SweepType(enum.Enum):
    LOG = "log"
    LINEAR = "linear"


class Method(enum.Enum):
    SINEFIT = "sinefit"
    BUILTIN = "builtin"


class Flag(enum.Flag):
    NONE = 0
    CLIPPED = enum.auto()
    BELOW_FLOOR = enum.auto()
    AUTORANGE_FAILED = enum.auto()
    LOW_SNR = enum.auto()
    REMEASURED = enum.auto()
    BUILTIN = enum.auto()
    SKEW_UNCHECKED = enum.auto()
    REF_SUSPECT = enum.auto()       # the reference capture did not hold the stimulus, even after retries

    def names(self) -> list[str]:
        return [f.name for f in Flag if f is not Flag.NONE and f in self]

    def to_text(self) -> str:
        return "|".join(self.names())

    @classmethod
    def from_text(cls, text: str) -> "Flag":
        out = cls.NONE
        for part in (text or "").replace(",", "|").split("|"):
            part = part.strip()
            if part and part in cls.__members__:
                out |= cls[part]
        return out


class EngineState(enum.Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    PAUSED = "paused"
    ABORTING = "aborting"
    DONE = "done"
    ERROR = "error"


@dataclass
class SweepConfig:
    sweep_type: SweepType = SweepType.LOG
    start_hz: float = 50.0
    stop_hz: float = 20e6
    points_per_decade: int = 20     # LOG
    n_points: int = 101             # LINEAR
    descending: bool = False


@dataclass
class StimulusConfig:
    gen_channel: int = 1
    amp_vpp: float = 1.0
    offset_v: float = 0.0
    load: str = "HIGHZ"


@dataclass
class ScopeConfig:
    ref_channel: int = 1
    dut_channel: int = 2
    probe_atten: dict[int, float] = field(default_factory=lambda: {1: 10.0, 2: 10.0})
    coupling: str = "DC"            # "DC" | "AC"
    bw_limit: bool = False
    target_cycles: float = 5.0
    min_samples_per_cycle: int = 20


@dataclass
class MeasureSettings:
    method: Method = Method.SINEFIT
    averages: int = 1
    settle_ms: float = 50.0
    settle_cycles: float = 3.0      # settle = max(settle_ms, settle_cycles/f)
    autorange_target: tuple[float, float] = (0.6, 0.8)   # fraction of full scale (p-p)
    autorange_max_retries: int = 3
    floor_fraction: float = 0.1     # below this at min V/div -> BELOW_FLOOR
    acquire_timeout_s: float = 5.0
    vdiv_settle_ms: float = 20.0
    low_snr_db: float = 20.0
    # A reference fit below this SNR is not a noisy capture but a wrong one (bench,
    # 2026-10-06: both channels read 0.021 V instead of 0.496 V, SNR -28 dB, on the first
    # point after a timebase change). Such a capture is kept on disk and taken again.
    bad_ref_snr_db: float = 6.0
    bad_capture_retries: int = 2


@dataclass
class PointResult:
    freq_hz: float
    h: complex                  # Vdut / Vref, skew-corrected
    gain_db: float
    phase_deg: float            # wrapped (-180, 180], skew-corrected
    vref_amp: float             # volts peak at the probe tip
    vdut_amp: float
    vdiv_ref: float
    vdiv_dut: float
    timebase: float
    n_avg: int
    snr_ref_db: float | None
    snr_dut_db: float | None
    flags: Flag
    duration_s: float
    skew_corr_deg: float = 0.0  # phase removed by the skew correction; raw = phase_deg + this
    retries: int = 0


@dataclass
class SkewCheck:
    """Result of the channel skew wizard (SPEC.md section 8.6)."""
    delay_s: float              # delta-t applied: snapped state, or the measured value
    measured_s: float
    snapped: bool
    gain_db: float              # gain mismatch DUT/ref
    freqs_hz: list[float]
    per_freq_delay_s: list[float]
    per_freq_gain_db: list[float]
    warnings: list[str]
    checked_at: str             # ISO time
    alignment_epoch: int        # digitizer epoch when checked

    def to_meta(self) -> dict:
        return asdict(self)


@dataclass
class WaveformPair:
    freq_hz: float
    t: Any                      # numpy arrays; Any keeps this module numpy-free
    ref_v: Any
    dut_v: Any
    ref_fit: Any = None
    dut_fit: Any = None


@dataclass
class LogEntry:
    level: str                  # "info" | "warn" | "error"
    text: str
    time: str = ""


@dataclass
class SweepResult:
    config: dict                # full snapshot of all configs
    points: list[PointResult]   # sorted by frequency
    meta: dict                  # app version, timestamps, IDNs, aborted flag, skew check


# ------------------------------------------------------------------ (de)serialisation
def to_jsonable(obj: Any) -> Any:
    """Dataclasses, enums, complex numbers and tuples -> plain JSON types."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Flag):
        return obj.to_text()
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, complex):
        return [obj.real, obj.imag]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def _coerce(cls, name: str, value: Any, default: Any) -> Any:
    try:
        if isinstance(default, enum.Enum):
            return type(default)(value)
        if isinstance(default, bool):
            return bool(value)
        if isinstance(default, int) and not isinstance(default, bool):
            return int(value)
        if isinstance(default, float):
            return float(value)
        if isinstance(default, tuple):
            return tuple(float(x) for x in value)
        if isinstance(default, dict):
            return {int(k): float(v) for k, v in dict(value).items()}
        if isinstance(default, str):
            return str(value)
    except (TypeError, ValueError):
        return default
    return value


def from_dict(cls, data: dict | None):
    """Build a config dataclass from a dict: unknown keys ignored, missing or bad
    keys take defaults. Never raises on an old or damaged file (SPEC.md section 11)."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in fields(cls):
        if f.name in data:
            setattr(obj, f.name, _coerce(cls, f.name, data[f.name], getattr(obj, f.name)))
    return obj


def config_snapshot(sweep: SweepConfig, stim: StimulusConfig, scope: ScopeConfig,
                    meas: MeasureSettings) -> dict:
    return {"sweep": to_jsonable(sweep), "stimulus": to_jsonable(stim),
            "scope": to_jsonable(scope), "measure": to_jsonable(meas)}
