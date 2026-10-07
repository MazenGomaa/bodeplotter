"""Application settings: connections, backend, window state, last preset (SPEC.md section 11).

Every file carries "schema_version". Unknown keys are ignored, missing keys take
defaults, and a damaged file never crashes the app.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

from ..drivers.visa_util import BACKENDS, DEFAULT_BACKEND

log = logging.getLogger("bodeplot.io")
SCHEMA_VERSION = 1
APP = "bodeplot"


def config_dir() -> Path:
    override = os.environ.get("BODEPLOT_CONFIG_DIR")
    return Path(override) if override else Path(user_config_dir(APP, appauthor=False))


def read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("could not read %s: %s", path, e)
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)               # atomic: a crash cannot leave half a file


# What a plain start comes up in. "last" = whatever mode was selected when the app closed.
STARTUP_MODES = ("instruments", "simulation", "last")
SCOPE_MIN_GAP_MS = (100.0, 2000.0)      # 100 ms is the pacing proven on the bench; never below it
TOOLTIP_DELAY_MS = (0.0, 10000.0)
MARKER_KINDS = ("cutoff", "peak", "notch", "margins")   # as markers.KINDS; a test keeps the two equal
AUTO_KEEP_MAX = 6                       # with the live sweep, seven of the eight trace colours
PANELS = ("dock_config", "dock_waveform", "dock_traces", "dock_markers", "dock_log")
SKEW_DEFAULTS = (10e6, 20e6, 3)         # check frequencies and captures per frequency (SPEC.md section 8.6)
SKEW_CAPTURES_MAX = 20
# Advanced measurement settings: stored key -> (lowest, highest, integer?). They override the
# matching fields of MeasureSettings for every sweep, whatever a preset holds.
ADVANCED = {"autorange_lo": (0.2, 0.9, False), "autorange_hi": (0.25, 0.95, False),
            "autorange_max_retries": (1, 10, True), "floor_fraction": (0.01, 0.5, False),
            "acquire_timeout_s": (1.0, 60.0, False), "low_snr_db": (0.0, 60.0, False),
            "bad_capture_retries": (0, 5, True)}


def measure_overrides(advanced) -> dict:
    """The stored advanced settings as keyword arguments for MeasureSettings: unknown keys
    and values that are not numbers are left out, numbers are limited to their range, and
    the auto-range pair is used only when it is a pair with the lower value below the upper."""
    out: dict = {}
    if not isinstance(advanced, dict):
        return out
    clean = {}
    for key, (lo, hi, whole) in ADVANCED.items():
        v = advanced.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            continue
        v = min(max(float(v), lo), hi)
        clean[key] = int(round(v)) if whole else v
    if "autorange_lo" in clean and "autorange_hi" in clean and clean["autorange_lo"] < clean["autorange_hi"]:
        out["autorange_target"] = (clean["autorange_lo"], clean["autorange_hi"])
    for key in ("autorange_max_retries", "floor_fraction", "acquire_timeout_s", "low_snr_db", "bad_capture_retries"):
        if key in clean:
            out[key] = clean[key]
    return out


@dataclass
class AppSettings:
    backend: str = DEFAULT_BACKEND
    source_resource: str = ""
    digitizer_resource: str = ""
    simulate: bool = False
    startup_mode: str = "instruments"
    # Minimum pause after a timebase or V/div change on the real scope, on top of *OPC?
    scope_min_gap_ms: float = 100.0
    last_preset: str = ""
    unwrap_phase: bool = False
    vertical_unit: str = "db"           # "db" | "v" | "pct" (gui/bode_plot.py UNITS)
    markers: list = field(default_factory=list)     # the automatic markers switched on (MARKER_KINDS)
    marker_values: bool = True          # write the values next to each marker on the plot (off: its name only)
    marker_color: str = ""              # "#rrggbb" for the markers of the plot; "" = the theme's
    window_geometry: str = ""           # base64 of QByteArray
    window_state: str = ""
    sim: dict = field(default_factory=lambda: {"preset": "rc_lpf", "params": {}, "noise_vrms": 1e-4,
                                               "latency_ms": 5.0})
    last_config: dict = field(default_factory=dict)     # last-used sweep/stimulus/scope/measure
    # ---- behaviour (user request 2026-10-07)
    skew_wizard_on_connect: bool = False    # the pop-up on every connect was removed on 2026-10-06; this brings it back
    tooltips: bool = True                   # every option explains itself ...
    tooltip_delay_ms: float = 3000.0        # ... after the mouse has rested this long
    auto_keep_sweeps: int = 0               # keep this many previous sweeps as traces; 0 = off
    export_folder: str = ""                 # fixed folder for Export and Load CSV; "" = the folder used last
    last_folder: str = ""
    grid_color: str = ""                    # "#rrggbb" for the plots' grid and axis lines; "" = the theme's
    startup_panels: dict = field(default_factory=lambda: {name: True for name in PANELS})
    debug_logging: bool = False             # log every instrument command, as --debug does
    advanced: dict = field(default_factory=dict)        # see ADVANCED and measure_overrides()
    # ---- the skew check's own settings, edited in the wizard
    skew_freq_lo_hz: float = SKEW_DEFAULTS[0]
    skew_freq_hi_hz: float = SKEW_DEFAULTS[1]
    skew_captures: int = SKEW_DEFAULTS[2]

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["schema_version"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        s = cls()
        if not isinstance(data, dict):
            return s
        for key, default in cls().__dict__.items():
            if key not in data:
                continue
            v = data[key]
            if isinstance(default, bool):
                setattr(s, key, bool(v))
            elif isinstance(default, int):
                if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
                    setattr(s, key, int(v))
            elif isinstance(default, float):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    setattr(s, key, float(v))
            elif isinstance(default, str):
                setattr(s, key, v if isinstance(v, str) else default)
            elif isinstance(default, dict):
                setattr(s, key, v if isinstance(v, dict) else default)
            elif isinstance(default, list):
                setattr(s, key, list(v) if isinstance(v, list) else default)
        if s.backend not in BACKENDS:
            s.backend = DEFAULT_BACKEND
        if s.startup_mode not in STARTUP_MODES:
            s.startup_mode = "instruments"
        s.scope_min_gap_ms = min(max(s.scope_min_gap_ms, SCOPE_MIN_GAP_MS[0]), SCOPE_MIN_GAP_MS[1])
        s.tooltip_delay_ms = min(max(s.tooltip_delay_ms, TOOLTIP_DELAY_MS[0]), TOOLTIP_DELAY_MS[1])
        s.auto_keep_sweeps = min(max(s.auto_keep_sweeps, 0), AUTO_KEEP_MAX)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", s.grid_color):
            s.grid_color = ""
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", s.marker_color):
            s.marker_color = ""
        s.startup_panels = {name: bool(s.startup_panels.get(name, True)) for name in PANELS}
        s.advanced = {k: v for k, v in s.advanced.items() if k in ADVANCED}
        if not (0 < s.skew_freq_lo_hz < s.skew_freq_hi_hz):
            s.skew_freq_lo_hz, s.skew_freq_hi_hz = SKEW_DEFAULTS[0], SKEW_DEFAULTS[1]
        s.skew_captures = min(max(s.skew_captures, 1), SKEW_CAPTURES_MAX)
        s.markers = [k for k in MARKER_KINDS if k in s.markers]
        return s


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> AppSettings:
    return AppSettings.from_dict(read_json(settings_path()))


def save_settings(s: AppSettings) -> None:
    try:
        write_json(settings_path(), s.to_dict())
    except OSError as e:
        log.warning("could not save settings: %s", e)
