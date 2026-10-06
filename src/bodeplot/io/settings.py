"""Application settings: connections, backend, window state, last preset (SPEC.md section 11).

Every file carries "schema_version". Unknown keys are ignored, missing keys take
defaults, and a damaged file never crashes the app.
"""
from __future__ import annotations

import json
import logging
import os
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
    window_geometry: str = ""           # base64 of QByteArray
    window_state: str = ""
    sim: dict = field(default_factory=lambda: {"preset": "rc_lpf", "params": {}, "noise_vrms": 1e-4,
                                               "latency_ms": 5.0})
    last_config: dict = field(default_factory=dict)     # last-used sweep/stimulus/scope/measure

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
            elif isinstance(default, float):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    setattr(s, key, float(v))
            elif isinstance(default, str):
                setattr(s, key, v if isinstance(v, str) else default)
            elif isinstance(default, dict):
                setattr(s, key, v if isinstance(v, dict) else default)
        if s.backend not in BACKENDS:
            s.backend = DEFAULT_BACKEND
        if s.startup_mode not in STARTUP_MODES:
            s.startup_mode = "instruments"
        s.scope_min_gap_ms = min(max(s.scope_min_gap_ms, SCOPE_MIN_GAP_MS[0]), SCOPE_MIN_GAP_MS[1])
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
