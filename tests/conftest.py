import os
import sys
from pathlib import Path

# Run the GUI tests without a display, and find the package without installing it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# No test may reach a real instrument: every VISA open raises while this is set.
os.environ["BODEPLOT_NO_HARDWARE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from bodeplot.drivers.mock import SimulatedDUT
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig
from bodeplot.sweep.core import Session, run_skew_check

NO_SLEEP = lambda s: None       # noqa: E731


@pytest.fixture
def no_sleep():
    return NO_SLEEP


@pytest.fixture
def make_session():
    """Factory for an opened simulated session; closes them all afterwards."""
    made = []

    def _make(dut: SimulatedDUT | None = None, seed: int = 1, skew_state: int | None = None,
              checked: bool = True, **kw) -> Session:
        s = Session.simulated_session(dut, seed=seed, **kw)
        if skew_state is not None:
            s.digitizer.force_skew_state(skew_state)
        if checked:
            s.accept_skew(run_skew_check(s, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                                         sleep=NO_SLEEP))
        made.append(s)
        return s

    yield _make
    for s in made:
        s.close()
