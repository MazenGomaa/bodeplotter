"""JSON presets: SweepConfig, StimulusConfig, ScopeConfig, MeasureSettings. No connection info
(SPEC.md section 11)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models import (MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, config_snapshot,
                      from_dict)
from ..units import fmt_si
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


# (section, key) -> (name as the Configuration panel shows it, unit)
LABELS = {
    ("sweep", "sweep_type"): ("Type", ""), ("sweep", "start_hz"): ("Start", "Hz"), ("sweep", "stop_hz"): ("Stop", "Hz"),
    ("sweep", "points_per_decade"): ("Points / decade", ""), ("sweep", "n_points"): ("Points", ""),
    ("sweep", "descending"): ("Descending", ""),
    ("stimulus", "gen_channel"): ("Generator channel", ""), ("stimulus", "amp_vpp"): ("Amplitude", "Vpp"),
    ("stimulus", "offset_v"): ("Offset", "V"), ("stimulus", "load"): ("Load", ""),
    ("scope", "ref_channel"): ("Reference channel", ""), ("scope", "dut_channel"): ("DUT channel", ""),
    ("scope", "probe_atten"): ("Probes", ""), ("scope", "coupling"): ("Coupling", ""),
    ("scope", "bw_limit"): ("20 MHz bandwidth limit", ""), ("scope", "target_cycles"): ("Target cycles", ""),
    ("measure", "method"): ("Method", ""), ("measure", "averages"): ("Averages", ""),
    ("measure", "settle_ms"): ("Settle time", "ms"), ("measure", "settle_cycles"): ("Settle cycles", ""),
}
WHAT_A_PRESET_HOLDS = ("A preset stores the Configuration panel (sweep, stimulus, scope, measurement) and nothing "
                       "else: not the simulated circuit, not the traces, not the calibration.")


def _show(value, unit: str) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (int, float)):
        if unit == "ms":
            return "%g ms" % value
        return fmt_si(value, unit) if unit else "%g" % value
    if isinstance(value, dict):
        return ", ".join("CH%s %gX" % (k, v) for k, v in sorted(value.items()))
    return str(value)


def describe_changes(before: Preset, after: Preset) -> list[str]:
    """What differs between two sets of settings, one line per setting, in the words of the
    Configuration panel: 'Start 200 Hz → 50 Hz'."""
    a, b = before.to_dict(), after.to_dict()
    out = []
    for section in ("sweep", "stimulus", "scope", "measure"):
        for key, new in b.get(section, {}).items():
            old = a.get(section, {}).get(key)
            if old == new:
                continue
            name, unit = LABELS.get((section, key), (key, ""))
            out.append("%s %s → %s" % (name, _show(old, unit), _show(new, unit)))
    return out
