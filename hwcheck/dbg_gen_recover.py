"""Troubleshooting: generator stopped answering after the undocumented *OPC?
probe. Try USB-level recovery, least invasive first. No SCPI except *IDN?.

  1. USBTMC class request INITIATE_CLEAR (5) + CHECK_CLEAR_STATUS (6)
     (USBTMC 1.0 spec, 4.2.1.6/4.2.1.7), then clear halt on both endpoints.
  2. USB port reset (libusb reset_device).
After each step a fresh pyvisa session tries *IDN?.
"""
import sys
import time

import libusb_package
import usb.core
import usb.util

import scpi
from common import GEN_PID, GEN_VID, find_resource, open_inst, open_rm


def try_idn(label):
    rm = open_rm("@py")
    try:
        res = find_resource(rm, GEN_VID, GEN_PID)
        if res is None:
            print(f"[{label}] resource not listed")
            return False
        g = open_inst(rm, res, timeout_ms=3000)
        try:
            print(f"[{label}] IDN:", g.query(scpi.IDN).strip())
            print(f"[{label}] OUT1/OUT2:", g.query(scpi.G_OUT.format(n=1) + "?").strip(),
                  g.query(scpi.G_OUT.format(n=2) + "?").strip())
            return True
        finally:
            g.close()
    except Exception as e:
        print(f"[{label}] FAILED: {type(e).__name__}: {e}")
        return False
    finally:
        rm.close()


def usbtmc_clear():
    dev = libusb_package.find(idVendor=GEN_VID, idProduct=GEN_PID)
    dev.set_configuration()
    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)]
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    try:
        bm = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS,
                                         usb.util.CTRL_RECIPIENT_INTERFACE)
        r = dev.ctrl_transfer(bm, 5, 0, intf.bInterfaceNumber, 1, timeout=2000)
        print("INITIATE_CLEAR ->", list(r))
        for _ in range(20):
            r = dev.ctrl_transfer(bm, 6, 0, intf.bInterfaceNumber, 2, timeout=2000)
            print("CHECK_CLEAR_STATUS ->", list(r))
            if r[0] != 2:       # 2 = STATUS_PENDING
                break
            time.sleep(0.1)
        for ep in intf:
            try:
                dev.clear_halt(ep.bEndpointAddress)
                print("clear_halt", hex(ep.bEndpointAddress), "ok")
            except Exception as e:
                print("clear_halt", hex(ep.bEndpointAddress), "failed:", e)
    finally:
        usb.util.release_interface(dev, intf.bInterfaceNumber)
        usb.util.dispose_resources(dev)


def port_reset():
    dev = libusb_package.find(idVendor=GEN_VID, idProduct=GEN_PID)
    dev.reset()
    usb.util.dispose_resources(dev)
    print("port reset issued")
    time.sleep(3.0)


if try_idn("before"):
    sys.exit(0)
for name, fn in (("usbtmc_clear", usbtmc_clear), ("port_reset", port_reset)):
    try:
        fn()
    except Exception as e:
        print(f"{name} raised {type(e).__name__}: {e}")
    time.sleep(1.0)
    if try_idn("after " + name):
        sys.exit(0)
print("generator still not responding")
sys.exit(1)
