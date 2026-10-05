import json
import math

import pytest

from bodeplot.drivers.mock import SimulatedDUT
from bodeplot.io import export_csv, export_image, export_touchstone, presets, settings
from bodeplot.models import (Flag, MeasureSettings, Method, ScopeConfig, StimulusConfig, SweepConfig,
                             SweepType)
from bodeplot.sweep.core import SweepRunner


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg"


@pytest.fixture
def result(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=50, skew_state=2)
    return SweepRunner(session, SweepConfig(SweepType.LOG, 100.0, 1e6, 6), StimulusConfig(),
                       ScopeConfig(), MeasureSettings(), sleep=no_sleep).run()


@pytest.fixture
def unchecked_result(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=51, skew_state=2, checked=False)
    return SweepRunner(session, SweepConfig(SweepType.LOG, 100.0, 1e6, 3), StimulusConfig(),
                       ScopeConfig(), MeasureSettings(), sleep=no_sleep).run()


# ------------------------------------------------------------------ CSV
def test_csv_round_trip(tmp_path, result):
    result.points[3].flags |= Flag.LOW_SNR | Flag.REMEASURED
    path = export_csv.write_csv(tmp_path / "sweep.csv", result)
    back = export_csv.load_csv(path)
    assert len(back.points) == len(result.points)
    for a, b in zip(result.points, back.points):
        for name in ("freq_hz", "gain_db", "phase_deg", "vref_amp", "vdut_amp", "vdiv_ref", "vdiv_dut",
                     "timebase", "snr_ref_db", "snr_dut_db", "skew_corr_deg"):
            assert getattr(b, name) == pytest.approx(getattr(a, name), rel=1e-12, abs=1e-15), name
        assert b.h == pytest.approx(a.h, rel=1e-12)
        assert b.n_avg == a.n_avg and b.flags == a.flags
    assert back.config == json.loads(json.dumps(result.config))
    assert back.meta["source_idn"] == result.meta["source_idn"]
    assert back.meta["skew"]["delay_s"] == result.meta["skew"]["delay_s"]
    assert export_csv.skew_from_meta(back.meta).snapped is True


def test_csv_header_columns_and_skew_lines(tmp_path, result, unchecked_result):
    text = export_csv.write_csv(tmp_path / "a.csv", result).read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# bodeplot_csv: 1"
    assert "# skew: checked" in lines
    assert "# skew_delay_ns: 2.1500" in lines and "# skew_snapped: yes" in lines
    assert any(l.startswith("# skew_checked_at: 20") for l in lines)
    assert any(l.startswith("# app_version:") for l in lines)
    header = next(l for l in lines if not l.startswith("#"))
    assert header.split(",") == export_csv.COLUMNS
    assert "phase_unwrapped_deg" in header and "skew_corr_deg" in header

    text = export_csv.write_csv(tmp_path / "b.csv", unchecked_result).read_text(encoding="utf-8")
    assert "# skew: not checked" in text
    back = export_csv.load_csv(tmp_path / "b.csv")
    assert all(p.flags & Flag.SKEW_UNCHECKED for p in back.points)
    assert back.meta["skew"] is None


def test_csv_loader_tolerates_a_minimal_file(tmp_path):
    p = tmp_path / "old.csv"
    p.write_text("freq_hz,gain_db,phase_deg\n100,-1.0,-10\n1000,-3.0,-45\n", encoding="utf-8")
    back = export_csv.load_csv(p)
    assert [q.freq_hz for q in back.points] == [100.0, 1000.0]
    assert back.points[1].gain_db == -3.0 and back.points[1].flags == Flag.NONE
    assert math.isnan(back.points[0].h.real) and back.config == {}


# ------------------------------------------------------------------ Touchstone
def test_touchstone(tmp_path, result, unchecked_result):
    path = export_touchstone.write_touchstone(tmp_path / "sweep.s2p", result)
    text = path.read_text(encoding="utf-8")
    assert "# Hz S RI R 50" in text.splitlines()
    assert "NOT a calibrated S-parameter measurement" in text
    assert "! skew_delay_ns: 2.1500" in text and "! skew_checked_at: 20" in text
    s21 = export_touchstone.read_touchstone_s21(path)
    assert len(s21) == len(result.points)
    for (f, h), p in zip(s21, result.points):
        assert f == pytest.approx(p.freq_hz, rel=1e-8) and h == pytest.approx(p.h, rel=1e-7)
    for line in text.splitlines():
        if line and line[0] not in "!#":
            v = line.split()
            assert len(v) == 9 and v[1:3] == ["0", "0"] and v[5:] == ["0", "0", "0", "0"]
    text = export_touchstone.write_touchstone(tmp_path / "u.s2p", unchecked_result).read_text("utf-8")
    assert "! skew: not checked" in text


