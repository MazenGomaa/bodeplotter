"""Step 3: list VISA resources per backend, plus what raw libusb can see."""
import traceback

import pyvisa

from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, save

out = {"pyvisa": pyvisa.__version__, "backends": {}, "libusb": {}}

for backend in ("@py", "@ivi"):
    entry = {}
    try:
        rm = pyvisa.ResourceManager("" if backend == "@ivi" else backend)
        entry["visalib"] = str(rm.visalib)
        entry["resources"] = list(rm.list_resources("?*"))
        rm.close()
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
    out["backends"][backend] = entry
    print(backend, entry)

# Raw libusb view: can the device be seen, and can it be opened?
try:
    import libusb_package
    import usb.core

    for name, vid, pid in (("scope", SCOPE_VID, SCOPE_PID), ("gen", GEN_VID, GEN_PID)):
        e = {}
        dev = libusb_package.find(idVendor=vid, idProduct=pid)
        e["found"] = dev is not None
        if dev is not None:
            try:
                e["serial"] = dev.serial_number
                e["product"] = dev.product
                e["manufacturer"] = dev.manufacturer
                cfg = dev.get_active_configuration()
                e["interfaces"] = [
                    {
                        "class": i.bInterfaceClass,
                        "subclass": i.bInterfaceSubClass,
                        "protocol": i.bInterfaceProtocol,
                        "endpoints": [hex(ep.bEndpointAddress) for ep in i],
                    }
                    for i in cfg
                ]
            except Exception as ex:
                e["open_error"] = f"{type(ex).__name__}: {ex}"
        out["libusb"][name] = e
        print("libusb", name, e)
except Exception:
    out["libusb"]["error"] = traceback.format_exc()
    print(out["libusb"]["error"])

print("saved", save("s03_visa_list.json", out))
