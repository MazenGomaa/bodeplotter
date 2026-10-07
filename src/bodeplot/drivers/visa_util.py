"""VISA resource discovery and backend selection (SPEC.md sections 3 and 5).

Default backend is pyvisa-py ("py"): free, and the one the I/O layer was tested on.
"ivi" needs a vendor VISA library the user already has a licence for.
pyvisa is imported lazily so simulation mode and the tests need no VISA at all.
"""
from __future__ import annotations

BACKENDS = ("py", "auto", "ivi")
DEFAULT_BACKEND = "py"


def _candidates(backend: str) -> list[str]:
    if backend == "py":
        return ["@py"]
    if backend == "ivi":
        return [""]
    if backend == "auto":
        return ["@py", ""]          # the free backend first
    raise ValueError(f"unknown backend {backend!r}")


NO_HARDWARE_ENV = "BODEPLOT_NO_HARDWARE"


def open_resource_manager(backend: str = DEFAULT_BACKEND):
    import os
    if os.environ.get(NO_HARDWARE_ENV):
        # set by the test suite: a test must never reach a real instrument, whatever it does
        raise RuntimeError("instrument access is disabled (%s is set)" % NO_HARDWARE_ENV)
    import pyvisa
    last = None
    for name in _candidates(backend):
        try:
            return pyvisa.ResourceManager(name)
        except Exception as e:      # missing library, missing backend
            last = e
    raise RuntimeError(f"no VISA backend available for {backend!r}: {last}")


def usb_ids(resource: str) -> tuple[int, int, str] | None:
    """(vid, pid, serial) from a USB INSTR resource string of either backend:
    'USB0::22102::2098::SER::0::INSTR' or 'USB0::0x5656::0x0832::SER::INSTR'."""
    parts = resource.split("::")
    if len(parts) < 4 or not parts[0].upper().startswith("USB"):
        return None
    try:
        return int(parts[1], 0), int(parts[2], 0), parts[3]
    except ValueError:
        return None


def discover(backend: str = DEFAULT_BACKEND) -> list[str]:
    import warnings
    rm = open_resource_manager(backend)
    try:
        with warnings.catch_warnings():
            # pyvisa-py also looks for LAN instruments and, at every start, prints a hint that
            # this needs the zeroconf package. The instruments are on USB (LAN was dropped by
            # the user), so the hint is noise; every other warning still comes through.
            warnings.filterwarnings("ignore", message=r".*requires the zeroconf package.*", category=UserWarning)
            return list(rm.list_resources("?*"))
    finally:
        rm.close()
