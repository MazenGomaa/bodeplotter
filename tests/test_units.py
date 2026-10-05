import math

import pytest

from bodeplot.units import fmt_si, parse_si


@pytest.mark.parametrize("value, unit, text", [
    (20e6, "Hz", "20 MHz"), (1.5e3, "Hz", "1.5 kHz"), (50.0, "Hz", "50 Hz"), (1e6, "Hz", "1 MHz"),
    (15915.4943, "Hz", "15.9155 kHz"), (11301900.0, "Hz", "11.3019 MHz"), (0.02, "V", "20 mV"),
    (5e-4, "V", "500 µV"), (2.5e-8, "s", "25 ns"), (1e-12, "F", "1 pF"), (3e9, "Hz", "3 GHz"),
    (0.0, "Hz", "0 Hz"), (-2.15e-9, "s", "-2.15 ns"), (1000.0, "", "1 k"), (999.9999, "Hz", "1 kHz"),
    (20.0, "V", "20 V")])
def test_fmt_si(value, unit, text):
    assert fmt_si(value, unit) == text


def test_fmt_si_edge_cases():
    assert fmt_si(None, "Hz") == "" and fmt_si(float("nan"), "Hz") == ""
    assert "e" in fmt_si(1e15, "Hz")                     # beyond the table: plain number, no crash
    assert fmt_si(0.0123456789, "V", 3) == "12.3 mV"


@pytest.mark.parametrize("text, value", [
    ("20M", 20e6), ("20 MHz", 20e6), ("20MHz", 20e6), ("1.5k", 1500.0), ("1.5 kHz", 1500.0), ("1K", 1e3),
    ("50", 50.0), ("50 Hz", 50.0), ("2e7", 2e7), ("2E7 Hz", 2e7), ("20meg", 20e6), ("100n", 1e-7),
    ("100 n", 1e-7), ("4.7u", 4.7e-6), ("4.7µ", 4.7e-6), ("1m", 1e-3), ("3G", 3e9), (".5k", 500.0),
    ("  10 k  ", 1e4), ("-2.15n", -2.15e-9)])
def test_parse_si(text, value):
    assert parse_si(text, "Hz") == pytest.approx(value, rel=1e-12)


def test_m_is_milli_and_capital_m_is_mega():
    assert parse_si("20m", "Hz") == pytest.approx(0.02)
    assert parse_si("20M", "Hz") == 20e6


@pytest.mark.parametrize("text", ["", "abc", "20x", "k", "1.2.3", "20 MHzz", "--5"])
def test_parse_si_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_si(text, "Hz")


def test_round_trip():
    for exp in range(-11, 10):
        for mant in (1.0, 2.5, 4.7, 9.99):
            v = mant * 10 ** exp
            assert parse_si(fmt_si(v, "Hz", 9), "Hz") == pytest.approx(v, rel=1e-8)
            assert math.isfinite(parse_si(fmt_si(v, "Hz"), "Hz"))
