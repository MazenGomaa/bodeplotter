"""Message transport under the real drivers.

A driver talks to a Transport, never to pyvisa directly, so the driver logic (reply
validation, resync, single-shot acquisition, pacing) is tested against simulated
instruments (tests/fakes.py) with no hardware.

VisaTransport is the real one: pyvisa, default backend pyvisa-py. It never runs anything
that needs administrator rights: a device clear is the USBTMC class request, sent through
pyusb when the backend has no clear of its own. Restarting the Windows device node
(pnputil) is deliberately not available here; it is documented in HW_REPORT.md only.
"""
from __future__ import annotations

import time

from . import visa_util


class TransportError(Exception):
    """A write or read failed or timed out."""


class Transport:
    """Interface. write() sends one command; read() returns one raw reply."""

    def write(self, cmd: str) -> None:
        raise NotImplementedError

    def read(self) -> bytes:
        raise NotImplementedError

    def clear(self) -> str:
        """Device clear (USBTMC INITIATE_CLEAR). Returns how it was done."""
        raise NotImplementedError

    def set_timeout(self, seconds: float) -> None:
        raise NotImplementedError

    def get_timeout(self) -> float:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def usbtmc_clear(vid: int, pid: int) -> list:
    """USBTMC clear with pyusb while no VISA session is open: INITIATE_CLEAR (bRequest 5),
    CHECK_CLEAR_STATUS (bRequest 6) until not pending, clear halt on the bulk endpoints
    (USBTMC 1.0, 4.2.1.6 and 4.2.1.7). A transport operation: it changes no instrument
    setting. pyvisa-py 0.8 has no clear() for USB INSTR, hence this."""
    import libusb_package
    import usb.util

    dev = libusb_package.find(idVendor=vid, idProduct=pid)
    if dev is None:
        raise TransportError(f"USB device {vid:04x}:{pid:04x} not found")
    dev.set_configuration()
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    log = []
    try:
        bm = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS,
                                         usb.util.CTRL_RECIPIENT_INTERFACE)
        r = dev.ctrl_transfer(bm, 5, 0, intf.bInterfaceNumber, 1, timeout=2000)
        log.append(("INITIATE_CLEAR", list(r)))
        for _ in range(20):
            r = dev.ctrl_transfer(bm, 6, 0, intf.bInterfaceNumber, 2, timeout=2000)
            log.append(("CHECK_CLEAR_STATUS", list(r)))
            if r[0] != 2:               # 2 = STATUS_PENDING
                break
            time.sleep(0.1)
        for ep in intf:
            try:
                dev.clear_halt(ep.bEndpointAddress)
            except Exception as e:      # reported, not fatal
                log.append(("clear_halt_failed", f"{hex(ep.bEndpointAddress)} {e}"))
    finally:
        usb.util.release_interface(dev, intf.bInterfaceNumber)
        usb.util.dispose_resources(dev)
    return log


class VisaTransport(Transport):
    def __init__(self, resource: str, backend: str = visa_util.DEFAULT_BACKEND, timeout_s: float = 5.0):
        self.resource, self.backend = resource, backend
        self._timeout_s = timeout_s
        self.rm = visa_util.open_resource_manager(backend)
        self.inst = None
        self._open()

    def _open(self) -> None:
        try:
            self.inst = self.rm.open_resource(self.resource)
        except Exception as e:
            raise TransportError(f"could not open {self.resource}: {e}") from e
        self.inst.timeout = int(self._timeout_s * 1000)
        self.inst.write_termination = "\n"      # both manuals: a command ends with <NL>
        # scope replies end CR LF (stripped by the driver); generator replies have no
        # terminator at all (HW_REPORT.md G1), so neither may wait for one
        self.inst.read_termination = None

    def write(self, cmd: str) -> None:
        try:
            self.inst.write(cmd)
        except Exception as e:                  # VisaIOError, or ValueError from pyvisa-py's USB layer
            raise TransportError(f"write {cmd!r}: {e}") from e

    def read(self) -> bytes:
        try:
            return bytes(self.inst.read_raw())
        except Exception as e:
            raise TransportError(f"read: {e}") from e

    def set_timeout(self, seconds: float) -> None:
        self._timeout_s = seconds
        if self.inst is not None:
            self.inst.timeout = int(seconds * 1000)

    def get_timeout(self) -> float:
        return self._timeout_s

    def clear(self) -> str:
        try:
            self.inst.clear()
            return "backend clear"
        except Exception as first:
            ids = visa_util.usb_ids(self.resource)
            if ids is None:
                raise TransportError(f"device clear not possible on {self.resource}: {first}") from first
            try:
                self.inst.close()
            except Exception:
                pass
            try:
                usbtmc_clear(ids[0], ids[1])
            except TransportError:
                raise
            except Exception as e:
                raise TransportError(f"USBTMC clear failed: {e}") from e
            finally:
                self._open()
            return "USBTMC INITIATE_CLEAR via pyusb"

    def close(self) -> None:
        for obj in (self.inst, self.rm):
            try:
                if obj is not None:
                    obj.close()
            except Exception:                   # closing must not raise
                pass
        self.inst = None