# ------------------------------------------------------------------ images
@pytest.mark.parametrize("ext, magic", [("png", b"\x89PNG"), ("svg", b"<?xml"), ("pdf", b"%PDF")])
def test_image_files_are_created_and_valid(tmp_path, result, ext, magic):
    result.points[2].flags |= Flag.CLIPPED
    path = export_image.write_image(tmp_path / ("plot." + ext), result,
                                    export_image.ImageOptions(title="RC low-pass", dpi=80, unwrap=True))
    data = path.read_bytes()
    assert data.startswith(magic) and len(data) > 1000


def test_image_rejects_unknown_format(tmp_path, result):
    with pytest.raises(ValueError):
        export_image.write_image(tmp_path / "plot.bmp", result)


# ------------------------------------------------------------------ presets and settings
def test_preset_save_load_delete(cfg_dir):
    p = presets.Preset(SweepConfig(SweepType.LINEAR, 10.0, 5e3, n_points=33, descending=True),
                       StimulusConfig(2, 0.5, 0.1, "50"),
                       ScopeConfig(2, 1, {1: 1.0, 2: 10.0}, "AC", True, 7.0, 30),
                       MeasureSettings(Method.BUILTIN, 4, 80.0, 5.0, (0.5, 0.9), 2, 0.2, 3.0))
    presets.save_preset("my filter", p)
    assert presets.list_presets() == ["my filter"]
    back = presets.load_preset("my filter")
    assert back == p
    data = json.loads(presets.preset_path("my filter").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "resource" not in json.dumps(data)               # no connection info in a preset
    assert presets.delete_preset("my filter") and presets.list_presets() == []
    assert presets.delete_preset("my filter") is False


def test_preset_old_schema_with_missing_and_bad_keys_loads_with_defaults(cfg_dir):
    path = presets.preset_path("old")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"sweep": {"start_hz": 123.0, "sweep_type": "nonsense", "future_key": 1},
                                "stimulus": "not a dict", "unknown_section": {}}), encoding="utf-8")
    p = presets.load_preset("old")
    assert p.sweep.start_hz == 123.0
    assert p.sweep.sweep_type is SweepType.LOG and p.sweep.stop_hz == SweepConfig().stop_hz
    assert p.stimulus == StimulusConfig() and p.scope == ScopeConfig() and p.measure == MeasureSettings()
    assert presets.load_preset("does not exist") == presets.Preset()
    presets.preset_path("broken").write_text("{ not json", encoding="utf-8")
    assert presets.load_preset("broken") == presets.Preset()


def test_preset_name_is_made_safe(cfg_dir):
    assert presets.preset_path("a/b:c").name == "a_b_c.json"
    with pytest.raises(ValueError):
        presets.preset_path("  ")


def test_settings_round_trip_and_defaults(cfg_dir):
    s = settings.load_settings()
    assert s.backend == "py" and s.simulate is False        # free backend is the default
    s.backend, s.source_resource, s.simulate, s.last_preset = "ivi", "USB0::1::2::X::INSTR", True, "p"
    settings.save_settings(s)
    back = settings.load_settings()
    assert (back.backend, back.source_resource, back.simulate, back.last_preset) == \
        ("ivi", "USB0::1::2::X::INSTR", True, "p")
    assert json.loads(settings.settings_path().read_text(encoding="utf-8"))["schema_version"] == 1
    settings.settings_path().write_text(json.dumps({"backend": "nope", "simulate": 1, "extra": 5}),
                                        encoding="utf-8")
    odd = settings.load_settings()
    assert odd.backend == "py" and odd.simulate is True
    settings.settings_path().write_text("garbage", encoding="utf-8")
    assert settings.load_settings() == settings.AppSettings()
