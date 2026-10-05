"""Troubleshooting, part 6. USBTMC INITIATE_CLEAR did not bring the scope's
replies back in step (dbg_resync.py). Try, in order, checking after each:
  a) two queries written back to back, then two reads
  b) one query, then reading until the reply is the expected one, then stop
  c) USBTMC INITIATE_ABORT_BULK_IN (bRequest 3) on the bulk-IN endpoint
  d) USB port reset (libusb reset_device)
Generator untouched. Only *IDN?, *OPC?, :SYSTem:ERRor? are sent."""
import sys
import time

import libusb_package
import usb.util

import scpi
from common import SCOPE_PID, SCOPE_VID, find_resource, open_inst, open_rm

PAIRS = [(scpi.IDN, "UNI-T"), (scpi.OPC_Q, "1"), (scpi.S_ERR_Q, "0,"), (scpi.IDN, "UNI-T"),
         (scpi.OPC_Q, "1")]


def session():
    rm = open_rm("@py")
    s = open_inst(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), timeout_ms=2000)
    return rm, s


def check(label):
    rm, s = session()
    ok = 0
    try:
        got = []
        for cmd, pre in PAIRS:
            r = s.query(cmd).strip()
            ok += r.startswith(pre)
            got.append(r[:14])
        print(f"  [{label}] replies {got} -> {'IN STEP' if ok == len(PAIRS) else 'out of step'}")
    except Exception as e:
        print(f"  [{label}] check failed: {type(e).__name__}: {e}")
        return False
    finally:
        s.close()
        rm.close()
    return ok == len(PAIRS)


def step_a():
    rm, s = session()
    try:
        s.write(scpi.IDN)
        s.write(scpi.OPC_Q)
        print("  a) reads after two writes:", [s.read().strip()[:14] for _ in range(3)])
    finally:
        s.close()
        rm.close()


def step_b():
    rm, s = session()
    try:
        s.write(scpi.IDN)
        seen = []
        for _ in range(4):
            r = s.read().strip()
            seen.append(r[:14])
            if r.startswith("UNI-T"):
                break
        print("  b) reads until expected:", seen)
    finally:
        s.close()
        rm.close()


def step_c():
    dev = libusb_package.find(idVendor=SCOPE_VID, idProduct=SCOPE_PID)
    dev.set_configuration()
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    try:
        ep_in = next(ep.bEndpointAddress for ep in intf if ep.bEndpointAddress & 0x80)
        bm = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS,
                                         usb.util.CTRL_RECIPIENT_ENDPOINT)
        r = dev.ctrl_transfer(bm, 3, 0, ep_in, 2, timeout=2000)   # INITIATE_ABORT_BULK_IN
        print("  c) INITIATE_ABORT_BULK_IN ->", list(r))
        r = dev.ctrl_transfer(bm, 4, 0, ep_in, 8, timeout=2000)   # CHECK_ABORT_BULK_IN_STATUS
        print("  c) CHECK_ABORT_BULK_IN_STATUS ->", list(r))
    except Exception as e:
        print("  c) raised", type(e).__name__, e)
    finally:
        usb.util.release_interface(dev, intf.bInterfaceNumber)
        usb.util.dispose_resources(dev)


def step_d():
    dev = libusb_package.find(idVendor=SCOPE_VID, idProduct=SCOPE_PID)
    try:
        dev.reset()
        print("  d) port reset issued")
    except Exception as e:
        print("  d) raised", type(e).__name__, e)
    usb.util.dispose_resources(dev)
    time.sleep(4.0)


if check("start"):
    sys.exit(0)
for name, fn in (("a", step_a), ("b", step_b), ("c", step_c), ("d", step_d)):
    fn()
    time.sleep(0.5)
    if check("after " + name):
        print("RECOVERED BY STEP", name)
        sys.exit(0)
print("scope still out of step")
sys.exit(1)
