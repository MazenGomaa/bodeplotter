"""USBTMC-level clear, done with pyusb while no VISA session is open.

pyvisa-py 0.8.1 answers inst.clear() on a USB INSTR with VI_ERROR_NSUP_OPER
(seen in dbg_gen_alive.py), so the class requests are sent directly:
INITIATE_CLEAR (bRequest 5) then CHECK_CLEAR_STATUS (bRequest 6) until not
pending, then clear halt on both bulk endpoints (USBTMC 1.0, 4.2.1.6-4.2.1.7).
This is a transport operation, not a SCPI command; it changes no instrument
setting.
"""
import time

import libusb_package
import usb.util


def usbtmc_clear(vid, pid, verbose=True):
    dev = libusb_package.find(idVendor=vid, idProduct=pid)
    if dev is None:
        raise RuntimeError(f"device {vid:04x}:{pid:04x} not found")
    dev.set_configuration()
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    try:
        bm = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS,
                                         usb.util.CTRL_RECIPIENT_INTERFACE)
        r = dev.ctrl_transfer(bm, 5, 0, intf.bInterfaceNumber, 1, timeout=2000)
        log = [("INITIATE_CLEAR", list(r))]
        for _ in range(20):
            r = dev.ctrl_transfer(bm, 6, 0, intf.bInterfaceNumber, 2, timeout=2000)
            log.append(("CHECK_CLEAR_STATUS", list(r)))
            if r[0] != 2:               # 2 = STATUS_PENDING
                break
            time.sleep(0.1)
        for ep in intf:
            try:
                dev.clear_halt(ep.bEndpointAddress)
                log.append(("clear_halt", hex(ep.bEndpointAddress)))
            except Exception as e:
                log.append(("clear_halt_failed", f"{hex(ep.bEndpointAddress)} {e}"))
    finally:
        usb.util.release_interface(dev, intf.bInterfaceNumber)
        usb.util.dispose_resources(dev)
    if verbose:
        print("usbtmc_clear:", log)
    return log
