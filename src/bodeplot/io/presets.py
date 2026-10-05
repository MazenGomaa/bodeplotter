"""JSON presets: SweepConfig, StimulusConfig, ScopeConfig, MeasureSettings. No connection info
(SPEC.md section 11)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models import (MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, config_snapshot,
                      from_dict)
from .settings import SCHEMA_VERSION, config_dir, read_json, write_json


@dataclass
class Preset:
    sweep: SweepConfig = field(default_factory=SweepConfig)
    stimulus: StimulusConfig = field(default_factory=StimulusConfig)
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    measure: MeasureSettings = field(default_factory=MeasureSettings)

    def to_dict(self) -> dict:
        d = config_snapshot(self.sweep, self.stimulus, self.scope, self.measure)
        d["schema_version"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> "Preset":
        data = data if isinstance(data, dict) else {}
        return cls(from_dict(SweepConfig, data.get("sweep")),
                   from_dict(StimulusConfig, data.get("stimulus")),
                   from_dict(ScopeConfig, data.get("scope")),
                   from_dict(MeasureSettings, data.get("measure")))


def presets_dir() -> Path:
    return config_dir() / "presets"


def _safe(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9 _.\-]", "_", name).strip(" .")
    if not clean:
        raise ValueError("preset name is empty")
    return clean


def preset_path(name: str) -> Path:
    return presets_dir() / (_safe(name) + ".json")


def list_presets() -> list[str]:
    d = presets_dir()
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def save_preset(name: str, preset: Preset) -> Path:
    path = preset_path(name)
    write_json(path, preset.to_dict())
    return path


def load_preset(name: str) -> Preset:
    return Preset.from_dict(read_json(preset_path(name)))


def delete_preset(name: str) -> bool:
    try:
        preset_path(name).unlink()
        return True
    except FileNotFoundError:
        return False
