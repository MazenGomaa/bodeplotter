"""Simulation mode with the circuits added for the analysis and the markers (measure/theory.py):
each one is swept by the simulated instruments and comes out as its formula says."""
import math

import pytest

from bodeplot.gui.main_window import MainWindow
from bodeplot.io.settings import AppSettings
from bodeplot.measure import theory
from bodeplot.models import EngineState, SweepConfig, SweepType

NEW = ("rlc_lpf", "rc_shelf", "wide_bpf", "butter_lpf", "cheby_lpf", "two_res", "crystal", "amp", "loop3")


@pytest.mark.parametrize("name", NEW)
def test_a_simulated_sweep_of_the_circuit_follows_its_formula(name, qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    sim = {"preset": name, "params": {}, "noise_vrms": 1e-4, "latency_ms": 0.0}
    win = MainWindow(simulate=True, settings=AppSettings(simulate=True, sim=sim), sim_seed=7)
    win.interactive = False
    qtbot.addWidget(win)
    win.show()
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.toggle_connection()
    qtbot.waitUntil(lambda: win.info.connected, timeout=5000)
    p = win.config.preset()
    p.sweep = SweepConfig(SweepType.LOG, 100.0, 2e6, 4)
    p.measure.settle_ms, p.measure.settle_cycles = 0.0, 0.0
    win.config.set_preset(p)
    with qtbot.waitSignal(win.engine.finished, timeout=60000):
        assert win.start_sweep()
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)
    tf = theory.build(name, {k: v[0] for k, v in theory.PARAMS[name].items()})
    points = win.result.points
    assert len(points) > 10
    checked = 0
    for pt in points:
        want = 20 * math.log10(abs(tf.h(pt.freq_hz)))
        if want > -40.0:                                # below that the simulated scope's noise takes over
            assert pt.gain_db == pytest.approx(want, abs=0.5), "%s at %g Hz" % (name, pt.freq_hz)
            checked += 1
    assert checked >= 5
    win.docks["dock_analysis"].raise_()
    win.analysis_panel.analyse()                        # the analysis takes whatever the sweep gave
    assert win.analysis_panel.rows() and not win.analysis_panel.stale()
    win.close()
